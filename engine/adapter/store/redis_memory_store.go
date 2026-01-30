package store

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"sync"
	"sync/atomic"
	"time"

	"github.com/forgegraph/engine/application/port"
	"github.com/forgegraph/engine/domain/entity"
	"github.com/forgegraph/engine/infrastructure/metrics"
	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

const (
	keyPrefixDefault    = "forgegraph"
	keyPatternMemory    = "%s:tenant:%s:memory:%s:%s"
	keyPatternBuffer    = "%s:tenant:%s:buffer:%s"
	keyPatternFacts     = "%s:tenant:%s:facts:%s:%s"
	circuitOpenDuration = 30 * time.Second
	failureThreshold    = 5
	defaultSummaryTTL   = 7 * 24 * time.Hour
)

var errCircuitOpen = errors.New("redis circuit open")

// RedisConfig defines options for connecting to Redis.
type RedisConfig struct {
	Addr         string
	Password     string
	DB           int
	DialTimeout  time.Duration
	ReadTimeout  time.Duration
	WriteTimeout time.Duration
	PoolSize     int
	KeyPrefix    string
}

// RedisMemoryStore implements MemoryStore using Redis with a circuit breaker.
type RedisMemoryStore struct {
	client       *redis.Client
	tenantID     string
	keyPrefix    string
	fallback     port.MemoryStore
	circuitOpen  atomic.Bool
	lastFailure  atomic.Value // time.Time
	failureCount atomic.Int32
	mu           sync.RWMutex
}

// NewRedisMemoryStore creates a new Redis-backed memory store.
func NewRedisMemoryStore(cfg RedisConfig, tenantID string, fallback port.MemoryStore) (*RedisMemoryStore, error) {
	if tenantID == "" {
		return nil, fmt.Errorf("tenant ID is required")
	}
	if _, err := uuid.Parse(tenantID); err != nil {
		return nil, fmt.Errorf("invalid tenant ID format: %w", err)
	}

	options := &redis.Options{
		Addr:         cfg.Addr,
		Password:     cfg.Password,
		DB:           cfg.DB,
		DialTimeout:  cfg.DialTimeout,
		ReadTimeout:  cfg.ReadTimeout,
		WriteTimeout: cfg.WriteTimeout,
		PoolSize:     cfg.PoolSize,
	}

	keyPrefix := cfg.KeyPrefix
	if keyPrefix == "" {
		keyPrefix = keyPrefixDefault
	}

	store := &RedisMemoryStore{
		client:    redis.NewClient(options),
		tenantID:  tenantID,
		keyPrefix: keyPrefix,
		fallback:  fallback,
	}
	store.lastFailure.Store(time.Time{})

	return store, nil
}

// Get retrieves a value by namespace and key.
func (s *RedisMemoryStore) Get(ctx context.Context, namespace, key string) (value any, found bool, err error) {
	start := time.Now()
	defer func() {
		metrics.RecordRedisOperation("get", time.Since(start), err)
	}()
	if s.isCircuitOpen() {
		metrics.RecordFallback()
		return s.fallbackGet(ctx, namespace, key, errCircuitOpen)
	}

	fullKey := s.buildKey(namespace, key)
	val, err := s.client.Get(ctx, fullKey).Result()
	if err == redis.Nil {
		return nil, false, nil
	}
	if err != nil {
		s.recordFailure()
		metrics.RecordFallback()
		return s.fallbackGet(ctx, namespace, key, err)
	}

	s.resetFailures()
	var result any
	if err := json.Unmarshal([]byte(val), &result); err != nil {
		return nil, false, fmt.Errorf("redis unmarshal error: %w", err)
	}
	return result, true, nil
}

// Set stores a value with optional TTL (seconds). ttlSeconds <= 0 means no expiry.
func (s *RedisMemoryStore) Set(ctx context.Context, namespace, key string, value any, ttlSeconds int) (err error) {
	start := time.Now()
	defer func() {
		metrics.RecordRedisOperation("set", time.Since(start), err)
	}()
	if s.isCircuitOpen() {
		metrics.RecordFallback()
		err = s.fallbackSet(ctx, namespace, key, value, ttlSeconds, errCircuitOpen)
		return err
	}

	data, err := json.Marshal(value)
	if err != nil {
		return fmt.Errorf("redis marshal error: %w", err)
	}

	fullKey := s.buildKey(namespace, key)
	ttl := time.Duration(ttlSeconds) * time.Second
	if ttlSeconds <= 0 {
		ttl = 0
	}

	if err := s.client.Set(ctx, fullKey, data, ttl).Err(); err != nil {
		s.recordFailure()
		metrics.RecordFallback()
		err = s.fallbackSet(ctx, namespace, key, value, ttlSeconds, err)
		return err
	}

	s.resetFailures()
	return nil
}

