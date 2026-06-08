# Atlas Profit Agency PR Roadmap

> **For Hermes:** Planning-only artifact. Do not implement from this file until Mike approves a specific PR slice. When executing, load `subagent-driven-development`, `test-driven-development`, and `github-pr-workflow`; preserve unrelated dirty work; use focused branches and focused PRs.

**Goal:** Turn the Digital Marketing Pro-inspired agency ideas into a clear ForgeGraph/Atlas work path with PR boundaries, objectives, and success criteria.

**Architecture:** Build shared agency/business primitives in ForgeGraph where they are reusable across verticals; put marketing-agency defaults, playbooks, department ownership, scoring weights, and product language in the Atlas layer. The backend remains the durable source of truth; frontend and engine surfaces consume backend-owned APIs/state.

**Tech Stack:** Django/DRF backend, ForgeGraph ORM/service layer, Next.js frontend repositories/components, pytest, ruff, frontend test/lint scripts, GitHub PR workflow.

---

## Guiding boundaries

### ForgeGraph-level changes

Use ForgeGraph-level primitives for reusable service-business capabilities:

- account/client health aggregation
- onboarding checklist persistence or virtual assembly
- connector readiness normalization
- agency playbook templates
- proposal/SOW/commercial opportunity metadata
- deliverable QA gate result schema
- approval/delivery lifecycle actions
- launch readiness/checkpoint state
- recurring reporting cadence
- scope/SLA/margin/churn/expansion tracking
- privacy-safe cross-client portfolio intelligence

### Atlas-specific changes

Use Atlas-specific services/catalogs/templates for marketing-agency behavior:

- Atlas department slugs/ownership
- digital-marketing health-score weights
- Atlas client profile schema defaults
- onboarding checklist default items
- marketing connector classification
- DMP-inspired playbook seed prompts
- deliverable QA rules for the 10 Atlas MVP deliverables
- client-facing Atlas UI wording
- client deliverable presentation

### PR sizing principles

- One PR should have one production-visible objective.
- Backend contract PRs should land before frontend PRs that depend on them.
- Schema/migration PRs should be isolated unless the behavior is impossible to test without them.
- Launch/spend/send execution must be separated from dry-run/readiness work.
- Commercial/profit metrics must never be fabricated; unknown values must be explicit.
- Client-facing payloads must filter internal notes, credentials, tokens, secrets, and raw connector config.

---

## Recommended execution order

| Order | PR / Feat | Scope | Layer | Why this order |
|---:|---|---|---|---|
| 0 | Merge current deliverable endpoint PR | Finish current open foundation | Backend | Avoid building on an unmerged branch/contract. |
| 1 | Account health + onboarding foundation | Read-only snapshot, virtual onboarding, connector readiness | Backend | Gives Atlas an agency operating cockpit vocabulary without risky mutations. |
| 2 | Agency cockpit frontend | Display health/onboarding/next actions | Frontend | Consumes stable PR 1 payload. |
| 3 | Playbook template catalog | Typed templates + Atlas DMP-inspired seeds | Backend | Provides reusable prompt/playbook layer before commercial and QA workflows. |
| 4 | Discovery-to-proposal commercial funnel | opportunity intake, proposal/SOW/ROI packet | Backend + light frontend/API | Moves Atlas toward revenue acquisition. |
| 5 | Deliverable QA gate | validate assembled deliverables before client delivery | Backend | Hardens current deliverables before lifecycle automation. |
| 6 | Deliverable lifecycle + client portal surface | ready/review/deliver/accept actions and UI | Backend + frontend | Converts deliverables into client-facing work product flow. |
| 7 | Launch readiness dry-run | backend-owned readiness review and blockers | Backend | Prepares safe launch logic without live spend/send. |
| 8 | Launch attempt/checkpoint model | durable execution attempt + idempotency scaffolding | Backend | Required before any real side effects. |
| 9 | Recurring reporting cadence | weekly/monthly/QBR schedules and report deliverables | Backend + frontend | Supports retention and client value proof. |
| 10 | Profitability, scope, SLA tracking | package economics, revision limits, scope alerts | Backend | Turns operations into a managed-profit agency model. |
| 11 | Churn/expansion signal generation | retention risks and upsell recommendations | Backend + cockpit UI | Builds on health, reports, scope, and commercial data. |
| 12 | Portfolio intelligence / benchmarks | privacy-safe cross-client insights | Backend + frontend | Last, because it needs enough normalized tenant-safe history. |

