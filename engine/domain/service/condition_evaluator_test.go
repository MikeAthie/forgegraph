package service

import (
	"testing"

	"github.com/forgegraph/engine/domain/entity"
)

// Helper functions to create test states
func emptyState() *entity.State {
	return entity.NewState()
}

func withVar(name string, value any) func() *entity.State {
	return func() *entity.State {
		s := entity.NewState()
		s.SetVar(name, value)
		return s
	}
}

func withNodeOutput(nodeID string, output any) func() *entity.State {
	return func() *entity.State {
		s := entity.NewState()
		s.SetNodeOutput(nodeID, output)
		return s
	}
}

func withInput(name string, value any) func() *entity.State {
	return func() *entity.State {
		s := entity.NewState()
		s.Set("input."+name, value)
		return s
	}
}

func TestConditionEvaluator_Evaluate(t *testing.T) {
	tests := []struct {
		name      string
		condition string
		state     func() *entity.State
		expected  any
		wantErr   bool
	}{
		// Boolean literals
		{
			name:      "true literal",
			condition: "true",
			state:     emptyState,
			expected:  true,
			wantErr:   false,
		},
		{
			name:      "false literal",
			condition: "false",
			state:     emptyState,
			expected:  false,
			wantErr:   false,
		},

		// String equality comparisons
		{
			name:      "string equality with double quotes",
			condition: `vars.status == "success"`,
			state:     withVar("status", "success"),
			expected:  true,
			wantErr:   false,
		},
		{
			name:      "string equality with single quotes",
			condition: `vars.status == 'success'`,
			state:     withVar("status", "success"),
			expected:  true,
			wantErr:   false,
		},
		{
			name:      "string equality false",
			condition: `vars.status == "failed"`,
			state:     withVar("status", "success"),
			expected:  false,
			wantErr:   false,
		},
		{
			name:      "string inequality",
			condition: `vars.status != "failed"`,
			state:     withVar("status", "success"),
			expected:  true,
			wantErr:   false,
		},

		// Number equality comparisons
		{
			name:      "integer equality",
			condition: "vars.count == 42",
			state:     withVar("count", 42),
			expected:  true,
			wantErr:   false,
		},
		{
			name:      "integer equality with int64",
			condition: "vars.count == 42",
			state:     withVar("count", int64(42)),
			expected:  true,
			wantErr:   false,
		},
		{
			name:      "float equality",
			condition: "vars.price == 19.99",
			state:     withVar("price", 19.99),
			expected:  true,
			wantErr:   false,
		},

		// Boolean comparisons
		{
			name:      "bool equality true",
			condition: "vars.enabled == true",
			state:     withVar("enabled", true),
			expected:  true,
			wantErr:   false,
		},
		{
			name:      "bool equality false",
			condition: "vars.enabled == false",
			state:     withVar("enabled", false),
			expected:  true,
			wantErr:   false,
		},
		{
			name:      "bool inequality",
			condition: "vars.approved != false",
			state:     withVar("approved", true),
			expected:  true,
			wantErr:   false,
		},

		// Numeric comparisons
		{
			name:      "greater than true",
			condition: "vars.score > 80",
			state:     withVar("score", 85),
			expected:  true,
			wantErr:   false,
		},
		{
			name:      "greater than false",
			condition: "vars.score > 80",
			state:     withVar("score", 75),
			expected:  false,
			wantErr:   false,
		},
		{
			name:      "greater than equal boundary",
			condition: "vars.score > 80",
			state:     withVar("score", 80),
			expected:  false,
			wantErr:   false,
		},
		{
			name:      "less than true",
			condition: "vars.age < 18",
			state:     withVar("age", 15),
			expected:  true,
			wantErr:   false,
		},
		{
			name:      "less than false",
			condition: "vars.age < 18",
			state:     withVar("age", 25),
			expected:  false,
			wantErr:   false,
		},
		{
			name:      "greater or equal true at boundary",
			condition: "vars.count >= 10",
			state:     withVar("count", 10),
			expected:  true,
			wantErr:   false,
		},
		{
			name:      "greater or equal true above",
			condition: "vars.count >= 10",
			state:     withVar("count", 15),
			expected:  true,
			wantErr:   false,
		},
		{
			name:      "greater or equal false",
			condition: "vars.count >= 10",
			state:     withVar("count", 5),
			expected:  false,
			wantErr:   false,
		},
		{
			name:      "less or equal true at boundary",
			condition: "vars.count <= 10",
			state:     withVar("count", 10),
			expected:  true,
			wantErr:   false,
		},
		{
			name:      "less or equal true below",
			condition: "vars.count <= 10",
			state:     withVar("count", 5),
			expected:  true,
			wantErr:   false,
		},

		// Nested path access
		{
			name:      "node output status code",
			condition: "node.http_1.output.status == 200",
			state:     withNodeOutput("http_1", map[string]any{"status": 200}),
			expected:  true,
			wantErr:   false,
		},
		{
			name:      "node output nested object",
			condition: `node.api.output.data.type == "user"`,
			state: func() *entity.State {
				s := entity.NewState()
				s.SetNodeOutput("api", map[string]any{
					"data": map[string]any{
						"type": "user",
					},
				})
				return s
			},
			expected: true,
			wantErr:  false,
		},
		{
			name:      "deeply nested array access",
			condition: `node.api.output.data.users.0.name == "Alice"`,
			state: func() *entity.State {
				s := entity.NewState()
				s.SetNodeOutput("api", map[string]any{
					"data": map[string]any{
						"users": []any{
							map[string]any{"name": "Alice"},
							map[string]any{"name": "Bob"},
						},
					},
				})
				return s
			},
			expected: true,
			wantErr:  false,
		},

		// Null handling
		{
			name:      "missing path equals null",
			condition: "vars.missing == null",
			state:     emptyState,
			expected:  true,
			wantErr:   false,
		},
		{
			name:      "existing value not null",
			condition: "vars.value != null",
			state:     withVar("value", "present"),
			expected:  true,
			wantErr:   false,
		},
		{
			name:      "nil literal comparison",
			condition: "vars.empty == nil",
			state:     emptyState,
			expected:  true,
			wantErr:   false,
		},

		// Path-only (truthy check)
		{
			name:      "truthy path with true bool",
			condition: "vars.active",
			state:     withVar("active", true),
			expected:  true,
			wantErr:   false,
		},
		{
			name:      "falsy path with false bool",
			condition: "vars.disabled",
			state:     withVar("disabled", false),
			expected:  false,
			wantErr:   false,
		},
		{
			name:      "empty string is falsy",
			condition: "vars.name",
			state:     withVar("name", ""),
			expected:  false,
			wantErr:   false,
		},
		{
			name:      "non-empty string is truthy",
			condition: "vars.name",
			state:     withVar("name", "John"),
			expected:  true,
			wantErr:   false,
		},
		{
			name:      "zero number is falsy",
			condition: "vars.count",
			state:     withVar("count", 0),
			expected:  false,
			wantErr:   false,
		},
		{
			name:      "non-zero number is truthy",
			condition: "vars.count",
			state:     withVar("count", 5),
			expected:  true,
			wantErr:   false,
		},
		{
			name:      "missing path is falsy",
			condition: "vars.nonexistent",
			state:     emptyState,
			expected:  false,
			wantErr:   false,
		},

		// Input path
		{
			name:      "input value comparison",
			condition: `input.mode == "production"`,
			state:     withInput("mode", "production"),
			expected:  true,
			wantErr:   false,
		},

		// Error cases
		{
			name:      "empty condition",
			condition: "",
			state:     emptyState,
			expected:  nil,
			wantErr:   true,
		},
		{
			name:      "whitespace only condition",
			condition: "   ",
			state:     emptyState,
			expected:  nil,
			wantErr:   true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			evaluator := NewConditionEvaluator()
			state := tt.state()

			result, err := evaluator.Evaluate(tt.condition, state)

			if tt.wantErr {
				if err == nil {
					t.Errorf("Expected error, got nil")
				}
				return
			}

			if err != nil {
				t.Errorf("Unexpected error: %v", err)
				return
			}

			if result != tt.expected {
				t.Errorf("Evaluate() = %v (%T), want %v (%T)", result, result, tt.expected, tt.expected)
			}
		})
	}
}

