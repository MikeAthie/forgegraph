package usecase

import (
	"context"
	"encoding/json"
	"errors"
	"sort"

	"github.com/forgegraph/engine/domain"
)

// RunSnapshot provides a deterministic inspection view of scheduler state for tests.
type RunSnapshot struct {
	RunID         string         `json:"run_id"`
	Status        string         `json:"status"`
	CurrentNodeID string         `json:"current_node_id,omitempty"`
	PausedNodeID  string         `json:"paused_node_id,omitempty"`
	State         map[string]any `json:"state,omitempty"`
	Pending       map[string]int `json:"pending,omitempty"`
	Completed     []string       `json:"completed,omitempty"`
	Skipped       []string       `json:"skipped,omitempty"`
	Running       []string       `json:"running,omitempty"`
	VisitCounts   map[string]int `json:"visit_counts,omitempty"`
	InitialNodes  []string       `json:"initial_nodes,omitempty"`
	Output        map[string]any `json:"output,omitempty"`
	Error         string         `json:"error,omitempty"`
}

// SnapshotRun returns the best available run view. Active runs include scheduler state;
// paused runs include the persisted pause snapshot; terminal runs include final status/output.
func (s *Scheduler) SnapshotRun(ctx context.Context, runID string) (*RunSnapshot, error) {
	if ctx == nil {
		ctx = context.Background()
	}

	run, err := s.repository.GetRun(ctx, runID)
	if err != nil {
		return nil, err
	}

	if value, ok := s.activeRuns.Load(runID); ok && run.Status == "running" {
		return snapshotActiveRun(value.(*runContext)), nil
	}

	snapshot := &RunSnapshot{
		RunID:  runID,
		Status: run.Status,
		Output: cloneMapAny(run.OutputJSON),
		Error:  run.ErrorMessage,
	}

	pausedNodeID, stateSnapshot, completedNodes, skippedNodes, _, _, pauseErr := s.repository.LoadPauseState(ctx, runID)
	if pauseErr == nil {
		snapshot.PausedNodeID = pausedNodeID
		snapshot.State = cloneMapAny(stateSnapshot)
		snapshot.Completed = cloneStringSlice(completedNodes)
		snapshot.Skipped = cloneStringSlice(skippedNodes)
		sort.Strings(snapshot.Completed)
		sort.Strings(snapshot.Skipped)
		return snapshot, nil
	}
	if !errors.Is(pauseErr, domain.ErrRunNotFound) {
		var validationErr *domain.ValidationError
		if !errors.As(pauseErr, &validationErr) {
			// Repository pause-state absence is non-fatal here.
		}
	}

	return snapshot, nil
}

func snapshotActiveRun(rc *runContext) *RunSnapshot {
	rc.pendingMu.Lock()
	completed := make([]string, 0, len(rc.completed))
	for nodeID := range rc.completed {
		completed = append(completed, nodeID)
	}
	skipped := make([]string, 0, len(rc.skipped))
	for nodeID := range rc.skipped {
		skipped = append(skipped, nodeID)
	}
	running := make([]string, 0, len(rc.running))
	for nodeID := range rc.running {
		running = append(running, nodeID)
	}
	pending := make(map[string]int, len(rc.pending))
	for nodeID, count := range rc.pending {
		pending[nodeID] = count
	}
	visitCounts := make(map[string]int, len(rc.visitCounts))
	for nodeID, count := range rc.visitCounts {
		visitCounts[nodeID] = count
	}
	initialNodes := append([]string(nil), rc.initialNodes...)
	rc.pendingMu.Unlock()

	sort.Strings(completed)
	sort.Strings(skipped)
	sort.Strings(running)
	sort.Strings(initialNodes)

	rc.currentNodeMu.RLock()
	currentNodeID := rc.currentNodeID
	rc.currentNodeMu.RUnlock()

	return &RunSnapshot{
		RunID:         rc.runID,
		Status:        "running",
		CurrentNodeID: currentNodeID,
		State:         cloneMapAny(rc.state.Snapshot()),
		Pending:       pending,
		Completed:     completed,
		Skipped:       skipped,
		Running:       running,
		VisitCounts:   visitCounts,
		InitialNodes:  initialNodes,
	}
}

func cloneMapAny(input map[string]any) map[string]any {
	if input == nil {
		return nil
	}
	clone := make(map[string]any, len(input))
	for key, value := range input {
		clone[key] = cloneValue(value)
	}
	return clone
}

func cloneStringSlice(values []string) []string {
	if values == nil {
		return nil
	}
	return append([]string(nil), values...)
}

func cloneValue(value any) any {
	switch typed := value.(type) {
	case map[string]any:
		return cloneMapAny(typed)
	case []any:
		cloned := make([]any, len(typed))
		for index, item := range typed {
			cloned[index] = cloneValue(item)
		}
		return cloned
	case []string:
		return append([]string(nil), typed...)
	default:
		payload, err := json.Marshal(typed)
		if err != nil {
			return typed
		}
		var decoded any
		if err := json.Unmarshal(payload, &decoded); err != nil {
			return typed
		}
		return decoded
	}
}
