# P1: Curated Memory, Runtime Integration, and Memory-First UX

## Objective
Turn ForgeGraph's current memory foundations into a product-level differentiator by adding curated memory that agents can save, retrieve, inspect, and reuse across runs.

If P0 made ForgeGraph truthful, P1 makes it memory-native.

## Status
P1 is complete as of March 13, 2026.

Validation and close-out references:
- `docs/mvp/p1-memory-qa-matrix.md`
- `docs/mvp/p1-memory-narrative.md`

## What P1 Must Achieve
At the end of P1, ForgeGraph should be able to make the following promise:

"You can build an agent workflow that explicitly saves observations, retrieves contextual memory across sessions, and explains how memory influenced the run."

## Assumptions
P1 assumes P0 is complete or very close:
- real `agent` node exists
- marketplace/runtime semantics are coherent
- Cloud-safe execution policy exists
- graph and event contracts are documented

P1 also locks these product decisions:
- curated memory is a native ForgeGraph subdomain
- MVP exposure is internal only: REST + gRPC + graph nodes + UI
- MVP capture is explicit first; no passive run-derived capture
- default retrieval is hybrid FTS + vector
- primary scope is graph/run/session, with tenant isolation underneath

## What Is Already Done
The following foundations already exist and should be reused:
- graph-level memory configuration and propagation to engine
- Tier 1 `MessageBuffer` behavior
- Tier 2 `MemoryStore`/Redis session and summary storage
- Tier 3 `MemoryChunk` retrieval via gRPC `RetrieveMemory`
- run detail page, replay hooks, and debugger surfaces
- graph editor, node form infrastructure, and Playwright authoring coverage

P1 is about adding a curated memory layer on top of those foundations, not replacing them.

## P1 Exit State
P1 is complete only when all of the following are true:
- [x] ForgeGraph has a first-class curated memory domain centered on observations.
- [x] Agents and workflows can save and retrieve curated memory through explicit nodes.
- [x] Users can browse memory items, search them, inspect details, and view timelines.
- [x] A Jackie-style supported workflow proves save -> later retrieval -> agent response end to end.
- [x] Memory behavior is inspectable in the run/debug surfaces rather than hidden inside raw state.

## Implementation Readiness
This file is ready to drive implementation once P0 is stable enough for product-facing work.

Use these docs as the execution entry point:
- `docs/mvp/forgegraph-mvp-implementation-plan.md`
- `docs/mvp/mvp-tasks-p1.md`
- `docs/architecture/curated-memory.md`
- `docs/mvp/p1-f01-implementation-tickets.md`
- `docs/mvp/p1-f02-implementation-tickets.md`
- `docs/mvp/p1-f03-implementation-tickets.md`

Implementation order for P1:
1. `P1-F01`
2. `P1-F02`
3. `P1-F03`

Start work immediately with these first PRs:
- `P1-F01`: contract/model PR from `p1-f01-implementation-tickets.md`
- `P1-F02`: runtime PR from `p1-f02-implementation-tickets.md`
- `P1-F03`: product-surface PR from `p1-f03-implementation-tickets.md`

No additional phase-planning doc should be needed before opening the first P1 implementation PRs.

---

## P1-F01: Curated Memory Domain and Contracts

### Feature Description
Add a native curated memory subdomain that introduces structured observations, topic-aware memory items, timeline inspection, and session-aware context assembly.

This is the core P1 feature. It changes ForgeGraph from having only operational memory tiers into having inspectable agent memory.

### Why This Is P1
- The repo already has buffer, KV, Redis/session, and vector memory foundations.
- What is missing is a durable, governable, product-visible memory object.
- This is the most defensible post-P0 differentiator.

### User-Facing Outcome
- A user or workflow can create structured memory observations.
- The system can search, inspect, and contextualize those observations later.
- Memory is visible as a product concept, not just implicit prompt state.

### Non-Goals for P1
- passive memory extraction from all runs
- public MCP server or external memory API
- organization-wide knowledge product
- export/import workflows

### Detailed Tasks

#### F01-T01: Define the curated memory contract
- [x] Finalize `docs/architecture/curated-memory.md`.
- [x] Define the `MemoryObservation` domain shape.
- [x] Define observation lifecycle semantics:
  - create
  - update
  - soft delete
  - dedupe
  - topic upsert
  - timeline
  - context assembly
