# Post-Stateless Engine Reliability Hardening v2

> Runtime precedence: [runtime-invariants.md](runtime-invariants.md) is canonical.
> This document is an implementation plan and rollout record, not the source of truth for runtime semantics.

This document captures the implementation plan and rollout contract for the post-stateless-engine hardening tranche. It exists to keep the execution context in-repo while the work is being implemented and verified.

## Objective

Move the runtime from "stateless in principle" to "reliable under failure" by hardening:

- run liveness and stale-run reconciliation
- state ownership enforcement at runtime boundaries
- event semantics and event-volume control
- multi-engine assignment foundations
- live end-to-end approval coverage

## Scope

This tranche includes:

- `Run.recovery_policy` with a durable policy hook
- stale-run reconciliation through `resolve_stale_run()` -> `apply_recovery_policy()`
- checkpoint diagnostics in stale-run failure artifacts
- queue-backed stale `retry` and checkpoint-backed stale `resume`
- explicit engine mode enforcement in the engine runtime
- normalized event categories
- summary-first event streaming with bounded observability fanout
- explicit engine assignment and callback validation
- one live Playwright HITL test as the reliability gate

This tranche does not include:

- cross-engine failover or reassignment
- product-direction refactors

## Core Invariants

- The backend control plane is the only durable source of truth.
- Events never mutate durable state directly.
- Events may trigger backend writes, but the backend validates, deduplicates, and applies the write.
- A run must never remain `running` forever after backend-observed progress stops.
- Engine ownership must be explicit and verifiable at runtime.

## Implementation Plan

### 1. Run Liveness

- Keep `Run.last_progress_at` as the authoritative stale-run clock.
- Keep `last_heartbeat_at`, `recovery_state`, and `engine_instance_id` as supporting runtime visibility fields.
- Model resume handoff explicitly with `Run.status=resume_requested`, `resume_requested_at`, and `resume_attempt_id`.
- Record backend-owned recovery cause in `Run.recovery_reason`.
- Accept `run_resumed` only when the callback matches the active `resume_attempt_id`.
- Add `Run.recovery_policy` with allowed values `fail`, `retry`, `resume` and default `fail`.
- Route stale-run reconciliation through `resolve_stale_run()` and `apply_recovery_policy()`.
- Touch liveness on every backend-observed progress path:
  - dispatch/start
  - invoke/replay/resume
  - engine callback ingestion
  - checkpoint upserts
  - pause-state writes
  - engine-facing run/node update APIs

### 2. Checkpoint-Aware Reconciliation

- Use the existing `Run.checkpoint` relation as the latest checkpoint source.
- On stale reconciliation, load the latest checkpoint before applying recovery policy.
- Persist checkpoint diagnostics into the generated `run.updated` event payload:
  - `checkpoint_available`
  - `checkpoint_node_id`
  - `checkpoint_step_index`
  - `checkpoint_updated_at`
- Include a compact checkpoint summary in the stale failure message for debugging.

### 3. Ownership Enforcement

- Production-like engine startup must fail unless `ENGINE_RUN_STATE_MODE=control-plane-http`.
- `in-memory` mode remains test/local only behind `ENGINE_ALLOW_IN_MEMORY_MODE=true`.
- Legacy runtime aliases and silent fallback behavior are not allowed.
- CI must fail if forbidden persistence paths or silent fallback behavior reappear.

### 4. Event Semantics

- Add optional `category` to engine callbacks, normalized backend events, and WS payloads.
- Canonical categories are:
  - `state`
  - `observability`
- Category is normalized server-side by event type.
- Incorrect caller-supplied category values are corrected server-side.

### 5. Backpressure and Event Volume Control

- Use `minimal`, `default`, `verbose` event verbosity levels.
- Production default is `default`.
- `minimal` carries lifecycle and terminal state only.
- `default` carries lifecycle plus aggregated stream summaries.
- `verbose` carries raw stream chunks and detailed observability traffic.
- Keep summary fanout bounded with:
  - max pending chunk count before forced flush
  - max active streams tracked per run
  - bounded summary preview sizes

