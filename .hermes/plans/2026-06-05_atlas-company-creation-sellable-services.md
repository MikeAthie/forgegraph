# Atlas Company Creation Inside ForgeGraph

> Corrected planning artifact after Mike's clarification: Atlas must **use ForgeGraph and live inside it**. Do not implement until Mike approves a slice. When executing, load `subagent-driven-development`, `test-driven-development`, and `github-pr-workflow`.

## Correction

The previous framing was wrong because it drifted toward a separate Atlas company-creation product/API surface. The right model is the one we had already started:

- Atlas is a **ForgeGraph Company / operating model**, not a separate app layer.
- The existing `Atlas Mkt` Company under `Intuition Labs` is the agency operating company.
- The `digital_marketing_pro.v1` operating-model pack, DepartmentRegistry records, company operating-model versions, service engagements, whiteboards, assets, approvals, and deliverables are the system of record.
- New marketing work should be created as ForgeGraph-native company/engagement/work artifacts that live inside the ForgeGraph company workspace and operating model.

So the implementation should not create a parallel `/api/atlas/companies` namespace as the primary move. It should extend the existing ForgeGraph company creation/setup/onboarding/service-engagement path.

## Earlier plan to resume

Use these existing plans/docs as the source of truth:

1. `.hermes/plans/2026-06-03_161655-atlas-departments-setup.md`
   - Goal: configure `Atlas Mkt` under `Intuition Labs` with organization departments and company operating-model metadata.
   - Key architecture: departments are both durable org-level `DepartmentRegistry` records and company operating-model graph/version metadata.
   - Existing company: `Atlas Mkt` (`bb78a7bc-092c-4c53-85e6-ae6f8f498926`).
   - Existing org: `Intuition Labs` (`3cd7cc65-9bdf-4bc5-b014-d7157c3947db`).

2. `.hermes/plans/2026-06-03_172513-atlas-client-deliverables.md`
   - Goal: shift Atlas toward named, versioned, reviewable client-facing marketing-agency deliverables.
   - Key architecture: compose existing ForgeGraph primitives: `Asset`, `AssetVersion`, `ServiceDeliverable`, communication threads, whiteboard contracts, approvals, report runs, tool executions, and evidence links.

3. `docs/atlas_onboarding.md`
   - Atlas onboarding is a backend-owned ForgeGraph contract.
   - Durable state must not move into frontend, client, engine, event stream, or local files.
   - Existing endpoint: `GET/POST /api/company-ops/atlas-onboarding`.

## Correct product model

### Atlas lives as a ForgeGraph operating company

`Atlas Mkt` should be a real ForgeGraph Company with:

- `company_workspace.v1` profile metadata.
- `digital_marketing_pro.v1` operating-model pack installed.
- organization-level Atlas departments:
  - `strategy_research`
  - `brand_content`
  - `channel_execution`
  - `crm_lifecycle`
  - `analytics_performance`
  - `qa_compliance`
  - `client_approval_ops`
- latest company operating-model version exposing those departments as company workflow nodes.
- backend-owned service/onboarding/deliverable state.

### Client work lives inside ForgeGraph primitives

A marketing engagement should not be an Atlas-only object. It should be represented with existing ForgeGraph resources:

- `Graph` / Company where appropriate.
- `ServiceCatalogItem` for sellable service offers.
- `ServiceEngagement` for a purchased/requested engagement.
- `WorkWhiteboard` for active agent-owned execution context.
- `TaskRoutingRecord` / whiteboard cards for internal agent work packets.
- `ServiceDeliverable` for promised and produced client outputs.
- `Asset` / `AssetVersion` for versioned artifacts.
- `ApprovalTask` / communication records for approval gates.
- `CompanySignal` for connector gaps, risks, and opportunities.

## What company creation should mean now

When we say "company creation (Atlas)", it should mean:

1. Create or verify the ForgeGraph Company that will operate the agency context.
2. Install/verify `digital_marketing_pro.v1` pack on that company.
3. Create/verify Atlas departments at the organization level.
4. Create/update the company operating-model version so Atlas's departments live in the graph.
5. Use existing ForgeGraph APIs to create service engagements, onboarding intake, whiteboards, and deliverables inside that company workspace.
6. Make the company workspace the operator surface for selling and delivering marketing services.

For a prospect/client engagement, the flow should start from existing ForgeGraph APIs:

