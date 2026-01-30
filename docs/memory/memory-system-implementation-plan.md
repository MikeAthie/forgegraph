# ForgeGraph Hierarchical Memory System Implementation Plan

## Executive Summary

This document outlines a comprehensive, phased implementation plan for a hierarchical memory system in ForgeGraph. The system provides three tiers of memory:

1. **Tier 1 - Local Buffer**: In-memory circular buffer for immediate context (sub-millisecond access)
2. **Tier 2 - Redis Cache**: Fast persistent storage for summaries and shared facts (<10ms access)
3. **Tier 3 - Vector DB**: Long-term semantic memory with embedding-based retrieval (<100ms access)

The implementation is divided into four phases:

| Phase | Focus | Complexity | Duration Estimate |
|-------|-------|------------|-------------------|
| Phase 1 | Foundation (Redis + Local Buffer) | L | 3-4 weeks |
| Phase 2 | Intelligent Summarization | M | 2-3 weeks |
| Phase 3 | Semantic Long-Term Memory | XL | 4-6 weeks |
| Phase 4 | Advanced Features & Optimization | L | 2-3 weeks |

**Key Design Decisions:**
- Extend existing `MemoryStore` interface rather than replace it
- Use composition pattern for tiered storage with fallback chain
- Message-count based limits initially (defer token counting to Phase 4)
- Redis provides cross-instance consistency; local buffers are per-instance
- Multi-tenant isolation via namespaced keys with tenant ID prefix
- Production parity: PostgreSQL is required for Phase 3+ (pgvector); SQLite is no longer supported for memory features

---

## Current Status (2026-01-30)

- Phase 1: complete (buffer, Redis integration, memory config, engine wiring).
- Phase 2: complete (summarization pipeline, config, UI, cost tracking).
- Phase 3: in progress.
  - Done: pgvector DB setup, MemoryChunk model/migrations, embedding + chunking services, vector search service, vector config fields/UI, memory GC scaffolding.
  - Pending: gRPC memory retrieval endpoint, prompt executor Tier3 integration, embedding pipeline integration tests, GC metrics, and remaining Phase 3 checklist items.

---

## Phase 1: Foundation (Redis Buffer + Local Buffer + Configuration)

### 1.1 Overview

**Goals:**
- Implement `RedisMemoryStore` conforming to existing `MemoryStore` interface
- Create in-memory circular buffer for immediate context (Tier 1)
- Establish configuration schema and storage in Django
- Pass memory configuration to Go engine via `StartRunRequest`
- Implement graceful fallback when Redis is unavailable

**Dependencies:** None (foundation phase)

**Complexity:** L (Large)

**Key Risks and Mitigations:**

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Redis connection instability | Medium | High | Implement circuit breaker with fallback to InMemoryMemoryStore |
| Multi-tenant data leakage | Low | Critical | Strict namespace prefixing with tenant ID; integration tests |
| Local buffer memory pressure | Medium | Medium | Configurable limits with eviction; monitoring |
| gRPC message size limits | Low | Medium | Compress large state; paginate if needed |

---

### 1.2 Task List

#### P1-T01: Create RedisMemoryStore Implementation

**Description:** Implement a Redis-backed `MemoryStore` that conforms to the existing interface defined in `engine/application/port/memory_store.go`. This provides fast, persistent, cross-instance storage for Tier 2 memory.

**Affected Components:** Go Engine

**Files to Create/Modify:**
- Create: `engine/adapter/store/redis_memory_store.go`
- Create: `engine/adapter/store/redis_memory_store_test.go`
- Modify: `engine/main.go` (wire up Redis store option)

**Implementation Details:**
```go
// Key structure:
// forgegraph:tenant:{tenant_id}:memory:{namespace}:{key}

type RedisMemoryStore struct {
    client      *redis.Client
    tenantID    string
    keyPrefix   string
    fallback    port.MemoryStore  // InMemoryMemoryStore for fallback
    circuitOpen atomic.Bool
    lastFailure atomic.Value      // time.Time
    failureCount atomic.Int32
}

// Circuit breaker config
const (
    circuitOpenDuration = 30 * time.Second
    failureThreshold    = 5
)
```

**Algorithm:**
1. Build composite key: `{keyPrefix}:tenant:{tenantID}:memory:{namespace}:{key}`
2. For `Get`: Check circuit breaker → Redis GET → JSON unmarshal → return
3. For `Set`: JSON marshal → Redis SET with TTL → check for errors
4. For `Delete`: Redis DEL → return success
5. On Redis error: Increment failure count → open circuit if threshold reached → fallback

**Dependencies:** None

**Estimated Effort:** 2 days

**SUCCESS CRITERIA:**
- [ ] `RedisMemoryStore.Get()` returns stored value within 10ms for 99th percentile
- [ ] `RedisMemoryStore.Set()` with TTL=3600 causes key to expire after 1 hour (±5 seconds)
- [ ] When Redis is unavailable, circuit breaker opens after 5 consecutive failures
- [ ] After circuit opens, system uses fallback for 30 seconds before retrying Redis
- [ ] All keys include tenant ID prefix verified by checking raw Redis keys
- [ ] Unit test `TestRedisMemoryStore_BasicOperations` passes
- [ ] Unit test `TestRedisMemoryStore_TTLExpiration` passes
- [ ] Unit test `TestRedisMemoryStore_CircuitBreaker` passes
- [ ] Unit test `TestRedisMemoryStore_TenantIsolation` passes

---

#### P1-T02: Implement Local Circular Buffer

**Description:** Create a goroutine-safe circular buffer that stores the last N messages per run. This buffer lives in Go engine memory and provides sub-millisecond access for immediate context.

**Affected Components:** Go Engine

**Files to Create/Modify:**
- Create: `engine/domain/entity/message_buffer.go`
- Create: `engine/domain/entity/message_buffer_test.go`

**Implementation Details:**
```go
type Message struct {
    Role      string    `json:"role"`       // "user", "assistant", "system"
    Content   string    `json:"content"`
    Timestamp time.Time `json:"timestamp"`
    NodeID    string    `json:"node_id,omitempty"`
    Metadata  map[string]any `json:"metadata,omitempty"`
}

type MessageBuffer struct {
    mu       sync.RWMutex
    messages []Message
    capacity int
    head     int  // Next write position
    count    int  // Current message count
}

// Methods:
// - Push(msg Message): Add message, evict oldest if at capacity
// - GetAll() []Message: Return all messages in chronological order
// - GetLast(n int) []Message: Return last n messages
// - Clear(): Reset buffer
// - Snapshot() []Message: Deep copy for checkpointing
// - Restore(msgs []Message): Restore from checkpoint
```

**Algorithm:**
- Circular buffer using array with head pointer
- On Push: Write to messages[head], increment head % capacity, increment count (max capacity)
- On GetAll: Return messages from oldest to newest accounting for wrap-around
- Thread safety via sync.RWMutex (write lock for Push/Clear, read lock for Get*)

**Dependencies:** None

**Estimated Effort:** 1 day

**SUCCESS CRITERIA:**
- [ ] `Push()` operation completes in <100μs (measured with benchmark)
- [ ] `GetAll()` returns messages in chronological order after wrap-around
- [ ] `GetLast(n)` returns exactly min(n, count) messages
- [ ] Concurrent Push/Get operations do not cause data races (tested with `-race`)
- [ ] Buffer correctly evicts oldest message when at capacity
- [ ] `Snapshot()` returns deep copy that is independent of buffer modifications
- [ ] `Restore()` correctly repopulates buffer from checkpoint
- [ ] Unit test `TestMessageBuffer_CircularBehavior` passes
- [ ] Unit test `TestMessageBuffer_Concurrency` passes with race detector

---

#### P1-T03: Integrate Message Buffer into Scheduler Run Context

**Description:** Embed the message buffer into the scheduler's `runContext` so that each run has its own isolated buffer. Messages are automatically captured during prompt execution.

**Affected Components:** Go Engine

**Files to Modify:**
- `engine/application/usecase/scheduler.go`
- `engine/adapter/executor/prompt_executor.go`

**Implementation Details:**

Modify `runContext` struct:
```go
type runContext struct {
    // ... existing fields ...
    messageBuffer *entity.MessageBuffer  // NEW: Local message buffer
    memoryConfig  *MemoryConfig          // NEW: Memory configuration
}

type MemoryConfig struct {
    BufferSize       int  `json:"buffer_size"`        // Max messages in local buffer
    EnableRedis      bool `json:"enable_redis"`       // Use Redis for Tier 2
    RedisNamespace   string `json:"redis_namespace"`  // Custom namespace
    AutoPrepend      bool `json:"auto_prepend"`       // Auto-prepend to prompts
}
```

Modify prompt executor to:
1. Before LLM call: Get buffered messages if `AutoPrepend` enabled
2. After LLM call: Push user message and assistant response to buffer

**Dependencies:** P1-T02

**Estimated Effort:** 1.5 days

**SUCCESS CRITERIA:**
- [ ] Each run has its own isolated message buffer
- [ ] Buffer size respects `MemoryConfig.BufferSize` configuration
- [ ] When `AutoPrepend=true`, prompt executor prepends buffer messages to LLM context
- [ ] User and assistant messages are captured after each prompt node execution
- [ ] Buffer is included in checkpoint snapshots via `state.Set("_messageBuffer", buffer.Snapshot())`
- [ ] Buffer is restored when run resumes from checkpoint
- [ ] Integration test: Run with 5 prompt nodes shows correct message history
- [ ] Memory usage stays bounded (monitored via pprof heap profile)

---

#### P1-T04: Create Memory Configuration Django Model

**Description:** Define Django models to store memory configuration at graph and user levels. Configuration is validated and passed to the engine.

**Affected Components:** Django Backend

**Files to Create/Modify:**
- Create: `backend/domain/entities/memory_config.py`
- Modify: `backend/infrastructure/orm/models.py`
- Create: `backend/infrastructure/orm/migrations/0011_memory_configuration.py`
- Modify: `backend/adapters/api/graphs/serializers.py`

**Implementation Details:**

```python
# New model
class MemoryConfiguration(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)

    # Scope: either graph-level or user-level default
    graph = models.OneToOneField(
        'Graph',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='memory_config'
    )
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='default_memory_config'
    )

    # Tier 1: Local Buffer
    buffer_enabled = models.BooleanField(default=True)
    buffer_size = models.PositiveIntegerField(default=20)  # Messages
    auto_prepend = models.BooleanField(default=True)

    # Tier 2: Redis
    redis_enabled = models.BooleanField(default=False)
    redis_summary_ttl = models.PositiveIntegerField(default=86400)  # 24 hours
    redis_facts_ttl = models.PositiveIntegerField(default=604800)   # 7 days

    # Tier 3: Vector (Phase 3, but define schema now)
    vector_enabled = models.BooleanField(default=False)
    vector_top_k = models.PositiveIntegerField(default=5)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'memory_configurations'
        constraints = [
            models.CheckConstraint(
                check=~(Q(graph__isnull=True) & Q(user__isnull=True)),
                name='memory_config_requires_scope'
            ),
            models.CheckConstraint(
                check=~(Q(graph__isnull=False) & Q(user__isnull=False)),
                name='memory_config_single_scope'
            ),
        ]
```

