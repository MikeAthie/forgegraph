# CareerOps as Native ForgeGraph Contract

**Decision:** CareerOps should not be ported as scripts-plus-files. Each Career-Ops feature must become a native ForgeGraph contract: workflow execution, task projection, decisions, memory observations, accounting, versioned artifacts, and backend-owned system state.

**Business goal:** daily 10:00 AM discovery should leave reviewed career options ready for Mike, while preserving human approval and avoiding repeated applications to the same company/role inside the 30-day cooldown.

---

## Feature translation contract

| Career-Ops feature | Native ForgeGraph equivalent | Desired result | Implementation rule |
| --- | --- | --- | --- |
| Auto-pipeline | Workflow Definition / GraphVersion + Execution/Run + TaskRecord + DecisionRecord | A URL/JD triggers durable execution, tracking, and possible human approval. | Do not store pipeline outcome only in markdown; materialize run, tasks, decisions, opportunity, and artifacts. |
| scan | Inbox/CompanySignal + TaskRecord + projection APIs | Scanner findings become observable tasks/pending items. | Every scanned lead gets stable external key and visible task/signal state. |
| tracker | TaskRecord + DecisionRecord + CostAggregate + StateProjection/CompanyOpportunity | Application state becomes queryable system state, not local markdown tables. | `CompanyOpportunity.metadata_json.career_ops` holds application status; read models derive from durable records. |
| pdf / cover | Workflow outputs + Library/AssetVersion + ServiceDeliverable | CV/cover artifacts are versioned execution outputs. | Every candidate-facing artifact has an asset version, source refs, and quality-gate metadata. |
| batch | Engine execution fan-out + backend durable checkpoints | Parallelism with recovery and correct state ownership. | Engine executes; backend owns checkpoint/result state and idempotency. |
| patterns / followup | MemoryObservation + TaskRecord + CostAggregate | Accumulated learning and suggested actions are visible system state. | Story/follow-up learning writes memory observations and follow-up tasks. |
| interview-prep / contacto / deep | Library/AssetVersion + MemoryObservation + DecisionRecord | Research/collateral is durable, reviewable knowledge. | Research notes and prep briefs are assets/memory, with approval decisions where externally used. |
| update-system / integrity | CI guardrails + migration/release invariants | System changes are verified against ownership contracts, not just syntax. | Tests must fail if engine/client/local files become authoritative. |

---

## Current ForgeGraph primitives confirmed in repo

The current ForgeGraph backend already has these native surfaces:

- `TaskRecord` in `backend/infrastructure/orm/models/run_records.py`
- `DecisionRecord` in `backend/infrastructure/orm/models/decisions_assets.py`
- `MemoryObservation` in `backend/infrastructure/orm/models/memory.py`
- `CostAggregate` in `backend/infrastructure/orm/models/evaluations.py`
- `CompanySignal` / `CompanyOpportunity` in `backend/infrastructure/orm/models/company_ops.py`
- `StateProjection` in governance models
- `Asset` / `AssetVersion` and `ServiceEngagement` / `ServiceDeliverable`
- `Run` / `GraphVersion` execution surfaces

Therefore: use these first. Add CareerOps-specific tables only if a test proves the generic primitives cannot represent the state or invariant.

---

## P0 implementation consequences

The next CareerOps implementation slice should adjust from “service-only MVP” to “native ForgeGraph MVP”:

1. **URL intake creates an execution context**
   - A pasted URL/JD should create or attach to a backend `Run`/execution.
   - It should create `TaskRecord` entries for scan, liveness, evaluation, packet, approval, and follow-up.

2. **Scan results are inbox/task material**
   - Scanned jobs create `CompanySignal(source="career_ops_scan", external_key=...)`.
   - Each actionable finding is visible as a `TaskRecord`, not just stored in an evaluation report.

3. **Tracker is a projection, not source of truth**
   - `CompanyOpportunity` holds canonical job opportunity/application metadata.
   - `StateProjection(career_ops:pipeline_snapshot)` is derived/rebuilt from opportunities, tasks, decisions, and deliverables.

4. **Approval uses native decisions**
   - Candidate approval should create `DecisionRecord(decision_type="human_approval")` with exact packet/asset-version refs.
   - No external side effect is allowed without that exact decision.

5. **Patterns and follow-ups become memory/tasks**
   - Story bank and search learnings write `MemoryObservation` and update `interview_story_bank` asset versions.
   - Follow-up recommendations create `TaskRecord` entries with due dates/status.

6. **Costs/accounting become visible**
   - Evaluations/rendering/batch work should attach cost metadata and eventually aggregate into `CostAggregate`.
   - This matters for daily cron so morning runs do not silently burn cost.

7. **Cron is a wake-up adapter only**
   - The 10:00 AM schedule belongs to ForgeGraph automations when available.
   - Hermes cron/OS cron may call `run_due_automations`, but schedule/run/idempotency/result state remains in ForgeGraph.

---

## Daily 10:00 AM discovery contract

Default schedule:

