package service

import (
	"testing"

	"github.com/forgegraph/engine/domain/entity"
)

func TestExecutionPlanner_SimpleGraph(t *testing.T) {
	graph := &entity.Graph{
		Nodes: []entity.Node{
			{ID: "a", Type: "transform", Name: "A"},
			{ID: "b", Type: "output", Name: "B"},
		},
		Edges: []entity.Edge{
			{ID: "e1", From: "a", To: "b"},
		},
	}

	planner := NewExecutionPlanner()
	plan := planner.Plan(graph)

	// Check node map
	if plan.GetNode("a") == nil {
		t.Error("Expected node 'a' in NodeMap")
	}
	if plan.GetNode("b") == nil {
		t.Error("Expected node 'b' in NodeMap")
	}
	if plan.GetNode("nonexistent") != nil {
		t.Error("Expected nil for nonexistent node")
	}

	// Check indegree
	if plan.GetIndegree("a") != 0 {
		t.Errorf("Expected indegree 0 for 'a', got %d", plan.GetIndegree("a"))
	}
	if plan.GetIndegree("b") != 1 {
		t.Errorf("Expected indegree 1 for 'b', got %d", plan.GetIndegree("b"))
	}

	// Check start nodes
	if len(plan.StartNodes) != 1 || plan.StartNodes[0] != "a" {
		t.Errorf("Expected ['a'] as start nodes, got %v", plan.StartNodes)
	}

	// Check adjacency
	children := plan.GetChildren("a")
	if len(children) != 1 || children[0] != "b" {
		t.Errorf("Expected 'a' to have child 'b', got %v", children)
	}
}

func TestExecutionPlanner_MultipleStartNodes(t *testing.T) {
	graph := &entity.Graph{
		Nodes: []entity.Node{
			{ID: "start1", Type: "transform", Name: "Start 1"},
			{ID: "start2", Type: "transform", Name: "Start 2"},
			{ID: "merge", Type: "merge", Name: "Merge"},
			{ID: "output", Type: "output", Name: "Output"},
		},
		Edges: []entity.Edge{
			{ID: "e1", From: "start1", To: "merge"},
			{ID: "e2", From: "start2", To: "merge"},
			{ID: "e3", From: "merge", To: "output"},
		},
	}

	planner := NewExecutionPlanner()
	plan := planner.Plan(graph)

	// Should have 2 start nodes
	if len(plan.StartNodes) != 2 {
		t.Errorf("Expected 2 start nodes, got %d", len(plan.StartNodes))
	}

	// Merge node should have indegree 2
	if plan.GetIndegree("merge") != 2 {
		t.Errorf("Expected indegree 2 for 'merge', got %d", plan.GetIndegree("merge"))
	}
}

func TestExecutionPlanner_EdgeMap(t *testing.T) {
	graph := &entity.Graph{
		Nodes: []entity.Node{
			{ID: "branch", Type: "branch", Name: "Branch"},
			{ID: "true_path", Type: "transform", Name: "True"},
			{ID: "false_path", Type: "transform", Name: "False"},
			{ID: "output", Type: "output", Name: "Output"},
		},
		Edges: []entity.Edge{
			{ID: "e1", From: "branch", To: "true_path", Condition: "x == true", Label: "true"},
			{ID: "e2", From: "branch", To: "false_path", Condition: "", Label: "false"},
			{ID: "e3", From: "true_path", To: "output"},
			{ID: "e4", From: "false_path", To: "output"},
		},
	}

	planner := NewExecutionPlanner()
	plan := planner.Plan(graph)

	// Branch should have 2 outgoing edges
	edges := plan.GetOutgoingEdges("branch")
	if len(edges) != 2 {
		t.Errorf("Expected 2 edges from 'branch', got %d", len(edges))
	}

	// Check conditional edges
	condEdges := plan.GetEdgesWithCondition("branch")
	if len(condEdges) != 1 {
		t.Errorf("Expected 1 conditional edge, got %d", len(condEdges))
	}

	// Check default edge
	defaultEdge := plan.GetDefaultEdge("branch")
	if defaultEdge == nil || defaultEdge.To != "false_path" {
		t.Error("Expected default edge to 'false_path'")
	}
}