**User-Friendly Labels Mapping:**
```python
BUFFER_SIZE_CHOICES = {
    'short': 10,
    'medium': 20,
    'long': 50,
    'extended': 100,
}
```

**Dependencies:** None

**Estimated Effort:** 1 day

**SUCCESS CRITERIA:**
- [ ] Migration `0011_memory_configuration` applies successfully
- [ ] Model enforces exactly one of `graph` or `user` is set
- [ ] Serializer validates buffer_size is between 1 and 200
- [ ] API endpoint `GET /api/graphs/{id}/memory-config/` returns configuration
- [ ] API endpoint `PATCH /api/graphs/{id}/memory-config/` updates configuration
- [ ] Default configuration created when graph is created
- [ ] User-level defaults are used when graph has no explicit config

---

#### P1-T05: Extend StartRunRequest with Memory Configuration

**Description:** Modify the gRPC `StartRunRequest` to include memory configuration. Update Django API and Go engine to pass and parse this configuration.

**Affected Components:** Go Engine, Django Backend

**Files to Modify:**
- `engine/proto/engine.proto`
- `engine/proto/engine.pb.go` (regenerated)
- `engine/proto/engine_grpc.pb.go` (regenerated)
- `backend/adapters/api/runs/views.py`
- `engine/application/usecase/scheduler.go`

**Implementation Details:**

Proto changes:
```protobuf
message StartRunRequest {
    string run_id = 1;
    string graph_json = 2;
    string input_json = 3;
    string callback_url = 4;
    string memory_config_json = 5;  // NEW
}
```

Memory config JSON structure:
```json
{
    "tier1": {
        "enabled": true,
        "buffer_size": 20,
        "auto_prepend": true
    },
    "tier2": {
        "enabled": true,
        "redis_namespace": "run:{run_id}",
        "summary_ttl_seconds": 86400,
        "facts_ttl_seconds": 604800
    },
    "tier3": {
        "enabled": false
    }
}
```

**Dependencies:** P1-T04

**Estimated Effort:** 1 day

**SUCCESS CRITERIA:**
- [ ] Proto regeneration succeeds without breaking existing clients
- [ ] Django serializes memory config and includes in `StartRunRequest`
- [ ] Go engine parses `memory_config_json` and populates `runContext.memoryConfig`
- [ ] Missing or empty `memory_config_json` uses sensible defaults
- [ ] Invalid JSON in `memory_config_json` logs warning and uses defaults
- [ ] Integration test: Start run with custom buffer_size=50, verify buffer created with that size

---

#### P1-T06: Create TieredMemoryStore Composition

**Description:** Create a composite `MemoryStore` implementation that chains multiple stores with fallback behavior. This provides the foundation for tiered storage.

**Affected Components:** Go Engine

**Files to Create/Modify:**
- Create: `engine/adapter/store/tiered_memory_store.go`
- Create: `engine/adapter/store/tiered_memory_store_test.go`

**Implementation Details:**

```go
type TieredMemoryStore struct {
    tier1    *entity.MessageBuffer  // Local buffer (Tier 1)
    tier2    port.MemoryStore       // Redis (Tier 2)
    tier3    port.MemoryStore       // Vector DB (Tier 3, Phase 3)
    config   TieredConfig
    metrics  *TieredMetrics
}

type TieredConfig struct {
    Tier1Enabled bool
    Tier2Enabled bool
    Tier3Enabled bool
    ReadOrder    []int  // e.g., [1, 2, 3] - which tiers to check
    WriteOrder   []int  // e.g., [2] - which tiers to write to
}

// Get checks tiers in ReadOrder, returns first hit
// Set writes to all tiers in WriteOrder
// Metrics track hit rates per tier
```

**Behavior:**
- `Get`: Check tiers in `ReadOrder` until found or exhausted
- `Set`: Write to all tiers in `WriteOrder` (parallel for performance)
- Track metrics: hit rate per tier, latency per tier

**Dependencies:** P1-T01, P1-T02

**Estimated Effort:** 1.5 days

**SUCCESS CRITERIA:**
- [ ] `Get()` returns value from first tier that has it
- [ ] `Get()` metrics show correct tier hit attribution
- [ ] `Set()` writes to all enabled tiers in WriteOrder
- [ ] If Tier 2 (Redis) fails, Tier 1 (local) still works
- [ ] Latency overhead of tiering is <1ms compared to direct access
- [ ] Unit test `TestTieredMemoryStore_FallbackChain` passes
- [ ] Unit test `TestTieredMemoryStore_WriteToMultipleTiers` passes

---

#### P1-T07: Create Frontend Memory Configuration UI

**Description:** Extend the existing `MemoryNodeForm.tsx` to support tiered memory configuration with user-friendly labels and smart defaults.

**Affected Components:** Frontend

**Files to Modify:**
- `frontend/components/graph-editor/forms/MemoryNodeForm.tsx`
- Create: `frontend/components/graph-editor/dialogs/MemoryConfigDialog.tsx`
- Modify: `frontend/lib/api/graphs.ts` (add memory config endpoints)

**Implementation Details:**

```typescript
// User-friendly memory depth options
const MEMORY_DEPTH_OPTIONS = [
  { value: 'short', label: 'Short (last 10 messages)', bufferSize: 10 },
  { value: 'medium', label: 'Medium (last 20 messages)', bufferSize: 20 },
  { value: 'long', label: 'Long (last 50 messages)', bufferSize: 50 },
  { value: 'extended', label: 'Extended (last 100 messages)', bufferSize: 100 },
  { value: 'custom', label: 'Custom...', bufferSize: null },
];

interface MemoryConfigFormData {
  memoryDepth: 'short' | 'medium' | 'long' | 'extended' | 'custom';
  customBufferSize?: number;
  enablePersistence: boolean;  // Maps to redis_enabled
  showAdvanced: boolean;
  // Advanced options (collapsed by default)
  autoPrepend: boolean;
  summaryTtlHours: number;
  factsTtlDays: number;
}
```

**UI Structure:**
1. Simple mode (default): Memory Depth dropdown + Enable Persistence toggle
2. Advanced mode (expandable): Full control over TTLs, auto-prepend, etc.

**Dependencies:** P1-T04 (API endpoints)

**Estimated Effort:** 2 days

**SUCCESS CRITERIA:**
- [ ] Memory depth dropdown shows 4 preset options + Custom
- [ ] Selecting "Custom" reveals numeric input for buffer size
- [ ] "Enable Persistence" toggle maps to `redis_enabled`
- [ ] "Advanced" accordion reveals TTL and auto-prepend settings
- [ ] Form saves configuration via `PATCH /api/graphs/{id}/memory-config/`
- [ ] Form loads existing configuration on dialog open
- [ ] Validation prevents buffer_size < 1 or > 200
- [ ] Visual tests pass for both light and dark themes

---

#### P1-T08: Add Redis Health Check and Metrics

**Description:** Implement health checking for Redis connectivity and expose metrics for monitoring memory system performance.

**Affected Components:** Go Engine, Django Backend

**Files to Create/Modify:**
- Create: `engine/adapter/store/redis_health.go`
- Modify: `engine/main.go` (add health endpoint)
- Create: `backend/adapters/api/health/memory_health.py`

**Implementation Details:**

Go health check:
```go
type RedisHealthChecker struct {
    client     *redis.Client
    lastCheck  time.Time
    lastStatus bool
    checkMu    sync.Mutex
}

func (h *RedisHealthChecker) Check(ctx context.Context) HealthStatus {
    // Ping Redis with 1s timeout
    // Return status with latency measurement
}
```

Metrics to expose:
```
# Go engine metrics (Prometheus format)
forgegraph_memory_tier1_operations_total{operation="get|set|delete"}
forgegraph_memory_tier1_buffer_size{run_id}
forgegraph_memory_tier2_operations_total{operation="get|set|delete"}
forgegraph_memory_tier2_latency_seconds{operation, quantile="0.5|0.9|0.99"}
forgegraph_memory_tier2_circuit_state{state="closed|open"}
forgegraph_memory_tier2_fallback_total
```

**Dependencies:** P1-T01

**Estimated Effort:** 1 day

**SUCCESS CRITERIA:**
- [ ] Health endpoint `/health/redis` returns status within 100ms
- [ ] Health check caches result for 5 seconds to avoid hammering Redis
- [ ] Prometheus metrics endpoint exposes all defined metrics
- [ ] Circuit breaker state changes are logged and metriced
- [ ] Fallback activations increment `forgegraph_memory_tier2_fallback_total`
- [ ] Grafana dashboard can visualize tier hit rates and latencies

---

#### P1-T09: Implement Multi-Tenant Key Isolation

**Description:** Ensure all memory operations are scoped by tenant ID to prevent cross-tenant data leakage. Add comprehensive testing for isolation.

**Affected Components:** Go Engine, Django Backend

**Files to Modify:**
- `engine/adapter/store/redis_memory_store.go`
- Create: `engine/adapter/store/tenant_test.go`
- Modify: `backend/adapters/api/runs/views.py` (pass tenant ID)

**Implementation Details:**

Key structure:
```
forgegraph:tenant:{tenant_id}:memory:{namespace}:{key}
forgegraph:tenant:{tenant_id}:buffer:{run_id}:messages
forgegraph:tenant:{tenant_id}:summary:{agent_id}
forgegraph:tenant:{tenant_id}:facts:{scope}:{fact_key}
```

Tenant ID propagation:
1. Django extracts tenant from authenticated user
2. Tenant ID included in `StartRunRequest` metadata
3. Go engine uses tenant ID for all key prefixes
4. No API allows specifying arbitrary tenant ID

**Dependencies:** P1-T01, P1-T05

**Estimated Effort:** 1 day

**SUCCESS CRITERIA:**
- [ ] All Redis keys include tenant ID verified by key inspection
- [ ] Tenant A cannot access Tenant B's data even with key guessing
- [ ] Missing tenant ID in request returns 400 Bad Request
- [ ] Integration test with 2 tenants shows complete isolation
- [ ] Unit test `TestTenantIsolation_CrossTenantBlocked` passes
- [ ] Security audit checklist item for tenant isolation is documented

---

#### P1-T10: Implement Graceful Degradation and Fallback

**Description:** Ensure the system continues operating when Redis is unavailable by falling back to in-memory storage with appropriate warnings.

**Affected Components:** Go Engine

**Files to Modify:**
- `engine/adapter/store/redis_memory_store.go`
- `engine/adapter/store/tiered_memory_store.go`
- Modify: `engine/application/usecase/scheduler.go`

**Implementation Details:**

