package usecase

import (
	"context"
	"encoding/json"
	"sync"
	"testing"
	"time"

	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/domain"
	"github.com/forgegraph/engine/domain/entity"
	"github.com/forgegraph/engine/domain/value"
)

type recordingRuntimeIntentPublisher struct {
	mu      sync.Mutex
	intents []*port.RuntimeIntentEnvelope
}

func (p *recordingRuntimeIntentPublisher) Publish(ctx context.Context, intent *port.RuntimeIntentEnvelope) error {
	_ = ctx
	p.mu.Lock()
	defer p.mu.Unlock()
	cloned := *intent
	cloned.Payload = cloneMapAny(intent.Payload)
	p.intents = append(p.intents, &cloned)
	return nil
}

func (p *recordingRuntimeIntentPublisher) Count() int {
	p.mu.Lock()
	defer p.mu.Unlock()
	return len(p.intents)
}

func (p *recordingRuntimeIntentPublisher) CountByIntentType(intentType string) int {
	p.mu.Lock()
	defer p.mu.Unlock()
	count := 0
	for _, intent := range p.intents {
		if intent.IntentType == intentType {
			count++
		}
	}
	return count
}

func (p *recordingRuntimeIntentPublisher) Last() *port.RuntimeIntentEnvelope {
	p.mu.Lock()
	defer p.mu.Unlock()
	if len(p.intents) == 0 {
		return nil
	}
	return p.intents[len(p.intents)-1]
}

func (p *recordingRuntimeIntentPublisher) LastByIntentType(intentType string) *port.RuntimeIntentEnvelope {
	p.mu.Lock()
	defer p.mu.Unlock()
	for i := len(p.intents) - 1; i >= 0; i-- {
		if p.intents[i].IntentType == intentType {
			cloned := *p.intents[i]
			cloned.Payload = cloneMapAny(p.intents[i].Payload)
			return &cloned
		}
	}
	return nil
}

func TestSchedulerPauseIntentActiveModePublishesWithoutLegacyPauseWrites(t *testing.T) {
	engine := NewTestEngine(t, 2)
	publisher := &recordingRuntimeIntentPublisher{}
	engine.Scheduler.SetRuntimeIntentPublisher(publisher, RuntimeWriteModePauseIntents)

	engine.RegisterExecutor(string(value.NodeTypeTransform), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewSuccessResult(map[string]any{"prepared": "ready"}), nil
	})
	engine.RegisterExecutor(string(value.NodeTypeHumanGate), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewPauseResult(map[string]any{"prompt_message": "approve"}), nil
	})
	engine.RegisterExecutor(string(value.NodeTypeOutput), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewSuccessResult(map[string]any{"done": true}), nil
	})

	runID := "run-pause-intents-active"
	graphJSON := makeGraphJSON(
		[]entity.Node{
			{ID: "start", Type: string(value.NodeTypeTransform), Name: "Start", Config: map[string]any{}},
			{ID: "gate", Type: string(value.NodeTypeHumanGate), Name: "Gate", Config: map[string]any{}},
			{ID: "output", Type: string(value.NodeTypeOutput), Name: "Output", Config: map[string]any{}},
		},
		[]entity.Edge{
			{From: "start", To: "gate"},
			{From: "gate", To: "output"},
		},
	)

	engine.StartRun(runID, graphJSON, "{}")
	engine.AwaitBlockedAttempt(runID, "start", 1)
	engine.Release(runID, "start")
	engine.AwaitBlockedAttempt(runID, "gate", 1)
	engine.Release(runID, "gate")

	deadline := time.Now().Add(2 * time.Second)
	for publisher.CountByIntentType("pause_run") == 0 && time.Now().Before(deadline) {
		time.Sleep(10 * time.Millisecond)
	}
	if publisher.CountByIntentType("pause_run") != 1 {
		t.Fatalf("expected one pause_run intent to be published, got %d", publisher.CountByIntentType("pause_run"))
	}
	if _, ok := engine.Repo.pauses[runID]; ok {
		t.Fatalf("expected active pause intent mode to skip legacy pause state writes")
	}
	if status := engine.Repo.getRunStatus(runID); status != string(value.RunStatusRunning) {
		t.Fatalf("expected legacy run status to remain running until backend applies intent, got %q", status)
	}
	if countEvents(engine.Bus.All(), port.EventTypeRunPaused) != 0 {
		t.Fatalf("expected active pause intent mode to suppress run_paused events")
	}

	intent := publisher.LastByIntentType("pause_run")
	if intent == nil {
		t.Fatal("expected published pause intent")
	}
	if intent.IntentType != "pause_run" {
		t.Fatalf("expected pause_run intent, got %q", intent.IntentType)
	}
	if intent.Payload["node_id"] != "gate" {
		t.Fatalf("expected gate node_id in pause intent, got %#v", intent.Payload["node_id"])
	}
}

