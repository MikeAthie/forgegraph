package usecase

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
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

func (p *recordingRuntimeIntentPublisher) All() []*port.RuntimeIntentEnvelope {
	p.mu.Lock()
	defer p.mu.Unlock()
	result := make([]*port.RuntimeIntentEnvelope, 0, len(p.intents))
	for _, intent := range p.intents {
		cloned := *intent
		cloned.Payload = cloneMapAny(intent.Payload)
		result = append(result, &cloned)
	}
	return result
}

type failingRuntimeIntentPublisher struct {
	intentType string
	err        error
}

func (p failingRuntimeIntentPublisher) Publish(ctx context.Context, intent *port.RuntimeIntentEnvelope) error {
	_ = ctx
	if intent != nil && (p.intentType == "" || intent.IntentType == p.intentType) {
		if p.err != nil {
			return p.err
		}
		return errors.New("runtime intent publish failed")
	}
	return nil
}

type repositoryAttemptCall struct {
	method    string
	attemptID string
}

type recordingAttemptRepository struct {
	*mockRepository

	mu    sync.Mutex
	calls []repositoryAttemptCall

	updateRunStatusErr error
	createNodeRunErr   error
	updateNodeRunErr   error
	saveCheckpointErr  error
	setRunEndedErr     error
}

func newRecordingAttemptRepository(base *mockRepository) *recordingAttemptRepository {
	return &recordingAttemptRepository{mockRepository: base}
}

func (r *recordingAttemptRepository) record(method string, ctx context.Context) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.calls = append(r.calls, repositoryAttemptCall{
		method:    method,
		attemptID: port.AttemptIDFrom(ctx),
	})
}

func (r *recordingAttemptRepository) attemptsFor(method string) []string {
	r.mu.Lock()
	defer r.mu.Unlock()
	attempts := make([]string, 0)
	for _, call := range r.calls {
		if call.method == method {
			attempts = append(attempts, call.attemptID)
		}
	}
	return attempts
}

func (r *recordingAttemptRepository) UpdateRunStatus(ctx context.Context, runID, status string) error {
	r.record("UpdateRunStatus", ctx)
	if r.updateRunStatusErr != nil {
		return r.updateRunStatusErr
	}
	return r.mockRepository.UpdateRunStatus(ctx, runID, status)
}

func (r *recordingAttemptRepository) CreateNodeRun(ctx context.Context, nodeRun *entity.NodeRun) error {
	r.record("CreateNodeRun", ctx)
	if r.createNodeRunErr != nil {
		return r.createNodeRunErr
	}
	return r.mockRepository.CreateNodeRun(ctx, nodeRun)
}

func (r *recordingAttemptRepository) UpdateNodeRun(ctx context.Context, nodeRun *entity.NodeRun) error {
	r.record("UpdateNodeRun", ctx)
	if r.updateNodeRunErr != nil {
		return r.updateNodeRunErr
	}
	return r.mockRepository.UpdateNodeRun(ctx, nodeRun)
}

func (r *recordingAttemptRepository) SetRunEnded(ctx context.Context, runID string, status string, output map[string]any, errorMsg string) error {
	r.record("SetRunEnded", ctx)
	if r.setRunEndedErr != nil {
		return r.setRunEndedErr
	}
	return r.mockRepository.SetRunEnded(ctx, runID, status, output, errorMsg)
}

func (r *recordingAttemptRepository) SaveCheckpoint(ctx context.Context, runID, nodeID string, stepIndex int, stateSnapshot map[string]any, completedNodes []string, skippedNodes []string, graphJSON string) error {
	r.record("SaveCheckpoint", ctx)
	if r.saveCheckpointErr != nil {
		return r.saveCheckpointErr
	}
	return r.mockRepository.SaveCheckpoint(ctx, runID, nodeID, stepIndex, stateSnapshot, completedNodes, skippedNodes, graphJSON)
}

func requireAllAttemptIDs(t *testing.T, intents []*port.RuntimeIntentEnvelope, attemptID string) {
	t.Helper()
	for _, intent := range intents {
		if strings.TrimSpace(intent.AttemptID) == "" {
			t.Fatalf("intent %s has empty attempt_id", intent.IntentType)
		}
		if intent.AttemptID != attemptID {
			t.Fatalf("intent %s attempt_id = %q, want %q", intent.IntentType, intent.AttemptID, attemptID)
		}
	}
}

