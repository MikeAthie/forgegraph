package executor

import (
	"testing"
	"time"
)

func TestPromptCache_GetSetAndExpiry(t *testing.T) {
	cache := NewPromptCache(4)
	now := time.Now()

	cache.Set("key-1", &LLMResponse{Content: "hello"}, time.Second, now)

	if _, ok := cache.Get("missing", now); ok {
		t.Fatalf("expected missing key lookup to return false")
	}

	value, ok := cache.Get("key-1", now.Add(500*time.Millisecond))
	if !ok {
		t.Fatalf("expected key to be present before ttl expiry")
	}
	if value.Content != "hello" {
		t.Fatalf("content = %q, want %q", value.Content, "hello")
	}

	if _, ok := cache.Get("key-1", now.Add(2*time.Second)); ok {
		t.Fatalf("expected key to expire after ttl")
	}
}

func TestPromptCache_EvictsLeastRecentlyUsed(t *testing.T) {
	cache := NewPromptCache(2)
	now := time.Now()

	cache.Set("a", &LLMResponse{Content: "a"}, time.Minute, now)
	cache.Set("b", &LLMResponse{Content: "b"}, time.Minute, now)
	if _, ok := cache.Get("a", now); !ok {
		t.Fatalf("expected key a to exist")
	}

	cache.Set("c", &LLMResponse{Content: "c"}, time.Minute, now)

	if _, ok := cache.Get("b", now); ok {
		t.Fatalf("expected key b to be evicted as least recently used")
	}
	if _, ok := cache.Get("a", now); !ok {
		t.Fatalf("expected key a to remain in cache")
	}
	if _, ok := cache.Get("c", now); !ok {
		t.Fatalf("expected key c to be in cache")
	}
}
