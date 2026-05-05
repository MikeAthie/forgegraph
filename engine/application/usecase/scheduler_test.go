//go:build legacy_engine_tests
// +build legacy_engine_tests

package usecase

import (
	"context"
	"encoding/json"
	"fmt"
	"sync"
	"testing"
	"time"

	"github.com/forgegraph/engine/adapter/executor"
	"github.com/forgegraph/engine/adapter/store"
	"github.com/forgegraph/engine/adapter/tool"
	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/domain"
	"github.com/forgegraph/engine/domain/entity"
	"github.com/forgegraph/engine/domain/value"
)

// mockRepository implements port.RunRepository for testing
type mockRepository struct {
	mu          sync.Mutex
	runs        map[string]*entity.Run
	nodeRuns    map[string]*entity.NodeRun
	pauses      map[string]mockPauseState
	checkpoints map[string]mockCheckpointState
	cache       map[string]mockCacheEntry
}

type mockPauseState struct {
	pausedNodeID   string
	stateSnapshot  map[string]any
	completedNodes []string
	skippedNodes   []string
	graphJSON      string
	tenantID       string
}

type mockCheckpointState struct {
	nodeID         string
	stepIndex      int
	stateSnapshot  map[string]any
	completedNodes []string
	skippedNodes   []string
	graphJSON      string
}

type mockCacheEntry struct {
	output    any
	expiresAt time.Time
}

func newMockRepository() *mockRepository {
	return &mockRepository{
		runs:        make(map[string]*entity.Run),
		nodeRuns:    make(map[string]*entity.NodeRun),
		pauses:      make(map[string]mockPauseState),
		checkpoints: make(map[string]mockCheckpointState),
		cache:       make(map[string]mockCacheEntry),
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

func (r *mockRepository) SavePauseState(ctx context.Context, runID, pausedNodeID string, stateSnapshot map[string]any, completedNodes []string, skippedNodes []string, graphJSON string, tenantID string) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.pauses[runID] = mockPauseState{
		pausedNodeID:   pausedNodeID,
		stateSnapshot:  stateSnapshot,
		completedNodes: completedNodes,
		skippedNodes:   skippedNodes,
		graphJSON:      graphJSON,
		tenantID:       tenantID,
	}
	return nil
}

func (r *mockRepository) LoadPauseState(ctx context.Context, runID string) (pausedNodeID string, stateSnapshot map[string]any, completedNodes []string, skippedNodes []string, graphJSON string, tenantID string, err error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	pause, ok := r.pauses[runID]
	if !ok {
		return "", nil, nil, nil, "", "", fmt.Errorf("pause state not found")
	}
	return pause.pausedNodeID, pause.stateSnapshot, pause.completedNodes, pause.skippedNodes, pause.graphJSON, pause.tenantID, nil
}

func (r *mockRepository) ClearPauseState(ctx context.Context, runID string) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	delete(r.pauses, runID)
	return nil
}

func (r *mockRepository) SaveCheckpoint(ctx context.Context, runID, nodeID string, stepIndex int, stateSnapshot map[string]any, completedNodes []string, skippedNodes []string, graphJSON string) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.checkpoints[runID] = mockCheckpointState{
		nodeID:         nodeID,
		stepIndex:      stepIndex,
		stateSnapshot:  stateSnapshot,
		completedNodes: append([]string(nil), completedNodes...),
		skippedNodes:   append([]string(nil), skippedNodes...),
		graphJSON:      graphJSON,
	}
	return nil
}

func (r *mockRepository) LoadLatestCheckpoint(ctx context.Context, runID string) (nodeID string, stepIndex int, stateSnapshot map[string]any, completedNodes []string, skippedNodes []string, graphJSON string, err error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	checkpoint, ok := r.checkpoints[runID]
	if !ok {
		return "", 0, nil, nil, nil, "", domain.ErrCheckpointNotFound
	}
	return checkpoint.nodeID, checkpoint.stepIndex, checkpoint.stateSnapshot, append([]string(nil), checkpoint.completedNodes...), append([]string(nil), checkpoint.skippedNodes...), checkpoint.graphJSON, nil
}

func (r *mockRepository) ClearCheckpoints(ctx context.Context, runID string) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	delete(r.checkpoints, runID)
	return nil
}

func (r *mockRepository) GetCachedNodeResult(ctx context.Context, cacheKey string) (output any, found bool, err error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	entry, ok := r.cache[cacheKey]
	if !ok {
		return nil, false, nil
	}
	if time.Now().After(entry.expiresAt) {
		delete(r.cache, cacheKey)
		return nil, false, nil
	}
	return entry.output, true, nil
}

