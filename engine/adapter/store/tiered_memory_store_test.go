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

func TestTieredMemoryStore_PartialFailure(t *testing.T) {
	tier1 := NewInMemoryMemoryStore()
	tier2 := failingStore{}

	cfg := TieredConfig{
		Tier1Enabled: true,
		Tier2Enabled: true,
		Tier3Enabled: false,
		ReadOrder:    []int{1, 2},
		WriteOrder:   []int{1, 2},
	}

	store := NewTieredMemoryStore(tier1, tier2, nil, cfg, NewTieredMetrics())
	ctx := context.Background()

	err := store.Set(ctx, "ns", "key", "value", 0)

	// Should return error
	if err == nil {
		t.Fatal("expected error for partial failure")
	}

	// Should be TieredWriteError
	tieredErr, ok := err.(*TieredWriteError)
	if !ok {
		t.Fatalf("expected TieredWriteError, got %T", err)
	}

	// Should indicate partial success
	if !tieredErr.IsPartialSuccess() {
		t.Fatal("expected partial success")
	}

	// Check tier 1 succeeded
	found := false
	for _, tier := range tieredErr.TierSuccess {
		if tier == 1 {
			found = true
			break
		}
	}
	if !found {
		t.Fatal("expected tier 1 in success list")
	}

	// Check tier 2 failed
	failedTiers := tieredErr.FailedTiers()
	found = false
	for _, tier := range failedTiers {
		if tier == 2 {
			found = true
			break
		}
	}
	if !found {
		t.Fatal("expected tier 2 in failed list")
	}

	// Data should be in tier 1
	val, ok, _ := tier1.Get(ctx, "ns", "key")
	if !ok || val != "value" {
		t.Fatal("expected value in tier 1")
	}
}

func TestTieredMemoryStore_AllFailed(t *testing.T) {
	tier1 := failingStore{}
	tier2 := failingStore{}

	cfg := TieredConfig{
		Tier1Enabled: true,
		Tier2Enabled: true,
		Tier3Enabled: false,
		ReadOrder:    []int{1, 2},
		WriteOrder:   []int{1, 2},
	}

	store := NewTieredMemoryStore(tier1, tier2, nil, cfg, NewTieredMetrics())
	ctx := context.Background()

	err := store.Set(ctx, "ns", "key", "value", 0)

	if err == nil {
		t.Fatal("expected error")
	}

	tieredErr, ok := err.(*TieredWriteError)
	if !ok {
		t.Fatalf("expected TieredWriteError, got %T", err)
	}

	if tieredErr.IsPartialSuccess() {
		t.Fatal("expected no partial success")
	}

	if len(tieredErr.TierErrors) != 2 {
		t.Fatalf("expected 2 tier errors, got %d", len(tieredErr.TierErrors))
	}
}

func TestIsTieredPartialSuccess(t *testing.T) {
	partialErr := &TieredWriteError{
		TierErrors:  map[int]error{2: errors.New("failed")},
		TierSuccess: []int{1},
	}
	if !IsTieredPartialSuccess(partialErr) {
		t.Fatal("expected partial success")
	}

	fullErr := &TieredWriteError{
		TierErrors:  map[int]error{1: errors.New("failed"), 2: errors.New("failed")},
		TierSuccess: []int{},
	}
	if IsTieredPartialSuccess(fullErr) {
		t.Fatal("expected not partial success")
	}

	otherErr := errors.New("random error")
	if IsTieredPartialSuccess(otherErr) {
		t.Fatal("expected false for non-tiered error")
	}
}

func TestTieredWriteError_Error(t *testing.T) {
	err := &TieredWriteError{
		Operation:   "set",
		Namespace:   "ns",
		Key:         "key",
		TierErrors:  map[int]error{2: errors.New("connection refused")},
		TierSuccess: []int{1},
	}

	msg := err.Error()
	if msg == "" {
		t.Fatal("expected non-empty error message")
	}

	// Check it contains relevant info
	if !contains(msg, "set") {
		t.Error("expected operation in message")
	}
	if !contains(msg, "tier2") {
		t.Error("expected tier number in message")
	}
}

func TestTieredMemoryStore_DeletePartialFailure(t *testing.T) {
	tier1 := NewInMemoryMemoryStore()
	tier2 := failingStore{}

	cfg := TieredConfig{
		Tier1Enabled: true,
		Tier2Enabled: true,
		Tier3Enabled: false,
		WriteOrder:   []int{1, 2},
	}

	store := NewTieredMemoryStore(tier1, tier2, nil, cfg, NewTieredMetrics())
	ctx := context.Background()

	// Set up data in tier1
	_ = tier1.Set(ctx, "ns", "key", "value", 0)

	deleted, err := store.Delete(ctx, "ns", "key")

	// Should return error
	if err == nil {
		t.Fatal("expected error for partial failure")
	}

	// Should be TieredWriteError
	tieredErr, ok := err.(*TieredWriteError)
	if !ok {
		t.Fatalf("expected TieredWriteError, got %T", err)
	}

	// Should indicate partial success
	if !tieredErr.IsPartialSuccess() {
		t.Fatal("expected partial success")
	}

	// Should have deleted from tier 1
	if !deleted {
		t.Fatal("expected deleted to be true")
	}

	// Verify it's actually deleted from tier 1
	_, found, _ := tier1.Get(ctx, "ns", "key")
	if found {
		t.Fatal("expected key to be deleted from tier 1")
	}
}

func contains(s, substr string) bool {
	return len(s) >= len(substr) && (s == substr || len(s) > 0 && containsAt(s, substr, 0))
}

func containsAt(s, substr string, start int) bool {
	for i := start; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}
