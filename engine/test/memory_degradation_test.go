package test

import (
	"context"
	"testing"

	"github.com/alicebob/miniredis/v2"
	"github.com/forgegraph/engine/adapter/store"
)

func TestGracefulDegradation_RedisDown(t *testing.T) {
	mini, err := miniredis.Run()
	if err != nil {
		t.Fatalf("miniredis start: %v", err)
	}

	fallback := store.NewInMemoryMemoryStore()
	redisStore, err := store.NewRedisMemoryStore(
		store.RedisConfig{Addr: mini.Addr()},
		"11111111-1111-1111-1111-111111111111",
		fallback,
	)
	if err != nil {
		mini.Close()
		t.Fatalf("new redis store: %v", err)
	}

	ctx := context.Background()
	if err := redisStore.Set(ctx, "ns", "key-up", "value-up", 0); err != nil {
		mini.Close()
		t.Fatalf("set while up failed: %v", err)
	}

	mini.Close()

	if err := redisStore.Set(ctx, "ns", "key-down", "value-down", 0); err != nil {
		t.Fatalf("set while down failed: %v", err)
	}

	val, found, err := fallback.Get(ctx, "ns", "key-down")
	if err != nil {
		t.Fatalf("fallback get failed: %v", err)
	}
	if !found || val != "value-down" {
		t.Fatalf("expected fallback value, got %v (found=%v)", val, found)
	}
}