func (r *mockRepository) SaveCachedNodeResult(ctx context.Context, cacheKey string, output any, ttlSeconds int) error {
	if ttlSeconds <= 0 {
		return nil
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	r.cache[cacheKey] = mockCacheEntry{
		output:    output,
		expiresAt: time.Now().Add(time.Duration(ttlSeconds) * time.Second),
	}
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

type schedulerLLMClient struct {
	response *executor.LLMResponse
}

type schedulerObservationClient struct {
	saveRequest    *port.ObservationSaveRequest
	saveResponse   port.Observation
	searchResponse []port.Observation
	contextResp    port.ObservationContextResponse
	timelineResp   []port.Observation
}

func (m *schedulerLLMClient) Complete(ctx context.Context, request *executor.LLMRequest) (*executor.LLMResponse, error) {
	if m.response != nil {
		return m.response, nil
	}
	return &executor.LLMResponse{
		Content: `{"action":"final_answer","final_answer":"done"}`,
		Model:   request.Model,
	}, nil
}

func (m *schedulerObservationClient) SaveObservation(ctx context.Context, request port.ObservationSaveRequest) (port.Observation, error) {
	m.saveRequest = &request
	return m.saveResponse, nil
}

func (m *schedulerObservationClient) SearchObservations(ctx context.Context, request port.ObservationSearchRequest) ([]port.Observation, error) {
	return m.searchResponse, nil
}

func (m *schedulerObservationClient) GetContext(ctx context.Context, request port.ObservationContextRequest) (port.ObservationContextResponse, error) {
	return m.contextResp, nil
}

func (m *schedulerObservationClient) GetTimeline(ctx context.Context, request port.ObservationTimelineRequest) ([]port.Observation, error) {
	return m.timelineResp, nil
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
	scheduler := NewScheduler(config, registry, repo, emitter, store.NewInMemoryMemoryStore())

	// Start run
	err := scheduler.StartRun(context.Background(), "run-1", graphJSON, "{}", "", "", "", "")
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

func TestScheduler_AgentGraph(t *testing.T) {
	nodes := []entity.Node{
		{
			ID:   "agent1",
			Type: string(value.NodeTypeAgent),
			Name: "Agent 1",
			Config: map[string]any{
				"model":          "gpt-4.1-mini",
				"provider":       "openai",
				"tools":          []any{"crm_lookup"},
				"max_steps":      3,
				"max_tool_calls": 1,
			},
		},
		{
			ID:   "output1",
			Type: string(value.NodeTypeOutput),
			Name: "Output 1",
			Config: map[string]any{
				"output_mapping": map[string]any{
					"agent_result": "node.agent1.output",
				},
			},
		},
	}
	edges := []entity.Edge{
		{From: "agent1", To: "output1"},
	}
	graphJSON := makeGraphJSON(nodes, edges)

	repo := newMockRepository()
	emitter := newRecordingEmitter()
	registry := port.NewExecutorRegistry()

	llmClient := &schedulerLLMClient{
		response: &executor.LLMResponse{
			Content: `{"action":"final_answer","final_answer":"Agent completed successfully."}`,
			Model:   "gpt-4.1-mini",
		},
	}

	registry.RegisterAll(
		executor.NewAgentExecutor(llmClient, tool.NewRegistry(), nil),
		executor.NewOutputExecutor(),
	)

	config := SchedulerConfig{MaxWorkers: 2, DefaultTimeoutMs: 5000}
	scheduler := NewScheduler(config, registry, repo, emitter, store.NewInMemoryMemoryStore())

	if err := scheduler.StartRun(context.Background(), "run-agent-1", graphJSON, `{"ticket_id":"T-999"}`, "", "", "", ""); err != nil {
		t.Fatalf("StartRun failed: %v", err)
	}

	waitForRunCompletion(t, scheduler, repo, "run-agent-1", 5*time.Second)

	if repo.getRunStatus("run-agent-1") != string(value.RunStatusSucceeded) {
		t.Fatalf("expected run status succeeded, got %s", repo.getRunStatus("run-agent-1"))
	}

	run, err := repo.GetRun(context.Background(), "run-agent-1")
	if err != nil {
		t.Fatalf("GetRun failed: %v", err)
	}
	if run.OutputJSON["agent_result"] == nil {
		t.Fatalf("expected output mapping to include agent_result, got %#v", run.OutputJSON)
	}

	events := emitter.getEvents()
	var sawAgentChunk bool
	for _, event := range events {
		if event.Type == port.EventTypeNodeStreamChunk && event.NodeID == "agent1" {
			sawAgentChunk = true
			break
		}
	}
	if !sawAgentChunk {
		t.Fatal("expected node_stream_chunk event for agent node")
	}
}

func TestScheduler_ObservationSaveGraphPassesRuntimeIdentifiers(t *testing.T) {
	graph := map[string]any{
		"graph_id": "graph-observation-1",
		"nodes": []map[string]any{
			{
				"id":   "observation_1",
				"type": "observation_save",
				"name": "Save Observation",
				"config": map[string]any{
					"type":    "fact",
					"scope":   "session",
					"content": "Remember the renewal date",
				},
			},
			{
				"id":     "output_1",
				"type":   "output",
				"name":   "Output",
				"config": map[string]any{},
			},
		},
		"edges": []map[string]any{
			{"id": "e1", "from": "observation_1", "to": "output_1"},
		},
	}
	graphBytes, err := json.Marshal(graph)
	if err != nil {
		t.Fatalf("json.Marshal() error = %v", err)
	}

	repo := newMockRepository()
	emitter := newRecordingEmitter()
	registry := port.NewExecutorRegistry()
	obsClient := &schedulerObservationClient{
		saveResponse: port.Observation{
			ID:        "obs-1",
			TenantID:  "tenant-obs",
			GraphID:   "graph-observation-1",
			RunID:     "run-observation-1",
			SessionID: "session-obs",
			Scope:     "session",
			Type:      "fact",
			Content:   "Remember the renewal date",
		},
	}
	registry.RegisterAll(
		executor.NewObservationSaveExecutor(obsClient),
		executor.NewOutputExecutor(),
	)

	scheduler := NewScheduler(
		SchedulerConfig{MaxWorkers: 2, DefaultTimeoutMs: 5000},
		registry,
		repo,
		emitter,
		store.NewInMemoryMemoryStore(),
	)

	runID := "run-observation-1"
	err = scheduler.StartRun(
		context.Background(),
		runID,
		string(graphBytes),
		"{}",
		"",
		"",
		"tenant-obs",
		"session-obs",
	)
	if err != nil {
		t.Fatalf("StartRun failed: %v", err)
	}

	waitForRunCompletion(t, scheduler, repo, runID, 5*time.Second)

	if obsClient.saveRequest == nil {
		t.Fatal("expected observation save request")
	}
	if obsClient.saveRequest.TenantID != "tenant-obs" {
		t.Fatalf("tenant_id = %q, want tenant-obs", obsClient.saveRequest.TenantID)
	}
	if obsClient.saveRequest.GraphID != "graph-observation-1" {
		t.Fatalf("graph_id = %q, want graph-observation-1", obsClient.saveRequest.GraphID)
	}
	if obsClient.saveRequest.RunID != runID {
		t.Fatalf("run_id = %q, want %s", obsClient.saveRequest.RunID, runID)
	}
	if obsClient.saveRequest.SessionID != "session-obs" {
		t.Fatalf("session_id = %q, want session-obs", obsClient.saveRequest.SessionID)
	}
	if repo.getRunStatus(runID) != string(value.RunStatusSucceeded) {
		t.Fatalf("expected succeeded run, got %s", repo.getRunStatus(runID))
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

	transformExec := newMockExecutor("transform", func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return &port.NodeExecutionResult{Output: node.ID + "_done"}, nil
	})

	outputExec := newMockExecutor("output", func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return &port.NodeExecutionResult{Output: map[string]any{"done": true}}, nil
	})

	registry := port.NewExecutorRegistry()
	registry.RegisterAll(transformExec, outputExec)

	config := SchedulerConfig{MaxWorkers: 4, DefaultTimeoutMs: 5000}
	scheduler := NewScheduler(config, registry, repo, emitter, store.NewInMemoryMemoryStore())

	err := scheduler.StartRun(context.Background(), "run-2", graphJSON, "{}", "", "", "", "")
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
	scheduler := NewScheduler(config, registry, repo, emitter, store.NewInMemoryMemoryStore())

	err := scheduler.StartRun(context.Background(), "run-3", graphJSON, "{}", "", "", "", "")
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
	scheduler := NewScheduler(config, registry, repo, emitter, store.NewInMemoryMemoryStore())

	err := scheduler.StartRun(context.Background(), "run-4", graphJSON, "{}", "", "", "", "")
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
	scheduler := NewScheduler(config, registry, repo, emitter, store.NewInMemoryMemoryStore())

	err := scheduler.StartRun(context.Background(), "run-5", graphJSON, "{}", "", "", "", "")
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
	scheduler := NewScheduler(config, registry, repo, emitter, store.NewInMemoryMemoryStore())

	err := scheduler.StartRun(context.Background(), "run-6", graphJSON, "{}", "", "", "", "")
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
	scheduler := NewScheduler(config, registry, repo, emitter, store.NewInMemoryMemoryStore())

	err := scheduler.StartRun(context.Background(), "run-7", graphJSON, "{}", "", "", "", "")
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

func TestScheduler_OnErrorSkipContinuesRun(t *testing.T) {
	nodes := []entity.Node{
		{ID: "fail", Type: "transform", Name: "Fail Node", Config: map[string]any{
			"expression_type": "static",
			"expression":      "fail",
			"output_key":      "result",
			"on_error": map[string]any{
				"strategy": "skip",
			},
		}},
		{ID: "output1", Type: "output", Name: "Output 1", Config: map[string]any{}},
	}
	edges := []entity.Edge{
		{From: "fail", To: "output1"},
	}
	graphJSON := makeGraphJSON(nodes, edges)

	repo := newMockRepository()
	emitter := newRecordingEmitter()

	transformExec := newMockExecutor("transform", func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return nil, fmt.Errorf("non-retryable failure")
	})
	outputExec := newMockExecutor("output", func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewSuccessResult(map[string]any{"ok": true}), nil
	})

	registry := port.NewExecutorRegistry()
	registry.RegisterAll(transformExec, outputExec)

	scheduler := NewScheduler(
		SchedulerConfig{MaxWorkers: 2, DefaultTimeoutMs: 5000},
		registry,
		repo,
		emitter,
		store.NewInMemoryMemoryStore(),
	)

	if err := scheduler.StartRun(context.Background(), "run-onerror-skip", graphJSON, "{}", "", "", "", ""); err != nil {
		t.Fatalf("StartRun failed: %v", err)
	}

	waitForRunCompletion(t, scheduler, repo, "run-onerror-skip", 5*time.Second)

	if repo.getRunStatus("run-onerror-skip") != string(value.RunStatusSucceeded) {
		t.Fatalf("Expected run status succeeded, got %s", repo.getRunStatus("run-onerror-skip"))
	}
	if outputExec.getNodeExecuteCount("output1") != 1 {
		t.Fatalf("Expected output node to execute once, got %d", outputExec.getNodeExecuteCount("output1"))
	}

	nodeRun, ok := repo.nodeRuns["run-onerror-skip-fail"]
	if !ok {
		t.Fatalf("Expected failed node run to be persisted")
	}
	if nodeRun.Status != string(value.NodeRunStatusFailed) {
		t.Fatalf("Expected failed node status, got %s", nodeRun.Status)
	}
	if nodeRun.ErrorJSON["on_error_action"] != "skip" {
		t.Fatalf("Expected on_error_action=skip, got %v", nodeRun.ErrorJSON["on_error_action"])
	}
	if !emitter.hasEventType(port.EventTypeNodeFailed) {
		t.Fatal("Expected node_failed event")
	}
}

func TestScheduler_OnErrorFallbackRoutesToConfiguredNodes(t *testing.T) {
	nodes := []entity.Node{
		{ID: "fail", Type: "transform", Name: "Fail Node", Config: map[string]any{
			"expression_type": "static",
			"expression":      "fail",
			"output_key":      "result",
			"on_error": map[string]any{
				"strategy":   "fallback",
				"next_nodes": []string{"fallback"},
			},
		}},
		{ID: "primary", Type: "transform", Name: "Primary", Config: map[string]any{}},
		{ID: "fallback", Type: "transform", Name: "Fallback", Config: map[string]any{}},
		{ID: "output1", Type: "output", Name: "Output 1", Config: map[string]any{}},
	}
	edges := []entity.Edge{
		{From: "fail", To: "primary"},
		{From: "fail", To: "fallback"},
		{From: "primary", To: "output1"},
		{From: "fallback", To: "output1"},
	}
	graphJSON := makeGraphJSON(nodes, edges)

	repo := newMockRepository()
	emitter := newRecordingEmitter()

	transformExec := newMockExecutor("transform", func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		if node.ID == "fail" {
			return nil, fmt.Errorf("force fallback")
		}
		return port.NewSuccessResult(map[string]any{"node_id": node.ID}), nil
	})
	outputExec := newMockExecutor("output", func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewSuccessResult(map[string]any{"ok": true}), nil
	})

	registry := port.NewExecutorRegistry()
	registry.RegisterAll(transformExec, outputExec)

	scheduler := NewScheduler(
		SchedulerConfig{MaxWorkers: 2, DefaultTimeoutMs: 5000},
		registry,
		repo,
		emitter,
		store.NewInMemoryMemoryStore(),
	)

	if err := scheduler.StartRun(context.Background(), "run-onerror-fallback", graphJSON, "{}", "", "", "", ""); err != nil {
		t.Fatalf("StartRun failed: %v", err)
	}

	waitForRunCompletion(t, scheduler, repo, "run-onerror-fallback", 5*time.Second)

	if repo.getRunStatus("run-onerror-fallback") != string(value.RunStatusSucceeded) {
		t.Fatalf("Expected run status succeeded, got %s", repo.getRunStatus("run-onerror-fallback"))
	}
	if transformExec.getNodeExecuteCount("primary") != 0 {
		t.Fatalf("Expected primary path to be skipped, got %d executions", transformExec.getNodeExecuteCount("primary"))
	}
	if transformExec.getNodeExecuteCount("fallback") != 1 {
		t.Fatalf("Expected fallback path to execute once, got %d", transformExec.getNodeExecuteCount("fallback"))
	}
	if outputExec.getNodeExecuteCount("output1") != 1 {
		t.Fatalf("Expected output node to execute once, got %d", outputExec.getNodeExecuteCount("output1"))
	}
}

