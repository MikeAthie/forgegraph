# Production Evidence Gate

This gate is the stabilization path for the Phase 1-7 production-readiness
work. It is intentionally about evidence, not new product scope.

For measured beta release decisions, use
`docs/ops/beta-launch-verification-plan.md` as the orchestration layer over this
gate. This document remains the canonical local production evidence command.

## Canonical Local Command

Run the full local evidence gate from the repo root:

```bash
bash scripts/ci/run_local_production_evidence.sh
```

The command starts or verifies:

- Postgres on `localhost:5433`
- Redis on `127.0.0.1:6379`
- deterministic OpenAI-compatible mock LLM on `127.0.0.1:8011`
- backend/Daphne/WebSocket on `127.0.0.1:8000`
- runtime-intent worker
- run-queue worker
- engine gRPC and metrics on `127.0.0.1:50051` and `127.0.0.1:9090`
- frontend on `127.0.0.1:3000`

The local runner uses Docker Compose for the service stack and then runs the
same required checks in `scripts/ci/run_required_checks.sh`. It leaves Docker
services running on failure for inspection. Set
`LOCAL_GATE_DOWN_ON_EXIT=true` when a clean teardown is preferred.
When `LOCAL_GATE_RUN_TESTS=false` is used, the deterministic LLM mock is also
left running so the stack remains usable for manual checks.

Useful switches:

```bash
LOCAL_GATE_RUN_TESTS=false bash scripts/ci/run_local_production_evidence.sh
LOCAL_GATE_BUILD=false bash scripts/ci/run_local_production_evidence.sh
LOCAL_GATE_INCLUDE_DOCKER_SMOKE=false bash scripts/ci/run_local_production_evidence.sh
```

When launching from PowerShell into WSL/Git Bash, pass overrides inline to
`bash -lc` so they reach the Linux shell:

```powershell
bash -lc "LOCAL_GATE_RUN_TESTS=false LOCAL_GATE_BUILD=false bash scripts/ci/run_local_production_evidence.sh"
```

## Required Check Order

`scripts/ci/run_required_checks.sh` is the local mirror of the required CI gate:

1. Backend unit, integration, migration, security regression, SRE readiness.
2. Engine deterministic, integration, and race checks.
3. Frontend unit and mocked Playwright checks.
4. Launch QA backend, engine, and frontend checks.
5. Live Playwright no-mock guard.
6. Live launch, OS surface, HITL, failure/dead-letter, tenant isolation checks.
7. 100-run no-LLM load smoke.
8. Docker image full-stack smoke, unless explicitly disabled.

Do not push release candidates when this sequence is red locally unless the
failure has a documented environment-only cause and CI is expected to be more
representative.

## Coverage Note

Run the required engine gates before treating coverage as release evidence. In
this workspace, `go test -cover ./...` is not a stable blocking gate while stale
Go build-cache artifacts can mix toolchain versions. If coverage fails with a
toolchain cache mismatch, clear the Go build cache outside the repo and rerun
the normal engine gates first. Promote a coverage command to required evidence
only after it is reproducible on the local and CI toolchains.

## Beta Gate Profiles

The beta launch plan separates the same evidence into decision points:

| Profile | Command | Blocking scope |
| --- | --- | --- |
| PR blocking | `bash scripts/ci/run_beta_pr_gate.sh` | Fast governance, idempotency guardrails, runtime ownership guardrails, changed-scope backend/engine/frontend checks, live no-mock guard, and loadgen dry-run smoke. |
| Nightly/pre-release blocking | `bash scripts/ci/run_beta_nightly_gate.sh` | Full required checks, live Playwright, runtime transport chaos, load smoke, and Docker smoke. |
| Beta release decision | `bash scripts/ci/run_beta_release_gate.sh` | Local production evidence, Gate A/B loadgen evidence, evidence package validation, Docker image smoke, and manual operator walkthrough. |

The beta gate scripts are orchestration only. They must not weaken the runtime
contract in `docs/architecture/runtime-invariants.md`.

## Review Slices

Keep review and merge discussion split by behavior:

- Runtime/HITL: resume attempt identity, backend-owned pause/resume, fail-closed engine writes.
- Lifecycle/retry/operator: task lifecycle ledger, retry records, dead letters, recovery APIs.
- Architecture/CI: architecture enforcement tests, live Playwright gates, Docker smoke.
- Security: route matrix, signed callbacks, replay protection, authz boundaries.
- Scalability/SRE: capacity tiers, load smoke, WebSocket hardening, SLO read models.
- Frontend OS surfaces: state-first approvals, tasks, memory, accounting, operations.

No runtime slice should merge if it weakens `docs/architecture/runtime-invariants.md`.

## Failure Classification

Classify every red check before changing code:

- Implementation bug: product behavior violates the invariant or acceptance test.
- Orchestration/env bug: services, ports, env, migrations, or startup ordering are wrong.
- Flaky timing: waits, retries, or readiness are insufficient but the invariant is sound.
- Test expectation drift: the test asserts obsolete behavior after an intentional contract change.

Fix orchestration/env issues before expanding coverage. A launch gate that is
hard to start is itself a production risk.

## Capacity Evidence

Use the capacity tiers in `docs/ops/scalability-program.md`.

- Private beta proof: Phase 3 Gate A and Gate B reports produced by
  `tools/loadgen` and validated by `scripts/ci/check_beta_capacity_evidence.py`.
- Production v1 proof: Phase 3 Gate C report through backend, engine, Redis, Postgres, projections, and WebSocket.
- Production scale proof: three consecutive passing Phase 3 Gate E reports with failure injection, reconnect storm, duplicate-event storm, HITL, memory, accounting, and multi-tenant coverage.

The CI load smoke is regression evidence only. It is not a capacity claim or a
marketing claim.

## Claim Gate

- [ ] Latest capacity evidence supports public concurrency claim
- [ ] Gate E passed 3 times
- [ ] Accounting metrics are backend-instrumented
- [ ] Command Ops is live/versioned

## Required Runbooks

Broad production requires on-call runbooks for the failure queues and recovery
paths operators depend on:

- Spool growth: [event_spool_growth.md](runbooks/event_spool_growth.md)
- Dead letters: [dead_letter_spike.md](runbooks/dead_letter_spike.md)
- Projection lag: [projection_lag.md](runbooks/projection_lag.md)
- WebSocket replay/fanout failures: [websocket_replay_failure.md](runbooks/websocket_replay_failure.md) and [websocket_fanout_degradation.md](runbooks/websocket_fanout_degradation.md)
- Redis degradation: [redis_degradation.md](runbooks/redis_degradation.md)
- LLM throttling: [llm_queue_saturation.md](runbooks/llm_queue_saturation.md)

## Operator Walkthrough

After the technical gate is green, validate the product with an operator
walkthrough:

- Command Center: current system state, active departments, recent executions.
- Approvals: pending decisions, risk/cost context, backend-confirmed resolution.
- Tasks: running, paused, retry scheduled, failed, and dead-lettered work.
- Run detail: timeline, checkpoint, last callback, recovery state.
- Memory: what was learned, source, search, retention/export/delete posture.
- Accounting: cost by org/department/agent/run/task/provider/model.
- Audit and operations: stuck-run inspection, dead-letter recovery, SLO/alert state.

Acceptance standard: an operator can answer "why is this company stuck?" and
"what did this cost, learn, and decide?" without reading raw logs.
