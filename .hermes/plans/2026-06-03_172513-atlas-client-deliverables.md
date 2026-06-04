# Atlas Client Deliverables Implementation Plan

> **For Hermes:** This is a planning-only document. Do not implement until Mike approves. Use `subagent-driven-development` only after approval, and execute task-by-task with tests.

**Goal:** Shift Atlas from “workflow completed / operations executed” toward a client-facing marketing-agency deliverables model: each engagement should produce named, versioned, reviewable client deliverables with evidence, approvals, departments, and handoff status.

**Architecture:** ForgeGraph already has useful primitives (`Asset`, `AssetVersion`, `ServiceDeliverable`, communication threads, whiteboard phase/deployment/performance contracts), but Atlas currently treats outputs mostly as operation state, reports, tool receipts, board cards, and signals. Add a deliverables layer that composes those existing artifacts into an explicit agency package: strategy, creative/content, media/channel plan, CRM/lifecycle plan, measurement plan, QA/compliance memo, approval packet, launch readiness, performance report, and next-steps roadmap.

**Tech Stack:** ForgeGraph Django/DRF backend, existing ORM models in `backend/infrastructure/orm/models`, operating-model pack services, archive/assets API, whiteboard orchestration services, frontend company workspace/translation UI, Atlas `digital_marketing_pro.v1` pack metadata.

---

## 1. Product Framing

Mike's direction: connector issues can wait. For now, plan around **deliverables**: what a marketing agency typically hands to a client and what ForgeGraph + Atlas need to change so those deliverables are first-class.

### Core principle

A client should not need to inspect internal workstreams, board cards, tool executions, or raw whiteboard contracts to know what they bought. They should see a coherent **client package**:

- what was requested,
- what was produced,
- what is approved / waiting / blocked,
- what evidence supports it,
- what can be used immediately,
- what is only a recommendation because a connector or approval is missing,
- what the agency recommends next.

---

## 2. Typical Marketing Agency Deliverables

### 2.1 Discovery / Intake Deliverables

1. **Client Brief / Campaign Brief**
   - Captures objective, audience, budget, timeline, product facts, brand constraints, approvals, assumptions, and missing information.
   - Atlas owner: `strategy_research` + `client_approval_ops`.
   - ForgeGraph source today: whiteboard onboarding fields + communication request message.

2. **Account / Brand Context Pack**
   - A reusable context document for future work: brand voice, product catalog facts, offer constraints, known risks, preferred channels, approval owners.
   - Atlas owner: `strategy_research`, `brand_content`, `client_approval_ops`.
   - ForgeGraph source today: company profile, assets/context packs, whiteboard metadata.

3. **Scope of Work / Engagement Plan**
   - What Atlas will produce, what is out of scope, what requires connectors/credentials, expected review gates.
   - Atlas owner: `client_approval_ops`.
   - ForgeGraph source today: service engagement models exist, but not exposed as a client-facing package in the Atlas flow.

### 2.2 Strategy Deliverables

4. **Marketing Strategy Brief**
   - Positioning, audience hypothesis, funnel approach, channel rationale, budget allocation, campaign thesis.
   - Atlas owner: `strategy_research`.
   - Current flow source: `strategy_brief`, `media_channel_plan`, `traffic_dependency_map` workstreams.

5. **Research / Insight Summary**
   - Evidence behind the strategy: customer assumptions, market context, competitor notes, risks.
   - Atlas owner: `strategy_research`.
   - Useful as a reusable Asset for future client work.

6. **Go-to-Market / Launch Plan**
   - Timeline, milestones, dependencies, channel sequence, approval gates, first-wave limitations.
   - Atlas owner: `channel_execution` + `client_approval_ops`.
   - Current source: deployment policy + phase contract.

### 2.3 Creative / Content Deliverables

7. **Message House**
   - Core promise, proof points, objections, tagline/CTA options, claims to avoid.
   - Atlas owner: `brand_content` + `qa_compliance`.
   - Current flow source: `copy_message_house`.

