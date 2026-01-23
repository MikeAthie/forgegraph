package usecase

import (
	"context"
	"encoding/json"
	"fmt"
	"sync"
	"testing"
	"time"

	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/domain"
	"github.com/forgegraph/engine/domain/entity"
	"github.com/forgegraph/engine/domain/value"
)

// mockRepository implements port.RunRepository for testing
type mockRepository struct {
	mu       sync.Mutex
	runs     map[string]*entity.Run
	nodeRuns map[string]*entity.NodeRun
	pauses   map[string]mockPauseState
}

type mockPauseState struct {
	pausedNodeID   string
	stateSnapshot  map[string]any
	completedNodes []string
	graphJSON      string
}

func newMockRepository() *mockRepository {
	return &mockRepository{
		runs:     make(map[string]*entity.Run),
		nodeRuns: make(map[string]*entity.NodeRun),
		pauses:   make(map[string]mockPauseState),
	}
}

func (r *mockRepository) GetRun(ctx context.Context, runID string) (*entity.Run, error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	run, ok := r.runs[runID]
	if !ok {
		return nil, domain.ErrRunNotFound
	}
	return run, nil
}

func (r *mockRepository) UpdateRunStatus(ctx context.Context, runID, status string) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	if r.runs[runID] == nil {
		r.runs[runID] = &entity.Run{ID: runID}
	}
	r.runs[runID].Status = status
	return nil
}

func (r *mockRepository) UpdateRunOutput(ctx context.Context, runID string, output map[string]any) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	if r.runs[runID] == nil {
		r.runs[runID] = &entity.Run{ID: runID}
	}
	r.runs[runID].OutputJSON = output
	return nil
}

func (r *mockRepository) UpdateRunError(ctx context.Context, runID, errorMsg string) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	if r.runs[runID] == nil {
		r.runs[runID] = &entity.Run{ID: runID}
	}
	r.runs[runID].ErrorMessage = errorMsg
	return nil
}

func (r *mockRepository) SetRunEnded(ctx context.Context, runID, status string, output map[string]any, errorMsg string) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	if r.runs[runID] == nil {
		r.runs[runID] = &entity.Run{ID: runID}
	}
	r.runs[runID].Status = status
	r.runs[runID].OutputJSON = output
	r.runs[runID].ErrorMessage = errorMsg
	return nil
}

func (r *mockRepository) SavePauseState(ctx context.Context, runID, pausedNodeID string, stateSnapshot map[string]any, completedNodes []string, graphJSON string) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.pauses[runID] = mockPauseState{
		pausedNodeID:   pausedNodeID,
		stateSnapshot:  stateSnapshot,
		completedNodes: completedNodes,
		graphJSON:      graphJSON,
	}
	return nil
}

func (r *mockRepository) LoadPauseState(ctx context.Context, runID string) (pausedNodeID string, stateSnapshot map[string]any, completedNodes []string, graphJSON string, err error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	pause, ok := r.pauses[runID]
	if !ok {
		return "", nil, nil, "", fmt.Errorf("pause state not found")
	}
	return pause.pausedNodeID, pause.stateSnapshot, pause.completedNodes, pause.graphJSON, nil
}

func (r *mockRepository) ClearPauseState(ctx context.Context, runID string) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	delete(r.pauses, runID)
	return nil
}

func (r *mockRepository) CreateNodeRun(ctx context.Context, nodeRun *entity.NodeRun) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.nodeRuns[nodeRun.ID] = nodeRun
	return nil
}

func (r *mockRepository) UpdateNodeRun(ctx context.Context, nodeRun *entity.NodeRun) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.nodeRuns[nodeRun.ID] = nodeRun
	return nil
}

func (r *mockRepository) GetNodeRun(ctx context.Context, runID, nodeID string) (*entity.NodeRun, error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	key := fmt.Sprintf("%s-%s", runID, nodeID)
	nodeRun, ok := r.nodeRuns[key]
	if !ok {
		return nil, fmt.Errorf("node run not found")
	}
	return nodeRun, nil
}

