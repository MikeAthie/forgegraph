package store

import (
	"context"
	"fmt"
	"sync"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/forgegraph/engine/domain/entity"
	"github.com/redis/go-redis/v9"
)

func newTestRedisStore(t *testing.T) (*RedisMemoryStore, *miniredis.Miniredis, *InMemoryMemoryStore) {
	t.Helper()

	mini, err := miniredis.Run()
	if err != nil {
		t.Fatalf("miniredis start: %v", err)
	}

	fallback := NewInMemoryMemoryStore()
	store, err := NewRedisMemoryStore(RedisConfig{Addr: mini.Addr()}, "11111111-1111-1111-1111-111111111111", fallback)
	if err != nil {
		mini.Close()
		t.Fatalf("new redis store: %v", err)
	}

	return store, mini, fallback
}

func TestRedisMemoryStore_SetGet(t *testing.T) {
	store, mini, _ := newTestRedisStore(t)
	defer mini.Close()

	ctx := context.Background()
	if err := store.Set(ctx, "ns", "key", map[string]any{"foo": "bar"}, 0); err != nil {
		t.Fatalf("set failed: %v", err)
	}

	value, found, err := store.Get(ctx, "ns", "key")
	if err != nil {
		t.Fatalf("get failed: %v", err)
	}
	if !found {
		t.Fatalf("expected value to be found")
	}

	parsed, ok := value.(map[string]any)
	if !ok {
		t.Fatalf("expected map[string]any, got %T", value)
	}
	if parsed["foo"] != "bar" {
		t.Fatalf("unexpected value: %#v", parsed)
	}
}

func TestRedisMemoryStore_TTLExpiration(t *testing.T) {
	store, mini, _ := newTestRedisStore(t)
	defer mini.Close()

	ctx := context.Background()
	if err := store.Set(ctx, "ns", "key", "value", 1); err != nil {
		t.Fatalf("set failed: %v", err)
	}

	mini.FastForward(2 * time.Second)

	_, found, err := store.Get(ctx, "ns", "key")
	if err != nil {
		t.Fatalf("get failed: %v", err)
	}
	if found {
		t.Fatalf("expected key to expire")
	}
}

func TestRedisMemoryStore_CircuitBreaker(t *testing.T) {
	store, mini, _ := newTestRedisStore(t)
	defer mini.Close()

	for i := 0; i < failureThreshold; i++ {
		store.recordFailure()
	}

	if !store.circuitOpen.Load() {
		t.Fatalf("expected circuit to be open after failures")
	}

	store.lastFailure.Store(time.Now().Add(-circuitOpenDuration - time.Second))
	if store.isCircuitOpen() {
		t.Fatalf("expected circuit to close after open duration")
	}
	if store.failureCount.Load() != 0 {
		t.Fatalf("expected failure count reset, got %d", store.failureCount.Load())
	}
}

func TestRedisMemoryStore_Fallback(t *testing.T) {
	store, mini, fallback := newTestRedisStore(t)

	ctx := context.Background()
	if err := fallback.Set(ctx, "ns", "key", "fallback", 0); err != nil {
		t.Fatalf("fallback set failed: %v", err)
	}

	mini.Close()

	value, found, err := store.Get(ctx, "ns", "key")
	if err != nil {
		t.Fatalf("expected fallback get without error, got %v", err)
	}
	if !found {
		t.Fatalf("expected fallback value to be found")
	}
	if value != "fallback" {
		t.Fatalf("unexpected fallback value: %v", value)
	}
}

func TestRedisMemoryStore_TenantIsolation(t *testing.T) {
	store, mini, _ := newTestRedisStore(t)
	defer mini.Close()

	ctx := context.Background()
	if err := store.Set(ctx, "ns", "key", "value", 0); err != nil {
		t.Fatalf("set failed: %v", err)
	}

	client := redis.NewClient(&redis.Options{Addr: mini.Addr()})
	defer client.Close()

	rawKey := store.buildKey("ns", "key")
	exists, err := client.Exists(ctx, rawKey).Result()
	if err != nil {
		t.Fatalf("exists failed: %v", err)
	}
	if exists != 1 {
		t.Fatalf("expected raw key to exist, got %d", exists)
	}
}