func requireRepositoryAttempts(t *testing.T, repo *recordingAttemptRepository, method string, attemptID string) {
	t.Helper()
	attempts := repo.attemptsFor(method)
	if len(attempts) == 0 {
		t.Fatalf("expected repository method %s to be called", method)
	}
	for _, observed := range attempts {
		if observed != attemptID {
			t.Fatalf("%s attempt_id = %q, want %q; all=%v", method, observed, attemptID, attempts)
		}
	}
}

func seedPausedHumanGateRun(t *testing.T, repo *mockRepository, runID string, graphJSON string) {
	t.Helper()
	if err := repo.UpdateRunStatus(context.Background(), runID, string(value.RunStatusPaused)); err != nil {
		t.Fatalf("seed run: %v", err)
	}
	if err := repo.SavePauseState(
		context.Background(),
		runID,
		"gate",
		map[string]any{"input.ticket": "FG-1"},
		nil,
		nil,
		graphJSON,
		"tenant-1",
	); err != nil {
		t.Fatalf("seed pause state: %v", err)
	}
	if err := repo.CreateNodeRun(context.Background(), &entity.NodeRun{
		ID:        fmt.Sprintf("%s-gate-1", runID),
		RunID:     runID,
		NodeID:    "gate",
		NodeType:  string(value.NodeTypeHumanGate),
		Status:    string(value.NodeRunStatusWaiting),
		Attempt:   1,
		StartedAt: time.Now().UTC(),
	}); err != nil {
		t.Fatalf("seed node run: %v", err)
	}
}

func makeGraphJSONWithMetadata(nodes []entity.Node, edges []entity.Edge, metadata map[string]any) string {
	graph := entity.Graph{
		Nodes:    nodes,
		Edges:    edges,
		Metadata: metadata,
	}
	data, _ := json.Marshal(graph)
	return string(data)
}

func waitForSchedulerInactive(t *testing.T, scheduler *Scheduler, runID string) {
	t.Helper()
	waitForRuntimeCondition(t, 2*time.Second, func() bool {
		return !scheduler.IsRunActive(runID)
	}, fmt.Sprintf("run %s remained active", runID))
}

func waitForRuntimeCondition(t *testing.T, timeout time.Duration, condition func() bool, failureMessage string) {
	t.Helper()
	if condition() {
		return
	}
	timer := time.NewTimer(timeout)
	defer timer.Stop()
	ticker := time.NewTicker(10 * time.Millisecond)
	defer ticker.Stop()
	for {
		select {
		case <-timer.C:
			t.Fatal(failureMessage)
		case <-ticker.C:
			if condition() {
				return
			}
		}
	}
}

func TestSchedulerStartRunFailsClosedWhenRunStartWriteFails(t *testing.T) {
	engine := NewTestEngine(t, 1)
	recordingRepo := newRecordingAttemptRepository(engine.Repo)
	recordingRepo.updateRunStatusErr = errors.New("backend unavailable on start")
	engine.Scheduler.repository = recordingRepo

	transformExec := engine.RegisterExecutor(string(value.NodeTypeTransform), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewSuccessResult(map[string]any{"prepared": true}), nil
	})
	engine.RegisterExecutor(string(value.NodeTypeOutput), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewSuccessResult(map[string]any{"done": true}), nil
	})

	runID := "run-start-write-fails-closed"
	graphJSON := makeGraphJSONWithMetadata(
		[]entity.Node{
			{ID: "start", Type: string(value.NodeTypeTransform), Name: "Start", Config: map[string]any{}},
			{ID: "output", Type: string(value.NodeTypeOutput), Name: "Output", Config: map[string]any{}},
		},
		[]entity.Edge{{From: "start", To: "output"}},
		map[string]any{"backend_attempt_id": "attempt-start-fails-closed"},
	)

	err := engine.Scheduler.StartRun(context.Background(), runID, graphJSON, "{}", "", "", "tenant-1", "")
	if err == nil {
		t.Fatal("expected start to fail when backend cannot persist running state")
	}
	if !strings.Contains(err.Error(), "critical run start state write failed") {
		t.Fatalf("unexpected error: %v", err)
	}
	if transformExec.getExecuteCount() != 0 {
		t.Fatalf("expected no node execution after start state write failure, got %d", transformExec.getExecuteCount())
	}
	if engine.Scheduler.IsRunActive(runID) {
		t.Fatalf("run should not remain active after start state write failure")
	}
}

