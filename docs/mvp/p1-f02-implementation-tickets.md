# P1-F02 Implementation Tickets

## Goal
Convert `P1-F02` into reviewable implementation slices with explicit file targets, acceptance criteria, tests, and PR boundaries.

`P1-F02` is the curated-memory runtime epic:
- engine must execute observation-centric node types
- runtime must call the new additive memory gRPC surface
- prompts and agents must be able to consume explicit curated context
- run/debug surfaces must persist enough memory activity to explain what happened

## Status
`P1-F02` is complete as of March 13, 2026.

## Dependency
`P1-F01` should be merged or stable first.

This ticket set assumes:
- `MemoryObservation` exists
- REST and gRPC observation contracts are stable
- async indexing/dedupe semantics are already decided

## Current Repo Reality
The current codebase already has:
- the `memory` KV node and executor
- prompt and agent runtime paths
- run events, node runs, trace surfaces, replay hooks, and approvals
- graph editor infrastructure and palette/form systems

The current gap is specific:
- there are no observation node types
- the engine cannot save/search/contextualize curated memory
- prompt and agent nodes do not yet consume explicit curated context outputs
- observation-related run behavior is not yet represented as a first-class trace surface

## Ticketing Strategy
The safest split is:
1. shared node contracts for observation runtime nodes
2. engine executor core and gRPC client integration
3. prompt/agent context composition and runtime shaping
4. backend run/event persistence and API exposure
5. integration and proof coverage

This keeps runtime semantics stable before debugger and full product UX work in `P1-F03`.

---

## PR-1: Observation Node Contracts

### Objective
Introduce the new curated-memory node types to the shared graph/runtime contracts before implementing their execution.

### Scope
- backend node enums and validation
- engine node type definitions
- frontend/shared type compatibility only

### Expected Files

#### Backend files
- `backend/domain/value_objects/node_types.py`
- `backend/domain/value_objects/node_schemas.py`
- `backend/domain/services/graph_validator.py`
- `backend/adapters/api/graphs/serializers.py`
- `backend/tests/unit/domain/test_node_schemas.py`
- `backend/tests/unit/domain/test_graph_validator.py`

#### Engine files
- `engine/domain/value/node_type.go`

#### Frontend/shared files
- `frontend/lib/graph-types.ts`
- `frontend/lib/node-type-signatures.ts`
- `frontend/lib/type-inference.ts`

### Acceptance Criteria
- [x] The graph contract supports:
  - `observation_save`
  - `observation_search`
  - `observation_context`
  - `observation_timeline`
- [x] Validation rules exist for required config and unsupported config combinations.
- [x] Node contracts are stable before runtime implementation starts.

### Tests
- backend unit tests for schema validation
- frontend/shared type and inference tests if those helpers are touched

### PR Boundary Notes
- Do not add engine executors here.
- Do not add full frontend authoring UX here.

---

## PR-2: Engine Executors and Memory gRPC Consumption

### Objective
Allow the engine to execute curated-memory node types against the additive gRPC memory service.

### Scope
- engine executors
- gRPC client plumbing
- scheduler/runtime integration
- base engine tests

### Expected Files

#### Engine files
- `engine/adapter/executor/observation_save_executor.go` (new)
- `engine/adapter/executor/observation_search_executor.go` (new)
- `engine/adapter/executor/observation_context_executor.go` (new)
- `engine/adapter/executor/observation_timeline_executor.go` (new)
- `engine/adapter/gateway/memory_client.go` or equivalent client wrapper
- `engine/application/usecase/scheduler.go`
- `engine/application/usecase/scheduler_test.go`
- `engine/main.go`

#### Tests
- `engine/adapter/executor/*_test.go` (new)
- `engine/test/integration_test.go`

### Acceptance Criteria
- [x] Each curated-memory node type executes successfully through gRPC.
- [x] Runtime errors are explicit for unavailable or invalid memory responses.
- [x] Scheduler integration works without breaking existing node types.
- [x] Node outputs are stable and usable by downstream nodes.

### Tests
- engine unit tests for each executor
- integration tests for minimal graphs using the new node types

### PR Boundary Notes
- Keep prompt/agent context composition out of this PR.
- Do not add frontend authoring here.