func (r *mockRepository) GetNodeRunsByRunID(ctx context.Context, runID string) ([]*entity.NodeRun, error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	var result []*entity.NodeRun
	for _, nr := range r.nodeRuns {
		if nr.RunID == runID {
			result = append(result, nr)
		}
	}
	return result, nil
}

func (r *mockRepository) getRunStatus(runID string) string {
	r.mu.Lock()
	defer r.mu.Unlock()
	if run, ok := r.runs[runID]; ok {
		return run.Status
	}
	return ""
}

func (r *mockRepository) getNodeRunCount(runID string) int {
	r.mu.Lock()
	defer r.mu.Unlock()
	count := 0
	for _, nr := range r.nodeRuns {
		if nr.RunID == runID {
			count++
		}
	}
	return count
}

// mockExecutor implements port.NodeExecutor for testing
type mockExecutor struct {
	nodeType      string
	executeFn     func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error)
	executeCount  int
	executeCounts map[string]int
	mu            sync.Mutex
}

func newMockExecutor(nodeType string, fn func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error)) *mockExecutor {
	return &mockExecutor{
		nodeType:      nodeType,
		executeFn:     fn,
		executeCounts: make(map[string]int),
	}
}

func (e *mockExecutor) NodeType() string {
	return e.nodeType
}

func (e *mockExecutor) Execute(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
	e.mu.Lock()
	e.executeCount++
	e.executeCounts[node.ID]++
	e.mu.Unlock()
	return e.executeFn(ctx, node, state)
}

func (e *mockExecutor) getExecuteCount() int {
	e.mu.Lock()
	defer e.mu.Unlock()
	return e.executeCount
}

func (e *mockExecutor) getNodeExecuteCount(nodeID string) int {
	e.mu.Lock()
	defer e.mu.Unlock()
	return e.executeCounts[nodeID]
}

// recordingEmitter captures emitted events for verification
type recordingEmitter struct {
	mu     sync.Mutex
	events []*port.ExecutionEvent
}

func newRecordingEmitter() *recordingEmitter {
	return &recordingEmitter{
		events: make([]*port.ExecutionEvent, 0),
	}
}

func (e *recordingEmitter) Emit(ctx context.Context, event *port.ExecutionEvent) error {
	e.mu.Lock()
	defer e.mu.Unlock()
	e.events = append(e.events, event)
	return nil
}

func (e *recordingEmitter) EmitAsync(event *port.ExecutionEvent) {
	e.Emit(context.Background(), event)
}

func (e *recordingEmitter) Flush(ctx context.Context) error {
	return nil
}

func (e *recordingEmitter) getEvents() []*port.ExecutionEvent {
	e.mu.Lock()
	defer e.mu.Unlock()
	result := make([]*port.ExecutionEvent, len(e.events))
	copy(result, e.events)
	return result
}

func (e *recordingEmitter) hasEventType(eventType port.EventType) bool {
	e.mu.Lock()
	defer e.mu.Unlock()
	for _, ev := range e.events {
		if ev.Type == eventType {
			return true
		}
	}
	return false
}

// Helper to create a test graph JSON
func makeGraphJSON(nodes []entity.Node, edges []entity.Edge) string {
	graph := entity.Graph{
		Nodes: nodes,
		Edges: edges,
	}
	data, _ := json.Marshal(graph)
	return string(data)
}

// =============================================================================
// Test: Simple Linear Graph Execution
// =============================================================================

