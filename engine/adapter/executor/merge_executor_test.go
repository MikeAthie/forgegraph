package executor

import (
	"context"
	"testing"

	"github.com/forgegraph/engine/domain/entity"
	"github.com/forgegraph/engine/domain/value"
)

func TestMergeExecutor_NodeType(t *testing.T) {
	executor := NewMergeExecutor()
	if executor.NodeType() != string(value.NodeTypeMerge) {
		t.Errorf("NodeType() = %v, want %v", executor.NodeType(), value.NodeTypeMerge)
	}
}

func TestMergeExecutor_Execute(t *testing.T) {
	tests := []struct {
		name           string
		strategy       string
		inputNodes     []string
		stateSetup     func(*entity.State)
		wantMergedKeys []string
		wantSources    []string
	}{
		{
			name:       "namespaced strategy - two branches",
			strategy:   "namespaced",
			inputNodes: []string{"branch_a", "branch_b"},
			stateSetup: func(s *entity.State) {
				s.SetNodeOutput("branch_a", map[string]any{"result": "A", "value": 1})
				s.SetNodeOutput("branch_b", map[string]any{"result": "B", "value": 2})
			},
			wantMergedKeys: []string{"branch_a", "branch_b"},
			wantSources:    []string{"branch_a", "branch_b"},
		},
		{
			name:       "namespaced strategy - default when not specified",
			strategy:   "", // Should default to namespaced
			inputNodes: []string{"node_1", "node_2"},
			stateSetup: func(s *entity.State) {
				s.SetNodeOutput("node_1", "output_1")
				s.SetNodeOutput("node_2", "output_2")
			},
			wantMergedKeys: []string{"node_1", "node_2"},
			wantSources:    []string{"node_1", "node_2"},
		},
		{
			name:       "last_write_wins strategy - merges map keys",
			strategy:   "last_write_wins",
			inputNodes: []string{"step_1", "step_2"},
			stateSetup: func(s *entity.State) {
				s.SetNodeOutput("step_1", map[string]any{"key": "first", "a": 1})
				s.SetNodeOutput("step_2", map[string]any{"key": "second", "b": 2})
			},
			wantMergedKeys: []string{"key", "a", "b"}, // Merged map keys
			wantSources:    []string{"step_1", "step_2"},
		},
		{
			name:       "last_write_wins - later overwrites earlier",
			strategy:   "last_write_wins",
			inputNodes: []string{"first", "second"},
			stateSetup: func(s *entity.State) {
				s.SetNodeOutput("first", map[string]any{"shared": "from_first"})
				s.SetNodeOutput("second", map[string]any{"shared": "from_second"})
			},
			wantMergedKeys: []string{"shared"},
			wantSources:    []string{"first", "second"},
		},
		{
			name:       "skipped predecessor - only collects available",
			strategy:   "namespaced",
			inputNodes: []string{"branch_a", "branch_b", "branch_c"},
			stateSetup: func(s *entity.State) {
				s.SetNodeOutput("branch_a", map[string]any{"result": "A"})
				// branch_b was skipped (no output)
				s.SetNodeOutput("branch_c", map[string]any{"result": "C"})
			},
			wantMergedKeys: []string{"branch_a", "branch_c"},
			wantSources:    []string{"branch_a", "branch_c"},
		},
		{
			name:       "all predecessors skipped - empty merge",
			strategy:   "namespaced",
			inputNodes: []string{"skip_1", "skip_2"},
			stateSetup: func(s *entity.State) {
				// No outputs set - all predecessors were skipped
			},
			wantMergedKeys: []string{},
			wantSources:    []string{},
		},
		{
			name:       "no input nodes specified",
			strategy:   "namespaced",
			inputNodes: nil,
			stateSetup: func(s *entity.State) {
				s.SetNodeOutput("some_node", "value")
			},
			wantMergedKeys: []string{},
			wantSources:    []string{},
		},
		{
			name:       "non-map output with last_write_wins",
			strategy:   "last_write_wins",
			inputNodes: []string{"string_node", "map_node"},
			stateSetup: func(s *entity.State) {
				s.SetNodeOutput("string_node", "plain string")
				s.SetNodeOutput("map_node", map[string]any{"key": "value"})
			},
			wantMergedKeys: []string{"string_node", "key"}, // string goes under node ID
			wantSources:    []string{"string_node", "map_node"},
		},
		{
			name:       "single input node",
			strategy:   "namespaced",
			inputNodes: []string{"only_one"},
			stateSetup: func(s *entity.State) {
				s.SetNodeOutput("only_one", map[string]any{"data": "value"})
			},
			wantMergedKeys: []string{"only_one"},
			wantSources:    []string{"only_one"},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			executor := NewMergeExecutor()
			state := entity.NewState()
			tt.stateSetup(state)

			// Build node config
			config := map[string]any{}
			if tt.strategy != "" {
				config["merge_strategy"] = tt.strategy
			}
			if tt.inputNodes != nil {
				config["_input_nodes"] = tt.inputNodes
			}

			node := &entity.Node{
				ID:     "test-merge",
				Type:   string(value.NodeTypeMerge),
				Name:   "Test Merge",
				Config: config,
			}

			result, err := executor.Execute(context.Background(), node, state)

			if err != nil {
				t.Fatalf("Unexpected error: %v", err)
			}

			if result.Error != nil {
				t.Fatalf("Unexpected result error: %v", result.Error)
			}

			// Verify output structure
			output, ok := result.Output.(map[string]any)
			if !ok {
				t.Fatalf("Expected map output, got %T", result.Output)
			}

			// Check merged keys
			merged, ok := output["merged"].(map[string]any)
			if !ok {
				t.Fatalf("Expected merged to be map, got %T", output["merged"])
			}

			if len(merged) != len(tt.wantMergedKeys) {
				t.Errorf("merged has %d keys, want %d. Keys: %v", len(merged), len(tt.wantMergedKeys), getKeys(merged))
			}

			for _, key := range tt.wantMergedKeys {
				if _, exists := merged[key]; !exists {
					t.Errorf("Expected key %q not found in merged: %v", key, getKeys(merged))
				}
			}

			// Check sources
			sources, ok := output["sources"].([]string)
			if !ok {
				t.Fatalf("Expected sources to be []string, got %T", output["sources"])
			}

			if len(sources) != len(tt.wantSources) {
				t.Errorf("sources = %v, want %v", sources, tt.wantSources)
			}

			// Verify all expected sources are present
			sourcesSet := make(map[string]bool)
			for _, s := range sources {
				sourcesSet[s] = true
			}
			for _, expected := range tt.wantSources {
				if !sourcesSet[expected] {
					t.Errorf("Expected source %q not found in %v", expected, sources)
				}
			}

			// Check strategy in output
			strategyOut, _ := output["strategy"].(string)
			expectedStrategy := tt.strategy
			if expectedStrategy == "" {
				expectedStrategy = "namespaced"
			}
			if strategyOut != expectedStrategy {
				t.Errorf("strategy = %q, want %q", strategyOut, expectedStrategy)
			}
		})
	}
}

