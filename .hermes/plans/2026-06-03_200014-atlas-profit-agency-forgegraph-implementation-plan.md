# Atlas Profit Agency ForgeGraph Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task after Mike approves the slice. This is a planning artifact only; do not implement until approved.

**Goal:** Translate the Digital Marketing Pro-inspired “real profit agency” concepts into ForgeGraph-native backend state, Atlas product-mode behavior, and frontend surfaces.

**Architecture:** Keep ForgeGraph backend as the only durable source of truth. Implement shared agency/business primitives in ForgeGraph backend services and API contracts; implement Atlas-specific catalogs, seeded playbooks, default metadata, and product-mode UI composition on top of those primitives. Avoid local-file or engine-owned durable state.

**Tech Stack:** Django/DRF backend, existing ForgeGraph ORM models/services, Next.js frontend repositories/components, pytest, ruff, existing company/product-mode test patterns.

---

## 0. Current repo context

### Runtime invariant that governs the plan

`docs/architecture/runtime-invariants.md` is authoritative:

- Durable state belongs to the backend control plane.
- Engine/client events are transport or observability, not authoritative state.
- Resume/checkpoint state for launch-style workflows must be backend-owned.

So the DMP patterns must be translated into backend-owned ForgeGraph resources, not plugin dotfolders, frontend local state, or engine-memory workflows.

### Existing ForgeGraph primitives to reuse

Do not create parallel systems when these existing concepts fit:

- `ServiceCatalogItem` — customer-facing service offers.
- `ServiceEngagement` — company-scoped request/purchase of a service.
- `ServiceDeliverable` — customer-facing wrapper around an asset/report.
- `Asset` / `AssetVersion` — durable artifacts and versioned contents.
- `WorkWhiteboard` — active work request context.
- `ApprovalTask` — human/client approval hooks.
- `ReportRun` — generated reports and metric snapshots.
- `CompanySignal` — backend-owned business signals.
- `CompanyOpportunity` — qualified company opportunities; currently commerce-shaped but reusable/extendable.
- `CompanyTeamRole` / `CompanyTeamAssignment` — team roles and assignments.
- `GatewayConnection` / `GatewayConnectorCapability` — connector state/capability metadata.
- operating-model pack installation config — good place for Atlas default connector inventory and agency pack metadata.

### Existing Atlas-specific implementation

Already present or in PR #56:

- `backend/application/services/agency_deliverable_catalog.py`
- `backend/application/services/agency_deliverables.py`
- `POST /api/whiteboards/{whiteboard_id}/atlas-deliverables/assemble`
- 10 MVP deliverable types:
  - `client_brief`
  - `strategy_brief`
  - `message_house`
  - `launch_readiness_checklist`
  - `connector_gap_report`
  - `measurement_plan`
  - `approval_packet`
  - `execution_receipt`
  - `performance_report`
  - `campaign_launch_package`
- Actual Atlas department slugs:
  - `strategy_research`
  - `brand_content`
  - `channel_execution`
  - `crm_lifecycle`
  - `analytics_performance`
  - `qa_compliance`
  - `client_approval_ops`

---

## 1. Translation map: DMP idea -> ForgeGraph term -> Atlas term

