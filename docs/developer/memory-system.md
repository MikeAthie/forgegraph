# Memory System Architecture

## Overview
ForgeGraph uses a three-tier memory system:

1. **Tier 1: Local Buffer** — in-memory, per-run circular buffer for immediate context.
2. **Tier 2: Redis Cache** — durable, shared memory for summaries and facts.
3. **Tier 3: Vector Memory** — semantic long-term memory (Phase 3).

This document covers Tier 1–2 implemented in Phase 1 and the configuration flow to the engine.

---

## Architecture Diagram

```
User Input
   │
   ▼
Scheduler ─────────────┐
   │                   │
   ▼                   │
Prompt Executor        │
   │                   │
   ▼                   │
Tier 1: MessageBuffer  │
   │                   │
   └─────► TieredMemoryStore ──► Tier 2: Redis
                               └─► Tier 3: Vector (Phase 3)
```

---

## Tier 1: Local Buffer

- **Implementation:** `engine/domain/entity/message_buffer.go`
- **Access:** sub-millisecond
- **Storage:** per-run in-memory circular buffer
- **Usage:** prompt executor auto-prepends recent messages when enabled

Key behaviors:
- Buffer size is configurable (default: 20 messages)
- Oldest messages are evicted on overflow
- Snapshot/restore supported via checkpoints

---

## Tier 2: Redis Cache

- **Implementation:** `engine/adapter/store/redis_memory_store.go`
- **Access:** fast persistent storage for summaries/facts
- **Fault tolerance:** circuit breaker with fallback

Key behaviors:
- Keys are tenant-prefixed: `forgegraph:tenant:{tenant_id}:memory:{namespace}:{key}`
- Circuit opens after repeated failures, uses fallback store
- Health check exposed at `/health/redis`

---

## Configuration Flow

1. Memory config stored in Django `MemoryConfiguration` model
2. UI updates config via `/api/graphs/{id}/memory-config`
3. Runs pass config to engine via gRPC `StartRunRequest.memory_config_json`
4. Engine parses config and initializes buffer per run

---

## Defaults

Engine defaults (when no config is provided):

- **Tier 1**
  - `enabled`: true
  - `buffer_size`: 20
  - `auto_prepend`: true
- **Tier 2**
  - `enabled`: false
  - `summary_ttl_seconds`: 86400 (24 hours)
  - `facts_ttl_seconds`: 604800 (7 days)
- **Tier 3**
  - `enabled`: false
  - `top_k`: 5
  - `threshold`: 0.7

Backend defaults (MemoryConfiguration model):

- `buffer_enabled`: true
- `buffer_size`: 20
- `auto_prepend`: true
- `redis_enabled`: false
- `redis_summary_ttl`: 86400
- `redis_facts_ttl`: 604800
- `vector_enabled`: false
- `vector_top_k`: 5
- `vector_threshold`: 0.7

---

## API Endpoints

### Graph Memory Configuration

- `GET /api/graphs/{graph_id}/memory-config`
- `PATCH /api/graphs/{graph_id}/memory-config`

Example payload:
```json
{
  "buffer_enabled": true,
  "buffer_size": 20,
  "auto_prepend": true,
  "redis_enabled": false,
  "redis_summary_ttl": 86400,
  "redis_facts_ttl": 604800
}
```

---

## Metrics

Prometheus metrics (engine):
- `forgegraph_memory_tier2_operations_total`
- `forgegraph_memory_tier2_latency_seconds`
- `forgegraph_memory_tier2_circuit_state`
- `forgegraph_memory_tier2_fallback_total`

Metrics endpoint: `:9090/metrics`

---

## Troubleshooting

**Redis connection errors**
- Check `REDIS_ADDR` and credentials.
- Verify `/health/redis` in engine.

**Memory buffer too small**
- Increase buffer size in graph memory config.

**Memory config not applying**
- Confirm graph has a MemoryConfiguration row.
- Check the run request includes `memory_config_json`.