Fallback behavior:
```go
func (s *TieredMemoryStore) Get(ctx context.Context, ns, key string) (any, bool, error) {
    // Try Tier 2 (Redis) first if enabled
    if s.config.Tier2Enabled {
        val, found, err := s.tier2.Get(ctx, ns, key)
        if err != nil {
            // Log warning, don't fail
            s.metrics.RecordFallback("tier2_read_failure")
            log.Warn("Redis read failed, continuing without cached data",
                "namespace", ns, "key", key, "error", err)
        } else if found {
            return val, true, nil
        }
    }

    // Fall through to local or return not found
    return nil, false, nil
}
```

Logging levels:
- First Redis failure: WARN
- Circuit breaker open: ERROR
- Fallback activation: INFO
- Circuit breaker reset: INFO

**Dependencies:** P1-T01, P1-T06

**Estimated Effort:** 0.5 days

**SUCCESS CRITERIA:**
- [ ] Run continues successfully when Redis is stopped mid-execution
- [ ] Warning logged on first Redis failure
- [ ] Error logged when circuit breaker opens
- [ ] Metric `forgegraph_memory_tier2_fallback_total` increments
- [ ] After Redis recovers, circuit breaker closes and Redis resumes
- [ ] Integration test: Stop Redis, verify run completes, restart Redis, verify reconnection

---

#### P1-T11: Add Message Buffer Checkpointing

**Description:** Integrate message buffer state into the existing checkpoint system so that runs can be resumed with full message history.

**Affected Components:** Go Engine

**Files to Modify:**
- `engine/application/usecase/scheduler.go`
- `engine/domain/entity/state.go`

**Implementation Details:**

Checkpoint structure extension:
```go
// In scheduler.saveCheckpoint:
checkpoint := map[string]any{
    "state":          ctx.state.Snapshot(),
    "completed":      ctx.completed,
    "skipped":        ctx.skipped,
    "message_buffer": ctx.messageBuffer.Snapshot(),  // NEW
    "memory_config":  ctx.memoryConfig,              // NEW
}

// In scheduler.restoreFromCheckpoint:
if bufferData, ok := checkpoint["message_buffer"].([]any); ok {
    ctx.messageBuffer.Restore(parseMessages(bufferData))
}
```

**Dependencies:** P1-T02, P1-T03

**Estimated Effort:** 0.5 days

**SUCCESS CRITERIA:**
- [ ] Checkpoint includes serialized message buffer
- [ ] Run resume restores message buffer to pre-pause state
- [ ] Message order is preserved after resume
- [ ] Buffer capacity is restored correctly
- [ ] Integration test: Pause run with 15 messages, resume, verify all 15 present
- [ ] Checkpoint size increase is <10% for typical runs

---

#### P1-T12: Update Documentation and Add Migration Guide

**Description:** Document the new memory system, configuration options, and provide a migration guide for existing deployments.

**Affected Components:** Documentation

**Files to Create:**
- `docs/developer/memory-system.md`
- `docs/user-guide/configuring-memory.md`
- `docs/developer/memory-migration.md`

**Content:**
1. Architecture overview with tier diagram
2. Configuration reference with all options
3. Troubleshooting guide
4. Migration steps for existing deployments
5. Performance tuning recommendations

**Dependencies:** All P1 tasks

**Estimated Effort:** 1 day

**SUCCESS CRITERIA:**
- [ ] Architecture diagram shows all three tiers
- [ ] All configuration options documented with defaults
- [ ] Migration guide tested by applying to fresh deployment
- [ ] Troubleshooting section covers common issues
- [ ] Code examples for custom memory store implementations

---

### 1.3 Integration Points

#### API Contracts

**Memory Configuration API (Django → Frontend):**
```
GET /api/graphs/{graph_id}/memory-config/
Response: {
    "buffer_enabled": true,
    "buffer_size": 20,
    "auto_prepend": true,
    "redis_enabled": false,
    "redis_summary_ttl": 86400,
    "redis_facts_ttl": 604800,
    "vector_enabled": false,
    "vector_top_k": 5
}

PATCH /api/graphs/{graph_id}/memory-config/
Request: { "buffer_size": 50, "redis_enabled": true }
Response: <updated config>
```

**StartRunRequest Extension (Django → Go Engine):**
```protobuf
message StartRunRequest {
    string run_id = 1;
    string graph_json = 2;
    string input_json = 3;
    string callback_url = 4;
    string memory_config_json = 5;  // NEW
    string tenant_id = 6;           // NEW (for multi-tenant isolation)
}
```

**Memory Config JSON Schema:**
```json
{
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
        "tier1": {
            "type": "object",
            "properties": {
                "enabled": { "type": "boolean", "default": true },
                "buffer_size": { "type": "integer", "minimum": 1, "maximum": 200, "default": 20 },
                "auto_prepend": { "type": "boolean", "default": true }
            }
        },
        "tier2": {
            "type": "object",
            "properties": {
                "enabled": { "type": "boolean", "default": false },
                "summary_ttl_seconds": { "type": "integer", "minimum": 60, "default": 86400 },
                "facts_ttl_seconds": { "type": "integer", "minimum": 60, "default": 604800 }
            }
        }
    }
}
```

---

### 1.4 Testing Strategy

#### Unit Tests

| Test File | Coverage |
|-----------|----------|
| `redis_memory_store_test.go` | Basic CRUD, TTL, circuit breaker, tenant isolation |
| `message_buffer_test.go` | Circular behavior, concurrency, snapshot/restore |
| `tiered_memory_store_test.go` | Fallback chain, write to multiple tiers |
| `test_memory_config_model.py` | Django model validation, constraints |
| `MemoryConfigDialog.test.tsx` | Form validation, API integration |

#### Integration Tests

| Test Scenario | Components Involved |
|---------------|---------------------|
| Redis failover | Go Engine + Redis (stopped/started) |
| Multi-tenant isolation | Django + Go Engine + Redis |
| Checkpoint with buffer | Go Engine + PostgreSQL |
| Config propagation | Frontend → Django → Go Engine |

#### End-to-End Tests

| Scenario | Steps |
|----------|-------|
| Full memory flow | 1. Configure graph with memory<br>2. Run with 10 prompt nodes<br>3. Verify buffer contains messages<br>4. Pause and resume<br>5. Verify buffer persists |
| Redis unavailable | 1. Start run<br>2. Stop Redis container<br>3. Continue execution<br>4. Verify fallback logged<br>5. Restart Redis<br>6. Verify reconnection |

#### Performance Benchmarks

| Benchmark | Target | Measurement |
|-----------|--------|-------------|
| MessageBuffer.Push | <100μs | `go test -bench=BenchmarkBufferPush` |
| MessageBuffer.GetAll (100 msgs) | <1ms | `go test -bench=BenchmarkBufferGetAll` |
| RedisMemoryStore.Get | <10ms p99 | Load test with 1000 concurrent requests |
| RedisMemoryStore.Set | <10ms p99 | Load test with 1000 concurrent requests |

---

### 1.5 Rollback Plan

**Feature Flags:**
```python
# Django settings
FEATURE_FLAGS = {
    'MEMORY_TIER1_ENABLED': env.bool('FF_MEMORY_TIER1', True),
    'MEMORY_TIER2_ENABLED': env.bool('FF_MEMORY_TIER2', False),  # Opt-in initially
}
```

**Rollback Steps:**
1. Set `FF_MEMORY_TIER2=false` in environment
2. Restart Django and Go Engine services
3. System uses InMemoryMemoryStore only
4. Existing runs continue (buffer cleared on restart)
5. Redis data preserved but unused

**Data Preservation:**
- Redis data has TTL and will expire naturally
- No migration needed for rollback
- Local buffers are ephemeral, no cleanup needed

---

### 1.6 Documentation Deliverables

| Document | Audience | Content |
|----------|----------|---------|
| `memory-system.md` | Developers | Architecture, implementation details |
| `configuring-memory.md` | Users | How to configure memory depth |
| `memory-api.md` | API consumers | Endpoint reference |
| Code comments | Developers | Inline documentation in Go/Python/TypeScript |

---

## Phase 2: Intelligent Summarization

### 2.1 Overview

**Goals:**
- Implement automatic summarization when buffer exceeds threshold
- Use cost-efficient model for summarization
- Async processing to avoid blocking LLM responses
- Extract and preserve critical facts during summarization

**Dependencies:** Phase 1 complete

**Complexity:** M (Medium)

**Key Risks and Mitigations:**

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Summarization quality loss | Medium | Medium | Fact extraction preserves key information |
| LLM cost for summarization | Medium | Low | Use cheap model (e.g., Claude Haiku) |
| Async processing complexity | Medium | Medium | Use Go channels with worker pool |
| Summarization latency | Low | Low | Background processing, don't block main flow |

---

### 2.2 Task List

#### P2-T01: Design Summarization Service Interface

**Description:** Define the interface for the summarization service that will compress message buffers into concise summaries.

**Affected Components:** Go Engine

**Files to Create:**
- `engine/application/port/summarizer.go`
- `engine/domain/entity/summary.go`

**Implementation Details:**

```go
// Port interface
type Summarizer interface {
    Summarize(ctx context.Context, messages []entity.Message, opts SummarizeOptions) (*Summary, error)
    ExtractFacts(ctx context.Context, messages []entity.Message) ([]Fact, error)
}

type SummarizeOptions struct {
    MaxOutputTokens int
    PreserveFacts   bool
    Model           string  // e.g., "claude-haiku"
}

// Domain entities
type Summary struct {
    ID           string
    Content      string
    SourceCount  int       // Number of messages summarized
    FactsExtracted []Fact
    CreatedAt    time.Time
}

type Fact struct {
    Key       string  // e.g., "user_name", "preferred_language"
    Value     string
    Confidence float64
    SourceNodeID string
}
```

**Dependencies:** None

**Estimated Effort:** 0.5 days

**SUCCESS CRITERIA:**
- [ ] Interface defined with clear contracts
- [ ] Summary entity captures all metadata needed for retrieval
- [ ] Fact entity supports confidence scoring
- [ ] Interface allows pluggable LLM backends

---

#### P2-T02: Implement LLM-Based Summarizer

**Description:** Create the summarization implementation using a cost-efficient LLM (Claude Haiku or similar).

**Affected Components:** Go Engine

**Files to Create:**
- `engine/adapter/summarizer/llm_summarizer.go`
- `engine/adapter/summarizer/llm_summarizer_test.go`

**Implementation Details:**

```go
type LLMSummarizer struct {
    client    LLMClient
    model     string
    maxRetries int
}

const summarizePrompt = `Summarize the following conversation concisely, preserving:
1. Key decisions made
2. Important facts mentioned
3. Current context and goals

Conversation:
{{messages}}

Output a JSON object:
{
  "summary": "...",
  "facts": [{"key": "...", "value": "...", "confidence": 0.0-1.0}]
}`

func (s *LLMSummarizer) Summarize(ctx context.Context, msgs []Message, opts SummarizeOptions) (*Summary, error) {
    // 1. Format messages into prompt
    // 2. Call LLM with cheap model
    // 3. Parse JSON response
    // 4. Return Summary with extracted facts
}
```