| DMP concept | ForgeGraph-native concept | Atlas product term | Notes |
|---|---|---|---|
| Brand profile | `CompanyAgencyProfile` service payload stored in `Graph.metadata_json` or a new profile model | Client Profile | Direct Atlas-visible feature; may start in metadata, promote to model later. |
| Client onboarding workflow | Backend-owned `ClientOnboardingChecklist` model/service | Client Onboarding | ForgeGraph primitive because other service verticals may need onboarding too. Atlas seeds checklist items. |
| Credential profile | `GatewayConnection` + `APIKey` + per-company connector policy | Connector Readiness | ForgeGraph-level primitive; Atlas uses it for marketing connectors. |
| Campaign audit | `ServiceEngagement` + `ServiceDeliverable` + `AssetVersion` + optional `ReportRun` | Baseline Audit | Atlas playbook/deliverable, ForgeGraph persistence. |
| Proposal/SOW | `ServiceCatalogItem` + `CompanyOpportunity` + `ServiceDeliverable` | Proposal Packet | Shared agency/commercial feature; Atlas-specific templates. |
| ROI calculator | Service function that writes ROI section into proposal/performance assets | ROI Estimate | Start as Atlas service helper; if generalized later, move to common service. |
| Agency dashboard | Aggregation service over companies, engagements, deliverables, approvals, connectors, report runs | Portfolio Health | ForgeGraph-level endpoint; Atlas UI section. |
| Client health score | Backend computed snapshot, no durable model needed initially | Client Health | Start read-only calculated API; persist snapshots only if trend/history is needed. |
| Churn risk | `CompanySignal(signal_kind=risk)` + health snapshot | Retention Risk | Direct Atlas feature, no new durable model in first slice. |
| Expansion signal | `CompanySignal(signal_kind=opportunity)` / `CompanyOpportunity` | Expansion Opportunity | Reuse/extend company ops. |
| Scope creep | Health/signal logic over package vs requested deliverables/revisions | Scope Alert | Needs package/SLA metadata first. |
| QA/check/eval | `DeliverableQualityGate` service + QA result metadata on `ServiceDeliverable`/`AssetVersion` | Quality Gate | Start service + metadata; later promote to model if review history matters. |
| Claim provenance | Claim objects linked to asset/deliverable | Claim Register | Likely ForgeGraph model, but can begin inside deliverable metadata. |
| Launch campaign | Backend-owned launch-readiness and launch-attempt records | Launch Readiness | Must be backend-owned due runtime invariants. |
| Weekly/monthly/QBR | recurring report schedule + generated deliverables | Reporting Cadence | Needs schedule object or metadata-based MVP. |
| Cross-client insights | consent-scoped, anonymized aggregate insights | Portfolio Intelligence | Later phase, requires explicit privacy guardrails. |
| DMP commands/skills | typed `AgencyPlaybookTemplate` catalog | Playbooks | ForgeGraph primitive; Atlas seeds marketing playbooks. |

---

## 2. Separation: Atlas-specific vs ForgeGraph-level changes

### Changes we can do directly in Atlas layer

These should live in Atlas-specific services/catalogs/templates because they encode marketing-agency behavior:

1. Atlas playbook catalog seed data:
   - `agency.discovery_to_proposal`
   - `agency.client_onboarding`
   - `agency.campaign_audit`
   - `agency.campaign_plan`
   - `agency.launch_readiness_review`
   - `agency.weekly_pulse`
   - `agency.monthly_review`
   - `agency.qbr`
   - `agency.deliverable_qa`
   - `agency.connector_gap_explainer`
   - `agency.churn_risk_review`
   - `agency.expansion_opportunity_review`
   - `agency.scope_creep_review`
2. Atlas deliverable QA rules for the 10 MVP deliverables.
3. Atlas default client profile schema fields.
4. Atlas onboarding default checklist items.
5. Atlas health-score weights for digital marketing accounts.
6. Atlas connector classifications for marketing channels.
7. Atlas UI naming and presentation.

### Changes that should be ForgeGraph-level primitives

These should not be Atlas-only because they are generic service-business building blocks:

1. Agency/account health aggregation endpoint.
2. Client onboarding checklist persistence.
3. Playbook template catalog and playbook execution/request metadata.
4. Deliverable quality gate result structure.
5. Launch readiness / launch attempt backend-owned checkpointing.
6. Reporting cadence/schedule model.
7. Proposal/SOW/commercial opportunity extensions.
8. Connector readiness normalization over `GatewayConnection` and pack config.
9. Claim/provenance register if review history and compliance auditability matter.
10. Scope/margin/SLA tracking.

---

## 3. Recommended implementation roadmap

### Phase 1 — Operator cockpit and onboarding foundation

This phase makes Atlas look and operate like an agency immediately, without needing live connector execution.

**Deliverables:**

1. `ClientAccountHealthSnapshot` read-only service + API.
2. Atlas client profile metadata schema.
3. Atlas onboarding checklist service seeded from `digital_marketing_pro.v1` pack installation.
4. Frontend portfolio/client health panel in company workspace.

**Why first:** Gives the operator a clear account cockpit and converts the DMP ideas into ForgeGraph terms without large migrations or execution risk.