func TestExecutionPlanner_FindEdge(t *testing.T) {
	graph := &entity.Graph{
		Nodes: []entity.Node{
			{ID: "a", Type: "transform", Name: "A"},
			{ID: "b", Type: "output", Name: "B"},
		},
		Edges: []entity.Edge{
			{ID: "e1", From: "a", To: "b"},
		},
	}

	planner := NewExecutionPlanner()
	plan := planner.Plan(graph)

	// Find existing edge
	edge := plan.FindEdge("a", "b")
	if edge == nil || edge.ID != "e1" {
		t.Error("Expected to find edge e1")
	}

	// Find non-existing edge
	edge = plan.FindEdge("b", "a")
	if edge != nil {
		t.Error("Expected nil for non-existing edge")
	}
}

func TestExecutionPlanner_TopologicalOrder(t *testing.T) {
	graph := &entity.Graph{
		Nodes: []entity.Node{
			{ID: "a", Type: "transform", Name: "A"},
			{ID: "b", Type: "transform", Name: "B"},
			{ID: "c", Type: "output", Name: "C"},
		},
		Edges: []entity.Edge{
			{ID: "e1", From: "a", To: "b"},
			{ID: "e2", From: "b", To: "c"},
		},
	}

	planner := NewExecutionPlanner()
	plan := planner.Plan(graph)

	order := plan.GetTopologicalOrder()

	if len(order) != 3 {
		t.Errorf("Expected 3 nodes in order, got %d", len(order))
	}

	// a must come before b, b must come before c
	aIdx, bIdx, cIdx := -1, -1, -1
	for i, id := range order {
		switch id {
		case "a":
			aIdx = i
		case "b":
			bIdx = i
		case "c":
			cIdx = i
		}
	}

	if aIdx > bIdx || bIdx > cIdx {
		t.Errorf("Topological order violated: a=%d, b=%d, c=%d", aIdx, bIdx, cIdx)
	}
}

func TestExecutionPlanner_CloneIndegree(t *testing.T) {
	graph := &entity.Graph{
		Nodes: []entity.Node{
			{ID: "a", Type: "transform", Name: "A"},
			{ID: "b", Type: "output", Name: "B"},
		},
		Edges: []entity.Edge{
			{ID: "e1", From: "a", To: "b"},
		},
	}

	planner := NewExecutionPlanner()
	plan := planner.Plan(graph)

	clone := plan.CloneIndegree()

	// Modify clone
	clone["a"] = 99

	// Original should be unchanged
	if plan.GetIndegree("a") != 0 {
		t.Error("CloneIndegree should create independent copy")
	}
}

func TestExecutionPlanner_IsStartNode_IsEndNode(t *testing.T) {
	graph := &entity.Graph{
		Nodes: []entity.Node{
			{ID: "a", Type: "transform", Name: "A"},
			{ID: "b", Type: "transform", Name: "B"},
			{ID: "c", Type: "output", Name: "C"},
		},
		Edges: []entity.Edge{
			{ID: "e1", From: "a", To: "b"},
			{ID: "e2", From: "b", To: "c"},
		},
	}

	planner := NewExecutionPlanner()
	plan := planner.Plan(graph)

	if !plan.IsStartNode("a") {
		t.Error("Expected 'a' to be a start node")
	}
	if plan.IsStartNode("b") {
		t.Error("Expected 'b' not to be a start node")
	}

	if !plan.IsEndNode("c") {
		t.Error("Expected 'c' to be an end node")
	}
	if plan.IsEndNode("a") {
		t.Error("Expected 'a' not to be an end node")
	}
}