func TestSchedulerStartRunFailsClosedWhenResumeSnapshotLookupFails(t *testing.T) {
	engine := NewTestEngine(t, 1)
	engine.Repo.loadRunSnapshotErr = errors.New("backend snapshot unavailable")

	transformExec := engine.RegisterExecutor(string(value.NodeTypeTransform), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewSuccessResult(map[string]any{"prepared": true}), nil
	})

	runID := "run-snapshot-lookup-fails-closed"
	graphJSON := makeGraphJSONWithMetadata(
		[]entity.Node{
			{ID: "start", Type: string(value.NodeTypeTransform), Name: "Start", Config: map[string]any{}},
		},
		nil,
		map[string]any{"backend_attempt_id": "attempt-snapshot-lookup-fails"},
	)

	err := engine.Scheduler.StartRun(context.Background(), runID, graphJSON, "{}", "", "", "tenant-1", "")
	if err == nil {
		t.Fatal("expected start to fail when backend resume snapshot lookup fails")
	}
	if !strings.Contains(err.Error(), "failed to load backend-owned resume snapshot") {
		t.Fatalf("unexpected error: %v", err)
	}
	if transformExec.getExecuteCount() != 0 {
		t.Fatalf("expected no node execution after snapshot lookup failure, got %d", transformExec.getExecuteCount())
	}
	if engine.Scheduler.IsRunActive(runID) {
		t.Fatalf("run should not remain active after snapshot lookup failure")
	}
}

func TestSchedulerStartRunFailsClosedWhenResumeSnapshotIsInvalid(t *testing.T) {
	engine := NewTestEngine(t, 1)
	runID := "run-invalid-snapshot-fails-closed"

	engine.Repo.runsMu.Lock()
	engine.Repo.runs[runID] = &entity.Run{
		ID:        runID,
		Status:    string(value.RunStatusRunning),
		InputJSON: map[string]any{"query": "backend-owned input"},
	}
	engine.Repo.runsMu.Unlock()

	engine.Repo.snapshotsMu.Lock()
	engine.Repo.snapshots[runID] = &port.RunResumeSnapshot{
		RunID:             runID,
		LastCompletedNode: "start",
		NextNode:          "output",
		AttemptID:         "attempt-invalid-snapshot",
		UpdatedAt:         time.Now(),
	}
	engine.Repo.snapshotsMu.Unlock()

	transformExec := engine.RegisterExecutor(string(value.NodeTypeTransform), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewSuccessResult(map[string]any{"prepared": true}), nil
	})
	outputExec := engine.RegisterExecutor(string(value.NodeTypeOutput), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewSuccessResult(map[string]any{"done": true}), nil
	})

	graphJSON := makeGraphJSONWithMetadata(
		[]entity.Node{
			{ID: "start", Type: string(value.NodeTypeTransform), Name: "Start", Config: map[string]any{}},
			{ID: "output", Type: string(value.NodeTypeOutput), Name: "Output", Config: map[string]any{}},
		},
		[]entity.Edge{{From: "start", To: "output"}},
		map[string]any{"backend_attempt_id": "attempt-invalid-snapshot"},
	)

	err := engine.Scheduler.StartRun(context.Background(), runID, graphJSON, "{}", "", "", "tenant-1", "")
	if err == nil {
		t.Fatal("expected start to fail when backend resume snapshot is inconsistent")
	}
	if !strings.Contains(err.Error(), "has no durable completed node run") {
		t.Fatalf("unexpected error: %v", err)
	}
	if transformExec.getExecuteCount() != 0 {
		t.Fatalf("expected no transform execution after invalid snapshot, got %d", transformExec.getExecuteCount())
	}
	if outputExec.getExecuteCount() != 0 {
		t.Fatalf("expected no output execution after invalid snapshot, got %d", outputExec.getExecuteCount())
	}
	if engine.Scheduler.IsRunActive(runID) {
		t.Fatalf("run should not remain active after invalid snapshot")
	}
}

