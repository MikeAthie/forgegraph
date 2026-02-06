// Package service contains domain services for the ForgeGraph engine.
package service

import (
	"strings"

	"github.com/forgegraph/engine/domain"
	"github.com/forgegraph/engine/domain/entity"
	"github.com/forgegraph/engine/domain/value"
)

// GraphValidator validates graph structure before execution
type GraphValidator struct{}

// NewGraphValidator creates a new graph validator
func NewGraphValidator() *GraphValidator {
	return &GraphValidator{}
}

// Validate checks the graph structure and returns any errors
func (v *GraphValidator) Validate(graph *entity.Graph) error {
	if graph == nil {
		return domain.ErrEmptyGraph
	}

	if len(graph.Nodes) == 0 {
		return domain.ErrEmptyGraph
	}

	// Check for duplicate node IDs
	if err := v.checkDuplicateNodes(graph); err != nil {
		return err
	}

	// Check for invalid node types
	if err := v.checkNodeTypes(graph); err != nil {
		return err
	}

	// Build adjacency and indegree maps
	nodeSet := make(map[string]bool)
	indegree := make(map[string]int)
	allowCycles := metadataAllowCycles(graph.Metadata)

	for _, node := range graph.Nodes {
		nodeSet[node.ID] = true
		indegree[node.ID] = 0
	}

	// Check edges reference valid nodes
	if err := v.checkEdges(graph, nodeSet); err != nil {
		return err
	}

	// Calculate indegrees
	for _, edge := range graph.Edges {
		indegree[edge.To]++
	}

	if allowCycles {
		backEdges := v.detectBackEdgeIndexes(graph)
		for i, edge := range graph.Edges {
			if !backEdges[i] {
				continue
			}
			indegree[edge.To]--
			if indegree[edge.To] < 0 {
				indegree[edge.To] = 0
			}
		}
	}

	// Check for output node
	hasOutputNode := false
	for _, node := range graph.Nodes {
		if node.Type == string(value.NodeTypeOutput) {
			hasOutputNode = true
			break
		}
	}
	if !hasOutputNode {
		return domain.ErrNoOutputNode
	}

	// Check for cycles using Kahn's algorithm
	if !allowCycles {
		if err := v.detectCycle(graph, indegree); err != nil {
			return err
		}
	}

	// Check for start nodes (indegree 0)
	// Note: For a valid edge set, "no start node" implies a cycle, so we run cycle
	// detection first to return the more specific ErrCycleDetected.
	hasStartNode := false
	for _, count := range indegree {
		if count == 0 {
			hasStartNode = true
			break
		}
	}
	if !hasStartNode {
		return domain.ErrNoStartNode
	}

	return nil
}

// checkDuplicateNodes checks for duplicate node IDs
func (v *GraphValidator) checkDuplicateNodes(graph *entity.Graph) error {
	seen := make(map[string]bool)
	for _, node := range graph.Nodes {
		if seen[node.ID] {
			return domain.ErrDuplicateNodeID
		}
		seen[node.ID] = true
	}
	return nil
}

// checkNodeTypes validates all node types
func (v *GraphValidator) checkNodeTypes(graph *entity.Graph) error {
	for _, node := range graph.Nodes {
		nodeType := value.NodeType(node.Type)
		if !nodeType.IsValid() {
			return domain.NewValidationError(
				"node.type",
				"invalid node type: "+node.Type,
			)
		}
	}
	return nil
}

// checkEdges validates all edges reference existing nodes
func (v *GraphValidator) checkEdges(graph *entity.Graph, nodeSet map[string]bool) error {
	for _, edge := range graph.Edges {
		// Check source node exists
		if !nodeSet[edge.From] {
			return domain.NewValidationError(
				"edge.from",
				"edge references non-existent source node: "+edge.From,
			)
		}
		// Check target node exists
		if !nodeSet[edge.To] {
			return domain.NewValidationError(
				"edge.to",
				"edge references non-existent target node: "+edge.To,
			)
		}
		// Check for self-loops
		if edge.From == edge.To {
			return domain.ErrSelfLoop
		}
	}
	return nil
}

// detectCycle uses Kahn's algorithm to detect cycles
func (v *GraphValidator) detectCycle(graph *entity.Graph, indegree map[string]int) error {
	// Copy indegree map
	indegreeCopy := make(map[string]int)
	for k, v := range indegree {
		indegreeCopy[k] = v
	}

	// Build adjacency list
	adj := make(map[string][]string)
	for _, edge := range graph.Edges {
		adj[edge.From] = append(adj[edge.From], edge.To)
	}

	// Kahn's algorithm: process nodes with indegree 0
	queue := []string{}
	for nodeID, count := range indegreeCopy {
		if count == 0 {
			queue = append(queue, nodeID)
		}
	}

	visited := 0
	for len(queue) > 0 {
		nodeID := queue[0]
		queue = queue[1:]
		visited++

		for _, neighbor := range adj[nodeID] {
			indegreeCopy[neighbor]--
			if indegreeCopy[neighbor] == 0 {
				queue = append(queue, neighbor)
			}
		}
	}

	// If we couldn't visit all nodes, there's a cycle
	if visited != len(graph.Nodes) {
		return domain.ErrCycleDetected
	}
	return nil
}

func metadataAllowCycles(metadata map[string]any) bool {
	if metadata == nil {
		return false
	}

	raw, exists := metadata["allow_cycles"]
	if !exists {
		return false
	}

	switch value := raw.(type) {
	case bool:
		return value
	case string:
		normalized := strings.TrimSpace(strings.ToLower(value))
		return normalized == "true" || normalized == "1"
	default:
		return false
	}
}

func (v *GraphValidator) detectBackEdgeIndexes(graph *entity.Graph) map[int]bool {
	backEdgeIndexes := make(map[int]bool)
	if graph == nil {
		return backEdgeIndexes
	}

	adjacency := make(map[string][]int)
	for i, edge := range graph.Edges {
		adjacency[edge.From] = append(adjacency[edge.From], i)
	}

	color := make(map[string]int, len(graph.Nodes))
	var dfs func(nodeID string)
	dfs = func(nodeID string) {
		color[nodeID] = 1 // gray
		for _, edgeIndex := range adjacency[nodeID] {
			edge := graph.Edges[edgeIndex]
			nextID := edge.To
			switch color[nextID] {
			case 0:
				dfs(nextID)
			case 1:
				backEdgeIndexes[edgeIndex] = true
			}
		}
		color[nodeID] = 2 // black
	}

	for _, node := range graph.Nodes {
		if color[node.ID] == 0 {
			dfs(node.ID)
		}
	}

	return backEdgeIndexes
}

// ValidateNode validates a single node's configuration
func (v *GraphValidator) ValidateNode(node *entity.Node) error {
	if node.ID == "" {
		return domain.NewValidationError("node.id", "node ID is required")
	}
	if node.Type == "" {
		return domain.NewValidationError("node.type", "node type is required")
	}

	nodeType := value.NodeType(node.Type)
	if !nodeType.IsValid() {
		return domain.NewValidationError("node.type", "invalid node type: "+node.Type)
	}

	return nil
}