func TestExecutionPlanner_GetNodeCount_GetEdgeCount(t *testing.T) {
	graph := &entity.Graph{
		Nodes: []entity.Node{
			{ID: "a", Type: "transform", Name: "A"},
			{ID: "b", Type: "transform", Name: "B"},
			{ID: "c", Type: "output", Name: "C"},
		},
		Edges: []entity.Edge{
			{ID: "e1", From: "a", To: "b"},
			{ID: "e2", From: "b", To: "c"},
		},
	}

	planner := NewExecutionPlanner()
	plan := planner.Plan(graph)

	if plan.GetNodeCount() != 3 {
		t.Errorf("Expected 3 nodes, got %d", plan.GetNodeCount())
	}

	if plan.GetEdgeCount() != 2 {
		t.Errorf("Expected 2 edges, got %d", plan.GetEdgeCount())
	}
}

func TestExecutionPlanner_GetPredecessors_SinglePredecessor(t *testing.T) {
	graph := &entity.Graph{
		Nodes: []entity.Node{
			{ID: "a", Type: "transform", Name: "A"},
			{ID: "b", Type: "output", Name: "B"},
		},
		Edges: []entity.Edge{
			{ID: "e1", From: "a", To: "b"},
		},
	}

	planner := NewExecutionPlanner()
	plan := planner.Plan(graph)

	preds := plan.GetPredecessors("b")
	if len(preds) != 1 {
		t.Errorf("Expected 1 predecessor for 'b', got %d", len(preds))
	}
	if len(preds) > 0 && preds[0] != "a" {
		t.Errorf("Expected predecessor 'a', got '%s'", preds[0])
	}
}

func TestExecutionPlanner_GetPredecessors_MultiplePredecessors(t *testing.T) {
	graph := &entity.Graph{
		Nodes: []entity.Node{
			{ID: "start1", Type: "transform", Name: "Start 1"},
			{ID: "start2", Type: "transform", Name: "Start 2"},
			{ID: "start3", Type: "transform", Name: "Start 3"},
			{ID: "merge", Type: "merge", Name: "Merge"},
		},
		Edges: []entity.Edge{
			{ID: "e1", From: "start1", To: "merge"},
			{ID: "e2", From: "start2", To: "merge"},
			{ID: "e3", From: "start3", To: "merge"},
		},
	}

	planner := NewExecutionPlanner()
	plan := planner.Plan(graph)

	preds := plan.GetPredecessors("merge")
	if len(preds) != 3 {
		t.Errorf("Expected 3 predecessors for 'merge', got %d", len(preds))
	}

	// Check that all expected predecessors are present
	predMap := make(map[string]bool)
	for _, pred := range preds {
		predMap[pred] = true
	}
	for _, expected := range []string{"start1", "start2", "start3"} {
		if !predMap[expected] {
			t.Errorf("Expected predecessor '%s' not found", expected)
		}
	}
}

func TestExecutionPlanner_GetPredecessors_NoPredecessors(t *testing.T) {
	graph := &entity.Graph{
		Nodes: []entity.Node{
			{ID: "a", Type: "transform", Name: "A"},
			{ID: "b", Type: "output", Name: "B"},
		},
		Edges: []entity.Edge{
			{ID: "e1", From: "a", To: "b"},
		},
	}

	planner := NewExecutionPlanner()
	plan := planner.Plan(graph)

	preds := plan.GetPredecessors("a")
	if len(preds) != 0 {
		t.Errorf("Expected 0 predecessors for 'a', got %d", len(preds))
	}
}

