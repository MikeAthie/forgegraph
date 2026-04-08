// Package port defines interfaces (ports) for the application layer.
// These are implemented by adapters in the infrastructure layer.
package port

import (
	"context"

	"github.com/forgegraph/engine/domain/entity"
)

// RunRepository persists engine runtime state through the backend-owned contract.
// Implementations should target the control-plane API in production and may use
// in-memory storage for tests or explicit local fallback only.
type RunRepository interface {
	// Run operations

	// GetRun retrieves a run by ID
	GetRun(ctx context.Context, runID string) (*entity.Run, error)

	// UpdateRunStatus updates the status of a run
	UpdateRunStatus(ctx context.Context, runID string, status string) error

	// UpdateRunOutput sets the final output JSON for a completed run
	UpdateRunOutput(ctx context.Context, runID string, output map[string]any) error

	// UpdateRunError sets the error message for a failed run
	UpdateRunError(ctx context.Context, runID string, errorMsg string) error

	// SetRunEnded marks a run as ended with the given status and optional output/error
	SetRunEnded(ctx context.Context, runID string, status string, output map[string]any, errorMsg string) error

	// Pause/Resume operations (for Human Gate)

	// SavePauseState saves the execution state when a run is paused at a human gate
	SavePauseState(
		ctx context.Context,
		runID,
		pausedNodeID string,
		stateSnapshot map[string]any,
		completedNodes []string,
		skippedNodes []string,
		graphJSON string,
		tenantID string,
	) error

	// LoadPauseState retrieves the saved pause state for resuming a run
	LoadPauseState(
		ctx context.Context,
		runID string,
	) (
		pausedNodeID string,
		stateSnapshot map[string]any,
		completedNodes []string,
		skippedNodes []string,
		graphJSON string,
		tenantID string,
		err error,
	)

	// ClearPauseState removes the pause state after a run is resumed
	ClearPauseState(ctx context.Context, runID string) error

	// Checkpoint operations (durable execution)

	// SaveCheckpoint persists the latest execution state for durable resume
	SaveCheckpoint(ctx context.Context, runID, nodeID string, stepIndex int, stateSnapshot map[string]any, completedNodes []string, skippedNodes []string, graphJSON string) error

	// LoadLatestCheckpoint retrieves the most recent checkpoint for a run
	LoadLatestCheckpoint(ctx context.Context, runID string) (nodeID string, stepIndex int, stateSnapshot map[string]any, completedNodes []string, skippedNodes []string, graphJSON string, err error)

	// ClearCheckpoints removes all checkpoints for a run
	ClearCheckpoints(ctx context.Context, runID string) error

	// Node cache operations

	// GetCachedNodeResult retrieves a cached node output by key if not expired
	GetCachedNodeResult(ctx context.Context, cacheKey string) (output any, found bool, err error)

	// SaveCachedNodeResult stores a cached node output with TTL seconds
	SaveCachedNodeResult(ctx context.Context, cacheKey string, output any, ttlSeconds int) error

	// NodeRun operations

	// CreateNodeRun creates a new node run record
	CreateNodeRun(ctx context.Context, nodeRun *entity.NodeRun) error

	// UpdateNodeRun updates an existing node run record
	UpdateNodeRun(ctx context.Context, nodeRun *entity.NodeRun) error

	// GetNodeRun retrieves a node run by run ID and node ID
	GetNodeRun(ctx context.Context, runID, nodeID string) (*entity.NodeRun, error)

	// GetNodeRunsByRunID retrieves all node runs for a given run
	GetNodeRunsByRunID(ctx context.Context, runID string) ([]*entity.NodeRun, error)
}

// GraphRepository loads graph definitions.
// Note: In the current architecture, graphs are passed via gRPC request,
// but this interface supports future scenarios where the engine loads graphs directly.
type GraphRepository interface {
	// GetGraph retrieves a graph by version ID
	GetGraph(ctx context.Context, versionID string) (*entity.Graph, error)
}
