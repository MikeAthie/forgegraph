# ForgeGraph MVP Remediation Tasks

## Purpose
This task list turns the current repo audit into an execution backlog for the gaps that still block a sellable MVP.

It is intentionally scoped to the current codebase, so it does not re-plan capabilities that already exist.

## Already Present: Do Not Re-Implement
- Replay from checkpoint and run resume flows already exist.
- `thread_id`, checkpoints, node runs, WS/SSE streaming, and run history already exist.
- LLM budgets, quotas, analytics endpoints, and tenant entitlements already exist.
- RBAC, audit logs, tenant policies, retention policies, OIDC, SCIM, and billing models already exist.
- Webhook-triggered runs and OAuth credential flows already exist.
- Graph cycles are already supported behind `metadata.allow_cycles`.
- The three-tier memory foundation already exists:
  - Tier 1 `MessageBuffer`
  - Tier 2 `MemoryStore`/Redis summaries and session memory
  - Tier 3 semantic retrieval over `MemoryChunk`

The work below focuses on what is still missing or structurally inconsistent.

## Priority Order
1. P0-A: Agent runtime primitive
2. P0-B: Marketplace runtime delivery
3. P0-C: Cloud-safe execution policy
4. P0-D: Stable contracts and missing specs
5. P1-A: Curated memory domain and contracts
6. P1-B: Curated memory runtime integration
7. P1-C: Memory Browser and Jackie-style UX packaging

---

## P0-A: Agent Runtime Primitive

### Objective
Ship a real `agent` execution primitive instead of relying on wizard/preset UX over `prompt` + `tool` composition.

### Deliverable
A first-class `agent` node type with loop semantics, tool calling, stop conditions, step limits, durable traces, and HITL hooks.

### Microtasks

#### A1. Define the agent contract
- [ ] Write `docs/architecture/agent-node.md` covering:
  - `agent` node goals and non-goals
  - loop model
  - state shape
  - stop conditions
  - error handling
  - replay semantics
- [ ] Decide whether the first version is:
  - internal loop only inside one node, or
  - graph-visible loop using existing `allow_cycles`
- [ ] Standardize the first state schema:
  - `messages`
  - `scratchpad`
  - `tool_results`
  - `final_output`
  - `step_count`
- [ ] Define config fields:
  - `provider`
  - `model`
  - `credential_id`
  - `tools`
  - `system_prompt`
  - `max_steps`
  - `max_tool_calls`
  - `stop_condition`
  - `temperature`
  - `budget_guard`

#### A2. Add backend schema support
- [ ] Add `agent` to backend node type enums and validation.
- [ ] Add `agent` config schema in backend node schemas.
- [ ] Extend graph validation rules to validate:
  - required `tools`
  - positive step limits
  - provider and credential compatibility
- [ ] Add serializer coverage for saving/loading graphs with `agent` nodes.
- [ ] Add migration only if any stored DB enum or persisted choice set requires it.

#### A3. Add engine node support
- [ ] Add `agent` to engine node type definitions.
- [ ] Add `agent_executor.go` with a loop:
  - call model
  - inspect tool call decision
  - execute tool
  - append tool result
  - repeat until stop
- [ ] Reuse the existing credential resolution path instead of inventing a second one.
- [ ] Reuse existing tenant policy enforcement for provider/model allowlists.
- [ ] Reuse existing event emitter to emit per-step progress.
- [ ] Add a hard fail when `max_steps` or `max_tool_calls` is exceeded.

#### A4. Add agent event and trace shape
- [ ] Define agent step event payloads:
  - `agent.step.started`
  - `agent.tool.called`
  - `agent.tool.completed`
  - `agent.step.completed`
  - `agent.completed`
- [ ] Normalize those events into existing run/node event persistence.
- [ ] Persist enough step metadata for replay/debugging:
  - tool name
  - tool args
  - tool result summary
  - model response summary
  - stop reason
- [ ] Redact sensitive tool args before persistence.