func TestScheduler_LinearGraph(t *testing.T) {
	// Create a simple linear graph: Transform -> Output
	nodes := []entity.Node{
		{ID: "transform1", Type: "transform", Name: "Transform 1", Config: map[string]any{
			"expression_type": "static",
			"expression":      "hello world",
			"output_key":      "result",
		}},
		{ID: "output1", Type: "output", Name: "Output 1", Config: map[string]any{}},
	}
	edges := []entity.Edge{
		{From: "transform1", To: "output1"},
	}
	graphJSON := makeGraphJSON(nodes, edges)

	// Create mocks
	repo := newMockRepository()
	emitter := newRecordingEmitter()

	// Track execution order
	var executionOrder []string
	var executionMu sync.Mutex

	transformExec := newMockExecutor("transform", func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		executionMu.Lock()
		executionOrder = append(executionOrder, node.ID)
		executionMu.Unlock()
		state.SetVar("result", "hello world")
		return &port.NodeExecutionResult{Output: "hello world"}, nil
	})

	outputExec := newMockExecutor("output", func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		executionMu.Lock()
		executionOrder = append(executionOrder, node.ID)
		executionMu.Unlock()
		result, _ := state.GetVar("result")
		return &port.NodeExecutionResult{Output: map[string]any{"result": result}}, nil
	})

	// Create registry
	registry := port.NewExecutorRegistry()
	registry.RegisterAll(transformExec, outputExec)

	// Create scheduler
	config := SchedulerConfig{MaxWorkers: 2, DefaultTimeoutMs: 5000}
	scheduler := NewScheduler(config, registry, repo, emitter)

	// Start run
	err := scheduler.StartRun(context.Background(), "run-1", graphJSON, "{}", "")
	if err != nil {
		t.Fatalf("StartRun failed: %v", err)
	}

	// Wait for completion
	waitForRunCompletion(t, scheduler, repo, "run-1", 5*time.Second)

	// Verify execution order
	executionMu.Lock()
	defer executionMu.Unlock()
	if len(executionOrder) != 2 {
		t.Errorf("Expected 2 nodes executed, got %d", len(executionOrder))
	}
	if executionOrder[0] != "transform1" {
		t.Errorf("Expected transform1 first, got %s", executionOrder[0])
	}
	if executionOrder[1] != "output1" {
		t.Errorf("Expected output1 second, got %s", executionOrder[1])
	}

	// Verify run status
	if repo.getRunStatus("run-1") != string(value.RunStatusSucceeded) {
		t.Errorf("Expected run status succeeded, got %s", repo.getRunStatus("run-1"))
	}

	// Verify events emitted
	if !emitter.hasEventType(port.EventTypeRunStarted) {
		t.Error("Expected run_started event")
	}
	if !emitter.hasEventType(port.EventTypeRunCompleted) {
		t.Error("Expected run_completed event")
	}
}

// =============================================================================
// Test: Parallel Branch Execution
// =============================================================================

func TestScheduler_ParallelBranches(t *testing.T) {
	// Create parallel graph: Start -> [A, B] -> Output
	// A and B should execute in parallel
	nodes := []entity.Node{
		{ID: "start", Type: "transform", Name: "Start", Config: map[string]any{
			"expression_type": "static",
			"expression":      "started",
			"output_key":      "status",
		}},
		{ID: "branchA", Type: "transform", Name: "Branch A", Config: map[string]any{
			"expression_type": "static",
			"expression":      "branch_a_result",
			"output_key":      "a_result",
		}},
		{ID: "branchB", Type: "transform", Name: "Branch B", Config: map[string]any{
			"expression_type": "static",
			"expression":      "branch_b_result",
			"output_key":      "b_result",
		}},
		{ID: "output1", Type: "output", Name: "Output 1", Config: map[string]any{}},
	}
	edges := []entity.Edge{
		{From: "start", To: "branchA"},
		{From: "start", To: "branchB"},
		{From: "branchA", To: "output1"},
		{From: "branchB", To: "output1"},
	}
	graphJSON := makeGraphJSON(nodes, edges)

	// Create mocks
	repo := newMockRepository()
	emitter := newRecordingEmitter()

	// Track parallel execution
	var executionTimes sync.Map
	parallelExec := make(chan struct{}, 2)

	transformExec := newMockExecutor("transform", func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		executionTimes.Store(node.ID, time.Now())
		// For branches, add delay to detect parallelism
		if node.ID == "branchA" || node.ID == "branchB" {
			parallelExec <- struct{}{}
			time.Sleep(50 * time.Millisecond)
		}
		return &port.NodeExecutionResult{Output: node.ID + "_done"}, nil
	})

	outputExec := newMockExecutor("output", func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return &port.NodeExecutionResult{Output: map[string]any{"done": true}}, nil
	})

	registry := port.NewExecutorRegistry()
	registry.RegisterAll(transformExec, outputExec)

	config := SchedulerConfig{MaxWorkers: 4, DefaultTimeoutMs: 5000}
	scheduler := NewScheduler(config, registry, repo, emitter)

	err := scheduler.StartRun(context.Background(), "run-2", graphJSON, "{}", "")
	if err != nil {
		t.Fatalf("StartRun failed: %v", err)
	}

	// Wait for completion
	waitForRunCompletion(t, scheduler, repo, "run-2", 5*time.Second)

	// Verify both branches were executed
	if transformExec.getNodeExecuteCount("branchA") != 1 {
		t.Error("Branch A was not executed")
	}
	if transformExec.getNodeExecuteCount("branchB") != 1 {
		t.Error("Branch B was not executed")
	}

	// Verify run completed successfully
	if repo.getRunStatus("run-2") != string(value.RunStatusSucceeded) {
		t.Errorf("Expected run status succeeded, got %s", repo.getRunStatus("run-2"))
	}
}

