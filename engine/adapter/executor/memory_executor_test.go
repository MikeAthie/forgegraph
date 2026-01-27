package executor

import (
	"context"
	"testing"

	"github.com/forgegraph/engine/adapter/store"
	"github.com/forgegraph/engine/domain/entity"
	"github.com/forgegraph/engine/domain/value"
)

func TestMemoryExecutor_NodeType(t *testing.T) {
	executor := NewMemoryExecutor(store.NewInMemoryMemoryStore())
	if executor.NodeType() != string(value.NodeTypeMemory) {
		t.Errorf("NodeType() = %v, want %v", executor.NodeType(), string(value.NodeTypeMemory))
	}
}

func TestMemoryExecutor_SetGetDelete(t *testing.T) {
	memStore := store.NewInMemoryMemoryStore()
	executor := NewMemoryExecutor(memStore)
	state := entity.NewState()

	setNode := &entity.Node{
		ID:   "mem_set",
		Type: string(value.NodeTypeMemory),
		Name: "Memory Set",
		Config: map[string]any{
			"action": "set",
			"key":    "greeting",
			"value":  "hello",
		},
	}

	result, err := executor.Execute(context.Background(), setNode, state)
	if err != nil || result.Error != nil {
		t.Fatalf("Expected set to succeed, got err=%v resultErr=%v", err, result.Error)
	}

	getNode := &entity.Node{
		ID:   "mem_get",
		Type: string(value.NodeTypeMemory),
		Name: "Memory Get",
		Config: map[string]any{
			"action": "get",
			"key":    "greeting",
		},
	}

	result, err = executor.Execute(context.Background(), getNode, state)
	if err != nil || result.Error != nil {
		t.Fatalf("Expected get to succeed, got err=%v resultErr=%v", err, result.Error)
	}
	output, ok := result.Output.(map[string]any)
	if !ok {
		t.Fatalf("Expected output map, got %T", result.Output)
	}
	if output["found"] != true || output["value"] != "hello" {
		t.Errorf("Expected found=true value=hello, got %v", output)
	}

	deleteNode := &entity.Node{
		ID:   "mem_delete",
		Type: string(value.NodeTypeMemory),
		Name: "Memory Delete",
		Config: map[string]any{
			"action": "delete",
			"key":    "greeting",
		},
	}

	result, err = executor.Execute(context.Background(), deleteNode, state)
	if err != nil || result.Error != nil {
		t.Fatalf("Expected delete to succeed, got err=%v resultErr=%v", err, result.Error)
	}
	output, ok = result.Output.(map[string]any)
	if !ok {
		t.Fatalf("Expected output map, got %T", result.Output)
	}
	if output["deleted"] != true {
		t.Errorf("Expected deleted=true, got %v", output)
	}
}