func TestSchedulerNodeStartWriteFailureStopsBeforeExecutor(t *testing.T) {
	engine := NewTestEngine(t, 1)
	recordingRepo := newRecordingAttemptRepository(engine.Repo)
	recordingRepo.createNodeRunErr = errors.New("backend unavailable on node start")
	engine.Scheduler.repository = recordingRepo

	transformExec := engine.RegisterExecutor(string(value.NodeTypeTransform), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewSuccessResult(map[string]any{"prepared": true}), nil
	})
	outputExec := engine.RegisterExecutor(string(value.NodeTypeOutput), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewSuccessResult(map[string]any{"done": true}), nil
	})

	runID := "run-node-start-write-fails-closed"
	graphJSON := makeGraphJSONWithMetadata(
		[]entity.Node{
			{ID: "start", Type: string(value.NodeTypeTransform), Name: "Start", Config: map[string]any{}},
			{ID: "output", Type: string(value.NodeTypeOutput), Name: "Output", Config: map[string]any{}},
		},
		[]entity.Edge{{From: "start", To: "output"}},
		map[string]any{"backend_attempt_id": "attempt-node-start-fails-closed"},
	)

	engine.StartRun(runID, graphJSON, "{}")
	snapshot := engine.AwaitRunStatus(runID, string(value.RunStatusFailed))
	if !strings.Contains(snapshot.Error, "failed to persist node start") {
		t.Fatalf("expected typed node-start persistence failure, got %q", snapshot.Error)
	}
	if transformExec.getExecuteCount() != 0 {
		t.Fatalf("expected transform executor not to run, got %d", transformExec.getExecuteCount())
	}
	if outputExec.getExecuteCount() != 0 {
		t.Fatalf("expected downstream output not to run, got %d", outputExec.getExecuteCount())
	}
	if countEvents(engine.Bus.All(), port.EventTypeNodeStarted) != 0 {
		t.Fatalf("expected no node_started event before backend node-start commit")
	}
}

func TestSchedulerCheckpointWriteFailureStopsDownstreamExecution(t *testing.T) {
	engine := NewTestEngine(t, 1)
	recordingRepo := newRecordingAttemptRepository(engine.Repo)
	recordingRepo.saveCheckpointErr = errors.New("backend unavailable on checkpoint")
	engine.Scheduler.repository = recordingRepo

	transformExec := engine.RegisterExecutor(string(value.NodeTypeTransform), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewSuccessResult(map[string]any{"prepared": true}), nil
	})
	outputExec := engine.RegisterExecutor(string(value.NodeTypeOutput), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewSuccessResult(map[string]any{"done": true}), nil
	})

	runID := "run-checkpoint-write-fails-closed"
	graphJSON := makeGraphJSONWithMetadata(
		[]entity.Node{
			{ID: "start", Type: string(value.NodeTypeTransform), Name: "Start", Config: map[string]any{}},
			{ID: "output", Type: string(value.NodeTypeOutput), Name: "Output", Config: map[string]any{}},
		},
		[]entity.Edge{{From: "start", To: "output"}},
		map[string]any{"backend_attempt_id": "attempt-checkpoint-fails-closed"},
	)

	engine.StartRun(runID, graphJSON, "{}")
	engine.AwaitBlockedAttempt(runID, "start", 1)
	engine.Release(runID, "start")
	snapshot := engine.AwaitRunStatus(runID, string(value.RunStatusFailed))
	if !strings.Contains(snapshot.Error, "failed to commit checkpoint") {
		t.Fatalf("expected checkpoint failure, got %q", snapshot.Error)
	}
	if transformExec.getNodeExecuteCount("start") != 1 {
		t.Fatalf("expected start to run once, got %d", transformExec.getNodeExecuteCount("start"))
	}
	if outputExec.getExecuteCount() != 0 {
		t.Fatalf("expected downstream output not to run after checkpoint failure, got %d", outputExec.getExecuteCount())
	}
}