**Model Selection:**
- Default: Claude Haiku for cost efficiency
- Configurable via `SummarizeOptions.Model`
- Retry with exponential backoff on failures

**Dependencies:** P2-T01

**Estimated Effort:** 1.5 days

**SUCCESS CRITERIA:**
- [ ] Summarizer produces coherent summaries
- [ ] Facts extracted with confidence scores
- [ ] API cost for summarizing 50 messages is <$0.01
- [ ] Summarization completes in <5 seconds for 50 messages
- [ ] Retry logic handles transient LLM failures
- [ ] Unit test with mocked LLM client passes
- [ ] Integration test with real LLM produces valid output

---

#### P2-T03: Create Async Summarization Worker

**Description:** Implement background worker that processes summarization requests without blocking the main execution flow.

**Affected Components:** Go Engine

**Files to Create:**
- `engine/application/usecase/summarization_worker.go`
- `engine/application/usecase/summarization_worker_test.go`

**Implementation Details:**

```go
type SummarizationWorker struct {
    summarizer port.Summarizer
    store      port.MemoryStore
    queue      chan SummarizationRequest
    workerPool int
    wg         sync.WaitGroup
}

type SummarizationRequest struct {
    RunID     string
    TenantID  string
    Messages  []entity.Message
    Callback  func(*entity.Summary, error)
}

func (w *SummarizationWorker) Start(ctx context.Context) {
    for i := 0; i < w.workerPool; i++ {
        w.wg.Add(1)
        go w.worker(ctx)
    }
}

func (w *SummarizationWorker) worker(ctx context.Context) {
    defer w.wg.Done()
    for {
        select {
        case req := <-w.queue:
            summary, err := w.summarizer.Summarize(ctx, req.Messages, DefaultOpts)
            if err == nil {
                // Store summary in Redis
                w.store.Set(ctx, req.TenantID, summaryKey(req.RunID), summary, 86400)
            }
            if req.Callback != nil {
                req.Callback(summary, err)
            }
        case <-ctx.Done():
            return
        }
    }
}
```

**Dependencies:** P2-T02

**Estimated Effort:** 1 day

**SUCCESS CRITERIA:**
- [ ] Worker processes requests asynchronously
- [ ] Main execution flow not blocked during summarization
- [ ] Worker pool configurable (default: 2)
- [ ] Queue has bounded size with backpressure
- [ ] Worker gracefully shuts down on context cancellation
- [ ] Callback invoked with result or error
- [ ] Unit test verifies async behavior

---

#### P2-T04: Implement Smart Trigger for Summarization

**Description:** Add logic to trigger summarization based on buffer size threshold rather than fixed turn count.

**Affected Components:** Go Engine

**Files to Modify:**
- `engine/adapter/executor/prompt_executor.go`
- `engine/application/usecase/scheduler.go`

**Implementation Details:**

```go
type SummarizationConfig struct {
    Enabled           bool
    TriggerThreshold  int     // Trigger when buffer reaches this size
    KeepRecentCount   int     // Keep this many recent messages after summarization
    CooldownMessages  int     // Don't summarize again until this many new messages
}

// In prompt executor, after adding message to buffer:
func (e *PromptExecutor) maybeRequestSummarization(ctx *runContext) {
    cfg := ctx.memoryConfig.Summarization
    if !cfg.Enabled {
        return
    }

    bufferSize := ctx.messageBuffer.Count()
    if bufferSize < cfg.TriggerThreshold {
        return
    }

    // Check cooldown
    if ctx.messagesSinceSummary < cfg.CooldownMessages {
        return
    }

    // Get messages to summarize (all except recent)
    toSummarize := ctx.messageBuffer.GetFirst(bufferSize - cfg.KeepRecentCount)

    // Queue async summarization
    e.summarizationWorker.Submit(SummarizationRequest{
        RunID:    ctx.runID,
        TenantID: ctx.tenantID,
        Messages: toSummarize,
        Callback: func(summary *Summary, err error) {
            if err == nil {
                ctx.currentSummary = summary
                ctx.messageBuffer.RemoveFirst(len(toSummarize))
                ctx.messagesSinceSummary = 0
            }
        },
    })
}
```

**Configuration Defaults:**
- `TriggerThreshold`: 30 messages
- `KeepRecentCount`: 10 messages
- `CooldownMessages`: 15 messages

**Dependencies:** P2-T03

**Estimated Effort:** 1 day

**SUCCESS CRITERIA:**
- [ ] Summarization triggered at threshold (not earlier)
- [ ] Recent messages preserved after summarization
- [ ] Cooldown prevents excessive summarization
- [ ] Configuration overridable per-graph
- [ ] Metrics track summarization triggers
- [ ] Integration test: 50 messages triggers 1 summarization, keeps last 10

---

#### P2-T05: Store and Retrieve Summaries in Redis

**Description:** Implement storage pattern for summaries in Redis Tier 2, including versioning for multiple summarization rounds.

**Affected Components:** Go Engine

**Files to Modify:**
- `engine/adapter/store/redis_memory_store.go`

**Implementation Details:**

Key structure:
```
forgegraph:tenant:{tenant_id}:summary:{run_id}:current  → latest summary
forgegraph:tenant:{tenant_id}:summary:{run_id}:v{n}     → historical summaries
forgegraph:tenant:{tenant_id}:facts:{run_id}:{fact_key} → extracted facts
```

```go
func (s *RedisMemoryStore) StoreSummary(ctx context.Context, tenantID, runID string, summary *entity.Summary) error {
    // 1. Get current version number
    version := s.incrementVersion(ctx, tenantID, runID)

    // 2. Store as versioned backup
    versionKey := fmt.Sprintf("summary:%s:v%d", runID, version)
    s.Set(ctx, tenantID, versionKey, summary, 604800)  // 7 days

    // 3. Store as current
    currentKey := fmt.Sprintf("summary:%s:current", runID)
    s.Set(ctx, tenantID, currentKey, summary, 604800)

    // 4. Store extracted facts individually
    for _, fact := range summary.FactsExtracted {
        factKey := fmt.Sprintf("facts:%s:%s", runID, fact.Key)
        s.Set(ctx, tenantID, factKey, fact.Value, 604800)
    }

    return nil
}
```

**Dependencies:** P1-T01

**Estimated Effort:** 0.5 days

**SUCCESS CRITERIA:**
- [ ] Summaries stored with 7-day TTL
- [ ] Version history preserved (last 5 versions)
- [ ] Facts stored as individual keys for fast lookup
- [ ] `GetSummary(runID)` returns current summary
- [ ] `GetFact(runID, factKey)` returns specific fact
- [ ] Old versions expire after TTL

---

#### P2-T06: Prepend Summaries to Prompts

**Description:** Modify prompt construction to include existing summaries before the recent message buffer.

**Affected Components:** Go Engine

**Files to Modify:**
- `engine/adapter/executor/prompt_executor.go`

**Implementation Details:**

Prompt structure:
```
[System prompt from node config]

[Previous conversation summary]
Summary of earlier conversation:
{summary.Content}

Key facts established:
- {fact.Key}: {fact.Value}
...

[Recent messages from buffer]
User: ...
Assistant: ...
...

[Current user input]
```

```go
func (e *PromptExecutor) buildPromptWithMemory(ctx *runContext, basePrompt string, currentInput string) string {
    var parts []string
    parts = append(parts, basePrompt)

    // Add summary if exists
    if summary := ctx.currentSummary; summary != nil {
        parts = append(parts, formatSummaryBlock(summary))
    }

    // Add recent messages
    if ctx.memoryConfig.Tier1.AutoPrepend {
        messages := ctx.messageBuffer.GetAll()
        parts = append(parts, formatMessagesBlock(messages))
    }

    // Add current input
    parts = append(parts, currentInput)

    return strings.Join(parts, "\n\n")
}
```

**Dependencies:** P2-T05

**Estimated Effort:** 0.5 days

**SUCCESS CRITERIA:**
- [ ] Summary appears before recent messages in prompt
- [ ] Facts formatted as key-value list
- [ ] Empty summary/facts sections omitted
- [ ] Prompt structure verified by inspection in logs
- [ ] Integration test: After summarization, next prompt includes summary

---

#### P2-T07: Add Summarization Configuration to Django/Frontend

**Description:** Extend memory configuration to include summarization settings.

**Affected Components:** Django Backend, Frontend

**Files to Modify:**
- `backend/infrastructure/orm/models.py`
- `backend/infrastructure/orm/migrations/0012_summarization_config.py`
- `frontend/components/graph-editor/dialogs/MemoryConfigDialog.tsx`

**Implementation Details:**

Django model extension:
```python
class MemoryConfiguration(models.Model):
    # ... existing fields ...

    # Summarization settings
    summarization_enabled = models.BooleanField(default=False)
    summarization_threshold = models.PositiveIntegerField(default=30)
    summarization_keep_recent = models.PositiveIntegerField(default=10)
    summarization_model = models.CharField(max_length=50, default='claude-haiku')
```

Frontend addition:
```typescript
// In Advanced section
<FormField label="Enable Summarization" help="Automatically summarize older messages">
  <Switch checked={summarizationEnabled} onChange={...} />
</FormField>

{summarizationEnabled && (
  <>
    <FormField label="Summarize after" help="Number of messages before summarizing">
      <NumberInput value={threshold} onChange={...} min={20} max={100} />
    </FormField>
    <FormField label="Keep recent" help="Messages to preserve after summarization">
      <NumberInput value={keepRecent} onChange={...} min={5} max={30} />
    </FormField>
  </>
)}
```

**Dependencies:** P1-T04, P1-T07

**Estimated Effort:** 1 day

**SUCCESS CRITERIA:**
- [ ] Migration adds new fields with defaults
- [ ] API serializes summarization settings
- [ ] Frontend shows summarization toggle in Advanced section
- [ ] Validation: threshold >= keepRecent + 10
- [ ] Configuration passed to engine via memory_config_json

---

#### P2-T08: Implement Cost Tracking for Summarization

**Description:** Track LLM costs associated with summarization to help users understand memory system expenses.

**Affected Components:** Go Engine, Django Backend

**Files to Create:**
- `engine/adapter/summarizer/cost_tracker.go`
- `backend/domain/entities/memory_usage.py`

**Implementation Details:**

```go
type CostTracker struct {
    mu      sync.Mutex
    totals  map[string]*TenantCost  // keyed by tenant ID
}

type TenantCost struct {
    SummarizationCalls   int64
    SummarizationTokens  int64
    EstimatedCostUSD     float64
}

// Pricing (configurable)
var modelPricing = map[string]struct{ Input, Output float64 }{
    "claude-haiku": {0.00025, 0.00125},  // per 1K tokens
}
```

Django reporting:
```python
class MemoryUsageLog(models.Model):
    tenant_id = models.UUIDField()
    date = models.DateField()
    summarization_calls = models.PositiveIntegerField(default=0)
    summarization_tokens = models.PositiveIntegerField(default=0)
    estimated_cost_usd = models.DecimalField(max_digits=10, decimal_places=6)
```