### Phase 2 — Playbook templates and commercial funnel

**Deliverables:**

1. `AgencyPlaybookTemplate` catalog.
2. Atlas playbook seeds.
3. Discovery-to-proposal / SOW / ROI packet assembly.
4. Company opportunity metadata extensions for agency sales.

**Why second:** Turns Atlas into a business-development assistant, not only a delivery assistant.

### Phase 3 — Deliverable QA and approval lifecycle

**Deliverables:**

1. `DeliverableQualityGate` service.
2. QA metadata attached to assembled deliverables.
3. Client/internal visibility split improvements.
4. Lifecycle actions: `mark_ready`, `submit_for_approval`, `deliver_to_client`, `accept`.

**Why third:** Raises deliverables from “generated” to “client-safe agency work.”

### Phase 4 — Launch readiness and execution safety

**Deliverables:**

1. `CampaignLaunchReadiness` dry-run endpoint.
2. Backend-owned launch attempt/checkpoint model or durable metadata.
3. Launch receipt deliverable.
4. Hard-block semantics for live spend/send actions.

**Why fourth:** Requires careful state modeling and strong idempotency; should follow QA and approval gates.

### Phase 5 — Recurring reporting, profit, retention, expansion

**Deliverables:**

1. Weekly/monthly/QBR report schedules.
2. Scope/margin/SLA tracking.
3. Churn and expansion signal generation.
4. Cross-client benchmarks with consent/aggregation guardrails.

**Why fifth:** Depends on enough engagement/report history to be meaningful.

---

## 4. First implementation slice proposal

### Slice name

`feat/atlas-account-health-onboarding-foundation`

### Scope

Implement a read-only agency health snapshot plus Atlas onboarding checklist assembly. Avoid new live execution and avoid connector mutation.

### User-visible outcome

For a company with the Atlas/digital marketing pack installed, the backend can return a structured health/onboarding snapshot like:

```json
{
  "company_id": "...",
  "profile": {
    "schema": "atlas.client_profile.v1",
    "brand_name": "Atlas Mkt",
    "target_markets": [],
    "regulated_industry": false,
    "primary_goal": "",
    "active_channels": []
  },
  "health": {
    "score": 72,
    "status": "amber",
    "lowest_dimension": "connector_readiness",
    "dimensions": [
      {"key": "deliverable_pipeline", "score": 80, "status": "green"},
      {"key": "approval_flow", "score": 75, "status": "amber"},
      {"key": "connector_readiness", "score": 45, "status": "red"},
      {"key": "reporting_cadence", "score": 60, "status": "amber"},
      {"key": "commercial_health", "score": 70, "status": "amber"}
    ]
  },
  "onboarding": {
    "status": "in_progress",
    "completed_count": 4,
    "total_count": 9,
    "items": [
      {"key": "brand_profile", "status": "completed"},
      {"key": "connector_readiness", "status": "blocked"}
    ]
  },
  "signals": {
    "risks": [],
    "opportunities": []
  },
  "next_actions": []
}
```

### Why this slice is small enough

- Mostly aggregation and metadata interpretation.
- Can reuse existing models.
- Does not require migrations if onboarding checklist starts as pack/company metadata or service-generated virtual checklist.
- Establishes vocabulary for later UI and backend primitives.

---

## 5. Detailed task plan for Slice 1

### Task 1: Add Atlas profile/onboarding/health catalog definitions

**Objective:** Define Atlas-specific schemas and default checklist/health dimensions without touching DB schema.

**Files:**

- Create: `backend/application/services/agency_account_catalog.py`
- Test: `backend/tests/unit/services/test_agency_account_catalog.py`

**Implementation details:**

Create dataclasses or typed dictionaries for:

- `ATLAS_CLIENT_PROFILE_SCHEMA = "atlas.client_profile.v1"`
- default profile fields:
  - `brand_name`
  - `industry`
  - `business_model`
  - `revenue_model`
  - `price_range`
  - `sales_cycle`
  - `target_markets`
  - `regulated_industry`
  - `brand_voice`
  - `primary_goal`
  - `active_channels`
  - `competitors`
  - `approved_claims`
  - `compliance_notes`