func TestSchedulerCompletionWriteFailureDoesNotEmitCompletedEvent(t *testing.T) {
	engine := NewTestEngine(t, 1)
	recordingRepo := newRecordingAttemptRepository(engine.Repo)
	recordingRepo.setRunEndedErr = errors.New("backend unavailable on completion")
	engine.Scheduler.repository = recordingRepo

	outputExec := engine.RegisterExecutor(string(value.NodeTypeOutput), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewSuccessResult(map[string]any{"done": true}), nil
	})

	runID := "run-completion-write-fails-closed"
	graphJSON := makeGraphJSONWithMetadata(
		[]entity.Node{{ID: "output", Type: string(value.NodeTypeOutput), Name: "Output", Config: map[string]any{}}},
		nil,
		map[string]any{"backend_attempt_id": "attempt-completion-fails-closed"},
	)

	engine.StartRun(runID, graphJSON, "{}")
	engine.AwaitBlockedAttempt(runID, "output", 1)
	engine.Release(runID, "output")
	waitForSchedulerInactive(t, engine.Scheduler, runID)

	if outputExec.getExecuteCount() != 1 {
		t.Fatalf("expected output to execute once, got %d", outputExec.getExecuteCount())
	}
	if countEvents(engine.Bus.All(), port.EventTypeRunCompleted) != 0 {
		t.Fatalf("expected no run_completed event when backend completion write fails")
	}
	if status := engine.Repo.getRunStatus(runID); status != string(value.RunStatusRunning) {
		t.Fatalf("run status = %q, want running because completion was not backend-committed", status)
	}
}

func TestSchedulerResumeAckFailureStopsBeforeDownstreamExecution(t *testing.T) {
	engine := NewTestEngine(t, 1)
	engine.Scheduler.SetRuntimeIntentPublisher(
		failingRuntimeIntentPublisher{
			intentType: "ack_run_resumed",
			err:        errors.New("backend unavailable on resume ack"),
		},
		RuntimeWriteModePauseIntents,
	)

	outputExec := engine.RegisterExecutor(string(value.NodeTypeOutput), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewSuccessResult(map[string]any{"done": true}), nil
	})

	runID := "run-resume-ack-fails-closed"
	graphJSON := makeGraphJSONWithMetadata(
		[]entity.Node{
			{ID: "gate", Type: string(value.NodeTypeHumanGate), Name: "Gate", Config: map[string]any{}},
			{ID: "output", Type: string(value.NodeTypeOutput), Name: "Output", Config: map[string]any{}},
		},
		[]entity.Edge{{From: "gate", To: "output"}},
		map[string]any{"backend_attempt_id": "attempt-resume-ack-fails-closed"},
	)
	seedPausedHumanGateRun(t, engine.Repo, runID, graphJSON)

	err := engine.Scheduler.ResumeRun(
		context.Background(),
		runID,
		"gate",
		`{"approved":true,"_forgegraph_resume_attempt_id":"resume-attempt-ack-down"}`,
	)
	if err == nil {
		t.Fatal("expected resume ack failure")
	}
	if !strings.Contains(err.Error(), "failed to publish ack_run_resumed intent") {
		t.Fatalf("unexpected error: %v", err)
	}
	if outputExec.getExecuteCount() != 0 {
		t.Fatalf("expected downstream output not to run after resume ack failure, got %d", outputExec.getExecuteCount())
	}
	if countEvents(engine.Bus.All(), port.EventTypeRunResumed) != 0 {
		t.Fatalf("expected no run_resumed event before backend resume ack commit")
	}
}

