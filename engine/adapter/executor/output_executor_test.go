package executor

import (
	"context"
	"testing"

	"github.com/forgegraph/engine/domain/entity"
	"github.com/forgegraph/engine/domain/value"
)

func TestOutputExecutor_NodeType(t *testing.T) {
	executor := NewOutputExecutor()
	if executor.NodeType() != string(value.NodeTypeOutput) {
		t.Errorf("NodeType() = %v, want %v", executor.NodeType(), string(value.NodeTypeOutput))
	}
}

func TestOutputExecutor_Execute_WithOutputMapping(t *testing.T) {
	executor := NewOutputExecutor()
	state := entity.NewState()
	state.SetNodeOutput("transform_1", map[string]any{"data": "processed"})
	state.SetVar("summary", "test summary")

	node := &entity.Node{
		ID:   "output_1",
		Type: string(value.NodeTypeOutput),
		Config: map[string]any{
			"output_mapping": map[string]any{
				"result":  "node.transform_1.output",
				"summary": "vars.summary",
			},
		},
	}

	result, err := executor.Execute(context.Background(), node, state)
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}

	output, ok := result.Output.(map[string]any)
	if !ok {
		t.Fatalf("Output is not map[string]any")
	}

	if output["result"] == nil {
		t.Error("Expected 'result' key in output")
	}
	if output["summary"] != "test summary" {
		t.Errorf("Expected summary = 'test summary', got %v", output["summary"])
	}
}

func TestOutputExecutor_Execute_WithOutputKeys(t *testing.T) {
	executor := NewOutputExecutor()
	state := entity.NewState()
	state.Set("node.http_1.output", map[string]any{"status": 200})
	state.Set("vars.computed", "value")

	node := &entity.Node{
		ID:   "output_1",
		Type: string(value.NodeTypeOutput),
		Config: map[string]any{
			"output_keys": []any{
				"node.http_1.output",
				"vars.computed",
			},
		},
	}

	result, err := executor.Execute(context.Background(), node, state)
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}

	output, ok := result.Output.(map[string]any)
	if !ok {
		t.Fatalf("Output is not map[string]any")
	}

	if output["node.http_1.output"] == nil {
		t.Error("Expected 'node.http_1.output' key in output")
	}
	if output["vars.computed"] != "value" {
		t.Errorf("Expected vars.computed = 'value', got %v", output["vars.computed"])
	}
}

func TestOutputExecutor_Execute_IncludeAll(t *testing.T) {
	executor := NewOutputExecutor()
	state := entity.NewState()
	state.SetNodeOutput("node_a", "output_a")
	state.SetNodeOutput("node_b", "output_b")
	state.SetVar("var1", "value1")
	state.Set("input.data", "input_value") // Should not be included

	node := &entity.Node{
		ID:     "output_1",
		Type:   string(value.NodeTypeOutput),
		Config: map[string]any{},
	}

	result, err := executor.Execute(context.Background(), node, state)
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}

	output, ok := result.Output.(map[string]any)
	if !ok {
		t.Fatalf("Output is not map[string]any")
	}

	// Should include node outputs
	if output["node.node_a.output"] != "output_a" {
		t.Error("Expected 'node.node_a.output' in output")
	}
	if output["node.node_b.output"] != "output_b" {
		t.Error("Expected 'node.node_b.output' in output")
	}
	// Should include vars
	if output["vars.var1"] != "value1" {
		t.Error("Expected 'vars.var1' in output")
	}
	// Should not include input
	if _, exists := output["input.data"]; exists {
		t.Error("Should not include 'input.data' in output")
	}
}

func TestOutputExecutor_Execute_IncludeAllFalse(t *testing.T) {
	executor := NewOutputExecutor()
	state := entity.NewState()
	state.SetNodeOutput("node_a", "output_a")

	node := &entity.Node{
		ID:   "output_1",
		Type: string(value.NodeTypeOutput),
		Config: map[string]any{
			"include_all": false,
		},
	}

	result, err := executor.Execute(context.Background(), node, state)
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}

	output, ok := result.Output.(map[string]any)
	if !ok {
		t.Fatalf("Output is not map[string]any")
	}

	if len(output) != 0 {
		t.Errorf("Expected empty output when include_all=false, got %v", output)
	}
}

func TestOutputExecutor_Execute_MissingKeys(t *testing.T) {
	executor := NewOutputExecutor()
	state := entity.NewState()
	// Don't set any values

	node := &entity.Node{
		ID:   "output_1",
		Type: string(value.NodeTypeOutput),
		Config: map[string]any{
			"output_keys": []any{
				"nonexistent.key",
			},
		},
	}

	result, err := executor.Execute(context.Background(), node, state)
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}

	output, ok := result.Output.(map[string]any)
	if !ok {
		t.Fatalf("Output is not map[string]any")
	}

	// Missing keys should be silently ignored
	if _, exists := output["nonexistent.key"]; exists {
		t.Error("Should not include nonexistent keys")
	}
}