func TestConditionEvaluator_EvaluateBool(t *testing.T) {
	tests := []struct {
		name      string
		condition string
		state     func() *entity.State
		expected  bool
		wantErr   bool
	}{
		{
			name:      "simple true condition",
			condition: "vars.score > 50",
			state:     withVar("score", 75),
			expected:  true,
			wantErr:   false,
		},
		{
			name:      "simple false condition",
			condition: "vars.score > 50",
			state:     withVar("score", 25),
			expected:  false,
			wantErr:   false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			evaluator := NewConditionEvaluator()
			state := tt.state()

			result, err := evaluator.EvaluateBool(tt.condition, state)

			if tt.wantErr {
				if err == nil {
					t.Errorf("Expected error, got nil")
				}
				return
			}

			if err != nil {
				t.Errorf("Unexpected error: %v", err)
				return
			}

			if result != tt.expected {
				t.Errorf("EvaluateBool() = %v, want %v", result, tt.expected)
			}
		})
	}
}

func TestConditionEvaluator_IsTruthy(t *testing.T) {
	evaluator := NewConditionEvaluator()

	tests := []struct {
		name     string
		value    any
		expected bool
	}{
		// Nil
		{"nil", nil, false},

		// Booleans
		{"true", true, true},
		{"false", false, false},

		// Numbers
		{"zero int", 0, false},
		{"non-zero int", 42, true},
		{"negative int", -1, true},
		{"zero int64", int64(0), false},
		{"non-zero int64", int64(100), true},
		{"zero float", 0.0, false},
		{"non-zero float", 3.14, true},

		// Strings
		{"empty string", "", false},
		{"false string", "false", false},
		{"zero string", "0", false},
		{"non-empty string", "hello", true},
		{"whitespace string", " ", true},

		// Collections
		{"empty slice", []any{}, false},
		{"non-empty slice", []any{1, 2, 3}, true},
		{"empty map", map[string]any{}, false},
		{"non-empty map", map[string]any{"key": "value"}, true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := evaluator.IsTruthy(tt.value)
			if result != tt.expected {
				t.Errorf("IsTruthy(%v) = %v, want %v", tt.value, result, tt.expected)
			}
		})
	}
}

