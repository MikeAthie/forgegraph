// Package executor contains node executor implementations for the ForgeGraph engine.
package executor

import (
	"context"
	"strings"

	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/domain/entity"
	"github.com/forgegraph/engine/domain/value"
)

// OutputExecutor handles output nodes that collect final workflow results.
// Output nodes gather data from the execution state and format it as the run's final output.
type OutputExecutor struct{}

// NewOutputExecutor creates a new output executor
func NewOutputExecutor() *OutputExecutor {
	return &OutputExecutor{}
}

// NodeType returns the node type this executor handles
func (e *OutputExecutor) NodeType() string {
	return string(value.NodeTypeOutput)
}

// Execute collects the specified outputs from state and returns them as the node's output.
//
// Config options:
//   - output_mapping: map[string]string - maps output keys to state paths
//     Example: {"result": "node.transform_1.output", "summary": "vars.summary"}
//   - output_keys: []string - list of state keys to include (simpler form)
//   - include_all: bool - if true, includes all node outputs
//
// If no config is provided, defaults to including all node outputs.
func (e *OutputExecutor) Execute(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
	output := make(map[string]any)

	// Check for output_mapping (most explicit)
	if mapping, ok := node.Config["output_mapping"].(map[string]any); ok {
		for key, pathVal := range mapping {
			if path, ok := pathVal.(string); ok {
				if val, exists := resolveOutputPath(state, path); exists {
					output[key] = val
				}
			}
		}
		return port.NewSuccessResult(output), nil
	}

	// Check for output_keys (simpler list form)
	if keys, ok := node.Config["output_keys"].([]any); ok {
		for _, keyVal := range keys {
			if key, ok := keyVal.(string); ok {
				if val, exists := state.Get(key); exists {
					output[key] = val
				}
			}
		}
		return port.NewSuccessResult(output), nil
	}

	// Check for include_all flag or default behavior
	includeAll := true
	if val, ok := node.Config["include_all"].(bool); ok {
		includeAll = val
	}

	if includeAll {
		// Collect all node outputs
		snapshot := state.Snapshot()
		for key, val := range snapshot {
			// Include node outputs
			if len(key) > 5 && key[:5] == "node." {
				output[key] = val
			}
			// Include vars
			if len(key) > 5 && key[:5] == "vars." {
				output[key] = val
			}
		}
	}

	return port.NewSuccessResult(output), nil
}

func resolveOutputPath(state *entity.State, path string) (any, bool) {
	if val, exists := state.Get(path); exists {
		return val, true
	}

	current := any(state.SnapshotNested())
	for _, part := range strings.Split(path, ".") {
		if part == "" {
			continue
		}
		nextMap, ok := current.(map[string]any)
		if !ok {
			return nil, false
		}
		next, exists := nextMap[part]
		if !exists {
			return nil, false
		}
		current = next
	}

	return current, true
}