---

## PR 0 — Merge current deliverable endpoint foundation

**Branch / PR:** Current PR #56, `feat/atlas-deliverable-assemble-endpoint`

**Objective:** Finish the already-built backend foundation for Atlas deliverable assembly endpoint and department slug cleanup.

**Scope:**

- `POST /api/whiteboards/{whiteboard_id}/atlas-deliverables/assemble`
- actual Atlas department slug alignment
- tests for endpoint/catalog/assembly

**Out of scope:**

- account health
- onboarding
- playbook templates
- frontend deliverables UI
- QA gate/lifecycle actions

**Success criteria:**

- PR #56 merged.
- Backend tests remain green.
- Ruff remains green.
- Local `main` is fast-forwarded after merge.

**Verification:**

```bash
gh pr view 56 --json state,mergeStateStatus,files
cd backend && uv run pytest tests/unit/services/test_agency_deliverable_catalog.py tests/unit/services/test_agency_deliverables.py tests/unit/api/test_service_engagements_api.py -q
cd backend && uv run ruff check application/services adapters/api tests/unit
```

---

## PR 1 — Backend account health + onboarding foundation

**Suggested branch:** `feat/atlas-account-health-onboarding-foundation`

**Objective:** Add a read-only ForgeGraph-native account health snapshot for Atlas companies, including virtual onboarding checklist and connector readiness normalization.

**Primary product outcome:** Atlas can answer: “Is this client account healthy, what is blocked, and what should the agency do next?”

**Layer split:**

- ForgeGraph-level:
  - account health aggregation service
  - connector readiness normalizer
  - read-only API endpoint
- Atlas-specific:
  - client profile schema defaults
  - onboarding checklist definitions
  - marketing connector categories
  - health dimension weights and department ownership

**Likely files:**

- Create: `backend/application/services/agency_account_catalog.py`
- Create: `backend/application/services/agency_connector_readiness.py`
- Create: `backend/application/services/agency_onboarding.py`
- Create: `backend/application/services/agency_account_health.py`
- Modify: `backend/adapters/api/company_ops/views.py`
- Modify: `backend/adapters/api/company_ops/urls.py`
- Maybe create: `backend/adapters/api/company_ops/serializers.py`
- Tests:
  - `backend/tests/unit/services/test_agency_account_catalog.py`
  - `backend/tests/unit/services/test_agency_connector_readiness.py`
  - `backend/tests/unit/services/test_agency_onboarding.py`
  - `backend/tests/unit/services/test_agency_account_health.py`
  - `backend/tests/unit/api/test_agency_account_health_api.py`

**Endpoint candidate:**

```text
GET /api/companies/{company_id}/ops/agency-health
```

If current routing conventions make that awkward, use:

```text
GET /api/company-ops/agency-health?company_id={company_id}
```

**Out of scope:**

- frontend panel
- durable onboarding DB model
- playbook execution
- commercial proposal generation
- deliverable QA mutations
- launch readiness

**Success criteria:**

- API returns account health, onboarding, connector readiness, next actions, risks/opportunities.
- No credentials, tokens, credential IDs, secrets, or raw connector configs appear in payload.
- Missing connectors degrade health and create next actions but do not crash.
- Commercial values that are unavailable are marked `unknown`, not guessed.
- All Atlas department slugs in catalog are valid actual Atlas slugs.
- Tests cover no-data, missing connector, stale approval, recent report, and secret redaction.

**Verification:**

```bash
cd backend && uv run pytest \
  tests/unit/services/test_agency_account_catalog.py \
  tests/unit/services/test_agency_connector_readiness.py \
  tests/unit/services/test_agency_onboarding.py \
  tests/unit/services/test_agency_account_health.py \
  tests/unit/api/test_agency_account_health_api.py -q

cd backend && uv run ruff check application/services adapters/api tests/unit
```

