package executor

import (
	"context"
	"testing"

	"github.com/forgegraph/engine/domain/entity"
	"github.com/forgegraph/engine/domain/value"
)

func TestTransformExecutor_NodeType(t *testing.T) {
	executor := NewTransformExecutor()
	if executor.NodeType() != string(value.NodeTypeTransform) {
		t.Errorf("NodeType() = %v, want %v", executor.NodeType(), string(value.NodeTypeTransform))
	}
}

func TestTransformExecutor_Execute_Static(t *testing.T) {
	executor := NewTransformExecutor()
	state := entity.NewState()

	node := &entity.Node{
		ID:   "transform_1",
		Type: string(value.NodeTypeTransform),
		Config: map[string]any{
			"expression_type": "static",
			"value":           "hello world",
			"output_key":      "greeting",
		},
	}

	result, err := executor.Execute(context.Background(), node, state)
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if result.Error != nil {
		t.Fatalf("result.Error = %v", result.Error)
	}

	if result.Output != "hello world" {
		t.Errorf("Output = %v, want 'hello world'", result.Output)
	}

	// Check state was updated
	val, exists := state.GetVar("greeting")
	if !exists || val != "hello world" {
		t.Errorf("State vars.greeting = %v, want 'hello world'", val)
	}
}

func TestTransformExecutor_Execute_KeyLookup(t *testing.T) {
	executor := NewTransformExecutor()
	state := entity.NewState()
	state.SetNodeOutput("http_1", map[string]any{
		"data": map[string]any{
			"name": "John",
		},
	})

	node := &entity.Node{
		ID:   "transform_1",
		Type: string(value.NodeTypeTransform),
		Config: map[string]any{
			"expression_type": "key_lookup",
			"expression":      "node.http_1.output.data.name",
			"output_key":      "user_name",
		},
	}

	result, err := executor.Execute(context.Background(), node, state)
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if result.Error != nil {
		t.Fatalf("result.Error = %v", result.Error)
	}

	if result.Output != "John" {
		t.Errorf("Output = %v, want 'John'", result.Output)
	}

	val, exists := state.GetVar("user_name")
	if !exists || val != "John" {
		t.Errorf("State vars.user_name = %v, want 'John'", val)
	}
}

func TestTransformExecutor_Execute_KeyLookup_DirectKey(t *testing.T) {
	executor := NewTransformExecutor()
	state := entity.NewState()
	state.Set("node.simple.output", "direct value")

	node := &entity.Node{
		ID:   "transform_1",
		Type: string(value.NodeTypeTransform),
		Config: map[string]any{
			"expression_type": "key_lookup",
			"expression":      "node.simple.output",
			"output_key":      "result",
		},
	}

	result, err := executor.Execute(context.Background(), node, state)
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}

	if result.Output != "direct value" {
		t.Errorf("Output = %v, want 'direct value'", result.Output)
	}
}

func TestTransformExecutor_Execute_JSONPath(t *testing.T) {
	executor := NewTransformExecutor()
	state := entity.NewState()
	state.SetNodeOutput("api", map[string]any{
		"users": []any{
			map[string]any{"name": "Alice"},
			map[string]any{"name": "Bob"},
		},
	})

	node := &entity.Node{
		ID:   "transform_1",
		Type: string(value.NodeTypeTransform),
		Config: map[string]any{
			"expression_type": "json_path",
			"expression":      "$.node.api.output.users.0.name",
			"output_key":      "first_user",
		},
	}

	result, err := executor.Execute(context.Background(), node, state)
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if result.Error != nil {
		t.Fatalf("result.Error = %v", result.Error)
	}

	if result.Output != "Alice" {
		t.Errorf("Output = %v, want 'Alice'", result.Output)
	}
}

func TestTransformExecutor_Execute_Template(t *testing.T) {
	executor := NewTransformExecutor()
	state := entity.NewState()
	state.SetVar("name", "World")
	state.SetNodeOutput("count", 42)

	node := &entity.Node{
		ID:   "transform_1",
		Type: string(value.NodeTypeTransform),
		Config: map[string]any{
			"expression_type": "template",
			"expression":      "Hello, {{vars.name}}! Count: {{node.count.output}}",
			"output_key":      "message",
		},
	}

	result, err := executor.Execute(context.Background(), node, state)
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if result.Error != nil {
		t.Fatalf("result.Error = %v", result.Error)
	}

	expected := "Hello, World! Count: 42"
	if result.Output != expected {
		t.Errorf("Output = %v, want %v", result.Output, expected)
	}
}

func TestTransformExecutor_Execute_MissingOutputKey(t *testing.T) {
	executor := NewTransformExecutor()
	state := entity.NewState()

	node := &entity.Node{
		ID:   "transform_1",
		Type: string(value.NodeTypeTransform),
		Config: map[string]any{
			"expression_type": "static",
			"value":           "test",
			// Missing output_key
		},
	}

	result, err := executor.Execute(context.Background(), node, state)
	if err != nil {
		t.Fatalf("Execute() should not return error, got %v", err)
	}
	if result.Error == nil {
		t.Error("Expected result.Error for missing output_key")
	}
}

func TestTransformExecutor_Execute_UnknownExpressionType(t *testing.T) {
	executor := NewTransformExecutor()
	state := entity.NewState()

	node := &entity.Node{
		ID:   "transform_1",
		Type: string(value.NodeTypeTransform),
		Config: map[string]any{
			"expression_type": "unknown",
			"output_key":      "result",
		},
	}

	result, err := executor.Execute(context.Background(), node, state)
	if err != nil {
		t.Fatalf("Execute() should not return error, got %v", err)
	}
	if result.Error == nil {
		t.Error("Expected result.Error for unknown expression_type")
	}
}

func TestTransformExecutor_Execute_DefaultExpressionType(t *testing.T) {
	executor := NewTransformExecutor()
	state := entity.NewState()
	state.Set("source.value", "from_source")

	node := &entity.Node{
		ID:   "transform_1",
		Type: string(value.NodeTypeTransform),
		Config: map[string]any{
			"expression": "source.value",
			"output_key": "dest",
			// No expression_type - should default to key_lookup
		},
	}

	result, err := executor.Execute(context.Background(), node, state)
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if result.Error != nil {
		t.Fatalf("result.Error = %v", result.Error)
	}

	if result.Output != "from_source" {
		t.Errorf("Output = %v, want 'from_source'", result.Output)
	}
}

func TestSubstituteTemplate(t *testing.T) {
	state := entity.NewState()
	state.Set("name", "Claude")
	state.SetNodeOutput("api", map[string]any{
		"version": "1.0",
	})

	tests := []struct {
		name     string
		template string
		expected string
	}{
		{
			name:     "simple substitution",
			template: "Hello {{name}}",
			expected: "Hello Claude",
		},
		{
			name:     "nested path",
			template: "API v{{node.api.output.version}}",
			expected: "API v1.0",
		},
		{
			name:     "missing key",
			template: "Value: {{nonexistent}}",
			expected: "Value: ",
		},
		{
			name:     "multiple substitutions",
			template: "{{name}} uses API v{{node.api.output.version}}",
			expected: "Claude uses API v1.0",
		},
		{
			name:     "no substitutions",
			template: "plain text",
			expected: "plain text",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := SubstituteTemplate(tt.template, state)
			if result != tt.expected {
				t.Errorf("SubstituteTemplate() = %v, want %v", result, tt.expected)
			}
		})
	}
}
