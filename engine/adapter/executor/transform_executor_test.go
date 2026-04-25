package executor

import (
	"context"
	"strings"
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

func TestTransformExecutor_Execute_SimulationStep_StrategyAgent(t *testing.T) {
	executor := NewTransformExecutor()
	state := entity.NewStateWithInput(map[string]any{
		"goal": "Launch a deterministic growth campaign.",
	})

	node := &entity.Node{
		ID:   "strategy_agent",
		Type: string(value.NodeTypeTransform),
		Config: map[string]any{
			"expression_type": "simulation_step",
			"simulation_role": "strategy_agent",
			"output_key":      "execution_state",
		},
	}

	result, err := executor.Execute(context.Background(), node, state)
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if result.Error != nil {
		t.Fatalf("result.Error = %v", result.Error)
	}

	output, ok := result.Output.(map[string]any)
	if !ok {
		t.Fatalf("Output type = %T, want map[string]any", result.Output)
	}
	statePayload, ok := output["state"].(map[string]any)
	if !ok {
		t.Fatalf("output.state type = %T, want map[string]any", output["state"])
	}
	if statePayload["goal"] != "Launch a deterministic growth campaign." {
		t.Fatalf("goal = %v", statePayload["goal"])
	}
	if _, ok := statePayload["strategy"].(map[string]any); !ok {
		t.Fatalf("strategy missing from state payload: %#v", statePayload)
	}

	stored, exists := state.Get("vars.execution_state")
	if !exists {
		t.Fatal("expected vars.execution_state to be stored")
	}
	storedMap, ok := stored.(map[string]any)
	if !ok {
		t.Fatalf("stored state type = %T, want map[string]any", stored)
	}
	if storedMap["goal"] != "Launch a deterministic growth campaign." {
		t.Fatalf("stored goal = %v", storedMap["goal"])
	}
}

func TestTransformExecutor_Execute_SimulationStep_ContentAndAnalytics(t *testing.T) {
	executor := NewTransformExecutor()
	state := entity.NewState()
	state.SetVar("execution_state", map[string]any{
		"goal": "Ship a visible campaign loop.",
		"strategy": map[string]any{
			"primary_channel": "linkedin",
		},
		"content_assets":    []any{},
		"distribution_plan": nil,
		"analytics":         nil,
		"iteration":         0,
	})

	contentNode := &entity.Node{
		ID:   "content_copywriter_specialist",
		Type: string(value.NodeTypeTransform),
		Config: map[string]any{
			"expression_type": "simulation_step",
			"simulation_role": "content_copywriter_specialist",
			"output_key":      "execution_state",
		},
	}

	if _, err := executor.Execute(context.Background(), contentNode, state); err != nil {
		t.Fatalf("content Execute() error = %v", err)
	}

	contentAgentNode := &entity.Node{
		ID:   "content_agent",
		Type: string(value.NodeTypeTransform),
		Config: map[string]any{
			"expression_type": "simulation_step",
			"simulation_role": "content_agent",
			"output_key":      "execution_state",
		},
	}

	if _, err := executor.Execute(context.Background(), contentAgentNode, state); err != nil {
		t.Fatalf("content agent Execute() error = %v", err)
	}

	distributionNode := &entity.Node{
		ID:   "distribution_agent",
		Type: string(value.NodeTypeTransform),
		Config: map[string]any{
			"expression_type": "simulation_step",
			"simulation_role": "distribution_agent",
			"output_key":      "execution_state",
		},
	}

	if _, err := executor.Execute(context.Background(), distributionNode, state); err != nil {
		t.Fatalf("distribution Execute() error = %v", err)
	}

	analyticsNode := &entity.Node{
		ID:   "analytics_agent",
		Type: string(value.NodeTypeTransform),
		Config: map[string]any{
			"expression_type": "simulation_step",
			"simulation_role": "analytics_agent",
			"output_key":      "execution_state",
		},
	}

	result, err := executor.Execute(context.Background(), analyticsNode, state)
	if err != nil {
		t.Fatalf("analytics Execute() error = %v", err)
	}
	if result.Error != nil {
		t.Fatalf("analytics result.Error = %v", result.Error)
	}

	stored, exists := state.Get("vars.execution_state")
	if !exists {
		t.Fatal("expected vars.execution_state to exist after simulation steps")
	}
	storedMap, ok := stored.(map[string]any)
	if !ok {
		t.Fatalf("stored state type = %T, want map[string]any", stored)
	}

	contentAssets, ok := storedMap["content_assets"].([]any)
	if !ok {
		t.Fatalf("content_assets type = %T, want []any", storedMap["content_assets"])
	}
	if len(contentAssets) != 1 {
		t.Fatalf("content_assets length = %d, want 1", len(contentAssets))
	}
	if _, ok := storedMap["distribution_plan"].(map[string]any); !ok {
		t.Fatalf("distribution_plan missing from stored state: %#v", storedMap)
	}
	if iteration, ok := storedMap["iteration"].(float64); !ok || iteration != 1 {
		t.Fatalf("iteration = %v, want 1", storedMap["iteration"])
	}
}

func TestTransformExecutor_Execute_SimulationStep_ForcedContentFailure(t *testing.T) {
	executor := NewTransformExecutor()
	state := entity.NewStateWithInput(map[string]any{
		"goal":                  "Test failure visibility.",
		"force_content_failure": true,
	})

	node := &entity.Node{
		ID:   "content_copywriter_specialist",
		Type: string(value.NodeTypeTransform),
		Config: map[string]any{
			"expression_type": "simulation_step",
			"simulation_role": "content_copywriter_specialist",
			"output_key":      "execution_state",
		},
	}

	result, err := executor.Execute(context.Background(), node, state)
	if err != nil {
		t.Fatalf("Execute() should not return transport error, got %v", err)
	}
	if result.Error == nil {
		t.Fatal("expected simulated failure result")
	}
}

func TestTransformExecutor_Execute_StatePatch_DeepMerge(t *testing.T) {
	executor := NewTransformExecutor()
	state := entity.NewState()
	state.SetVar("execution_state", map[string]any{
		"goal": "Upgrade campaign quality.",
		"strategy": map[string]any{
			"primary_channel": "linkedin",
		},
		"content_assets":    []any{},
		"distribution_plan": nil,
		"analytics":         nil,
		"iteration":         0,
	})
	state.SetNodeOutput("strategy_agent", map[string]any{
		"structured_response": map[string]any{
			"strategy": map[string]any{
				"company":         "ForgeGraph Digital Marketing Co",
				"objective":       "Upgrade campaign quality.",
				"primary_channel": "linkedin",
				"audience":        "B2B operators",
			},
		},
	})

	node := &entity.Node{
		ID:   "merge_strategy",
		Type: string(value.NodeTypeTransform),
		Config: map[string]any{
			"expression_type": "state_patch",
			"expression":      "node.strategy_agent.output.structured_response",
			"output_key":      "execution_state",
		},
	}

	result, err := executor.Execute(context.Background(), node, state)
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if result.Error != nil {
		t.Fatalf("result.Error = %v", result.Error)
	}

	output, ok := result.Output.(map[string]any)
	if !ok {
		t.Fatalf("Output type = %T, want map[string]any", result.Output)
	}
	statePayload, ok := output["state"].(map[string]any)
	if !ok {
		t.Fatalf("output.state type = %T, want map[string]any", output["state"])
	}
	strategy, ok := statePayload["strategy"].(map[string]any)
	if !ok {
		t.Fatalf("strategy type = %T, want map[string]any", statePayload["strategy"])
	}
	if strategy["company"] != "ForgeGraph Digital Marketing Co" {
		t.Fatalf("strategy.company = %v", strategy["company"])
	}
	if statePayload["goal"] != "Upgrade campaign quality." {
		t.Fatalf("goal = %v", statePayload["goal"])
	}
}

func TestTransformExecutor_Execute_StatePatch_AppendArray(t *testing.T) {
	executor := NewTransformExecutor()
	state := entity.NewState()
	state.SetVar("execution_state", map[string]any{
		"goal": "Upgrade campaign quality.",
		"strategy": map[string]any{
			"primary_channel": "linkedin",
		},
		"content_assets": []any{
			map[string]any{
				"asset_id": "copy-1",
			},
		},
		"distribution_plan": nil,
		"analytics":         nil,
		"iteration":         0,
	})
	state.SetNodeOutput("content_copywriter_specialist", map[string]any{
		"structured_response": map[string]any{
			"asset": map[string]any{
				"asset_id":    "copy-2",
				"specialist":  "copywriter_specialist",
				"channel":     "linkedin",
				"format":      "post",
				"headline":    "Replayable growth loop v2",
				"body":        "Guard rails and prompts are visible.",
				"iteration":   1,
				"reviewed":    false,
				"department":  "content",
				"state_field": "content_assets",
			},
		},
	})

	node := &entity.Node{
		ID:   "merge_copywriter_asset",
		Type: string(value.NodeTypeTransform),
		Config: map[string]any{
			"expression_type": "state_patch",
			"expression":      "node.content_copywriter_specialist.output.structured_response.asset",
			"patch_mode":      "append_array",
			"target_path":     "content_assets",
			"output_key":      "execution_state",
		},
	}

	result, err := executor.Execute(context.Background(), node, state)
	if err != nil {
		t.Fatalf("Execute() error = %v", err)
	}
	if result.Error != nil {
		t.Fatalf("result.Error = %v", result.Error)
	}

	output, ok := result.Output.(map[string]any)
	if !ok {
		t.Fatalf("Output type = %T, want map[string]any", result.Output)
	}
	statePayload, ok := output["state"].(map[string]any)
	if !ok {
		t.Fatalf("output.state type = %T, want map[string]any", output["state"])
	}
	contentAssets, ok := statePayload["content_assets"].([]any)
	if !ok {
		t.Fatalf("content_assets type = %T, want []any", statePayload["content_assets"])
	}
	if len(contentAssets) != 2 {
		t.Fatalf("content_assets length = %d, want 2", len(contentAssets))
	}
	lastAsset, ok := contentAssets[1].(map[string]any)
	if !ok {
		t.Fatalf("last asset type = %T, want map[string]any", contentAssets[1])
	}
	if lastAsset["asset_id"] != "copy-2" {
		t.Fatalf("last asset_id = %v", lastAsset["asset_id"])
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

func TestSubstituteTemplate_RendersStructuredStateAsJSON(t *testing.T) {
	state := entity.NewState()
	state.SetVar("execution_state", map[string]any{
		"goal": "Test prompt serialization",
		"strategy": map[string]any{
			"primary_channel": "linkedin",
		},
		"content_assets": []any{
			map[string]any{
				"asset_id": "copy-1",
				"headline": "Traceable campaigns",
			},
		},
		"distribution_plan": nil,
		"analytics":         nil,
		"iteration":         1,
	})

	result := SubstituteTemplate("BEGIN\n{{vars.execution_state}}\nEND", state)

	if !strings.Contains(result, "\"goal\": \"Test prompt serialization\"") {
		t.Fatalf("expected JSON goal in template output, got %q", result)
	}
	if !strings.Contains(result, "\"content_assets\": [") {
		t.Fatalf("expected JSON array in template output, got %q", result)
	}
	if strings.Contains(result, "map[") {
		t.Fatalf("expected JSON rendering instead of Go map formatting, got %q", result)
	}
}
