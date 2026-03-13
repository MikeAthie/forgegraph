# P0: Sellable MVP Remediation Tasks

## Objective
Deliver the smallest P0 slice that turns ForgeGraph from a technically impressive platform into a coherent, sellable MVP for agent workflows.

P0 is not "add more features."
P0 is:
- making `agent` a real runtime primitive
- making marketplace semantics honest and executable
- making Cloud execution safe
- publishing the missing contracts the code already assumes

## What P0 Must Achieve
At the end of P0, ForgeGraph should be able to make the following promise without hand-waving:

"You can visually build, run, inspect, and safely operate an agent workflow with approved tools and clear execution contracts."

## What Is Already Done
The following capabilities exist in the repo already and are not P0 build targets:
- replay from checkpoint and run resume
- `thread_id`, run history, node runs, WS/SSE streaming
- LLM budgets, quotas, usage analytics, entitlements
- RBAC, audit logs, retention policies, tenancy models
- webhook-triggered runs
- OAuth credential flows
- cycle support behind `metadata.allow_cycles`

P0 work should reuse those capabilities, not replace them.

## P0 Exit State
P0 is complete only when all of the following are true:
- [x] Users can add a real `agent` node and run it end-to-end.
- [x] Marketplace packages mean the same thing in backend, frontend, and engine.
- [x] Cloud mode blocks unsafe execution paths such as `exec`.
- [x] `SPECS.md` and the run event contract exist and match real behavior.
- [x] The product has a narrow, credible MVP story built on top of the above.

## Implementation Readiness
This file is ready to drive implementation.

Use these docs as the execution entry point:
- `docs/mvp/forgegraph-mvp-implementation-plan.md`
- `docs/mvp/p0-f01-implementation-tickets.md`
- `docs/mvp/p0-f02-implementation-tickets.md`

Implementation order for P0:
1. `P0-F01`
2. `P0-F02`
3. `P0-F03`
4. `P0-F04`

Start work immediately with these first PRs:
- `P0-F01`: contract/schema PR from `p0-f01-implementation-tickets.md`
- `P0-F02`: package contract/release model PR from `p0-f02-implementation-tickets.md`
- `P0-F03`: policy contract PR defining Cloud-safe runtime rules before enforcement changes
- `P0-F04`: doc-first PR creating `SPECS.md` and the run event contract

No additional roadmap work should be required before opening the first implementation PRs for P0.

---

## P0-F01: Agent Node as a First-Class Runtime Primitive

### Feature Description
Introduce a real `agent` node type that handles model-to-tool looping internally instead of forcing users to simulate agent behavior by chaining `prompt`, `tool`, and `http` nodes manually.

This is the most important P0 feature because the current product language says "agents," but the runtime still exposes only workflow composition primitives.

### Why This Is P0
- It closes the biggest product truth gap.
- It reduces graph complexity for real users.
- It aligns the runtime model with market expectations.
- It gives the debugger something meaningful to show at the step level.

### User-Facing Outcome
- A builder can drag in an `agent` node, choose a model, allow tools, define limits, and run it.
- The run view shows agent steps, tool calls, stop reason, and paused approvals when needed.

### Non-Goals for P0
- Multi-agent collaboration
- long-horizon planning systems
- autonomous background task queues for agents
- graph-wide visual loop authoring as the primary UX

### Detailed Tasks

#### F01-T01: Define the agent execution contract
- [x] Write `docs/architecture/agent-node.md`.
- [x] Decide the first implementation shape:
  - internal loop inside one node
  - no graph-level loop authoring required for v1
- [x] Define the canonical runtime state:
  - `messages`
  - `scratchpad`
  - `tool_results`
  - `final_output`
  - `step_count`
- [x] Define node config fields:
  - `provider`
  - `model`
  - `credential_id`
  - `system_prompt`
  - `tools`
  - `max_steps`
  - `max_tool_calls`
  - `temperature`
  - `approval_required_tools`
  - `stop_condition`
