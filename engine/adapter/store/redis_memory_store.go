package store

import (
	"bytes"
	"compress/zlib"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"strconv"
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

	compressionThreshold = 1024
	compressionFlagNone  = byte(0x00)
	compressionFlagZlib  = byte(0x01)
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
	raw, err := s.client.Get(ctx, fullKey).Bytes()
	if err == redis.Nil {
		return nil, false, nil
	}
	if err != nil {
		s.recordFailure()
		metrics.RecordFallback()
		return s.fallbackGet(ctx, namespace, key, err)
	}

	s.resetFailures()
	val, err := s.decodePayload(raw)
	if err != nil {
		return nil, false, err
	}
	var result any
	if err := json.Unmarshal(val, &result); err != nil {
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

	payload, err := s.encodePayload(data)
	if err != nil {
		return fmt.Errorf("redis encode error: %w", err)
	}

	fullKey := s.buildKey(namespace, key)
	ttl := time.Duration(ttlSeconds) * time.Second
	if ttlSeconds <= 0 {
		ttl = 0
	}

	if err := s.client.Set(ctx, fullKey, payload, ttl).Err(); err != nil {
		s.recordFailure()
		metrics.RecordFallback()
		err = s.fallbackSet(ctx, namespace, key, value, ttlSeconds, err)
		return err
	}

	s.resetFailures()
	return nil
}

// BatchGet retrieves multiple values by namespace and keys with fallback support.
func (s *RedisMemoryStore) BatchGet(ctx context.Context, namespace string, keys []string) (map[string]any, error) {
	if len(keys) == 0 {
		return map[string]any{}, nil
	}

	// Circuit breaker check with fallback
	if s.isCircuitOpen() {
		metrics.RecordFallback()
		log.Printf("circuit open, using fallback for batch get (namespace=%s key_count=%d)", namespace, len(keys))
		return s.fallbackBatchGet(ctx, namespace, keys)
	}

	pipe := s.client.Pipeline()
	cmds := make(map[string]*redis.StringCmd, len(keys))
	for _, key := range keys {
		fullKey := s.buildKey(namespace, key)
		cmds[key] = pipe.Get(ctx, fullKey)
	}

	start := time.Now()
	_, err := pipe.Exec(ctx)
	duration := time.Since(start)

	// Handle complete pipeline failure
	if err != nil && err != redis.Nil {
		s.recordFailure()
		metrics.RecordRedisOperation("batch_get", duration, err)

		if s.fallback != nil {
			log.Printf("redis batch get failed, using fallback (namespace=%s key_count=%d duration=%v error=%v)",
				namespace, len(keys), duration, err)
			metrics.RecordFallback()
			return s.fallbackBatchGet(ctx, namespace, keys)
		}
		return nil, fmt.Errorf("batch get failed: %w", err)
	}

	s.resetFailures()
	metrics.RecordRedisOperation("batch_get", duration, nil)

	// Collect results
	results := make(map[string]any, len(keys))
	for key, cmd := range cmds {
		raw, err := cmd.Bytes()
		if err == redis.Nil {
			continue // Key not found
		}
		if err != nil {
			// Individual key error - log but continue
			log.Printf("batch get key error (key=%s error=%v)", key, err)
			continue
		}

		val, err := s.decodePayload(raw)
		if err != nil {
			log.Printf("batch get decode error (key=%s error=%v)", key, err)
			continue
		}

		var decoded any
		if err := json.Unmarshal(val, &decoded); err != nil {
			log.Printf("batch get unmarshal error (key=%s error=%v)", key, err)
			continue
		}

		results[key] = decoded
	}

	return results, nil
}

// BatchSet stores multiple values with optional TTL and fallback support.
func (s *RedisMemoryStore) BatchSet(ctx context.Context, namespace string, items map[string]any, ttlSeconds int) error {
	if len(items) == 0 {
		return nil
	}

	if s.isCircuitOpen() {
		metrics.RecordFallback()
		return s.fallbackBatchSet(ctx, namespace, items, ttlSeconds)
	}

	pipe := s.client.Pipeline()
	ttl := time.Duration(ttlSeconds) * time.Second

	for key, value := range items {
		data, err := json.Marshal(value)
		if err != nil {
			return fmt.Errorf("marshal error for key %s: %w", key, err)
		}

		encoded, err := s.encodePayload(data)
		if err != nil {
			return fmt.Errorf("encode error for key %s: %w", key, err)
		}

		fullKey := s.buildKey(namespace, key)

		if ttlSeconds > 0 {
			pipe.Set(ctx, fullKey, encoded, ttl)
		} else {
			pipe.Set(ctx, fullKey, encoded, 0)
		}
	}

	start := time.Now()
	_, err := pipe.Exec(ctx)
	duration := time.Since(start)

	if err != nil {
		s.recordFailure()
		metrics.RecordRedisOperation("batch_set", duration, err)

		if s.fallback != nil {
			log.Printf("redis batch set failed, using fallback (error=%v)", err)
			metrics.RecordFallback()
			return s.fallbackBatchSet(ctx, namespace, items, ttlSeconds)
		}
		return err
	}

	s.resetFailures()
	metrics.RecordRedisOperation("batch_set", duration, nil)
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
		return s.fallbackStoreSummary(ctx, runID, summary, ttlSeconds)
	}

	payload, err := json.Marshal(summary)
	if err != nil {
		return fmt.Errorf("summary marshal error: %w", err)
	}

	encoded, err := s.encodePayload(payload)
	if err != nil {
		return fmt.Errorf("summary encode error: %w", err)
	}

	ttl := ttlSeconds
	if ttl <= 0 {
		ttl = int(defaultSummaryTTL.Seconds())
	}

	// Build keys for Lua script
	versionKey := s.buildSummaryVersionKey(runID)
	currentKey := s.buildSummaryKey(runID, "current")
	versionedPrefix := s.buildSummaryKey(runID, "")

	// Execute atomic Lua script
	start := time.Now()
	_, err = storeSummaryScript.Run(
		ctx,
		s.client,
		[]string{versionKey, currentKey, versionedPrefix},
		encoded,
		ttl,
	).Int64()
	duration := time.Since(start)

	if err != nil {
		s.recordFailure()
		metrics.RecordRedisOperation("store_summary", duration, err)

		if s.fallback != nil {
			log.Printf("redis store summary failed, using fallback (run_id=%s error=%v)", runID, err)
			return s.fallbackStoreSummary(ctx, runID, summary, ttlSeconds)
		}
		return fmt.Errorf("store summary: %w", err)
	}

	s.resetFailures()
	metrics.RecordRedisOperation("store_summary", duration, nil)
	return nil
}