8. **Channel Copy Pack**
   - Email subject/body draft, WhatsApp draft, social captions, landing page copy outline.
   - Must distinguish `ready for use`, `draft only`, and `blocked/recommendation` if connector or approval is missing.
   - Atlas owner: `brand_content`, `channel_execution`.

9. **Creative Direction / Asset Brief**
   - Visual guidelines, image prompts, format specs, asset list, production instructions.
   - Atlas owner: `brand_content`.
   - Could later connect to image/video generation, but initial deliverable can be text/spec only.

10. **Content Calendar / Flighting Plan**
    - Timing, sequence, channel cadence, inventory constraints, budget pacing.
    - Atlas owner: `brand_content` + `channel_execution`.
    - Current flow source: `timing_flighting_plan`.

### 2.4 Media / Channel Execution Deliverables

11. **Media Plan / Channel Plan**
    - Channel mix, budget split, audience targeting, expected outcomes, dependency map.
    - Atlas owner: `channel_execution`.
    - Current flow source: `media_channel_plan`.

12. **Launch Readiness Checklist**
    - Status of every channel: ready, blocked, needs approval, missing connector, recommendation only.
    - Atlas owner: `channel_execution` + `qa_compliance`.
    - Current source: deployment contract channel states.

13. **Execution Receipt / Deployment Evidence**
    - What actually happened: sandbox email/WhatsApp receipt, tool execution IDs, blocked channel signal IDs, no-publication disclaimer.
    - Atlas owner: `channel_execution`.
    - Current source: `ToolExecution`, deployment channel receipt, `CompanySignal`, routing records.

14. **Connector Gap / Production Readiness Report**
    - Missing credentials/connectors, what would unlock production execution, priority and impact.
    - Atlas owner: `client_approval_ops` + `channel_execution`.
    - This is explicitly important because connector work is deferred.

### 2.5 CRM / Lifecycle Deliverables

15. **Audience Segmentation Plan**
    - Segments, consent assumptions, lifecycle stage, targeting criteria.
    - Atlas owner: `crm_lifecycle`.

16. **Lifecycle Journey / Nurture Plan**
    - Follow-up sequence, retention/remarketing handoff, CRM-safe copy notes.
    - Atlas owner: `crm_lifecycle` + `brand_content`.

17. **Customer Data / Consent Checklist**
    - What data is needed, what is safe to use, what cannot be assumed.
    - Atlas owner: `crm_lifecycle` + `qa_compliance`.

### 2.6 Measurement / Performance Deliverables

18. **Measurement Plan**
    - KPIs, baselines, targets, data sources, attribution assumptions, cadence, decision rules.
    - Atlas owner: `analytics_performance`.
    - Current source: `analytics_measurement_plan`.

19. **Performance Report**
    - Snapshot of metrics, what changed, what worked, what did not, what to do next.
    - Atlas owner: `analytics_performance`.
    - Current source: performance contract `metric_snapshot_id`, `report_run_id`, `evaluation_id`.

20. **Optimization Roadmap**
    - Prioritized next experiments, expected impact, required approvals/connectors.
    - Atlas owner: `analytics_performance` + `strategy_research`.

### 2.7 QA / Compliance / Approval Deliverables

21. **Claims & Compliance Memo**
    - Claims verified, claims blocked, evidence needed, risk level, final compliance gate result.
    - Atlas owner: `qa_compliance`.
    - Current source: `legal_claims_precheck`, gate scorecard, approval task payload/result.

22. **Approval Packet**
    - Client-facing bundle for approval: summary, assets to approve, risk notes, exact decision requested.
    - Atlas owner: `client_approval_ops`.
    - Current source: approval task + phase contract + deliverable list.

23. **Decision / Approval Log**
    - What was approved, by whom, when, with notes and scope of approval.
    - Atlas owner: `client_approval_ops`.
    - Current source: `ApprovalTask` + communication messages.

### 2.8 Final Client Package

24. **Campaign Launch Package**
    - A unified client handoff containing brief, strategy, content, channel plan, approval packet, launch readiness, execution receipts/blockers, and measurement plan.

