// Package repository contains repository adapter implementations for the ForgeGraph engine.
package repository

import (
	"context"
	"fmt"
	"sync"
	"time"

	"github.com/forgegraph/engine/domain"
	"github.com/forgegraph/engine/domain/entity"
)

// pauseState holds the pause information for a run
type pauseState struct {
	pausedNodeID   string
	stateSnapshot  map[string]any
	completedNodes []string
	graphJSON      string
}

type checkpointState struct {
	nodeID         string
	stepIndex      int
	stateSnapshot  map[string]any
	completedNodes []string
	skippedNodes   []string
	graphJSON      string
}

type cacheEntry struct {
	output    any
	expiresAt time.Time
}

// MemoryRunRepository is an in-memory implementation of RunRepository for testing.
// It is thread-safe and stores runs and node runs in memory.
type MemoryRunRepository struct {
	mu          sync.RWMutex
	runs        map[string]*entity.Run
	nodeRuns    map[string]*entity.NodeRun // key: runID-nodeID
	pauseStates map[string]*pauseState     // key: runID
	checkpoints map[string]*checkpointState
	cache       map[string]*cacheEntry
}

// NewMemoryRunRepository creates a new in-memory run repository
func NewMemoryRunRepository() *MemoryRunRepository {
	return &MemoryRunRepository{
		runs:        make(map[string]*entity.Run),
		nodeRuns:    make(map[string]*entity.NodeRun),
		pauseStates: make(map[string]*pauseState),
		checkpoints: make(map[string]*checkpointState),
		cache:       make(map[string]*cacheEntry),
	}
}

// AddRun adds a run to the repository (test helper)
func (r *MemoryRunRepository) AddRun(run *entity.Run) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.runs[run.ID] = run
}

// GetRun retrieves a run by ID
func (r *MemoryRunRepository) GetRun(ctx context.Context, runID string) (*entity.Run, error) {
	r.mu.RLock()
	defer r.mu.RUnlock()

	run, ok := r.runs[runID]
	if !ok {
		return nil, domain.ErrRunNotFound
	}

	// Return a copy to prevent modification
	runCopy := *run
	return &runCopy, nil
}

// UpdateRunStatus updates the status of a run
func (r *MemoryRunRepository) UpdateRunStatus(ctx context.Context, runID string, status string) error {
	r.mu.Lock()
	defer r.mu.Unlock()

	run, ok := r.runs[runID]
	if !ok {
		return domain.ErrRunNotFound
	}

	run.Status = status
	return nil
}

// UpdateRunOutput sets the final output JSON for a completed run
func (r *MemoryRunRepository) UpdateRunOutput(ctx context.Context, runID string, output map[string]any) error {
	r.mu.Lock()
	defer r.mu.Unlock()

	run, ok := r.runs[runID]
	if !ok {
		return domain.ErrRunNotFound
	}

	run.OutputJSON = output
	return nil
}

// UpdateRunError sets the error message for a failed run
func (r *MemoryRunRepository) UpdateRunError(ctx context.Context, runID string, errorMsg string) error {
	r.mu.Lock()
	defer r.mu.Unlock()

	run, ok := r.runs[runID]
	if !ok {
		return domain.ErrRunNotFound
	}

	run.ErrorMessage = errorMsg
	return nil
}

// SetRunEnded marks a run as ended with the given status and optional output/error
func (r *MemoryRunRepository) SetRunEnded(ctx context.Context, runID string, status string, output map[string]any, errorMsg string) error {
	r.mu.Lock()
	defer r.mu.Unlock()

	run, ok := r.runs[runID]
	if !ok {
		return domain.ErrRunNotFound
	}

	run.Status = status
	run.OutputJSON = output
	run.ErrorMessage = errorMsg
	run.EndedAt = timePtr(time.Now())

	return nil
}

// CreateNodeRun creates a new node run record
func (r *MemoryRunRepository) CreateNodeRun(ctx context.Context, nodeRun *entity.NodeRun) error {
	r.mu.Lock()
	defer r.mu.Unlock()

	key := nodeRunKey(nodeRun.RunID, nodeRun.NodeID)
	r.nodeRuns[key] = nodeRun
	return nil
}

