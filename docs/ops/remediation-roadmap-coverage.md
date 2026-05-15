# Remediation Roadmap Coverage

This is the implementation crosswalk for the ForgeGraph remediation roadmap.
`docs/architecture/runtime-invariants.md` remains the canonical contract.

Status meanings:

- **Covered**: implemented in code/docs with focused tests or CI guardrails.
- **Guarded**: drift is blocked, but a migration or external proof is still pending.
- **Partial**: meaningful implementation exists, but one or more original exit criteria are not fully met.
- **Evidence pending**: requires signoff or long-running evidence outside a normal unit/integration test run.

## Phase 0

| Item | Status | Evidence | Remaining work |
| --- | --- | --- | --- |
| P0.1 architecture boundaries | Guarded | `docs/architecture/state-ownership.md`, `event-contracts.md`, `frontend-state-contract.md`, `scripts/ci/check_engine_ownership.sh`, `scripts/check-engine-ownership.ps1` | Lead signoff is explicitly pending in the ADR. |
| P0.2 remove synthetic frontend metrics | Covered | `frontend/pages/overview/index.tsx`, `frontend/pages/accounting.tsx`, `frontend/domain/repositories/*Repository.ts`, `frontend/__tests__/unit/pages/financial-provenance.test.ts` | Real revenue/profit remain `Not yet instrumented` until backend accounting instrumentation exists. |
| P0.3 structured callback semantics | Covered | `backend/adapters/api/runs/views.py`, `engine/adapter/gateway/http_event_emitter.go`, `engine/adapter/metrics/event_metrics.go`, `engine/adapter/gateway/http_event_emitter_test.go`, `docs/ops/event-spool-growth-runbook.md` | None for Phase 0. |

## Phase 1

| Item | Status | Evidence | Remaining work |
| --- | --- | --- | --- |
| P1.1 backend-owned memory | Covered | `backend/application/services/memory_intents.py`, memory intent handling in `backend/adapters/api/runs/views.py`, engine `memory_write_requested`/`memory_fact_extracted`/`summary_created` events, `backend/tests/unit/services/test_memory_intents.py`, ownership CI with no exception manifest | None for product memory ownership; Redis runtime transport remains allowed only for backend-owned queues. |
| P1.2 projections out of request path | Covered | `backend/infrastructure/orm/management/commands/process_os_projections.py`, projection metadata in `backend/application/services/os_projections.py`, request-path guard test `backend/tests/unit/api/test_projection_request_path_guardrails.py`, `docs/architecture/read-models-and-projections.md` | Long-run read latency proof is part of Phase 3 gates. |
| P1.3 canonical event envelope | Covered | Canonical v2 emission in `engine/adapter/gateway/http_event_emitter.go`, backend parser/validator `backend/application/services/canonical_events.py`, tests `engine/adapter/gateway/http_event_emitter_test.go` and `backend/tests/unit/services/test_canonical_events.py`, source guard `scripts/ci/check_engine_event_envelope.sh` | Legacy CloudEvent parsing remains only behind the off-by-default compatibility flag. |
| P1.4 HITL first-class | Covered | `DecisionRecord` model, decision API, resume attempt identity in `backend/adapters/api/runs/resume_view.py`, engine resume intent checks in `engine/application/usecase/runtime_intents_test.go`, backend resume/idempotency tests in `backend/tests/integration/adapters/runs/test_cancel_resume.py` | Expiry/escalation policy can be expanded, but durable decision state and duplicate-safe resume are implemented. |

## Phase 2

| Item | Status | Evidence | Remaining work |
| --- | --- | --- | --- |
| P2.1 replayable WebSocket state feed | Covered | `StateFeedEvent` model/migration, `backend/application/services/state_feed.py`, `backend/adapters/ws/runs/consumers.py`, `frontend/hooks/useRunLiveUpdates.ts`, tests `test_state_feed.py`, `test_run_ws.py`, `useRunLiveUpdates.test.tsx` | Long-run reconnect storm evidence is Phase 3 Gate D/E. |
| P2.2 end-to-end idempotency matrix | Guarded | Event idempotency, runtime intent idempotency, task lifecycle/retry idempotency, memory intent idempotency, processed HTTP commands, LLM usage external keys, frontend `Idempotency-Key` propagation, and focused processed-command tests | More crash-after-apply-before-ack tests should be added for every live boundary before broad production, but the remaining gap is test breadth rather than missing primitives. |
| P2.3 dead-letter/reconciliation console | Covered | `EventDeadLetterRecord`, `backend/application/services/event_dead_letters.py`, operator APIs/views, `frontend/pages/admin/operations.tsx`, tests in `backend/tests/integration/adapters/test_operator_api.py`, alert/SLO docs | Actual replay processing of `replay_requested` event dead letters remains an operator workflow; requests are audited. |
| P2.4 formal run state machine | Covered | `backend/application/services/run_state_machine.py`, state-machine tests, status mutation guard `scripts/ci/check_run_state_machine.py`, wiring in run APIs, engine callback ingestion, runtime intents, liveness recovery, operators, integrations, and queue workers | Backend recovery requeue uses an explicit state-machine exception to preserve existing persisted status vocabulary. |