```text
0 10 * * *
```

Handler key proposal:

```text
career_ops.daily_discovery
```

Input shape:

```json
{
  "company_id": "<career_ops_company_uuid>",
  "cooldown_days": 30,
  "max_new_options": 10,
  "max_evaluations": 5,
  "min_score_for_packet": 4.0,
  "submit_mode": "manual_only",
  "quiet_noop": false
}
```

Run behavior:

1. Load base CV/profile/proof points.
2. Discover or accept configured sources/queries.
3. Normalize scanned jobs into `CompanySignal`.
4. Skip same employer+role when an application happened within `cooldown_days`.
5. Create/update `CompanyOpportunity` tracker entries.
6. Run liveness/G-legitimacy before expensive evaluation.
7. Evaluate top jobs only up to budget limits.
8. Draft packets only for score-qualified opportunities.
9. Run pre-live quality gates.
10. Create approval `DecisionRecord` / pending task for Mike.
11. Persist morning summary as `pipeline_health_report` / `StateProjection`.
12. Never submit applications.

---

## Base CV contract

Before any daily discovery or packet generation can be live-ready:

- `AssetVersion` for `cv_source` must exist.
- `StateProjection(career_ops:candidate_profile)` must exist.
- `AssetVersion` for `proof_point_digest` should exist, even if initially sparse.
- Tailored resume/cover/application answers must cite source refs from:
  - base CV version,
  - proof points,
  - candidate profile/positioning,
  - target opportunity/job posting,
  - liveness/evaluation receipts.

If `cv_source` is missing, the automation should produce a blocked setup task, not generate applications.

---

## Apply saturation / cooldown contract

Default: do not generate a new application packet for the same employer+role if an application was marked `applied` in the last 30 days.

Cooldown match dimensions:

- normalized employer name,
- normalized role title or role family,
- canonical job URL when available,
- optional domain/company ATS identifier.

Allowed behavior inside cooldown:

- update tracker with duplicate/cooldown signal,
- create a low-priority review task if role is materially different,
- recommend “skip due to recent application.”

Blocked behavior inside cooldown:

- mark as ready to apply,
- generate live packet by default,
- send/submit externally.

---

## CI / go-no-go gates for the port

### ForgeGraph minimum local gate for CareerOps slices

```bash
cd backend
UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest \
  tests/unit/services/test_career_ops_graph_contract.py \
  tests/unit/services/test_career_ops_opportunities.py \
  -q

UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run ruff check \
  application/services/career_ops_graph_contract.py \
  application/services/career_ops_opportunities.py \
  tests/unit/services/test_career_ops_graph_contract.py \
  tests/unit/services/test_career_ops_opportunities.py

DEBUG=1 USE_SQLITE=1 USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 \
  UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run python manage.py check
```

### Full platform go/no-go before claiming replication

```bash
# ForgeGraph backend
cd backend && uv run pytest

# ForgeGraph frontend
cd ../frontend && npm test && npm run test:e2e

# ForgeGraph engine
cd ../engine && go test ./...

# Career-Ops origin parity checks when inspecting upstream directly
npm run doctor
node test-all.mjs
cd dashboard && go build -o career-dashboard .
```

If full frontend/engine/origin checks are unavailable in the current environment, report that honestly and keep the claim scoped to the verified backend slice.

---

## Additional tests to add before live use

### ForgeGraph-native ownership tests

- URL auto-pipeline creates `Run`, `TaskRecord`, `CompanySignal`, `CompanyOpportunity`, `DecisionRecord`, and `ServiceDeliverable` records.
- Engine events/callbacks cannot become authoritative durable state.
- Pipeline snapshot can be rebuilt from durable records.
- Approval decisions require exact asset/packet version refs.
- Daily discovery idempotency prevents duplicate tasks/signals for the same scheduled fire key.
- 30-day cooldown blocks same employer+role packet readiness.

### CareerOps provider/parity tests

- Versioned fixtures for Ashby, Greenhouse, Lever first; later Recruitee, SmartRecruiters, Workable, Workday.
- PDF/cover visual and text extraction regression.
- Dashboard/TUI equivalent deferred; read-model API must be deterministic first.

---

## Diagram

```text
JD / URL / scheduled discovery
  -> Inbox / CompanySignal
  -> Workflow Definition + Revision
  -> Execution / Run
  -> TaskRecord fan-out
  -> Engine work + RunEvent observability
  -> Backend materializes durable state
  -> DecisionRecord if human approval required
  -> MemoryObservation for learnings
  -> CostLedger / CostAggregate for cost visibility
  -> AssetVersion / ServiceDeliverable artifacts
  -> UI/API: Overview / Tasks / Inbox / Memory / Accounting / Workflows
```

---

## Final architecture statement

Career-Ops validates the product; ForgeGraph validates the platform. The correct port is not to copy scripts into ForgeGraph, but to express each Career-Ops feature as a native ForgeGraph workflow, task, decision, memory, accounting, artifact, and projection contract — then harden that translation with CI gates by feature family.
