package usecase

import (
	"context"
	"encoding/json"
	"fmt"
	"sync"
	"time"

	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/domain"
	"github.com/forgegraph/engine/domain/entity"
)

// mockRepository implements port.RunRepository for deterministic tests.
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

func cloneRunEntity(run *entity.Run) *entity.Run {
	if run == nil {
		return nil
	}
	cloned := *run
	cloned.InputJSON = cloneMapAny(run.InputJSON)
	cloned.OutputJSON = cloneMapAny(run.OutputJSON)
	if run.EndedAt != nil {
		endedAt := *run.EndedAt
		cloned.EndedAt = &endedAt
	}
	return &cloned
}

func cloneNodeRunEntity(nodeRun *entity.NodeRun) *entity.NodeRun {
	if nodeRun == nil {
		return nil
	}
	cloned := *nodeRun
	cloned.InputJSON = cloneMapAny(nodeRun.InputJSON)
	cloned.OutputJSON = cloneMapAny(nodeRun.OutputJSON)
	cloned.ErrorJSON = cloneMapAny(nodeRun.ErrorJSON)
	if nodeRun.EndedAt != nil {
		endedAt := *nodeRun.EndedAt
		cloned.EndedAt = &endedAt
	}
	return &cloned
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
	return cloneRunEntity(run), nil
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
	r.runs[runID].OutputJSON = cloneMapAny(output)
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
	r.runs[runID].OutputJSON = cloneMapAny(output)
	r.runs[runID].ErrorMessage = errorMsg
	return nil
}

func (r *mockRepository) SavePauseState(ctx context.Context, runID, pausedNodeID string, stateSnapshot map[string]any, completedNodes []string, skippedNodes []string, graphJSON string, tenantID string) error {
	r.mu.Lock()
	defer r.mu.Unlock()
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

func (r *mockRepository) LoadPauseState(ctx context.Context, runID string) (pausedNodeID string, stateSnapshot map[string]any, completedNodes []string, skippedNodes []string, graphJSON string, tenantID string, err error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	pause, ok := r.pauses[runID]
	if !ok {
		return "", nil, nil, nil, "", "", fmt.Errorf("pause state not found")
	}
	return pause.pausedNodeID, cloneMapAny(pause.stateSnapshot), append([]string(nil), pause.completedNodes...), append([]string(nil), pause.skippedNodes...), pause.graphJSON, pause.tenantID, nil
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
		stateSnapshot:  cloneMapAny(stateSnapshot),
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
	return checkpoint.nodeID, checkpoint.stepIndex, cloneMapAny(checkpoint.stateSnapshot), append([]string(nil), checkpoint.completedNodes...), append([]string(nil), checkpoint.skippedNodes...), checkpoint.graphJSON, nil
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
	return cloneValue(entry.output), true, nil
}

func (r *mockRepository) SaveCachedNodeResult(ctx context.Context, cacheKey string, output any, ttlSeconds int) error {
	if ttlSeconds <= 0 {
		return nil
	}
	r.mu.Lock()
	defer r.mu.Unlock()
	r.cache[cacheKey] = mockCacheEntry{
		output:    cloneValue(output),
		expiresAt: time.Now().Add(time.Duration(ttlSeconds) * time.Second),
	}
	return nil
}

func (r *mockRepository) CreateNodeRun(ctx context.Context, nodeRun *entity.NodeRun) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.nodeRuns[nodeRun.ID] = cloneNodeRunEntity(nodeRun)
	return nil
}

func (r *mockRepository) UpdateNodeRun(ctx context.Context, nodeRun *entity.NodeRun) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.nodeRuns[nodeRun.ID] = cloneNodeRunEntity(nodeRun)
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
	return cloneNodeRunEntity(nodeRun), nil
}

func (r *mockRepository) GetNodeRunsByRunID(ctx context.Context, runID string) ([]*entity.NodeRun, error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	var result []*entity.NodeRun
	for _, nr := range r.nodeRuns {
		if nr.RunID == runID {
			result = append(result, cloneNodeRunEntity(nr))
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

// mockExecutor implements port.NodeExecutor for deterministic tests.
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

func makeGraphJSON(nodes []entity.Node, edges []entity.Edge) string {
	graph := entity.Graph{
		Nodes: nodes,
		Edges: edges,
	}
	data, _ := json.Marshal(graph)
	return string(data)
}