### 6. Multi-Engine Foundations

- Replace single-endpoint assumptions with `{engine_id, client}` selection.
- Persist `run.engine_instance_id` at dispatch time.
- On callback ingestion:
  - if `run.engine_instance_id` is empty, allow first assignment
  - otherwise require exact match
- Require callback engine identity once multi-engine mode is enabled.

### 7. Live Approval Reliability Coverage

- Add one live Playwright path covering:
  - start run
  - real engine execution
  - pause at human gate
  - resume via inbox UI
  - terminal success without page refresh
- This test must use:
  - real backend
  - real engine
  - real WS
  - existing local LLM mock
  - no mocked run/execution API routes

## Task List

- [x] Add `Run.recovery_policy` and migration.
- [x] Refactor stale reconciliation through recovery-policy hooks.
- [x] Attach checkpoint diagnostics to stale-run failure artifacts.
- [x] Implement queue-backed stale `retry` and checkpoint-backed stale `resume`.
- [x] Touch liveness on backend-observed progress paths.
- [x] Enforce engine mode guardrails in runtime startup.
- [x] Add CI ownership guardrails.
- [x] Add normalized event categories.
- [x] Add summary-first event verbosity and bounded stream fanout.
- [x] Add backend engine selection and explicit assignment validation.
- [x] Fix frontend realtime auth to use WebSocket tickets instead of raw access tokens.
- [x] Fix human-gate authoring to persist `prompt_message` for real engine execution.
- [x] Add targeted unit/integration coverage for liveness, event categories, streaming levels, and engine assignment.
- [ ] Finish the live Playwright HITL reliability test.
- [ ] Resolve the remaining backend/engine callback `409 Conflict` issue observed during live approval resume.

## Success Criteria

- No run remains `running` indefinitely after backend-observed progress stops.
- Stale-run handling always flows through a reusable recovery-policy hook.
- Stale-run failures always record whether a checkpoint existed and which checkpoint was latest.
- Human approval resume handoff cannot remain stuck in `paused`; stalled resume requests become explicit backend recovery decisions.
- Production-like engine startup cannot silently bypass the control-plane ownership contract.
- Events are explicitly categorized and never treated as direct durable state mutation.
- Default live streaming is summary-first and bounded.
- Engine assignment is explicit, first-assignment-safe, and mismatch-protected.
- CI contains at least one live backend-engine-WS-HITL approval path.

## Test Adaptation

### Unit

- verify `recovery_policy` defaults to `fail`
- verify stale reconciliation dispatches through the policy hook
- verify checkpoint context is recorded when present and marked unavailable when absent
- verify paused runs are excluded from stale reconciliation
- verify category normalization and incorrect caller category correction
- verify `minimal` and `default` levels suppress raw chunk fanout

### Integration

- verify engine callbacks refresh liveness and persist normalized categories
- verify first callback assignment is allowed when `engine_instance_id` is empty
- verify callback mismatch is rejected once an engine is assigned
- verify stale-run reconciliation persists checkpoint diagnostics
- verify engine API serialization includes `recovery_policy`

### End-to-End

- keep mocked UI tests for narrow rendering coverage only
- require one live Playwright approval path to validate:
  - backend
  - engine
  - WS
  - human gate pause/resume

## Current Status

Verified:

- engine Go test suite passes
- targeted backend unit and integration coverage for the hardening tranche passes
- frontend unit coverage for realtime auth and human-gate form changes passes

Open blocker:

- the live Playwright HITL test still fails because the run remains `paused` after approval and backend logs show repeated `409 Conflict` responses on `/api/runs/engine-events`
- this is a real backend/engine callback issue and must be fixed before the tranche is considered complete

## Related Documents

- [state-ownership-contract.md](state-ownership-contract.md)
- [run-event-contract.md](run-event-contract.md)
- [system-invariants.md](system-invariants.md)