- [x] Define stop reasons:
  - final answer returned
  - max steps reached
  - max tool calls reached
  - tool policy denied
  - approval required

#### F01-T02: Add backend graph/schema support
- [x] Add `agent` to backend node type enums.
- [x] Add agent config schema to backend validation.
- [x] Extend graph serializers to support `agent`.
- [x] Add validation rules for:
  - missing tools
  - invalid provider/model
  - invalid step limits
  - incompatible credentials
- [x] Decide whether existing saved graphs need migration support or only forward compatibility.

#### F01-T03: Add engine support for agent execution
- [x] Add `agent` to engine node type definitions.
- [x] Create `agent_executor.go`.
- [x] Implement the execution loop:
  - call model
  - inspect tool call intent
  - execute tool
  - append tool result
  - repeat until stop
- [x] Reuse existing credential resolution and tenant policy enforcement.
- [x] Fail clearly when step or tool-call budgets are exceeded.
- [x] Ensure output shape is stable for downstream nodes.

#### F01-T04: Add step-level tracing and persistence
- [x] Define step-level events for agent runs.
- [x] Normalize those events into existing run and node event persistence.
- [x] Persist enough detail for:
  - debugging
  - replay
  - support
  - audit
- [x] Redact sensitive tool arguments and credential-derived fields before persistence.

#### F01-T05: Reuse HITL for agent tool approvals
- [x] Define how an agent pauses before selected tools.
- [x] Reuse the existing approval task flow.
- [x] Store enough context to resume from the paused tool call instead of restarting the loop.
- [x] Ensure replay semantics are documented for paused agent runs.

#### F01-T06: Add frontend authoring support
- [x] Add `agent` to frontend graph types.
- [x] Add an Agent node form with model, credential, tools, step limits, stop rules, and approval settings.
- [x] Update the node palette to expose `agent` directly.
- [x] Update the current agent wizard so it creates a real `agent` node instead of a preset-only pseudo-agent flow.
- [x] Add agent trace rendering in the inspector and run detail UI.

#### F01-T07: Test coverage
- [x] Backend unit tests for schema and graph validation.
- [x] Engine unit tests for:
  - normal stop
  - step-limit stop
  - tool failure
  - approval pause/resume
  - invalid tool selection
- [x] Integration tests for:
  - save graph with `agent`
  - start run with `agent`
  - replay/resume after pause
- [x] Frontend tests for form rendering and trace display.

### Success Criteria
- [x] A graph can include a real `agent` node end-to-end.
- [x] The engine executes multi-step tool loops without manual graph wiring.
- [x] Run detail surfaces step traces, tool calls, and stop reason.
- [x] HITL pauses and resumes work inside an agent run.

### Proof / Demo Feat
Create one demo graph with a single `agent` node plus output node that:
- reads input
- chooses a tool
- pauses before a protected tool
- resumes
- returns a final answer with visible step trace

---

## P0-F02: Marketplace Runtime Contract and Delivery

### Feature Description
Fix the current mismatch where the marketplace behaves like a productized extension system in UI and DB, while the engine only knows how to load local manifests.

P0 requires one honest marketplace model. Either packages are templates, or they are executable runtime artifacts. The product cannot keep implying both at once.

### Why This Is P0
- It removes one of the biggest end-to-end inconsistencies in the stack.
- It affects buyer trust immediately.
- It directly impacts the node palette, quick add flow, and admin marketplace UI.

### User-Facing Outcome
- When a package appears installable and executable, it actually is.
- When a package is only a template, the UI says so clearly.

### Non-Goals for P0
- public third-party package ecosystem
- arbitrary remote code plugins
- self-service package publishing for untrusted packages in Cloud

### Detailed Tasks

#### F02-T01: Decide and document package classes
- [x] Write `docs/architecture/marketplace-runtime-contract.md`.
- [x] Define package classes:
  - `template_http`
  - `template_prompt`
  - `runtime_tool`
  - `runtime_transform`
- [x] Decide which classes are allowed in Cloud for P0.
- [x] Define what "install" means for each class.