// =============================================================================
// Test: Cancellation
// =============================================================================

func TestScheduler_Cancellation(t *testing.T) {
	// Create a graph with a slow node
	nodes := []entity.Node{
		{ID: "slow", Type: "transform", Name: "Slow Node", Config: map[string]any{
			"expression_type": "static",
			"expression":      "slow",
			"output_key":      "result",
		}},
		{ID: "output1", Type: "output", Name: "Output 1", Config: map[string]any{}},
	}
	edges := []entity.Edge{
		{From: "slow", To: "output1"},
	}
	graphJSON := makeGraphJSON(nodes, edges)

	repo := newMockRepository()
	emitter := newRecordingEmitter()

	started := make(chan struct{})
	transformExec := newMockExecutor("transform", func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		close(started)
		// Wait for cancellation
		select {
		case <-ctx.Done():
			return nil, ctx.Err()
		case <-time.After(10 * time.Second):
			return &port.NodeExecutionResult{Output: "done"}, nil
		}
	})

	outputExec := newMockExecutor("output", func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return &port.NodeExecutionResult{Output: map[string]any{}}, nil
	})

	registry := port.NewExecutorRegistry()
	registry.RegisterAll(transformExec, outputExec)

	config := SchedulerConfig{MaxWorkers: 2, DefaultTimeoutMs: 30000}
	scheduler := NewScheduler(config, registry, repo, emitter)

	err := scheduler.StartRun(context.Background(), "run-3", graphJSON, "{}", "")
	if err != nil {
		t.Fatalf("StartRun failed: %v", err)
	}

	// Wait for execution to start
	<-started

	// Cancel the run
	err = scheduler.CancelRun("run-3")
	if err != nil {
		t.Fatalf("CancelRun failed: %v", err)
	}

	// Wait for completion
	waitForRunInactive(t, scheduler, "run-3", 5*time.Second)

	// Verify run status is canceled
	status := repo.getRunStatus("run-3")
	if status != string(value.RunStatusCanceled) {
		t.Errorf("Expected run status canceled, got %s", status)
	}

	// Verify cancel event emitted
	if !emitter.hasEventType(port.EventTypeRunCanceled) {
		t.Error("Expected run_canceled event")
	}
}

// =============================================================================
// Test: Timeout Handling
// =============================================================================

