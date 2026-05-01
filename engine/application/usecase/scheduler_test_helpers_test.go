package usecase

import (
	"context"
	"encoding/json"
	"fmt"
	"sync"
	"testing"
	"time"

	"github.com/forgegraph/engine/adapter/executor"
	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/domain"
	"github.com/forgegraph/engine/domain/entity"
)

// mockRepository implements port.RunRepository for deterministic tests.
type mockRepository struct {
	runsMu        sync.RWMutex
	nodeRunsMu    sync.RWMutex
	pausesMu      sync.RWMutex
	checkpointsMu sync.RWMutex
	snapshotsMu   sync.RWMutex
	cacheMu       sync.RWMutex

	runs        map[string]*entity.Run
	nodeRuns    map[string]*entity.NodeRun
	pauses      map[string]mockPauseState
	checkpoints map[string]mockCheckpointState
	snapshots   map[string]*port.RunResumeSnapshot
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
		snapshots:   make(map[string]*port.RunResumeSnapshot),
		cache:       make(map[string]mockCacheEntry),
	}
}

// ---------------- RUNS ----------------

func (r *mockRepository) GetRun(ctx context.Context, runID string) (*entity.Run, error) {
	r.runsMu.RLock()
	defer r.runsMu.RUnlock()

	run, ok := r.runs[runID]
	if !ok {
		return nil, domain.ErrRunNotFound
	}
	return cloneRunEntity(run), nil
}

func (r *mockRepository) UpdateRunStatus(ctx context.Context, runID, status string) error {
	r.runsMu.Lock()
	defer r.runsMu.Unlock()

	if r.runs[runID] == nil {
		r.runs[runID] = &entity.Run{ID: runID}
	}
	r.runs[runID].Status = status
	return nil
}

func (r *mockRepository) UpdateRunOutput(ctx context.Context, runID string, output map[string]any) error {
	r.runsMu.Lock()
	defer r.runsMu.Unlock()

	if r.runs[runID] == nil {
		r.runs[runID] = &entity.Run{ID: runID}
	}
	r.runs[runID].OutputJSON = cloneMapAny(output)
	return nil
}

func (r *mockRepository) UpdateRunError(ctx context.Context, runID, errorMsg string) error {
	r.runsMu.Lock()
	defer r.runsMu.Unlock()

	if r.runs[runID] == nil {
		r.runs[runID] = &entity.Run{ID: runID}
	}
	r.runs[runID].ErrorMessage = errorMsg
	return nil
}

func (r *mockRepository) SetRunEnded(ctx context.Context, runID, status string, output map[string]any, errorMsg string) error {
	r.runsMu.Lock()
	defer r.runsMu.Unlock()

	if r.runs[runID] == nil {
		r.runs[runID] = &entity.Run{ID: runID}
	}
	r.runs[runID].Status = status
	r.runs[runID].OutputJSON = cloneMapAny(output)
	r.runs[runID].ErrorMessage = errorMsg
	return nil
}

func (r *mockRepository) getRunStatus(runID string) string {
	r.runsMu.RLock()
	defer r.runsMu.RUnlock()

	if run, ok := r.runs[runID]; ok {
		return run.Status
	}
	return ""
}

// ---------------- PAUSES ----------------

func (r *mockRepository) SavePauseState(ctx context.Context, runID, pausedNodeID string, stateSnapshot map[string]any, completedNodes []string, skippedNodes []string, graphJSON string, tenantID string) error {
	r.pausesMu.Lock()
	defer r.pausesMu.Unlock()

	r.pauses[runID] = mockPauseState{
		pausedNodeID:   pausedNodeID,
		stateSnapshot:  cloneMapAny(stateSnapshot),
		completedNodes: append([]string(nil), completedNodes...),
		skippedNodes:   append([]string(nil), skippedNodes...),
		graphJSON:      graphJSON,
		tenantID:       tenantID,
	}
	return nil
}

func (r *mockRepository) LoadPauseState(ctx context.Context, runID string) (string, map[string]any, []string, []string, string, string, error) {
	r.pausesMu.RLock()
	defer r.pausesMu.RUnlock()

	pause, ok := r.pauses[runID]
	if !ok {
		return "", nil, nil, nil, "", "", fmt.Errorf("pause state not found")
	}
	return pause.pausedNodeID,
		cloneMapAny(pause.stateSnapshot),
		append([]string(nil), pause.completedNodes...),
		append([]string(nil), pause.skippedNodes...),
		pause.graphJSON,
		pause.tenantID,
		nil
}

func (r *mockRepository) ClearPauseState(ctx context.Context, runID string) error {
	r.pausesMu.Lock()
	defer r.pausesMu.Unlock()

	delete(r.pauses, runID)
	return nil
}

// ---------------- CHECKPOINTS ----------------