- [x] Define the scope model:
  - graph
  - run
  - session
  - tenant isolation
- [x] Define degradation behavior when vector indexing is unavailable.

#### F01-T02: Add backend model and persistence
- [x] Add `MemoryObservation` ORM model and migration.
- [x] Add indexes for:
  - tenant + recency
  - tenant + topic_key
  - FTS search
- [x] Keep `MemoryEntry` and `MemoryChunk` unchanged and additive.
- [x] Add metadata linkage from observations to optional `MemoryChunk` rows.

#### F01-T03: Add REST contracts
- [x] Add endpoints for:
  - create observation
  - update observation
  - delete observation
  - search observations
  - get observation detail
  - get timeline
  - get context
- [x] Define redaction, pagination, and filtering behavior.
- [x] Keep the API isolated under `/api/memory/...`.

#### F01-T04: Extend gRPC contracts
- [x] Extend the memory service with additive methods:
  - `SaveObservation`
  - `SearchObservations`
  - `GetObservation`
  - `GetContext`
  - `GetTimeline`
- [x] Keep `RetrieveMemory` backward compatible.
- [x] Version contract changes so old engine behavior does not break.

#### F01-T05: Add observation service behavior
- [x] Implement normalization and `topic_key` handling.
- [x] Implement duplicate detection.
- [x] Implement soft delete and timeline paging.
- [x] Implement async observation-to-vector indexing.
- [x] Ensure observation writes do not block on embedding generation.

#### F01-T06: Test coverage
- [x] Unit tests for:
  - normalization
  - dedupe
  - topic upsert
  - soft delete
  - timeline ordering
- [x] Integration tests for REST and gRPC contract behavior.
- [x] Tenant isolation tests.
- [x] Failure tests for indexing lag/fallback behavior.

### Success Criteria
- [x] Curated memory exists as a native backend domain, not an overloaded extension of KV memory.
- [x] REST and gRPC contracts are stable and additive.
- [x] Observation writes succeed independently of vector indexing progress.
- [x] Existing memory features continue to work unchanged.

### Proof / Demo Feat
Create an observation through the new API, retrieve it through search and detail views, and show the same memory item available for runtime context assembly later.

---

## P1-F02: Curated Memory Runtime Integration

### Feature Description
Expose curated memory to workflows and agents as explicit runtime primitives rather than hidden backend-only state.

### Why This Is P1
- Without engine integration, curated memory is only an admin/data feature.
- The product value comes from workflows being able to save, retrieve, and reuse memory in visible steps.

### User-Facing Outcome
- Builders can add observation nodes to graphs.
- Agents can retrieve curated context explicitly.
- Runs show when memory was saved or retrieved.

### Non-Goals for P1
- replacing the existing KV memory node
- graph-global implicit memory injection everywhere
- autonomous background memory distillation

### Detailed Tasks

#### F02-T01: Add curated memory node types
- [x] Add node types for:
  - `observation_save`
  - `observation_search`
  - `observation_context`
  - `observation_timeline`
- [x] Define stable config and output shapes for each node.
- [x] Keep existing `memory` node behavior intact.

#### F02-T02: Implement engine executors
- [x] Add engine executors for the new node types.
- [x] Wire them to the extended memory gRPC service.
- [x] Respect tenant, graph, run, and session scope automatically.
- [x] Surface explicit runtime errors for unavailable memory backends or contract failures.

#### F02-T03: Integrate curated context with prompts and agents
- [x] Allow prompt/agent flows to consume `observation_context` outputs.
- [x] Define the context composition order:
  - curated observations
  - summary/facts if enabled
  - semantic chunk retrieval if enabled
  - recent buffer if enabled
- [x] Ensure this remains explicit in graph authoring for MVP.

#### F02-T04: Add trace/debug visibility
- [x] Persist observation save/search/context events in run surfaces.
- [x] Show retrieved memory summaries in run detail.
- [x] Make memory influence on prompt/agent execution inspectable.

#### F02-T05: Test coverage
- [x] Engine tests for save/search/context/timeline nodes.
- [x] Integration tests for run-time observation usage.
- [x] Negative tests for:
  - missing scope
  - invalid observation payloads
  - unavailable gRPC methods
  - degraded vector indexing