**Dependencies:** P2-T02

**Estimated Effort:** 0.5 days

**SUCCESS CRITERIA:**
- [ ] Cost tracked per tenant
- [ ] Daily usage logged to Django
- [ ] API endpoint: `GET /api/memory/usage/` returns cost data
- [ ] Metrics exposed for Prometheus
- [ ] Dashboard shows monthly summarization costs

---

### 2.3 Integration Points

**Summarization Worker ↔ Scheduler:**
- Worker started with Scheduler
- Requests queued via channel
- Callbacks update run context

**Summary Storage (Redis):**
```
SET forgegraph:tenant:{tenant_id}:summary:{run_id}:current <JSON> EX 604800
SET forgegraph:tenant:{tenant_id}:facts:{run_id}:{fact_key} <value> EX 604800
```

**Configuration Extension:**
```json
{
    "tier1": { ... },
    "tier2": { ... },
    "summarization": {
        "enabled": true,
        "threshold": 30,
        "keep_recent": 10,
        "model": "claude-haiku"
    }
}
```

---

### 2.4 Testing Strategy

#### Unit Tests

| Test | Description |
|------|-------------|
| `TestLLMSummarizer_ParseResponse` | JSON parsing of LLM output |
| `TestSummarizationWorker_Async` | Verify non-blocking behavior |
| `TestSmartTrigger_Threshold` | Trigger at exact threshold |
| `TestSmartTrigger_Cooldown` | Respect cooldown period |

#### Integration Tests

| Test | Description |
|------|-------------|
| `TestSummarization_EndToEnd` | 50 messages → summary stored |
| `TestPromptWithSummary` | Prompt includes summary block |
| `TestFactExtraction` | Facts stored and retrievable |

---

### 2.5 Rollback Plan

**Feature Flag:**
```python
FEATURE_FLAGS = {
    'MEMORY_SUMMARIZATION_ENABLED': env.bool('FF_MEMORY_SUMMARIZATION', False),
}
```

**Rollback:**
1. Set `FF_MEMORY_SUMMARIZATION=false`
2. Restart services
3. Summarization stops; buffers grow until limit
4. Existing summaries remain in Redis until TTL expiry

---

### 2.6 Documentation Deliverables

| Document | Content |
|----------|---------|
| `summarization-guide.md` | How summarization works, configuration |
| `cost-estimation.md` | Expected costs per message volume |
| API updates | Summarization config endpoints |

---

## Phase 3: Semantic Long-Term Memory

### 3.1 Overview

**Goals:**
- Implement PostgreSQL + pgvector for semantic search
- Create embedding pipeline for conversation chunks
- Implement hybrid retrieval (semantic + recency)
- Integrate with Django for embedding management

**Dependencies:** Phase 2 complete

**Complexity:** XL (Extra Large)

**Key Risks and Mitigations:**

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| pgvector performance at scale | Medium | High | Proper indexing, query optimization |
| Embedding cost | Medium | Medium | Batch processing, caching |
| Chunking quality | Medium | Medium | Configurable strategies, testing |
| Search latency | Medium | Medium | Index tuning, result caching |

---

### 3.2 Task List

#### P3-T01: Add pgvector Extension to PostgreSQL

**Description:** Configure PostgreSQL with pgvector extension for vector similarity search.

**Affected Components:** Infrastructure, Django Backend

**Files to Modify:**
- `docker-compose.yml`
- Create: `backend/infrastructure/orm/migrations/0013_pgvector_setup.py`

**Implementation Details:**

Docker Compose:
```yaml
postgres:
  image: pgvector/pgvector:pg16
  # ... existing config
```

Migration:
```python
from django.db import migrations

class Migration(migrations.Migration):
    operations = [
        migrations.RunSQL(
            "CREATE EXTENSION IF NOT EXISTS vector;",
            reverse_sql="DROP EXTENSION IF EXISTS vector;"
        ),
    ]
```

**Dependencies:** None

**Estimated Effort:** 0.5 days

**SUCCESS CRITERIA:**
- [ ] pgvector extension installed
- [ ] `SELECT vector_dims(...)` SQL works
- [ ] Docker image builds successfully
- [ ] Existing data preserved after migration

---

#### P3-T02: Create Memory Chunk Django Model

**Description:** Define the model for storing conversation chunks with their embeddings.

**Affected Components:** Django Backend

**Files to Create:**
- `backend/infrastructure/orm/migrations/0014_memory_chunks.py`
- `backend/domain/entities/memory_chunk.py`

**Implementation Details:**

```python
from pgvector.django import VectorField

class MemoryChunk(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    tenant_id = models.UUIDField(db_index=True)

    # Scope
    agent_id = models.UUIDField(null=True, db_index=True)
    run_id = models.UUIDField(null=True, db_index=True)
    session_id = models.UUIDField(null=True, db_index=True)

    # Content
    content = models.TextField()
    chunk_type = models.CharField(max_length=20)  # 'message', 'summary', 'fact'
    metadata = models.JSONField(default=dict)

    # Embedding
    embedding = VectorField(dimensions=1536)  # OpenAI ada-002 compatible
    embedding_model = models.CharField(max_length=50)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    source_timestamp = models.DateTimeField()  # When original content was created

    class Meta:
        db_table = 'memory_chunks'
        indexes = [
            models.Index(fields=['tenant_id', 'agent_id']),
            models.Index(fields=['tenant_id', 'session_id']),
            # Vector index added separately
        ]
```

Vector index:
```sql
CREATE INDEX memory_chunks_embedding_idx ON memory_chunks
USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

**Dependencies:** P3-T01

**Estimated Effort:** 1 day

**SUCCESS CRITERIA:**
- [ ] Model created with vector field
- [ ] IVFFlat index created for fast similarity search
- [ ] Migrations apply without errors
- [ ] Test insert/query with sample embedding

---

#### P3-T03: Implement Embedding Service

**Description:** Create a service to generate embeddings for text chunks using an embedding API.

**Affected Components:** Django Backend

**Files to Create:**
- `backend/application/services/embedding_service.py`
- `backend/adapters/embedding/openai_embedder.py`
- `backend/adapters/embedding/voyage_embedder.py`

**Implementation Details:**

```python
# Port
class EmbeddingService(ABC):
    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        pass

    @abstractmethod
    def dimension(self) -> int:
        pass

# OpenAI implementation
class OpenAIEmbedder(EmbeddingService):
    def __init__(self, model: str = "text-embedding-ada-002"):
        self.client = OpenAI()
        self.model = model
        self._dimension = 1536

    async def embed(self, texts: list[str]) -> list[list[float]]:
        response = await self.client.embeddings.create(
            model=self.model,
            input=texts
        )
        return [e.embedding for e in response.data]

    def dimension(self) -> int:
        return self._dimension
```

**Batch Processing:**
- Batch up to 100 texts per API call
- Async processing with rate limiting
- Cache embeddings for duplicate content (hash-based)

**Dependencies:** None

**Estimated Effort:** 1.5 days

**SUCCESS CRITERIA:**
- [ ] OpenAI embedder generates 1536-dim vectors
- [ ] Batch processing handles 100+ texts efficiently
- [ ] Rate limiting prevents API throttling
- [ ] Embedding cache reduces duplicate API calls
- [ ] Unit test with mocked API passes
- [ ] Integration test with real API produces valid embeddings

---

#### P3-T04: Create Chunking Strategy Service

**Description:** Implement strategies for breaking conversations into semantically meaningful chunks.

**Affected Components:** Django Backend

**Files to Create:**
- `backend/application/services/chunking_service.py`

**Implementation Details:**

```python
class ChunkingStrategy(ABC):
    @abstractmethod
    def chunk(self, messages: list[Message]) -> list[Chunk]:
        pass

class TurnBasedChunking(ChunkingStrategy):
    """Chunk by conversation turns (user + assistant pairs)"""
    def __init__(self, turns_per_chunk: int = 3, overlap_turns: int = 1):
        self.turns_per_chunk = turns_per_chunk
        self.overlap_turns = overlap_turns

class TopicBasedChunking(ChunkingStrategy):
    """Chunk by detected topic boundaries"""
    def __init__(self, min_chunk_size: int = 500, max_chunk_size: int = 2000):
        self.min_size = min_chunk_size
        self.max_size = max_chunk_size

class SlidingWindowChunking(ChunkingStrategy):
    """Fixed size sliding window with overlap"""
    def __init__(self, window_size: int = 1000, overlap: int = 200):
        self.window_size = window_size
        self.overlap = overlap
```

Default strategy: `TurnBasedChunking(turns_per_chunk=3, overlap_turns=1)`

**Dependencies:** None

**Estimated Effort:** 1 day

**SUCCESS CRITERIA:**
- [ ] TurnBasedChunking groups user+assistant pairs correctly
- [ ] Overlap maintains context across chunk boundaries
- [ ] Configurable chunk sizes
- [ ] Empty/short messages handled gracefully
- [ ] Unit tests for all chunking strategies

---

#### P3-T05: Implement Async Embedding Pipeline

**Description:** Create a background worker that processes messages, chunks them, generates embeddings, and stores in the vector database.

**Affected Components:** Django Backend

**Files to Create:**
- `backend/application/services/embedding_pipeline.py`
- `backend/adapters/worker/embedding_worker.py`

**Implementation Details:**

```python
class EmbeddingPipeline:
    def __init__(
        self,
        chunker: ChunkingStrategy,
        embedder: EmbeddingService,
        repository: MemoryChunkRepository
    ):
        self.chunker = chunker
        self.embedder = embedder
        self.repository = repository
        self.queue = asyncio.Queue()

    async def process_messages(
        self,
        tenant_id: UUID,
        agent_id: UUID,
        run_id: UUID,
        messages: list[Message]
    ) -> list[MemoryChunk]:
        # 1. Chunk messages
        chunks = self.chunker.chunk(messages)

        # 2. Extract text from chunks
        texts = [c.content for c in chunks]

        # 3. Generate embeddings (batched)
        embeddings = await self.embedder.embed(texts)

        # 4. Create and store MemoryChunk entities
        memory_chunks = []
        for chunk, embedding in zip(chunks, embeddings):
            mc = MemoryChunk(
                tenant_id=tenant_id,
                agent_id=agent_id,
                run_id=run_id,
                content=chunk.content,
                embedding=embedding,
                ...
            )
            memory_chunks.append(mc)

        await self.repository.bulk_create(memory_chunks)
        return memory_chunks
