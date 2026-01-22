package executor

import (
	"context"
	"testing"

	"github.com/forgegraph/engine/domain/entity"
	"github.com/forgegraph/engine/domain/value"
)

func TestBranchExecutor_NodeType(t *testing.T) {
	executor := NewBranchExecutor()
	if executor.NodeType() != string(value.NodeTypeBranch) {
		t.Errorf("NodeType() = %v, want %v", executor.NodeType(), value.NodeTypeBranch)
	}
}

func TestBranchExecutor_Execute(t *testing.T) {
	tests := []struct {
		name          string
		condition     string
		edges         []map[string]any
		state         func() *entity.State
		wantNextNodes []string
		wantBranch    bool
		wantErr       bool
	}{
		{
			name:      "true branch taken with high score",
			condition: "vars.score > 80",
			edges: []map[string]any{
				{"id": "e1", "from": "branch", "to": "success_node", "label": "true"},
				{"id": "e2", "from": "branch", "to": "failure_node", "label": "false"},
			},
			state: func() *entity.State {
				s := entity.NewState()
				s.SetVar("score", 90)
				return s
			},
			wantNextNodes: []string{"success_node"},
			wantBranch:    true,
			wantErr:       false,
		},
		{
			name:      "false branch taken with low score",
			condition: "vars.score > 80",
			edges: []map[string]any{
				{"id": "e1", "from": "branch", "to": "success_node", "label": "true"},
				{"id": "e2", "from": "branch", "to": "failure_node", "label": "false"},
			},
			state: func() *entity.State {
				s := entity.NewState()
				s.SetVar("score", 70)
				return s
			},
			wantNextNodes: []string{"failure_node"},
			wantBranch:    false,
			wantErr:       false,
		},
		{
			name:      "boundary condition - exactly at threshold",
			condition: "vars.score >= 80",
			edges: []map[string]any{
				{"id": "e1", "from": "branch", "to": "pass", "label": "true"},
				{"id": "e2", "from": "branch", "to": "fail", "label": "false"},
			},
			state: func() *entity.State {
				s := entity.NewState()
				s.SetVar("score", 80)
				return s
			},
			wantNextNodes: []string{"pass"},
			wantBranch:    true,
			wantErr:       false,
		},
		{
			name:      "string equality condition",
			condition: `vars.status == "approved"`,
			edges: []map[string]any{
				{"id": "e1", "from": "branch", "to": "process", "label": "true"},
				{"id": "e2", "from": "branch", "to": "reject", "label": "false"},
			},
			state: func() *entity.State {
				s := entity.NewState()
				s.SetVar("status", "approved")
				return s
			},
			wantNextNodes: []string{"process"},
			wantBranch:    true,
			wantErr:       false,
		},
		{
			name:      "boolean variable check",
			condition: "vars.enabled == true",
			edges: []map[string]any{
				{"id": "e1", "from": "branch", "to": "enabled_path", "label": "true"},
				{"id": "e2", "from": "branch", "to": "disabled_path", "label": "false"},
			},
			state: func() *entity.State {
				s := entity.NewState()
				s.SetVar("enabled", true)
				return s
			},
			wantNextNodes: []string{"enabled_path"},
			wantBranch:    true,
			wantErr:       false,
		},
		{
			name:      "default edge fallback when false",
			condition: "vars.approved == true",
			edges: []map[string]any{
				{"id": "e1", "from": "branch", "to": "approved_node", "label": "true"},
				{"id": "e2", "from": "branch", "to": "default_node", "label": ""}, // default
			},
			state: func() *entity.State {
				s := entity.NewState()
				s.SetVar("approved", false)
				return s
			},
			wantNextNodes: []string{"default_node"},
			wantBranch:    false,
			wantErr:       false,
		},
		{
			name:      "multiple edges with same label",
			condition: "vars.broadcast == true",
			edges: []map[string]any{
				{"id": "e1", "from": "branch", "to": "channel_a", "label": "true"},
				{"id": "e2", "from": "branch", "to": "channel_b", "label": "true"},
				{"id": "e3", "from": "branch", "to": "skip", "label": "false"},
			},
			state: func() *entity.State {
				s := entity.NewState()
				s.SetVar("broadcast", true)
				return s
			},
			wantNextNodes: []string{"channel_a", "channel_b"},
			wantBranch:    true,
			wantErr:       false,
		},
		{
			name:      "node output condition",
			condition: "node.http_1.output.status == 200",
			edges: []map[string]any{
				{"id": "e1", "from": "branch", "to": "success", "label": "true"},
				{"id": "e2", "from": "branch", "to": "error", "label": "false"},
			},
			state: func() *entity.State {
				s := entity.NewState()
				s.SetNodeOutput("http_1", map[string]any{"status": 200, "body": "OK"})
				return s
			},
			wantNextNodes: []string{"success"},
			wantBranch:    true,
			wantErr:       false,
		},
		{
			name:      "missing condition returns error",
			condition: "",
			edges:     []map[string]any{},
			state: func() *entity.State {
				return entity.NewState()
			},
			wantErr: true,
		},
		{
			name:      "no edges - returns result without routing",
			condition: "vars.test == true",
			edges:     nil, // No edges injected
			state: func() *entity.State {
				s := entity.NewState()
				s.SetVar("test", true)
				return s
			},
			wantNextNodes: nil,
			wantBranch:    true,
			wantErr:       false,
		},
		{
			name:      "truthy path check",
			condition: "vars.count", // Just check if truthy
			edges: []map[string]any{
				{"id": "e1", "from": "branch", "to": "has_items", "label": "true"},
				{"id": "e2", "from": "branch", "to": "empty", "label": "false"},
			},
			state: func() *entity.State {
				s := entity.NewState()
				s.SetVar("count", 5)
				return s
			},
			wantNextNodes: []string{"has_items"},
			wantBranch:    true,
			wantErr:       false,
		},
		{
			name:      "falsy zero check",
			condition: "vars.count",
			edges: []map[string]any{
				{"id": "e1", "from": "branch", "to": "has_items", "label": "true"},
				{"id": "e2", "from": "branch", "to": "empty", "label": "false"},
			},
			state: func() *entity.State {
				s := entity.NewState()
				s.SetVar("count", 0)
				return s
			},
			wantNextNodes: []string{"empty"},
			wantBranch:    false,
			wantErr:       false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			executor := NewBranchExecutor()
			state := tt.state()

			// Build node config
			config := map[string]any{
				"condition": tt.condition,
			}
			if tt.edges != nil {
				config["_edges"] = tt.edges
			}

			node := &entity.Node{
				ID:     "test-branch",
				Type:   string(value.NodeTypeBranch),
				Name:   "Test Branch",
				Config: config,
			}

			result, err := executor.Execute(context.Background(), node, state)

			// Check error expectation
			if tt.wantErr {
				if err == nil && (result == nil || result.Error == nil) {
					t.Errorf("Expected error, got nil")
				}
				return
			}

			if err != nil {
				t.Errorf("Unexpected error: %v", err)
				return
			}

			if result.Error != nil {
				t.Errorf("Unexpected result error: %v", result.Error)
				return
			}

			// Check next nodes
			if len(result.NextNodes) != len(tt.wantNextNodes) {
				t.Errorf("NextNodes = %v, want %v", result.NextNodes, tt.wantNextNodes)
				return
			}

			// Verify all expected nodes are present
			nextNodesSet := make(map[string]bool)
			for _, n := range result.NextNodes {
				nextNodesSet[n] = true
			}
			for _, expected := range tt.wantNextNodes {
				if !nextNodesSet[expected] {
					t.Errorf("Expected next node %s not found in %v", expected, result.NextNodes)
				}
			}

			// Check output values
			if result.Output != nil {
				output, ok := result.Output.(map[string]any)
				if ok {
					branchTaken, _ := output["branch_taken"].(bool)
					if branchTaken != tt.wantBranch {
						t.Errorf("branch_taken = %v, want %v", branchTaken, tt.wantBranch)
					}
				}
			}
		})
	}
}

