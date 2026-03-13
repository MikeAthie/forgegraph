# P1-F01 Implementation Tickets

## Goal
Convert `P1-F01` into reviewable implementation slices with explicit file targets, acceptance criteria, tests, and PR boundaries.

`P1-F01` is the curated-memory domain epic:
- backend must gain a first-class `MemoryObservation` domain
- the memory service contract must expand without breaking existing retrieval
- REST and gRPC must expose observation-centric workflows
- indexing, dedupe, and tenant scoping must be explicit and testable

## Current Repo Reality
The current codebase already has:
- graph-level memory configuration
- Tier 1 buffer via `MessageBuffer`
- Tier 2 shared/session memory via `MemoryStore`
- Tier 3 semantic retrieval over `MemoryChunk` through `RetrieveMemory`
- `MemoryEntry`, `MemoryChunk`, and `MemorySession` models

The current gap is specific:
- there is no durable, governable observation object
- there is no observation search/detail/timeline/context API
- gRPC memory support is retrieval-only
- the product cannot yet expose inspectable agent memory as a first-class concept

`P1-F01` fixes that gap without replacing existing KV or semantic memory primitives.

## Ticketing Strategy
The safest split is:
1. contract and architecture doc
2. backend model and service skeleton
3. REST API and read model
4. additive gRPC contract and servicer support
5. indexing, dedupe, and tenant-hardening

This keeps the domain stable before engine/runtime and UI begin to depend on it.

---

## PR-1: Curated Memory Contract and Architecture

### Objective
Introduce the curated-memory architecture and lock the domain decisions before implementation starts changing models and APIs.

### Scope
- architecture docs
- MVP plan references
- contract shape only; no runtime behavior yet

### Expected Files

#### New files
- `docs/architecture/curated-memory.md`
- `docs/mvp/p1-f01-implementation-tickets.md`

#### Planning files
- `docs/mvp/mvp-tasks-p1.md`
- `docs/mvp/forgegraph-mvp-implementation-plan.md`
- `docs/mvp/forgegraph-mvp-tasks.md`
- `docs/mvp/mvp-remediation-tasks.md`

### Acceptance Criteria
- [ ] Curated memory is documented as a native ForgeGraph subdomain.
- [ ] The MVP decisions are locked:
  - internal-only exposure
  - explicit capture first
  - hybrid FTS + vector
  - graph/run/session scope
  - async indexing
- [ ] Existing KV/session/vector memory is explicitly preserved.
- [ ] P1 docs and implementation plan point to curated memory instead of the older onboarding-first P1 narrative.

### Tests
- doc-only PR; no new code tests required

### PR Boundary Notes
- Do not add models, migrations, or API code here.
- This PR exists to prevent later contract drift.

---

## PR-2: Backend Model and Observation Service Skeleton

### Objective
Add the `MemoryObservation` persistence model and service-layer primitives without yet exposing the full product API.

### Scope
- ORM model and migration
- service skeleton
- repository/query scaffolding
- no engine/runtime integration yet

### Expected Files

#### Backend files
- `backend/infrastructure/orm/models.py`
- `backend/infrastructure/orm/migrations/<new>_memory_observations.py`
- `backend/application/services/memory_observation_service.py` (new)
- `backend/tests/unit/application/test_memory_observation_service.py` (new)

#### Optional files depending on implementation
- `backend/adapters/repositories/memory_observation_repository.py` (new)
- `backend/tests/unit/domain/test_models.py`

### Acceptance Criteria
- [ ] `MemoryObservation` exists with the agreed core fields.
- [ ] Tenant, graph, run, and session scope are represented explicitly.
- [ ] Soft-delete-ready fields exist.
- [ ] Service methods exist for create/update/delete/search/detail/timeline/context orchestration, even if API handlers are not wired yet.
- [ ] Existing memory models remain backward compatible.

### Tests
- backend model tests for indexes/constraints where appropriate
- unit tests for service normalization and lifecycle entry points

### PR Boundary Notes
- Keep vector indexing asynchronous or stubbed behind the service boundary.
- Do not add engine node types in this PR.

---

## PR-3: REST API for Observations, Search, Timeline, and Context

### Objective
Expose curated memory through backend REST endpoints for product UI and browser flows.

### Scope
- serializers
- views
- URLs
- pagination/filtering/read models

### Expected Files

#### Backend files
- `backend/adapters/api/memory/urls.py`
- `backend/adapters/api/memory/views.py` or split views under `adapters/api/memory/`
- `backend/adapters/api/memory/serializers.py` (new)
- `backend/tests/integration/adapters/test_memory_observation_api.py` (new)

#### Optional files depending on implementation
- `backend/adapters/api/runs/serializers.py`
- `backend/adapters/api/runs/views.py`

