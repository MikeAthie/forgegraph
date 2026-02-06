# P0: Core Runtime + Agent Execution (Weeks 1-2)

## Objective
Close the highest-risk runtime gaps: conditional routing, loops, durable state, streaming output, and complete prompt/tool/memory node behavior.

## Prerequisites
- MVP and V1 run pipeline is operational.
- Existing branch/merge and checkpoint code paths are baseline-tested.

---

## Task List

### P0-T01: Conditional Edges + Loop Semantics
Effort: Medium

Why critical:
Branching and loops are foundational for non-trivial agents.

Implementation steps:
1. Define loop-safe execution semantics (iteration cap, break conditions, loop state keys).
2. Extend validator rules to allow intentional cycles only through approved loop constructs.
3. Update scheduler dependency handling for loop iterations and merge synchronization.
4. Add loop diagnostics in run events (iteration index, exit reason).

Recommended patterns / best practices:
- Explicit max-iteration guardrails per graph/node.
- Deterministic merge behavior under repeated branch execution.

Testing strategy:
- Unit: conditional routing truth table + loop termination logic.
- Integration: branch -> loop -> merge workflow with expected outputs.

Success criteria / Definition of Done:
- [ ] User can build a Branch/Merge workflow that executes correctly.
- [ ] Looping graph paths complete without deadlock or infinite execution.
- [ ] Validation blocks unsafe cycles and allows approved loop patterns.

Dependencies:
- Existing branch/merge executors and graph validator.

Risks:
- Race conditions on looped dependency counts under concurrency.

---

### P0-T02: Durable State + Checkpoint Resume
Effort: Medium

Why critical:
Long-running workflows must survive restarts and human pause points.

Implementation steps:
1. Standardize checkpoint payload shape (state, completed/skipped nodes, memory metadata).
2. Ensure checkpoints persist at configured cadence and on pause boundaries.
3. Harden replay/resume to restore all execution-critical context.
4. Add replay UX hooks for selecting checkpoint scope.

Recommended patterns / best practices:
- Idempotent checkpoint writes keyed by run and step.
- Keep checkpoint schema versioned for migrations.

Testing strategy:
- Integration: kill/restart run process and resume from latest checkpoint.
- E2E: pause at human gate, resume, and verify downstream continuity.

Success criteria / Definition of Done:
- [ ] Graphs can be paused and resumed mid-execution.
- [ ] Replay from checkpoint produces deterministic downstream behavior.
- [ ] Checkpoint restore includes state + execution progress.

Dependencies:
- Run repository checkpoint storage.

Risks:
- Partial checkpoint writes if process crashes during persistence.

---

### P0-T03: Streaming Output (Token/Chunk Incremental)
Effort: Medium

Why critical:
Streaming is required for responsive agent UX.

Implementation steps:
1. Add streaming event contract (`node_stream.chunk`) through engine -> backend -> WS/SSE.
2. Add provider adapters for incremental chunk emission.
3. Update run detail UI to render partial prompt output before final node completion.
4. Add reconnect-safe replay support for chunk events.

Recommended patterns / best practices:
- Preserve final node output as source of truth.
- Treat chunk stream as append-only, best-effort UI layer.

Testing strategy:
- Unit: stream parser and chunk ordering.
- Integration: streamed prompt run emits ordered chunks and final response.

Success criteria / Definition of Done:
- [ ] UI displays partial LLM responses incrementally.
- [ ] Stream reconnect does not corrupt final displayed response.
- [ ] Final node output remains consistent with streamed content.

Dependencies:
- Event ingest and broadcast pipeline.

Risks:
- Duplicate chunk delivery on reconnect.

---

### P0-T04: Prompt Node Completion (Model, Templates, Params)
Effort: Small

Why critical:
Prompt node is the primary agent building block.

Implementation steps:
1. Finalize prompt config schema for provider, model, temperature, max tokens, and template variables.
2. Add prompt template validation and runtime substitution safeguards.
3. Add default parameter profiles and provider-aware model lists.
4. Surface prompt usage and finish reason in node output.

Recommended patterns / best practices:
- Server-side schema validation with clear per-field errors.
- Provider/model allowlist controlled by tenant policy.

Testing strategy:
- Unit: prompt config validation cases.
- Integration: run prompt node with configurable parameters across providers.

Success criteria / Definition of Done:
- [ ] User can configure model, temperature, max tokens, and template.
- [ ] Prompt node returns valid output for at least one configured provider.
- [ ] Invalid config is caught before run start.

Dependencies:
- Credential resolution and provider adapters.

Risks:
- Model naming drift across providers.

---

### P0-T05: Tool Node Runtime for External APIs + User Functions
Effort: Medium

Why critical:
Agent usefulness depends on tool access.

Implementation steps:
1. Finalize tool registry contract (name/version/input schema/output schema).
2. Add HTTP/API tool execution path with timeout/retry controls.
3. Add user-defined function tool support (controlled sandbox or allowlisted runtime).
4. Improve tool error propagation and retry classification.

Recommended patterns / best practices:
- Strong schema validation pre-execution.
- Explicit per-tool timeout and retry policy.

Testing strategy:
- Unit: tool schema enforcement.
- Integration: calculator or web-search-like tool call through tool node.

Success criteria / Definition of Done:
- [ ] Agent can call an external API via Tool node.
- [ ] Tool node supports user-defined function execution path.
- [ ] Tool failures are visible and recoverable via policy.

Dependencies:
- Credential and HTTP execution infrastructure.

Risks:
- Unbounded tool latency affecting worker throughput.

---

### P0-T06: Memory Node GET/SET with Persistent Backend
Effort: Medium

Why critical:
Cross-run context is required for assistant-like behavior.

Implementation steps:
1. Finalize memory node operations (`get`, `set`, `delete`) and namespace strategy.
2. Persist memory entries to backend store with tenant/session isolation.
3. Add TTL, size limits, and cleanup jobs.
4. Expose memory operation telemetry in run details.

Recommended patterns / best practices:
- Tenant-scoped namespaces to enforce isolation.
- Idempotent writes for repeated retries.

Testing strategy:
- Unit: memory operation contract and key resolution.
- Integration: SET in run A and GET in run B with same memory scope.

Success criteria / Definition of Done:
- [ ] Memory SET followed by GET returns stored value.
- [ ] Memory persists across separate runs in intended scope.
- [ ] DELETE removes entries predictably.

Dependencies:
- Memory storage adapters and retention jobs.

Risks:
- Namespace collisions across templates without strict scoping.