#### A5. Add HITL guardrails for tool calls
- [ ] Define config for “approval before tool execution”.
- [ ] Allow an agent node to pause before selected tools.
- [ ] Reuse existing approval task flow instead of creating a parallel HITL system.
- [ ] Store resume context so the loop continues from the paused tool call, not from step 0.

#### A6. Add frontend authoring support
- [ ] Add `agent` to frontend graph types.
- [ ] Add an Agent node form with:
  - provider/model/credential
  - system prompt
  - allowed tools
  - max steps
  - stop conditions
  - approval-required tools
- [ ] Update the node palette to expose `agent` as a first-class node.
- [ ] Update the agent wizard to create a real `agent` node instead of a preset-only pseudo-flow.
- [ ] Add inspector tabs for:
  - config
  - run data
  - step trace

#### A7. Test coverage
- [ ] Backend unit tests for agent config validation.
- [ ] Engine unit tests for:
  - normal stop
  - max step stop
  - tool failure
  - approval pause/resume
  - invalid tool selection
- [ ] Integration tests for:
  - graph save/load with agent node
  - run start with agent node
  - replay after agent pause
- [ ] Frontend tests for:
  - Agent form rendering
  - wizard creating real agent nodes
  - trace rendering

#### A8. Exit criteria
- [ ] A graph can contain a real `agent` node.
- [ ] The engine executes multi-step tool loops without manual graph wiring.
- [ ] Runs expose agent step traces in the UI.
- [ ] HITL pauses and resumes inside an agent loop.

---

## P0-B: Marketplace Runtime Delivery

### Objective
Make marketplace packages either truly executable or explicitly limited to templates. Remove the current mixed model.

### Deliverable
A single package model that the backend, frontend, and engine all implement consistently.

### Decision Gate
Choose one and document it before coding:
- Option 1: Marketplace packages are node templates only.
- Option 2: Marketplace packages can deliver runtime artifacts to the engine.

### Microtasks

#### B1. Make the package model explicit
- [ ] Write `docs/architecture/marketplace-runtime-contract.md`.
- [ ] Define package classes:
  - `template_http`
  - `template_prompt`
  - `runtime_tool`
  - `runtime_transform`
- [ ] Decide which classes are allowed in Cloud for MVP.
- [ ] Define the review policy for each class.

#### B2. Extend release metadata
- [ ] Add explicit release fields for:
  - `package_kind`
  - `runtime_manifest`
  - `manifest_version`
  - `review_notes`
  - `cloud_allowed`
- [ ] Reject releases whose metadata is incomplete for their package class.
- [ ] For template-only packages, validate `execution_node_type` + `config_defaults`.
- [ ] For runtime packages, validate the manifest schema before approval.

#### B3. Implement backend manifest delivery
- [ ] Add a manifest rendering service in the backend.
- [ ] Add an endpoint for engine manifest fetch by tenant if runtime packages are enabled.
- [ ] Include package installation versioning and cache headers.
- [ ] Make installations tenant-scoped and deterministic.
- [ ] Add signature or checksum generation for emitted manifests.

#### B4. Implement engine package loading
- [ ] Decide refresh model:
  - polling
  - startup only
  - admin-triggered refresh
- [ ] Add a tenant-aware manifest loader if runtime packages are enabled.
- [ ] Keep filesystem manifests for self-host/dev compatibility.
- [ ] Merge runtime-delivered manifests with built-in manifests safely.
- [ ] Reject invalid or untrusted manifests with visible logs and metrics.

#### B5. Fix frontend semantics
- [ ] Surface package class in the marketplace UI.
- [ ] If package is template-only, label it as a template.
- [ ] If package is runtime-backed, label it as installed and executable.
- [ ] Disable unsupported package classes in quick-add UI.
- [ ] Show missing runtime reason when a package cannot execute.

#### B6. Test coverage
- [ ] Integration tests for:
  - install package
  - fetch installed manifest set
  - engine refresh
  - execute installed runtime package
- [ ] Frontend tests for package labeling and disabled states.
- [ ] Contract tests for manifest schema validation.