func TestScheduler_OnErrorFallbackInvalidTargetFailsRun(t *testing.T) {
	nodes := []entity.Node{
		{ID: "fail", Type: "transform", Name: "Fail Node", Config: map[string]any{
			"expression_type": "static",
			"expression":      "fail",
			"output_key":      "result",
			"on_error": map[string]any{
				"strategy":   "fallback",
				"next_nodes": []string{"missing"},
			},
		}},
		{ID: "output1", Type: "output", Name: "Output 1", Config: map[string]any{}},
	}
	edges := []entity.Edge{
		{From: "fail", To: "output1"},
	}
	graphJSON := makeGraphJSON(nodes, edges)

	repo := newMockRepository()
	emitter := newRecordingEmitter()

	transformExec := newMockExecutor("transform", func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return nil, fmt.Errorf("force fallback failure")
	})
	outputExec := newMockExecutor("output", func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewSuccessResult(map[string]any{"ok": true}), nil
	})

	registry := port.NewExecutorRegistry()
	registry.RegisterAll(transformExec, outputExec)

	scheduler := NewScheduler(
		SchedulerConfig{MaxWorkers: 2, DefaultTimeoutMs: 5000},
		registry,
		repo,
		emitter,
		store.NewInMemoryMemoryStore(),
	)

	if err := scheduler.StartRun(context.Background(), "run-onerror-invalid-fallback", graphJSON, "{}", "", "", "", ""); err != nil {
		t.Fatalf("StartRun failed: %v", err)
	}

	waitForRunCompletion(t, scheduler, repo, "run-onerror-invalid-fallback", 5*time.Second)

	if repo.getRunStatus("run-onerror-invalid-fallback") != string(value.RunStatusFailed) {
		t.Fatalf("Expected run status failed, got %s", repo.getRunStatus("run-onerror-invalid-fallback"))
	}
	nodeRun, ok := repo.nodeRuns["run-onerror-invalid-fallback-fail"]
	if !ok {
		t.Fatalf("Expected failed node run to be persisted")
	}
	if _, exists := nodeRun.ErrorJSON["on_error_routing_error"]; !exists {
		t.Fatalf("Expected on_error_routing_error in error payload, got %v", nodeRun.ErrorJSON)
	}
}