- onboarding items:
  - `brand_profile`
  - `credential_profile`
  - `connector_readiness`
  - `crm_sync`
  - `team_assignment`
  - `reporting_cadence`
  - `baseline_campaign_audit`
  - `service_package_selection`
  - `approval_contacts`
- health dimensions:
  - `deliverable_pipeline`
  - `approval_flow`
  - `connector_readiness`
  - `reporting_cadence`
  - `commercial_health`

**Tests:**

- Verify item keys are stable.
- Verify health weights total 100.
- Verify default profile contains required schema/version keys.
- Verify all checklist items have owner department slugs that match the actual Atlas slugs.

**Run:**

```bash
cd backend && uv run pytest tests/unit/services/test_agency_account_catalog.py -q
```

Expected: new tests pass.

---

### Task 2: Build connector readiness normalizer

**Objective:** Translate pack config and gateway connection state into a common connector readiness payload.

**Files:**

- Create: `backend/application/services/agency_connector_readiness.py`
- Test: `backend/tests/unit/services/test_agency_connector_readiness.py`

**Inputs to support:**

1. Company pack installation config keys:
   - `available_connectors`
   - `connector_inventory`
   - `missing_connectors`
2. Existing `GatewayConnection` records when present.
3. Optional expected connector list from Atlas catalog.

**Output status classes:**

- `connected`
- `missing`
- `expired`
- `permission_limited`
- `stale_data`
- `dry_run_only`
- `real_execution_enabled`
- `error`
- `unknown`

**Rules:**

- Missing connectors degrade audits/planning but become blockers for launch/spend/send readiness later.
- Dry-run/sandbox connectors count as available for rehearsal but not live execution.
- Do not expose credential values or token metadata.

**Tests:**

- Pack inventory with sandbox connector -> `dry_run_only`.
- Missing connector entry -> `missing`.
- GatewayConnection `status=error` -> `error`.
- Payload redacts credential IDs/secrets.

---

### Task 3: Build virtual onboarding checklist assembler

**Objective:** Compute onboarding checklist status without adding a DB model yet.

**Files:**

- Create: `backend/application/services/agency_onboarding.py`
- Test: `backend/tests/unit/services/test_agency_onboarding.py`

**Approach:**

Read from:

- company `metadata_json.agency_profile` or `metadata_json.atlas.client_profile`
- pack installation config
- connector readiness output
- team assignments if available
- existing service deliverables for `baseline_campaign_audit` or related deliverable type

Return:

- checklist items
- completed/blocked/not_started counts
- next action per blocked item
- owner department slug

**No migration in this slice.**

If later we need assigned owners, due dates, comments, and audit history, promote this to a `ClientOnboardingChecklist` model.

**Tests:**

- Empty profile -> brand profile item is `not_started`.
- Missing connectors -> connector readiness is `blocked`.
- Existing baseline audit deliverable -> baseline audit item is `completed`.
- All item owners use valid Atlas department slugs.

---

### Task 4: Build account health snapshot service

**Objective:** Aggregate ForgeGraph resources into a client health snapshot.

**Files:**

- Create: `backend/application/services/agency_account_health.py`
- Test: `backend/tests/unit/services/test_agency_account_health.py`

**Inputs:**

- `company: Graph`
- `user: User`
- optional `now`

**Dimensions:**

1. `deliverable_pipeline`
   - count ready/delivered/overdue/in_review deliverables
   - score draft/in_review/ready/delivered balance
2. `approval_flow`
   - approval task statuses and age
   - score lower when client approvals are stale
3. `connector_readiness`
   - connector readiness normalizer output
   - score based on required vs available connectors
4. `reporting_cadence`
   - recent `ReportRun` / performance report deliverables
   - score lower if no recent report exists
5. `commercial_health`
   - start with safe placeholders from `ServiceEngagement.metadata_json.pricing`, `pricing_metadata_json`, and future scope fields
   - do not fake margin numbers; mark unknown when unavailable

**Output:**

- total score 0-100
- status: `green`, `amber`, `red`
- lowest dimension
- dimension details
- risks/opportunities from `CompanySignal` and `CompanyOpportunity`
- next recommended actions

**Tests:**