func TestMergeExecutor_InputNodesFromAnySlice(t *testing.T) {
	// Test that input nodes can be parsed from []any (JSON unmarshaling case)
	executor := NewMergeExecutor()
	state := entity.NewState()
	state.SetNodeOutput("node_1", "output_1")
	state.SetNodeOutput("node_2", "output_2")

	node := &entity.Node{
		ID:   "test-merge",
		Type: string(value.NodeTypeMerge),
		Name: "Test Merge",
		Config: map[string]any{
			"merge_strategy": "namespaced",
			"_input_nodes":   []any{"node_1", "node_2"}, // []any instead of []string
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

	sources, ok := output["sources"].([]string)
	if !ok {
		t.Fatalf("Expected sources to be []string, got %T", output["sources"])
	}

	if len(sources) != 2 {
		t.Errorf("Expected 2 sources, got %d: %v", len(sources), sources)
	}
}

func TestMergeExecutor_LastWriteWinsOrder(t *testing.T) {
	// Verify that last_write_wins respects order
	executor := NewMergeExecutor()
	state := entity.NewState()
	state.SetNodeOutput("first", map[string]any{"value": 1})
	state.SetNodeOutput("second", map[string]any{"value": 2})
	state.SetNodeOutput("third", map[string]any{"value": 3})

	node := &entity.Node{
		ID:   "test-merge",
		Type: string(value.NodeTypeMerge),
		Name: "Test Merge",
		Config: map[string]any{
			"merge_strategy": "last_write_wins",
			"_input_nodes":   []string{"first", "second", "third"},
		},
	}

	result, err := executor.Execute(context.Background(), node, state)
	if err != nil {
		t.Fatalf("Unexpected error: %v", err)
	}

	output := result.Output.(map[string]any)
	merged := output["merged"].(map[string]any)

	// The last node's value should win
	if merged["value"] != 3 {
		t.Errorf("Expected value=3 (from third), got %v", merged["value"])
	}
}

// Helper to get map keys
func getKeys(m map[string]any) []string {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	return keys
}