**Manual verification:**

- Call endpoint for local `Atlas Mkt` company.
- Confirm payload includes health dimensions and onboarding items.
- Confirm connector gaps are represented as gaps.
- Confirm no secret-like fields are present.

---

## PR 2 — Frontend agency cockpit panel

**Suggested branch:** `feat/atlas-agency-cockpit-panel`

**Objective:** Surface the PR 1 account health/onboarding payload in the Atlas/company workspace.

**Primary product outcome:** Agency operator sees a client account cockpit: health score, blocked onboarding, connector gaps, next actions, risks, and opportunities.

**Layer split:**

- ForgeGraph frontend/domain:
  - repository method and view model translation
- Atlas UI:
  - panel placement, naming, and presentation

**Likely files:**

- Modify/create: `frontend/domain/repositories/agencyRepository.ts`
- Modify: `frontend/domain/repositories/index.ts`
- Modify: `frontend/domain/translation/viewModels.ts`
- Create: `frontend/components/company/AgencyHealthPanel.tsx`
- Modify: `frontend/components/company/CompanyWorkspaceShell.tsx`
- Tests:
  - frontend repository test
  - component test for `AgencyHealthPanel`

**Out of scope:**

- changing backend payload shape unless PR 1 bugs are found
- mutating onboarding items
- client-facing portal
- launch execution

**Success criteria:**

- Atlas/company workspace shows health score and status.
- Checklist progress displays completed/blocked/not-started counts.
- Connector readiness summary highlights missing/degraded connectors.
- Next actions are visible.
- Internal-only hints are visually scoped to operator/admin context, not generic client view.
- UI handles loading, error, and empty states.

**Verification:**

```bash
cd frontend && npm test -- AgencyHealthPanel
cd frontend && npm run lint
```

Manual:

- Open local Atlas company workspace.
- Confirm health panel renders from real backend payload.
- Simulate missing/empty payload state if tests or local data support it.

---

## PR 3 — Agency playbook template catalog

**Suggested branch:** `feat/agency-playbook-template-catalog`

**Objective:** Create a typed playbook template catalog so DMP-style prompts become backend-owned, versioned agency templates instead of loose prompt text.

**Primary product outcome:** Atlas has a reusable set of agency playbooks for discovery, onboarding, campaign audit, campaign planning, QA, reporting, churn, expansion, and connector gap explanation.

**Layer split:**

- ForgeGraph-level:
  - playbook template schema/service/API
- Atlas-specific:
  - DMP-inspired template seeds and owner department slugs

**Schema fields:**

- slug
- title
- stage
- audience: `internal`, `operator`, `client`, `customer`
- prompt_template or structured instruction body
- required_context_keys
- output_deliverable_type
- owner_department_slug
- risk_classification
- enabled
- version

**Initial Atlas seeds:**

- `agency.discovery_to_proposal`
- `agency.client_onboarding`
- `agency.campaign_audit`
- `agency.campaign_plan`
- `agency.launch_readiness_review`
- `agency.launch_execution_preview`
- `agency.weekly_pulse`
- `agency.monthly_review`
- `agency.qbr`
- `agency.deliverable_qa`
- `agency.connector_gap_explainer`
- `agency.churn_risk_review`
- `agency.expansion_opportunity_review`
- `agency.scope_creep_review`

**Likely files:**

- Create: `backend/application/services/agency_playbook_catalog.py`
- Maybe create model/migration if DB-backed; otherwise metadata/service catalog MVP.
- Create/modify API under service engagements, operating model packs, or new agency namespace.
- Tests for catalog stability, schema, slug uniqueness, valid owner department slugs.

**Out of scope:**

- executing playbooks through engine
- generating proposal deliverables
- frontend playbook selector beyond maybe API contract

**Success criteria:**

- Backend can list Atlas playbook templates.
- Every template has stable slug, stage, audience, owner department, required context, and output mapping.
- Slugs are unique.
- No prompt contains credentials/secrets or references local DMP dotfolder state.
- Tests validate template integrity.

