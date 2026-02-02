package store

import (
	"context"
	"fmt"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/forgegraph/engine/domain/entity"
	"github.com/redis/go-redis/v9"
)

func newTestRedisStore(t testing.TB) (*RedisMemoryStore, *miniredis.Miniredis, *InMemoryMemoryStore) {
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

func TestRedisMemoryStore_BatchGet(t *testing.T) {
	store, mini, _ := newTestRedisStore(t)
	defer mini.Close()

	ctx := context.Background()
	if err := store.Set(ctx, "ns", "a", "one", 0); err != nil {
		t.Fatalf("set failed: %v", err)
	}
	if err := store.Set(ctx, "ns", "b", "two", 0); err != nil {
		t.Fatalf("set failed: %v", err)
	}

	results, err := store.BatchGet(ctx, "ns", []string{"a", "b", "missing"})
	if err != nil {
		t.Fatalf("batch get failed: %v", err)
	}
	if len(results) != 2 {
		t.Fatalf("expected 2 results, got %d", len(results))
	}
	if results["a"] != "one" || results["b"] != "two" {
		t.Fatalf("unexpected results: %#v", results)
	}
}

func TestRedisMemoryStore_BatchGet_FallbackOnCircuitOpen(t *testing.T) {
	store, mini, fallback := newTestRedisStore(t)
	defer mini.Close()

	ctx := context.Background()

	// Set data in fallback
	if err := fallback.Set(ctx, "ns", "key1", "value1", 0); err != nil {
		t.Fatalf("fallback set failed: %v", err)
	}
	if err := fallback.Set(ctx, "ns", "key2", "value2", 0); err != nil {
		t.Fatalf("fallback set failed: %v", err)
	}

	// Force circuit open
	for i := 0; i < failureThreshold+1; i++ {
		store.recordFailure()
	}

	// Should use fallback
	results, err := store.BatchGet(ctx, "ns", []string{"key1", "key2", "key3"})

	if err != nil {
		t.Fatalf("expected no error with fallback, got: %v", err)
	}
	if results["key1"] != "value1" {
		t.Fatalf("expected value1, got %v", results["key1"])
	}
	if results["key2"] != "value2" {
		t.Fatalf("expected value2, got %v", results["key2"])
	}
	if _, exists := results["key3"]; exists {
		t.Fatal("key3 should not exist in results")
	}
}

func TestRedisMemoryStore_BatchGet_FallbackOnError(t *testing.T) {
	store, mini, fallback := newTestRedisStore(t)

	ctx := context.Background()

	// Set data in fallback
	if err := fallback.Set(ctx, "ns", "key1", "fallback-value", 0); err != nil {
		t.Fatalf("fallback set failed: %v", err)
	}

	// Close miniredis to trigger error
	mini.Close()

	results, err := store.BatchGet(ctx, "ns", []string{"key1"})

	if err != nil {
		t.Fatalf("expected fallback to succeed, got error: %v", err)
	}
	if results["key1"] != "fallback-value" {
		t.Fatalf("expected fallback-value, got %v", results["key1"])
	}
}

func TestRedisMemoryStore_BatchSet(t *testing.T) {
	store, mini, _ := newTestRedisStore(t)
	defer mini.Close()

	ctx := context.Background()

	items := map[string]any{
		"a": "one",
		"b": "two",
		"c": "three",
	}

	if err := store.BatchSet(ctx, "ns", items, 0); err != nil {
		t.Fatalf("batch set failed: %v", err)
	}

	// Verify values
	for key, expected := range items {
		val, found, err := store.Get(ctx, "ns", key)
		if err != nil {
			t.Fatalf("get %s failed: %v", key, err)
		}
		if !found {
			t.Fatalf("expected %s to be found", key)
		}
		if val != expected {
			t.Fatalf("expected %s=%v, got %v", key, expected, val)
		}
	}
}

func TestRedisMemoryStore_BatchSet_FallbackOnCircuitOpen(t *testing.T) {
	store, mini, fallback := newTestRedisStore(t)
	defer mini.Close()

	ctx := context.Background()

	// Force circuit open
	for i := 0; i < failureThreshold+1; i++ {
		store.recordFailure()
	}

	items := map[string]any{
		"key1": "value1",
	}

	// Should use fallback
	err := store.BatchSet(ctx, "ns", items, 0)

	if err != nil {
		t.Fatalf("expected no error with fallback, got: %v", err)
	}

	// Verify data in fallback
	val, found, _ := fallback.Get(ctx, "ns", "key1")
	if !found || val != "value1" {
		t.Fatalf("expected data in fallback, got found=%v val=%v", found, val)
	}
}

func TestRedisMemoryStore_BatchSet_FallbackOnError(t *testing.T) {
	store, mini, fallback := newTestRedisStore(t)

	ctx := context.Background()

	// Close miniredis to trigger error
	mini.Close()

	items := map[string]any{
		"key1": "fallback-value",
	}

	err := store.BatchSet(ctx, "ns", items, 0)

	if err != nil {
		t.Fatalf("expected fallback to succeed, got error: %v", err)
	}

	// Verify data in fallback
	val, found, _ := fallback.Get(ctx, "ns", "key1")
	if !found || val != "fallback-value" {
		t.Fatalf("expected data in fallback, got found=%v val=%v", found, val)
	}
}

func TestRedisMemoryStore_BatchSet_WithTTL(t *testing.T) {
	store, mini, _ := newTestRedisStore(t)
	defer mini.Close()

	ctx := context.Background()

	items := map[string]any{
		"expiring": "value",
	}

	if err := store.BatchSet(ctx, "ns", items, 1); err != nil {
		t.Fatalf("batch set failed: %v", err)
	}

	// Fast forward past TTL
	mini.FastForward(2 * time.Second)

	_, found, _ := store.Get(ctx, "ns", "expiring")
	if found {
		t.Fatal("expected key to expire")
	}
}

func TestRedisMemoryStore_CompressionRoundTrip(t *testing.T) {
	store, mini, _ := newTestRedisStore(t)
	defer mini.Close()

	ctx := context.Background()
	payload := map[string]any{
		"data": string(make([]byte, compressionThreshold+10)),
	}
	if err := store.Set(ctx, "ns", "big", payload, 0); err != nil {
		t.Fatalf("set failed: %v", err)
	}

	value, found, err := store.Get(ctx, "ns", "big")
	if err != nil {
		t.Fatalf("get failed: %v", err)
	}
	if !found {
		t.Fatalf("expected value to be found")
	}
	decoded, ok := value.(map[string]any)
	if !ok {
		t.Fatalf("expected map value, got %T", value)
	}
	if _, ok := decoded["data"]; !ok {
		t.Fatalf("expected data key in decoded payload")
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

func BenchmarkRedisMemoryStore_BatchGet(b *testing.B) {
	store, mini, _ := newTestRedisStore(b)
	defer mini.Close()

	ctx := context.Background()
	keys := make([]string, 10)
	for i := range keys {
		key := fmt.Sprintf("bench-%d", i)
		keys[i] = key
		if err := store.Set(ctx, "ns", key, "value", 0); err != nil {
			b.Fatalf("set failed: %v", err)
		}
	}

	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		if _, err := store.BatchGet(ctx, "ns", keys); err != nil {
			b.Fatalf("batch get failed: %v", err)
		}
	}
}

func BenchmarkRedisMemoryStore_GetMulti(b *testing.B) {
	store, mini, _ := newTestRedisStore(b)
	defer mini.Close()

	ctx := context.Background()
	keys := make([]string, 10)
	for i := range keys {
		key := fmt.Sprintf("bench-%d", i)
		keys[i] = key
		if err := store.Set(ctx, "ns", key, "value", 0); err != nil {
			b.Fatalf("set failed: %v", err)
		}
	}

	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		for _, key := range keys {
			if _, _, err := store.Get(ctx, "ns", key); err != nil {
				b.Fatalf("get failed: %v", err)
			}
		}
	}
}

func BenchmarkRedisMemoryStore_CompressLargeSet(b *testing.B) {
	store, mini, _ := newTestRedisStore(b)
	defer mini.Close()

	ctx := context.Background()
	payload := map[string]any{
		"data": strings.Repeat("x", compressionThreshold+2048),
	}

	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		if err := store.Set(ctx, "ns", "large", payload, 0); err != nil {
			b.Fatalf("set failed: %v", err)
		}
	}
}

func BenchmarkRedisMemoryStore_UncompressedSet(b *testing.B) {
	store, mini, _ := newTestRedisStore(b)
	defer mini.Close()

	ctx := context.Background()
	payload := map[string]any{
		"data": "small",
	}

	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		if err := store.Set(ctx, "ns", "small", payload, 0); err != nil {
			b.Fatalf("set failed: %v", err)
		}
	}
}