// Delete removes a key/value entry. Returns true if an entry was deleted.
func (s *RedisMemoryStore) Delete(ctx context.Context, namespace, key string) (deleted bool, err error) {
	start := time.Now()
	defer func() {
		metrics.RecordRedisOperation("delete", time.Since(start), err)
	}()
	if s.isCircuitOpen() {
		metrics.RecordFallback()
		deleted, err = s.fallbackDelete(ctx, namespace, key, errCircuitOpen)
		return deleted, err
	}

	fullKey := s.buildKey(namespace, key)
	result, err := s.client.Del(ctx, fullKey).Result()
	if err != nil {
		s.recordFailure()
		metrics.RecordFallback()
		deleted, err = s.fallbackDelete(ctx, namespace, key, err)
		return deleted, err
	}

	s.resetFailures()
	deleted = result > 0
	return deleted, nil
}

// Ping verifies Redis connectivity.
func (s *RedisMemoryStore) Ping(ctx context.Context) error {
	return s.client.Ping(ctx).Err()
}

// StoreSummary stores the current summary and keeps a limited version history.
func (s *RedisMemoryStore) StoreSummary(ctx context.Context, tenantID, runID string, summary *entity.Summary, ttlSeconds int) error {
	if summary == nil {
		return errors.New("summary is nil")
	}
	if runID == "" {
		return errors.New("run ID is required")
	}
	if tenantID == "" {
		tenantID = s.tenantID
	}
	if tenantID != s.tenantID {
		return fmt.Errorf("tenant mismatch: %s", tenantID)
	}
	if s.isCircuitOpen() {
		return errCircuitOpen
	}

	payload, err := json.Marshal(summary)
	if err != nil {
		return fmt.Errorf("summary marshal error: %w", err)
	}

	ttl := time.Duration(ttlSeconds) * time.Second
	if ttlSeconds <= 0 {
		ttl = defaultSummaryTTL
	}

	versionKey := s.buildSummaryVersionKey(runID)
	version, err := s.client.Incr(ctx, versionKey).Result()
	if err != nil {
		s.recordFailure()
		return err
	}
	_ = s.client.Expire(ctx, versionKey, ttl).Err()

	currentKey := s.buildSummaryKey(runID, "current")
	versionedKey := s.buildSummaryKey(runID, fmt.Sprintf("v%d", version))

	pipe := s.client.TxPipeline()
	pipe.Set(ctx, currentKey, payload, ttl)
	pipe.Set(ctx, versionedKey, payload, ttl)
	if version > 5 {
		oldKey := s.buildSummaryKey(runID, fmt.Sprintf("v%d", version-5))
		pipe.Del(ctx, oldKey)
	}

	if _, err := pipe.Exec(ctx); err != nil {
		s.recordFailure()
		return err
	}

	s.resetFailures()
	return nil
}

// StoreFacts stores extracted facts for a run.
func (s *RedisMemoryStore) StoreFacts(ctx context.Context, tenantID, runID string, facts []entity.Fact, ttlSeconds int) error {
	if runID == "" {
		return errors.New("run ID is required")
	}
	if tenantID == "" {
		tenantID = s.tenantID
	}
	if tenantID != s.tenantID {
		return fmt.Errorf("tenant mismatch: %s", tenantID)
	}
	if s.isCircuitOpen() {
		return errCircuitOpen
	}

	ttl := time.Duration(ttlSeconds) * time.Second
	if ttlSeconds <= 0 {
		ttl = defaultSummaryTTL
	}

	pipe := s.client.TxPipeline()
	for _, fact := range facts {
		if fact.Key == "" {
			continue
		}
		payload, err := json.Marshal(fact)
		if err != nil {
			return fmt.Errorf("fact marshal error: %w", err)
		}
		pipe.Set(ctx, s.buildFactKey(runID, fact.Key), payload, ttl)
	}

	if _, err := pipe.Exec(ctx); err != nil {
		s.recordFailure()
		return err
	}

	s.resetFailures()
	return nil
}

// GetSummary retrieves the current summary for a run.
func (s *RedisMemoryStore) GetSummary(ctx context.Context, tenantID, runID string) (*entity.Summary, bool, error) {
	if runID == "" {
		return nil, false, errors.New("run ID is required")
	}
	if tenantID == "" {
		tenantID = s.tenantID
	}
	if tenantID != s.tenantID {
		return nil, false, fmt.Errorf("tenant mismatch: %s", tenantID)
	}
	if s.isCircuitOpen() {
		return nil, false, errCircuitOpen
	}

	val, err := s.client.Get(ctx, s.buildSummaryKey(runID, "current")).Result()
	if err == redis.Nil {
		return nil, false, nil
	}
	if err != nil {
		s.recordFailure()
		return nil, false, err
	}

	var summary entity.Summary
	if err := json.Unmarshal([]byte(val), &summary); err != nil {
		return nil, false, fmt.Errorf("summary unmarshal error: %w", err)
	}
	s.resetFailures()
	return &summary, true, nil
}

