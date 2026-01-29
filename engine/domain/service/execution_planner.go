package service

import (
	"github.com/forgegraph/engine/domain/entity"
)

// ExecutionPlan holds pre-computed graph metadata for execution
type ExecutionPlan struct {
	Graph      *entity.Graph
	NodeMap    map[string]*entity.Node   // Quick lookup by ID
	Adjacency  map[string][]string       // node -> outgoing node IDs
	Indegree   map[string]int            // node -> incoming edge count
	StartNodes []string                  // Nodes with indegree 0
	EdgeMap    map[string][]*entity.Edge // from_node_id -> edges
}

// ExecutionPlanner builds an execution plan from a graph
type ExecutionPlanner struct{}

// NewExecutionPlanner creates a new execution planner
func NewExecutionPlanner() *ExecutionPlanner {
	return &ExecutionPlanner{}
}

// Plan creates an ExecutionPlan from a Graph
func (p *ExecutionPlanner) Plan(graph *entity.Graph) *ExecutionPlan {
	plan := &ExecutionPlan{
		Graph:      graph,
		NodeMap:    make(map[string]*entity.Node),
		Adjacency:  make(map[string][]string),
		Indegree:   make(map[string]int),
		StartNodes: []string{},
		EdgeMap:    make(map[string][]*entity.Edge),
	}

	// Build node map and initialize indegree
	for i := range graph.Nodes {
		node := &graph.Nodes[i]
		plan.NodeMap[node.ID] = node
		plan.Indegree[node.ID] = 0
		plan.Adjacency[node.ID] = []string{}
	}

	// Build adjacency list and edge map, calculate indegrees
	for i := range graph.Edges {
		edge := &graph.Edges[i]
		plan.Adjacency[edge.From] = append(plan.Adjacency[edge.From], edge.To)
		plan.EdgeMap[edge.From] = append(plan.EdgeMap[edge.From], edge)
		plan.Indegree[edge.To]++
	}

	// Find start nodes (indegree == 0)
	for nodeID, count := range plan.Indegree {
		if count == 0 {
			plan.StartNodes = append(plan.StartNodes, nodeID)
		}
	}

	return plan
}

// GetNode returns a node by ID
func (p *ExecutionPlan) GetNode(nodeID string) *entity.Node {
	return p.NodeMap[nodeID]
}

// GetOutgoingEdges returns all edges from a given node
func (p *ExecutionPlan) GetOutgoingEdges(nodeID string) []*entity.Edge {
	return p.EdgeMap[nodeID]
}

// GetChildren returns all nodes that this node connects to
func (p *ExecutionPlan) GetChildren(nodeID string) []string {
	return p.Adjacency[nodeID]
}

// GetIndegree returns the number of incoming edges for a node
func (p *ExecutionPlan) GetIndegree(nodeID string) int {
	return p.Indegree[nodeID]
}

// IsStartNode returns true if the node has no incoming edges
func (p *ExecutionPlan) IsStartNode(nodeID string) bool {
	return p.Indegree[nodeID] == 0
}

// IsEndNode returns true if the node has no outgoing edges
func (p *ExecutionPlan) IsEndNode(nodeID string) bool {
	return len(p.Adjacency[nodeID]) == 0
}

// GetNodeCount returns the total number of nodes
func (p *ExecutionPlan) GetNodeCount() int {
	return len(p.NodeMap)
}

// GetEdgeCount returns the total number of edges
func (p *ExecutionPlan) GetEdgeCount() int {
	count := 0
	for _, edges := range p.EdgeMap {
		count += len(edges)
	}
	return count
}

// FindEdge finds a specific edge between two nodes
func (p *ExecutionPlan) FindEdge(from, to string) *entity.Edge {
	for _, edge := range p.EdgeMap[from] {
		if edge.To == to {
			return edge
		}
	}
	return nil
}

// GetEdgesWithCondition returns edges from a node that have a condition
func (p *ExecutionPlan) GetEdgesWithCondition(nodeID string) []*entity.Edge {
	var result []*entity.Edge
	for _, edge := range p.EdgeMap[nodeID] {
		if edge.Condition != "" {
			result = append(result, edge)
		}
	}
	return result
}

// GetDefaultEdge returns the edge without a condition (default path)
func (p *ExecutionPlan) GetDefaultEdge(nodeID string) *entity.Edge {
	for _, edge := range p.EdgeMap[nodeID] {
		if edge.Condition == "" {
			return edge
		}
	}
	return nil
}

// GetTopologicalOrder returns nodes in topological order (for debugging)
func (p *ExecutionPlan) GetTopologicalOrder() []string {
	// Copy indegree map
	indegree := make(map[string]int)
	for k, v := range p.Indegree {
		indegree[k] = v
	}

	var order []string
	queue := make([]string, len(p.StartNodes))
	copy(queue, p.StartNodes)

	for len(queue) > 0 {
		nodeID := queue[0]
		queue = queue[1:]
		order = append(order, nodeID)

		for _, child := range p.Adjacency[nodeID] {
			indegree[child]--
			if indegree[child] == 0 {
				queue = append(queue, child)
			}
		}
	}

	return order
}

// Clone creates a copy of the indegree map for use during execution
func (p *ExecutionPlan) CloneIndegree() map[string]int {
	clone := make(map[string]int, len(p.Indegree))
	for k, v := range p.Indegree {
		clone[k] = v
	}
	return clone
}

// GetPredecessors returns all node IDs that have edges leading to the target node.
// Used by merge nodes to identify which predecessor outputs to collect.
func (p *ExecutionPlan) GetPredecessors(nodeID string) []string {
	var predecessors []string
	for _, edge := range p.Graph.Edges {
		if edge.To == nodeID {
			predecessors = append(predecessors, edge.From)
		}
	}
	return predecessors
}

// GetEdgesByLabel returns edges from a node filtered by label.
// Used by branch nodes to identify true/false paths.
func (p *ExecutionPlan) GetEdgesByLabel(nodeID string, label string) []*entity.Edge {
	var result []*entity.Edge
	for _, edge := range p.EdgeMap[nodeID] {
		if edge.Label == label {
			result = append(result, edge)
		}
	}
	return result
}

// SerializeEdgesForConfig converts edges to a format suitable for node config injection.
// Returns a slice of maps with edge properties.
func (p *ExecutionPlan) SerializeEdgesForConfig(nodeID string) []map[string]any {
	edges := p.EdgeMap[nodeID]
	result := make([]map[string]any, len(edges))
	for i, edge := range edges {
		result[i] = map[string]any{
			"id":        edge.ID,
			"from":      edge.From,
			"to":        edge.To,
			"label":     edge.Label,
			"condition": edge.Condition,
			"data_type": edge.DataType,
		}
	}
	return result
}

// GetIncomingEdges returns all edges that lead to this node.
// Used for debugging and data type tracking.
func (p *ExecutionPlan) GetIncomingEdges(nodeID string) []*entity.Edge {
	var result []*entity.Edge
	for _, edge := range p.Graph.Edges {
		if edge.To == nodeID {
			result = append(result, &edge)
		}
	}
	return result
}

// GetIncomingDataTypes returns a map of source node ID to data type
// for all edges leading to this node.
func (p *ExecutionPlan) GetIncomingDataTypes(nodeID string) map[string]string {
	result := make(map[string]string)
	for _, edge := range p.Graph.Edges {
		if edge.To == nodeID && edge.DataType != "" {
			result[edge.From] = edge.DataType
		}
	}
	return result
}