```

Worker integration:
- Celery task for async processing
- Triggered after summarization or on buffer overflow
- Retry logic with exponential backoff

**Dependencies:** P3-T03, P3-T04

**Estimated Effort:** 2 days

**SUCCESS CRITERIA:**
- [ ] Pipeline processes messages end-to-end
- [ ] Chunks stored with embeddings in PostgreSQL
- [ ] Celery task queued and processed asynchronously
- [ ] Batch processing handles 100+ messages
- [ ] Retry logic handles transient failures
- [ ] Integration test: 50 messages → N chunks stored

---

#### P3-T06: Implement Vector Similarity Search

**Description:** Create a search service that retrieves relevant memory chunks based on semantic similarity.

**Affected Components:** Django Backend

**Files to Create:**
- `backend/application/services/vector_search_service.py`
- `backend/adapters/repository/memory_chunk_repository.py`

**Implementation Details:**

```python
class VectorSearchService:
    def __init__(
        self,
        embedder: EmbeddingService,
        repository: MemoryChunkRepository
    ):
        self.embedder = embedder
        self.repository = repository

    async def search(
        self,
        query: str,
        tenant_id: UUID,
        agent_id: UUID | None = None,
        top_k: int = 5,
        threshold: float = 0.7,
        recency_weight: float = 0.2
    ) -> list[SearchResult]:
        # 1. Embed query
        query_embedding = (await self.embedder.embed([query]))[0]

        # 2. Vector similarity search
        results = await self.repository.similarity_search(
            embedding=query_embedding,
            tenant_id=tenant_id,
            agent_id=agent_id,
            limit=top_k * 2  # Get extra for hybrid ranking
        )

        # 3. Hybrid ranking (semantic + recency)
        ranked = self._hybrid_rank(results, recency_weight)

        # 4. Filter by threshold and return top_k
        return [r for r in ranked if r.score >= threshold][:top_k]

    def _hybrid_rank(self, results, recency_weight):
        now = datetime.utcnow()
        for r in results:
            age_hours = (now - r.source_timestamp).total_seconds() / 3600
            recency_score = math.exp(-age_hours / 168)  # Decay over 1 week
            r.score = (1 - recency_weight) * r.similarity + recency_weight * recency_score
        return sorted(results, key=lambda r: r.score, reverse=True)
```

SQL for similarity search:
```sql
SELECT *, 1 - (embedding <=> %s) as similarity
FROM memory_chunks
WHERE tenant_id = %s AND agent_id = %s
ORDER BY embedding <=> %s
LIMIT %s;
```

**Dependencies:** P3-T02, P3-T03

**Estimated Effort:** 1.5 days

**SUCCESS CRITERIA:**
- [ ] Search returns semantically relevant chunks
- [ ] Cosine similarity computed correctly
- [ ] Hybrid ranking boosts recent content
- [ ] Query latency <100ms for 10K chunks
- [ ] Threshold filtering works correctly
- [ ] Integration test: Query returns relevant chunks

---

#### P3-T07: Create Memory Retrieval gRPC Endpoint

**Description:** Add gRPC endpoint for Go engine to retrieve relevant memories during prompt execution.

**Affected Components:** Django Backend, Go Engine

**Files to Modify:**
- `engine/proto/engine.proto`
- Regenerate proto files
- Create: `backend/adapters/grpc/memory_service.py`

**Implementation Details:**

Proto definition:
```protobuf
message RetrieveMemoryRequest {
    string tenant_id = 1;
    string agent_id = 2;
    string query = 3;
    int32 top_k = 4;
    float threshold = 5;
}

message MemoryChunk {
    string id = 1;
    string content = 2;
    float score = 3;
    string chunk_type = 4;
    int64 timestamp = 5;
}

message RetrieveMemoryResponse {
    repeated MemoryChunk chunks = 1;
}

service MemoryService {
    rpc RetrieveMemory(RetrieveMemoryRequest) returns (RetrieveMemoryResponse);
}
```

Go client:
```go
type MemoryClient interface {
    RetrieveMemory(ctx context.Context, req *RetrieveMemoryRequest) (*RetrieveMemoryResponse, error)
}
```

**Dependencies:** P3-T06

**Estimated Effort:** 1 day

**SUCCESS CRITERIA:**
- [ ] gRPC endpoint implemented and tested
- [ ] Go client generated from proto
- [ ] Engine can call Django for memory retrieval
- [ ] Timeout handling (100ms default)
- [ ] Fallback when service unavailable
- [ ] Integration test: Engine retrieves memories via gRPC

---

#### P3-T08: Integrate Vector Memory into Prompt Executor

**Description:** Modify prompt executor to retrieve and include relevant memories in prompts when vector memory is enabled.

**Affected Components:** Go Engine

**Files to Modify:**
- `engine/adapter/executor/prompt_executor.go`

**Implementation Details:**

```go
func (e *PromptExecutor) buildPromptWithMemory(ctx *runContext, basePrompt, currentInput string) string {
    var parts []string
    parts = append(parts, basePrompt)

    // Add summary if exists (Tier 2)
    if summary := ctx.currentSummary; summary != nil {
        parts = append(parts, formatSummaryBlock(summary))
    }

    // Add relevant memories (Tier 3) - NEW
    if ctx.memoryConfig.Tier3.Enabled {
        memories, err := e.memoryClient.RetrieveMemory(ctx.ctx, &RetrieveMemoryRequest{
            TenantId:  ctx.tenantID,
            AgentId:   ctx.agentID,
            Query:     currentInput,
            TopK:      int32(ctx.memoryConfig.Tier3.TopK),
            Threshold: float32(ctx.memoryConfig.Tier3.Threshold),
        })
        if err != nil {
            log.Warn("Failed to retrieve memories", "error", err)
        } else if len(memories.Chunks) > 0 {
            parts = append(parts, formatMemoriesBlock(memories.Chunks))
        }
    }

    // Add recent messages (Tier 1)
    if ctx.memoryConfig.Tier1.AutoPrepend {
        messages := ctx.messageBuffer.GetAll()
        parts = append(parts, formatMessagesBlock(messages))
    }

    parts = append(parts, currentInput)
    return strings.Join(parts, "\n\n")
}

func formatMemoriesBlock(chunks []*MemoryChunk) string {
    var sb strings.Builder
    sb.WriteString("Relevant information from previous conversations:\n")
    for _, c := range chunks {
        sb.WriteString(fmt.Sprintf("- %s\n", c.Content))
    }
    return sb.String()
}
```

**Dependencies:** P3-T07

**Estimated Effort:** 1 day

**SUCCESS CRITERIA:**
- [ ] Vector memories included in prompts when enabled
- [ ] Memories formatted appropriately
- [ ] Retrieval failure logged but doesn't break execution
- [ ] Integration test: Prompt includes retrieved memories
- [ ] Latency overhead <100ms

---

#### P3-T09: Add Vector Memory Configuration

**Description:** Extend configuration model and UI for vector memory settings.

**Affected Components:** Django Backend, Frontend

**Files to Modify:**
- `backend/infrastructure/orm/models.py`
- `backend/infrastructure/orm/migrations/0015_vector_config.py`
- `frontend/components/graph-editor/dialogs/MemoryConfigDialog.tsx`

**Implementation Details:**

Django:
```python
class MemoryConfiguration(models.Model):
    # ... existing fields ...

    # Tier 3: Vector
    vector_enabled = models.BooleanField(default=False)
    vector_top_k = models.PositiveIntegerField(default=5)
    vector_threshold = models.FloatField(default=0.7)
    vector_recency_weight = models.FloatField(default=0.2)
    embedding_model = models.CharField(max_length=50, default='text-embedding-ada-002')
```

Frontend:
```typescript
// In Memory Configuration dialog, new section
<Accordion title="Long-Term Memory (Vector Search)">
  <FormField label="Enable semantic search">
    <Switch checked={vectorEnabled} onChange={...} />
  </FormField>

  {vectorEnabled && (
    <>
      <FormField label="Results to retrieve" help="Number of relevant memories to include">
        <NumberInput value={topK} onChange={...} min={1} max={20} />
      </FormField>
      <FormField label="Relevance threshold" help="Minimum similarity score (0-1)">
        <Slider value={threshold} onChange={...} min={0.5} max={0.95} step={0.05} />
      </FormField>
    </>
  )}
</Accordion>
```

**Dependencies:** P1-T04, P1-T07

**Estimated Effort:** 1 day

**SUCCESS CRITERIA:**
- [ ] Migration adds vector config fields
- [ ] API includes vector settings in response
- [ ] Frontend shows vector configuration section
- [ ] Validation: threshold between 0.5 and 0.99
- [ ] Configuration passed to engine

---

#### P3-T10: Implement Memory Garbage Collection

**Description:** Create background job to clean up old memory chunks and manage storage growth.

**Affected Components:** Django Backend

**Files to Create:**
- `backend/application/services/memory_gc.py`
- `backend/adapters/worker/gc_worker.py`

**Implementation Details:**

```python
class MemoryGarbageCollector:
    def __init__(self, repository: MemoryChunkRepository):
        self.repository = repository

    async def cleanup_deleted_users(self, batch_size: int = 1000):
        """Remove chunks for deleted users"""
        deleted_tenant_ids = await self._get_deleted_tenant_ids()
        for tenant_id in deleted_tenant_ids:
            await self.repository.delete_by_tenant(tenant_id, batch_size)

    async def cleanup_old_chunks(
        self,
        max_age_days: int = 90,
        batch_size: int = 1000
    ):
        """Remove chunks older than max_age_days"""
        cutoff = datetime.utcnow() - timedelta(days=max_age_days)
        await self.repository.delete_older_than(cutoff, batch_size)

    async def compact_indices(self):
        """Rebuild vector indices for performance"""
        await self.repository.reindex()
```

Celery beat schedule:
```python
CELERY_BEAT_SCHEDULE = {
    'memory-gc-daily': {
        'task': 'memory.gc.cleanup',
        'schedule': crontab(hour=3, minute=0),  # 3 AM daily
    },
}
```

**Dependencies:** P3-T02

**Estimated Effort:** 1 day

**SUCCESS CRITERIA:**
- [ ] Deleted user chunks removed within 24 hours
- [ ] Old chunks cleaned based on retention policy
- [ ] Batch processing prevents memory spikes
- [ ] Index compaction improves query performance
- [ ] Metrics track storage usage and cleanup

---

### 3.3 Integration Points

**Django ↔ PostgreSQL (pgvector):**
- Vector storage and similarity search
- IVFFlat index for approximate nearest neighbor

**Go Engine ↔ Django (gRPC):**
```protobuf
service MemoryService {
    rpc RetrieveMemory(RetrieveMemoryRequest) returns (RetrieveMemoryResponse);
}
```

**Embedding Pipeline Flow:**
```
Messages → Chunking → Embedding API → PostgreSQL storage
                                           ↓
                                    Vector search
