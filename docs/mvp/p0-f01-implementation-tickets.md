# P0-F01 Implementation Tickets

## Goal
Convert `P0-F01` into reviewable implementation slices with explicit file targets, acceptance criteria, tests, and PR boundaries.

`P0-F01` is the agent runtime primitive epic:
- backend must understand a real `agent` node
- engine must execute it
- frontend must author it
- run/debug surfaces must explain it

## Ticketing Strategy
The safest split is:
1. contract and schema
2. engine runtime core
3. backend run/event integration
4. frontend authoring
5. debugger and workflow polish

This keeps each PR understandable and avoids cross-stack merges that are too large to review safely.

---

## PR-1: Agent Contract and Graph Schema

### Objective
Introduce the `agent` node to the shared contract and graph validation layers without yet implementing runtime execution.

### Scope
- docs
- backend enums and validation
- frontend type contracts

### Expected Files

#### New files
- `docs/architecture/agent-node.md`

#### Backend files
- `backend/domain/value_objects/node_types.py`
- `backend/domain/value_objects/node_schemas.py`
- `backend/domain/services/graph_validator.py`
- `backend/adapters/api/graphs/serializers.py`
- `backend/tests/unit/domain/test_node_schemas.py`
- `backend/tests/unit/domain/test_graph_validator.py`
- `backend/tests/integration/adapters/test_graph_api.py`

#### Frontend files
- `frontend/lib/graph-types.ts`
- `frontend/lib/node-type-signatures.ts`
- `frontend/lib/type-inference.ts`
- `frontend/lib/graph-validator.ts`
- `frontend/__tests__/unit/lib/graph-validator.test.ts`
- `frontend/__tests__/lib/node-type-signatures.test.ts`
- `frontend/__tests__/lib/type-inference.test.ts`

### Acceptance Criteria
- [ ] `agent` is a valid node type in backend and frontend contracts.
- [ ] Graph validation accepts valid `agent` nodes and rejects malformed ones.
- [ ] The `agent` node contract is written down in `docs/architecture/agent-node.md`.
- [ ] No runtime execution changes are required for this PR to merge.

### Tests
- backend unit tests for schema validation
- backend integration tests for graph save/validate endpoints
- frontend unit tests for graph types and validation helpers

### PR Boundary Notes
- Do not add engine executor code here.
- Do not add frontend form UX here beyond type-level compatibility.

---

## PR-2: Engine Agent Runtime Core

### Objective
Add the engine-side `agent` executor and make the scheduler able to run a real `agent` node.

### Scope
- engine node type support
- core loop execution
- base engine tests

### Expected Files

#### Engine files
- `engine/domain/value/node_type.go`
- `engine/adapter/executor/agent_executor.go` (new)
- `engine/adapter/executor/agent_executor_test.go` (new)
- `engine/application/port/event_emitter.go`
- `engine/application/usecase/scheduler.go`
- `engine/application/usecase/scheduler_test.go`
- `engine/main.go`

#### Optional shared/runtime files depending on implementation
- `engine/domain/entity/state.go`
- `engine/domain/entity/run.go`
- `engine/application/port/node_executor.go`

### Acceptance Criteria
- [ ] The engine can execute an `agent` node in a minimal graph.
- [ ] The loop stops correctly on final-answer and step-limit conditions.
- [ ] Scheduler integration works without breaking existing node types.
- [ ] Base engine events for agent execution are emitted in a stable shape.

### Tests
- engine unit tests for:
  - normal completion
  - step-limit completion
  - tool selection flow
  - invalid tool selection
- scheduler tests for graphs containing an `agent` node

### PR Boundary Notes
- Keep approval/HITL support minimal or stubbed if needed.
- Do not attempt full frontend authoring in this PR.

---

## PR-3: Backend Run/Event Integration for Agent Steps

### Objective
Persist and expose agent execution state so backend APIs and run detail views have something real to show.

### Scope
- backend event normalization/persistence
- run detail serialization
- approval reuse for agent tool approvals if included at this stage

### Expected Files

#### Backend files
- `backend/adapters/api/runs/serializers.py`
- `backend/adapters/api/runs/views.py`
- `backend/domain/events/run_events.py`
- `backend/infrastructure/orm/models.py`
- `backend/tests/integration/adapters/test_run_api.py`
- `backend/tests/integration/adapters/test_run_ws.py`

#### If approval integration lands here
- `backend/adapters/api/approvals/views.py`
- `backend/adapters/api/approvals/serializers.py`
- `backend/tests/integration/adapters/test_approvals_api.py` (new or existing coverage expansion)