25. **Post-Launch / Performance Package**
    - Performance report, optimization roadmap, connector gaps, next sprint recommendations.

---

## 3. Proposed Deliverable Taxonomy for Atlas

Use stable deliverable types instead of ad hoc strings. Initial taxonomy:

```text
client_brief
brand_context_pack
scope_of_work
strategy_brief
research_insight_summary
go_to_market_plan
message_house
channel_copy_pack
creative_direction_brief
content_calendar
media_plan
launch_readiness_checklist
execution_receipt
connector_gap_report
audience_segmentation_plan
lifecycle_journey_plan
consent_data_checklist
measurement_plan
performance_report
optimization_roadmap
claims_compliance_memo
approval_packet
approval_log
campaign_launch_package
post_launch_performance_package
```

Each deliverable should carry metadata:

```json
{
  "deliverable_type": "strategy_brief",
  "title": "Legacy DEPP GOLD Strategy Brief",
  "status": "draft|in_review|ready|delivered|accepted|archived",
  "visibility": "customer|operator|internal",
  "department_slug": "strategy_research",
  "engagement_id": "...",
  "whiteboard_id": "...",
  "phase_id": "...",
  "source_workstream_ids": ["strategy_brief", "media_channel_plan"],
  "source_operation_ids": ["..."],
  "asset_id": "...",
  "asset_version_id": "...",
  "report_run_id": "...",
  "approval_task_id": "...",
  "evidence_links": ["..."],
  "blocked_by": ["missing_connector:social_connector"],
  "client_summary": "Plain-language summary for the client.",
  "internal_notes": "Optional operator-only notes.",
  "requires_client_approval": true,
  "approved_at": null,
  "delivered_at": null
}
```

---

## 4. What Needs To Change In ForgeGraph

### 4.1 Backend domain model alignment

Current useful primitives:

- `Asset` / `AssetVersion` in `backend/infrastructure/orm/models/decisions_assets.py`.
- `ServiceDeliverable` in `backend/infrastructure/orm/models/operating_models.py`.
- `CommunicationThread` and `CommunicationMessage` can already reference artifacts, reports, deliverables, approvals, departments.
- Archive API exposes assets and asset versions.
- Whiteboard phase/deployment/performance services already produce contracts and evidence IDs.

Main gap: these primitives are not yet orchestrated into a first-class Atlas deliverables workflow.

Planned backend changes:

1. **Add a deliverable catalog / registry**
   - Define canonical deliverable type metadata: label, description, owning department, default visibility, whether approval required, source phase/workstream mappings.
   - Prefer pack metadata first (`digital_marketing_pro.v1`) and service helper accessors; add database only if needed later.

2. **Add deliverable assembly service**
   - New service likely under `backend/application/services/agency_deliverables.py` or `backend/application/services/service_deliverables.py`.
   - Input: whiteboard, company, pack installation, phase/deployment/performance contracts.
   - Output: planned/actual `ServiceDeliverable` records plus linked `Asset`/`AssetVersion` content.

3. **Create assets for client-facing content**
   - Use `Asset(asset_type="deliverable"|"report"|"memo")` and `AssetVersion` for the body/content pointer.
   - Decide content storage approach:
     - short-term: content URI points to existing archive/blob/local storage mechanism already used by ArchiveService;
     - do not invent a new storage backend if ArchiveService already has one.

4. **Expose deliverables API**
   - Candidate endpoints:
     ```text
     GET  /api/companies/{company_id}/deliverables
     GET  /api/companies/{company_id}/deliverables/{deliverable_id}
     GET  /api/whiteboards/{whiteboard_id}/deliverables
     POST /api/whiteboards/{whiteboard_id}/deliverables/assemble
     PATCH /api/deliverables/{deliverable_id}
     POST /api/deliverables/{deliverable_id}/deliver
     ```
   - Requires idempotency for assemble/deliver actions.
   - Must preserve RBAC: viewer can read customer-visible deliverables, admin/operator can assemble/deliver.

