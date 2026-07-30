package entity

import "testing"

func TestStateSnapshot_DeepClonesNestedStructures(t *testing.T) {
	state := NewState()
	state.SetVar("execution_state", map[string]any{
		"goal": "launch",
		"content_assets": []any{
			map[string]any{"asset_id": "copy-1"},
		},
	})

	snapshot := state.Snapshot()
	varsPayload, ok := snapshot["vars.execution_state"].(map[string]any)
	if !ok {
		t.Fatalf("snapshot vars.execution_state type = %T, want map[string]any", snapshot["vars.execution_state"])
	}

	contentAssets, ok := varsPayload["content_assets"].([]any)
	if !ok {
		t.Fatalf("content_assets type = %T, want []any", varsPayload["content_assets"])
	}
	firstAsset, ok := contentAssets[0].(map[string]any)
	if !ok {
		t.Fatalf("first asset type = %T, want map[string]any", contentAssets[0])
	}

	firstAsset["asset_id"] = "copy-mutated"

	current, exists := state.Get("vars.execution_state")
	if !exists {
		t.Fatal("expected vars.execution_state to remain in state")
	}
	currentMap, ok := current.(map[string]any)
	if !ok {
		t.Fatalf("current vars.execution_state type = %T, want map[string]any", current)
	}
	currentAssets, ok := currentMap["content_assets"].([]any)
	if !ok {
		t.Fatalf("current content_assets type = %T, want []any", currentMap["content_assets"])
	}
	currentFirstAsset, ok := currentAssets[0].(map[string]any)
	if !ok {
		t.Fatalf("current first asset type = %T, want map[string]any", currentAssets[0])
	}
	if currentFirstAsset["asset_id"] != "copy-1" {
		t.Fatalf("state mutated through snapshot clone: asset_id = %v", currentFirstAsset["asset_id"])
	}
}

func TestStateDoesNotExposeOrRetainMutableValues(t *testing.T) {
	state := NewState()
	input := map[string]any{
		"nested": map[string]any{
			"items": []any{map[string]any{"name": "original"}},
		},
	}

	state.Set("payload", input)
	input["nested"].(map[string]any)["items"].([]any)[0].(map[string]any)["name"] = "changed-after-set"

	stored, ok := state.Get("payload")
	if !ok {
		t.Fatal("expected stored payload")
	}
	stored.(map[string]any)["nested"].(map[string]any)["items"].([]any)[0].(map[string]any)["name"] = "changed-after-get"

	again, ok := state.Get("payload")
	if !ok {
		t.Fatal("expected stored payload on second get")
	}
	name := again.(map[string]any)["nested"].(map[string]any)["items"].([]any)[0].(map[string]any)["name"]
	if name != "original" {
		t.Fatalf("state retained or exposed mutable value: name = %v, want original", name)
	}
}