func TestExecutionPlanner_GetEdgesByLabel_MatchingLabel(t *testing.T) {
	graph := &entity.Graph{
		Nodes: []entity.Node{
			{ID: "branch", Type: "branch", Name: "Branch"},
			{ID: "true_path", Type: "transform", Name: "True"},
			{ID: "false_path", Type: "transform", Name: "False"},
		},
		Edges: []entity.Edge{
			{ID: "e1", From: "branch", To: "true_path", Label: "true"},
			{ID: "e2", From: "branch", To: "false_path", Label: "false"},
		},
	}

	planner := NewExecutionPlanner()
	plan := planner.Plan(graph)

	trueEdges := plan.GetEdgesByLabel("branch", "true")
	if len(trueEdges) != 1 {
		t.Errorf("Expected 1 edge with label 'true', got %d", len(trueEdges))
	}
	if len(trueEdges) > 0 && trueEdges[0].To != "true_path" {
		t.Errorf("Expected edge to 'true_path', got '%s'", trueEdges[0].To)
	}

	falseEdges := plan.GetEdgesByLabel("branch", "false")
	if len(falseEdges) != 1 {
		t.Errorf("Expected 1 edge with label 'false', got %d", len(falseEdges))
	}
	if len(falseEdges) > 0 && falseEdges[0].To != "false_path" {
		t.Errorf("Expected edge to 'false_path', got '%s'", falseEdges[0].To)
	}
}

func TestExecutionPlanner_GetEdgesByLabel_NoMatches(t *testing.T) {
	graph := &entity.Graph{
		Nodes: []entity.Node{
			{ID: "a", Type: "transform", Name: "A"},
			{ID: "b", Type: "output", Name: "B"},
		},
		Edges: []entity.Edge{
			{ID: "e1", From: "a", To: "b", Label: "primary"},
		},
	}

	planner := NewExecutionPlanner()
	plan := planner.Plan(graph)

	edges := plan.GetEdgesByLabel("a", "nonexistent")
	if len(edges) != 0 {
		t.Errorf("Expected 0 edges with label 'nonexistent', got %d", len(edges))
	}
}

func TestExecutionPlanner_GetEdgesByLabel_EmptyLabel(t *testing.T) {
	graph := &entity.Graph{
		Nodes: []entity.Node{
			{ID: "a", Type: "transform", Name: "A"},
			{ID: "b", Type: "output", Name: "B"},
			{ID: "c", Type: "output", Name: "C"},
		},
		Edges: []entity.Edge{
			{ID: "e1", From: "a", To: "b", Label: "labeled"},
			{ID: "e2", From: "a", To: "c", Label: ""},
		},
	}

	planner := NewExecutionPlanner()
	plan := planner.Plan(graph)

	emptyLabelEdges := plan.GetEdgesByLabel("a", "")
	if len(emptyLabelEdges) != 1 {
		t.Errorf("Expected 1 edge with empty label, got %d", len(emptyLabelEdges))
	}
	if len(emptyLabelEdges) > 0 && emptyLabelEdges[0].To != "c" {
		t.Errorf("Expected edge to 'c', got '%s'", emptyLabelEdges[0].To)
	}
}

func TestExecutionPlanner_SerializeEdgesForConfig_AllFields(t *testing.T) {
	graph := &entity.Graph{
		Nodes: []entity.Node{
			{ID: "a", Type: "transform", Name: "A"},
			{ID: "b", Type: "output", Name: "B"},
			{ID: "c", Type: "output", Name: "C"},
		},
		Edges: []entity.Edge{
			{ID: "e1", From: "a", To: "b", Label: "primary", Condition: "x > 0", DataType: "string"},
			{ID: "e2", From: "a", To: "c", Label: "secondary", Condition: "", DataType: "number"},
		},
	}

	planner := NewExecutionPlanner()
	plan := planner.Plan(graph)

	serialized := plan.SerializeEdgesForConfig("a")
	if len(serialized) != 2 {
		t.Fatalf("Expected 2 serialized edges, got %d", len(serialized))
	}

	// Find the first edge by ID
	var edge1, edge2 map[string]any
	for _, e := range serialized {
		if e["id"] == "e1" {
			edge1 = e
		} else if e["id"] == "e2" {
			edge2 = e
		}
	}

	if edge1 == nil || edge2 == nil {
		t.Fatal("Expected to find both edges in serialized output")
	}

	// Verify edge1 fields
	if edge1["from"] != "a" {
		t.Errorf("Expected edge1 from='a', got '%v'", edge1["from"])
	}
	if edge1["to"] != "b" {
		t.Errorf("Expected edge1 to='b', got '%v'", edge1["to"])
	}
	if edge1["label"] != "primary" {
		t.Errorf("Expected edge1 label='primary', got '%v'", edge1["label"])
	}
	if edge1["condition"] != "x > 0" {
		t.Errorf("Expected edge1 condition='x > 0', got '%v'", edge1["condition"])
	}
	if edge1["data_type"] != "string" {
		t.Errorf("Expected edge1 data_type='string', got '%v'", edge1["data_type"])
	}

	// Verify edge2 fields
	if edge2["data_type"] != "number" {
		t.Errorf("Expected edge2 data_type='number', got '%v'", edge2["data_type"])
	}
	if edge2["condition"] != "" {
		t.Errorf("Expected edge2 condition='', got '%v'", edge2["condition"])
	}
}

