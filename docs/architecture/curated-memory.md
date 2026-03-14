# Curated Memory Architecture

## Summary
ForgeGraph will add an Engram-style curated memory layer as a native product subdomain.

This is not a replacement for the existing three-tier memory system.
It is an additive layer that introduces structured observations, session-aware context assembly, deterministic search, and timeline-style inspection on top of the current buffer, key/value, and vector memory foundations.

The curated memory MVP is intentionally constrained:
- native ForgeGraph implementation only
- REST + gRPC + graph nodes + product UI only
- no public MCP surface in MVP
- explicit capture first; no passive run-derived capture in MVP
- hybrid FTS + vector retrieval by default
- graph/run/session-scoped behavior with strict tenant isolation

## Product Positioning
The purpose of curated memory is to make agent memory inspectable, governable, and reusable across runs without relying only on raw conversation buffers or opaque semantic chunks.

ForgeGraph should be able to say:

"Agents can explicitly save observations, retrieve curated context, and use session-aware memory through visible workflow steps and debuggable product surfaces."

## Existing Memory Layers
ForgeGraph already has these memory layers:
- Tier 1: local `MessageBuffer` for recent context
- Tier 2: `MemoryStore`-backed shared memory for summaries/facts and session snapshots
- Tier 3: semantic retrieval over `MemoryChunk`

Curated memory must integrate with these layers, not fork them.

The existing `memory` node remains the KV-style operational memory primitive.
Curated memory introduces a separate observation-centric model and node set.

## New Domain Model
### `MemoryObservation`
Add a first-class backend model for curated memory observations.

Required fields:
- `id`
- `tenant_id`
- `graph_id`
- `run_id`
- `session_id`
- `agent_id`
- `type`
- `title`
- `content`
- `scope`
- `topic_key`
- `tool_name`
- `revision_count`
- `duplicate_count`
- `last_seen_at`
- `created_at`
- `updated_at`
- `deleted_at`

Behavioral rules:
- writes are tenant-isolated
- writes are graph/run/session scoped by default
- `topic_key` supports update-latest semantics where configured
- duplicate detection is built into the service layer
- deletion is soft delete in MVP

### Relationship to Existing Models
- `MemoryEntry` stays unchanged for KV memory nodes
- `MemoryChunk` stays unchanged for semantic retrieval storage
- each indexed observation may create or update a linked `MemoryChunk` with:
  - `chunk_type = observation`
  - metadata carrying `observation_id`, `type`, `topic_key`, and scope metadata

## Interfaces
### REST
Add curated-memory endpoints under `/api/memory`:
- `POST /api/memory/observations`
- `PATCH /api/memory/observations/{id}`
- `DELETE /api/memory/observations/{id}`
- `GET /api/memory/observations/search`
- `GET /api/memory/observations/{id}`
- `GET /api/memory/context`
- `GET /api/memory/timeline`

REST is the source for product UI and admin/browser flows.

### gRPC
Extend the existing memory service with additive methods:
- `SaveObservation`
- `SearchObservations`
- `GetObservation`
- `GetContext`
- `GetTimeline`

`RetrieveMemory` remains supported and unchanged for backward compatibility.

### Engine Node Types
Add explicit curated-memory node types:
- `observation_save`
- `observation_search`
- `observation_context`
- `observation_timeline`

These nodes are additive. They do not replace:
- `memory`
- `prompt`
- `agent`

## Retrieval Model
### Default Strategy
Curated memory retrieval uses hybrid ranking:
- FTS for deterministic keyword/topic retrieval
- vector search for semantic recall

### Context Composition
`observation_context` and related prompt/agent integrations should assemble context in this order:
1. curated observation hits
2. active session summary/facts if enabled
3. semantic chunk retrieval if enabled
4. current run buffer if enabled by graph memory config

This preserves current memory behavior while adding curated context explicitly.

### Write Path
Observation save is split into two paths:
- synchronous transactional write to `MemoryObservation`
- asynchronous embedding/indexing to `MemoryChunk`

Run execution must not block on embedding generation.

### Degradation Rules
If vector indexing is unavailable or delayed:
- observation writes still succeed
- FTS search still works
- context retrieval degrades to non-vector behavior cleanly

## Scope and Security
### Scope Defaults
MVP curated memory is scoped primarily by:
- graph
- run
- session

Tenant isolation is mandatory and non-optional.

### Out of Scope for MVP
- organization-wide knowledge management as the primary model
- user-personal memory as the primary model
- passive extraction of observations from all runs/messages
- public MCP-compatible memory server
- export/import workflows

### Safety Rules
Curated memory must include:
- size limits on observation fields
- server-side validation and normalization
- redaction hooks before persistence where needed
- idempotent save semantics where retries are possible
- retention/GC alignment with existing memory lifecycle controls

## UI Surfaces
P1 UI should add:
- a Memory Browser page for search, filters, detail, and timeline
- node forms for the curated-memory node types
- run/debug surfaces that show observation hits and context assembly clearly
- one supported Jackie-style workflow that demonstrates save + later retrieval

## Rollout
Use feature flags:
- `FF_CURATED_MEMORY_ENABLED`
- `FF_CURATED_MEMORY_VECTOR_INDEXING`

Rollback behavior:
- disabling flags removes the new surfaces from active use
- existing Tier 1/2/3 memory remains intact
- observation data can remain stored but unused

## Testing Expectations
Curated memory must land with:
- unit tests for normalization, dedupe, upsert, and timeline behavior
- integration tests for REST + gRPC + tenant isolation
- engine tests for new node executors and failure behavior
- browser E2E proving save -> later retrieval in a Jackie-style flow
- performance checks for search/context latency and vector degradation

## Operational References
For the shipped P2 operator/admin layer, also see:
- `docs/ops/p2-memory-governance-support.md`
- `docs/ops/p2-team-admin-walkthrough.md`