5. **Wire deliverables into orchestration milestones**
   - Phase synthesis should create/update strategy/content/QA/approval deliverables.
   - Deployment prepare should create/update launch readiness, execution receipt, connector gap report.
   - Performance report/evaluate should create/update performance report and optimization roadmap.

6. **Approval integration**
   - Approval tasks should reference one or more deliverables.
   - Approval result should update deliverable status (`in_review -> ready`, or rejected back to draft).
   - Store a client-readable approval log deliverable.

7. **Evidence linking**
   - Link deliverables to tool executions, report runs, metric snapshots, company signals, and routing records.
   - Use existing `EvidenceLink` where appropriate instead of adding parallel evidence tables.

8. **Export/read model support**
   - Add a compact `deliverable_payload()` serializer with:
     - title/type/status/visibility,
     - preview/summary,
     - content or content URL,
     - department,
     - approval status,
     - evidence counts/links,
     - created/updated/delivered timestamps.

### 4.2 Backend files likely to change

- `backend/infrastructure/orm/models/operating_models.py`
  - Maybe add fields/indexes to `ServiceDeliverable` only if existing fields are insufficient.
  - Prefer not to add schema until service-level metadata is proven.

- `backend/infrastructure/orm/models/communications.py`
  - Already references `ServiceDeliverable`; likely no schema changes.

- `backend/infrastructure/orm/models/decisions_assets.py`
  - Likely no schema changes; use `Asset`/`AssetVersion`.

- `backend/application/services/operating_model_packs.py`
  - Add/read deliverable definitions from pack manifests if pack-managed.

- `backend/application/services/workstream_phases.py` or equivalent phase service
  - Hook deliverable assembly after phase synthesis/evaluation.

- `backend/application/services/deployment_orchestration.py`
  - Emit launch readiness / execution receipt / connector gap deliverables.

- `backend/application/services/performance_orchestration.py`
  - Emit performance report / optimization roadmap deliverables.

- New: `backend/application/services/agency_deliverables.py`
  - Central assembly/upsert logic.

- New or existing API package:
  - `backend/adapters/api/deliverables/urls.py`
  - `backend/adapters/api/deliverables/views.py`
  - `backend/adapters/api/deliverables/serializers.py`

- Root URL registration file, whichever includes app API modules.

### 4.3 Backend tests to plan

- Unit: deliverable taxonomy maps expected departments/workstreams.
- Unit: assembly is idempotent for same whiteboard/phase.
- Unit: status transitions respect approval state.
- Integration: after phase synthesis/evaluation, expected deliverables exist.
- Integration: after deployment prepare, executed and blocked channels appear in client-readable deliverables.
- Integration: after performance evaluate, performance report and optimization roadmap are ready.
- API/RBAC: viewer can read, admin can assemble/deliver, unrelated org cannot read.

---

## 5. What Needs To Change In Atlas

Atlas is the agency operating-model layer. It needs deliverables encoded in its pack metadata, department responsibilities, prompts, gates, and UI presentation.

### 5.1 Atlas pack metadata

Add a `deliverables` section to `digital_marketing_pro.v1` pack config/manifest:

```json
{
  "deliverables": [
    {
      "type": "client_brief",
      "label": "Client Brief",
      "owner_department": "strategy_research",
      "source_workstreams": ["account_brief_compilation"],
      "visibility": "customer",
      "requires_approval": false,
      "ready_when": ["account_brief_compilation.completed"]
    },
    {
      "type": "strategy_brief",
      "label": "Marketing Strategy Brief",
      "owner_department": "strategy_research",
      "source_workstreams": ["strategy_brief", "media_channel_plan", "traffic_dependency_map"],
      "visibility": "customer",
      "requires_approval": true,
      "ready_when": ["phase_gate.pass"]
    },
    {
      "type": "connector_gap_report",
      "label": "Connector Gap & Production Readiness Report",
      "owner_department": "client_approval_ops",
      "source_contracts": ["deployment_contract"],
      "visibility": "customer",
      "requires_approval": false,
      "ready_when": ["deployment.prepared"]
    }
  ]
}
```

### 5.2 Department responsibilities