**Verification:**

```bash
cd backend && uv run pytest tests/unit/services/test_agency_playbook_catalog.py -q
cd backend && uv run ruff check application/services tests/unit
```

---

## PR 4 — Discovery-to-proposal commercial funnel

**Suggested branch:** `feat/atlas-discovery-proposal-funnel`

**Objective:** Add the first revenue-acquisition flow: convert discovery/intake context into proposal/SOW/ROI packet deliverables tied to ForgeGraph service catalog and opportunities.

**Primary product outcome:** Atlas helps win clients, not just service existing clients.

**Layer split:**

- ForgeGraph-level:
  - opportunity/commercial metadata conventions
  - proposal packet deliverable assembly contract
- Atlas-specific:
  - marketing-agency proposal/SOW/ROI templates

**Likely reused models:**

- `CompanySignal`
- `CompanyOpportunity`
- `ServiceCatalogItem`
- `ServiceEngagement`
- `ServiceDeliverable`
- `Asset` / `AssetVersion`

**Likely files:**

- Create: `backend/application/services/agency_commercial_funnel.py`
- Create/modify: `backend/application/services/agency_deliverable_catalog.py`
- Create API action for proposal packet assembly, likely under service engagements or company ops.
- Tests for opportunity intake, proposal asset creation, ROI unknown handling, and client-safe payload.

**Out of scope:**

- billing/payment processing
- exact pricing engine
- CRM connector sync
- frontend full sales pipeline UI

**Success criteria:**

- Given discovery/intake data, backend assembles a proposal packet deliverable.
- Packet includes discovery summary, proposed service package, SOW, assumptions, ROI estimate section, and next steps.
- Missing budget/retainer/margin data is marked unknown.
- Proposal is customer-visible but filters internal notes.
- Opportunity status can be updated without corrupting service engagement state.

**Verification:**

```bash
cd backend && uv run pytest tests/unit/services/test_agency_commercial_funnel.py tests/unit/api/test_agency_commercial_funnel_api.py -q
cd backend && uv run ruff check application/services adapters/api tests/unit
```

---

## PR 5 — Deliverable quality gate

**Suggested branch:** `feat/atlas-deliverable-quality-gate`

**Objective:** Add a QA gate for Atlas deliverables before they are submitted for client approval or delivery.

**Primary product outcome:** Atlas deliverables become agency-grade and client-safe, not just assembled markdown/assets.

**Layer split:**

- ForgeGraph-level:
  - quality gate result shape and API behavior
- Atlas-specific:
  - per-deliverable required sections, risk rules, claim/evidence requirements

**Likely files:**

- Create: `backend/application/services/agency_deliverable_quality.py`
- Modify: `backend/application/services/agency_deliverable_catalog.py`
- Modify API under service deliverables or assemble endpoint.
- Tests:
  - `backend/tests/unit/services/test_agency_deliverable_quality.py`
  - API tests for run quality gate action

**Checks:**

- required sections present
- placeholder patterns absent
- no internal/confidential leakage
- evidence/source references present where required
- CTA consistency
- claim/provenance warnings
- approval risk classification
- customer-safe summary

**Out of scope:**

- full compliance legal review
- C2PA asset implementation unless already present
- lifecycle state actions beyond maybe setting metadata

**Success criteria:**

- QA gate returns pass/warn/fail with findings.
- QA result is stored in `ServiceDeliverable.metadata_json["quality_gate"]` or equivalent.
- Failed QA prevents `ready`/delivery path in later lifecycle PR; for this PR, it must at least expose machine-readable blockers.
- Tests cover placeholder leak, internal note leak, missing evidence, and successful pass.

**Verification:**

```bash
cd backend && uv run pytest tests/unit/services/test_agency_deliverable_quality.py tests/unit/api/test_service_deliverable_quality_api.py -q
cd backend && uv run ruff check application/services adapters/api tests/unit
```

---

## PR 6 — Deliverable lifecycle + client portal surface

**Suggested branch:** `feat/service-deliverable-client-lifecycle`

