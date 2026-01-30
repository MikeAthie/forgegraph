package store

import (
	"context"
	"log"
	"sync"

	"github.com/forgegraph/engine/application/port"
)

// TieredMemoryStore composes multiple memory stores with fallback behavior.
type TieredMemoryStore struct {
	tier1   port.MemoryStore
	tier2   port.MemoryStore
	tier3   port.MemoryStore
	config  TieredConfig
	metrics *TieredMetrics
}

// TieredConfig configures which tiers are enabled and the read/write order.
type TieredConfig struct {
	Tier1Enabled bool
	Tier2Enabled bool
	Tier3Enabled bool
	ReadOrder    []int
	WriteOrder   []int
}

// TieredMetrics tracks tier hits/misses for observability.
type TieredMetrics struct {
	mu     sync.Mutex
	hits   map[int]int64
	misses map[int]int64
}

// NewTieredMetrics initializes metrics tracking.
func NewTieredMetrics() *TieredMetrics {
	return &TieredMetrics{
		hits:   make(map[int]int64),
		misses: make(map[int]int64),
	}
}

func (m *TieredMetrics) RecordHit(tier int) {
	if m == nil {
		return
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	m.hits[tier]++
}

func (m *TieredMetrics) RecordMiss(tier int) {
	if m == nil {
		return
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	m.misses[tier]++
}

// NewTieredMemoryStore creates a new tiered memory store.
func NewTieredMemoryStore(tier1, tier2, tier3 port.MemoryStore, config TieredConfig, metrics *TieredMetrics) *TieredMemoryStore {
	if len(config.ReadOrder) == 0 {
		config.ReadOrder = []int{1, 2, 3}
	}
	if len(config.WriteOrder) == 0 {
		config.WriteOrder = []int{2}
	}
	return &TieredMemoryStore{
		tier1:   tier1,
		tier2:   tier2,
		tier3:   tier3,
		config:  config,
		metrics: metrics,
	}
}

// Get checks tiers in ReadOrder and returns the first hit.
func (s *TieredMemoryStore) Get(ctx context.Context, namespace, key string) (any, bool, error) {
	for _, tier := range s.config.ReadOrder {
		store := s.getTierStore(tier)
		if store == nil {
			continue
		}
		val, found, err := store.Get(ctx, namespace, key)
		if err != nil {
			log.Printf("tiered memory read error (tier=%d namespace=%s key=%s): %v", tier, namespace, key, err)
			s.metrics.RecordMiss(tier)
			continue
		}
		if found {
			s.metrics.RecordHit(tier)
			return val, true, nil
		}
		s.metrics.RecordMiss(tier)
	}
	return nil, false, nil
}

// Set writes to all tiers in WriteOrder.
func (s *TieredMemoryStore) Set(ctx context.Context, namespace, key string, value any, ttlSeconds int) error {
	var lastErr error
	for _, tier := range s.config.WriteOrder {
		store := s.getTierStore(tier)
		if store == nil {
			continue
		}
		if err := store.Set(ctx, namespace, key, value, ttlSeconds); err != nil {
			lastErr = err
		}
	}
	return lastErr
}

// Delete removes a key from all tiers in WriteOrder.
func (s *TieredMemoryStore) Delete(ctx context.Context, namespace, key string) (bool, error) {
	var deleted bool
	var lastErr error
	for _, tier := range s.config.WriteOrder {
		store := s.getTierStore(tier)
		if store == nil {
			continue
		}
		ok, err := store.Delete(ctx, namespace, key)
		if err != nil {
			lastErr = err
			continue
		}
		if ok {
			deleted = true
		}
	}
	return deleted, lastErr
}

func (s *TieredMemoryStore) getTierStore(tier int) port.MemoryStore {
	switch tier {
	case 1:
		if s.config.Tier1Enabled {
			return s.tier1
		}
	case 2:
		if s.config.Tier2Enabled {
			return s.tier2
		}
	case 3:
		if s.config.Tier3Enabled {
			return s.tier3
		}
	}
	return nil
}