// GetFact retrieves a fact by key for a run.
func (s *RedisMemoryStore) GetFact(ctx context.Context, tenantID, runID, factKey string) (*entity.Fact, bool, error) {
	if runID == "" || factKey == "" {
		return nil, false, errors.New("run ID and fact key are required")
	}
	if tenantID == "" {
		tenantID = s.tenantID
	}
	if tenantID != s.tenantID {
		return nil, false, fmt.Errorf("tenant mismatch: %s", tenantID)
	}
	if s.isCircuitOpen() {
		return nil, false, errCircuitOpen
	}

	val, err := s.client.Get(ctx, s.buildFactKey(runID, factKey)).Result()
	if err == redis.Nil {
		return nil, false, nil
	}
	if err != nil {
		s.recordFailure()
		return nil, false, err
	}

	var fact entity.Fact
	if err := json.Unmarshal([]byte(val), &fact); err != nil {
		return nil, false, fmt.Errorf("fact unmarshal error: %w", err)
	}
	s.resetFailures()
	return &fact, true, nil
}

func (s *RedisMemoryStore) buildKey(namespace, key string) string {
	return fmt.Sprintf(keyPatternMemory, s.keyPrefix, s.tenantID, namespace, key)
}

func (s *RedisMemoryStore) buildBufferKey(runID string) string {
	return fmt.Sprintf(keyPatternBuffer, s.keyPrefix, s.tenantID, runID)
}

func (s *RedisMemoryStore) buildSummaryKey(runID, suffix string) string {
	return fmt.Sprintf("%s:tenant:%s:summary:%s:%s", s.keyPrefix, s.tenantID, runID, suffix)
}

func (s *RedisMemoryStore) buildSummaryVersionKey(runID string) string {
	return fmt.Sprintf("%s:tenant:%s:summary:%s:version", s.keyPrefix, s.tenantID, runID)
}

func (s *RedisMemoryStore) buildFactKey(runID, factKey string) string {
	return fmt.Sprintf(keyPatternFacts, s.keyPrefix, s.tenantID, runID, factKey)
}

// ListTenantKeys lists keys for a tenant (admin/debug use).
func (s *RedisMemoryStore) ListTenantKeys(ctx context.Context, pattern string) ([]string, error) {
	fullPattern := fmt.Sprintf("%s:tenant:%s:%s", s.keyPrefix, s.tenantID, pattern)
	var keys []string
	iter := s.client.Scan(ctx, 0, fullPattern, 100).Iterator()
	for iter.Next(ctx) {
		keys = append(keys, iter.Val())
	}
	return keys, iter.Err()
}

func (s *RedisMemoryStore) isCircuitOpen() bool {
	if !s.circuitOpen.Load() {
		return false
	}

	lastFail, _ := s.lastFailure.Load().(time.Time)
	if time.Since(lastFail) > circuitOpenDuration {
		if s.attemptRecovery(context.Background()) {
			return false
		}
		s.lastFailure.Store(time.Now())
	}

	return true
}

func (s *RedisMemoryStore) recordFailure() {
	count := s.failureCount.Add(1)
	s.lastFailure.Store(time.Now())
	if count == 1 {
		log.Printf("Redis failure detected")
	}
	if count >= failureThreshold {
		s.circuitOpen.Store(true)
		metrics.RecordCircuitState(true)
		log.Printf("Redis circuit breaker opening after %d failures", failureThreshold)
	}
}

func (s *RedisMemoryStore) resetFailures() {
	if s.failureCount.Load() > 0 {
		s.failureCount.Store(0)
		if s.circuitOpen.Load() {
			s.circuitOpen.Store(false)
			metrics.RecordCircuitState(false)
			log.Printf("Redis circuit breaker closing, Redis recovered")
		}
	}
}

func (s *RedisMemoryStore) attemptRecovery(ctx context.Context) bool {
	healthCtx, cancel := context.WithTimeout(ctx, time.Second)
	defer cancel()

	if err := s.client.Ping(healthCtx).Err(); err != nil {
		return false
	}

	s.circuitOpen.Store(false)
	s.failureCount.Store(0)
	metrics.RecordCircuitState(false)
	log.Printf("Redis connection recovered")
	return true
}

func (s *RedisMemoryStore) fallbackGet(ctx context.Context, namespace, key string, cause error) (any, bool, error) {
	if s.fallback != nil {
		return s.fallback.Get(ctx, namespace, key)
	}
	if cause == nil {
		cause = errCircuitOpen
	}
	return nil, false, cause
}

func (s *RedisMemoryStore) fallbackSet(ctx context.Context, namespace, key string, value any, ttlSeconds int, cause error) error {
	if s.fallback != nil {
		return s.fallback.Set(ctx, namespace, key, value, ttlSeconds)
	}
	if cause == nil {
		cause = errCircuitOpen
	}
	return cause
}

func (s *RedisMemoryStore) fallbackDelete(ctx context.Context, namespace, key string, cause error) (bool, error) {
	if s.fallback != nil {
		return s.fallback.Delete(ctx, namespace, key)
	}
	if cause == nil {
		cause = errCircuitOpen
	}
	return false, cause
}
