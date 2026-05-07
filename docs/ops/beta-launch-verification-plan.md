# Beta Launch Verification Plan

This plan turns the current launch analysis into versioned evidence and CI
gates. It does not change the runtime architecture. The controlling rule is
`docs/architecture/runtime-invariants.md`: the backend is the only durable
source of truth, the engine only executes work and holds ephemeral state, and
events remain transport and observability artifacts.

The target is a measured beta. Broad production launch and any public 500-agent
claim remain blocked until the existing Gate E policy is satisfied.

## Gate Profiles

| Profile | Command | Blocks | Purpose |
| --- | --- | --- | --- |
| PR beta gate | `bash scripts/ci/run_beta_pr_gate.sh` | Fast PR checks | Governance, idempotency guardrails, runtime ownership guardrails, changed-scope backend/engine/frontend checks, live no-mock guard, and loadgen dry-run smoke. |
| Nightly beta gate | `bash scripts/ci/run_beta_nightly_gate.sh` | Main/nightly | Full required checks, live Playwright, load smoke, Docker full-stack smoke, and runtime transport chaos. |
| Beta release gate | `bash scripts/ci/run_beta_release_gate.sh` | Release candidate | Local production evidence gate, Gate A/B loadgen evidence, beta capacity evidence validation, Docker image smoke, and manual operator walkthrough signoff. |

`scripts/ci/run_required_checks.sh` remains the local mirror of required CI.
The beta scripts organize when the same checks are used for PR, nightly, and
release decisions.

## Evidence Rules

- CI load smoke is regression evidence only.
- `tools/loadgen` is the source of capacity evidence.
- Checked-in capacity reports belong under `docs/ops/capacity/`.
- Raw loadgen artifacts belong under `logs/loadgen/`.
- Launch gates use the stricter benchmark thresholds in
  `docs/perf/500-agent-benchmark.md`.
- `docs/ops/production-slos.yaml` remains the operational alerting catalog.
- `scripts/ci/check_launch_claims.py` continues to block unsupported public
  claims. A 500-agent claim requires three latest consecutive passing checked-in
  Gate E reports.

## P0: Truth And Safety

| Suite | Owner | Exit criteria | No-go condition | Gate |
| --- | --- | --- | --- | --- |
| Crash-after-apply-before-ack idempotency breadth | Backend + Frontend | Engine callbacks, runtime intents, human decision submit, projections, memory, accounting, and frontend command retry each prove replay-after-apply, exactly one durable write, correct idempotent response, and zero drift. | Any duplicate durable mutation, cost double count, memory duplicate drift, or silent task loss. | PR for fast boundaries; nightly for live/slow boundaries. |
| Runtime transport at-least-once, reclaim, and dead letter | Backend + SRE | Accepted intents reach a backend read model or visible dead letter before deadline; backlog returns to zero. | Accepted message disappears or a run remains running with no visible progress path. | Nightly. |
| HITL lifecycle duplicate/conflict/stale resume | Backend + Frontend | Duplicate submit returns already-applied semantics, conflict returns explicit rejection, stale resume attempts are ignored or rejected, and no run remains stuck in `resume_requested`. | Human decision path loses or duplicates durable state. | Nightly and release. |
| State feed replay, reconnect, and full resync | Frontend + Backend | Clients converge to backend DTO state after reconnect, replay gap, or `full_resync_required`. | UI remains stale outside the defined window or crosses tenant visibility. | Small PR smoke where possible; nightly at live scale. |
| Tenant isolation, JWT revocation, signed callback replay, throttling | Backend + Security | Cross-tenant reads fail, revoked tokens and replayed signatures fail, scoped throttles return expected 429s, and audit records exist. | Any cross-tenant leak or accepted revoked/replayed credential. | PR for critical matrix; nightly with moderate concurrency. |
| Engine fail-closed on backend write failures | Engine | No downstream executor runs and no committed-looking event is emitted before backend commit succeeds. | Engine execution or event emission implies durable state that backend did not commit. | PR. |
| Live operator walkthrough | Frontend + Backend + Product Ops | Operator can answer "why is this company stuck?" and "what did this cost, learn, and decide?" without raw logs. | Required truth exists only in raw logs or ad hoc database inspection. | Release decision. |

## P1: Measured Beta Capacity

| Gate | Command | Exit criteria | Blocks |
| --- | --- | --- | --- |
| Gate A | `go run ./tools/loadgen --gate A --base-url http://127.0.0.1:8000 --output-dir logs/loadgen --capacity-report-dir docs/ops/capacity` | 25 agents for 1h, every planned run starts and reaches backend-owned `succeeded`, terminal run failures = 0, silent drops = 0, checked-in report under `docs/ops/capacity/`, raw artifacts under `logs/loadgen/`. | Private beta expansion. |
| Gate B | `go run ./tools/loadgen --gate B --base-url http://127.0.0.1:8000 --output-dir logs/loadgen --capacity-report-dir docs/ops/capacity` | 50 agents for 2h, every planned run starts and reaches backend-owned `succeeded`, terminal run failures = 0, projection lag p95 < 2s, silent drops = 0, checked-in report under `docs/ops/capacity/`, raw artifacts under `logs/loadgen/`. | Private beta expansion. |

The release wrapper runs both gates through:

```bash
bash scripts/ci/run_beta_capacity_gates.sh
```

Use `BETA_CAPACITY_GATES="A B"` to select gates. Gate C and Gate D are the next
phase before larger cohorts.

## P2: Larger Cohorts And Public Claims

| Gate | Scope | Exit criteria | Blocks |
| --- | --- | --- | --- |
| Gate C | 100 agents with HITL, memory, accounting, and retries | Approval paths stable, cost double-counting = 0, memory duplicate drift = 0, dead-letter visibility within SLO. | Cohorts that need full company-OS workload. |
| Gate D | 250 agents with reconnect storm and 250 WS clients | UI convergence, replay/resync correctness, no cross-tenant WS leaks, projection lag p95 < 2s. | Large beta cohorts. |
| Gate E synthetic/control/real | 500 agents with duplicate storm, reconnect storm, HITL, memory, accounting, LLM throttling, and disruption hooks | Three latest consecutive passing checked-in Gate E reports. | Any public 500-agent claim or broad production scale claim. |

Gate E is not required for a measured beta, but it remains a hard blocker for
public scale copy.

## P3: Soak And Operations

| Suite | Owner | Exit criteria | No-go condition |
| --- | --- | --- | --- |
| 24h soak | SRE + Platform | No permanent backlog, no cost/memory drift, no unexplained WS staleness, alerts match real symptoms. | Slow leak, invisible queue saturation, or drift that only appears after long runtime. |
| Gameday | SRE + Product Ops + Platform | On-call follows runbooks, MTTD/MTTR recorded, recovery is visible through product/operator surfaces. | Recovery requires raw internals or undocumented manual state repair. |

## Release Decision Checklist

- [ ] `bash scripts/ci/run_required_checks.sh` is green.
- [ ] `bash scripts/ci/run_local_production_evidence.sh` is green for the
  release candidate environment.
- [ ] P0 suites are green in PR or nightly based on duration.
- [ ] Gate A and Gate B reports are passing and checked in before beta
  expansion.
- [ ] State ownership ADR has human signoff before beta release.
- [ ] Operator walkthrough is approved without raw-log dependency.
- [ ] No public 500-agent claim is made until the three-Gate-E policy passes.