- No data returns neutral/amber with unknown commercial fields, not fabricated numbers.
- Missing connector lowers connector readiness and creates next action.
- Stale approval lowers approval score.
- Recent delivered report improves reporting cadence.
- Total score uses configured weights.

---

### Task 5: Add API endpoint for account health snapshot

**Objective:** Expose the snapshot through a backend-controlled API.

**Files:**

- Modify: `backend/adapters/api/company_ops/views.py`
- Modify: `backend/adapters/api/company_ops/urls.py`
- Possibly create/modify: `backend/adapters/api/company_ops/serializers.py`
- Test: `backend/tests/unit/api/test_company_ops_api.py` or new `test_agency_account_health_api.py`

**Endpoint proposal:**

```text
GET /api/companies/{company_id}/ops/agency-health
```

Alternative if current routing does not nest company ops under `/companies/{company_id}`:

```text
GET /api/company-ops/agency-health?company_id=...
```

Prefer whichever matches existing `company_ops` routing conventions after implementation inspection.

**Permissions:**

- `IsAuthenticated`
- user must have company access
- viewer can read
- no mutation

**API test cases:**

- Unauthorized returns 401.
- No company access returns 403/404 according to existing convention.
- Accessible company returns expected payload.
- Payload contains no secrets.

---

### Task 6: Surface health snapshot in frontend repository layer

**Objective:** Give frontend a typed repository method without building full UI yet.

**Files:**

- Modify: `frontend/domain/repositories/companyRepository.ts` or create `frontend/domain/repositories/agencyRepository.ts`
- Modify: `frontend/domain/translation/viewModels.ts` if using view model translation
- Test: relevant frontend unit repository test

**Types:**

Add view models for:

- `AgencyHealthSnapshotViewModel`
- `AgencyHealthDimensionViewModel`
- `AgencyOnboardingItemViewModel`
- `AgencyConnectorReadinessViewModel`

**Tests:**

- Repository calls correct endpoint.
- Translation handles missing/unknown fields.
- Does not render raw backend-only/internal metadata to clients by default.

---

### Task 7: Add Atlas agency cockpit panel to company workspace

**Objective:** Show account health and onboarding status in Atlas/company workspace.

**Files:**

- Modify: `frontend/components/company/CompanyWorkspaceShell.tsx`
- Possibly create: `frontend/components/company/AgencyHealthPanel.tsx`
- Possibly modify: `frontend/components/company/OperatingModelWorkspace.tsx`
- Test: add/update component unit tests if existing project supports this.

**UI content:**

- Health score and status color.
- Lowest dimension.
- Checklist progress.
- Connector readiness summary.
- Next actions.
- Risks/opportunities.

**Important UI split:**

- Operator view may show internal risk/scope/margin hints.
- Client-facing deliverable panels must not show internal notes unless explicitly intended.

---

### Task 8: Verification for Slice 1

**Backend commands:**

```bash
cd backend && uv run pytest \
  tests/unit/services/test_agency_account_catalog.py \
  tests/unit/services/test_agency_connector_readiness.py \
  tests/unit/services/test_agency_onboarding.py \
  tests/unit/services/test_agency_account_health.py \
  tests/unit/api/test_agency_account_health_api.py -q

cd backend && uv run ruff check application/services adapters/api tests/unit
```

**Frontend commands:**

Use existing package manager conventions after checking repo scripts. Likely:

```bash
cd frontend && npm test -- AgencyHealthPanel
cd frontend && npm run lint
```

**Manual API verification:**

Against local Atlas Mkt company:

```text
GET /api/companies/{company_id}/ops/agency-health
```

Verify:

- score/status present
- onboarding items present
- connector gaps represented as gaps, not crashes
- no tokens/secrets
- values are derived from current backend state

---

## 6. Future slice plans

### Slice 2: Agency playbook template catalog

**ForgeGraph-level primitive:**

Create model/service or metadata-backed MVP for `AgencyPlaybookTemplate`:

- slug
- title
- stage
- audience: internal/client/customer
- prompt_template
- required_context_keys
- output_deliverable_type
- owner_department_slug
- risk_classification
- enabled

**Atlas seeds:**

