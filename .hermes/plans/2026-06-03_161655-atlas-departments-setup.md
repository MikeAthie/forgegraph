# Atlas Department Setup Implementation Plan

> **For Hermes:** Use this plan before mutating Atlas Mkt. This plan is intentionally non-mutating; implementation should happen only after Mike approves the plan.

**Goal:** Configure Atlas Mkt under Intuition Labs with the organization-level departments and company operating-model metadata needed for the Atlas agency full-flow to work repeatably.

**Architecture:** Treat departments as two related layers: (1) durable organization department registry records via `/api/departments/`, and (2) the company operating model graph/version metadata that exposes departments as company workflow nodes. Install/verify the `digital_marketing_pro.v1` operating model pack because the Playwright flow depends on its agency work graph, deployment policy, performance policy, judge profiles, connector config, and generated team roles.

**Tech Stack:** Local ForgeGraph backend on port `8000`, authenticated direct HTTP API calls with bearer token from `C:/Users/mathi/AppData/Local/Temp/forgegraph-atlas-live/session.json`, Django/DRF endpoints, Graph/GraphVersion-backed company storage.

---

## Current Context

- Organization already exists: `Intuition Labs` (`3cd7cc65-9bdf-4bc5-b014-d7157c3947db`).
- Company already exists: `Atlas Mkt` (`bb78a7bc-092c-4c53-85e6-ae6f8f498926`).
- The Playwright test source of truth is `frontend/__tests__/product-modes-live/atlas-agency-full-flow.e2e.spec.ts`.
- Relevant helper/model code inspected:
  - `frontend/lib/company-workspace.ts`
  - `frontend/__tests__/product-modes-live/fixtures.live.ts`
  - `backend/adapters/api/departments/views.py`
  - `backend/adapters/api/companies/views.py`
  - `backend/adapters/api/operating_models/urls.py`
- The department registry API requires `IsAuthenticated` and organization-level `admin` or higher for creation. The current user is org owner, so expected to pass.
- Existing `/api/companies/` company alias is backed by `Graph`; operating model versions can be created via `/api/companies/{company_id}/operating-model-versions` or `/api/graphs/{graph_id}/versions`.

## Department Set From The Playwright Flow

Create/verify these Atlas agency departments at organization level and represent them in the Atlas Mkt company profile/graph.

| Slug / Subject ID | Label | Why it is required |
|---|---|---|
| `strategy_research` | Strategy & Research | Required by department judge profile and final board lane; owns problem framing, evidence discipline, targeting/positioning, constraints, downstream usefulness. |
| `brand_content` | Brand & Content | Required by department judge profile and final board lane; owns message clarity, brand fit, creative assets, claim discipline. |
| `channel_execution` | Channel Execution | Required by department judge profile and final board lane; owns launch readiness, sequencing, connector honesty, approval compliance. |
| `crm_lifecycle` | CRM & Lifecycle | Required by department judge profile; owns segmentation, consent/customer safety, lifecycle handoff, measurement tie-in. |
| `analytics_performance` | Analytics & Performance | Required by department judge profile and final board lane; owns KPIs, baselines/targets, attribution realism, optimization loop. |
| `qa_compliance` | QA & Compliance | Required by department judge profile and final board lane; owns claim verification, risk identification, gate enforcement, client safety. |
| `client_approval_ops` | Client/Approval Ops | Required by department judge profile and final board lane; owns approval traceability and client-ready communication. |

Notes:
- The test’s final board assertion requires lanes containing: `strategy_research`, `qa_compliance`, `channel_execution`, `brand_content`, `analytics_performance`, `client_approval_ops`.
- The judge profiles also include `crm_lifecycle`, so include it even if the board assertion does not explicitly require it.
- The operating model pack separately seeds team roles such as `brand_manager`, `strategist`, `researcher`, `content_lead`, `copywriter`, `media_buyer`, `crm_specialist`, `analyst`, `qa_compliance`, `approver`, and `client_stakeholder`. Do not confuse those roles with the higher-level department registry records.

## Proposed Implementation Steps

### Task 1: Snapshot current Atlas state

**Objective:** Avoid duplicate departments or accidental overwrites.

**Read-only API calls:**

```bash
GET /api/auth/me
GET /api/orgs/
GET /api/companies/
GET /api/companies/bb78a7bc-092c-4c53-85e6-ae6f8f498926
GET /api/departments/
GET /api/companies/bb78a7bc-092c-4c53-85e6-ae6f8f498926/operating-model-versions/latest
GET /api/companies/bb78a7bc-092c-4c53-85e6-ae6f8f498926/packs
GET /api/system/operating-model-packs/health
```

**Expected:**
- Authenticated user can read org/company.
- Pack health status is `ok`, contains `digital_marketing_pro`, and has no missing required packs/contents.
- Record existing departments by slug so implementation can upsert instead of blindly creating.

### Task 2: Install or verify the digital marketing operating model pack