func TestBranchExecutor_ComplexConditions(t *testing.T) {
	executor := NewBranchExecutor()

	tests := []struct {
		name       string
		condition  string
		stateSetup func(*entity.State)
		wantBranch bool
	}{
		{
			name:      "nested object access",
			condition: `node.api.output.data.user.role == "admin"`,
			stateSetup: func(s *entity.State) {
				s.SetNodeOutput("api", map[string]any{
					"data": map[string]any{
						"user": map[string]any{
							"role": "admin",
						},
					},
				})
			},
			wantBranch: true,
		},
		{
			name:      "array index access",
			condition: "node.list.output.items.0 == 100",
			stateSetup: func(s *entity.State) {
				s.SetNodeOutput("list", map[string]any{
					"items": []any{100, 200, 300},
				})
			},
			wantBranch: true,
		},
		{
			name:      "inequality check",
			condition: `vars.env != "production"`,
			stateSetup: func(s *entity.State) {
				s.SetVar("env", "development")
			},
			wantBranch: true,
		},
		{
			name:      "null check for missing value",
			condition: "vars.optional == null",
			stateSetup: func(s *entity.State) {
				// Don't set vars.optional
			},
			wantBranch: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			state := entity.NewState()
			tt.stateSetup(state)

			node := &entity.Node{
				ID:   "branch",
				Type: string(value.NodeTypeBranch),
				Name: "Branch",
				Config: map[string]any{
					"condition": tt.condition,
					"_edges": []map[string]any{
						{"to": "true_path", "label": "true"},
						{"to": "false_path", "label": "false"},
					},
				},
			}

			result, err := executor.Execute(context.Background(), node, state)
			if err != nil {
				t.Fatalf("Unexpected error: %v", err)
			}

			output, ok := result.Output.(map[string]any)
			if !ok {
				t.Fatalf("Expected map output, got %T", result.Output)
			}

			branchTaken, _ := output["branch_taken"].(bool)
			if branchTaken != tt.wantBranch {
				t.Errorf("branch_taken = %v, want %v (condition: %s)", branchTaken, tt.wantBranch, tt.condition)
			}
		})
	}
}