// UpdateNodeRun updates an existing node run record
func (r *MemoryRunRepository) UpdateNodeRun(ctx context.Context, nodeRun *entity.NodeRun) error {
	r.mu.Lock()
	defer r.mu.Unlock()

	key := nodeRunKey(nodeRun.RunID, nodeRun.NodeID)
	if _, ok := r.nodeRuns[key]; !ok {
		return domain.ErrNodeNotFound
	}

	r.nodeRuns[key] = nodeRun
	return nil
}

// GetNodeRun retrieves a node run by run ID and node ID
func (r *MemoryRunRepository) GetNodeRun(ctx context.Context, runID, nodeID string) (*entity.NodeRun, error) {
	r.mu.RLock()
	defer r.mu.RUnlock()

	key := nodeRunKey(runID, nodeID)
	nodeRun, ok := r.nodeRuns[key]
	if !ok {
		return nil, domain.ErrNodeNotFound
	}

	// Return a copy
	nodeRunCopy := *nodeRun
	return &nodeRunCopy, nil
}

// GetNodeRunsByRunID retrieves all node runs for a given run
func (r *MemoryRunRepository) GetNodeRunsByRunID(ctx context.Context, runID string) ([]*entity.NodeRun, error) {
	r.mu.RLock()
	defer r.mu.RUnlock()

	var result []*entity.NodeRun
	for key, nodeRun := range r.nodeRuns {
		if nodeRun.RunID == runID {
			nodeRunCopy := *nodeRun
			result = append(result, &nodeRunCopy)
			_ = key // Silence unused variable warning
		}
	}

	return result, nil
}

// GetAllRuns returns all runs (test helper)
func (r *MemoryRunRepository) GetAllRuns() []*entity.Run {
	r.mu.RLock()
	defer r.mu.RUnlock()

	result := make([]*entity.Run, 0, len(r.runs))
	for _, run := range r.runs {
		runCopy := *run
		result = append(result, &runCopy)
	}
	return result
}

// GetAllNodeRuns returns all node runs (test helper)
func (r *MemoryRunRepository) GetAllNodeRuns() []*entity.NodeRun {
	r.mu.RLock()
	defer r.mu.RUnlock()

	result := make([]*entity.NodeRun, 0, len(r.nodeRuns))
	for _, nodeRun := range r.nodeRuns {
		nodeRunCopy := *nodeRun
		result = append(result, &nodeRunCopy)
	}
	return result
}

// Clear removes all data (test helper)
func (r *MemoryRunRepository) Clear() {
	r.mu.Lock()
	defer r.mu.Unlock()

	r.runs = make(map[string]*entity.Run)
	r.nodeRuns = make(map[string]*entity.NodeRun)
	r.pauseStates = make(map[string]*pauseState)
	r.checkpoints = make(map[string]*checkpointState)
	r.cache = make(map[string]*cacheEntry)
}

// SavePauseState saves the execution state when a run is paused at a human gate
func (r *MemoryRunRepository) SavePauseState(ctx context.Context, runID, pausedNodeID string, stateSnapshot map[string]any, completedNodes []string, graphJSON string) error {
	r.mu.Lock()
	defer r.mu.Unlock()

	if _, ok := r.runs[runID]; !ok {
		return domain.ErrRunNotFound
	}

	r.pauseStates[runID] = &pauseState{
		pausedNodeID:   pausedNodeID,
		stateSnapshot:  stateSnapshot,
		completedNodes: completedNodes,
		graphJSON:      graphJSON,
	}

	return nil
}

// LoadPauseState retrieves the saved pause state for resuming a run
func (r *MemoryRunRepository) LoadPauseState(ctx context.Context, runID string) (pausedNodeID string, stateSnapshot map[string]any, completedNodes []string, graphJSON string, err error) {
	r.mu.RLock()
	defer r.mu.RUnlock()

	if _, ok := r.runs[runID]; !ok {
		return "", nil, nil, "", domain.ErrRunNotFound
	}

	ps, ok := r.pauseStates[runID]
	if !ok || ps.pausedNodeID == "" {
		return "", nil, nil, "", fmt.Errorf("run is not paused")
	}

	return ps.pausedNodeID, ps.stateSnapshot, ps.completedNodes, ps.graphJSON, nil
}