**Objective:** Ensure Atlas Mkt has the package that powers the agency work graph, launch deployment, performance review, connector setup, judge profiles, and team roles.

**API:**

```bash
GET /api/companies/bb78a7bc-092c-4c53-85e6-ae6f8f498926/packs
POST /api/companies/bb78a7bc-092c-4c53-85e6-ae6f8f498926/packs/install
```

**Install payload if missing:**

```json
{
  "pack_id": "digital_marketing_pro.v1",
  "role": "primary",
  "config_overrides": {
    "available_connectors": [
      "email_connector",
      "social_connector",
      "analytics_connector",
      "whatsapp_connector",
      "social_analytics_connector"
    ]
  }
}
```

**If already installed:** patch/update only if connector availability is missing.

**Expected verification:**
- `GET /api/companies/{company_id}/packs` returns a `digital_marketing_pro.v1` installation, preferably `role: primary`.
- Public/config contains expected sandbox connectors.
- Pack-generated team roles are present if exposed by pack objects endpoint.

### Task 3: Create missing organization DepartmentRegistry records

**Objective:** Create durable org-level departments that Atlas can reuse across companies.

**API:**

```bash
GET /api/departments/
POST /api/departments/
PATCH /api/departments/{department_id}
```

**Payload template:**

```json
{
  "slug": "strategy_research",
  "name": "Strategy & Research",
  "department_type": "agency_department",
  "service_tags": ["atlas", "digital_marketing_pro", "strategy", "research"],
  "active": true,
  "metadata": {
    "source": "atlas-agency-full-flow.e2e.spec.ts",
    "company_id": "bb78a7bc-092c-4c53-85e6-ae6f8f498926",
    "subject_id": "strategy_research",
    "operating_model_pack_id": "digital_marketing_pro.v1"
  }
}
```

**Exact department metadata plan:**

1. `strategy_research` / `Strategy & Research` / tags: `atlas`, `digital_marketing_pro`, `strategy`, `research`
2. `brand_content` / `Brand & Content` / tags: `atlas`, `digital_marketing_pro`, `brand`, `content`, `creative`
3. `channel_execution` / `Channel Execution` / tags: `atlas`, `digital_marketing_pro`, `channels`, `launch`, `connectors`
4. `crm_lifecycle` / `CRM & Lifecycle` / tags: `atlas`, `digital_marketing_pro`, `crm`, `lifecycle`, `consent`
5. `analytics_performance` / `Analytics & Performance` / tags: `atlas`, `digital_marketing_pro`, `analytics`, `performance`, `measurement`
6. `qa_compliance` / `QA & Compliance` / tags: `atlas`, `digital_marketing_pro`, `qa`, `compliance`, `risk`
7. `client_approval_ops` / `Client/Approval Ops` / tags: `atlas`, `digital_marketing_pro`, `client`, `approval`, `ops`

**Conflict handling:**
- If POST returns `409 DEPARTMENT_SLUG_CONFLICT`, re-read `/api/departments/`, find the slug, and PATCH it with the desired fields instead of creating duplicates.

### Task 4: Create or update Atlas Mkt operating model version with department nodes

**Objective:** Make the company workspace itself reflect the Atlas department model, not just org-level records.

**Preferred graph shape:** Use a `company_workspace.v1` metadata profile plus a simple DAG of agent department nodes and final output, following `frontend/lib/company-workspace.ts::buildCompanyGraphJson`.

**Company profile metadata:**

```json
{
  "schema": "company_workspace.v1",
  "companyName": "Atlas Mkt",
  "companyType": "Growth & Marketing Agency",
  "objective": "Operate an Atlas-style digital marketing agency that can turn client campaign requests into strategy, content, approval, deployment evidence, performance review, and optimization recommendations.",
  "autonomyMode": "assisted",
  "aiAccessMode": "managed",
  "intelligenceProvider": "openai",
  "companyStatus": "Ready to launch",
  "departments": [
    { "id": "strategy_research", "label": "Strategy & Research", "responsibility": "Frames the client problem, gathers evidence, defines targeting and positioning, and produces downstream-ready strategy constraints.", "tools": ["Research synthesis", "Campaign planning", "Positioning"], "category": "department" },
    { "id": "brand_content", "label": "Brand & Content", "responsibility": "Translates strategy into message houses, channel-ready content plans, claim-safe copy, and creative direction.", "tools": ["Messaging", "Creative review", "Content planning"], "category": "department" },
    { "id": "channel_execution", "label": "Channel Execution", "responsibility": "Turns approved plans into channel execution readiness, sequencing, connector evidence, and launch handoffs.", "tools": ["Connector readiness", "Launch sequencing", "Sandbox execution"], "category": "department" },
    { "id": "crm_lifecycle", "label": "CRM & Lifecycle", "responsibility": "Owns segmentation, consent-aware customer lifecycle planning, lifecycle handoffs, and CRM measurement tie-ins.", "tools": ["Segmentation", "Consent review", "Lifecycle planning"], "category": "department" },
    { "id": "analytics_performance", "label": "Analytics & Performance", "responsibility": "Defines KPIs, baselines, targets, attribution assumptions, performance reports, and optimization loops.", "tools": ["Performance analysis", "Measurement planning", "Reporting"], "category": "department" },
    { "id": "qa_compliance", "label": "QA & Compliance", "responsibility": "Verifies claims, identifies risks, enforces gates, and blocks unsafe or unsupported client work.", "tools": ["Quality assurance", "Risk checks", "Claim verification"], "category": "department" },
    { "id": "client_approval_ops", "label": "Client/Approval Ops", "responsibility": "Packages client-ready briefs, manages stakeholder approvals, records approval traceability, and coordinates client-safe communication.", "tools": ["Client communication", "Approval routing", "Handoffs"], "category": "department" }
  ],
  "skills": [
    "Campaign planning",
    "Research synthesis",
    "Messaging",
    "Creative review",
    "Connector readiness",
    "Performance analysis",
    "Quality assurance",
    "Client communication"
  ]
}
```

