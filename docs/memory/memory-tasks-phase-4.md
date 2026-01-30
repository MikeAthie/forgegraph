# Phase 4: Advanced Features and Optimization

## Objective
Deliver advanced memory features: token-aware limits, cross-session memory, analytics, preloading, and performance optimizations.

## Prerequisites
- Phase 3 complete (vector memory pipeline and retrieval)
- Metrics stack available (Prometheus/Grafana)

---

## Task List

### P4-T01: Implement Token-Aware Buffer Limits
**Files:**
- `engine/domain/service/token_counter.go`
- `engine/domain/entity/message_buffer.go`

- [ ] Add TokenCounter interface with tiktoken implementation.
- [ ] Extend MessageBuffer to support token-based limits.
- [ ] Cache token counts to reduce overhead.
- [ ] Fallback to message count on failure.
- [ ] Add unit tests and benchmarks.

```go
type TokenCounter interface {
    Count(text string) int
    CountMessages(msgs []Message) int
}
```

**Acceptance Criteria:**
- [ ] Token counts match tiktoken output
- [ ] Buffer evicts based on token limit
- [ ] Token counting overhead <1ms per message
- [ ] Tests and benchmarks pass

---

### P4-T02: Implement Cross-Session Memory
**Files:**
- `engine/adapter/store/redis_memory_store.go`
- `backend/domain/entities/memory_session.py`
- `backend/infrastructure/orm/migrations/0016_memory_sessions.py`

- [ ] Add session-level memory keys in Redis.
- [ ] Create MemorySession model with expiration.
- [ ] Pass session ID in StartRunRequest.
- [ ] Share buffer across runs in same session.
- [ ] Add integration tests for session sharing.

Key structure:
```
forgegraph:tenant:{tenant_id}:session:{session_id}:buffer
forgegraph:tenant:{tenant_id}:agent:{agent_id}:memory
```

**Acceptance Criteria:**
- [ ] Session buffer shared across runs
- [ ] Agent-level memory accessible within tenant
- [ ] Sessions expire and clean up correctly
- [ ] Integration tests pass

---

### P4-T03: Add Memory Analytics Dashboard
**Files:**
- `backend/adapters/api/analytics/memory_analytics.py`
- `frontend/pages/analytics/memory.tsx`

- [ ] Implement analytics API endpoints for usage, costs, performance.
- [ ] Build dashboard with charts for tier usage and costs.
- [ ] Add tenant isolation for analytics queries.
- [ ] Add export/report functionality.

**Acceptance Criteria:**
- [ ] API returns accurate usage metrics
- [ ] Dashboard renders charts and filters
- [ ] Data refreshes automatically
- [ ] Tenant isolation verified

---

### P4-T04: Implement Memory Preloading
**Files:**
- `engine/application/usecase/scheduler.go`

- [ ] Add preloadMemory step on run start.
- [ ] Restore session buffer asynchronously.
- [ ] Warm vector cache when Tier3 enabled.
- [ ] Track preload metrics.

**Acceptance Criteria:**
- [ ] Preload happens in background
- [ ] First prompt uses preloaded memory
- [ ] Preload does not block run startup

---

### P4-T05: Optimize Redis Pipeline Operations
**Files:**
- `engine/adapter/store/redis_memory_store.go`

- [ ] Add BatchGet using Redis pipelining.
- [ ] Handle per-key errors gracefully.
- [ ] Add benchmarks for batch vs single get.

**Acceptance Criteria:**
- [ ] BatchGet reduces round trips to 1
- [ ] Latency for 10 keys close to single key
- [ ] Benchmark shows 5x improvement

---

### P4-T06: Add Memory Compression
**Files:**
- `engine/adapter/store/redis_memory_store.go`

- [ ] Compress values over threshold before storage.
- [ ] Add transparent decompression on get.
- [ ] Store compression flag prefix.
- [ ] Add compression benchmark.

```go
const compressionThreshold = 1024 // bytes
```

**Acceptance Criteria:**
- [ ] Large values compressed
- [ ] Compression ratio >2x for conversation data
- [ ] Small values not compressed
- [ ] Compression overhead <1ms

---

### P4-T07: Implement Memory Export/Import
**Files:**
- `backend/application/services/memory_export.py`
- `backend/adapters/api/memory/export_views.py`
- `frontend/components/settings/MemoryExportDialog.tsx`

- [ ] Implement export job for memory data.
- [ ] Add import endpoint for JSON uploads.
- [ ] Regenerate embeddings on import.
- [ ] Add progress indicator for large jobs.

**Acceptance Criteria:**
- [ ] Export produces valid JSON bundle
- [ ] Import restores data correctly
- [ ] Large exports handled via background jobs
- [ ] UI shows progress and completion

---

### P4-T08: Add Memory Search UI
**Files:**
- `frontend/pages/memory/index.tsx`
- `frontend/components/memory/MemoryBrowser.tsx`
- `frontend/components/memory/SearchResults.tsx`

- [ ] Implement search UI with filters and pagination.
- [ ] Integrate with memory search API.
- [ ] Add delete and bulk actions.
- [ ] Handle empty and loading states.

**Acceptance Criteria:**
- [ ] Search returns highlighted results
- [ ] Filters and pagination work
- [ ] Delete and bulk actions work
- [ ] Empty state handled cleanly

---

## Acceptance Criteria (Phase 4 Overall)

1. Token-aware buffer limits available
2. Cross-session memory sharing implemented
3. Analytics dashboards and APIs live
4. Preloading improves first-prompt latency
5. Redis pipeline and compression optimizations active
6. Export/import and search UI available

## Status: NOT STARTED

## Dependencies

- Phase 3 complete

## Output

- [ ] Token counter and token-aware buffer
- [ ] Cross-session memory support
- [ ] Analytics API and dashboard
- [ ] Memory preloading logic
- [ ] Redis pipeline and compression
- [ ] Export/import UI and API
- [ ] Memory search UI
