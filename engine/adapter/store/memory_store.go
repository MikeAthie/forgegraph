package store

import (
	"context"
	"sync"
	"time"
)

type memoryEntry struct {
	value     any
	expiresAt time.Time
	hasExpiry bool
}

// InMemoryMemoryStore is a thread-safe in-memory implementation of MemoryStore.
type InMemoryMemoryStore struct {
	mu      sync.RWMutex
	entries map[string]memoryEntry
}

// NewInMemoryMemoryStore creates a new in-memory memory store.
func NewInMemoryMemoryStore() *InMemoryMemoryStore {
	return &InMemoryMemoryStore{
		entries: make(map[string]memoryEntry),
	}
}

// Get retrieves a value by namespace and key.
func (s *InMemoryMemoryStore) Get(ctx context.Context, namespace, key string) (value any, found bool, err error) {
	_ = ctx
	compositeKey := buildCompositeKey(namespace, key)

	s.mu.RLock()
	entry, ok := s.entries[compositeKey]
	s.mu.RUnlock()

	if !ok {
		return nil, false, nil
	}

	if entry.hasExpiry && time.Now().After(entry.expiresAt) {
		s.mu.Lock()
		delete(s.entries, compositeKey)
		s.mu.Unlock()
		return nil, false, nil
	}

	return entry.value, true, nil
}

// Set stores a value with optional TTL (seconds). ttlSeconds <= 0 means no expiry.
func (s *InMemoryMemoryStore) Set(ctx context.Context, namespace, key string, value any, ttlSeconds int) error {
	_ = ctx
	compositeKey := buildCompositeKey(namespace, key)

	entry := memoryEntry{value: value}
	if ttlSeconds > 0 {
		entry.hasExpiry = true
		entry.expiresAt = time.Now().Add(time.Duration(ttlSeconds) * time.Second)
	}

	s.mu.Lock()
	s.entries[compositeKey] = entry
	s.mu.Unlock()
	return nil
}

// Delete removes a key/value entry. Returns true if an entry was deleted.
func (s *InMemoryMemoryStore) Delete(ctx context.Context, namespace, key string) (bool, error) {
	_ = ctx
	compositeKey := buildCompositeKey(namespace, key)

	s.mu.Lock()
	_, existed := s.entries[compositeKey]
	delete(s.entries, compositeKey)
	s.mu.Unlock()

	return existed, nil
}

func buildCompositeKey(namespace, key string) string {
	if namespace == "" {
		return key
	}
	return namespace + ":" + key
}