func TestSchedulerResumeRunRequiresResumeAttemptInRuntimeIntentMode(t *testing.T) {
	engine := NewTestEngine(t, 1)
	publisher := &recordingRuntimeIntentPublisher{}
	engine.Scheduler.SetRuntimeIntentPublisher(publisher, RuntimeWriteModePauseIntents)

	graphJSON := makeGraphJSON(
		[]entity.Node{
			{ID: "gate", Type: string(value.NodeTypeHumanGate), Name: "Gate", Config: map[string]any{}},
			{ID: "output", Type: string(value.NodeTypeOutput), Name: "Output", Config: map[string]any{}},
		},
		[]entity.Edge{{From: "gate", To: "output"}},
	)
	seedPausedHumanGateRun(t, engine.Repo, "run-resume-requires-attempt", graphJSON)

	err := engine.Scheduler.ResumeRun(
		context.Background(),
		"run-resume-requires-attempt",
		"gate",
		`{"approved":true}`,
	)

	if err == nil {
		t.Fatal("expected resume without backend attempt id to fail")
	}
	if !strings.Contains(err.Error(), "resume_attempt_id is required") {
		t.Fatalf("unexpected error: %v", err)
	}
	if publisher.Count() != 0 {
		t.Fatalf("expected no runtime intents without resume attempt, got %d", publisher.Count())
	}
}

func TestSchedulerResumeRunPropagatesResumeAttemptToRuntimeIntents(t *testing.T) {
	engine := NewTestEngine(t, 1)
	publisher := &recordingRuntimeIntentPublisher{}
	recordingRepo := newRecordingAttemptRepository(engine.Repo)
	engine.Scheduler.repository = recordingRepo
	engine.Scheduler.SetRuntimeIntentPublisher(publisher, RuntimeWriteModePauseIntents)

	engine.RegisterExecutor(string(value.NodeTypeOutput), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewSuccessResult(map[string]any{"done": true}), nil
	})

	runID := "run-resume-attempt-propagated"
	resumeAttemptID := "resume-attempt-1"
	graphJSON := makeGraphJSON(
		[]entity.Node{
			{ID: "gate", Type: string(value.NodeTypeHumanGate), Name: "Gate", Config: map[string]any{}},
			{ID: "output", Type: string(value.NodeTypeOutput), Name: "Output", Config: map[string]any{}},
		},
		[]entity.Edge{{From: "gate", To: "output"}},
	)
	seedPausedHumanGateRun(t, engine.Repo, runID, graphJSON)

	engine.ResumeRun(
		runID,
		"gate",
		fmt.Sprintf(`{"approved":true,"feedback":"ship it","_forgegraph_resume_attempt_id":%q}`, resumeAttemptID),
	)
	engine.AwaitBlockedAttempt(runID, "output", 1)
	engine.Release(runID, "output")
	engine.AwaitRunStatus(runID, string(value.RunStatusSucceeded))

	if publisher.CountByIntentType("ack_run_resumed") != 1 {
		t.Fatalf("expected one ack_run_resumed intent, got %d", publisher.CountByIntentType("ack_run_resumed"))
	}
	if publisher.CountByIntentType("node_completed") != 1 {
		t.Fatalf("expected one node_completed intent, got %d", publisher.CountByIntentType("node_completed"))
	}
	requireAllAttemptIDs(t, publisher.All(), resumeAttemptID)
	requireRepositoryAttempts(t, recordingRepo, "UpdateNodeRun", resumeAttemptID)
	requireRepositoryAttempts(t, recordingRepo, "SaveCheckpoint", resumeAttemptID)
	requireRepositoryAttempts(t, recordingRepo, "SetRunEnded", resumeAttemptID)

	resumedEvent := engine.Bus.All()
	foundRunResumed := false
	for _, observed := range resumedEvent {
		if observed.Event.Type == port.EventTypeRunResumed {
			foundRunResumed = true
			if observed.Event.AttemptID != resumeAttemptID {
				t.Fatalf("run_resumed event attempt_id = %q, want %q", observed.Event.AttemptID, resumeAttemptID)
			}
		}
	}
	if !foundRunResumed {
		t.Fatal("expected run_resumed event")
	}
}

