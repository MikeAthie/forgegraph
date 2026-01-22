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

// MemoryRunRepository is an in-memory implementation of RunRepository for testing.
// It is thread-safe and stores runs and node runs in memory.
type MemoryRunRepository struct {
	mu       sync.RWMutex
	runs     map[string]*entity.Run
	nodeRuns map[string]*entity.NodeRun // key: runID-nodeID
}

// NewMemoryRunRepository creates a new in-memory run repository
func NewMemoryRunRepository() *MemoryRunRepository {
	return &MemoryRunRepository{
		runs:     make(map[string]*entity.Run),
		nodeRuns: make(map[string]*entity.NodeRun),
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
}

// nodeRunKey generates a unique key for a node run
func nodeRunKey(runID, nodeID string) string {
	return fmt.Sprintf("%s-%s", runID, nodeID)
}

// timePtr returns a pointer to a time value
func timePtr(t time.Time) *time.Time {
	return &t
}