func TestScheduler_OnErrorRetryOverridesRetryPolicy(t *testing.T) {
	nodes := []entity.Node{
		{ID: "retry", Type: "transform", Name: "Retry Node", Config: map[string]any{
			"expression_type": "static",
			"expression":      "retry",
			"output_key":      "result",
			"on_error": map[string]any{
				"strategy":         "retry",
				"max_attempts":     2,
				"backoff_ms":       1,
				"backoff_strategy": "fixed",
			},
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
		attemptMu.Unlock()
		return nil, domain.NewRetryableError(fmt.Errorf("retry me"), "transient")
	})
	outputExec := newMockExecutor("output", func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewSuccessResult(map[string]any{"ok": true}), nil
	})

	registry := port.NewExecutorRegistry()
	registry.RegisterAll(transformExec, outputExec)

	scheduler := NewScheduler(
		SchedulerConfig{MaxWorkers: 2, DefaultTimeoutMs: 5000},
		registry,
		repo,
		emitter,
		store.NewInMemoryMemoryStore(),
	)

	if err := scheduler.StartRun(context.Background(), "run-onerror-retry-policy", graphJSON, "{}", "", "", "", ""); err != nil {
		t.Fatalf("StartRun failed: %v", err)
	}

	waitForRunCompletion(t, scheduler, repo, "run-onerror-retry-policy", 5*time.Second)

	attemptMu.Lock()
	if attemptCount != 2 {
		t.Fatalf("Expected 2 attempts from on_error retry override, got %d", attemptCount)
	}
	attemptMu.Unlock()

	if repo.getRunStatus("run-onerror-retry-policy") != string(value.RunStatusFailed) {
		t.Fatalf("Expected run status failed, got %s", repo.getRunStatus("run-onerror-retry-policy"))
	}

	nodeRun, ok := repo.nodeRuns["run-onerror-retry-policy-retry"]
	if !ok {
		t.Fatalf("Expected failed node run to be persisted")
	}
	if nodeRun.Attempt != 2 {
		t.Fatalf("Expected final node attempt 2, got %d", nodeRun.Attempt)
	}
	if nodeRun.ErrorJSON["max_attempts"] != 2 {
		t.Fatalf("Expected max_attempts=2 in error payload, got %v", nodeRun.ErrorJSON["max_attempts"])
	}

	events := emitter.getEvents()
	finalAttempt := 0
	for _, ev := range events {
		if ev.Type == port.EventTypeNodeFailed {
			finalAttempt = ev.Attempt
		}
	}
	if finalAttempt != 2 {
		t.Fatalf("Expected node_failed event attempt=2, got %d", finalAttempt)
	}
}