func TestExecutionPlanner_SerializeEdgesForConfig_NoEdges(t *testing.T) {
	graph := &entity.Graph{
		Nodes: []entity.Node{
			{ID: "a", Type: "transform", Name: "A"},
			{ID: "b", Type: "output", Name: "B"},
		},
		Edges: []entity.Edge{
			{ID: "e1", From: "a", To: "b"},
		},
	}

	planner := NewExecutionPlanner()
	plan := planner.Plan(graph)

	serialized := plan.SerializeEdgesForConfig("b")
	if len(serialized) != 0 {
		t.Errorf("Expected 0 serialized edges for node 'b', got %d", len(serialized))
	}
}

func TestExecutionPlanner_GetIncomingEdges_SingleEdge(t *testing.T) {
	graph := &entity.Graph{
		Nodes: []entity.Node{
			{ID: "a", Type: "transform", Name: "A"},
			{ID: "b", Type: "output", Name: "B"},
		},
		Edges: []entity.Edge{
			{ID: "e1", From: "a", To: "b", DataType: "string"},
		},
	}

	planner := NewExecutionPlanner()
	plan := planner.Plan(graph)

	incoming := plan.GetIncomingEdges("b")
	if len(incoming) != 1 {
		t.Fatalf("Expected 1 incoming edge for 'b', got %d", len(incoming))
	}
	if incoming[0].ID != "e1" {
		t.Errorf("Expected edge ID 'e1', got '%s'", incoming[0].ID)
	}
	if incoming[0].From != "a" {
		t.Errorf("Expected edge from 'a', got '%s'", incoming[0].From)
	}
	if incoming[0].DataType != "string" {
		t.Errorf("Expected data_type 'string', got '%s'", incoming[0].DataType)
	}
}

func TestExecutionPlanner_GetIncomingEdges_MultipleEdges(t *testing.T) {
	graph := &entity.Graph{
		Nodes: []entity.Node{
			{ID: "start1", Type: "transform", Name: "Start 1"},
			{ID: "start2", Type: "transform", Name: "Start 2"},
			{ID: "merge", Type: "merge", Name: "Merge"},
		},
		Edges: []entity.Edge{
			{ID: "e1", From: "start1", To: "merge", DataType: "array"},
			{ID: "e2", From: "start2", To: "merge", DataType: "object"},
		},
	}

	planner := NewExecutionPlanner()
	plan := planner.Plan(graph)

	incoming := plan.GetIncomingEdges("merge")
	if len(incoming) != 2 {
		t.Fatalf("Expected 2 incoming edges for 'merge', got %d", len(incoming))
	}

	// Check that both edges are present
	edgeMap := make(map[string]*entity.Edge)
	for _, edge := range incoming {
		edgeMap[edge.ID] = edge
	}

	if edgeMap["e1"] == nil {
		t.Error("Expected to find edge 'e1'")
	}
	if edgeMap["e2"] == nil {
		t.Error("Expected to find edge 'e2'")
	}
}

