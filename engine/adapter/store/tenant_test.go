package store

import (
	"context"
	"testing"

	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
)

func TestTenantIsolation_SeparateData(t *testing.T) {
	mini, err := miniredis.Run()
	if err != nil {
		t.Fatalf("miniredis start: %v", err)
	}
	defer mini.Close()

	cfg := RedisConfig{Addr: mini.Addr()}
	tenant1Store, err := NewRedisMemoryStore(cfg, "11111111-1111-1111-1111-111111111111", nil)
	if err != nil {
		t.Fatalf("tenant1 store: %v", err)
	}
	tenant2Store, err := NewRedisMemoryStore(cfg, "22222222-2222-2222-2222-222222222222", nil)
	if err != nil {
		t.Fatalf("tenant2 store: %v", err)
	}

	ctx := context.Background()
	if err := tenant1Store.Set(ctx, "ns", "key1", "secret-value", 0); err != nil {
		t.Fatalf("tenant1 set failed: %v", err)
	}

	val, found, err := tenant2Store.Get(ctx, "ns", "key1")
	if err != nil {
		t.Fatalf("tenant2 get failed: %v", err)
	}
	if found || val != nil {
		t.Fatalf("expected tenant2 not to see tenant1 data")
	}

	client := redis.NewClient(&redis.Options{Addr: mini.Addr()})
	defer client.Close()

	rawKey := tenant1Store.buildKey("ns", "key1")
	exists, err := client.Exists(ctx, rawKey).Result()
	if err != nil {
		t.Fatalf("exists failed: %v", err)
	}
	if exists != 1 {
		t.Fatalf("expected raw key to exist")
	}
}

func TestTenantIsolation_CannotAccessOtherTenantKeys(t *testing.T) {
	mini, err := miniredis.Run()
	if err != nil {
		t.Fatalf("miniredis start: %v", err)
	}
	defer mini.Close()

	cfg := RedisConfig{Addr: mini.Addr()}
	store, err := NewRedisMemoryStore(cfg, "11111111-1111-1111-1111-111111111111", nil)
	if err != nil {
		t.Fatalf("store: %v", err)
	}

	ctx := context.Background()
	_, found, _ := store.Get(ctx, "tenant:22222222-2222-2222-2222-222222222222:memory:ns", "key")
	if found {
		t.Fatalf("expected crafted namespace to not leak data")
	}
}

func TestTenantIsolation_DeleteOnlyOwnKeys(t *testing.T) {
	mini, err := miniredis.Run()
	if err != nil {
		t.Fatalf("miniredis start: %v", err)
	}
	defer mini.Close()

	cfg := RedisConfig{Addr: mini.Addr()}
	tenant1Store, err := NewRedisMemoryStore(cfg, "11111111-1111-1111-1111-111111111111", nil)
	if err != nil {
		t.Fatalf("tenant1 store: %v", err)
	}
	tenant2Store, err := NewRedisMemoryStore(cfg, "22222222-2222-2222-2222-222222222222", nil)
	if err != nil {
		t.Fatalf("tenant2 store: %v", err)
	}

	ctx := context.Background()
	_ = tenant1Store.Set(ctx, "ns", "key", "tenant1-value", 0)
	_ = tenant2Store.Set(ctx, "ns", "key", "tenant2-value", 0)

	deleted, err := tenant1Store.Delete(ctx, "ns", "key")
	if err != nil || !deleted {
		t.Fatalf("tenant1 delete failed: %v", err)
	}

	val, found, _ := tenant2Store.Get(ctx, "ns", "key")
	if !found || val != "tenant2-value" {
		t.Fatalf("expected tenant2 value to remain")
	}
}