func TestScheduler_Timeout(t *testing.T) {
	// Create a graph with a node that times out
	nodes := []entity.Node{
		{ID: "timeout", Type: "transform", Name: "Timeout Node", TimeoutMs: 100, Config: map[string]any{
			"expression_type": "static",
			"expression":      "timeout",
			"output_key":      "result",
		}},
		{ID: "output1", Type: "output", Name: "Output 1", Config: map[string]any{}},
	}
	edges := []entity.Edge{
		{From: "timeout", To: "output1"},
	}
	graphJSON := makeGraphJSON(nodes, edges)

	repo := newMockRepository()
	emitter := newRecordingEmitter()

	transformExec := newMockExecutor("transform", func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		// Sleep longer than timeout
		select {
		case <-ctx.Done():
			return nil, ctx.Err()
		case <-time.After(5 * time.Second):
			return &port.NodeExecutionResult{Output: "done"}, nil
		}
	})

	outputExec := newMockExecutor("output", func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return &port.NodeExecutionResult{Output: map[string]any{}}, nil
	})

	registry := port.NewExecutorRegistry()
	registry.RegisterAll(transformExec, outputExec)

	config := SchedulerConfig{MaxWorkers: 2, DefaultTimeoutMs: 5000}
	scheduler := NewScheduler(config, registry, repo, emitter)

	err := scheduler.StartRun(context.Background(), "run-4", graphJSON, "{}", "")
	if err != nil {
		t.Fatalf("StartRun failed: %v", err)
	}

	// Wait for completion (should fail due to timeout)
	waitForRunCompletion(t, scheduler, repo, "run-4", 5*time.Second)

	// Verify run failed
	status := repo.getRunStatus("run-4")
	if status != string(value.RunStatusFailed) {
		t.Errorf("Expected run status failed, got %s", status)
	}

	// Verify failure event emitted
	if !emitter.hasEventType(port.EventTypeRunFailed) {
		t.Error("Expected run_failed event")
	}
}

// =============================================================================
// Test: Retry Logic
// =============================================================================

func TestScheduler_RetrySuccess(t *testing.T) {
	// Create a graph with a node that fails twice then succeeds
	nodes := []entity.Node{
		{ID: "retry", Type: "transform", Name: "Retry Node", Config: map[string]any{
			"expression_type": "static",
			"expression":      "retry",
			"output_key":      "result",
		}, RetryPolicy: &entity.RetryPolicy{
			MaxAttempts:     3,
			BackoffMs:       10,
			BackoffStrategy: "fixed",
		}},
		{ID: "output1", Type: "output", Name: "Output 1", Config: map[string]any{}},
	}
	edges := []entity.Edge{
		{From: "retry", To: "output1"},
	}
	graphJSON := makeGraphJSON(nodes, edges)

	repo := newMockRepository()
	emitter := newRecordingEmitter()

	attemptCount := 0
	var attemptMu sync.Mutex

	transformExec := newMockExecutor("transform", func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		attemptMu.Lock()
		attemptCount++
		currentAttempt := attemptCount
		attemptMu.Unlock()

		// Fail first two attempts with retryable error
		if currentAttempt < 3 {
			return nil, domain.NewRetryableError(fmt.Errorf("transient error %d", currentAttempt), "transient failure")
		}
		return &port.NodeExecutionResult{Output: "success"}, nil
	})

	outputExec := newMockExecutor("output", func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return &port.NodeExecutionResult{Output: map[string]any{"result": "done"}}, nil
	})

	registry := port.NewExecutorRegistry()
	registry.RegisterAll(transformExec, outputExec)

	config := SchedulerConfig{MaxWorkers: 2, DefaultTimeoutMs: 5000}
	scheduler := NewScheduler(config, registry, repo, emitter)

	err := scheduler.StartRun(context.Background(), "run-5", graphJSON, "{}", "")
	if err != nil {
		t.Fatalf("StartRun failed: %v", err)
	}

	// Wait for completion
	waitForRunCompletion(t, scheduler, repo, "run-5", 5*time.Second)

	// Verify 3 attempts were made
	attemptMu.Lock()
	if attemptCount != 3 {
		t.Errorf("Expected 3 attempts, got %d", attemptCount)
	}
	attemptMu.Unlock()

	// Verify run succeeded
	if repo.getRunStatus("run-5") != string(value.RunStatusSucceeded) {
		t.Errorf("Expected run status succeeded, got %s", repo.getRunStatus("run-5"))
	}

	// Verify retry events were emitted
	if !emitter.hasEventType(port.EventTypeNodeRetrying) {
		t.Error("Expected node_retrying event")
	}
}

