package usecase

import (
	"context"
	"sync"
	"testing"
	"time"

	"github.com/forgegraph/engine/application/port"
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