#### B7. Exit criteria
- [ ] Package install means the same thing across backend, frontend, and engine.
- [ ] No approved package can appear executable in UI while being non-executable in runtime.
- [ ] Runtime-backed package delivery is tenant-aware and versioned.

---

## P0-C: Cloud-Safe Execution Policy

### Objective
Block unsafe runtime behavior before expanding marketplace/runtime delivery.

### Deliverable
A clear Cloud execution policy that disables or gates `exec` and enforces outbound controls consistently.

### Microtasks

#### C1. Introduce runtime mode
- [ ] Add an explicit runtime mode flag:
  - `self_hosted`
  - `cloud`
- [ ] Thread that mode through backend and engine config.
- [ ] Document what each mode allows.

#### C2. Block unsafe tool kinds in Cloud
- [ ] In engine tool loading, reject `exec` manifests in `cloud` mode.
- [ ] In backend marketplace review, reject `runtime_tool` releases that require `exec` in `cloud` mode.
- [ ] In frontend admin UI, show why the package is blocked.
- [ ] Add a kill switch to disable all runtime packages quickly.

#### C3. Tighten egress policy enforcement
- [ ] Extend current tenant policy docs to cover:
  - HTTP nodes
  - tool HTTP calls
  - provider-host allowlists
- [ ] Add shared policy evaluation tests across HTTP executor and tool executor.
- [ ] Add clear error codes for:
  - blocked host
  - blocked provider
  - blocked model
  - blocked tool kind

#### C4. Add auditability
- [ ] Log policy-denied executions to audit logs.
- [ ] Add package review audit events for blocked unsafe releases.
- [ ] Add admin-visible telemetry for rejected runtime loads.

#### C5. Test coverage
- [ ] Engine tests for `exec` rejection in cloud mode.
- [ ] Backend integration tests for blocked release approval.
- [ ] Integration tests for egress-denied tool execution.

#### C6. Exit criteria
- [ ] Cloud mode cannot execute `exec` tools.
- [ ] Unsafe packages fail before installation or load.
- [ ] Policy denials are visible to operators and auditable.

---

## P0-D: Stable Contracts and Missing Specs

### Objective
Publish the contracts the code already assumes so integrations and future work stop relying on comments and drift.

### Deliverable
Versioned graph and run-event specs in the repo.

### Microtasks

#### D1. Publish Graph JSON spec
- [ ] Create root `SPECS.md`.
- [ ] Document:
  - node model
  - edge model
  - metadata
  - editor-only state
  - sentinel `START`/`END`
  - cycle semantics
  - `allow_cycles`
- [ ] Include the new `agent` node contract once implemented.
- [ ] Link the spec from README and frontend graph type comments.

#### D2. Publish run event contract
- [ ] Create `docs/ops/run-event-contract.md`.
- [ ] Document persisted event types and payload fields.
- [ ] Document SSE/WS message envelopes and compatibility rules.
- [ ] Document redaction guarantees and non-guarantees.

#### D3. Clean documentation drift
- [ ] Update README feature list to match the real repo state.
- [ ] Add “already implemented” sections for:
  - replay
  - budgets
  - RBAC
  - OAuth
  - webhook triggers
- [ ] Remove or rewrite outdated MVP claims in docs that describe missing features as if they do not exist.

#### D4. Test and validation
- [ ] Add contract tests for example Graph JSON fixtures.
- [ ] Add contract tests for event payload serialization if a shared schema is introduced.

#### D5. Exit criteria
- [ ] `SPECS.md` exists and is linked from the code/docs that reference it.
- [ ] Event payloads have one documented contract.
- [ ] Current docs no longer materially misdescribe repo capabilities.

---

## P1-A: Curated Memory Domain and Contracts

### Objective
Add a native curated memory subdomain that introduces structured observations, session-aware context assembly, deterministic search, and additive contracts over the existing three-tier memory foundations.

### Deliverable
A first-class `MemoryObservation` domain with REST and additive gRPC contracts, async observation indexing, and stable service semantics.