```text
POST /api/companies/                         # if creating a new ForgeGraph company/account boundary
POST /api/companies/{company_id}/packs/install
POST /api/companies/{company_id}/operating-model-versions
POST /api/company-ops/atlas-onboarding       # create/update onboarding ServiceEngagement
POST /api/service-engagements                # sellable engagement, if not handled by onboarding upsert
POST /api/service-engagements/{id}/deliverables
POST /api/whiteboards/{id}/atlas-deliverables/assemble
```

The productized work should be a ForgeGraph service/helper around these existing contracts, not a separate Atlas app model.

## Correct implementation direction

### PR 1 — Resume Atlas Mkt company setup / verification

**Objective:** Make `Atlas Mkt` itself a complete ForgeGraph agency operating company.

Use the earlier department setup plan.

**Verify/read first:**

```text
GET /api/auth/me
GET /api/orgs/
GET /api/companies/
GET /api/companies/bb78a7bc-092c-4c53-85e6-ae6f8f498926
GET /api/departments/
GET /api/companies/bb78a7bc-092c-4c53-85e6-ae6f8f498926/packs
GET /api/companies/bb78a7bc-092c-4c53-85e6-ae6f8f498926/operating-model-versions/latest
GET /api/system/operating-model-packs/health
```

**Mutate only if missing/stale:**

- install/patch `digital_marketing_pro.v1` pack
- create/patch the 7 Atlas `DepartmentRegistry` records
- create a new company operating-model version with the Atlas department graph/profile

**Acceptance criteria:**

- `Atlas Mkt` has the pack installed.
- all 7 Atlas department slugs exist once and are active.
- latest operating-model version includes those departments in `metadata.company_profile.departments`.
- graph nodes expose the Atlas agency departments.
- no extra non-ForgeGraph Atlas state is introduced.

### PR 2 — Productize sellable service setup inside ForgeGraph

**Objective:** Add a ForgeGraph-native helper/service that creates or upserts a sellable marketing engagement inside existing company/onboarding contracts.

This should probably extend existing services rather than add a new Atlas namespace:

- `backend/application/services/atlas_onboarding.py`
- `backend/application/services/agency_deliverables.py`
- `backend/application/services/service_engagements.py`
- possibly create `backend/application/services/atlas_service_packages.py` for package definitions only

Package definitions can still be useful, but they should feed existing `ServiceCatalogItem`, `ServiceEngagement`, and `ServiceDeliverable` records.

Starter packages:

- `atlas.discovery_to_proposal.v1`
- `atlas.campaign_launch.v1`
- `atlas.monthly_growth_retainer.v1`

### PR 3 — Convert Playwright fixture choreography into real ForgeGraph workflow

**Objective:** Make the e2e flow call the productized ForgeGraph contracts instead of manually composing fake product setup inside test helpers.

Relevant source:

- `frontend/__tests__/product-modes-live/atlas-agency-full-flow.e2e.spec.ts`
- `frontend/__tests__/product-modes-live/fixtures.live.ts`

The test should prove that the real ForgeGraph Company + pack + departments + onboarding + engagement + deliverable path works.

## Digital Marketing Pro translation, corrected

DMP is inspiration for what Atlas should sell and produce; it is not architecture.

Translate it into ForgeGraph like this:

- DMP brand profile -> ForgeGraph company profile / onboarding intake / account context asset.
- DMP engagement workflow -> ForgeGraph `ServiceEngagement` + `WorkWhiteboard` + routing tasks.
- DMP proposal/SOW -> `ServiceDeliverable` + `AssetVersion` attached to a service engagement.
- DMP campaign plan -> Atlas deliverable package generated from whiteboard/engagement state.
- DMP client report -> recurring `ReportRun` / `ServiceDeliverable`.
- DMP client validation -> `ApprovalTask` / communication thread / service engagement status.

## Non-goals

- Do not create a separate Atlas object model outside ForgeGraph.
- Do not make Atlas a frontend-only wizard.
- Do not make `/api/atlas/companies` the primary architecture.
- Do not bypass `Graph`/Company, operating-model packs, department registry, service engagements, whiteboards, assets, approvals, or deliverables.
- Do not treat connector gaps as blockers to planning deliverables; they become explicit gap reports and readiness state.

## Strong recommendation

Resume from the earlier ForgeGraph-native plan:

1. finish/verify `Atlas Mkt` as the agency Company inside ForgeGraph;
2. use `digital_marketing_pro.v1` + departments + operating-model version as the agency operating system;
3. layer sellable service packages into existing `ServiceCatalogItem` / `ServiceEngagement` / `ServiceDeliverable` / whiteboard contracts;
4. only then adjust frontend and Playwright to use this real ForgeGraph path.