**Objective:** Add explicit deliverable lifecycle actions and UI surface for client review/delivery/acceptance.

**Primary product outcome:** Atlas can move deliverables through an agency/client approval lifecycle: ready → review → delivered → accepted.

**Layer split:**

- ForgeGraph-level:
  - lifecycle actions and permissions for `ServiceDeliverable`
- Atlas-specific:
  - how Atlas presents deliverable bundles and client language

**Actions:**

- `mark_ready`
- `submit_for_approval`
- `deliver_to_client`
- `accept`
- optional `request_revision`

**Likely files:**

- Modify: service engagement/deliverable API views/serializers/urls.
- Modify: application service for deliverable lifecycle.
- Frontend repository and panel for deliverables/client-facing package.

**Out of scope:**

- launch execution
- recurring reporting schedules
- payment/billing

**Success criteria:**

- Lifecycle transitions are validated and permissioned.
- Client-facing payload excludes internal/operator-only fields.
- Approval task integration works or is clearly deferred with status metadata.
- UI lets an operator see status and deliver/submit where allowed.
- Tests cover invalid transitions and access control.

**Verification:**

```bash
cd backend && uv run pytest tests/unit/api/test_service_deliverable_lifecycle_api.py -q
cd backend && uv run ruff check application/services adapters/api tests/unit
cd frontend && npm test -- Deliverable
cd frontend && npm run lint
```

---

## PR 7 — Campaign launch readiness dry-run

**Suggested branch:** `feat/atlas-launch-readiness-dry-run`

**Objective:** Add a backend-owned dry-run readiness review for campaign launch without performing live spend/send/publish side effects.

**Primary product outcome:** Atlas can tell the agency what blocks a launch before any risky execution.

**Layer split:**

- ForgeGraph-level:
  - launch readiness response structure and blocker semantics
- Atlas-specific:
  - campaign/marketing launch checklist rules

**Checks:**

- campaign plan approved
- assets approved
- landing page/tracking readiness
- connector readiness
- UTMs present
- compliance checks complete
- client approval present
- QA gate passed
- spend/send/publish exposure identified

**Likely files:**

- Create: `backend/application/services/agency_launch_readiness.py`
- API endpoint under whiteboards, service engagements, or company ops.
- Tests for hard blockers, warnings, dry-run-only connector behavior, and no mutation/side effects.

**Out of scope:**

- actual launch execution
- external connector calls
- spend/send side effects
- durable checkpoint model if this PR is pure dry-run

**Success criteria:**

- Endpoint returns blockers, warnings, launch preview, required approvals, and side-effect exposure.
- Missing connectors hard-block live launch but not planning deliverables.
- Dry run does not mutate external systems.
- Tests prove no launch/send/spend call is attempted.

**Verification:**

```bash
cd backend && uv run pytest tests/unit/services/test_agency_launch_readiness.py tests/unit/api/test_agency_launch_readiness_api.py -q
cd backend && uv run ruff check application/services adapters/api tests/unit
```

---

## PR 8 — Launch attempt/checkpoint model and idempotency scaffolding

**Suggested branch:** `feat/campaign-launch-attempt-checkpoints`

**Objective:** Add backend-owned durable launch attempt/checkpoint state and idempotency keys, preparing Atlas for eventual live execution.

**Primary product outcome:** Atlas has the control-plane state needed to safely execute launch actions later.

**Layer split:**

- ForgeGraph-level:
  - durable launch attempt/checkpoint model
  - side-effect ID/idempotency structure
- Atlas-specific:
  - marketing launch action categories

**Likely model fields:**

- attempt id
- organization/company/engagement/whiteboard references
- readiness review reference or snapshot
- status: draft/ready/running/paused/completed/failed/cancelled
- side_effect_ids_json
- checkpoints_json or child checkpoint rows
- requested_by/approved_by
- started_at/completed_at
- error_json

**Out of scope:**

- live connector execution
- UI beyond API visibility
- retry/resume engine implementation unless already supported

**Success criteria:**

- Launch attempt can be created from a passing readiness review.
- Attempts are idempotent by stable key.
- Backend owns all durable state.
- State transitions reject invalid/unsafe moves.
- Tests align with `docs/architecture/runtime-invariants.md`.