## Phase 3

| Item | Status | Evidence | Remaining work |
| --- | --- | --- | --- |
| P3.1 define 500-agent target | Covered | `docs/ops/scalability-program.md`, `scripts/stress_runner.py` Gate E definition | Approval/signoff remains external. |
| P3.2 bottleneck removal before scaling | Guarded | Projection request-path guardrails, WS replay, bounded queue/LLM stress controls, stress harness metrics, runbooks | Actual clean 50/100/250/500-agent results are evidence pending. |
| P3.3 capacity ramp gates | Evidence pending | Gate A-E implementation in `tools/loadgen`, beta orchestration in `docs/ops/beta-launch-verification-plan.md`, `scripts/ci/run_beta_capacity_gates.sh`, `scripts/ci/check_beta_capacity_evidence.py`, legacy/regression scenarios in `scripts/stress_runner.py`, claim guard in `scripts/ci/check_capacity_claims.py` | Must run and check in Gate A/B evidence before beta expansion; must run and check in three passing Gate E reports before any 500-agent claim. |

## Cross-Cutting Tests

| Area | Status | Evidence | Remaining work |
| --- | --- | --- | --- |
| T1 engine tests | Covered | deterministic scheduler tests, callback semantics tests, canonical envelope tests, engine ownership CI, race check script | Continue running targeted race checks in release gates. |
| T2 backend tests | Guarded | projection guardrails, memory intents, state feed, event dead letters, runtime intent/task idempotency, processed command tests, state-machine tests, security matrix tests | Some crash-after-apply-before-ack cases remain incomplete. |
| T3 frontend tests | Covered | financial provenance unit test, WS replay hook test, OS/admin operation surfaces | Live Playwright coverage still depends on the production evidence gate environment. |

## Security Closure

| Area | Status | Evidence | Remaining work |
| --- | --- | --- | --- |
| JWT revocation and WS tickets | Covered | `backend/tests/integration/adapters/test_security_matrix.py`, WS ticket services and consumers | Continue running live security matrix in release gate. |
| Tenant isolation | Guarded | memory/state feed/dead-letter/operator tests and live tenant-isolation gate scripts | Phase 3 multi-tenant evidence still pending. |
| Rate limiting and RBAC | Covered | rate-limit services, operator RBAC checks, route security matrix tests | Load validation is Phase 3 evidence. |
| Audit and secrets | Guarded | audit logs for operator replay/decision paths, callback signature tests, secret scanning expectations | Production secret scanning must remain enabled in CI/release tooling. |

## Product Alignment

| Item | Status | Evidence | Remaining work |
| --- | --- | --- | --- |
| No 500-agent overclaim | Covered | `scripts/ci/check_capacity_claims.py`, `docs/ops/scalability-program.md`, `docs/architecture/system-invariants.md` | Gate E evidence required before changing copy. |
| Backend-provenance product surfaces | Covered | Command Ops/accounting/overview provenance metadata and frontend tests | Real revenue/profit instrumentation remains future backend work. |

## Remaining No-Go Blockers

These are the items that still block measured beta release or expansion:

1. Complete crash-after-apply-before-ack idempotency tests for every mutation boundary.
2. Run and check in Gate A and Gate B loadgen evidence before beta expansion.
3. Complete human signoff for the state ownership ADR.
4. Complete the operator walkthrough without raw-log dependency.

These are the additional items that still block a broad production or
500-agent claim:

1. Run and check in Phase 3 Gate C/D evidence before larger cohorts.
2. Run and check in three successful latest consecutive Gate E reports before
   any public 500-agent claim.