func (s *RedisMemoryStore) fallbackStoreSummary(ctx context.Context, runID string, summary *entity.Summary, ttlSeconds int) error {
	if s.fallback == nil {
		return errCircuitOpen
	}

	key := fmt.Sprintf("summary:%s:current", runID)
	return s.fallback.Set(ctx, s.tenantID, key, summary, ttlSeconds)
}

// SummaryWithVersion holds a summary along with its version number.
type SummaryWithVersion struct {
	Summary *entity.Summary
	Version int64
}

// GetSummaryWithVersion retrieves the current summary and its version for a run.
func (s *RedisMemoryStore) GetSummaryWithVersion(ctx context.Context, tenantID, runID string) (*SummaryWithVersion, error) {
	if runID == "" {
		return nil, errors.New("run ID is required")
	}
	if tenantID == "" {
		tenantID = s.tenantID
	}
	if tenantID != s.tenantID {
		return nil, fmt.Errorf("tenant mismatch: %s", tenantID)
	}
	if s.isCircuitOpen() {
		// Fallback doesn't track versions
		summary, found, err := s.fallbackGetSummary(ctx, runID)
		if err != nil || !found {
			return nil, err
		}
		return &SummaryWithVersion{Summary: summary, Version: 0}, nil
	}

	versionKey := s.buildSummaryVersionKey(runID)
	currentKey := s.buildSummaryKey(runID, "current")

	result, err := getSummaryWithVersionScript.Run(
		ctx,
		s.client,
		[]string{versionKey, currentKey},
	).Slice()

	if err != nil {
		s.recordFailure()
		return nil, err
	}

	s.resetFailures()

	versionStr, ok := result[0].(string)
	if !ok {
		versionStr = "0"
	}
	dataStr, ok := result[1].(string)
	if !ok || dataStr == "" {
		return nil, nil
	}

	version, _ := strconv.ParseInt(versionStr, 10, 64)

	decoded, err := s.decodePayload([]byte(dataStr))
	if err != nil {
		return nil, err
	}

	var summary entity.Summary
	if err := json.Unmarshal(decoded, &summary); err != nil {
		return nil, err
	}

	return &SummaryWithVersion{
		Summary: &summary,
		Version: version,
	}, nil
}

