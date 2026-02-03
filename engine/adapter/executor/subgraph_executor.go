package executor

import (
	"context"
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
	"time"

	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/domain"
	"github.com/forgegraph/engine/domain/entity"
	"github.com/forgegraph/engine/domain/service"
	"github.com/forgegraph/engine/domain/value"
)

// SubgraphExecutor runs a nested graph inline and returns its output.
type SubgraphExecutor struct {
	registry         port.ExecutorRegistry
	defaultTimeoutMs int
	conditions       *service.ConditionEvaluator
}

// NewSubgraphExecutor creates a subgraph executor.
func NewSubgraphExecutor(registry port.ExecutorRegistry) *SubgraphExecutor {
	return &SubgraphExecutor{
		registry:         registry,
		defaultTimeoutMs: 30000,
		conditions:       service.NewConditionEvaluator(),
	}
}

// NodeType returns the node type this executor handles.
func (e *SubgraphExecutor) NodeType() string {
	return string(value.NodeTypeSubgraph)
}

// Execute runs the referenced subgraph.
//
// Config options:
//   - graph_json: object or string (required)
//   - input_mapping: object (optional) map subgraph input keys -> state paths
//   - input_path: string (optional) state path to an object used as input
//   - input: object (optional) static input object
//   - output_mapping: object (optional) map parent state paths -> subgraph output paths
//   - output_key: string (optional) write entire subgraph output into parent state at this key
func (e *SubgraphExecutor) Execute(ctx context.Context, node *entity.Node, state *entity.State) (*port.NodeExecutionResult, error) {
	graph, err := parseSubgraphConfig(node.Config)
	if err != nil {
		return port.NewErrorResult(err), nil
	}

	inputs := buildSubgraphInputs(node.Config, state)

	output, err := e.runSubgraph(ctx, graph, inputs)
	if err != nil {
		return port.NewErrorResult(err), nil
	}

	if outputKey := strings.TrimSpace(getStringConfig(node.Config, "output_key")); outputKey != "" {
		state.Set(outputKey, output)
	}

	if mappings, ok := node.Config["output_mapping"].(map[string]any); ok {
		for dest, srcRaw := range mappings {
			src, _ := srcRaw.(string)
			if src == "" {
				continue
			}
			if value := resolveSubgraphValue(output, src); value != nil {
				state.Set(dest, value)
			}
		}
	}

	return port.NewSuccessResult(map[string]any{
		"output": output,
	}), nil
}