func TestScheduler_RetryExhausted(t *testing.T) {
	// Create a graph with a node that always fails
	nodes := []entity.Node{
		{ID: "fail", Type: "transform", Name: "Fail Node", Config: map[string]any{
			"expression_type": "static",
			"expression":      "fail",
			"output_key":      "result",
		}, RetryPolicy: &entity.RetryPolicy{
			MaxAttempts:     3,
			BackoffMs:       10,
			BackoffStrategy: "fixed",
		}},
		{ID: "output1", Type: "output", Name: "Output 1", Config: map[string]any{}},
	}
	edges := []entity.Edge{
		{From: "fail", To: "output1"},
	}
	graphJSON := makeGraphJSON(nodes, edges)

	repo := newMockRepository()
	emitter := newRecordingEmitter()

	attemptCount := 0
	var attemptMu sync.Mutex

	transformExec := newMockExecutor("transform", func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		attemptMu.Lock()
		attemptCount++
		attemptMu.Unlock()
		return nil, domain.NewRetryableError(fmt.Errorf("always fails"), "persistent failure")
	})

	outputExec := newMockExecutor("output", func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return &port.NodeExecutionResult{Output: map[string]any{}}, nil
	})

	registry := port.NewExecutorRegistry()
	registry.RegisterAll(transformExec, outputExec)

	config := SchedulerConfig{MaxWorkers: 2, DefaultTimeoutMs: 5000}
	scheduler := NewScheduler(config, registry, repo, emitter)

	err := scheduler.StartRun(context.Background(), "run-6", graphJSON, "{}", "")
	if err != nil {
		t.Fatalf("StartRun failed: %v", err)
	}

	// Wait for completion
	waitForRunCompletion(t, scheduler, repo, "run-6", 5*time.Second)

	// Verify all 3 attempts were made
	attemptMu.Lock()
	if attemptCount != 3 {
		t.Errorf("Expected 3 attempts, got %d", attemptCount)
	}
	attemptMu.Unlock()

	// Verify run failed
	if repo.getRunStatus("run-6") != string(value.RunStatusFailed) {
		t.Errorf("Expected run status failed, got %s", repo.getRunStatus("run-6"))
	}
}

func TestScheduler_NonRetryableError(t *testing.T) {
	// Create a graph with a node that fails with non-retryable error
	nodes := []entity.Node{
		{ID: "fail", Type: "transform", Name: "Fail Node", Config: map[string]any{
			"expression_type": "static",
			"expression":      "fail",
			"output_key":      "result",
		}, RetryPolicy: &entity.RetryPolicy{
			MaxAttempts:     3,
			BackoffMs:       10,
			BackoffStrategy: "fixed",
		}},
		{ID: "output1", Type: "output", Name: "Output 1", Config: map[string]any{}},
	}
	edges := []entity.Edge{
		{From: "fail", To: "output1"},
	}
	graphJSON := makeGraphJSON(nodes, edges)

	repo := newMockRepository()
	emitter := newRecordingEmitter()

	attemptCount := 0
	var attemptMu sync.Mutex

	transformExec := newMockExecutor("transform", func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		attemptMu.Lock()
		attemptCount++
		attemptMu.Unlock()
		// Non-retryable error - should not retry
		return nil, fmt.Errorf("validation error")
	})

	outputExec := newMockExecutor("output", func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return &port.NodeExecutionResult{Output: map[string]any{}}, nil
	})

	registry := port.NewExecutorRegistry()
	registry.RegisterAll(transformExec, outputExec)

	config := SchedulerConfig{MaxWorkers: 2, DefaultTimeoutMs: 5000}
	scheduler := NewScheduler(config, registry, repo, emitter)

	err := scheduler.StartRun(context.Background(), "run-7", graphJSON, "{}", "")
	if err != nil {
		t.Fatalf("StartRun failed: %v", err)
	}

	// Wait for completion
	waitForRunCompletion(t, scheduler, repo, "run-7", 5*time.Second)

	// Verify only 1 attempt was made (no retries for non-retryable errors)
	attemptMu.Lock()
	if attemptCount != 1 {
		t.Errorf("Expected 1 attempt (no retries), got %d", attemptCount)
	}
	attemptMu.Unlock()

	// Verify run failed
	if repo.getRunStatus("run-7") != string(value.RunStatusFailed) {
		t.Errorf("Expected run status failed, got %s", repo.getRunStatus("run-7"))
	}
}