Update Atlas department metadata to describe deliverable ownership, not just workflow ownership:

- `strategy_research`: client brief, strategy brief, research summary, GTM plan.
- `brand_content`: message house, copy pack, creative direction, content calendar.
- `channel_execution`: media plan, launch checklist, execution receipts.
- `crm_lifecycle`: segmentation plan, lifecycle journey, consent/data checklist.
- `analytics_performance`: measurement plan, performance report, optimization roadmap.
- `qa_compliance`: claims/compliance memo, QA checklist, risk notes.
- `client_approval_ops`: scope of work, approval packet, approval log, final client package.

### 5.3 Workstream prompts / outputs

Each workstream should stop returning generic “completed” summaries and instead return structured sections usable in deliverables.

Example output contract for a workstream:

```json
{
  "deliverable_sections": [
    {
      "deliverable_type": "strategy_brief",
      "section_id": "channel_rationale",
      "title": "Channel rationale",
      "content_markdown": "...",
      "evidence": ["source:client_brief", "workstream:media_channel_plan"],
      "risk_notes": []
    }
  ],
  "client_summary": "...",
  "internal_notes": "...",
  "handoff_to": ["brand_content", "channel_execution"]
}
```

### 5.4 Gates and approval packets

Atlas should generate a deliberate approval packet before asking the client to approve anything.

Approval packet should include:

- one-page summary,
- exact decision requested,
- list of deliverables included,
- risk classification,
- claims/compliance notes,
- blocked connector disclosures,
- what approval permits and does not permit,
- expiry/re-review conditions.

### 5.5 Final package composition

Atlas should assemble a final package rather than only showing a board state.

Initial package sections:

1. Executive summary.
2. Client brief.
3. Strategy recommendation.
4. Message house and draft copy.
5. Channel/media plan.
6. Launch readiness checklist.
7. Execution receipts and blocked items.
8. Measurement plan.
9. Compliance/approval notes.
10. Next steps / optimization roadmap.

---

## 6. Frontend / Client Experience Changes

Current frontend has `DeliverableVM` in `frontend/domain/translation/viewModels.ts`, but it is operation-centric and preview-based. The Atlas UX should evolve into a deliverables workspace.

### 6.1 Add deliverables tab/section

For company/whiteboard pages:

- “Deliverables” tab with grouped cards:
  - Strategy
  - Creative & Content
  - Launch / Channel Execution
  - CRM / Lifecycle
  - Measurement / Performance
  - Compliance / Approval
  - Final Packages

Each card should show:

- title,
- status,
- owner department,
- approval state,
- updated date,
- evidence count,
- preview,
- CTA: view / download / send for approval / mark delivered.

### 6.2 Client-readable detail view

A deliverable detail page should show:

- rendered Markdown content,
- evidence links,
- version history,
- approval state,
- blocked connector disclosures,
- related board cards/workstreams,
- “copy/share/export” actions.

### 6.3 Package view

A “Client Package” view should bundle multiple deliverables into a single narrative.

Possible routes/components:

- `frontend/app/companies/[companyId]/deliverables/page.tsx`
- `frontend/app/companies/[companyId]/deliverables/[deliverableId]/page.tsx`
- `frontend/app/whiteboards/[whiteboardId]/deliverables/page.tsx`
- `frontend/components/company-workspace/DeliverablesPanel.tsx`
- `frontend/components/company-workspace/DeliverableCard.tsx`
- `frontend/components/company-workspace/DeliverableDetail.tsx`

### 6.4 Frontend tests

- Unit: transform API deliverable payload to `DeliverableVM`.
- Component: render grouped deliverable cards with status/evidence.
- E2E/live: Atlas flow ends with visible client package and detail pages.

---

## 7. Step-by-Step Implementation Plan

### Task 1: Map existing deliverable primitives and APIs

**Objective:** Confirm current Asset/ServiceDeliverable/archive behavior before adding new code.

**Files to inspect:**
- `backend/infrastructure/orm/models/operating_models.py`
- `backend/infrastructure/orm/models/decisions_assets.py`
- `backend/infrastructure/orm/models/communications.py`
- `backend/adapters/api/archive/views.py`
- `backend/application/services/*archive*`