// ClearPauseState removes the pause state after a run is resumed
func (r *MemoryRunRepository) ClearPauseState(ctx context.Context, runID string) error {
	r.mu.Lock()
	defer r.mu.Unlock()

	if _, ok := r.runs[runID]; !ok {
		return domain.ErrRunNotFound
	}

	delete(r.pauseStates, runID)
	return nil
}

// SaveCheckpoint persists the latest execution state for durable resume
func (r *MemoryRunRepository) SaveCheckpoint(ctx context.Context, runID, nodeID string, stepIndex int, stateSnapshot map[string]any, completedNodes []string, skippedNodes []string, graphJSON string) error {
	r.mu.Lock()
	defer r.mu.Unlock()

	if _, ok := r.runs[runID]; !ok {
		return domain.ErrRunNotFound
	}

	if existing, ok := r.checkpoints[runID]; ok && existing.stepIndex > stepIndex {
		return nil
	}

	completedCopy := append([]string(nil), completedNodes...)
	skippedCopy := append([]string(nil), skippedNodes...)

	r.checkpoints[runID] = &checkpointState{
		nodeID:         nodeID,
		stepIndex:      stepIndex,
		stateSnapshot:  stateSnapshot,
		completedNodes: completedCopy,
		skippedNodes:   skippedCopy,
		graphJSON:      graphJSON,
	}

	return nil
}

// LoadLatestCheckpoint retrieves the most recent checkpoint for a run
func (r *MemoryRunRepository) LoadLatestCheckpoint(ctx context.Context, runID string) (nodeID string, stepIndex int, stateSnapshot map[string]any, completedNodes []string, skippedNodes []string, graphJSON string, err error) {
	r.mu.RLock()
	defer r.mu.RUnlock()

	if _, ok := r.runs[runID]; !ok {
		return "", 0, nil, nil, nil, "", domain.ErrRunNotFound
	}

	checkpoint, ok := r.checkpoints[runID]
	if !ok {
		return "", 0, nil, nil, nil, "", domain.ErrCheckpointNotFound
	}

	completedCopy := append([]string(nil), checkpoint.completedNodes...)
	skippedCopy := append([]string(nil), checkpoint.skippedNodes...)

	return checkpoint.nodeID, checkpoint.stepIndex, checkpoint.stateSnapshot, completedCopy, skippedCopy, checkpoint.graphJSON, nil
}

// ClearCheckpoints removes all checkpoints for a run
func (r *MemoryRunRepository) ClearCheckpoints(ctx context.Context, runID string) error {
	r.mu.Lock()
	defer r.mu.Unlock()

	if _, ok := r.runs[runID]; !ok {
		return domain.ErrRunNotFound
	}

	delete(r.checkpoints, runID)
	return nil
}

// GetCachedNodeResult retrieves a cached node output by key if not expired
func (r *MemoryRunRepository) GetCachedNodeResult(ctx context.Context, cacheKey string) (output any, found bool, err error) {
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

// SaveCachedNodeResult stores a cached node output with TTL seconds
func (r *MemoryRunRepository) SaveCachedNodeResult(ctx context.Context, cacheKey string, output any, ttlSeconds int) error {
	if ttlSeconds <= 0 {
		return nil
	}
	r.mu.Lock()
	defer r.mu.Unlock()

	r.cache[cacheKey] = &cacheEntry{
		output:    output,
		expiresAt: time.Now().Add(time.Duration(ttlSeconds) * time.Second),
	}
	return nil
}

// nodeRunKey generates a unique key for a node run
func nodeRunKey(runID, nodeID string) string {
	return fmt.Sprintf("%s-%s", runID, nodeID)
}

// timePtr returns a pointer to a time value
func timePtr(t time.Time) *time.Time {
	return &t
}