### Success Criteria
- [x] Workflows can explicitly save and retrieve curated memory end to end.
- [x] Curated memory works with agent and prompt flows without hidden magic.
- [x] Run/debug views show what memory was created or used.
- [x] Existing prompt/agent behavior is unchanged unless curated memory nodes are used.

### Proof / Demo Feat
Run a workflow that saves an observation in one step, retrieves contextual memory in a later step, and shows both operations clearly in the run trace.

---

## P1-F03: Memory Browser, Jackie Journey, and UX Packaging

### Feature Description
Turn curated memory into a user-understandable product surface with a browser UI, node forms, and one supported Jackie-style workflow that demonstrates the value clearly.

### Why This Is P1
- The memory domain and runtime are not enough if users cannot browse, debug, and trust the memory they are creating.
- The MVP needs one opinionated story that demonstrates why curated memory matters.

### User-Facing Outcome
- Users can browse observations, filter them, inspect detail, and view a timeline.
- Builders can author curated-memory nodes without raw JSON.
- The main demo workflow shows explicit memory save and later retrieval.

### Non-Goals for P1
- broad template marketplace expansion
- general-purpose knowledge management workspace
- passive inbox-like memory feeds

### Detailed Tasks

#### F03-T01: Add Memory Browser UI
- [x] Add a Memory Browser page for:
  - search
  - filters
  - detail view
  - timeline view
- [x] Support keyword and semantic retrieval results clearly.
- [x] Make scope and recency visible.

#### F03-T02: Add authoring support
- [x] Add graph editor forms for all curated-memory node types.
- [x] Add palette entries and inspector support.
- [x] Add validation and empty-state guidance.

#### F03-T03: Add memory-aware debugger surfaces
- [x] Show observation hits and context assembly on run detail pages.
- [x] Group memory events so users can see what was saved, what was reused, and why.
- [x] Keep raw payloads available only as drill-down.

#### F03-T04: Package the Jackie-style supported journey
- [x] Define one supported memory-first workflow based on Jackie.
- [x] Ensure the journey demonstrates:
  - explicit observation save
  - later retrieval through context
  - final agent answer using that context
- [x] Keep required integrations narrow and documented.

#### F03-T05: Browser and QA proof
- [x] Add Playwright coverage for:
  - authoring curated-memory nodes
  - saving a graph with memory flow
  - executing save -> later retrieval
  - inspecting memory influence in the run UI
- [x] Record known limitations explicitly.

### Success Criteria
- [x] Users can browse and understand curated memory without source-code reading.
- [x] The editor supports curated-memory authoring end to end.
- [x] A Jackie-style workflow demonstrates the full save -> later retrieval story.
- [x] Browser-level proof exists for the supported memory journey.

### Proof / Demo Feat
Use the product UI to create a Jackie-style workflow that saves an observation during one interaction and uses it in a later run to answer with visible, memory-backed context.

---

## Cross-Cutting P1 Tasks

### P1-X01: Scope Discipline
- [x] Keep P1 focused on explicit curated memory and one supported Jackie-style journey.
- [x] Reject passive capture, public MCP, and broad memory-product expansion from the MVP surface.

### P1-X02: Internal QA Matrix
- [x] Build a QA matrix covering:
  - observation create/update/delete
  - search and timeline behavior
  - vector indexing lag/fallback
  - save -> later retrieval runtime flow
  - Jackie-style browser proof
- [x] Record known limitations and unsupported states.

### P1-X03: Internal Product Narrative
- [x] Write one internal positioning note covering:
  - why curated memory exists
  - how it differs from KV/session/vector memory
  - which workflows are officially supported in MVP

---

## Suggested Build Order

### Week 1
- F01-T01 to F01-T04
- F02-T01
- F03-T04

### Week 2
- F01-T05 to F01-T06
- F02-T02 to F02-T04
- F03-T01 to F03-T03

### Week 3
- F02-T05
- F03-T05
- P1-X01 to P1-X03

## Final Definition of Done
- [x] P1-F01 complete
- [x] P1-F02 complete
- [x] P1-F03 complete
- [x] ForgeGraph has a memory-first MVP story built around curated observations
- [x] Users can save, retrieve, inspect, and debug curated memory through the product UI
- [x] The Jackie-style workflow proves the memory value end to end
