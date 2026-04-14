# Runtime Invariants

This file is the single canonical runtime contract for ForgeGraph.

If any other document, prompt, plan, or historical note conflicts with this file, this file wins.

## 1. Source Of Truth

- The backend control plane is the only source of truth for durable system state.
- No other component may persist or authoritatively mutate durable runtime state.

## 2. Engine Contract

The engine exists to execute work.

- It executes tasks and workflow revisions.
- It may hold ephemeral in-memory execution state.
- It must not persist durable runtime state.
- It must not assume authority over system state outside active execution.

## 3. Durable State Mutation Rule

- All durable state mutations must go through backend-controlled APIs or backend-owned persistence paths.
- Events may trigger backend work, but they do not apply durable state by themselves.
- The engine must not write durable run state, durable memory, or durable checkpoints directly.

## 4. Event Semantics

- Events are transport signals.
- Events are observability artifacts.
- Events are not authoritative state.
- Backend-materialized state is authoritative.
- Every runtime event is categorized as either `state` or `observability`.
- Only `state` events may trigger backend-controlled runtime state writes.
- `observability` events may be stored and broadcast for inspection, but they must not mutate authoritative runtime state.

## 5. Run Liveness

- The backend is responsible for detecting stalled or abandoned runs.
- No run may remain in `running` indefinitely without backend-observed progress.
- No run may remain in `resume_requested` indefinitely without backend-observed progress or explicit backend recovery.

## 6. Failure Model

- Engine failure must not corrupt authoritative state.
- Loss of engine memory must be survivable.
- The backend must detect inactivity and either mark the run failed or drive explicit recovery behavior.
- Recovery decisions are backend-owned policy decisions, not engine decisions.
- `retry` means a clean backend restart from canonical run input after clearing stale checkpoint state.
- `resume` means backend re-dispatch from the latest backend-owned checkpoint for the same run.
- Human approval handoff is two-stage: `paused` means awaiting human input; `resume_requested` means the backend accepted the decision and is waiting for engine acknowledgment.
- A `run_resumed` acknowledgement is valid only for the active backend `resume_attempt_id`; stale acknowledgements must be ignored or rejected.
- Recovery actions should record a backend-owned `recovery_reason` such as `engine_stalled`, `resume_timeout`, or `missing_checkpoint`.

## 7. Snapshot And Resume

- Snapshots and resume checkpoints are owned by the backend.
- Resume must start from backend-provided snapshot state.
- Engine-local process state must never be required for recovery.
- If no backend-owned checkpoint exists, checkpoint-based resume must fail closed.

## 8. Testing Contract

Tests must reinforce this architecture.

- Engine tests verify execution behavior, not durable state ownership.
- Backend tests verify state correctness, liveness, idempotency, and recovery decisions.
- Integration tests verify the full control-plane to execution-plane flow.
- Legacy tests or fixtures that depend on engine-owned durable state are invalid and should be removed or isolated as historical artifacts.

## 9. Enforcement Points

- Agent guidance: [AGENTS.md](../../AGENTS.md) and [CLAUDE.md](../../CLAUDE.md) must defer to this file for runtime decisions.
- CI guardrails: `scripts/ci/check_engine_ownership.sh` and `scripts/check-engine-ownership.ps1` enforce ownership boundaries.
- Runtime guardrails: `engine/main.go` must reject unsupported ownership modes and fail closed outside the control-plane contract.

## 10. Practical Decision Rule

Before changing runtime code or docs, answer this question:

Does this make any component other than the backend authoritative for durable state?

If the answer is yes, it violates the runtime invariants.
