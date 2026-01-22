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