func TestScheduler_RetryAfterDelayRespected(t *testing.T) {
	nodes := []entity.Node{
		{ID: "retry", Type: "transform", Name: "Retry Node", Config: map[string]any{
			"expression_type": "static",
			"expression":      "retry",
			"output_key":      "result",
		}, RetryPolicy: &entity.RetryPolicy{
			MaxAttempts:     2,
			BackoffMs:       1,
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
	var firstAttemptAt time.Time
	var secondAttemptAt time.Time
	var attemptMu sync.Mutex

	transformExec := newMockExecutor("transform", func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		attemptMu.Lock()
		defer attemptMu.Unlock()
		attemptCount++
		if attemptCount == 1 {
			firstAttemptAt = time.Now()
			return nil, domain.NewRetryableErrorWithDetails(
				fmt.Errorf("rate limited"),
				"rate limited",
				"rate_limited",
				40,
				map[string]any{
					"retry_after_ms": 40,
				},
			)
		}
		secondAttemptAt = time.Now()
		return port.NewSuccessResult(map[string]any{"ok": true}), nil
	})

	outputExec := newMockExecutor("output", func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewSuccessResult(map[string]any{"ok": true}), nil
	})

	registry := port.NewExecutorRegistry()
	registry.RegisterAll(transformExec, outputExec)

	config := SchedulerConfig{MaxWorkers: 2, DefaultTimeoutMs: 5000}
	scheduler := NewScheduler(config, registry, repo, emitter, store.NewInMemoryMemoryStore())

	err := scheduler.StartRun(context.Background(), "run-retry-after", graphJSON, "{}", "", "", "", "")
	if err != nil {
		t.Fatalf("StartRun failed: %v", err)
	}

	waitForRunCompletion(t, scheduler, repo, "run-retry-after", 5*time.Second)

	if repo.getRunStatus("run-retry-after") != string(value.RunStatusSucceeded) {
		t.Fatalf("Expected run status succeeded, got %s", repo.getRunStatus("run-retry-after"))
	}

	if firstAttemptAt.IsZero() || secondAttemptAt.IsZero() {
		t.Fatalf("Expected two attempts to run")
	}
	delayMs := secondAttemptAt.Sub(firstAttemptAt).Milliseconds()
	if delayMs < 30 {
		t.Fatalf("Expected retry delay to respect retry_after (>=30ms), got %dms", delayMs)
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
	scheduler := NewScheduler(config, registry, repo, emitter, store.NewInMemoryMemoryStore())

	err := scheduler.StartRun(context.Background(), "run-branch-merge", graphJSON, "{}", "", "", "", "")
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

func TestScheduler_DynamicNextNodesFromOutput(t *testing.T) {
	nodes := []entity.Node{
		{ID: "start", Type: "transform", Name: "Start", Config: map[string]any{}},
		{ID: "branch", Type: "transform", Name: "Branch", Config: map[string]any{}},
		{ID: "output", Type: "output", Name: "Output", Config: map[string]any{}},
	}
	edges := []entity.Edge{
		{From: "start", To: "branch"},
		{From: "start", To: "output"},
		{From: "branch", To: "output"},
	}
	graphJSON := makeGraphJSON(nodes, edges)

	repo := newMockRepository()
	emitter := newRecordingEmitter()

	transformExec := newMockExecutor("transform", func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		if node.ID == "start" {
			return &port.NodeExecutionResult{
				Output: map[string]any{
					"next_nodes": []string{"output"},
				},
			}, nil
		}
		return &port.NodeExecutionResult{Output: map[string]any{"ran": node.ID}}, nil
	})

	outputExec := newMockExecutor("output", func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return &port.NodeExecutionResult{Output: map[string]any{"ok": true}}, nil
	})

	registry := port.NewExecutorRegistry()
	registry.RegisterAll(transformExec, outputExec)

	config := SchedulerConfig{MaxWorkers: 2, DefaultTimeoutMs: 5000}
	scheduler := NewScheduler(config, registry, repo, emitter, store.NewInMemoryMemoryStore())

	err := scheduler.StartRun(context.Background(), "run-dynamic-next", graphJSON, "{}", "", "", "", "")
	if err != nil {
		t.Fatalf("StartRun failed: %v", err)
	}

	waitForRunCompletion(t, scheduler, repo, "run-dynamic-next", 5*time.Second)

	if transformExec.getNodeExecuteCount("start") != 1 {
		t.Errorf("Expected start to execute once, got %d", transformExec.getNodeExecuteCount("start"))
	}
	if transformExec.getNodeExecuteCount("branch") != 0 {
		t.Errorf("Expected branch to be skipped, got %d", transformExec.getNodeExecuteCount("branch"))
	}
	if outputExec.getNodeExecuteCount("output") != 1 {
		t.Errorf("Expected output to execute once, got %d", outputExec.getNodeExecuteCount("output"))
	}
}

func TestScheduler_CycleExecutionWithDynamicRouting(t *testing.T) {
	nodes := []entity.Node{
		{ID: "loopStart", Type: "transform", Name: "Loop Start", Config: map[string]any{}},
		{ID: "router", Type: "transform", Name: "Router", Config: map[string]any{}},
		{ID: "output", Type: "output", Name: "Output", Config: map[string]any{}},
	}
	edges := []entity.Edge{
		{From: "loopStart", To: "router"},
		{From: "router", To: "loopStart"},
		{From: "router", To: "output"},
	}
	graphData, err := json.Marshal(entity.Graph{
		Nodes: nodes,
		Edges: edges,
		Metadata: map[string]any{
			"allow_cycles":       true,
			"default_max_visits": 10,
		},
	})
	if err != nil {
		t.Fatalf("Failed to marshal loop graph: %v", err)
	}
	graphJSON := string(graphData)

	repo := newMockRepository()
	emitter := newRecordingEmitter()

	transformExec := newMockExecutor("transform", func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		switch node.ID {
		case "loopStart":
			counter := 0
			if raw, exists := state.GetVar("counter"); exists {
				switch value := raw.(type) {
				case int:
					counter = value
				case float64:
					counter = int(value)
				}
			}
			counter++
			state.SetVar("counter", counter)
			return port.NewSuccessResult(map[string]any{"counter": counter}), nil
		case "router":
			counter := 0
			if raw, exists := state.GetVar("counter"); exists {
				switch value := raw.(type) {
				case int:
					counter = value
				case float64:
					counter = int(value)
				}
			}
			if counter < 3 {
				return &port.NodeExecutionResult{
					Output: map[string]any{
						"next_nodes": []string{"loopStart"},
					},
				}, nil
			}
			return &port.NodeExecutionResult{
				Output: map[string]any{
					"next_nodes": []string{"output"},
				},
			}, nil
		default:
			return port.NewSuccessResult(map[string]any{"ok": true}), nil
		}
	})

	outputExec := newMockExecutor("output", func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		counter, _ := state.GetVar("counter")
		return port.NewSuccessResult(map[string]any{"counter": counter}), nil
	})

	registry := port.NewExecutorRegistry()
	registry.RegisterAll(transformExec, outputExec)

	config := SchedulerConfig{MaxWorkers: 2, DefaultTimeoutMs: 5000}
	scheduler := NewScheduler(config, registry, repo, emitter, store.NewInMemoryMemoryStore())

	if err := scheduler.StartRun(context.Background(), "run-loop-routing", graphJSON, "{}", "", "", "", ""); err != nil {
		t.Fatalf("StartRun failed: %v", err)
	}

	waitForRunCompletion(t, scheduler, repo, "run-loop-routing", 5*time.Second)

	if repo.getRunStatus("run-loop-routing") != string(value.RunStatusSucceeded) {
		t.Fatalf("Expected run status succeeded, got %s", repo.getRunStatus("run-loop-routing"))
	}
	if transformExec.getNodeExecuteCount("loopStart") != 3 {
		t.Errorf("Expected loopStart to execute 3 times, got %d", transformExec.getNodeExecuteCount("loopStart"))
	}
	if transformExec.getNodeExecuteCount("router") != 3 {
		t.Errorf("Expected router to execute 3 times, got %d", transformExec.getNodeExecuteCount("router"))
	}
	if outputExec.getNodeExecuteCount("output") != 1 {
		t.Errorf("Expected output to execute once, got %d", outputExec.getNodeExecuteCount("output"))
	}

	events := emitter.getEvents()
	var completedEvents int
	for _, ev := range events {
		if ev.Type != port.EventTypeNodeCompleted {
			continue
		}
		completedEvents++
		loopPayload, ok := ev.Output["loop"].(map[string]any)
		if !ok {
			t.Fatalf("expected loop diagnostics on node_completed event for node %s", ev.NodeID)
		}
		iterationValue, exists := loopPayload["iteration_index"]
		if !exists {
			t.Fatalf("expected iteration_index in loop diagnostics for node %s", ev.NodeID)
		}
		iteration := 0
		switch typed := iterationValue.(type) {
		case int:
			iteration = typed
		case int64:
			iteration = int(typed)
		case float64:
			iteration = int(typed)
		default:
			t.Fatalf("unexpected iteration_index type for node %s: %T", ev.NodeID, iterationValue)
		}
		if iteration <= 0 {
			t.Fatalf("expected positive iteration index for node %s, got %#v", ev.NodeID, iterationValue)
		}
		if _, ok := loopPayload["exit_reason"].(string); !ok {
			t.Fatalf("expected exit_reason in loop diagnostics for node %s", ev.NodeID)
		}
	}
	if completedEvents == 0 {
		t.Fatal("expected node_completed events with loop diagnostics")
	}
}