#### F02-T02: Extend release metadata
- [x] Add explicit release fields for:
  - `package_kind`
  - `runtime_manifest`
  - `manifest_version`
  - `cloud_allowed`
  - `review_notes`
- [x] Reject releases whose metadata does not match their package class.
- [x] Validate template packages against `execution_node_type` and `config_defaults`.
- [x] Validate runtime packages against a strict manifest schema.

#### F02-T03: Implement backend delivery path
- [x] Add a backend manifest rendering/fetch service for runtime packages.
- [x] Keep tenant scoping explicit.
- [x] Add versioned install payloads and cache headers.
- [x] Add manifest signatures or checksums.
- [x] Add admin-visible package load status.

#### F02-T04: Implement engine loading path
- [x] Decide refresh mode:
  - startup only
  - polling
  - admin-triggered refresh
- [x] Load tenant-aware runtime manifests if runtime packages are enabled.
- [x] Preserve local filesystem manifests for self-host/dev.
- [x] Reject invalid, unsigned, or unsupported manifests visibly.

#### F02-T05: Fix frontend marketplace semantics
- [x] Show package class in admin marketplace and quick-add UI.
- [x] Label template-only packages as templates.
- [x] Label runtime-backed packages as executable.
- [x] Disable quick-add for unsupported classes.
- [x] Show why a package is blocked or unavailable.

#### F02-T06: Test coverage
- [x] Integration tests for:
  - install package
  - fetch installed manifest set
  - engine refresh
  - execute installed runtime package
- [x] Frontend tests for package labels and disabled states.
- [x] Contract tests for manifest schema validation.

### Success Criteria
- [x] Package installation means the same thing in backend, frontend, and engine.
- [x] No approved package appears executable in UI while lacking runtime support.
- [x] Runtime-backed package delivery is tenant-aware, versioned, and test-backed.

### Proof / Demo Feat
Install one official package from the marketplace, add it from the palette, and execute it successfully without editing files or restarting the whole app stack manually.

---

## P0-F03: Cloud-Safe Execution and Policy Enforcement

### Feature Description
Introduce an explicit Cloud-safe execution policy so that runtime expansion does not accidentally expose unsafe behaviors such as `exec` tools.

### Why This Is P0
- This is the main operational and security blocker for a sellable cloud product.
- It must be solved before marketplace runtime delivery can be trusted.
- It lets the product draw a clean line between Cloud and self-hosted capabilities.

### User-Facing Outcome
- Cloud customers can use approved packages and tools safely.
- Operators can explain why something was blocked.
- Self-host users still retain broader flexibility.

### Non-Goals for P0
- full sandboxing infrastructure
- syscall isolation
- container-per-tool execution
- enterprise governance UI depth

### Detailed Tasks

#### F03-T01: Introduce runtime mode
- [x] Add an explicit runtime mode flag:
  - `cloud`
  - `self_hosted`
- [x] Thread it through backend and engine configuration.
- [x] Document capability differences by mode.

#### F03-T02: Block unsafe tool kinds in Cloud
- [x] Reject `exec` manifests in engine load path when runtime mode is `cloud`.
- [x] Reject runtime package releases that require `exec` in marketplace review when mode is `cloud`.
- [x] Surface blocked-package reasons in the admin UI.
- [x] Add an emergency kill switch for runtime package loading.

#### F03-T03: Tighten egress policy consistency
- [x] Ensure the same tenant policy logic covers:
  - HTTP nodes
  - tool HTTP calls
  - provider/model allowlists
- [x] Add shared tests to prevent policy drift across executors.
- [x] Add explicit error codes/messages for policy denials.

#### F03-T04: Add auditability and operator visibility
- [x] Log policy-denied executions to audit logs.
- [x] Log rejected runtime package reviews.
- [x] Add engine/backend telemetry for rejected runtime loads.
- [x] Add operator-facing docs for what gets blocked and why.

#### F03-T05: Test coverage
- [x] Engine tests for `exec` rejection in `cloud` mode.
- [x] Backend integration tests for blocked release approval.
- [x] Integration tests for policy-denied HTTP/tool executions.