func TestRedisMemoryStore_ConcurrentAccess(t *testing.T) {
	store, mini, _ := newTestRedisStore(t)
	defer mini.Close()

	ctx := context.Background()
	const workers = 25
	const iterations = 20

	var wg sync.WaitGroup
	errCh := make(chan error, workers*iterations)

	for i := 0; i < workers; i++ {
		wg.Add(1)
		go func(worker int) {
			defer wg.Done()
			for j := 0; j < iterations; j++ {
				key := fmt.Sprintf("key-%d-%d", worker, j)
				if err := store.Set(ctx, "ns", key, "value", 0); err != nil {
					errCh <- fmt.Errorf("set failed: %w", err)
					return
				}
				_, found, err := store.Get(ctx, "ns", key)
				if err != nil {
					errCh <- fmt.Errorf("get failed: %w", err)
					return
				}
				if !found {
					errCh <- fmt.Errorf("missing key %s", key)
					return
				}
			}
		}(i)
	}

	wg.Wait()
	close(errCh)

	for err := range errCh {
		t.Error(err)
	}
}

func TestRedisMemoryStore_SummaryAndFacts(t *testing.T) {
	store, mini, _ := newTestRedisStore(t)
	defer mini.Close()

	ctx := context.Background()
	summary := &entity.Summary{
		ID:          "summary-1",
		Content:     "recap",
		SourceCount: 3,
		CreatedAt:   time.Now().UTC(),
		FactsExtracted: []entity.Fact{
			{Key: "owner", Value: "Ada", Confidence: 0.9},
		},
	}

	if err := store.StoreSummary(ctx, store.tenantID, "run-1", summary, 60); err != nil {
		t.Fatalf("StoreSummary failed: %v", err)
	}

	loaded, found, err := store.GetSummary(ctx, store.tenantID, "run-1")
	if err != nil {
		t.Fatalf("GetSummary failed: %v", err)
	}
	if !found || loaded == nil || loaded.Content != "recap" {
		t.Fatalf("unexpected summary: %#v", loaded)
	}

	if err := store.StoreFacts(ctx, store.tenantID, "run-1", summary.FactsExtracted, 60); err != nil {
		t.Fatalf("StoreFacts failed: %v", err)
	}

	fact, found, err := store.GetFact(ctx, store.tenantID, "run-1", "owner")
	if err != nil {
		t.Fatalf("GetFact failed: %v", err)
	}
	if !found || fact == nil || fact.Value != "Ada" {
		t.Fatalf("unexpected fact: %#v", fact)
	}

	currentKey := store.buildSummaryKey("run-1", "current")
	if !mini.Exists(currentKey) {
		t.Fatalf("expected current summary key to exist")
	}
}

func TestRedisMemoryStore_SummaryVersionRetention(t *testing.T) {
	store, mini, _ := newTestRedisStore(t)
	defer mini.Close()

	ctx := context.Background()
	for i := 1; i <= 6; i++ {
		summary := &entity.Summary{
			ID:          fmt.Sprintf("summary-%d", i),
			Content:     fmt.Sprintf("recap-%d", i),
			SourceCount: i,
			CreatedAt:   time.Now().UTC(),
		}
		if err := store.StoreSummary(ctx, store.tenantID, "run-2", summary, 60); err != nil {
			t.Fatalf("StoreSummary failed: %v", err)
		}
	}

	if mini.Exists(store.buildSummaryKey("run-2", "v1")) {
		t.Fatalf("expected v1 to be evicted after 6 summaries")
	}
	if !mini.Exists(store.buildSummaryKey("run-2", "v2")) {
		t.Fatalf("expected v2 to remain")
	}
	if !mini.Exists(store.buildSummaryKey("run-2", "v6")) {
		t.Fatalf("expected v6 to remain")
	}
}