```

---

### 3.4 Testing Strategy

#### Unit Tests

| Test | Description |
|------|-------------|
| `TestChunking_TurnBased` | Correct grouping of turns |
| `TestEmbedding_Batching` | Batch API calls |
| `TestVectorSearch_Ranking` | Hybrid ranking |
| `TestGC_OldChunks` | Age-based cleanup |

#### Integration Tests

| Test | Description |
|------|-------------|
| `TestEmbeddingPipeline_EndToEnd` | Messages → stored chunks |
| `TestVectorSearch_Real` | Search with real embeddings |
| `TestGRPC_MemoryRetrieval` | Engine → Django → response |

#### Performance Benchmarks

| Benchmark | Target |
|-----------|--------|
| Vector search (10K chunks) | <100ms p99 |
| Embedding batch (100 texts) | <5s |
| Index rebuild | <1 hour for 1M chunks |

---

### 3.5 Rollback Plan

**Feature Flag:**
```python
FEATURE_FLAGS = {
    'MEMORY_VECTOR_ENABLED': env.bool('FF_MEMORY_VECTOR', False),
}
```

**Rollback:**
1. Set `FF_MEMORY_VECTOR=false`
2. Restart services
3. Vector search disabled; Tier 1+2 continue working
4. Chunk data preserved in PostgreSQL
5. Embedding pipeline pauses

---

### 3.6 Documentation Deliverables

| Document | Content |
|----------|---------|
| `vector-memory-guide.md` | Setup, configuration, tuning |
| `embedding-models.md` | Supported models, costs |
| `chunking-strategies.md` | Available strategies |

---

## Phase 4: Advanced Features & Optimization

### 4.1 Overview

**Goals:**
- Implement token-aware buffer limits
- Enable cross-session memory sharing
- Add memory analytics and insights
- Performance optimization and tuning

**Dependencies:** Phase 3 complete

**Complexity:** L (Large)

**Key Risks and Mitigations:**

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Token counting overhead | Medium | Low | Lazy counting, caching |
| Cross-session consistency | Medium | Medium | Clear scope rules |
| Analytics privacy | Low | High | Aggregated metrics only |

---

### 4.2 Task List

#### P4-T01: Implement Token-Aware Buffer Limits

**Description:** Add optional token counting to buffer management so limits can be specified in tokens rather than messages.

**Affected Components:** Go Engine

**Files to Create:**
- `engine/domain/service/token_counter.go`
- Modify: `engine/domain/entity/message_buffer.go`

**Implementation Details:**

```go
type TokenCounter interface {
    Count(text string) int
    CountMessages(msgs []Message) int
}

// tiktoken-go based implementation
type TiktokenCounter struct {
    encoding *tiktoken.Encoding
}

func (t *TiktokenCounter) Count(text string) int {
    tokens := t.encoding.Encode(text, nil, nil)
    return len(tokens)
}

// Extended buffer with token awareness
type TokenAwareBuffer struct {
    *MessageBuffer
    counter      TokenCounter
    maxTokens    int
    currentTokens int
}

func (b *TokenAwareBuffer) Push(msg Message) {
    tokens := b.counter.Count(msg.Content)

    // Evict old messages until under limit
    for b.currentTokens + tokens > b.maxTokens && b.count > 0 {
        evicted := b.evictOldest()
        b.currentTokens -= b.counter.Count(evicted.Content)
    }

    b.MessageBuffer.Push(msg)
    b.currentTokens += tokens
}
```

**Dependencies:** None

**Estimated Effort:** 1.5 days

**SUCCESS CRITERIA:**
- [ ] Token counting matches tiktoken output
- [ ] Buffer evicts based on token limit when configured
- [ ] Token counting overhead <1ms per message
- [ ] Cached token counts avoid recomputation
- [ ] Falls back to message count if token counting fails
- [ ] Unit test: Buffer with 1000 token limit evicts correctly

---

#### P4-T02: Implement Cross-Session Memory

**Description:** Enable memory to persist and be shared across multiple runs within a session or agent scope.

**Affected Components:** Go Engine, Django Backend

**Files to Modify:**
- `engine/adapter/store/redis_memory_store.go`
- Create: `backend/domain/entities/memory_session.py`

**Implementation Details:**

Key hierarchy:
```
forgegraph:tenant:{tenant_id}:session:{session_id}:buffer    → Cross-run buffer
forgegraph:tenant:{tenant_id}:agent:{agent_id}:memory        → Agent-level memory
forgegraph:tenant:{tenant_id}:global:facts                   → Global facts
```

Session management:
```python
class MemorySession(models.Model):
    id = models.UUIDField(primary_key=True)
    tenant_id = models.UUIDField()
    agent_id = models.UUIDField(null=True)

    # Session linking
    parent_session = models.ForeignKey('self', null=True, on_delete=models.SET_NULL)

    # State
    created_at = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField()
```

**Dependencies:** P1-T01

**Estimated Effort:** 2 days

**SUCCESS CRITERIA:**
- [ ] Session ID passed in StartRunRequest
- [ ] Buffer shared across runs in same session
- [ ] Agent-level memory accessible to all runs for that agent
- [ ] Session expiration works correctly
- [ ] Integration test: Two runs in same session share memory

---

#### P4-T03: Add Memory Analytics Dashboard

**Description:** Create analytics endpoints and dashboard for memory usage insights.

**Affected Components:** Django Backend, Frontend

**Files to Create:**
- `backend/adapters/api/analytics/memory_analytics.py`
- `frontend/pages/analytics/memory.tsx`

**Implementation Details:**

API endpoints:
```python
# GET /api/analytics/memory/usage/
{
    "period": "30d",
    "tier1": {
        "total_messages": 125000,
        "avg_buffer_size": 18.5,
        "peak_buffer_size": 50
    },
    "tier2": {
        "redis_keys": 3420,
        "storage_mb": 45.2,
        "hit_rate": 0.92
    },
    "tier3": {
        "chunks_stored": 15000,
        "embeddings_generated": 12000,
        "search_queries": 8500,
        "avg_search_latency_ms": 45
    },
    "costs": {
        "summarization_usd": 12.50,
        "embedding_usd": 8.25
    }
}
```

Dashboard components:
- Usage over time chart
- Tier hit rates
- Cost breakdown
- Top agents by memory usage

**Dependencies:** P3-T10

**Estimated Effort:** 2 days

**SUCCESS CRITERIA:**
- [ ] API returns accurate usage metrics
- [ ] Dashboard renders usage charts
- [ ] Data refreshes automatically
- [ ] Export functionality for reports
- [ ] Tenant isolation in analytics

---

#### P4-T04: Implement Memory Preloading

**Description:** Preload relevant memories when a run starts to reduce first-prompt latency.

**Affected Components:** Go Engine

**Files to Modify:**
- `engine/application/usecase/scheduler.go`

**Implementation Details:**

```go
func (s *Scheduler) preloadMemory(ctx *runContext) {
    if !ctx.memoryConfig.PreloadEnabled {
        return
    }

    // Start preload in background
    go func() {
        // Load session buffer from Redis
        if ctx.sessionID != "" {
            buffer, _ := s.memoryStore.GetSessionBuffer(ctx.ctx, ctx.tenantID, ctx.sessionID)
            if buffer != nil {
                ctx.messageBuffer.Restore(buffer)
            }
        }

        // Warm up vector search cache with recent queries
        if ctx.memoryConfig.Tier3.Enabled {
            s.warmupVectorCache(ctx)
        }
    }()
}
```

**Dependencies:** P4-T02

**Estimated Effort:** 1 day

**SUCCESS CRITERIA:**
- [ ] Preloading happens in background
- [ ] First prompt has access to preloaded memory
- [ ] Preload timeout doesn't block execution
- [ ] Metrics track preload hit rates

---

#### P4-T05: Optimize Redis Pipeline Operations

**Description:** Use Redis pipelining for batch operations to reduce round-trip latency.

**Affected Components:** Go Engine

**Files to Modify:**
- `engine/adapter/store/redis_memory_store.go`

**Implementation Details:**

```go
func (s *RedisMemoryStore) BatchGet(ctx context.Context, ns string, keys []string) (map[string]any, error) {
    pipe := s.client.Pipeline()

    cmds := make(map[string]*redis.StringCmd)
    for _, key := range keys {
        fullKey := s.buildKey(ns, key)
        cmds[key] = pipe.Get(ctx, fullKey)
    }

    _, err := pipe.Exec(ctx)
    if err != nil && err != redis.Nil {
        return nil, err
    }

    results := make(map[string]any)
    for key, cmd := range cmds {
        if val, err := cmd.Result(); err == nil {
            var decoded any
            json.Unmarshal([]byte(val), &decoded)
            results[key] = decoded
        }
    }

    return results, nil
}
```

**Dependencies:** P1-T01

**Estimated Effort:** 0.5 days

**SUCCESS CRITERIA:**
- [ ] BatchGet reduces N round trips to 1
- [ ] Latency for 10 keys is similar to 1 key
- [ ] Error handling per-key works correctly
- [ ] Benchmark shows 5x improvement for batch operations

---

#### P4-T06: Add Memory Compression

**Description:** Compress large values before storing in Redis to reduce memory usage.

**Affected Components:** Go Engine

**Files to Modify:**
- `engine/adapter/store/redis_memory_store.go`

**Implementation Details:**

```go
const compressionThreshold = 1024  // bytes

func (s *RedisMemoryStore) Set(ctx context.Context, ns, key string, value any, ttl int) error {
    data, _ := json.Marshal(value)

    var stored []byte
    if len(data) > compressionThreshold {
        compressed := s.compress(data)
        stored = append([]byte{0x01}, compressed...)  // 0x01 = compressed flag
    } else {
        stored = append([]byte{0x00}, data...)  // 0x00 = uncompressed
    }

    return s.client.Set(ctx, s.buildKey(ns, key), stored, time.Duration(ttl)*time.Second).Err()
}

func (s *RedisMemoryStore) compress(data []byte) []byte {
    var buf bytes.Buffer
    w := zstd.NewWriter(&buf)
    w.Write(data)
    w.Close()
    return buf.Bytes()
}
```

**Dependencies:** P1-T01

**Estimated Effort:** 0.5 days

**SUCCESS CRITERIA:**
- [ ] Large values compressed before storage
- [ ] Compression ratio >2x for conversation data
- [ ] Decompression transparent to callers
- [ ] Small values not compressed (overhead)
- [ ] Benchmark: Compression adds <1ms latency

---

#### P4-T07: Implement Memory Export/Import

**Description:** Allow users to export and import memory data for backup or migration.

**Affected Components:** Django Backend, Frontend

**Files to Create:**
- `backend/application/services/memory_export.py`
- `backend/adapters/api/memory/export_views.py`
- `frontend/components/settings/MemoryExportDialog.tsx`

**Implementation Details:**

Export format (JSON):
```json
{
    "version": "1.0",
    "exported_at": "2025-01-15T10:30:00Z",
    "tenant_id": "...",
    "data": {
        "chunks": [...],
        "summaries": [...],
        "facts": [...]
    }
}
```

API:
```
POST /api/memory/export/
{
    "scope": "agent" | "session" | "all",
    "scope_id": "...",
    "include_embeddings": false  // embeddings regenerated on import
}

Response: { "download_url": "..." }

