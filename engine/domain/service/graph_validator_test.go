package service

import (
	"testing"

	"github.com/forgegraph/engine/domain"
	"github.com/forgegraph/engine/domain/entity"
)

func TestGraphValidator_ValidGraph(t *testing.T) {
	graph := &entity.Graph{
		Nodes: []entity.Node{
			{ID: "start", Type: "transform", Name: "Start"},
			{ID: "end", Type: "output", Name: "End"},
		},
		Edges: []entity.Edge{
			{ID: "e1", From: "start", To: "end"},
		},
	}

	validator := NewGraphValidator()
	err := validator.Validate(graph)

	if err != nil {
		t.Errorf("Expected valid graph, got error: %v", err)
	}
}

func TestGraphValidator_EmptyGraph(t *testing.T) {
	graph := &entity.Graph{
		Nodes: []entity.Node{},
		Edges: []entity.Edge{},
	}

	validator := NewGraphValidator()
	err := validator.Validate(graph)

	if err != domain.ErrEmptyGraph {
		t.Errorf("Expected ErrEmptyGraph, got: %v", err)
	}
}

func TestGraphValidator_NilGraph(t *testing.T) {
	validator := NewGraphValidator()
	err := validator.Validate(nil)

	if err != domain.ErrEmptyGraph {
		t.Errorf("Expected ErrEmptyGraph for nil graph, got: %v", err)
	}
}

func TestGraphValidator_NoStartNode(t *testing.T) {
	// Graph where all nodes have incoming edges
	graph := &entity.Graph{
		Nodes: []entity.Node{
			{ID: "a", Type: "transform", Name: "A"},
			{ID: "b", Type: "output", Name: "B"},
		},
		Edges: []entity.Edge{
			{ID: "e1", From: "a", To: "b"},
			{ID: "e2", From: "b", To: "a"}, // Creates cycle, no start node
		},
	}

	validator := NewGraphValidator()
	err := validator.Validate(graph)

	// This will either fail with NoStartNode or CycleDetected
	if err == nil {
		t.Error("Expected error for graph with no start node")
	}
}

func TestGraphValidator_NoOutputNode(t *testing.T) {
	graph := &entity.Graph{
		Nodes: []entity.Node{
			{ID: "a", Type: "transform", Name: "A"},
			{ID: "b", Type: "transform", Name: "B"},
		},
		Edges: []entity.Edge{
			{ID: "e1", From: "a", To: "b"},
		},
	}

	validator := NewGraphValidator()
	err := validator.Validate(graph)

	if err != domain.ErrNoOutputNode {
		t.Errorf("Expected ErrNoOutputNode, got: %v", err)
	}
}

func TestGraphValidator_DetectsCycle(t *testing.T) {
	graph := &entity.Graph{
		Nodes: []entity.Node{
			{ID: "a", Type: "transform", Name: "A"},
			{ID: "b", Type: "transform", Name: "B"},
			{ID: "c", Type: "output", Name: "C"},
		},
		Edges: []entity.Edge{
			{ID: "e1", From: "a", To: "b"},
			{ID: "e2", From: "b", To: "c"},
			{ID: "e3", From: "c", To: "a"}, // Creates cycle
		},
	}

	validator := NewGraphValidator()
	err := validator.Validate(graph)

	if err != domain.ErrCycleDetected {
		t.Errorf("Expected ErrCycleDetected, got: %v", err)
	}
}

func TestGraphValidator_DuplicateNodeID(t *testing.T) {
	graph := &entity.Graph{
		Nodes: []entity.Node{
			{ID: "a", Type: "transform", Name: "A"},
			{ID: "a", Type: "output", Name: "A Duplicate"},
		},
		Edges: []entity.Edge{},
	}

	validator := NewGraphValidator()
	err := validator.Validate(graph)

	if err != domain.ErrDuplicateNodeID {
		t.Errorf("Expected ErrDuplicateNodeID, got: %v", err)
	}
}

func TestGraphValidator_InvalidNodeType(t *testing.T) {
	graph := &entity.Graph{
		Nodes: []entity.Node{
			{ID: "a", Type: "invalid_type", Name: "A"},
			{ID: "b", Type: "output", Name: "B"},
		},
		Edges: []entity.Edge{
			{ID: "e1", From: "a", To: "b"},
		},
	}

	validator := NewGraphValidator()
	err := validator.Validate(graph)

	if err == nil {
		t.Error("Expected error for invalid node type")
	}
}

func TestGraphValidator_EdgeToNonExistentNode(t *testing.T) {
	graph := &entity.Graph{
		Nodes: []entity.Node{
			{ID: "a", Type: "transform", Name: "A"},
			{ID: "b", Type: "output", Name: "B"},
		},
		Edges: []entity.Edge{
			{ID: "e1", From: "a", To: "nonexistent"},
		},
	}

	validator := NewGraphValidator()
	err := validator.Validate(graph)

	if err == nil {
		t.Error("Expected error for edge to non-existent node")
	}
}

func TestGraphValidator_SelfLoop(t *testing.T) {
	graph := &entity.Graph{
		Nodes: []entity.Node{
			{ID: "a", Type: "transform", Name: "A"},
			{ID: "b", Type: "output", Name: "B"},
		},
		Edges: []entity.Edge{
			{ID: "e1", From: "a", To: "a"}, // Self-loop
			{ID: "e2", From: "a", To: "b"},
		},
	}

	validator := NewGraphValidator()
	err := validator.Validate(graph)

	if err != domain.ErrSelfLoop {
		t.Errorf("Expected ErrSelfLoop, got: %v", err)
	}
}

func TestGraphValidator_ComplexValidGraph(t *testing.T) {
	// A more complex graph with branches
	graph := &entity.Graph{
		Nodes: []entity.Node{
			{ID: "start", Type: "transform", Name: "Start"},
			{ID: "branch", Type: "branch", Name: "Branch"},
			{ID: "path_a", Type: "http", Name: "Path A"},
			{ID: "path_b", Type: "prompt", Name: "Path B"},
			{ID: "merge", Type: "merge", Name: "Merge"},
			{ID: "output", Type: "output", Name: "Output"},
		},
		Edges: []entity.Edge{
			{ID: "e1", From: "start", To: "branch"},
			{ID: "e2", From: "branch", To: "path_a", Condition: "true"},
			{ID: "e3", From: "branch", To: "path_b", Condition: "false"},
			{ID: "e4", From: "path_a", To: "merge"},
			{ID: "e5", From: "path_b", To: "merge"},
			{ID: "e6", From: "merge", To: "output"},
		},
	}

	validator := NewGraphValidator()
	err := validator.Validate(graph)

	if err != nil {
		t.Errorf("Expected valid complex graph, got error: %v", err)
	}
}