**Verification:**

```bash
cd backend && uv run pytest tests/unit/models/test_campaign_launch_attempt.py tests/unit/services/test_campaign_launch_attempts.py tests/unit/api/test_campaign_launch_attempts_api.py -q
cd backend && uv run ruff check infrastructure/orm application/services adapters/api tests/unit
```

---

## PR 9 — Recurring reporting cadence

**Suggested branch:** `feat/agency-reporting-cadence`

**Objective:** Add recurring report cadence definitions and generation hooks for weekly pulse, monthly review, QBR, and annual growth planning.

**Primary product outcome:** Atlas supports retention by repeatedly proving value and surfacing next actions.

**Layer split:**

- ForgeGraph-level:
  - reporting cadence model/metadata and API
- Atlas-specific:
  - weekly/monthly/QBR report templates and metrics interpretation

**Cadences:**

- `weekly_pulse`
- `monthly_review`
- `quarterly_business_review`
- `annual_growth_plan`

**Out of scope:**

- full scheduler/cron automation if not already present
- cross-client benchmarking
- live data connector ingestion

**Success criteria:**

- Engagement/company can declare reporting cadence.
- Backend can assemble report deliverable from available state.
- Stale/missing report cadence lowers health snapshot or emits next action.
- Report deliverables include wins, risks, numbers, interpretation, and next actions.
- Unknown metrics are explicit.

**Verification:**

```bash
cd backend && uv run pytest tests/unit/services/test_agency_reporting_cadence.py tests/unit/api/test_agency_reporting_cadence_api.py -q
cd backend && uv run ruff check application/services adapters/api tests/unit
```

---

## PR 10 — Profitability, scope, and SLA tracking

**Suggested branch:** `feat/agency-profit-scope-sla-tracking`

**Objective:** Add commercial controls so Atlas can manage a profitable agency relationship: package, included deliverables, revision limits, SLA, cost-to-serve, and margin status.

**Primary product outcome:** Atlas begins tracking whether a client is profitable and whether work is drifting out of scope.

**Layer split:**

- ForgeGraph-level:
  - package/SLA/scope metadata structures
  - health/commercial dimension integration
- Atlas-specific:
  - marketing-service package defaults and thresholds

**Potential fields:**

- retainer/package name
- included deliverable types/counts
- revision limits
- SLA response/review windows
- estimated hours/cost
- actual hours/cost if available
- gross margin target/status
- scope creep signals

**Out of scope:**

- billing invoices/payments
- exact time tracking unless already available
- fabricated actual cost values

**Success criteria:**

- Commercial health dimension uses package/SLA metadata.
- Unknown cost/margin remains unknown.
- Scope creep next action appears when deliverables/revisions exceed package limits.
- Tests cover no-commercial-data, healthy package, scope creep, and stale SLA.

**Verification:**

```bash
cd backend && uv run pytest tests/unit/services/test_agency_profitability.py tests/unit/services/test_agency_account_health.py -q
cd backend && uv run ruff check application/services tests/unit
```

---

## PR 11 — Churn and expansion signal generation

**Suggested branch:** `feat/agency-retention-expansion-signals`

**Objective:** Generate retention risk and expansion opportunity signals from health, reporting cadence, approvals, connector gaps, performance, and scope data.

**Primary product outcome:** Atlas proactively tells the agency which clients are at risk and where to upsell.

**Layer split:**

- ForgeGraph-level:
  - signal generation conventions using `CompanySignal` / `CompanyOpportunity`
- Atlas-specific:
  - digital marketing churn/expansion heuristics

**Signals:**

- churn risk from stale approvals, stale reports, poor performance, connector gaps, no recent wins
- expansion from strong performance, repeated out-of-scope requests, new channel opportunity, high engagement
- scope risk from revision/deliverable overages

**Out of scope:**

- automated sales outreach
- cross-client benchmarks
- ML prediction

**Success criteria:**