### Microtasks
- [ ] Write `docs/architecture/curated-memory.md` and lock the MVP decisions:
  - native subdomain
  - internal-only exposure
  - explicit capture first
  - hybrid FTS + vector retrieval
  - graph/run/session scope
- [ ] Add `MemoryObservation` model and migration.
- [ ] Add indexes for:
  - tenant + recency
  - tenant + topic_key
  - FTS search
- [ ] Add REST endpoints for:
  - create/update/delete
  - search
  - detail
  - timeline
  - context
- [ ] Extend memory gRPC with additive methods:
  - `SaveObservation`
  - `SearchObservations`
  - `GetObservation`
  - `GetContext`
  - `GetTimeline`
- [ ] Keep `RetrieveMemory`, `MemoryEntry`, and `MemoryChunk` backward compatible.
- [ ] Add service behavior for:
  - normalization
  - dedupe
  - topic upsert
  - soft delete
  - async observation-to-vector indexing

### Exit criteria
- [ ] Curated memory exists as a native backend domain.
- [ ] REST and gRPC contracts are stable and additive.
- [ ] Observation writes do not block on embeddings.
- [ ] Existing KV/session/vector memory features remain intact.

---

## P1-B: Curated Memory Runtime Integration

### Objective
Expose curated memory to workflows and agents as explicit runtime primitives.

### Deliverable
New observation node types and runtime integration that let graphs save, search, contextualize, and inspect curated memory explicitly.

### Microtasks
- [ ] Add node types for:
  - `observation_save`
  - `observation_search`
  - `observation_context`
  - `observation_timeline`
- [ ] Add engine executors for those node types.
- [ ] Wire them to the extended memory gRPC service.
- [ ] Respect tenant, graph, run, and session scope automatically.
- [ ] Define stable config and output shapes for each node.
- [ ] Persist observation save/search/context events into run surfaces.
- [ ] Allow prompt/agent flows to consume explicit curated-context outputs.
- [ ] Keep the existing KV `memory` node unchanged.

### Exit criteria
- [ ] Workflows can explicitly save and retrieve curated memory end to end.
- [ ] Run/debug surfaces show what memory was saved or used.
- [ ] Prompt/agent behavior remains unchanged unless curated-memory nodes are used.

---

## P1-C: Memory Browser and Jackie-Style UX Packaging

### Objective
Turn curated memory into a user-understandable product surface and one supported memory-first workflow.

### Deliverable
A Memory Browser UI, curated-memory authoring support in the editor, and one Jackie-style journey proving save -> later retrieval -> final answer.

### Microtasks
- [ ] Add a Memory Browser page for:
  - search
  - filters
  - detail
  - timeline
- [ ] Add graph editor forms and palette entries for curated-memory nodes.
- [ ] Add memory-aware debugger surfaces on run detail pages.
- [ ] Define one supported Jackie-style workflow that demonstrates:
  - explicit observation save
  - later retrieval through context
  - final agent answer using that context
- [ ] Add Playwright coverage for authoring and running the supported memory flow.
- [ ] Keep required integrations narrow and documented.

### Exit criteria
- [ ] Users can browse and understand curated memory without source-code reading.
- [ ] The editor supports curated-memory authoring end to end.
- [ ] The Jackie-style workflow proves the memory value end to end.

---

## Suggested Delivery Sequence

### Sprint 1
- P0-A A1-A3
- P0-B B1-B2
- P0-C C1-C2
- P0-D D1

### Sprint 2
- P0-A A4-A8
- P0-B B3-B7
- P0-C C3-C6
- P0-D D2-D5

### Sprint 3
- P1-A
- P1-B
- P1-C

## Final Readiness Checklist
- [ ] `agent` is a real runtime primitive.
- [ ] Marketplace semantics are consistent end-to-end.
- [ ] Cloud mode blocks unsafe execution.
- [ ] Graph and event contracts are documented and versionable.
- [ ] Curated memory is the next implementation-ready product differentiator.