func TestScheduler_NodeCacheTTL(t *testing.T) {
	nodes := []entity.Node{
		{ID: "cached", Type: "transform", Name: "Cached", Config: map[string]any{
			"cache": map[string]any{
				"enabled":     true,
				"ttl_seconds": 60,
			},
		}},
		{ID: "output", Type: "output", Name: "Output", Config: map[string]any{}},
	}
	edges := []entity.Edge{
		{From: "cached", To: "output"},
	}
	graphJSON := makeGraphJSON(nodes, edges)

	repo := newMockRepository()
	emitter := newRecordingEmitter()

	transformExec := newMockExecutor("transform", func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return &port.NodeExecutionResult{Output: map[string]any{"value": "cached"}}, nil
	})
	outputExec := newMockExecutor("output", func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return &port.NodeExecutionResult{Output: map[string]any{"ok": true}}, nil
	})

	registry := port.NewExecutorRegistry()
	registry.RegisterAll(transformExec, outputExec)

	config := SchedulerConfig{MaxWorkers: 2, DefaultTimeoutMs: 5000}
	scheduler := NewScheduler(config, registry, repo, emitter, store.NewInMemoryMemoryStore())

	err := scheduler.StartRun(context.Background(), "run-cache-1", graphJSON, "{}", "", "", "", "")
	if err != nil {
		t.Fatalf("StartRun failed: %v", err)
	}
	waitForRunCompletion(t, scheduler, repo, "run-cache-1", 5*time.Second)

	err = scheduler.StartRun(context.Background(), "run-cache-2", graphJSON, "{}", "", "", "", "")
	if err != nil {
		t.Fatalf("StartRun failed: %v", err)
	}
	waitForRunCompletion(t, scheduler, repo, "run-cache-2", 5*time.Second)

	if transformExec.getExecuteCount() != 1 {
		t.Errorf("Expected cached transform to execute once, got %d", transformExec.getExecuteCount())
	}
}

