package executor

import (
	"context"
	"fmt"

	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/domain"
	"github.com/forgegraph/engine/domain/entity"
	"github.com/forgegraph/engine/domain/service"
	"github.com/forgegraph/engine/domain/value"
)

// BranchExecutor handles branch nodes that route execution based on conditions.
// Branch nodes evaluate a boolean expression against state and route to matching edges.
type BranchExecutor struct {
	evaluator *service.ConditionEvaluator
}

// NewBranchExecutor creates a new branch executor
func NewBranchExecutor() *BranchExecutor {
	return &BranchExecutor{
		evaluator: service.NewConditionEvaluator(),
	}
}

// NodeType returns the node type this executor handles
func (e *BranchExecutor) NodeType() string {
	return string(value.NodeTypeBranch)
}

// Execute evaluates the branch condition and determines which path to take.
//
// Config options:
//   - condition: string - The condition expression to evaluate (e.g., "vars.score > 80")
//
// The scheduler injects edge information via:
//   - _edges: []map[string]any - Array of edge objects with id, from, to, label, condition
//
// Edge routing:
//   - Edges with label "true" are taken when condition evaluates to true
//   - Edges with label "false" are taken when condition evaluates to false
//   - Edges with no label act as default (taken when no labeled edge matches)
//
// Output:
//   - condition: string - The original condition expression
//   - result: any - The raw evaluation result
//   - branch_taken: bool - Whether the true or false branch was taken
//   - next_nodes: []string - Node IDs of the next nodes to execute
func (e *BranchExecutor) Execute(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
	// 1. Get condition from config (required)
	condition := node.GetConfigString("condition")
	if condition == "" {
		return port.NewErrorResult(domain.NewValidationError("condition", "branch node requires condition")), nil
	}

	// 2. Evaluate condition against state
	result, err := e.evaluator.Evaluate(condition, state)
	if err != nil {
		return port.NewErrorResult(fmt.Errorf("%w: %v", domain.ErrConditionEvalFailed, err)), nil
	}

	// 3. Determine branch taken (truthy/falsy)
	branchTaken := e.evaluator.IsTruthy(result)
	branchLabel := "false"
	if branchTaken {
		branchLabel = "true"
	}

	// 4. Get edges from config (injected by scheduler)
	edges, ok := node.Config["_edges"].([]map[string]any)
	if !ok {
		// If no edges injected, return the result without routing
		// The scheduler will handle this case
		output := map[string]any{
			"condition":    condition,
			"result":       result,
			"branch_taken": branchTaken,
		}
		return port.NewSuccessResult(output), nil
	}

	// 5. Find matching edge(s) based on label
	var nextNodes []string
	var defaultEdges []string

	for _, edge := range edges {
		edgeLabel, _ := edge["label"].(string)
		edgeTo, _ := edge["to"].(string)

		if edgeTo == "" {
			continue
		}

		if edgeLabel == branchLabel {
			nextNodes = append(nextNodes, edgeTo)
		} else if edgeLabel == "" {
			// Remember default edges (no label) for fallback
			defaultEdges = append(defaultEdges, edgeTo)
		}
	}

	// 6. Fallback to default edge(s) if no label match
	if len(nextNodes) == 0 && len(defaultEdges) > 0 {
		nextNodes = defaultEdges
	}

	// 7. Build output
	output := map[string]any{
		"condition":    condition,
		"result":       result,
		"branch_taken": branchTaken,
		"next_nodes":   nextNodes,
	}

	return port.NewBranchResult(output, nextNodes), nil
}