---

## PR-3: Prompt and Agent Context Composition

### Objective
Allow prompt and agent runtime paths to consume explicit curated context outputs in a stable and inspectable way.

### Scope
- prompt executor integration
- agent executor integration
- explicit context assembly order
- output shaping for traces/debugging

### Expected Files

#### Engine files
- `engine/adapter/executor/prompt_executor.go`
- `engine/adapter/executor/prompt_executor_test.go`
- `engine/adapter/executor/agent_executor.go`
- `engine/adapter/executor/agent_executor_test.go`
- `engine/application/port/run_context.go`

#### Optional backend contract files if read models must change first
- `backend/adapters/api/runs/serializers.py`

### Acceptance Criteria
- [x] Prompt and agent flows can consume curated context explicitly.
- [x] Context composition order is stable:
  - curated observations
  - summary/facts
  - semantic chunk retrieval
  - recent buffer
- [x] Existing flows behave the same unless curated-memory nodes are present.
- [x] The runtime emits enough information to explain curated-memory usage later.

### Tests
- prompt executor tests for context composition
- agent executor tests for memory-backed context use
- regression tests for prompt/agent runs without curated-memory nodes

### PR Boundary Notes
- Keep UI and run-page rendering out of this PR.
- Avoid implicit global memory injection for MVP.

---

## PR-4: Backend Run/Event Persistence for Curated Memory Activity

### Objective
Persist and expose curated-memory runtime activity so run surfaces can explain what was saved, searched, and reused.

### Scope
- event normalization
- run detail shaping
- node-run output enrichment
- API exposure for future debugger UI

### Expected Files

#### Backend files
- `backend/adapters/api/runs/serializers.py`
- `backend/adapters/api/runs/views.py`
- `backend/tests/integration/adapters/test_run_api.py`
- `backend/tests/integration/adapters/test_run_ws.py`

#### Optional files depending on implementation
- `backend/infrastructure/orm/models.py`
- `backend/domain/events/run_events.py`

### Acceptance Criteria
- [x] Observation save/search/context/timeline events persist in run history.
- [x] Run detail exposes enough information for future debugger surfaces.
- [x] Sensitive observation payloads respect redaction rules where required.
- [x] Non-memory runs remain unchanged.

### Tests
- integration tests for run detail payloads
- SSE/WS event availability tests if event streaming changes
- redaction tests where observation content is sensitive

### PR Boundary Notes
- Keep heavy frontend changes out of this PR.
- Backend should expose a stable read model before `P1-F03` consumes it.

---

## PR-5: Integration Proof and Runtime Readiness

### Objective
Prove the runtime path end to end with curated-memory graphs before the full Memory Browser and Jackie UX work lands.

### Scope
- cross-stack integration coverage
- minimal demo graph fixture
- explicit runtime acceptance criteria

### Expected Files

#### Backend / engine tests
- `backend/tests/integration/adapters/test_run_api.py`
- `engine/test/integration_test.go`

#### Docs / planning files
- `docs/mvp/mvp-tasks-p1.md`
- `docs/mvp/forgegraph-mvp-implementation-plan.md`
- `docs/mvp/p1-f02-implementation-tickets.md`

### Acceptance Criteria
- [x] One graph can save an observation and another step can retrieve curated context successfully.
- [x] Prompt or agent output can be shown to depend on curated context.
- [x] The runtime proof is test-backed, not just manually described.
- [x] `P1-F03` can start from a stable runtime and read model.

### Tests
- backend/engine integration tests for save -> later retrieval
- regression tests for runtime failure paths and degraded vector behavior

### PR Boundary Notes
- This PR should prove the runtime contract, not finish the product UX.
- Keep the demo fixture narrow and repeatable.

---

## Recommended Merge Order
1. PR-1
2. PR-2
3. PR-3
4. PR-4
5. PR-5

## Final Ticket-Level Definition of Done
- [x] Observation node contracts are stable
- [x] Engine can execute curated-memory nodes
- [x] Prompt and agent flows can consume explicit curated context
- [x] Run surfaces expose enough memory activity for debugger work
- [x] `P1-F03` can proceed without inventing runtime semantics