- `agency.discovery_to_proposal`
- `agency.client_onboarding`
- `agency.campaign_audit`
- `agency.campaign_plan`
- `agency.launch_readiness_review`
- `agency.weekly_pulse`
- `agency.monthly_review`
- `agency.qbr`
- `agency.deliverable_qa`
- `agency.connector_gap_explainer`

**Likely files:**

- `backend/infrastructure/orm/models/operating_models.py` or new model group if DB-backed
- `backend/application/services/agency_playbooks.py`
- `backend/adapters/api/service_engagements` or new `agency_playbooks` API
- frontend repository and UI selector

### Slice 3: Discovery-to-proposal commercial funnel

**Use/extend:**

- `CompanySignal`
- `CompanyOpportunity`
- `ServiceCatalogItem`
- `ServiceEngagement`
- `ServiceDeliverable`

**Features:**

- opportunity intake fields: ICP fit, pain, budget, authority, timing, expected retainer, close probability
- proposal packet deliverable
- SOW section
- ROI estimate section
- pricing/package metadata
- win/loss status update

### Slice 4: Deliverable QA gate

**MVP without migration:**

- `backend/application/services/agency_deliverable_quality.py`
- QA schema in `agency_deliverable_catalog.py`
- QA result stored in `ServiceDeliverable.metadata_json["quality_gate"]`
- API action: `POST /api/service-deliverables/{id}/quality-gate/run` or integrate into assemble endpoint with `run_quality_gate=true`

**Checks:**

- required sections
- placeholder patterns
- internal/confidential leakage
- evidence/source availability
- CTA consistency
- approval risk classification

### Slice 5: Launch readiness dry-run

**ForgeGraph-level durable state needed:**

- Either new `CampaignLaunchAttempt` / `LaunchReadinessReview` model,
- or initially an `Asset`/`ServiceDeliverable` + metadata approach if no resume/execution occurs.

**Hard rule:**

No launch/spend/send execution until backend has:

- approved plan
- approved assets
- connector readiness
- tracking verification
- compliance checks
- client approval
- idempotency key / side-effect IDs

### Slice 6: Recurring reports and retention/expansion

**Features:**

- reporting cadence metadata/model
- weekly pulse/monthly/QBR generation
- stale-report risk signal
- churn risk signal
- expansion opportunity signal
- scope creep signal
- package margin fields

---

## 7. Risks and tradeoffs

### Risk: too many new models too soon

Mitigation: Slice 1 uses services and metadata-first approaches. Promote to models only when audit history, assignment, due dates, or trend persistence is necessary.

### Risk: mixing Atlas-specific agency logic into core ForgeGraph

Mitigation: Put generic abstractions in ForgeGraph (`health snapshot`, `playbook template`, `onboarding checklist`, `connector readiness`) and put marketing-specific seeds/rules in Atlas catalogs.

### Risk: fabricating commercial metrics

Mitigation: Unknown margins/retainers must be represented as `unknown`, not guessed. Health score should clearly distinguish measured vs unavailable dimensions.

### Risk: leaking internal notes to client-facing deliverables

Mitigation: Keep `visibility` and `client_safe` filtering explicit. QA gate should check for internal-only leakage.

### Risk: launch readiness becomes engine-owned

Mitigation: Store launch state/checkpoints in backend models or backend-owned assets. Engine can execute, but backend owns launch attempt state and side-effect IDs.

### Risk: connector gaps block too much

Mitigation: Planning/audit/deliverables degrade gracefully. Only live launch/spend/send actions hard-block.

---

## 8. Open questions for Mike before implementation

1. Should Slice 1 include frontend UI immediately, or start backend-only with API verification?
2. Should onboarding checklist be metadata/virtual for MVP, or do we want a first-class DB model now?
3. Should proposal/SOW come before account health if the immediate goal is client acquisition rather than operations?
4. Should agency health live under `company_ops` routes, or should we introduce an `agency` API namespace?
5. Which view is first priority: operator cockpit, client-facing portal, or internal Atlas workspace?

---

## 9. Recommended next step

Proceed with **Slice 1 backend-first**:

1. Catalog definitions.
2. Connector readiness normalizer.
3. Virtual onboarding checklist.
4. Account health snapshot service.
5. Read-only API endpoint.
6. Backend tests + ruff.

Then do a second PR for frontend cockpit UI once the payload shape is stable.