func (e *SubgraphExecutor) runSubgraph(ctx context.Context, graph *entity.Graph, inputs map[string]any) (map[string]any, error) {
	validator := service.NewGraphValidator()
	if err := validator.Validate(graph); err != nil {
		return nil, fmt.Errorf("subgraph validation failed: %w", err)
	}

	planner := service.NewExecutionPlanner()
	plan := planner.Plan(graph)

	subState := entity.NewStateWithInput(inputs)
	pending := plan.CloneIndegree()
	completed := make(map[string]bool)
	skipped := make(map[string]bool)

	queue := append([]string{}, plan.StartNodes...)

	for len(queue) > 0 {
		nodeID := queue[0]
		queue = queue[1:]

		if completed[nodeID] || skipped[nodeID] {
			continue
		}
		if pending[nodeID] > 0 {
			continue
		}

		node := plan.GetNode(nodeID)
		if node == nil {
			return nil, fmt.Errorf("subgraph node %s not found", nodeID)
		}

		executor, ok := e.registry.Get(node.Type)
		if !ok {
			return nil, fmt.Errorf("subgraph executor not found for node type %s", node.Type)
		}

		e.injectNodeMetadata(plan, node)

		result, err := e.executeWithRetries(ctx, node, executor, subState)
		if err != nil {
			return nil, err
		}
		if result == nil {
			continue
		}
		if result.Error != nil {
			return nil, result.Error
		}
		if result.Pause {
			return nil, fmt.Errorf("subgraph nodes cannot pause execution")
		}

		if !result.HasNextNodes() {
			nextNodes, hasDirective, directiveErr := extractNextNodesFromOutput(result.Output)
			if directiveErr != nil {
				return nil, directiveErr
			}
			if hasDirective && len(nextNodes) > 0 {
				result.NextNodes = nextNodes
			}
		}

		if result.Output != nil {
			subState.SetNodeOutput(nodeID, result.Output)
		}

		completed[nodeID] = true

		edges := plan.GetOutgoingEdges(nodeID)
		nextIDs, skippedIDs, usedConditions, err := e.evaluateEdgeConditions(edges, subState)
		if err != nil {
			return nil, err
		}

		if result.HasNextNodes() {
			nextIDs = result.NextNodes
			skippedIDs = nil
			outgoingSet := make(map[string]bool)
			for _, edge := range edges {
				outgoingSet[edge.To] = true
			}
			for _, nextID := range nextIDs {
				if !outgoingSet[nextID] {
					return nil, domain.NewValidationError("next_nodes", fmt.Sprintf("invalid next_nodes: %s", nextID))
				}
			}
			for _, edge := range edges {
				found := false
				for _, next := range nextIDs {
					if next == edge.To {
						found = true
						break
					}
				}
				if !found {
					skippedIDs = append(skippedIDs, edge.To)
				}
			}
		} else if !usedConditions {
			for _, edge := range edges {
				nextIDs = append(nextIDs, edge.To)
			}
		}

		for _, skippedID := range skippedIDs {
			if !skipped[skippedID] {
				skipped[skippedID] = true
				for _, edge := range plan.GetOutgoingEdges(skippedID) {
					pending[edge.To]--
				}
			}
		}

		for _, nextID := range nextIDs {
			pending[nextID]--
			if pending[nextID] <= 0 && !completed[nextID] && !skipped[nextID] {
				queue = append(queue, nextID)
			}
		}
	}

	return extractFinalOutput(plan, subState), nil
}

func (e *SubgraphExecutor) executeWithRetries(ctx context.Context, node *entity.Node, executor port.NodeExecutor, state *entity.State) (*port.NodeExecutionResult, error) {
	policy := node.RetryPolicy
	if policy == nil {
		policy = entity.DefaultRetryPolicy()
	}

	timeout := node.TimeoutMs
	if timeout == 0 {
		timeout = e.defaultTimeoutMs
	}

	var lastErr error
	for attempt := 1; attempt <= policy.MaxAttempts; attempt++ {
		execCtx, cancel := context.WithTimeout(ctx, time.Duration(timeout)*time.Millisecond)
		result, err := executor.Execute(execCtx, node, state)
		cancel()

		if err == nil && result.Error == nil {
			return result, nil
		}
		if err == nil && result.Error != nil {
			err = result.Error
		}
		lastErr = err
		if !domain.IsRetryable(err) {
			return nil, err
		}
	}
	return nil, fmt.Errorf("max retries exceeded: %w", lastErr)
}

func (e *SubgraphExecutor) evaluateEdgeConditions(edges []*entity.Edge, state *entity.State) ([]string, []string, bool, error) {
	hasCondition := false
	for _, edge := range edges {
		if strings.TrimSpace(edge.Condition) != "" {
			hasCondition = true
			break
		}
	}
	if !hasCondition {
		return nil, nil, false, nil
	}

	var next []string
	var skipped []string
	var defaultEdges []string
	for _, edge := range edges {
		condition := strings.TrimSpace(edge.Condition)
		if condition == "" {
			defaultEdges = append(defaultEdges, edge.To)
			continue
		}
		ok, err := e.conditions.EvaluateBool(condition, state)
		if err != nil {
			return nil, nil, true, err
		}
		if ok {
			next = append(next, edge.To)
		} else {
			skipped = append(skipped, edge.To)
		}
	}

	if len(next) == 0 {
		next = defaultEdges
	} else if len(defaultEdges) > 0 {
		skipped = append(skipped, defaultEdges...)
	}

	return next, skipped, true, nil
}

func (e *SubgraphExecutor) injectNodeMetadata(plan *service.ExecutionPlan, node *entity.Node) {
	if node.Config == nil {
		node.Config = make(map[string]any)
	}
	switch node.Type {
	case string(value.NodeTypeBranch):
		node.Config["_edges"] = plan.SerializeEdgesForConfig(node.ID)
	case string(value.NodeTypeMerge):
		node.Config["_input_nodes"] = plan.GetPredecessors(node.ID)
	}
}