POST /api/memory/import/
Content-Type: multipart/form-data
file: <exported JSON>
```

**Dependencies:** P3-T02

**Estimated Effort:** 1.5 days

**SUCCESS CRITERIA:**
- [ ] Export produces valid JSON
- [ ] Import restores all data correctly
- [ ] Embeddings regenerated on import
- [ ] Large exports handled via background job
- [ ] Progress indicator for long operations

---

#### P4-T08: Add Memory Search UI

**Description:** Create a UI for users to search and browse stored memories.

**Affected Components:** Frontend

**Files to Create:**
- `frontend/pages/memory/index.tsx`
- `frontend/components/memory/MemoryBrowser.tsx`
- `frontend/components/memory/SearchResults.tsx`

**Implementation Details:**

Features:
- Text search across chunks
- Filter by date range, agent, session
- View chunk details and source
- Delete individual chunks
- Bulk operations

```typescript
interface MemorySearchParams {
    query: string;
    agentId?: string;
    dateFrom?: Date;
    dateTo?: Date;
    chunkType?: 'message' | 'summary' | 'fact';
    page: number;
    pageSize: number;
}

// GET /api/memory/search/
// Returns paginated chunks with highlights
```

**Dependencies:** P3-T06

**Estimated Effort:** 2 days

**SUCCESS CRITERIA:**
- [ ] Search returns relevant results with highlighting
- [ ] Filters work correctly
- [ ] Pagination handles large result sets
- [ ] Delete functionality works
- [ ] Empty state handled gracefully

---

### 4.3 Integration Points

**Token Counter Integration:**
```go
// Configuration
type MemoryConfig struct {
    LimitMode    string  // "messages" | "tokens"
    MaxMessages  int
    MaxTokens    int
}
```

**Analytics API:**
```
GET /api/analytics/memory/usage/?period=30d
GET /api/analytics/memory/costs/?period=30d
GET /api/analytics/memory/performance/
```

---

### 4.4 Testing Strategy

#### Unit Tests

| Test | Description |
|------|-------------|
| `TestTokenCounter_Accuracy` | Match tiktoken output |
| `TestTokenAwareBuffer_Eviction` | Correct eviction |
| `TestCompression_RoundTrip` | Compress/decompress |
| `TestBatchGet_Pipeline` | Pipeline optimization |

#### Integration Tests

| Test | Description |
|------|-------------|
| `TestCrossSession_Memory` | Memory shared across runs |
| `TestExportImport_RoundTrip` | Export then import |
| `TestAnalytics_Accuracy` | Metrics match reality |

#### Performance Benchmarks

| Benchmark | Target |
|-----------|--------|
| Token counting (1K chars) | <1ms |
| Batch get (10 keys) | <15ms |
| Compression (10KB) | <2ms |

---

### 4.5 Rollback Plan

**Feature Flags:**
```python
FEATURE_FLAGS = {
    'MEMORY_TOKEN_LIMITS': env.bool('FF_MEMORY_TOKEN_LIMITS', False),
    'MEMORY_CROSS_SESSION': env.bool('FF_MEMORY_CROSS_SESSION', False),
    'MEMORY_ANALYTICS': env.bool('FF_MEMORY_ANALYTICS', True),
}
```

**Rollback:**
- Disable specific features via flags
- No data migration needed
- Existing functionality unaffected

---

### 4.6 Documentation Deliverables

| Document | Content |
|----------|---------|
| `token-limits.md` | How token limits work |
| `cross-session.md` | Session memory sharing |
| `analytics-guide.md` | Using analytics dashboard |
| `export-import.md` | Backup and migration |

---

## Appendix A: Configuration Schema

### Complete Memory Configuration Schema

```json
{
    "$schema": "http://json-schema.org/draft-07/schema#",
    "$id": "https://forgegraph.io/schemas/memory-config.json",
    "title": "ForgeGraph Memory Configuration",
    "type": "object",
    "properties": {
        "tier1": {
            "type": "object",
            "description": "Local buffer configuration",
            "properties": {
                "enabled": { "type": "boolean", "default": true },
                "limit_mode": {
                    "type": "string",
                    "enum": ["messages", "tokens"],
                    "default": "messages"
                },
                "max_messages": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 200,
                    "default": 20
                },
                "max_tokens": {
                    "type": "integer",
                    "minimum": 100,
                    "maximum": 100000,
                    "default": 4000
                },
                "auto_prepend": { "type": "boolean", "default": true }
            }
        },
        "tier2": {
            "type": "object",
            "description": "Redis cache configuration",
            "properties": {
                "enabled": { "type": "boolean", "default": false },
                "namespace": { "type": "string", "default": "" },
                "summary_ttl_seconds": {
                    "type": "integer",
                    "minimum": 60,
                    "default": 86400
                },
                "facts_ttl_seconds": {
                    "type": "integer",
                    "minimum": 60,
                    "default": 604800
                }
            }
        },
        "tier3": {
            "type": "object",
            "description": "Vector database configuration",
            "properties": {
                "enabled": { "type": "boolean", "default": false },
                "top_k": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 20,
                    "default": 5
                },
                "threshold": {
                    "type": "number",
                    "minimum": 0.5,
                    "maximum": 0.99,
                    "default": 0.7
                },
                "recency_weight": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                    "default": 0.2
                },
                "embedding_model": {
                    "type": "string",
                    "default": "text-embedding-ada-002"
                }
            }
        },
        "summarization": {
            "type": "object",
            "description": "Automatic summarization configuration",
            "properties": {
                "enabled": { "type": "boolean", "default": false },
                "trigger_threshold": {
                    "type": "integer",
                    "minimum": 20,
                    "default": 30
                },
                "keep_recent": {
                    "type": "integer",
                    "minimum": 5,
                    "default": 10
                },
                "model": { "type": "string", "default": "claude-haiku" }
            }
        },
        "cross_session": {
            "type": "object",
            "description": "Cross-session memory configuration",
            "properties": {
                "enabled": { "type": "boolean", "default": false },
                "session_ttl_hours": {
                    "type": "integer",
                    "minimum": 1,
                    "default": 24
                },
                "share_with_agent": { "type": "boolean", "default": false }
            }
        }
    }
}
```

---

## Appendix B: API Contracts

### Memory Configuration API

```yaml
openapi: 3.0.3
info:
  title: ForgeGraph Memory API
  version: 1.0.0

paths:
  /api/graphs/{graph_id}/memory-config/:
    get:
      summary: Get memory configuration for a graph
      responses:
        200:
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/MemoryConfig'

    patch:
      summary: Update memory configuration
      requestBody:
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/MemoryConfigUpdate'
      responses:
        200:
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/MemoryConfig'

  /api/memory/search/:
    get:
      summary: Search stored memories
      parameters:
        - name: query
          in: query
          required: true
          schema:
            type: string
        - name: agent_id
          in: query
          schema:
            type: string
            format: uuid
        - name: top_k
          in: query
          schema:
            type: integer
            default: 10
      responses:
        200:
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/MemoryChunk'

  /api/memory/export/:
    post:
      summary: Export memory data
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                scope:
                  type: string
                  enum: [agent, session, all]
                scope_id:
                  type: string
                  format: uuid
      responses:
        202:
          content:
            application/json:
              schema:
                type: object
                properties:
                  job_id:
                    type: string
                  download_url:
                    type: string

components:
  schemas:
    MemoryConfig:
      type: object
      properties:
        tier1:
          type: object
        tier2:
          type: object
        tier3:
          type: object
        summarization:
          type: object

    MemoryChunk:
      type: object
      properties:
        id:
          type: string
          format: uuid
        content:
          type: string
        score:
          type: number
        chunk_type:
          type: string
        created_at:
          type: string
          format: date-time
```

---

## Appendix C: Database Migrations

### Migration Sequence

| Migration | Phase | Description |
|-----------|-------|-------------|
| `0011_memory_configuration.py` | P1 | MemoryConfiguration model |
| `0012_summarization_config.py` | P2 | Summarization fields |
| `0014_pgvector_setup.py` | P3 | Enable pgvector extension |
| `0015_memory_chunks.py` | P3 | MemoryChunk with vector field |
| `0016_vector_config.py` | P3 | Vector configuration fields |
| `0017_memory_sessions.py` | P4 | MemorySession model |
| `0018_memory_analytics.py` | P4 | MemoryUsageLog model |

### Rollback Commands

```bash
# Rollback to before Phase 3
python manage.py migrate infrastructure 0012

# Rollback to before Phase 1
python manage.py migrate infrastructure 0010
```

---

## Appendix D: Monitoring & Alerts

### Prometheus Metrics

```
# Tier 1 (Local Buffer)
forgegraph_memory_buffer_size{run_id, tenant_id}
forgegraph_memory_buffer_push_total{tenant_id}
forgegraph_memory_buffer_eviction_total{tenant_id}

# Tier 2 (Redis)
forgegraph_memory_redis_operations_total{operation, status}
forgegraph_memory_redis_latency_seconds{operation, quantile}
forgegraph_memory_redis_circuit_state{state}
forgegraph_memory_redis_fallback_total

# Tier 3 (Vector)
forgegraph_memory_vector_search_total{tenant_id}
forgegraph_memory_vector_search_latency_seconds{quantile}
forgegraph_memory_embedding_total{status}
forgegraph_memory_chunks_total{tenant_id}

# Summarization
forgegraph_memory_summarization_total{status}
forgegraph_memory_summarization_latency_seconds{quantile}
forgegraph_memory_summarization_cost_usd{tenant_id}
```

### Alert Rules

```yaml
groups:
  - name: forgegraph-memory
    rules:
      - alert: RedisCircuitOpen
        expr: forgegraph_memory_redis_circuit_state{state="open"} == 1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: Redis circuit breaker open

      - alert: VectorSearchSlow
        expr: histogram_quantile(0.99, forgegraph_memory_vector_search_latency_seconds) > 0.2
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: Vector search p99 latency above 200ms

      - alert: MemoryStorageGrowth
        expr: rate(forgegraph_memory_chunks_total[24h]) > 100000
        for: 1h
        labels:
          severity: info
        annotations:
          summary: Memory chunks growing rapidly
```

### Grafana Dashboard Panels

1. **Memory Tier Hit Rates** - Stacked bar chart by tier
2. **Redis Operations Latency** - Heatmap
3. **Vector Search Performance** - Time series with p50/p95/p99
4. **Buffer Sizes Distribution** - Histogram
5. **Summarization Costs** - Cumulative by tenant
6. **Storage Growth** - Area chart

---

## Implementation Timeline Summary

| Phase | Tasks | Total Effort | Calendar Duration |
|-------|-------|--------------|-------------------|
| Phase 1 | P1-T01 to P1-T12 | ~15 days | 3-4 weeks |
| Phase 2 | P2-T01 to P2-T08 | ~8 days | 2-3 weeks |
| Phase 3 | P3-T01 to P3-T10 | ~13 days | 4-6 weeks |
| Phase 4 | P4-T01 to P4-T08 | ~12 days | 2-3 weeks |
| **Total** | **38 tasks** | **~48 days** | **11-16 weeks** |

---

*Document generated for ForgeGraph Memory System Implementation*
*Version: 1.0.0*
*Last Updated: 2026-01-30*