- Service emits deterministic signals from backend state.
- Duplicate signals are idempotent/coalesced.
- Signals appear in account health/cockpit payload.
- Tests cover churn risk, expansion opportunity, duplicate prevention, and no false metrics.

**Verification:**

```bash
cd backend && uv run pytest tests/unit/services/test_agency_retention_expansion_signals.py tests/unit/services/test_agency_account_health.py -q
cd backend && uv run ruff check application/services tests/unit
```

---

## PR 12 — Portfolio intelligence and privacy-safe benchmarks

**Suggested branch:** `feat/agency-portfolio-intelligence`

**Objective:** Add cross-client, privacy-safe portfolio insights and benchmarks for agency operators.

**Primary product outcome:** Atlas can help the agency improve operations across clients while respecting tenant/privacy boundaries.

**Layer split:**

- ForgeGraph-level:
  - aggregation and privacy guardrails
- Atlas-specific:
  - marketing benchmark dimensions and interpretation

**Guardrails:**

- no raw client data leakage across tenants
- no small-N benchmarks unless threshold is met
- no secrets/internal notes
- no client-identifying details in aggregate benchmarks unless same company/org permission permits it
- opt-in/consent flag if needed

**Candidate insights:**

- average approval latency by package/channel
- common connector blockers
- reporting cadence compliance
- deliverable throughput
- launch readiness blockers
- scope creep frequency
- churn/expansion signal counts

**Out of scope:**

- public/global benchmarking
- ML recommendations
- marketplace data sharing

**Success criteria:**

- Portfolio endpoint returns aggregate metrics only.
- Small-N or disallowed cohorts return `insufficient_data`.
- Tests prove no cross-tenant details leak.
- Cockpit can display insights at agency/operator level.

**Verification:**

```bash
cd backend && uv run pytest tests/unit/services/test_agency_portfolio_intelligence.py tests/unit/api/test_agency_portfolio_intelligence_api.py -q
cd backend && uv run ruff check application/services adapters/api tests/unit
```

---

## Dependency graph

```text
PR 0 current endpoint foundation
  -> PR 1 account health/onboarding backend
      -> PR 2 frontend cockpit
      -> PR 3 playbook catalog
          -> PR 4 discovery/proposal funnel
          -> PR 5 deliverable QA gate
              -> PR 6 deliverable lifecycle/client portal
              -> PR 7 launch readiness dry-run
                  -> PR 8 launch attempt/checkpoints
      -> PR 9 reporting cadence
          -> PR 10 profit/scope/SLA
              -> PR 11 churn/expansion signals
                  -> PR 12 portfolio intelligence
```

Some work can run in parallel after PR 1:

- PR 2 frontend cockpit can run while PR 3 playbook catalog is planned.
- PR 4 commercial funnel and PR 5 QA can be separate parallel backend efforts after PR 3 if the playbook contract is stable.
- PR 9 reporting can start after PR 1 even before launch readiness if report assembly uses existing deliverable/report primitives.

---

## Success criteria for the whole roadmap

Atlas should be able to operate like a real profit agency:

1. **Acquire:** intake prospect context and generate proposal/SOW/ROI packets.
2. **Onboard:** profile brand/client, verify connectors, assign team roles, set reporting cadence.
3. **Plan:** use typed playbooks and evidence to produce client-safe campaign plans.
4. **Produce:** assemble deliverables as assets with versions and metadata.
5. **QA:** run quality/compliance/client-safety gates before delivery.
6. **Approve:** route deliverables through client/internal approval lifecycle.
7. **Launch safely:** dry-run readiness before any spend/send/publish action.
8. **Report:** provide weekly/monthly/QBR proof of value.
9. **Retain:** detect churn risks and propose recovery actions.
10. **Expand:** identify upsell/cross-sell opportunities from evidence.
11. **Profit:** track scope, SLA, package economics, and cost-to-serve.
12. **Learn:** aggregate privacy-safe portfolio insights across accounts.

---

## Recommended next action

After PR #56 is merged, start **PR 1: `feat/atlas-account-health-onboarding-foundation`** as a backend-only PR.

Do not start PR 2 frontend UI until PR 1 payload is stable and verified locally.
