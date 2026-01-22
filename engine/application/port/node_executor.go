package port

import (
	"context"

	"github.com/forgegraph/engine/domain/entity"
)

// NodeExecutionResult holds the result of executing a node
type NodeExecutionResult struct {
	// Output is the data produced by the node (stored in state)
	Output any

	// Error is set if the node execution failed
	Error error

	// NextNodes specifies which nodes to execute next (for branch nodes)
	// If empty, all connected nodes are executed (normal flow)
	NextNodes []string

	// Pause signals the scheduler to pause execution (for human gate nodes)
	Pause bool

	// Skip signals that this node should be considered skipped
	Skip bool
}

// NewSuccessResult creates a successful execution result
func NewSuccessResult(output any) *NodeExecutionResult {
	return &NodeExecutionResult{
		Output: output,
	}
}

// NewErrorResult creates a failed execution result
func NewErrorResult(err error) *NodeExecutionResult {
	return &NodeExecutionResult{
		Error: err,
	}
}

// NewBranchResult creates a result that routes to specific next nodes
func NewBranchResult(output any, nextNodes []string) *NodeExecutionResult {
	return &NodeExecutionResult{
		Output:    output,
		NextNodes: nextNodes,
	}
}

// NewPauseResult creates a result that pauses execution (human gate)
func NewPauseResult(output any) *NodeExecutionResult {
	return &NodeExecutionResult{
		Output: output,
		Pause:  true,
	}
}

// IsSuccess returns true if the execution succeeded
func (r *NodeExecutionResult) IsSuccess() bool {
	return r.Error == nil && !r.Skip
}

// HasNextNodes returns true if specific next nodes are specified
func (r *NodeExecutionResult) HasNextNodes() bool {
	return len(r.NextNodes) > 0
}

// NodeExecutor executes a specific node type.
// Each node type (prompt, http, transform, etc.) has its own executor implementation.
type NodeExecutor interface {
	// Execute runs the node logic and returns the result.
	// The executor receives:
	// - ctx: context for cancellation and timeouts
	// - node: the node definition with its configuration
	// - state: the current execution state (read/write)
	Execute(ctx context.Context, node *entity.Node, state *entity.State) (*NodeExecutionResult, error)

	// NodeType returns which node type this executor handles.
	// This is used by the scheduler to route nodes to the correct executor.
	NodeType() string
}

// ExecutorRegistry manages registered node executors
type ExecutorRegistry interface {
	// Register adds an executor for a node type
	Register(executor NodeExecutor)

	// Get retrieves the executor for a node type
	Get(nodeType string) (NodeExecutor, bool)

	// Has checks if an executor is registered for a node type
	Has(nodeType string) bool
}

// DefaultExecutorRegistry is a simple map-based registry
type DefaultExecutorRegistry struct {
	executors map[string]NodeExecutor
}

// NewExecutorRegistry creates a new executor registry
func NewExecutorRegistry() *DefaultExecutorRegistry {
	return &DefaultExecutorRegistry{
		executors: make(map[string]NodeExecutor),
	}
}

// Register adds an executor to the registry
func (r *DefaultExecutorRegistry) Register(executor NodeExecutor) {
	r.executors[executor.NodeType()] = executor
}

// Get retrieves an executor by node type
func (r *DefaultExecutorRegistry) Get(nodeType string) (NodeExecutor, bool) {
	executor, ok := r.executors[nodeType]
	return executor, ok
}

// Has checks if an executor exists for a node type
func (r *DefaultExecutorRegistry) Has(nodeType string) bool {
	_, ok := r.executors[nodeType]
	return ok
}

// RegisterAll registers multiple executors at once
func (r *DefaultExecutorRegistry) RegisterAll(executors ...NodeExecutor) {
	for _, executor := range executors {
		r.Register(executor)
	}
}