### Acceptance Criteria
- [ ] REST endpoints exist for:
  - create/update/delete
  - search
  - detail
  - timeline
  - context
- [ ] Filters, pagination, and scope constraints are explicit and stable.
- [ ] Redaction and field-size validation are enforced at API boundaries.
- [ ] Cross-tenant access is denied consistently.

### Tests
- integration tests for create/search/detail/delete flows
- integration tests for timeline and context payloads
- cross-tenant access denial tests

### PR Boundary Notes
- Keep the UI out of this PR.
- The API should be usable for future Memory Browser work without further contract invention.

---

## PR-4: Additive gRPC Memory Contract and Servicer Support

### Objective
Extend the memory gRPC surface so runtime components can save and retrieve curated observations without breaking existing `RetrieveMemory` behavior.

### Scope
- proto changes
- generated bindings
- backend servicer support
- backend-side integration tests

### Expected Files

#### Shared / proto files
- `backend/infrastructure/grpc/engine.proto` or the canonical proto source
- generated gRPC bindings as required by the repo workflow

#### Backend files
- `backend/adapters/grpc/memory_service.py`
- `backend/tests/integration/adapters/test_memory_grpc_service.py`
- `backend/tests/integration/adapters/test_memory_grpc_health.py`

#### Optional engine-side contract files
- generated engine gRPC client bindings
- client wrapper files that P1-F02 will later consume

### Acceptance Criteria
- [ ] The memory service exposes additive methods for:
  - `SaveObservation`
  - `SearchObservations`
  - `GetObservation`
  - `GetContext`
  - `GetTimeline`
- [ ] `RetrieveMemory` remains backward compatible.
- [ ] Timeout and error handling match the existing memory gRPC expectations.
- [ ] Response shapes are stable enough for engine/runtime work to build on directly.

### Tests
- gRPC integration tests for new methods
- regression tests for existing `RetrieveMemory`
- timeout/error-path tests where practical

### PR Boundary Notes
- Do not add engine executors here.
- Keep contract generation and service implementation together so the next phase inherits one stable surface.

---

## PR-5: Indexing, Dedupe, and Query Hardening

### Objective
Finish the domain with production-grade search and write-path semantics: dedupe, topic upsert, FTS behavior, and async observation-to-vector indexing.

### Scope
- service hardening
- async indexing pipeline
- FTS query behavior
- observability and failure-path handling

### Expected Files

#### Backend files
- `backend/application/services/memory_observation_service.py`
- `backend/application/services/embedding_pipeline.py`
- `backend/application/services/vector_search_service.py`
- `backend/application/services/memory_gc.py`
- `backend/tests/unit/application/test_memory_observation_service.py`
- `backend/tests/integration/adapters/test_memory_observation_api.py`

#### Optional files depending on implementation
- `backend/adapters/repositories/memory_chunk_repository.py`
- `backend/adapters/api/analytics/memory_analytics.py`

### Acceptance Criteria
- [ ] Observation writes support normalization, dedupe, and topic-aware updates.
- [ ] Async indexing creates or updates `MemoryChunk` records with observation metadata.
- [ ] Search degrades safely when embeddings are unavailable or delayed.
- [ ] Retention/GC behavior for observations is defined and does not conflict with existing memory cleanup.
- [ ] Domain metrics or counters exist for indexing failures and observation volume if needed for the next phase.

### Tests
- unit tests for dedupe and topic-upsert behavior
- integration tests for FTS and degraded vector behavior
- tests for async indexing side effects and metadata linkage

### PR Boundary Notes
- This is the last backend-heavy PR before P1-F02 starts consuming the domain from the engine.
- Keep UI and editor changes out of this slice.

---

## Optional PR-0: Curated Memory Review Pass

### Objective
Land the memory architecture and planning docs before implementation if the team wants one review pass on the domain boundaries first.

### Expected Files
- `docs/architecture/curated-memory.md`
- `docs/mvp/mvp-tasks-p1.md`
- `docs/mvp/forgegraph-mvp-implementation-plan.md`
- `docs/mvp/p1-f01-implementation-tickets.md`

### Acceptance Criteria
- [ ] The domain and roadmap decisions are agreed before model/API work starts.

---

## Recommended Merge Order
1. Optional PR-0
2. PR-1
3. PR-2
4. PR-3
5. PR-4
6. PR-5

## Final Ticket-Level Definition of Done
- [ ] All PRs merged in order or with explicitly managed overlap
- [ ] Curated memory exists as a first-class backend domain
- [ ] REST and gRPC contracts are stable and additive
- [ ] Observation writes, search, context, and indexing behavior are test-backed
- [ ] `P1-F02` can start without making new contract decisions