func TestSchedulerResumeRunRejectionUsesResumeAttempt(t *testing.T) {
	engine := NewTestEngine(t, 1)
	publisher := &recordingRuntimeIntentPublisher{}
	recordingRepo := newRecordingAttemptRepository(engine.Repo)
	engine.Scheduler.repository = recordingRepo
	engine.Scheduler.SetRuntimeIntentPublisher(publisher, RuntimeWriteModePauseIntents)

	runID := "run-resume-rejected-attempt"
	resumeAttemptID := "resume-attempt-rejected"
	graphJSON := makeGraphJSON(
		[]entity.Node{{ID: "gate", Type: string(value.NodeTypeHumanGate), Name: "Gate", Config: map[string]any{}}},
		nil,
	)
	seedPausedHumanGateRun(t, engine.Repo, runID, graphJSON)

	err := engine.Scheduler.ResumeRun(
		context.Background(),
		runID,
		"gate",
		fmt.Sprintf(`{"approved":false,"feedback":"needs changes","_forgegraph_resume_attempt_id":%q}`, resumeAttemptID),
	)
	if err != nil {
		t.Fatalf("ResumeRun rejected path failed: %v", err)
	}

	requireRepositoryAttempts(t, recordingRepo, "UpdateNodeRun", resumeAttemptID)
	requireRepositoryAttempts(t, recordingRepo, "SetRunEnded", resumeAttemptID)
	if publisher.Count() != 0 {
		t.Fatalf("expected rejected resume to use repository intents only, got scheduler-published intents=%d", publisher.Count())
	}
	if status := engine.Repo.getRunStatus(runID); status != string(value.RunStatusFailed) {
		t.Fatalf("run status = %q, want failed", status)
	}
}

func TestSchedulerResumeRunPropagatesRepositoryWriteFailure(t *testing.T) {
	engine := NewTestEngine(t, 1)
	recordingRepo := newRecordingAttemptRepository(engine.Repo)
	recordingRepo.updateNodeRunErr = errors.New("publish upsert_node_run failed")
	engine.Scheduler.repository = recordingRepo
	engine.Scheduler.SetRuntimeIntentPublisher(&recordingRuntimeIntentPublisher{}, RuntimeWriteModePauseIntents)

	runID := "run-resume-write-failure"
	resumeAttemptID := "resume-attempt-write-failure"
	graphJSON := makeGraphJSON(
		[]entity.Node{
			{ID: "gate", Type: string(value.NodeTypeHumanGate), Name: "Gate", Config: map[string]any{}},
			{ID: "output", Type: string(value.NodeTypeOutput), Name: "Output", Config: map[string]any{}},
		},
		[]entity.Edge{{From: "gate", To: "output"}},
	)
	seedPausedHumanGateRun(t, engine.Repo, runID, graphJSON)

	err := engine.Scheduler.ResumeRun(
		context.Background(),
		runID,
		"gate",
		fmt.Sprintf(`{"approved":true,"_forgegraph_resume_attempt_id":%q}`, resumeAttemptID),
	)

	if err == nil {
		t.Fatal("expected repository write failure")
	}
	if !strings.Contains(err.Error(), "failed to update resumed human gate node run") {
		t.Fatalf("unexpected error: %v", err)
	}
	requireRepositoryAttempts(t, recordingRepo, "UpdateNodeRun", resumeAttemptID)
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

	waitForRuntimeCondition(t, 2*time.Second, func() bool {
		return publisher.CountByIntentType("pause_run") > 0
	}, "expected pause_run intent to be published")
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

	waitForRuntimeCondition(t, 2*time.Second, func() bool {
		return publisher.CountByIntentType("tool_execution_succeeded") > 0
	}, "expected tool_execution_succeeded intent to be published")
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

	waitForRuntimeCondition(t, 2*time.Second, func() bool {
		return engine.Repo.getRunStatus(runID) == string(value.RunStatusFailed)
	}, "expected unsafe tool run to fail")
	if attempts != 1 {
		t.Fatalf("unsafe tool attempts = %d, want 1", attempts)
	}
	if status := engine.Repo.getRunStatus(runID); status != string(value.RunStatusFailed) {
		t.Fatalf("run status = %q", status)
	}
}