func TestScheduler_BranchSkipDoesNotBlockMerge(t *testing.T) {
	nodes := []entity.Node{
		{ID: "branch", Type: "branch", Name: "Branch", Config: map[string]any{}},
		{ID: "truePath", Type: "transform", Name: "True Path", Config: map[string]any{}},
		{ID: "falsePath", Type: "transform", Name: "False Path", Config: map[string]any{}},
		{ID: "merge", Type: "merge", Name: "Merge", Config: map[string]any{}},
		{ID: "output1", Type: "output", Name: "Output 1", Config: map[string]any{}},
	}
	edges := []entity.Edge{
		{From: "branch", To: "truePath"},
		{From: "branch", To: "falsePath"},
		{From: "truePath", To: "merge"},
		{From: "falsePath", To: "merge"},
		{From: "merge", To: "output1"},
	}
	graphJSON := makeGraphJSON(nodes, edges)

	repo := newMockRepository()
	emitter := newRecordingEmitter()

	branchExec := newMockExecutor("branch", func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		// Only take the truePath
		return port.NewBranchResult(map[string]any{"taken": "true"}, []string{"truePath"}), nil
	})

	transformExec := newMockExecutor("transform", func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewSuccessResult(map[string]any{"node_id": node.ID}), nil
	})

	mergeExec := newMockExecutor("merge", func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewSuccessResult(map[string]any{"merged": true}), nil
	})

	outputExec := newMockExecutor("output", func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewSuccessResult(map[string]any{"ok": true}), nil
	})

	registry := port.NewExecutorRegistry()
	registry.RegisterAll(branchExec, transformExec, mergeExec, outputExec)

	config := SchedulerConfig{MaxWorkers: 2, DefaultTimeoutMs: 5000}
	scheduler := NewScheduler(config, registry, repo, emitter)

	err := scheduler.StartRun(context.Background(), "run-branch-merge", graphJSON, "{}", "")
	if err != nil {
		t.Fatalf("StartRun failed: %v", err)
	}

	waitForRunCompletion(t, scheduler, repo, "run-branch-merge", 5*time.Second)

	if repo.getRunStatus("run-branch-merge") != string(value.RunStatusSucceeded) {
		t.Fatalf("Expected run status succeeded, got %s", repo.getRunStatus("run-branch-merge"))
	}

	if transformExec.getNodeExecuteCount("falsePath") != 0 {
		t.Errorf("Expected falsePath to be skipped (0 executes), got %d", transformExec.getNodeExecuteCount("falsePath"))
	}
	if mergeExec.getNodeExecuteCount("merge") != 1 {
		t.Errorf("Expected merge to execute once, got %d", mergeExec.getNodeExecuteCount("merge"))
	}
	if outputExec.getNodeExecuteCount("output1") != 1 {
		t.Errorf("Expected output to execute once, got %d", outputExec.getNodeExecuteCount("output1"))
	}

	if !emitter.hasEventType(port.EventTypeNodeSkipped) {
		t.Error("Expected node_skipped event")
	}
}