func (r *mockRepository) SaveCheckpoint(ctx context.Context, runID, nodeID string, stepIndex int, stateSnapshot map[string]any, completedNodes []string, skippedNodes []string, graphJSON string) error {
	r.checkpointsMu.Lock()
	defer r.checkpointsMu.Unlock()

	r.checkpoints[runID] = mockCheckpointState{
		nodeID:         nodeID,
		stepIndex:      stepIndex,
		stateSnapshot:  cloneMapAny(stateSnapshot),
		completedNodes: append([]string(nil), completedNodes...),
		skippedNodes:   append([]string(nil), skippedNodes...),
		graphJSON:      graphJSON,
	}
	return nil
}

func (r *mockRepository) LoadLatestCheckpoint(ctx context.Context, runID string) (string, int, map[string]any, []string, []string, string, error) {
	r.checkpointsMu.RLock()
	defer r.checkpointsMu.RUnlock()

	checkpoint, ok := r.checkpoints[runID]
	if !ok {
		return "", 0, nil, nil, nil, "", domain.ErrCheckpointNotFound
	}
	return checkpoint.nodeID,
		checkpoint.stepIndex,
		cloneMapAny(checkpoint.stateSnapshot),
		append([]string(nil), checkpoint.completedNodes...),
		append([]string(nil), checkpoint.skippedNodes...),
		checkpoint.graphJSON,
		nil
}

func (r *mockRepository) ClearCheckpoints(ctx context.Context, runID string) error {
	r.checkpointsMu.Lock()
	defer r.checkpointsMu.Unlock()

	delete(r.checkpoints, runID)
	return nil
}

func (r *mockRepository) LoadRunSnapshot(ctx context.Context, runID string) (*port.RunResumeSnapshot, error) {
	r.snapshotsMu.RLock()
	defer r.snapshotsMu.RUnlock()

	snapshot, ok := r.snapshots[runID]
	if ok {
		cloned := *snapshot
		return &cloned, nil
	}
	checkpoint, ok := r.checkpoints[runID]
	if !ok {
		return nil, domain.ErrCheckpointNotFound
	}
	return &port.RunResumeSnapshot{
		RunID:             runID,
		LastCompletedNode: checkpoint.nodeID,
		UpdatedAt:         time.Now(),
	}, nil
}

// ---------------- CACHE ----------------

func (r *mockRepository) GetCachedNodeResult(ctx context.Context, cacheKey string) (any, bool, error) {
	r.cacheMu.RLock()
	defer r.cacheMu.RUnlock()

	entry, ok := r.cache[cacheKey]
	if !ok {
		return nil, false, nil
	}
	if time.Now().After(entry.expiresAt) {
		delete(r.cache, cacheKey)
		return nil, false, nil
	}
	return cloneValue(entry.output), true, nil
}

func (r *mockRepository) SaveCachedNodeResult(ctx context.Context, cacheKey string, output any, ttlSeconds int) error {
	if ttlSeconds <= 0 {
		return nil
	}

	r.cacheMu.Lock()
	defer r.cacheMu.Unlock()

	r.cache[cacheKey] = mockCacheEntry{
		output:    cloneValue(output),
		expiresAt: time.Now().Add(time.Duration(ttlSeconds) * time.Second),
	}
	return nil
}

// ---------------- NODE RUNS ----------------

func (r *mockRepository) CreateNodeRun(ctx context.Context, nodeRun *entity.NodeRun) error {
	r.nodeRunsMu.Lock()
	defer r.nodeRunsMu.Unlock()

	r.nodeRuns[nodeRun.ID] = cloneNodeRunEntity(nodeRun)
	return nil
}

func (r *mockRepository) UpdateNodeRun(ctx context.Context, nodeRun *entity.NodeRun) error {
	r.nodeRunsMu.Lock()
	defer r.nodeRunsMu.Unlock()

	r.nodeRuns[nodeRun.ID] = cloneNodeRunEntity(nodeRun)
	return nil
}

func (r *mockRepository) GetNodeRun(ctx context.Context, runID, nodeID string) (*entity.NodeRun, error) {
	r.nodeRunsMu.RLock()
	defer r.nodeRunsMu.RUnlock()

	key := fmt.Sprintf("%s-%s", runID, nodeID)
	nodeRun, ok := r.nodeRuns[key]
	if !ok {
		for _, candidate := range r.nodeRuns {
			if candidate.RunID == runID && candidate.NodeID == nodeID {
				return cloneNodeRunEntity(candidate), nil
			}
		}
		return nil, fmt.Errorf("node run not found")
	}
	return cloneNodeRunEntity(nodeRun), nil
}

func (r *mockRepository) GetNodeRunsByRunID(ctx context.Context, runID string) ([]*entity.NodeRun, error) {
	r.nodeRunsMu.RLock()
	defer r.nodeRunsMu.RUnlock()

	var result []*entity.NodeRun
	for _, nr := range r.nodeRuns {
		if nr.RunID == runID {
			result = append(result, cloneNodeRunEntity(nr))
		}
	}
	return result, nil
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

// Helper to create a mock scheduler for tests
func newMockScheduler(t *testing.T) (*Scheduler, *mockRepository, *recordingEmitter) {
	repo := newMockRepository()
	emitter := newRecordingEmitter()

	return nil, repo, emitter
}