func (s *RedisMemoryStore) fallbackGetSummary(ctx context.Context, runID string) (*entity.Summary, bool, error) {
	if s.fallback == nil {
		return nil, false, errCircuitOpen
	}

	key := fmt.Sprintf("summary:%s:current", runID)
	val, found, err := s.fallback.Get(ctx, s.tenantID, key)
	if err != nil || !found {
		return nil, false, err
	}

	summary, ok := val.(*entity.Summary)
	if !ok {
		// Try to unmarshal if it's stored as map
		if m, ok := val.(map[string]any); ok {
			data, _ := json.Marshal(m)
			var s entity.Summary
			if err := json.Unmarshal(data, &s); err == nil {
				return &s, true, nil
			}
		}
		return nil, false, nil
	}
	return summary, true, nil
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

func (s *RedisMemoryStore) fallbackBatchGet(ctx context.Context, namespace string, keys []string) (map[string]any, error) {
	if s.fallback == nil {
		return nil, errCircuitOpen
	}

	results := make(map[string]any, len(keys))
	var mu sync.Mutex
	var wg sync.WaitGroup

	// Parallel fetches from fallback (it's in-memory, so fast)
	for _, key := range keys {
		wg.Add(1)
		go func(k string) {
			defer wg.Done()

			val, found, err := s.fallback.Get(ctx, namespace, k)
			if err != nil || !found {
				return
			}

			mu.Lock()
			results[k] = val
			mu.Unlock()
		}(key)
	}

	wg.Wait()
	return results, nil
}

func (s *RedisMemoryStore) fallbackBatchSet(ctx context.Context, namespace string, items map[string]any, ttlSeconds int) error {
	if s.fallback == nil {
		return errCircuitOpen
	}

	var lastErr error
	for key, value := range items {
		if err := s.fallback.Set(ctx, namespace, key, value, ttlSeconds); err != nil {
			lastErr = err
		}
	}
	return lastErr
}

func (s *RedisMemoryStore) encodePayload(data []byte) ([]byte, error) {
	if len(data) == 0 {
		return []byte{compressionFlagNone}, nil
	}
	if len(data) <= compressionThreshold {
		out := make([]byte, 1+len(data))
		out[0] = compressionFlagNone
		copy(out[1:], data)
		return out, nil
	}

	var buf bytes.Buffer
	zw := zlib.NewWriter(&buf)
	if _, err := zw.Write(data); err != nil {
		_ = zw.Close()
		return nil, err
	}
	if err := zw.Close(); err != nil {
		return nil, err
	}

	compressed := buf.Bytes()
	out := make([]byte, 1+len(compressed))
	out[0] = compressionFlagZlib
	copy(out[1:], compressed)
	return out, nil
}

func (s *RedisMemoryStore) decodePayload(raw []byte) ([]byte, error) {
	if len(raw) == 0 {
		return nil, nil
	}

	flag := raw[0]
	payload := raw[1:]

	// Backward compatibility: plain JSON stored without flag.
	if flag != compressionFlagNone && flag != compressionFlagZlib {
		return raw, nil
	}

	switch flag {
	case compressionFlagNone:
		return payload, nil
	case compressionFlagZlib:
		reader, err := zlib.NewReader(bytes.NewReader(payload))
		if err != nil {
			return nil, err
		}
		defer reader.Close()
		return io.ReadAll(reader)
	default:
		return raw, nil
	}
}