**API options:**

```bash
POST /api/companies/bb78a7bc-092c-4c53-85e6-ae6f8f498926/operating-model-versions
# or
POST /api/graphs/bb78a7bc-092c-4c53-85e6-ae6f8f498926/versions
```

**Validation expectations:**
- Top-level graph JSON includes `nodes` and `edges`.
- Node ids are unique.
- Edges include `START -> first department`, serial department handoffs, `last department -> final_deliverable`, `final_deliverable -> END`.
- `GraphValidator.validate(..., require_entry_exit=False)` accepts it.

### Task 5: Verify department availability in backend-owned Atlas flow

**Objective:** Prove the setup is sufficient before starting the full expensive flow.

**Verification calls:**

```bash
GET /api/departments/
GET /api/companies/bb78a7bc-092c-4c53-85e6-ae6f8f498926/operating-model-versions/latest
GET /api/companies/bb78a7bc-092c-4c53-85e6-ae6f8f498926/operating-model
GET /api/companies/bb78a7bc-092c-4c53-85e6-ae6f8f498926/packs
```

**Expected assertions:**
- All 7 department slugs exist and are active.
- Latest company profile contains all 7 department IDs.
- Graph nodes include all 7 department labels.
- Pack `digital_marketing_pro.v1` is installed with expected connectors.
- No `Legacy Eyewear` or function-company artifacts are created during department setup.

### Task 6: Save reusable Hermes skill after first verified implementation

**Objective:** Preserve the exact endpoint sequence and payload conventions once the live implementation is proven.

**Skill name:** `forgegraph-company-setup`

**Category:** `software-development` or user-local default category.

**Trigger:** Use when creating or updating ForgeGraph organizations, companies, departments, company operating-model versions, and operating-model pack installations via direct API calls.

**Skill should include:**
- How to load session token safely from `C:/Users/mathi/AppData/Local/Temp/forgegraph-atlas-live/session.json` without printing it.
- Required order: auth -> org -> company -> packs -> departments -> graph version -> verification.
- Idempotency rules: GET first, POST missing resources, PATCH conflicts, never duplicate slugs.
- Endpoint list and sample payloads.
- Verification checklist.
- Pitfalls: department API requires org admin; companies are Graph-backed; pack roles are not department records; current session cannot see newly created skills until refreshed.

**Reason not to create it before implementation:** creating it after the verified run avoids baking in untested payload shapes or endpoint assumptions.

## Risks / Open Questions

1. **API payload shape for pack install may need adjustment.** Confirm serializer fields and actual accepted payload before POST.
2. **DepartmentRegistry may be global to organization, not company-scoped.** Store `company_id` only as metadata, not as ownership semantics.
3. **Whiteboard lanes may be generated by the operating model pack rather than company graph metadata.** We still need both: pack for runtime policies and company profile for workspace/team setup.
4. **Current Atlas Mkt may already have an operating model version.** Preserve existing metadata and append/replace department profile carefully rather than overwriting unrelated useful fields.
5. **CRM lane is judge-required but not final-board-asserted.** Include it in setup; if the pack creates no CRM board lane, that is acceptable as long as judges and department registry can reference it.

## Implementation Acceptance Criteria

- All 7 Atlas department slugs are present and active in `/api/departments/`.
- Atlas Mkt latest operating model version contains all 7 department IDs in `metadata.company_profile.departments`.
- Atlas Mkt pack list contains `digital_marketing_pro.v1` with sandbox connector availability.
- A verification JSON file is written under `C:/Users/mathi/AppData/Local/Temp/forgegraph-atlas-live/` with department IDs, company version ID, pack installation ID, and timestamps.
- After successful verification, create the `forgegraph-company-setup` skill so future org/company/department setup is faster and less error-prone.