func TestSessionBufferPersistence(t *testing.T) {
	memoryStore := store.NewInMemoryMemoryStore()
	scheduler := NewScheduler(DefaultSchedulerConfig(), port.NewExecutorRegistry(), newMockRepository(), port.NewNoOpEventEmitter(), memoryStore)

	buffer := entity.NewMessageBuffer(10)
	buffer.Push(entity.Message{Role: "user", Content: "hello"})
	buffer.Push(entity.Message{Role: "assistant", Content: "world"})
	snapshot := buffer.Snapshot()

	rc := &runContext{
		tenantID:      "tenant-1",
		sessionID:     "session-1",
		messageBuffer: buffer,
		memoryConfig: &entity.MemoryConfig{
			CrossSession: entity.CrossSessionConfig{Enabled: true, SessionTTLHours: 1},
		},
	}

	scheduler.persistSessionBuffer(rc, snapshot)
	loaded := scheduler.loadSessionBuffer(context.Background(), rc.tenantID, rc.sessionID)

	if len(loaded) != len(snapshot) {
		t.Fatalf("expected %d messages, got %d", len(snapshot), len(loaded))
	}
	if loaded[0].Content != "hello" || loaded[1].Content != "world" {
		t.Fatalf("unexpected loaded messages: %#v", loaded)
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
	scheduler := NewScheduler(config, registry, repo, emitter, store.NewInMemoryMemoryStore())

	err := scheduler.StartRun(context.Background(), "run-8", graphJSON, inputJSON, "", "", "", "")
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
	waitForSchedulerCondition(t, timeout, func() bool {
		if !scheduler.IsRunActive(runID) {
			return true
		}
		return false
	}, fmt.Sprintf("Run %s did not complete within %v", runID, timeout))
}

func waitForRunInactive(t *testing.T, scheduler *Scheduler, runID string, timeout time.Duration) {
	t.Helper()
	waitForSchedulerCondition(t, timeout, func() bool {
		if !scheduler.IsRunActive(runID) {
			return true
		}
		return false
	}, fmt.Sprintf("Run %s did not become inactive within %v", runID, timeout))
}

func waitForSchedulerCondition(t *testing.T, timeout time.Duration, condition func() bool, failureMessage string) {
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

// =============================================================================
// Test: Disabled Nodes
// =============================================================================

func TestScheduler_DisabledNodeIsSkipped(t *testing.T) {
	// Create a graph with a disabled node that should be skipped
	nodes := []entity.Node{
		{ID: "start", Type: "transform", Name: "Start", Config: map[string]any{
			"expression_type": "static",
			"expression":      "started",
			"output_key":      "status",
		}},
		{ID: "disabled_node", Type: "transform", Name: "Disabled Node", Disabled: true, Config: map[string]any{
			"expression_type": "static",
			"expression":      "should_not_run",
			"output_key":      "disabled_output",
		}},
		{ID: "output1", Type: "output", Name: "Output 1", Config: map[string]any{}},
	}
	edges := []entity.Edge{
		{From: "start", To: "disabled_node"},
		{From: "disabled_node", To: "output1"},
	}
	graphJSON := makeGraphJSON(nodes, edges)

	repo := newMockRepository()
	emitter := newRecordingEmitter()

	transformExec := newMockExecutor("transform", func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return &port.NodeExecutionResult{Output: map[string]any{"node_id": node.ID}}, nil
	})

	outputExec := newMockExecutor("output", func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return &port.NodeExecutionResult{Output: map[string]any{"done": true}}, nil
	})

	registry := port.NewExecutorRegistry()
	registry.RegisterAll(transformExec, outputExec)

	config := SchedulerConfig{MaxWorkers: 2, DefaultTimeoutMs: 5000}
	scheduler := NewScheduler(config, registry, repo, emitter, store.NewInMemoryMemoryStore())

	err := scheduler.StartRun(context.Background(), "run-disabled", graphJSON, "{}", "", "", "", "")
	if err != nil {
		t.Fatalf("StartRun failed: %v", err)
	}

	waitForRunCompletion(t, scheduler, repo, "run-disabled", 5*time.Second)

	// Verify disabled node was not executed
	if transformExec.getNodeExecuteCount("disabled_node") != 0 {
		t.Errorf("Expected disabled_node to be skipped (0 executes), got %d", transformExec.getNodeExecuteCount("disabled_node"))
	}

	// Verify start node was executed
	if transformExec.getNodeExecuteCount("start") != 1 {
		t.Errorf("Expected start to execute once, got %d", transformExec.getNodeExecuteCount("start"))
	}

	// Verify output node was executed (downstream of disabled node)
	if outputExec.getNodeExecuteCount("output1") != 0 {
		t.Errorf("Expected output1 to be skipped, got %d", outputExec.getNodeExecuteCount("output1"))
	}

	// Verify run completed successfully
	if repo.getRunStatus("run-disabled") != string(value.RunStatusSucceeded) {
		t.Errorf("Expected run status succeeded, got %s", repo.getRunStatus("run-disabled"))
	}

	// Verify skipped event was emitted
	if !emitter.hasEventType(port.EventTypeNodeSkipped) {
		t.Error("Expected node_skipped event for disabled node")
	}
}