**Output:** short note in implementation PR explaining which primitives are reused and which gaps remain.

### Task 2: Add backend deliverable taxonomy constants

**Objective:** Create a canonical source of deliverable types, labels, departments, and default statuses.

**Likely files:**
- Create: `backend/application/services/agency_deliverable_catalog.py`
- Test: `backend/tests/application/services/test_agency_deliverable_catalog.py`

**Validation:** taxonomy contains all planned deliverable types and each maps to a valid Atlas department slug.

### Task 3: Add pack-level deliverable definitions

**Objective:** Teach `digital_marketing_pro.v1` what deliverables it is expected to produce.

**Likely files:**
- Pack manifest/config file used by `backend/application/services/operating_model_packs.py`.
- Existing pack fixtures/seeds under backend operating-model pack assets.

**Validation:** pack health endpoint includes/accepts deliverable definitions; no checksum/manifest regression.

### Task 4: Add deliverable assembly service

**Objective:** Idempotently create/update `ServiceDeliverable` + `Asset` records from whiteboard state.

**Likely files:**
- Create: `backend/application/services/agency_deliverables.py`
- Tests: `backend/tests/application/services/test_agency_deliverables.py`

**Core functions:**

```python
assemble_phase_deliverables(user, whiteboard, phase_id) -> list[ServiceDeliverable]
assemble_deployment_deliverables(user, whiteboard, policy_id) -> list[ServiceDeliverable]
assemble_performance_deliverables(user, whiteboard, policy_id) -> list[ServiceDeliverable]
assemble_client_package(user, whiteboard) -> ServiceDeliverable
```

**Important:** use deterministic `source_key`/metadata so repeated assembly updates existing assets/deliverables rather than duplicating them.

### Task 5: Add deliverables API

**Objective:** Expose deliverables to frontend and future clients.

**Likely files:**
- Create: `backend/adapters/api/deliverables/urls.py`
- Create: `backend/adapters/api/deliverables/views.py`
- Create: `backend/adapters/api/deliverables/serializers.py`
- Modify root API URL registration.

**Endpoints:**

```text
GET  /api/companies/{company_id}/deliverables
GET  /api/whiteboards/{whiteboard_id}/deliverables
GET  /api/deliverables/{deliverable_id}
POST /api/whiteboards/{whiteboard_id}/deliverables/assemble
POST /api/deliverables/{deliverable_id}/deliver
```

**Validation:** RBAC + idempotency + response schemas.

### Task 6: Wire assembly into whiteboard orchestration

**Objective:** Deliverables appear naturally when the existing flow reaches milestones.

**Likely files:**
- `backend/application/services/workstream_phases.py` or phase orchestration file.
- `backend/application/services/deployment_orchestration.py`
- `backend/application/services/performance_orchestration.py`
- `backend/adapters/api/whiteboards/views.py`

**Milestones:**
- phase synth/evaluate -> strategy/content/QA/approval deliverables,
- approval resolve -> approval log/status update,
- deployment prepare -> launch readiness/execution receipt/connector gap,
- performance report/evaluate -> performance report/optimization roadmap,
- final package assemble -> campaign launch package/post-launch package.

### Task 7: Add frontend API repository and view models

**Objective:** Make deliverables fetchable and renderable.

**Likely files:**
- `frontend/domain/repositories/*deliverable*Repository.ts`
- `frontend/domain/translation/viewModels.ts`
- `frontend/domain/translation/index.ts`
- API client/domain types.

**Validation:** unit tests for mapping payloads to `DeliverableVM` and grouped deliverable sections.

### Task 8: Add deliverables UI

**Objective:** Show client-ready outputs, not just operation status.

**Likely files:**
- Create: `frontend/components/company-workspace/DeliverablesPanel.tsx`
- Create: `frontend/components/company-workspace/DeliverableCard.tsx`
- Create: `frontend/components/company-workspace/DeliverableDetail.tsx`
- Modify company/whiteboard workspace pages.