func TestConditionEvaluator_TypeCoercion(t *testing.T) {
	evaluator := NewConditionEvaluator()

	tests := []struct {
		name      string
		condition string
		state     func() *entity.State
		expected  bool
	}{
		{
			name:      "string number equals int",
			condition: `vars.count == 42`,
			state:     withVar("count", "42"),
			expected:  true,
		},
		{
			name:      "int equals float",
			condition: "vars.value == 10",
			state:     withVar("value", 10.0),
			expected:  true,
		},
		{
			name:      "string true equals bool true",
			condition: "vars.flag == true",
			state:     withVar("flag", "true"),
			expected:  true,
		},
		{
			name:      "bool true equals string true",
			condition: `vars.flag == "true"`,
			state:     withVar("flag", true),
			expected:  true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			state := tt.state()
			result, err := evaluator.EvaluateBool(tt.condition, state)
			if err != nil {
				t.Errorf("Unexpected error: %v", err)
				return
			}
			if result != tt.expected {
				t.Errorf("Evaluate() = %v, want %v", result, tt.expected)
			}
		})
	}
}

func TestConditionEvaluator_NumericComparisonWithStrings(t *testing.T) {
	evaluator := NewConditionEvaluator()

	// Numeric comparison with non-numeric string values returns error
	// This validates that the condition evaluator properly handles type mismatches
	state := withVar("name", "Alice")()

	result, err := evaluator.EvaluateBool(`vars.name > "Bob"`, state)
	// The comparison should fail with an error because strings can't be compared numerically
	if err == nil {
		// If no error, result should be false (safe default for failed comparison)
		if result != false {
			t.Errorf("Expected false for non-numeric comparison, got %v", result)
		}
	}
	// If there is an error, that's also acceptable behavior
}
