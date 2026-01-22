package executor

import (
	"context"

	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/domain/entity"
	"github.com/forgegraph/engine/domain/value"
)

// MergeExecutor handles merge nodes that join parallel branches.
// Merge nodes wait for all predecessors to complete before executing,
// then combine their outputs according to the configured strategy.
type MergeExecutor struct{}

// NewMergeExecutor creates a new merge executor
func NewMergeExecutor() *MergeExecutor {
	return &MergeExecutor{}
}

// NodeType returns the node type this executor handles
func (e *MergeExecutor) NodeType() string {
	return string(value.NodeTypeMerge)
}

// Execute combines outputs from predecessor nodes.
//
// Config options:
//   - merge_strategy: string - "namespaced" (default) or "last_write_wins"
//
// The scheduler injects predecessor information via:
//   - _input_nodes: []string - Array of predecessor node IDs
//
// Merge strategies:
//   - "namespaced": Each predecessor's output is preserved under merged[nodeID]
//   - "last_write_wins": Map values from predecessors are merged, later overwrites earlier
//
// Output:
//   - merged: map[string]any - Combined outputs from predecessors
//   - strategy: string - The merge strategy used
//   - sources: []string - List of predecessor node IDs that contributed
func (e *MergeExecutor) Execute(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
	// 1. Get merge strategy (default: namespaced)
	strategy := node.GetConfigString("merge_strategy")
	if strategy == "" {
		strategy = "namespaced"
	}

	// 2. Get input nodes from config (injected by scheduler)
	inputNodes := e.getInputNodes(node)

	// 3. Collect outputs from input nodes
	merged := make(map[string]any)
	sources := make([]string, 0)

	for _, nodeID := range inputNodes {
		output, exists := state.GetNodeOutput(nodeID)
		if !exists {
			// Skip nodes without output (may have been skipped in a branch)
			continue
		}

		sources = append(sources, nodeID)

		switch strategy {
		case "namespaced":
			// Each input goes under its node ID
			merged[nodeID] = output

		case "last_write_wins":
			// Merge map values, later nodes overwrite earlier
			if m, ok := output.(map[string]any); ok {
				for k, v := range m {
					merged[k] = v
				}
			} else {
				// Non-map outputs go under node ID
				merged[nodeID] = output
			}

		default:
			// Unknown strategy, default to namespaced
			merged[nodeID] = output
		}
	}

	// 4. Build output
	output := map[string]any{
		"merged":   merged,
		"strategy": strategy,
		"sources":  sources,
	}

	return port.NewSuccessResult(output), nil
}

// getInputNodes extracts the input node IDs from config
func (e *MergeExecutor) getInputNodes(node *entity.Node) []string {
	// Try to get from _input_nodes (injected by scheduler)
	if inputNodes, ok := node.Config["_input_nodes"].([]string); ok {
		return inputNodes
	}

	// Try to parse from []any (JSON unmarshaling may produce this)
	if inputNodesAny, ok := node.Config["_input_nodes"].([]any); ok {
		result := make([]string, 0, len(inputNodesAny))
		for _, item := range inputNodesAny {
			if s, ok := item.(string); ok {
				result = append(result, s)
			}
		}
		return result
	}

	// No input nodes specified
	return nil
}