### Success Criteria
- [x] `cloud` mode cannot execute `exec` tools.
- [x] Unsafe packages fail before installation or runtime load.
- [x] Policy denials are auditable and understandable.

### Proof / Demo Feat
Attempt to install or run an unsafe package in Cloud mode and show a clean policy-denied response instead of silent failure or undefined behavior.

---

## P0-F04: Stable Graph and Event Contracts

### Feature Description
Publish the contracts that the code already references implicitly, especially `SPECS.md` and the run event contract.

### Why This Is P0
- The repo already refers to `SPECS.md`, but it is missing.
- The product cannot sell extensibility or stability without contracts.
- Agent node and marketplace work will drift immediately if the contracts are not written down.

### User-Facing Outcome
- Internal teams and future external integrators have a stable source of truth.
- Docs, code comments, and runtime behavior finally line up.

### Non-Goals for P0
- full SDKs
- public API versioning program
- generated developer portal

### Detailed Tasks

#### F04-T01: Publish Graph JSON spec
- [x] Create root `SPECS.md`.
- [x] Document:
  - node model
  - edge model
  - metadata
  - editor-only state
  - sentinel `START` and `END`
  - cycle semantics
  - `allow_cycles`
  - `agent` node once available
- [x] Link the spec from README and from the frontend graph type comments that reference it.

#### F04-T02: Publish run event contract
- [x] Create `docs/architecture/run-event-contract.md`.
- [x] Document persisted event types and payloads.
- [x] Document SSE/WS envelopes.
- [x] Document redaction guarantees and non-guarantees.
- [x] Document compatibility rules for new event fields.

#### F04-T03: Clean documentation drift
- [x] Update README feature list to reflect the actual repo state.
- [x] Add "already implemented" notes for:
  - replay
  - budgets
  - RBAC
  - OAuth
  - webhook triggers
- [x] Remove outdated claims in MVP docs that describe existing capabilities as missing.

#### F04-T04: Add contract validation
- [x] Add Graph JSON fixture tests if shared fixtures are introduced.
- [x] Add run event serialization/contract tests if a shared schema layer is introduced.

### Success Criteria
- [x] `SPECS.md` exists and is linked from the places that already reference it.
- [x] Run events have one documented contract.
- [x] Documentation no longer materially misdescribes the current repo.

### Proof / Demo Feat
A new engineer can answer "what is a valid graph?" and "what events does a run emit?" from repo docs without reverse-engineering the code.

---

## Cross-Cutting P0 Tasks

### P0-X01: Slice the Work Into Reviewable PRs
- [x] Define PR boundaries for F01-F04.
- [x] Keep architecture/spec docs first where they unblock implementation.
- [x] Avoid one mega-PR for all P0 work.

### P0-X02: Demo and QA Validation
- [x] Build one scripted demo flow around the new `agent` node.
- [x] Validate:
  - graph authoring
  - package installation
  - policy denial behavior
  - pause/resume
  - trace display
- [x] Record known limitations explicitly.

### P0-X03: Release Notes for Internal Launch
- [x] Summarize what changed in runtime semantics.
- [x] Summarize what is safe in Cloud vs self-hosted.
- [x] Summarize what package classes are supported.

---

## Suggested Build Order

### Week 1
- F01-T01 to F01-T03
- F02-T01 to F02-T02
- F03-T01 to F03-T02
- F04-T01

### Week 2
- F01-T04 to F01-T06
- F02-T03 to F02-T05
- F03-T03 to F03-T04
- F04-T02 to F04-T03

### Week 3
- F01-T07
- F02-T06
- F03-T05
- F04-T04
- P0-X01 to P0-X03

## Final Definition of Done
- [x] P0-F01 complete
- [x] P0-F02 complete
- [x] P0-F03 complete
- [x] P0-F04 complete
- [x] Demo flow runs without repo-level caveats or hidden manual steps
- [x] The product story is narrower, truer, and easier to defend