### Acceptance Criteria
- [ ] Agent step events persist cleanly in run event history.
- [ ] Run detail payloads expose enough information for the UI to render agent steps.
- [ ] If approval-required tools are supported in this slice, pause/resume uses the existing approval flow.
- [ ] Existing non-agent run flows remain intact.

### Tests
- integration tests for run detail payloads
- integration tests for SSE/WS event availability
- integration tests for pause/resume if agent approvals land here

### PR Boundary Notes
- Avoid large UI changes in this PR.
- Backend should expose the data contract before frontend consumes all of it.

---

## PR-4: Frontend Agent Authoring

### Objective
Make the `agent` node creatable and configurable in the graph editor.

### Scope
- palette
- config dialog
- node display
- wizard conversion away from pseudo-agent-only flows

### Expected Files

#### Frontend files
- `frontend/lib/graph-types.ts`
- `frontend/lib/node-palette-catalog.ts`
- `frontend/components/graph-editor/GraphEditor.tsx`
- `frontend/components/graph-editor/NodeConfigDialog.tsx`
- `frontend/components/graph-editor/NodeInspector.tsx`
- `frontend/components/graph-editor/forms/node-form-registry.ts`
- `frontend/components/graph-editor/forms/index.ts`
- `frontend/components/graph-editor/forms/AgentNodeForm.tsx` (new)
- `frontend/components/graph-editor/nodes/GraphNode.tsx`
- `frontend/components/graph-editor/wizard/AgentWizard.tsx`
- `frontend/lib/agent-wizard-presets.ts`

#### Frontend tests
- `frontend/__tests__/components/graph-editor/GraphEditor.test.tsx`
- `frontend/__tests__/components/graph-editor/NodeInspector.test.tsx`
- `frontend/__tests__/components/graph-editor/NodeConfigDialog.test.tsx`
- `frontend/__tests__/components/graph-editor/wizard/AgentWizard.test.tsx`
- `frontend/__tests__/components/graph-editor/forms/AgentNodeForm.test.tsx` (new)

### Acceptance Criteria
- [ ] Users can add an `agent` node from the editor.
- [ ] Users can configure agent runtime fields in the node form.
- [ ] The current agent wizard creates a real `agent` node or a real agent-based graph entry point.
- [ ] Agent nodes render with clear labels and distinguishable visual identity.

### Tests
- frontend unit tests for node form rendering and config save
- graph editor interaction tests for adding/configuring an `agent` node

### PR Boundary Notes
- Do not try to solve full debugger UX here.
- Authoring support should rely on the backend/frontend contracts from PR-1.

---

## PR-5: Agent Debugger and HITL Polish

### Objective
Make agent runs inspectable and usable from the run/debugging surfaces.

### Scope
- step timeline and drill-down
- tool-call trace rendering
- approval state UX
- replay affordances for agent runs

### Expected Files

#### Frontend files
- `frontend/pages/runs/[runId].tsx`
- `frontend/components/graph-editor/GraphEditor.tsx`
- `frontend/components/graph-editor/NodeInspector.tsx`
- `frontend/lib/api.ts`
- `frontend/lib/error-messages.ts`
- `frontend/__tests__/unit/pages/runs.test.tsx`
- `frontend/__tests__/e2e/runs.spec.ts`

#### Backend files if additional payload shaping is needed
- `backend/adapters/api/runs/views.py`
- `backend/adapters/api/runs/serializers.py`
- `backend/tests/integration/adapters/test_run_api.py`

### Acceptance Criteria
- [ ] Agent runs show step-level drill-down in the run UI.
- [ ] Tool calls and stop reason are visible.
- [ ] Approval-required agent steps are understandable in the UI.
- [ ] Replay/retry affordances for agent runs are clearly scoped.

### Tests
- unit tests for run page rendering
- e2e tests for:
  - paused agent run
  - resumed agent run
  - failed agent run with visible trace

### PR Boundary Notes
- This is the first PR where the feature should feel complete for end users.
- Keep any additional backend shape changes tightly scoped to UI needs.

---

## Optional PR-0: Doc-Only Precursor

### Objective
Land the contract docs before implementation begins if the team wants design review first.

### Expected Files
- `docs/architecture/agent-node.md`
- `docs/mvp/mvp-tasks-p0.md`
- `docs/mvp/forgegraph-mvp-implementation-plan.md`
- `docs/mvp/p0-f01-implementation-tickets.md`

### Acceptance Criteria
- [ ] Implementation can start with clear review boundaries and agreed semantics.

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
- [ ] `agent` node works in contract, runtime, backend state, editor authoring, and run debugging
- [ ] Test coverage exists across backend, engine, and frontend layers
- [ ] The product can demo a real agent workflow without pretending preset composition is the agent feature