func TestScheduler_PauseStopsScheduling(t *testing.T) {
	nodes := []entity.Node{
		{ID: "start", Type: "transform", Name: "Start", Config: map[string]any{}},
		{ID: "gate", Type: "human_gate", Name: "Human Gate", Config: map[string]any{}},
		{ID: "after", Type: "output", Name: "After", Config: map[string]any{}},
	}
	edges := []entity.Edge{
		{From: "start", To: "gate"},
		{From: "gate", To: "after"},
	}
	graphJSON := makeGraphJSON(nodes, edges)

	repo := newMockRepository()
	emitter := newRecordingEmitter()

	transformExec := newMockExecutor("transform", func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewSuccessResult(map[string]any{"ok": true}), nil
	})

	humanGateExec := newMockExecutor("human_gate", func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewPauseResult(map[string]any{"prompt_message": "Please approve"}), nil
	})

	outputExec := newMockExecutor("output", func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewSuccessResult(map[string]any{"should_not_run": true}), nil
	})

	registry := port.NewExecutorRegistry()
	registry.RegisterAll(transformExec, humanGateExec, outputExec)

	config := SchedulerConfig{MaxWorkers: 2, DefaultTimeoutMs: 5000}
	scheduler := NewScheduler(config, registry, repo, emitter)

	err := scheduler.StartRun(context.Background(), "run-paused", graphJSON, "{}", "")
	if err != nil {
		t.Fatalf("StartRun failed: %v", err)
	}

	waitForRunInactive(t, scheduler, "run-paused", 5*time.Second)

	if repo.getRunStatus("run-paused") != string(value.RunStatusPaused) {
		t.Fatalf("Expected run status paused, got %s", repo.getRunStatus("run-paused"))
	}
	if outputExec.getNodeExecuteCount("after") != 0 {
		t.Errorf("Expected 'after' not to execute, got %d", outputExec.getNodeExecuteCount("after"))
	}
	if !emitter.hasEventType(port.EventTypeRunPaused) {
		t.Error("Expected run_paused event")
	}

	pausedNodeID, snapshot, completedNodes, graphJSONLoaded, loadErr := repo.LoadPauseState(context.Background(), "run-paused")
	if loadErr != nil {
		t.Fatalf("Expected pause state to be saved, got error: %v", loadErr)
	}
	if pausedNodeID != "gate" {
		t.Errorf("Expected paused node id 'gate', got %q", pausedNodeID)
	}
	if snapshot == nil {
		t.Error("Expected non-nil state snapshot")
	}
	if graphJSONLoaded == "" {
		t.Error("Expected graph JSON to be saved")
	}
	if len(completedNodes) == 0 {
		t.Error("Expected at least one completed node (start) recorded")
	}
}

// =============================================================================
// Test: Input Variables
// =============================================================================

func TestScheduler_InputVariables(t *testing.T) {
	nodes := []entity.Node{
		{ID: "transform1", Type: "transform", Name: "Transform 1", Config: map[string]any{
			"expression_type": "key_lookup",
			"expression":      "input.name",
			"output_key":      "result",
		}},
		{ID: "output1", Type: "output", Name: "Output 1", Config: map[string]any{}},
	}
	edges := []entity.Edge{
		{From: "transform1", To: "output1"},
	}
	graphJSON := makeGraphJSON(nodes, edges)
	inputJSON := `{"name": "test_user"}`

	repo := newMockRepository()
	emitter := newRecordingEmitter()

	var capturedInput any
	transformExec := newMockExecutor("transform", func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		capturedInput, _ = state.Get("input.name")
		return &port.NodeExecutionResult{Output: capturedInput}, nil
	})

	outputExec := newMockExecutor("output", func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return &port.NodeExecutionResult{Output: map[string]any{"result": "done"}}, nil
	})

	registry := port.NewExecutorRegistry()
	registry.RegisterAll(transformExec, outputExec)

	config := SchedulerConfig{MaxWorkers: 2, DefaultTimeoutMs: 5000}
	scheduler := NewScheduler(config, registry, repo, emitter)

	err := scheduler.StartRun(context.Background(), "run-8", graphJSON, inputJSON, "")
	if err != nil {
		t.Fatalf("StartRun failed: %v", err)
	}

	waitForRunCompletion(t, scheduler, repo, "run-8", 5*time.Second)

	// Verify input was accessible
	if capturedInput != "test_user" {
		t.Errorf("Expected input 'test_user', got %v", capturedInput)
	}
}

// =============================================================================
// Helper Functions
// =============================================================================

func waitForRunCompletion(t *testing.T, scheduler *Scheduler, repo *mockRepository, runID string, timeout time.Duration) {
	t.Helper()
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		if !scheduler.IsRunActive(runID) {
			return
		}
		time.Sleep(50 * time.Millisecond)
	}
	t.Fatalf("Run %s did not complete within %v", runID, timeout)
}

func waitForRunInactive(t *testing.T, scheduler *Scheduler, runID string, timeout time.Duration) {
	t.Helper()
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		if !scheduler.IsRunActive(runID) {
			return
		}
		time.Sleep(50 * time.Millisecond)
	}
	t.Fatalf("Run %s did not become inactive within %v", runID, timeout)
}