func TestSchedulerPublishesToolExecutionLifecycleIntents(t *testing.T) {
	engine := NewTestEngine(t, 2)
	publisher := &recordingRuntimeIntentPublisher{}
	engine.Scheduler.SetRuntimeIntentPublisher(publisher, RuntimeWriteModeLegacySync)

	engine.RegisterExecutor(string(value.NodeTypeTool), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewSuccessResult(map[string]any{"ok": true}), nil
	})
	engine.RegisterExecutor(string(value.NodeTypeOutput), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewSuccessResult(map[string]any{"done": true}), nil
	})

	runID := "run-tool-execution-lifecycle"
	graph := entity.Graph{
		Nodes: []entity.Node{
			{
				ID:   "tool_1",
				Type: string(value.NodeTypeTool),
				Name: "Tool",
				Config: map[string]any{
					"tool":              "email.send",
					"version":           "1.0.0",
					"tool_execution_id": "11111111-1111-1111-1111-111111111111",
					"idempotency_key":   "idem-tool-1",
					"side_effect_class": "idempotent",
				},
			},
			{ID: "output", Type: string(value.NodeTypeOutput), Name: "Output", Config: map[string]any{}},
		},
		Edges: []entity.Edge{{From: "tool_1", To: "output"}},
		Metadata: map[string]any{
			"engine_contract_version": "2",
			"backend_attempt_id":      "backend-attempt-tool-lifecycle",
		},
	}
	graphJSONBytes, err := json.Marshal(graph)
	if err != nil {
		t.Fatalf("marshal graph: %v", err)
	}

	engine.StartRun(runID, string(graphJSONBytes), "{}")
	engine.AwaitBlockedAttempt(runID, "tool_1", 1)
	engine.Release(runID, "tool_1")
	engine.AwaitBlockedAttempt(runID, "output", 1)
	engine.Release(runID, "output")

	deadline := time.Now().Add(2 * time.Second)
	for publisher.CountByIntentType("tool_execution_succeeded") == 0 && time.Now().Before(deadline) {
		time.Sleep(10 * time.Millisecond)
	}
	if publisher.CountByIntentType("tool_execution_started") != 1 {
		t.Fatalf("expected one tool_execution_started intent, got %d", publisher.CountByIntentType("tool_execution_started"))
	}
	if publisher.CountByIntentType("tool_execution_succeeded") != 1 {
		t.Fatalf("expected one tool_execution_succeeded intent, got %d", publisher.CountByIntentType("tool_execution_succeeded"))
	}
	intent := publisher.LastByIntentType("tool_execution_succeeded")
	if intent.AttemptID != "backend-attempt-tool-lifecycle" {
		t.Fatalf("attempt_id = %q", intent.AttemptID)
	}
	if intent.Payload["tool_execution_id"] != "11111111-1111-1111-1111-111111111111" {
		t.Fatalf("tool_execution_id = %#v", intent.Payload["tool_execution_id"])
	}
	if intent.Payload["idempotency_key"] != "idem-tool-1" {
		t.Fatalf("idempotency_key = %#v", intent.Payload["idempotency_key"])
	}
}