func TestScheduler_DisabledNodeWithMultipleDownstream(t *testing.T) {
	// Test that a disabled node properly propagates to its downstream nodes
	nodes := []entity.Node{
		{ID: "start", Type: "transform", Name: "Start", Config: map[string]any{}},
		{ID: "disabled", Type: "transform", Name: "Disabled", Disabled: true, Config: map[string]any{}},
		{ID: "after_disabled", Type: "transform", Name: "After Disabled", Config: map[string]any{}},
		{ID: "output", Type: "output", Name: "Output", Config: map[string]any{}},
	}
	edges := []entity.Edge{
		{From: "start", To: "disabled"},
		{From: "disabled", To: "after_disabled"},
		{From: "after_disabled", To: "output"},
	}
	graphJSON := makeGraphJSON(nodes, edges)

	repo := newMockRepository()
	emitter := newRecordingEmitter()

	transformExec := newMockExecutor("transform", func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewSuccessResult(map[string]any{"ran": node.ID}), nil
	})
	outputExec := newMockExecutor("output", func(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
		return port.NewSuccessResult(map[string]any{"ok": true}), nil
	})

	registry := port.NewExecutorRegistry()
	registry.RegisterAll(transformExec, outputExec)

	config := SchedulerConfig{MaxWorkers: 2, DefaultTimeoutMs: 5000}
	scheduler := NewScheduler(config, registry, repo, emitter, store.NewInMemoryMemoryStore())

	err := scheduler.StartRun(context.Background(), "run-disabled-chain", graphJSON, "{}", "", "", "", "")
	if err != nil {
		t.Fatalf("StartRun failed: %v", err)
	}

	waitForRunCompletion(t, scheduler, repo, "run-disabled-chain", 5*time.Second)

	// Verify disabled node was skipped
	if transformExec.getNodeExecuteCount("disabled") != 0 {
		t.Errorf("Expected disabled node to be skipped, got %d", transformExec.getNodeExecuteCount("disabled"))
	}

	// The after_disabled node should be skipped because its only upstream is skipped
	// This tests the recursive skip behavior
	if transformExec.getNodeExecuteCount("after_disabled") != 0 {
		t.Errorf("Expected after_disabled to be skipped (only upstream is skipped), got %d", transformExec.getNodeExecuteCount("after_disabled"))
	}

	// Output should also be skipped since its only upstream is skipped
	if outputExec.getNodeExecuteCount("output") != 0 {
		t.Errorf("Expected output to be skipped, got %d", outputExec.getNodeExecuteCount("output"))
	}
}

func TestScheduler_MaybeTriggerSummarization(t *testing.T) {
	s := &Scheduler{}
	emitter := newRecordingEmitter()
	s.emitter = emitter

	summarizer := &summarizerStub{}
	worker := NewSummarizationWorker(summarizer, 1, 5)
	worker.Start(context.Background())
	defer worker.Stop()
	s.SetSummarizationWorker(worker)

	buffer := entity.NewMessageBuffer(10)
	buffer.Push(entity.Message{Role: "user", Content: "one"})
	buffer.Push(entity.Message{Role: "assistant", Content: "two"})
	buffer.Push(entity.Message{Role: "user", Content: "three"})
	buffer.Push(entity.Message{Role: "assistant", Content: "four"})

	cfg := &entity.MemoryConfig{
		Tier1: entity.Tier1Config{Enabled: true, AutoPrepend: true},
		Tier2: entity.Tier2Config{Enabled: true, SummaryTTL: 60, FactsTTL: 120},
		Summarization: entity.SummarizationConfig{
			Enabled:          true,
			TriggerThreshold: 4,
			KeepRecentCount:  2,
			CooldownMessages: 5,
			Model:            "gpt-4",
		},
	}

	rc := &runContext{
		runID:         "run-1",
		tenantID:      "tenant-1",
		messageBuffer: buffer,
		memoryConfig:  cfg,
		memoryCtx: &port.RunContext{
			MemoryBuffer: buffer,
			MemoryConfig: cfg,
		},
	}
	rc.memoryCtx.TrackMessage = rc.trackMessages
	rc.trackMessages(4)

	node := &entity.Node{ID: "prompt-1", Type: string(value.NodeTypePrompt)}
	s.maybeTriggerSummarization(rc, node)

	waitForSchedulerCondition(t, 2*time.Second, func() bool {
		return rc.currentSummary != nil && rc.messageBuffer.Count() == 2
	}, fmt.Sprintf("expected summary and trimmed buffer, got summary=%v count=%d", rc.currentSummary, rc.messageBuffer.Count()))

	events := emitter.getEvents()
	if len(events) != 1 {
		t.Fatalf("expected one backend memory intent event, got %d", len(events))
	}
	if events[0].Type != port.EventTypeSummaryCreated {
		t.Fatalf("event type = %s, want %s", events[0].Type, port.EventTypeSummaryCreated)
	}
	if events[0].Output["backend_owner"] != "memory_service" {
		t.Fatalf("backend_owner = %#v, want memory_service", events[0].Output["backend_owner"])
	}
}

type summarizerStub struct {
	mu    sync.Mutex
	calls int
}

func (s *summarizerStub) Summarize(ctx context.Context, messages []entity.Message, opts port.SummarizeOptions) (*entity.Summary, error) {
	s.mu.Lock()
	s.calls++
	s.mu.Unlock()
	return &entity.Summary{
		ID:      "summary-1",
		Content: "summary",
	}, nil
}

func (s *summarizerStub) ExtractFacts(ctx context.Context, messages []entity.Message) ([]entity.Fact, error) {
	return nil, nil
}