func TestExecutionPlanner_GetIncomingEdges_NoEdges(t *testing.T) {
	graph := &entity.Graph{
		Nodes: []entity.Node{
			{ID: "a", Type: "transform", Name: "A"},
			{ID: "b", Type: "output", Name: "B"},
		},
		Edges: []entity.Edge{
			{ID: "e1", From: "a", To: "b"},
		},
	}

	planner := NewExecutionPlanner()
	plan := planner.Plan(graph)

	incoming := plan.GetIncomingEdges("a")
	if len(incoming) != 0 {
		t.Errorf("Expected 0 incoming edges for 'a', got %d", len(incoming))
	}
}

func TestExecutionPlanner_GetIncomingDataTypes_WithDataTypes(t *testing.T) {
	graph := &entity.Graph{
		Nodes: []entity.Node{
			{ID: "start1", Type: "transform", Name: "Start 1"},
			{ID: "start2", Type: "transform", Name: "Start 2"},
			{ID: "merge", Type: "merge", Name: "Merge"},
		},
		Edges: []entity.Edge{
			{ID: "e1", From: "start1", To: "merge", DataType: "string"},
			{ID: "e2", From: "start2", To: "merge", DataType: "number"},
		},
	}

	planner := NewExecutionPlanner()
	plan := planner.Plan(graph)

	dataTypes := plan.GetIncomingDataTypes("merge")
	if len(dataTypes) != 2 {
		t.Fatalf("Expected 2 data types for 'merge', got %d", len(dataTypes))
	}

	if dataTypes["start1"] != "string" {
		t.Errorf("Expected data type 'string' from 'start1', got '%s'", dataTypes["start1"])
	}
	if dataTypes["start2"] != "number" {
		t.Errorf("Expected data type 'number' from 'start2', got '%s'", dataTypes["start2"])
	}
}

func TestExecutionPlanner_GetIncomingDataTypes_WithoutDataTypes(t *testing.T) {
	graph := &entity.Graph{
		Nodes: []entity.Node{
			{ID: "a", Type: "transform", Name: "A"},
			{ID: "b", Type: "output", Name: "B"},
		},
		Edges: []entity.Edge{
			{ID: "e1", From: "a", To: "b"},
		},
	}

	planner := NewExecutionPlanner()
	plan := planner.Plan(graph)

	dataTypes := plan.GetIncomingDataTypes("b")
	if len(dataTypes) != 0 {
		t.Errorf("Expected 0 data types for 'b', got %d", len(dataTypes))
	}
}

func TestExecutionPlanner_GetIncomingDataTypes_Mixed(t *testing.T) {
	graph := &entity.Graph{
		Nodes: []entity.Node{
			{ID: "start1", Type: "transform", Name: "Start 1"},
			{ID: "start2", Type: "transform", Name: "Start 2"},
			{ID: "start3", Type: "transform", Name: "Start 3"},
			{ID: "merge", Type: "merge", Name: "Merge"},
		},
		Edges: []entity.Edge{
			{ID: "e1", From: "start1", To: "merge", DataType: "array"},
			{ID: "e2", From: "start2", To: "merge", DataType: ""},
			{ID: "e3", From: "start3", To: "merge", DataType: "object"},
		},
	}

	planner := NewExecutionPlanner()
	plan := planner.Plan(graph)

	dataTypes := plan.GetIncomingDataTypes("merge")
	// Should only include edges with non-empty data types
	if len(dataTypes) != 2 {
		t.Fatalf("Expected 2 data types for 'merge', got %d", len(dataTypes))
	}

	if dataTypes["start1"] != "array" {
		t.Errorf("Expected data type 'array' from 'start1', got '%s'", dataTypes["start1"])
	}
	if dataTypes["start3"] != "object" {
		t.Errorf("Expected data type 'object' from 'start3', got '%s'", dataTypes["start3"])
	}
	if _, exists := dataTypes["start2"]; exists {
		t.Error("Did not expect data type from 'start2' (empty data type)")
	}
}