func TestSchedulerBlocksAutomaticRetryForUnsafeToolExecution(t *testing.T) {
	engine := NewTestEngine(t, 2)
	var attempts int
	engine.RegisterExecutor(string(value.NodeTypeTool), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		attempts++
		return nil, domain.NewRetryableError(context.DeadlineExceeded, "retryable unsafe tool failure")
	})
	engine.RegisterExecutor(string(value.NodeTypeOutput), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewSuccessResult(map[string]any{"done": true}), nil
	})

	runID := "run-tool-unsafe-retry-blocked"
	graphJSON := makeGraphJSON(
		[]entity.Node{
			{
				ID:   "tool_1",
				Type: string(value.NodeTypeTool),
				Name: "Tool",
				Config: map[string]any{
					"tool":              "email.send",
					"version":           "1.0.0",
					"tool_execution_id": "11111111-1111-1111-1111-111111111111",
					"idempotency_key":   "idem-tool-1",
					"side_effect_class": "non_idempotent",
				},
				RetryPolicy: &entity.RetryPolicy{MaxAttempts: 3, BackoffMs: 1, BackoffStrategy: "fixed"},
			},
			{ID: "output", Type: string(value.NodeTypeOutput), Name: "Output", Config: map[string]any{}},
		},
		[]entity.Edge{{From: "tool_1", To: "output"}},
	)

	engine.StartRun(runID, graphJSON, "{}")
	engine.AwaitBlockedAttempt(runID, "tool_1", 1)
	engine.Release(runID, "tool_1")

	deadline := time.Now().Add(2 * time.Second)
	for engine.Repo.getRunStatus(runID) != string(value.RunStatusFailed) && time.Now().Before(deadline) {
		time.Sleep(10 * time.Millisecond)
	}
	if attempts != 1 {
		t.Fatalf("unsafe tool attempts = %d, want 1", attempts)
	}
	if status := engine.Repo.getRunStatus(runID); status != string(value.RunStatusFailed) {
		t.Fatalf("run status = %q", status)
	}
}

func TestSchedulerPauseIntentShadowModePublishesAndPreservesLegacyPauseWrites(t *testing.T) {
	engine := NewTestEngine(t, 2)
	publisher := &recordingRuntimeIntentPublisher{}
	engine.Scheduler.SetRuntimeIntentPublisher(publisher, RuntimeWriteModePauseIntentsShadow)

	engine.RegisterExecutor(string(value.NodeTypeTransform), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewSuccessResult(map[string]any{"prepared": "ready"}), nil
	})
	engine.RegisterExecutor(string(value.NodeTypeHumanGate), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewPauseResult(map[string]any{"prompt_message": "approve"}), nil
	})
	engine.RegisterExecutor(string(value.NodeTypeOutput), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewSuccessResult(map[string]any{"done": true}), nil
	})

	runID := "run-pause-intents-shadow"
	graphJSON := makeGraphJSON(
		[]entity.Node{
			{ID: "start", Type: string(value.NodeTypeTransform), Name: "Start", Config: map[string]any{}},
			{ID: "gate", Type: string(value.NodeTypeHumanGate), Name: "Gate", Config: map[string]any{}},
			{ID: "output", Type: string(value.NodeTypeOutput), Name: "Output", Config: map[string]any{}},
		},
		[]entity.Edge{
			{From: "start", To: "gate"},
			{From: "gate", To: "output"},
		},
	)

	engine.StartRun(runID, graphJSON, "{}")
	engine.AwaitBlockedAttempt(runID, "start", 1)
	engine.Release(runID, "start")
	engine.AwaitBlockedAttempt(runID, "gate", 1)
	engine.Release(runID, "gate")

	snapshot := engine.AwaitRunStatus(runID, string(value.RunStatusPaused))
	if snapshot.PausedNodeID != "gate" {
		t.Fatalf("expected paused node gate, got %q", snapshot.PausedNodeID)
	}
	if publisher.CountByIntentType("pause_run") != 1 {
		t.Fatalf("expected one pause_run intent in shadow mode, got %d", publisher.CountByIntentType("pause_run"))
	}
	if countEvents(engine.Bus.All(), port.EventTypeRunPaused) != 1 {
		t.Fatalf("expected shadow mode to preserve run_paused events")
	}
}