func parseSubgraphConfig(config map[string]any) (*entity.Graph, error) {
	raw, ok := config["graph_json"]
	if !ok {
		return nil, domain.NewValidationError("graph_json", "subgraph node requires graph_json")
	}

	var bytes []byte
	switch typed := raw.(type) {
	case string:
		bytes = []byte(typed)
	default:
		encoded, err := json.Marshal(typed)
		if err != nil {
			return nil, err
		}
		bytes = encoded
	}

	var graph entity.Graph
	if err := json.Unmarshal(bytes, &graph); err != nil {
		return nil, fmt.Errorf("invalid subgraph json: %w", err)
	}
	return &graph, nil
}

func buildSubgraphInputs(config map[string]any, state *entity.State) map[string]any {
	inputs := map[string]any{}

	if rawInput, ok := config["input"].(map[string]any); ok {
		for k, v := range rawInput {
			inputs[k] = v
		}
	}

	if inputPath, ok := config["input_path"].(string); ok && strings.TrimSpace(inputPath) != "" {
		if val, ok := state.Get(inputPath); ok {
			if mapped, ok := val.(map[string]any); ok {
				for k, v := range mapped {
					inputs[k] = v
				}
			} else {
				inputs["payload"] = val
			}
		}
	}

	if mapping, ok := config["input_mapping"].(map[string]any); ok {
		for dest, srcRaw := range mapping {
			src, _ := srcRaw.(string)
			if src == "" {
				continue
			}
			if value := resolveSubgraphValue(state.SnapshotNested(), src); value != nil {
				inputs[dest] = value
			}
		}
	}

	return inputs
}

func resolveSubgraphValue(root any, path string) any {
	parts := strings.Split(path, ".")
	current := root
	for _, part := range parts {
		if part == "" {
			continue
		}
		switch typed := current.(type) {
		case map[string]any:
			current = typed[part]
		case []any:
			idx, err := strconv.Atoi(part)
			if err != nil || idx < 0 || idx >= len(typed) {
				return nil
			}
			current = typed[idx]
		default:
			return nil
		}
	}
	return current
}

func extractFinalOutput(plan *service.ExecutionPlan, state *entity.State) map[string]any {
	output := make(map[string]any)
	for _, node := range plan.Graph.Nodes {
		if node.Type == string(value.NodeTypeOutput) {
			if nodeOutput, ok := state.GetNodeOutput(node.ID); ok {
				output[node.ID] = nodeOutput
			}
		}
	}
	if len(output) == 1 {
		for _, v := range output {
			if m, ok := v.(map[string]any); ok {
				return m
			}
		}
	}
	return output
}

func getStringConfig(config map[string]any, key string) string {
	if config == nil {
		return ""
	}
	if val, ok := config[key]; ok {
		if str, ok := val.(string); ok {
			return str
		}
	}
	return ""
}

func extractNextNodesFromOutput(output any) ([]string, bool, error) {
	outputMap, ok := output.(map[string]any)
	if !ok {
		return nil, false, nil
	}

	var raw any
	if value, ok := outputMap["next_nodes"]; ok {
		raw = value
	} else if value, ok := outputMap["next_node"]; ok {
		raw = value
	} else {
		return nil, false, nil
	}

	switch typed := raw.(type) {
	case string:
		if typed == "" {
			return nil, true, domain.NewValidationError("next_nodes", "next_node cannot be empty")
		}
		return []string{typed}, true, nil
	case []string:
		return typed, true, nil
	case []any:
		parsed := make([]string, 0, len(typed))
		for _, item := range typed {
			value, ok := item.(string)
			if !ok || value == "" {
				return nil, true, domain.NewValidationError("next_nodes", "next_nodes must contain non-empty strings")
			}
			parsed = append(parsed, value)
		}
		return parsed, true, nil
	default:
		return nil, true, domain.NewValidationError("next_nodes", "next_nodes must be a string or list of strings")
	}
}