func TestSchedulerRecordsRetryOperationBeforeRetryDelay(t *testing.T) {
	engine := NewTestEngine(t, 1)
	publisher := &recordingRuntimeIntentPublisher{}
	engine.Scheduler.SetRuntimeIntentPublisher(publisher, RuntimeWriteModePauseIntents)

	var attempts int
	engine.RegisterExecutor(string(value.NodeTypeTransform), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		attempts++
		return nil, domain.NewRetryableError(context.DeadlineExceeded, "transient backend transport failure")
	})
	engine.RegisterExecutor(string(value.NodeTypeOutput), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewSuccessResult(map[string]any{"done": true}), nil
	})

	runID := "run-record-retry-operation"
	graphJSON := makeGraphJSON(
		[]entity.Node{
			{
				ID:     "retry",
				Type:   string(value.NodeTypeTransform),
				Name:   "Retry",
				Config: map[string]any{},
				RetryPolicy: &entity.RetryPolicy{
					MaxAttempts:     2,
					BackoffMs:       5000,
					BackoffStrategy: "fixed",
				},
			},
			{ID: "output", Type: string(value.NodeTypeOutput), Name: "Output", Config: map[string]any{}},
		},
		[]entity.Edge{{From: "retry", To: "output"}},
	)

	engine.StartRun(runID, graphJSON, "{}")
	engine.AwaitBlockedAttempt(runID, "retry", 1)
	engine.Release(runID, "retry")

	waitForRuntimeCondition(t, 2*time.Second, func() bool {
		return publisher.CountByIntentType("record_retry_operation") > 0
	}, "expected record_retry_operation intent to be published")
	intent := publisher.LastByIntentType("record_retry_operation")
	if intent == nil {
		t.Fatal("expected record_retry_operation intent")
	}
	if attempts != 1 {
		t.Fatalf("attempts before retry delay = %d, want 1", attempts)
	}
	if intent.Payload["node_id"] != "retry" {
		t.Fatalf("node_id = %#v", intent.Payload["node_id"])
	}
	if fmt.Sprint(intent.Payload["attempt_number"]) != "2" {
		t.Fatalf("attempt_number = %#v", intent.Payload["attempt_number"])
	}
	if fmt.Sprint(intent.Payload["parent_attempt_number"]) != "1" {
		t.Fatalf("parent_attempt_number = %#v", intent.Payload["parent_attempt_number"])
	}
	if fmt.Sprint(intent.Payload["max_attempts"]) != "2" {
		t.Fatalf("max_attempts = %#v", intent.Payload["max_attempts"])
	}
	if fmt.Sprint(intent.Payload["retry_delay_ms"]) != "5000" {
		t.Fatalf("retry_delay_ms = %#v", intent.Payload["retry_delay_ms"])
	}
	if intent.Payload["terminal_fallback"] != "fail_run" {
		t.Fatalf("terminal_fallback = %#v", intent.Payload["terminal_fallback"])
	}
}

func TestSchedulerFailsClosedWhenRetryOperationCannotBeRecorded(t *testing.T) {
	engine := NewTestEngine(t, 1)
	engine.Scheduler.SetRuntimeIntentPublisher(
		failingRuntimeIntentPublisher{intentType: "record_retry_operation"},
		RuntimeWriteModePauseIntents,
	)

	var attempts int
	engine.RegisterExecutor(string(value.NodeTypeTransform), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		attempts++
		return nil, domain.NewRetryableError(context.DeadlineExceeded, "transient backend transport failure")
	})
	engine.RegisterExecutor(string(value.NodeTypeOutput), func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewSuccessResult(map[string]any{"done": true}), nil
	})

	runID := "run-retry-record-fails-closed"
	graphJSON := makeGraphJSON(
		[]entity.Node{
			{
				ID:     "retry",
				Type:   string(value.NodeTypeTransform),
				Name:   "Retry",
				Config: map[string]any{},
				RetryPolicy: &entity.RetryPolicy{
					MaxAttempts:     3,
					BackoffMs:       1,
					BackoffStrategy: "fixed",
				},
			},
			{ID: "output", Type: string(value.NodeTypeOutput), Name: "Output", Config: map[string]any{}},
		},
		[]entity.Edge{{From: "retry", To: "output"}},
	)

	engine.StartRun(runID, graphJSON, "{}")
	engine.AwaitBlockedAttempt(runID, "retry", 1)
	engine.Release(runID, "retry")
	engine.AwaitRunStatus(runID, string(value.RunStatusFailed))

	if attempts != 1 {
		t.Fatalf("attempts after retry record failure = %d, want 1", attempts)
	}
	if _, ok := engine.Repo.nodeRuns[fmt.Sprintf("%s-output-1", runID)]; ok {
		t.Fatal("downstream output node executed after retry record failure")
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