**Validation:** component tests render deliverables by group/status and show evidence/approval indicators.

### Task 9: Update Atlas live flow tests

**Objective:** Make tests assert client deliverables exist after the flow.

**Likely files:**
- `frontend/__tests__/product-modes-live/atlas-agency-full-flow.e2e.spec.ts`
- `frontend/__tests__/product-modes-live/fixtures.live.ts`
- backend integration tests for deliverables API.

**Assertions:**
- `campaign_launch_package` exists.
- `strategy_brief`, `message_house`, `launch_readiness_checklist`, `connector_gap_report`, `measurement_plan`, `performance_report`, `approval_log` exist.
- blocked connector deliverables are clear and honest.
- at least one deliverable links to execution receipt/tool evidence.
- at least one deliverable links to performance report/metric snapshot.

### Task 10: Add export/share later, not now

**Objective:** Keep first implementation focused.

Out of scope for the first pass:
- PDF export,
- email sending,
- client portal sharing links,
- production connector sending,
- design-polished decks.

Those can be later once canonical deliverables exist.

---

## 8. Recommended MVP Deliverables

For the first implementation, do not build all 25. Build the minimum set that proves the model and maps to the flow Mike already ran:

1. `client_brief`
2. `strategy_brief`
3. `message_house`
4. `launch_readiness_checklist`
5. `connector_gap_report`
6. `measurement_plan`
7. `approval_packet`
8. `execution_receipt`
9. `performance_report`
10. `campaign_launch_package`

Reason: these cover intake, strategy, creative, deployment honesty, approval, measurement, and final package without needing production connectors.

---

## 9. Acceptance Criteria

Planning acceptance:

- [x] Identify typical marketing agency deliverables.
- [x] Map each deliverable to Atlas departments.
- [x] Identify ForgeGraph primitives that can support deliverables.
- [x] Identify ForgeGraph backend/API changes needed.
- [x] Identify Atlas pack/workstream/UI changes needed.
- [x] Keep connector execution out of scope for now.

Implementation acceptance, once approved:

- [ ] Atlas Mkt flow creates at least the 10 MVP deliverables.
- [ ] Deliverables are durable, versioned, customer-visible where appropriate, and linked to evidence.
- [ ] Deliverables are visible through API and frontend.
- [ ] Approval packet and approval log clearly distinguish approved work from blocked recommendations.
- [ ] Final client package summarizes the campaign in client language.
- [ ] Live manual Atlas flow can verify deliverables without Playwright/mocks.

---

## 10. Risks / Open Questions

1. **Asset content storage:** Need to confirm the ArchiveService storage path for generated Markdown content before implementation.
2. **ServiceDeliverable engagement requirement:** `ServiceDeliverable.engagement` is required; implementation must either create/find a `ServiceEngagement` per whiteboard/request or consider loosening this constraint. Prefer creating/finding an engagement.
3. **Pack manifest checksum:** If deliverables live in pack manifests, pack release checksum/update workflow must be respected.
4. **Content generation quality:** First pass can assemble deterministic sections from existing contracts; later pass can use LLM formatting/judging.
5. **Client vs internal visibility:** Some deliverables need operator-only risk notes. Avoid leaking internal reasoning or credentials.
6. **Versioning semantics:** Need clear policy: new version on every re-assemble after material change; no duplicate assets for same source state.
7. **Whiteboard status:** Current flow may remain `in_approval` even after downstream operations; deliverable readiness should depend on contracts/evidence, not only whiteboard status.

---

## 11. Suggested Next Step

If Mike approves implementation, start with the MVP path:

1. Confirm `ServiceEngagement` creation/reuse for a whiteboard.
2. Add deliverable taxonomy constants and tests.
3. Add assembly service for three deliverables first: `client_brief`, `strategy_brief`, `connector_gap_report`.
4. Add API listing endpoint.
5. Verify against the existing live Atlas whiteboard `f3cdf9be-4460-44a0-96f9-4abdb061fedb` in read/write implementation mode.
6. Expand to the remaining MVP deliverables.
