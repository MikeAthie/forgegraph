package store

import (
	"context"
	"errors"
	"testing"

	"github.com/forgegraph/engine/application/port"
)

type failingStore struct{}

func (f failingStore) Get(ctx context.Context, namespace, key string) (any, bool, error) {
	return nil, false, errors.New("read failed")
}
func (f failingStore) Set(ctx context.Context, namespace, key string, value any, ttlSeconds int) error {
	return errors.New("write failed")
}
func (f failingStore) Delete(ctx context.Context, namespace, key string) (bool, error) {
	return false, errors.New("delete failed")
}

func TestTieredMemoryStore_FallbackChain(t *testing.T) {
	tier1 := failingStore{}
	tier2 := NewInMemoryMemoryStore()
	tier3 := NewInMemoryMemoryStore()

	cfg := TieredConfig{
		Tier1Enabled: true,
		Tier2Enabled: true,
		Tier3Enabled: true,
		ReadOrder:    []int{1, 2, 3},
		WriteOrder:   []int{2},
	}

	store := NewTieredMemoryStore(tier1, tier2, tier3, cfg, NewTieredMetrics())
	ctx := context.Background()

	if err := tier2.Set(ctx, "ns", "key", "value", 0); err != nil {
		t.Fatalf("setup failed: %v", err)
	}

	val, found, err := store.Get(ctx, "ns", "key")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !found || val != "value" {
		t.Fatalf("expected tier2 value, got %v (found=%v)", val, found)
	}
}

func TestTieredMemoryStore_WriteToMultipleTiers(t *testing.T) {
	tier1 := NewInMemoryMemoryStore()
	tier2 := NewInMemoryMemoryStore()
	var tier3 port.MemoryStore

	cfg := TieredConfig{
		Tier1Enabled: true,
		Tier2Enabled: true,
		Tier3Enabled: false,
		ReadOrder:    []int{1, 2},
		WriteOrder:   []int{1, 2},
	}

	store := NewTieredMemoryStore(tier1, tier2, tier3, cfg, nil)
	ctx := context.Background()

	if err := store.Set(ctx, "ns", "key", "value", 0); err != nil {
		t.Fatalf("set failed: %v", err)
	}

	if val, found, _ := tier1.Get(ctx, "ns", "key"); !found || val != "value" {
		t.Fatalf("expected tier1 to have value")
	}
	if val, found, _ := tier2.Get(ctx, "ns", "key"); !found || val != "value" {
		t.Fatalf("expected tier2 to have value")
	}
}
