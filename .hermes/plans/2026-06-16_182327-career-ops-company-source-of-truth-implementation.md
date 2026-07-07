# CareerOps ForgeGraph Company Source-of-Truth Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Implement a ForgeGraph-native CareerOps company whose departments, stages, agents, responsibilities, records, and deliverables are governed by the Mermaid company graph we created.

**Architecture:** Treat the Mermaid graph as the product source of truth for the first implementation slice. Promote it into the repo as a versioned graph contract, implement `career_ops.v1` as an operating-model pack that mirrors the graph exactly, then add backend services that create and operate a CareerOps company through existing ForgeGraph primitives (`Graph`, `CompanyProgram`, `ProgramStageState`, `CompanySignal`, `CompanyOpportunity`, `StateProjection`, `AssetVersion`, `ServiceEngagement`, `ServiceDeliverable`, `Run`, and `ToolExecution`). The first working version should create one seeded CareerOps company with one fake job opportunity flowing from scan -> liveness -> evaluation -> application packet -> approval gate, without any live scraping or auto-apply side effects.

**Tech Stack:** Django/Python backend, ForgeGraph operating-model packs, YAML manifests, pytest, ruff, existing company blueprint APIs, existing service/deliverable primitives, optional Mermaid docs for Excalidraw visualization.

**Scope lock:** See `.hermes/plans/2026-06-16_183620-career-ops-clear-scope.md`. The week-one product goal is **one interview**, so the P0 scope is URL-to-evaluation-to-quality-gated-packet-to-manual-submit. Full portal scanner coverage, dashboard TUI, and batch worker farm are explicitly deferred until this loop works.

**Native platform contract:** See `.hermes/plans/2026-06-16_190000-career-ops-native-forgegraph-contract.md`. Implement CareerOps as native ForgeGraph workflows/executions/tasks/decisions/memory/accounting/artifacts/projections, not as a copied local-file CLI.

---

## Non-negotiable source-of-truth rule

The graph file is the implementation contract:

```text
C:\Users\mathi\projects\forgegraph\.hermes\plans\career_ops_company_graph.mmd
```

During implementation, promote this file into the repo as:

```text
docs/operating-model-packs/career-ops-company-graph.mmd
```

Every implementation task below must preserve the graph contract:

1. **Departments:** exactly 8 departments from `D1`-`D8`.
2. **Program stages:** exactly 12 stages from `S01`-`S12`.
3. **Durable state:** candidate profile, positioning, CV, proof points, pipeline snapshot, and story bank are backend-owned records.
4. **Core records:** scan/evaluation/rendering operations create ForgeGraph records, not local markdown source-of-truth files.
5. **Deliverables:** the MVP deliverables in the graph exist as pack artifact schemas and/or service deliverable definitions.
6. **Governance:** candidate approval gate blocks unsafe external side effects; no auto-apply.
7. **Feedback loops:** pipeline review feeds search strategy; learning update feeds candidate profile, positioning, and story bank.

If the graph changes, implementation must change in the same PR. Do not let pack YAML, services, tests, or docs drift away from the graph.

---

## Graph contract extracted from the Mermaid source

### Company

```yaml
pack_id: career_ops.v1
base_pack_id: career_ops
display_name: Career Operations
company_type_label: Career Operations Company
workspace_label: CareerOps Workspace
```

### Backend-owned durable state

| Mermaid node | ForgeGraph primitive | Projection/artifact key |
| --- | --- | --- |
| `PROFILE` | `StateProjection` | `career_ops:candidate_profile` |
| `POSITIONING` | `StateProjection` | `career_ops:career_positioning` |
| `CV` | `Asset` / `AssetVersion` | `cv_source` |
| `PROOF` | `Asset` / `AssetVersion` | `proof_point_digest` |
| `PIPELINE` | `StateProjection` | `career_ops:pipeline_snapshot` |
| `STORYBANK` | `Asset` / `AssetVersion` | `interview_story_bank` |

### Departments

| ID | Slug | Label | Owns stages |
| --- | --- | --- | --- |
| `D1` | `candidate_profile_strategy` | Candidate Profile & Strategy | `S01`, `S02`, `S12` |
| `D2` | `market_role_discovery` | Market & Role Discovery | `S03`, `S04` |
| `D3` | `opportunity_evaluation` | Opportunity Evaluation | `S05` |
| `D4` | `application_packet_studio` | Application Packet Studio | `S06` |
| `D5` | `application_operations` | Application Operations | `S08` |
| `D6` | `interview_negotiation_prep` | Interview & Negotiation Prep | `S09`, `S10` |
| `D7` | `pipeline_integrity_analytics` | Pipeline Integrity & Analytics | `S11` |
| `D8` | `candidate_approval_governance` | Candidate Approval & Governance | `S07` |

### Program stages

| ID | Stage slug | Label | Owner department | Required output |
| --- | --- | --- | --- | --- |
| `S01` | `stage_01_candidate_onboarding` | Candidate onboarding | `candidate_profile_strategy` | profile + CV + proof-point state |
| `S02` | `stage_02_search_strategy` | Search strategy | `candidate_profile_strategy` | target role strategy |
| `S03` | `stage_03_market_scan` | Market scan | `market_role_discovery` | scanned lead signals |
| `S04` | `stage_04_liveness_and_dedupe` | Liveness and dedupe | `market_role_discovery` | liveness receipt + deduped opportunity |
| `S05` | `stage_05_fit_evaluation` | Fit evaluation | `opportunity_evaluation` | A-G evaluation report |
| `S06` | `stage_06_application_packet` | Application packet | `application_packet_studio` | application packet deliverables |
| `S07` | `stage_07_candidate_approval` | Candidate approval gate | `candidate_approval_governance` | approval/block decision |
| `S08` | `stage_08_submission_tracking` | Submission tracking | `application_operations` | application status update |
| `S09` | `stage_09_interview_prep` | Interview prep | `interview_negotiation_prep` | interview prep brief |
| `S10` | `stage_10_followup_negotiation` | Follow-up and negotiation | `interview_negotiation_prep` | follow-up plan / negotiation script |
| `S11` | `stage_11_pipeline_review` | Pipeline review | `pipeline_integrity_analytics` | pipeline health report |
| `S12` | `stage_12_learning_update` | Learning update | `candidate_profile_strategy` | updated profile/positioning/story bank |

### MVP deliverables

```text
job_liveness_receipt
job_evaluation_report
tailored_resume_pdf
cover_letter_draft
cover_letter_pdf
application_answers
application_packet
company_interview_prep
followup_plan
pipeline_health_report
```

---

## Implementation strategy

Build in four PR-sized vertical slices:

1. **Graph contract + pack compile:** make `career_ops.v1` compile and prove it mirrors the graph.
2. **Company creation + seed:** create a real ForgeGraph company from the pack and seed backend-owned state/records.
3. **CareerOps services:** add deterministic services for onboarding, scan normalization, liveness, evaluation, deliverable assembly, and approval gating using fake fixtures.
4. **Pipeline read model + smoke operation:** expose the backend-owned pipeline state and run one end-to-end fake opportunity through the operating loop.

Do **not** start with live portal scraping, PDF polish, or frontend UI. The first acceptance target is a backend-owned company and one verifiable fake job run matching the graph.

---

# Phase 0: Preserve the graph as source of truth

## Task 0.1: Promote Mermaid graph into repo docs

**Objective:** Move the graph from `.hermes/plans` into a repo path that implementation/tests can reference.

**Files:**
- Create: `docs/operating-model-packs/career-ops-company-graph.mmd`
- Create: `docs/operating-model-packs/career-ops.md`

**Step 1: Copy the Mermaid graph**

Copy the current contents of:

```text
.hermes/plans/career_ops_company_graph.mmd
```

into:

```text
docs/operating-model-packs/career-ops-company-graph.mmd
```

**Step 2: Create the documentation wrapper**

Create `docs/operating-model-packs/career-ops.md` with:

```markdown
# Career Operations Operating Model Pack

`career_ops.v1` turns ForgeGraph into a backend-owned career operations company.

The source-of-truth company graph is:

```text
docs/operating-model-packs/career-ops-company-graph.mmd
```

Every department, stage, durable record, and deliverable in the pack must map to the Mermaid graph.

## Runtime invariant

ForgeGraph backend state is authoritative. Local files, Mermaid diagrams, worker memory, and events are documentation/execution aids only; durable career search state is stored in ForgeGraph backend records.
```

**Step 3: Verify file is readable**

Run:

```bash
cd /c/Users/mathi/projects/forgegraph
python - <<'PY'
from pathlib import Path
p = Path('docs/operating-model-packs/career-ops-company-graph.mmd')
text = p.read_text(encoding='utf-8')
assert 'CareerOps Workspace' in text
assert 'Candidate Approval and Governance Agent' in text
print('career-ops graph doc ok')
PY
```

Expected: `career-ops graph doc ok`.

---

## Task 0.2: Add a machine-checkable graph contract module

**Objective:** Give tests and services a single Python contract derived from the Mermaid graph so pack YAML and services cannot drift.

**Files:**
- Create: `backend/application/services/career_ops_graph_contract.py`
- Create: `backend/tests/unit/services/test_career_ops_graph_contract.py`

**Step 1: Write failing test**

Create `backend/tests/unit/services/test_career_ops_graph_contract.py`:

```python
from __future__ import annotations

from application.services.career_ops_graph_contract import (
    CAREER_OPS_DEPARTMENTS,
    CAREER_OPS_DELIVERABLE_TYPES,
    CAREER_OPS_DURABLE_STATE_KEYS,
    CAREER_OPS_STAGE_SEQUENCE,
    CAREER_OPS_STAGE_TO_DEPARTMENT,
)


def test_career_ops_graph_contract_matches_mermaid_source_of_truth() -> None:
    assert len(CAREER_OPS_DEPARTMENTS) == 8
    assert len(CAREER_OPS_STAGE_SEQUENCE) == 12
    assert CAREER_OPS_STAGE_SEQUENCE[0] == "stage_01_candidate_onboarding"
    assert CAREER_OPS_STAGE_SEQUENCE[-1] == "stage_12_learning_update"
    assert CAREER_OPS_STAGE_TO_DEPARTMENT["stage_07_candidate_approval"] == (
        "candidate_approval_governance"
    )
    assert "application_packet" in CAREER_OPS_DELIVERABLE_TYPES
    assert "career_ops:candidate_profile" in CAREER_OPS_DURABLE_STATE_KEYS
```

**Step 2: Run test to verify failure**

Run from `backend/`:

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest tests/unit/services/test_career_ops_graph_contract.py -q
```

Expected: FAIL because `career_ops_graph_contract.py` does not exist.

**Step 3: Implement contract module**

Create `backend/application/services/career_ops_graph_contract.py`:

```python
"""CareerOps graph contract derived from docs/operating-model-packs/career-ops-company-graph.mmd."""

from __future__ import annotations

CAREER_OPS_PACK_ID = "career_ops.v1"
CAREER_OPS_BASE_PACK_ID = "career_ops"
CAREER_OPS_COMPANY_TYPE_LABEL = "Career Operations Company"

CAREER_OPS_DEPARTMENTS: tuple[dict[str, object], ...] = (
    {
        "slug": "candidate_profile_strategy",
        "label": "Candidate Profile & Strategy",
        "responsibilities": (
            "Own CV, target roles, constraints, positioning, and proof points.",
            "Maintain candidate profile and source-of-truth career positioning.",
        ),
    },
    {
        "slug": "market_role_discovery",
        "label": "Market & Role Discovery",
        "responsibilities": (
            "Scan job sources cheaply before expensive agent work.",
            "Normalize, filter, and dedupe job leads with source receipts.",
        ),
    },
    {
        "slug": "opportunity_evaluation",
        "label": "Opportunity Evaluation",
        "responsibilities": (
            "Score fit, legitimacy, compensation, and apply/no-apply recommendations.",
            "Produce A-G evaluation reports backed by evidence.",
        ),
    },
    {
        "slug": "application_packet_studio",
        "label": "Application Packet Studio",
        "responsibilities": (
            "Produce truthful tailored resumes, cover letters, and application answers.",
            "Maintain ATS, PDF, packet manifest, and artifact quality.",
        ),
    },
    {
        "slug": "application_operations",
        "label": "Application Operations",
        "responsibilities": (
            "Track application status, next actions, follow-ups, and receipts.",
            "Coordinate submission readiness after candidate approval.",
        ),
    },
    {
        "slug": "interview_negotiation_prep",
        "label": "Interview & Negotiation Prep",
        "responsibilities": (
            "Build reusable STAR+Reflection story bank.",
            "Prepare company-specific interview and negotiation briefs.",
        ),
    },
    {
        "slug": "pipeline_integrity_analytics",
        "label": "Pipeline Integrity & Analytics",
        "responsibilities": (
            "Keep the pipeline trustworthy through dedupe and artifact checks.",
            "Report conversion, stale follow-ups, and score calibration feedback.",
        ),
    },
    {
        "slug": "candidate_approval_governance",
        "label": "Candidate Approval & Governance",
        "responsibilities": (
            "Enforce human-in-the-loop approval before external side effects.",
            "Prevent auto-apply, false claims, privacy leaks, and invented experience.",
        ),
    },
)

CAREER_OPS_STAGE_SEQUENCE: tuple[str, ...] = (
    "stage_01_candidate_onboarding",
    "stage_02_search_strategy",
    "stage_03_market_scan",
    "stage_04_liveness_and_dedupe",
    "stage_05_fit_evaluation",
    "stage_06_application_packet",
    "stage_07_candidate_approval",
    "stage_08_submission_tracking",
    "stage_09_interview_prep",
    "stage_10_followup_negotiation",
    "stage_11_pipeline_review",
    "stage_12_learning_update",
)

CAREER_OPS_STAGE_LABELS: dict[str, str] = {
    "stage_01_candidate_onboarding": "Candidate onboarding",
    "stage_02_search_strategy": "Search strategy",
    "stage_03_market_scan": "Market scan",
    "stage_04_liveness_and_dedupe": "Liveness and dedupe",
    "stage_05_fit_evaluation": "Fit evaluation",
    "stage_06_application_packet": "Application packet",
    "stage_07_candidate_approval": "Candidate approval gate",
    "stage_08_submission_tracking": "Submission tracking",
    "stage_09_interview_prep": "Interview prep",
    "stage_10_followup_negotiation": "Follow-up and negotiation",
    "stage_11_pipeline_review": "Pipeline review",
    "stage_12_learning_update": "Learning update",
}

CAREER_OPS_STAGE_TO_DEPARTMENT: dict[str, str] = {
    "stage_01_candidate_onboarding": "candidate_profile_strategy",
    "stage_02_search_strategy": "candidate_profile_strategy",
    "stage_03_market_scan": "market_role_discovery",
    "stage_04_liveness_and_dedupe": "market_role_discovery",
    "stage_05_fit_evaluation": "opportunity_evaluation",
    "stage_06_application_packet": "application_packet_studio",
    "stage_07_candidate_approval": "candidate_approval_governance",
    "stage_08_submission_tracking": "application_operations",
    "stage_09_interview_prep": "interview_negotiation_prep",
    "stage_10_followup_negotiation": "interview_negotiation_prep",
    "stage_11_pipeline_review": "pipeline_integrity_analytics",
    "stage_12_learning_update": "candidate_profile_strategy",
}

CAREER_OPS_DURABLE_STATE_KEYS: tuple[str, ...] = (
    "career_ops:candidate_profile",
    "career_ops:career_positioning",
    "career_ops:cv_source",
    "career_ops:proof_point_digest",
    "career_ops:pipeline_snapshot",
    "career_ops:interview_story_bank",
)

CAREER_OPS_DELIVERABLE_TYPES: tuple[str, ...] = (
    "job_liveness_receipt",
    "job_evaluation_report",
    "tailored_resume_pdf",
    "cover_letter_draft",
    "cover_letter_pdf",
    "application_answers",
    "application_packet",
    "company_interview_prep",
    "followup_plan",
    "pipeline_health_report",
)
```

**Step 4: Verify pass**

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest tests/unit/services/test_career_ops_graph_contract.py -q
```

Expected: PASS.

---

# Phase 1: Implement the `career_ops.v1` operating-model pack

## Task 1.1: Create pack YAML files from the graph contract

**Objective:** Add a compileable `career_ops.v1` pack that mirrors departments, stages, and deliverables from the graph.

**Files:**
- Create: `operating_model_packs/career_ops/manifest.yml`
- Create: `operating_model_packs/career_ops/departments.yml`
- Create: `operating_model_packs/career_ops/agents.yml`
- Create: `operating_model_packs/career_ops/programs.yml`
- Create: `operating_model_packs/career_ops/stages.yml`
- Create: `operating_model_packs/career_ops/artifacts.yml`
- Create: `operating_model_packs/career_ops/operations.yml`
- Create: `operating_model_packs/career_ops/evaluations.yml`
- Create: `operating_model_packs/career_ops/policies.yml`
- Create: `operating_model_packs/career_ops/tools.yml`
- Create: `operating_model_packs/career_ops/signals.yml`
- Create: `operating_model_packs/career_ops/dashboards.yml`
- Create: `operating_model_packs/career_ops/reports.yml`
- Test: `backend/tests/unit/services/test_career_ops_pack.py`

**Step 1: Write failing pack tests**

Create `backend/tests/unit/services/test_career_ops_pack.py`:

```python
from __future__ import annotations

from application.services.career_ops_graph_contract import (
    CAREER_OPS_COMPANY_TYPE_LABEL,
    CAREER_OPS_DEPARTMENTS,
    CAREER_OPS_DELIVERABLE_TYPES,
    CAREER_OPS_PACK_ID,
    CAREER_OPS_STAGE_LABELS,
    CAREER_OPS_STAGE_SEQUENCE,
    CAREER_OPS_STAGE_TO_DEPARTMENT,
)
from application.services.operating_model_packs import compile_pack, load_pack_definition
from domain.services.graph_validator import GraphValidator


def test_career_ops_pack_loads_and_compiles_valid_graph_json() -> None:
    definition = load_pack_definition(CAREER_OPS_PACK_ID)

    assert definition.base_pack_id == "career_ops"
    assert definition.company_type_label == CAREER_OPS_COMPANY_TYPE_LABEL

    compiled = compile_pack(
        pack_id=CAREER_OPS_PACK_ID,
        company_name="Candidate CareerOps",
        objective="Run a selective evidence-backed job search.",
        autonomy_mode="assisted",
        ai_access_mode="managed",
        intelligence_provider="openai",
        selected_services=["job evaluation", "application packets"],
        regions=["remote"],
    )

    assert GraphValidator().validate(compiled.graph_json, strict=True, require_entry_exit=True) == []
    assert compiled.graph_json["metadata"]["operating_model_pack"]["pack_id"] == CAREER_OPS_PACK_ID
    assert compiled.graph_json["metadata"]["company_profile"]["companyType"] == (
        CAREER_OPS_COMPANY_TYPE_LABEL
    )


def test_career_ops_pack_departments_match_graph_contract() -> None:
    compiled = compile_pack(
        pack_id=CAREER_OPS_PACK_ID,
        company_name="Candidate CareerOps",
        objective="Run a selective evidence-backed job search.",
        autonomy_mode="assisted",
        ai_access_mode="managed",
        intelligence_provider="openai",
        selected_services=[],
        regions=[],
    )
    profile_departments = compiled.graph_json["metadata"]["company_profile"]["departments"]

    assert [item["id"] for item in profile_departments] == [
        str(item["slug"]) for item in CAREER_OPS_DEPARTMENTS
    ]
    assert [item["label"] for item in profile_departments] == [
        str(item["label"]) for item in CAREER_OPS_DEPARTMENTS
    ]


def test_career_ops_pack_program_stages_match_graph_contract() -> None:
    definition = load_pack_definition(CAREER_OPS_PACK_ID)
    stages = definition.files["stages"]["stages"]

    assert [stage["id"] for stage in stages] == list(CAREER_OPS_STAGE_SEQUENCE)
    assert {stage["id"]: stage["label"] for stage in stages} == CAREER_OPS_STAGE_LABELS
    assert {stage["id"]: stage["owner_department_slug"] for stage in stages} == (
        CAREER_OPS_STAGE_TO_DEPARTMENT
    )


def test_career_ops_artifacts_include_graph_deliverables() -> None:
    definition = load_pack_definition(CAREER_OPS_PACK_ID)
    artifact_ids = {item["id"] for item in definition.files["artifacts"]["artifact_schemas"]}

    assert set(CAREER_OPS_DELIVERABLE_TYPES).issubset(artifact_ids)
```

**Step 2: Run test to verify failure**

```bash
cd /c/Users/mathi/projects/forgegraph/backend
UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest tests/unit/services/test_career_ops_pack.py -q
```

Expected: FAIL because the pack files do not exist.

**Step 3: Create minimal compileable manifest**

Create `operating_model_packs/career_ops/manifest.yml`:

```yaml
pack_id: career_ops.v1
base_pack_id: career_ops
version: "1.0.0"
display_name: Career Operations
description: Company operating model pack for selective, evidence-backed career search operations.
company_type_label: Career Operations Company
checksum: auto
compatibility:
  forgegraph_min: "0.1.0"
  schema: operating_model_pack.v1
files:
  departments: departments.yml
  agents: agents.yml
  modules: modules.yml
  operations: operations.yml
  programs: programs.yml
  stages: stages.yml
  artifacts: artifacts.yml
  evaluations: evaluations.yml
  policies: policies.yml
  tools: tools.yml
  signals: signals.yml
  dashboards: dashboards.yml
  reports: reports.yml
install:
  default_program_template: career_ops.selective_search
  default_projection_type: career_ops:candidate_profile
  default_projection_label: Candidate Profile
  create_graph_version: true
  create_operation_templates: true
```

**Step 4: Create departments from graph**

Create `operating_model_packs/career_ops/departments.yml` with all 8 departments. Each department must include `id`, `label`, `responsibility`, and `responsibilities` matching the graph.

**Step 5: Create stage YAML from graph**

Create `operating_model_packs/career_ops/stages.yml` with all 12 stages, each with:

```yaml
- id: stage_01_candidate_onboarding
  label: Candidate onboarding
  sequence: 1
  owner_department_slug: candidate_profile_strategy
  required_outputs:
    - candidate_profile_snapshot
    - cv_source
    - proof_point_digest
  entry_criteria:
    - Candidate has provided initial identity and target-role intent.
  exit_criteria:
    - Candidate profile, CV source, and proof points are persisted as backend-owned records.
```

Repeat the shape for every stage from the graph contract.

**Step 6: Create artifacts YAML from graph deliverables and durable state**

Create `operating_model_packs/career_ops/artifacts.yml` with `artifact_schemas` including durable state artifacts and MVP deliverables.

Minimum required IDs:

```yaml
artifact_schemas:
  - id: candidate_profile_snapshot
    label: Candidate Profile Snapshot
  - id: cv_source
    label: CV Source
  - id: proof_point_digest
    label: Proof Point Digest
  - id: target_role_strategy
    label: Target Role Strategy
  - id: portal_scan_result
    label: Portal Scan Result
  - id: job_liveness_receipt
    label: Job Liveness Receipt
  - id: job_evaluation_report
    label: Job Evaluation Report
  - id: tailored_resume_pdf
    label: Tailored Resume PDF
  - id: cover_letter_draft
    label: Cover Letter Draft
  - id: cover_letter_pdf
    label: Cover Letter PDF
  - id: application_answers
    label: Application Answers
  - id: application_packet
    label: Application Packet
  - id: company_interview_prep
    label: Company Interview Prep
  - id: interview_story_bank
    label: Interview Story Bank
  - id: negotiation_script
    label: Negotiation Script
  - id: followup_plan
    label: Follow-up Plan
  - id: pipeline_health_report
    label: Pipeline Health Report
```

**Step 7: Create minimal companion YAML files**

Create `agents.yml`, `programs.yml`, `operations.yml`, `evaluations.yml`, `policies.yml`, `tools.yml`, `signals.yml`, `dashboards.yml`, `reports.yml`, and `modules.yml` using the DMP pack conventions. Keep them minimal but valid. Use pack-specific labels in YAML; do not create new core models.

**Step 8: Verify pass**

```bash
cd /c/Users/mathi/projects/forgegraph/backend
UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest tests/unit/services/test_career_ops_graph_contract.py tests/unit/services/test_career_ops_pack.py -q
```

Expected: PASS.

---

## Task 1.2: Add company blueprint alias support

**Objective:** Allow existing ForgeGraph company blueprint APIs/services to compile and create CareerOps companies.

**Files:**
- Modify: `backend/application/services/company_blueprints.py`
- Modify: `backend/tests/unit/services/test_company_blueprints.py`
- Modify: `backend/tests/unit/api/test_company_blueprints_api.py`

**Step 1: Add failing service test**

Append to `backend/tests/unit/services/test_company_blueprints.py`:

```python
from application.services.career_ops_graph_contract import CAREER_OPS_PACK_ID


def test_company_blueprint_compiler_accepts_career_ops_alias() -> None:
    result = CompanyBlueprintCompiler().compile(
        company_name="Mike CareerOps",
        objective="Run a selective job search pipeline.",
        blueprint_id="career-ops",
        services=["job evaluation", "application packets"],
        regions=["remote"],
        autonomy_mode="assisted",
        ai_access_mode="managed",
        intelligence_provider="openai",
    )

    assert result.graph_json["metadata"]["operating_model_pack"]["pack_id"] == CAREER_OPS_PACK_ID
    assert result.graph_json["metadata"]["company_profile"]["companyType"] == (
        "Career Operations Company"
    )
```

**Step 2: Run test to verify failure**

```bash
cd /c/Users/mathi/projects/forgegraph/backend
UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest tests/unit/services/test_company_blueprints.py::test_company_blueprint_compiler_accepts_career_ops_alias -q
```

Expected: FAIL because `career-ops` is not recognized.

**Step 3: Implement alias support**

In `backend/application/services/company_blueprints.py`, extend `_BLUEPRINT_ALIASES`:

```python
_BLUEPRINT_ALIASES.update(
    {
        "career_ops.v1": "career_ops.v1",
        "career_ops": "career_ops.v1",
        "career-ops": "career_ops.v1",
        "career operations": "career_ops.v1",
        "job_search_ops": "career_ops.v1",
        "job-search-ops": "career_ops.v1",
    }
)
```

If the dict is literal-only, add the entries directly in the literal instead of using `.update()`.

**Step 4: Add API test**

In `backend/tests/unit/api/test_company_blueprints_api.py`, add a POST test for `/api/company-blueprints/compile` with `blueprint_id: career-ops`, asserting the returned graph metadata uses `career_ops.v1`.

**Step 5: Verify pass**

```bash
cd /c/Users/mathi/projects/forgegraph/backend
UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest tests/unit/services/test_company_blueprints.py tests/unit/api/test_company_blueprints_api.py -q
```

Expected: PASS.

---

# Phase 2: Backend-owned CareerOps state and seed company

## Task 2.1: Add CareerOps onboarding state service

**Objective:** Persist candidate profile, positioning, CV source, proof points, and story bank exactly as graph-owned durable state.

**Files:**
- Create: `backend/application/services/career_ops_state.py`
- Create: `backend/tests/unit/services/test_career_ops_state.py`

**Step 1: Write failing tests**

Create tests that assert:

1. `upsert_candidate_profile_state(...)` creates a `StateProjection` with `projection_type="career_ops:candidate_profile"`.
2. `upsert_career_positioning_state(...)` creates `career_ops:career_positioning`.
3. `upsert_career_asset(...)` creates idempotent `Asset` and `AssetVersion` for `cv_source`, `proof_point_digest`, and `interview_story_bank`.
4. Re-running with identical content does not create duplicate assets/versions.
5. Credential-like fields are stripped or rejected from profile metadata.

**Step 2: Run test to verify failure**

```bash
cd /c/Users/mathi/projects/forgegraph/backend
UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest tests/unit/services/test_career_ops_state.py -q
```

Expected: FAIL because service does not exist.

**Step 3: Implement minimal service**

Implement functions:

```python
def upsert_candidate_profile_state(*, company: Graph, user: User | None, profile: dict[str, Any]) -> StateProjection: ...
def upsert_career_positioning_state(*, company: Graph, user: User | None, positioning: dict[str, Any]) -> StateProjection: ...
def upsert_career_asset(*, company: Graph, user: User | None, artifact_type: str, title: str, content: str, mime_type: str = "text/markdown") -> AssetVersion: ...
def bootstrap_candidate_state(*, company: Graph, user: User | None, profile: dict[str, Any], cv_markdown: str, proof_points_markdown: str = "") -> dict[str, Any]: ...
```

Use existing `Asset`, `AssetVersion`, `StateProjection`, and `ArchiveService` patterns. Do not add new models.

**Step 4: Verify pass**

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest tests/unit/services/test_career_ops_state.py -q
```

Expected: PASS.

---

## Task 2.2: Add seed command for a graph-complete demo company

**Objective:** Create a local CareerOps company with graph-complete records and one fake opportunity.

**Files:**
- Create: `backend/infrastructure/orm/management/commands/seed_career_ops_company.py`
- Create: `backend/tests/unit/management/test_seed_career_ops_company.py`

**Step 1: Write failing test**

The test should call the management command and assert it creates:

- `Graph(name="Mike CareerOps")` or provided name.
- latest `GraphVersion` with `metadata.operating_model_pack.pack_id == "career_ops.v1"`.
- `CompanyOperatingModelInstallation(pack_id="career_ops.v1")`.
- `CompanyProgram(template_id="career_ops.selective_search")` with 12 `ProgramStageState` records.
- `StateProjection` records for `career_ops:candidate_profile`, `career_ops:career_positioning`, and `career_ops:pipeline_snapshot`.
- `AssetVersion` records for `cv_source`, `proof_point_digest`, and `interview_story_bank`.
- one fake job `CompanySignal` and one fake `CompanyOpportunity`.
- no live external side effects.

**Step 2: Run test to verify failure**

```bash
cd /c/Users/mathi/projects/forgegraph/backend
UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest tests/unit/management/test_seed_career_ops_company.py -q
```

Expected: FAIL because command does not exist.

**Step 3: Implement command**

Command flags:

```text
--email mike@example.test
--company-name "Mike CareerOps"
--candidate-name "Mike"
--dry-run
```

Implementation flow:

1. Get or create user + default organization.
2. Create company through `create_company_from_blueprint(... blueprint_id="career_ops.v1" ...)`.
3. Create/select `CompanyProgram` from pack template.
4. Call `bootstrap_candidate_state(...)`.
5. Create one fake opportunity signal with source `career_ops_seed`.
6. Create pipeline snapshot `StateProjection`.
7. Return JSON summary on stdout.

**Step 4: Verify idempotency**

Run the command twice in the test and assert counts do not double for company, installation, program, profile projection, and fake opportunity.

**Step 5: Verify pass**

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest tests/unit/management/test_seed_career_ops_company.py -q
```

Expected: PASS.

---

# Phase 3: CareerOps pipeline services matching graph flow

## Task 3.1: Add opportunity normalization service

**Objective:** Convert scanned jobs into backend-owned `CompanySignal` and `CompanyOpportunity` records.

**Files:**
- Create: `backend/application/services/career_ops_opportunities.py`
- Create: `backend/tests/unit/services/test_career_ops_opportunities.py`

**Step 1: Write failing tests**

Required tests:

- `record_scanned_job(...)` creates `CompanySignal(source="career_ops_scan")` with stable `external_key` from normalized URL.
- The same URL replays idempotently.
- Same company+role with different source URL links to one current `CompanyOpportunity` where possible.
- Closed liveness status does not mark opportunity evaluation-ready.
- `metadata_json.career_ops` includes title, company, URL, location, provider, score, liveness status, and application status.

**Step 2: Run failure**

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest tests/unit/services/test_career_ops_opportunities.py -q
```

**Step 3: Implement service**

Core API:

```python
def normalize_job_key(*, company_name: str, role_title: str, url: str) -> str: ...
def record_scanned_job(*, company: Graph, user: User | None, posting: dict[str, Any], source: str = "career_ops_scan") -> CompanySignal: ...
def ensure_opportunity_for_signal(*, signal: CompanySignal, user: User | None) -> CompanyOpportunity | None: ...
def update_application_status(*, opportunity: CompanyOpportunity, status: str, user: User | None, metadata: dict[str, Any] | None = None) -> CompanyOpportunity: ...
```

No new models in this task.

**Step 4: Verify pass**

Run focused tests.

---

## Task 3.2: Add fake-provider-first scanner

**Objective:** Implement the `S03 Market scan` graph stage without live scraping.

**Files:**
- Create: `backend/application/services/career_ops_scan_providers.py`
- Create: `backend/application/services/career_ops_scanner.py`
- Create: `backend/tests/unit/services/test_career_ops_scanner.py`

**Step 1: Write failing tests**

Tests must verify:

- `FakeCareerOpsScanProvider` returns normalized jobs.
- Scanner filters by title/location/salary with missing data passing conservatively.
- Scanner records `ToolExecution` or equivalent receipt for the scan.
- Scanner calls `record_scanned_job(...)` and returns signal IDs.
- No Playwright/browser/network is required for unit tests.

**Step 2: Run failure**

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest tests/unit/services/test_career_ops_scanner.py -q
```

**Step 3: Implement provider interface**

```python
@dataclass(frozen=True)
class CareerOpsJobPosting:
    title: str
    company: str
    url: str
    location: str = ""
    provider: str = "fake"
    salary: dict[str, Any] | None = None
    raw: dict[str, Any] | None = None

class CareerOpsScanProvider(Protocol):
    id: str
    def fetch(self, config: dict[str, Any]) -> list[CareerOpsJobPosting]: ...
```

**Step 4: Verify pass**

Run focused tests.

---

## Task 3.3: Add liveness and dedupe gate

**Objective:** Implement `S04 Liveness and dedupe` as a mandatory gate before evaluation.

**Files:**
- Create: `backend/application/services/career_ops_liveness.py`
- Create: `backend/tests/unit/services/test_career_ops_liveness.py`

**Step 1: Write failing tests**

Tests:

- Active fixture creates `job_liveness_receipt` content and updates opportunity metadata to `liveness_status="active"`.
- Closed fixture creates risk signal and blocks evaluation readiness.
- Ambiguous fixture marks `liveness_status="proceed_with_caution"`.
- A receipt references source signal and opportunity IDs.

**Step 2: Run failure**

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest tests/unit/services/test_career_ops_liveness.py -q
```

**Step 3: Implement deterministic liveness classifier**

Use text fixture inputs first. Live browser checks can come later.

Statuses:

```text
active
closed
proceed_with_caution
blocked_unreachable
```

**Step 4: Verify pass**

Run focused tests.

---

## Task 3.4: Add deterministic A-G evaluation service

**Objective:** Implement `S05 Fit evaluation` with a stable contract before adding LLM-backed agents.

**Files:**
- Create: `backend/application/services/career_ops_evaluation.py`
- Create: `backend/tests/unit/services/test_career_ops_evaluation.py`

**Step 1: Write failing tests**

Tests must assert evaluation output includes:

```python
sections = {
    "A_role_summary",
    "B_cv_match",
    "C_level_strategy",
    "D_comp_demand",
    "E_customization_plan",
    "F_interview_plan",
    "G_posting_legitimacy",
}
```

Also assert:

- closed liveness blocks evaluation.
- score < 4.0 recommends no apply/hold.
- score >= 4.0 can proceed to packet but still needs `S07` approval before external side effects.
- exact source refs are recorded for profile, CV, proof points, liveness receipt, and opportunity.

**Step 2: Run failure**

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest tests/unit/services/test_career_ops_evaluation.py -q
```

**Step 3: Implement deterministic evaluator**

Implement a rule-based evaluator using fixture/profile/job metadata. Do not call external LLMs here.

**Step 4: Verify pass**

Run focused tests.

---

## Task 3.5: Add application packet deliverable assembly

**Objective:** Implement `S06 Application packet` and create graph deliverables through `ServiceEngagement`, `ServiceDeliverable`, `Asset`, and `AssetVersion`.

**Files:**
- Create: `backend/application/services/career_ops_deliverable_catalog.py`
- Create: `backend/application/services/career_ops_deliverables.py`
- Create: `backend/tests/unit/services/test_career_ops_deliverables.py`

**Step 1: Write failing tests**

Test cases:

- `ensure_career_ops_service_engagement(...)` creates idempotent catalog item and engagement with `required_pack_ids_json == ["career_ops.v1"]`.
- `assemble_career_ops_deliverable(..., "job_evaluation_report")` creates asset version and service deliverable.
- `assemble_career_ops_application_packet(...)` creates `application_packet` plus child deliverables for resume draft/PDF placeholder, cover letter draft, and answers.
- Deliverable metadata includes owner department slug from graph contract.
- No Markdown is marked candidate-facing unless it is an internal source artifact.

**Step 2: Run failure**

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest tests/unit/services/test_career_ops_deliverables.py -q
```

**Step 3: Implement service**

Mirror the generic pattern from `application/services/agency_deliverables.py`, but use CareerOps constants and graph contract.

Constants:

```python
ASSEMBLY_SOURCE = "career_ops_deliverable_assembly"
CATALOG_SLUG = "career-ops-application-engagement"
CATALOG_SOURCE_KEY = "career-ops-catalog:application-engagement"
REQUIRED_PACK_ID = "career_ops.v1"
```

**Step 4: Verify pass**

Run focused tests.

---

## Task 3.6: Add approval governance service

**Objective:** Implement `S07 Candidate approval gate` and enforce no-auto-apply policy.

**Files:**
- Create: `backend/application/services/career_ops_approval.py`
- Create: `backend/tests/unit/services/test_career_ops_approval.py`

**Step 1: Write failing tests**

Tests:

- packet starts as `status="in_review"` or metadata `approval_status="pending"`.
- `approve_application_packet(...)` can mark packet approved.
- `request_packet_changes(...)` sends flow back to `stage_06_application_packet` status or metadata.
- `assert_external_side_effect_allowed(...)` raises unless packet is approved.
- no-auto-apply rule blocks `submit_application` side effect even if packet exists and score is high, unless explicit approval exists.

**Step 2: Run failure**

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest tests/unit/services/test_career_ops_approval.py -q
```

**Step 3: Implement minimal governance service**

Use deliverable metadata and/or existing approval primitives if suitable. Do not add new external connector behavior.

**Step 4: Verify pass**

Run focused tests.

---

## Task 3.7: Add pipeline read model and integrity checks

**Objective:** Implement `S11 Pipeline review` as a backend read model.

**Files:**
- Create: `backend/application/services/career_ops_pipeline.py`
- Create: `backend/tests/unit/services/test_career_ops_pipeline.py`

**Step 1: Write failing tests**

Pipeline summary must include:

- counts by status: `discovered`, `liveness_checked`, `evaluated`, `packet_ready`, `approval_pending`, `approved`, `applied`, `interview`, `offer`, `rejected`, `skip`.
- top opportunities by score.
- stale follow-ups.
- duplicate warnings.
- broken/missing artifact warnings.
- approval-required packets.

**Step 2: Run failure**

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest tests/unit/services/test_career_ops_pipeline.py -q
```

**Step 3: Implement read model**

Read from `CompanyOpportunity`, `CompanySignal`, `ServiceEngagement`, `ServiceDeliverable`, `AssetVersion`, and `StateProjection`. Persist optional snapshot using `career_ops:pipeline_snapshot` only after computing from DB-owned state.

**Step 4: Verify pass**

Run focused tests.

---

# Phase 4: End-to-end fake opportunity smoke

## Task 4.1: Add graph-owned end-to-end orchestration service

**Objective:** Run one fake job from scan through packet creation using backend services and graph stage ownership.

**Files:**
- Create: `backend/application/services/career_ops_company_run.py`
- Create: `backend/tests/unit/services/test_career_ops_company_run.py`

**Step 1: Write failing test**

The test should:

1. Seed a CareerOps company.
2. Run fake scan.
3. Run liveness check.
4. Run evaluation.
5. Assemble packet.
6. Leave packet pending candidate approval.
7. Build pipeline snapshot.
8. Assert all records map to graph stages and departments.

Expected final record evidence:

- `CompanySignal` for scanned lead.
- `ToolExecution` or receipt for scan/liveness.
- `CompanyOpportunity` with score/recommendation metadata.
- `ServiceEngagement` for application engagement.
- `ServiceDeliverable` records for `job_liveness_receipt`, `job_evaluation_report`, `application_packet`, `company_interview_prep` as applicable.
- `StateProjection(career_ops:pipeline_snapshot)`.
- No external send/submit receipt.

**Step 2: Run failure**

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest tests/unit/services/test_career_ops_company_run.py -q
```

**Step 3: Implement orchestration service**

Function:

```python
def run_fake_career_ops_opportunity_flow(*, company: Graph, user: User | None) -> dict[str, Any]: ...
```

Return a JSON-serializable evidence payload with IDs and statuses.

**Step 4: Verify pass**

Run focused test.

---

## Task 4.2: Add management command for smoke run

**Objective:** Let Mike run the same fake end-to-end flow locally and inspect JSON evidence.

**Files:**
- Create: `backend/infrastructure/orm/management/commands/run_career_ops_smoke.py`
- Create: `backend/tests/unit/management/test_run_career_ops_smoke.py`

**Step 1: Write failing test**

Assert command outputs JSON containing:

```json
{
  "company_id": "...",
  "pack_id": "career_ops.v1",
  "program_stage_count": 12,
  "opportunity_id": "...",
  "liveness_status": "active",
  "evaluation_score": "...",
  "application_packet_id": "...",
  "approval_status": "pending",
  "external_side_effects": []
}
```

**Step 2: Run failure**

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest tests/unit/management/test_run_career_ops_smoke.py -q
```

**Step 3: Implement command**

Flags:

```text
--email mike@example.test
--company-name "Mike CareerOps"
--json
```

**Step 4: Verify pass**

Run focused command test.

---

# Phase 5: Pre-live safety and quality gates

This phase is mandatory before any real employer-facing send, submit, export, or recommendation is allowed. The goal is to prove we do not produce flaky CVs, invented claims, broken PDFs, leaked internal metadata, bad ATS output, or accidental external side effects.

## Live-readiness policy

A CareerOps run can be marked `live_ready=true` only when all of these gates pass for the specific packet/version being sent:

1. **Source truth gate:** every claim in resume, cover letter, and answers maps to CV/proof-point/profile source refs.
2. **No-invention gate:** generated content contains no unverified skills, employers, degrees, metrics, certifications, dates, salary claims, visa claims, or location availability.
3. **ATS parseability gate:** resume PDF text is extractable, single-column enough for parsing, and includes required contact/profile sections.
4. **PDF integrity gate:** PDFs start with `%PDF`, have expected page count, non-empty extracted text, and no rendering placeholders.
5. **Internal leakage gate:** candidate-facing files contain no `prompt`, `model`, `metadata_json`, `provenance_json`, raw tool traces, internal IDs unless intended, Hermes references, or ForgeGraph implementation details.
6. **Employer identity gate:** packet is addressed to the intended employer/job and cannot mix content from a different opportunity.
7. **Approval gate:** no external send/submit connector can run without explicit candidate approval for the exact packet version.
8. **Side-effect dry-run gate:** staging/dry-run connector tests pass before live connectors are enabled.
9. **Regression gate:** golden fixture packets remain stable except for intentional snapshot updates reviewed in the PR.
10. **Independent review gate:** pre-commit code review and a domain-specific packet QA reviewer both pass.

---

## Task 5.1: Add live-readiness domain model and quality-gate service

**Objective:** Add a single service that evaluates whether a CareerOps application packet is safe to show/send to an actual employer.

**Files:**
- Create: `backend/application/services/career_ops_quality_gates.py`
- Create: `backend/tests/unit/services/test_career_ops_quality_gates.py`

**Step 1: Write failing tests**

Create tests that assert:

- `evaluate_application_packet_quality(...)` returns `status="blocked"` if any required artifact is missing.
- `status="blocked"` if the packet has no source refs for CV/profile/proof points/opportunity.
- `status="blocked"` if candidate-facing text contains internal leakage tokens.
- `status="blocked"` if any claim lacks source support.
- `status="pass"` only when all required checks pass.
- quality-gate result is persisted into `ServiceDeliverable.metadata_json["quality_gate"]`.

Suggested test skeleton:

```python
from __future__ import annotations

import pytest

from application.services.career_ops_quality_gates import (
    CAREER_OPS_INTERNAL_LEAKAGE_TOKENS,
    evaluate_application_packet_quality,
)

pytestmark = pytest.mark.django_db


def test_packet_quality_blocks_missing_source_refs(career_ops_packet_fixture) -> None:
    packet = career_ops_packet_fixture(source_refs=[])

    result = evaluate_application_packet_quality(packet)

    assert result["status"] == "blocked"
    assert "source_refs_missing" in result["blocking_codes"]


def test_packet_quality_blocks_internal_leakage(career_ops_packet_fixture) -> None:
    packet = career_ops_packet_fixture(content="Resume text\nmetadata_json: {secret}\n")

    result = evaluate_application_packet_quality(packet)

    assert result["status"] == "blocked"
    assert "internal_leakage" in result["blocking_codes"]
    assert "metadata_json" in CAREER_OPS_INTERNAL_LEAKAGE_TOKENS
```

**Step 2: Run failure**

```bash
cd /c/Users/mathi/projects/forgegraph/backend
UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest tests/unit/services/test_career_ops_quality_gates.py -q
```

Expected: FAIL because the service does not exist.

**Step 3: Implement quality-gate service**

Implement:

```python
def evaluate_application_packet_quality(packet: ServiceDeliverable) -> dict[str, Any]: ...
def refresh_application_packet_quality_gate(packet: ServiceDeliverable) -> ServiceDeliverable: ...
def assert_packet_live_ready(packet: ServiceDeliverable) -> None: ...
```

Return shape:

```python
{
    "status": "pass" | "blocked" | "warning",
    "blocking_codes": [],
    "warning_codes": [],
    "checks": {
        "source_refs": {"status": "pass"},
        "claim_support": {"status": "pass"},
        "ats_parseability": {"status": "pass"},
        "pdf_integrity": {"status": "pass"},
        "internal_leakage": {"status": "pass"},
        "employer_identity": {"status": "pass"},
        "approval": {"status": "pass"},
    },
}
```

**Step 4: Verify pass**

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest tests/unit/services/test_career_ops_quality_gates.py -q
```

---

## Task 5.2: Add claim-source validation tests

**Objective:** Ensure generated CVs/letters/answers never invent candidate facts.

**Files:**
- Create: `backend/application/services/career_ops_claims.py`
- Create: `backend/tests/unit/services/test_career_ops_claims.py`

**Step 1: Write failing tests**

Tests must include both allowed and blocked examples:

- Allowed: a rephrased claim that is supported by CV/proof text.
- Blocked: an unmentioned skill (`Kubernetes`, `SOC2`, `Spanish C2`, etc.) not in source refs.
- Blocked: inflated metric (`50%` -> `80%`) unless exact value appears in source.
- Blocked: fake certification/degree.
- Blocked: employer/job content leaking from another opportunity.

Example:

```python
def test_claim_validator_blocks_unverified_skill() -> None:
    result = validate_candidate_claims(
        generated_text="Built production Kubernetes platforms for fintech clients.",
        source_texts=["Built production Docker services for ecommerce clients."],
    )

    assert result.status == "blocked"
    assert "Kubernetes" in result.unsupported_terms
```

**Step 2: Run failure**

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest tests/unit/services/test_career_ops_claims.py -q
```

**Step 3: Implement conservative validator**

Start rule-based and conservative:

- Extract candidate-sensitive claim terms: skills, tools, companies, metrics, degrees, certifications, languages, locations, visa/sponsorship claims.
- Require exact or configured alias support in source text.
- Permit stylistic rewrites only when noun/metric facts are source-backed.
- Return warnings for uncertain terms; block high-risk unsupported facts.

**Step 4: Integrate with quality gate**

`evaluate_application_packet_quality(...)` must call claim validation for each candidate-facing artifact.

**Step 5: Verify pass**

Run claim tests and quality gate tests.

---

## Task 5.3: Add ATS/PDF parseability tests

**Objective:** Catch broken, unreadable, or ATS-hostile CV PDFs before they reach employers.

**Files:**
- Create: `backend/application/services/career_ops_document_quality.py`
- Create: `backend/tests/unit/services/test_career_ops_document_quality.py`

**Step 1: Write failing tests**

Tests:

- Valid PDF bytes must start with `%PDF`.
- PDF text extraction must produce non-empty text with candidate name, contact section, experience section, and skills/competencies section.
- Placeholder strings (`{{NAME}}`, `TODO`, `lorem ipsum`, `undefined`, `None None`) block live readiness.
- Overlong generated resume blocks or warns when it exceeds configured page count.
- HTML candidate-facing artifact blocks if it contains multi-column/sidebar CSS when `ats_strict=True`, unless explicitly marked visual-only.

**Step 2: Run failure**

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest tests/unit/services/test_career_ops_document_quality.py -q
```

**Step 3: Implement document checks**

Use existing PDF/text extraction dependencies if already present in ForgeGraph. If no PDF extractor is available in test environment, implement byte/header/placeholder checks first and mark text extraction as a skipped capability with a blocker for live readiness.

Suggested API:

```python
def evaluate_pdf_integrity(*, content: bytes, expected_text: list[str] | None = None) -> dict[str, Any]: ...
def evaluate_ats_parseability(*, text: str, ats_strict: bool = True) -> dict[str, Any]: ...
def find_candidate_facing_placeholders(text: str) -> list[str]: ...
```

**Step 4: Integrate with packet quality gate**

Quality gate must block `tailored_resume_pdf` if PDF integrity or ATS parseability fails.

**Step 5: Verify pass**

Run document-quality and packet-quality tests.

---

## Task 5.4: Add employer/opportunity isolation tests

**Objective:** Prevent a packet for one employer from containing another employer's company name, role, URL, or cover-letter angle.

**Files:**
- Create: `backend/tests/unit/services/test_career_ops_opportunity_isolation.py`
- Modify: `backend/application/services/career_ops_quality_gates.py`

**Step 1: Write failing tests**

Tests:

- Create two opportunities: `Acme AI Engineer` and `Globex Product Manager`.
- Build a packet for Acme containing `Globex` in cover letter body.
- Assert quality gate blocks with `employer_identity_mismatch`.
- Assert source refs must point to the same opportunity as the packet engagement.

**Step 2: Run failure**

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest tests/unit/services/test_career_ops_opportunity_isolation.py -q
```

**Step 3: Implement employer identity check**

Use opportunity metadata:

```text
career_ops.employer_name
career_ops.role_title
career_ops.job_url
```

Block when candidate-facing text contains another known employer/opportunity name from the same CareerOps company unless explicitly quoted in comparison context and not in the final packet.

**Step 4: Verify pass**

Run isolation and quality-gate tests.

---

## Task 5.5: Add no-live-side-effects test harness

**Objective:** Guarantee tests and pre-live smoke runs cannot send applications, emails, WhatsApp messages, or browser form submissions.

**Files:**
- Create: `backend/application/services/career_ops_side_effects.py`
- Create: `backend/tests/unit/services/test_career_ops_side_effects.py`
- Modify: `backend/application/services/career_ops_approval.py`

**Step 1: Write failing tests**

Tests:

- `assert_career_ops_external_side_effect_allowed(...)` blocks when `CAREER_OPS_LIVE_SEND_ENABLED` is false.
- Blocks when packet quality gate is not pass.
- Blocks when approval does not reference the exact `asset_version_id` / `packet_version_id`.
- Blocks when recipient/employer domain does not match approved opportunity.
- Allows only `dry_run` in test/staging by default.

**Step 2: Run failure**

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest tests/unit/services/test_career_ops_side_effects.py -q
```

**Step 3: Implement side-effect guard**

Default settings must be safe:

```python
CAREER_OPS_LIVE_SEND_ENABLED = False
CAREER_OPS_ALLOWED_EXTERNAL_ACTIONS = ("dry_run",)
```

Only permit live side effects when:

1. explicit setting enables live sends,
2. packet quality gate passes,
3. explicit candidate approval is present for exact packet version,
4. connector dry-run has passed,
5. operation has idempotency key and audit metadata.

**Step 4: Verify pass**

Run side-effect and approval tests.

---

## Task 5.6: Add golden fixture regression tests for generated packets

**Objective:** Prevent subtle regressions in generated resumes/cover letters/application packets.

**Files:**
- Create: `backend/tests/fixtures/career_ops/golden_candidate_profile.json`
- Create: `backend/tests/fixtures/career_ops/golden_cv.md`
- Create: `backend/tests/fixtures/career_ops/golden_job_posting.json`
- Create: `backend/tests/fixtures/career_ops/expected_packet_snapshot.json`
- Create: `backend/tests/unit/services/test_career_ops_golden_packet.py`

**Step 1: Write failing snapshot-style tests**

Tests should build a packet from deterministic fixture input and assert:

- section headings are stable,
- required source refs exist,
- recommendation/score are stable,
- no unsupported claims appear,
- generated packet shape matches expected JSON snapshot excluding volatile IDs/timestamps.

**Step 2: Run failure**

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest tests/unit/services/test_career_ops_golden_packet.py -q
```

**Step 3: Implement snapshot normalizer**

Normalize volatile fields before snapshot compare:

```python
VOLATILE_KEYS = {"id", "created_at", "updated_at", "asset_version_id", "company_id"}
```

**Step 4: Verify pass**

Run golden packet test. Future intentional changes must update the fixture in the same PR and explain why.

---

## Task 5.7: Add pre-live smoke command

**Objective:** Provide a single command that says whether CareerOps is safe for live employer-facing use.

**Files:**
- Create: `backend/infrastructure/orm/management/commands/check_career_ops_live_readiness.py`
- Create: `backend/tests/unit/management/test_check_career_ops_live_readiness.py`

**Step 1: Write failing tests**

Test JSON output shape:

```json
{
  "status": "blocked",
  "company_id": "...",
  "packet_id": "...",
  "checks": {
    "quality_gate": "pass",
    "claim_source": "pass",
    "pdf_integrity": "pass",
    "ats_parseability": "pass",
    "internal_leakage": "pass",
    "approval": "blocked",
    "side_effect_guard": "blocked"
  },
  "live_send_allowed": false
}
```

Test that a packet without approval returns `status="blocked"` even if all artifact quality checks pass.

**Step 2: Run failure**

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest tests/unit/management/test_check_career_ops_live_readiness.py -q
```

**Step 3: Implement command**

Flags:

```text
--company-id <uuid>
--packet-id <uuid>
--json
```

The command must never perform side effects. It only reads backend records and returns readiness.

**Step 4: Verify pass**

Run management test.

---

## Task 5.8: Add independent packet QA review step to implementation workflow

**Objective:** Require a fresh reviewer before any code or packet is treated as live-ready.

**Files:**
- Modify: this plan's implementation workflow only, or create docs if desired: `docs/operating-model-packs/career-ops.md`

**Required reviewer prompt during implementation:**

```text
Review this CareerOps application packet as if it might be sent to a real employer.
Fail closed. Return blockers if:
- any candidate claim lacks source evidence,
- PDF/HTML has placeholders or broken formatting,
- employer/job identity is mixed,
- internal metadata or prompts leak,
- application is not explicitly candidate-approved,
- external side effects are enabled by default.
```

**Verification:** The reviewer output must be attached to PR notes or implementation summary. Any blocker means no live use.

---

# Optional Phase 6: API surface after backend proof

Only add API routes after the backend services pass. If added, prefer generic company-ops namespace over `/api/career/*`.

## Task 5.1: Add company-ops CareerOps snapshot API

**Objective:** Expose backend-owned CareerOps pipeline state for frontend/TUI without making UI the source of truth.

**Files:**
- Create: `backend/adapters/api/company_ops/career_ops.py` or extend existing `backend/adapters/api/company_ops/views.py`
- Modify: `backend/adapters/api/company_ops/urls.py`
- Create: `backend/tests/unit/api/test_career_ops_company_ops_api.py`
- Modify: route security matrix if required.

**Endpoint proposal:**

```text
GET /api/company-ops/career-ops?company_id=<uuid>
POST /api/company-ops/career-ops/smoke-run
```

**Security:** Must require authenticated organization/company access. Must have route-security-matrix coverage for `/api` and `/api/v1` if route is production.

---

# Full verification command set

Run from `C:\Users\mathi\projects\forgegraph\backend`:

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest \
  tests/unit/services/test_career_ops_graph_contract.py \
  tests/unit/services/test_career_ops_pack.py \
  tests/unit/services/test_company_blueprints.py \
  tests/unit/api/test_company_blueprints_api.py \
  tests/unit/services/test_career_ops_state.py \
  tests/unit/management/test_seed_career_ops_company.py \
  tests/unit/services/test_career_ops_opportunities.py \
  tests/unit/services/test_career_ops_scanner.py \
  tests/unit/services/test_career_ops_liveness.py \
  tests/unit/services/test_career_ops_evaluation.py \
  tests/unit/services/test_career_ops_deliverables.py \
  tests/unit/services/test_career_ops_approval.py \
  tests/unit/services/test_career_ops_pipeline.py \
  tests/unit/services/test_career_ops_company_run.py \
  tests/unit/management/test_run_career_ops_smoke.py \
  tests/unit/services/test_career_ops_quality_gates.py \
  tests/unit/services/test_career_ops_claims.py \
  tests/unit/services/test_career_ops_document_quality.py \
  tests/unit/services/test_career_ops_opportunity_isolation.py \
  tests/unit/services/test_career_ops_side_effects.py \
  tests/unit/services/test_career_ops_golden_packet.py \
  tests/unit/management/test_check_career_ops_live_readiness.py \
  -q

UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run ruff check \
  application/services/career_ops_graph_contract.py \
  application/services/career_ops_state.py \
  application/services/career_ops_opportunities.py \
  application/services/career_ops_scan_providers.py \
  application/services/career_ops_scanner.py \
  application/services/career_ops_liveness.py \
  application/services/career_ops_evaluation.py \
  application/services/career_ops_deliverable_catalog.py \
  application/services/career_ops_deliverables.py \
  application/services/career_ops_approval.py \
  application/services/career_ops_pipeline.py \
  application/services/career_ops_company_run.py \
  application/services/career_ops_quality_gates.py \
  application/services/career_ops_claims.py \
  application/services/career_ops_document_quality.py \
  application/services/career_ops_side_effects.py \
  infrastructure/orm/management/commands/seed_career_ops_company.py \
  infrastructure/orm/management/commands/run_career_ops_smoke.py \
  infrastructure/orm/management/commands/check_career_ops_live_readiness.py \
  tests/unit/services/test_career_ops_*.py \
  tests/unit/management/test_seed_career_ops_company.py \
  tests/unit/management/test_run_career_ops_smoke.py \
  tests/unit/management/test_check_career_ops_live_readiness.py

DEBUG=1 USE_SQLITE=1 USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run python manage.py check
```

If any API routes are added:

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest tests/integration/adapters/test_security_matrix.py -q
```

---

# Acceptance criteria for first working company

The first implementation is complete when:

- [ ] `docs/operating-model-packs/career-ops-company-graph.mmd` exists and matches the current graph.
- [ ] `career_ops_graph_contract.py` exists and tests prove it matches the departments/stages/deliverables from the graph.
- [ ] `operating_model_packs/career_ops/` exists and `career_ops.v1` compiles.
- [ ] `CompanyBlueprintCompiler` supports `career_ops.v1` and `career-ops` alias.
- [ ] `seed_career_ops_company` creates a CareerOps company, installation, graph version, 12-stage program, candidate profile state, CV/proof/story assets, and one fake opportunity.
- [ ] Fake scanner creates backend-owned job lead records.
- [ ] Liveness gate blocks closed postings before evaluation.
- [ ] A-G evaluation creates a backend-owned report payload.
- [ ] Application packet creates service engagement and deliverables.
- [ ] Candidate approval remains pending by default.
- [ ] Quality gate blocks packets with missing source refs, unsupported claims, placeholders, internal leakage, broken PDFs, employer mismatch, or missing exact-version approval.
- [ ] Claim-source validation proves CVs/cover letters/application answers cannot invent skills, metrics, degrees, certifications, languages, employers, dates, salary claims, or availability.
- [ ] ATS/PDF tests prove generated CV PDFs are valid, parseable, non-empty, placeholder-free, and within configured page/layout limits before live use.
- [ ] Opportunity isolation tests prove one employer's packet cannot contain another employer's name, role, URL, or cover-letter angle.
- [ ] Side-effect guard defaults to dry-run/manual-only and blocks email/browser-form/WhatsApp/application submission unless live sends are explicitly enabled, packet quality passes, and exact packet-version approval exists.
- [ ] Golden fixture regression tests pass for deterministic candidate/job packets.
- [ ] `check_career_ops_live_readiness` reports `blocked` until every quality, approval, and side-effect guard passes.
- [ ] No auto-apply, no live external side effects, no local markdown/SQLite source of truth.
- [ ] Pipeline snapshot is derived from DB records.
- [ ] Focused pytest, ruff, and `manage.py check` pass, including all pre-live safety tests.

---

# Implementation notes for subagents

When executing this plan with `subagent-driven-development`:

1. Dispatch one subagent per task or tightly grouped pair of tasks.
2. Pass this plan and the Mermaid graph path in each subagent context.
3. Require subagents to preserve the graph contract and runtime invariants.
4. Require each subagent to return:
   - files changed
   - tests run
   - real command output summary
   - blockers
5. After each subagent, run a separate review subagent for:
   - graph contract compliance
   - runtime invariant compliance
   - no accidental live side effects
6. Do not proceed to live scraping, frontend, or PDF polish until the fake end-to-end flow passes.

---

# Risks and guardrails

## Risk: Graph drift

Guardrail: `career_ops_graph_contract.py` and pack tests must fail when departments, stages, or deliverables diverge.

## Risk: Local-file source-of-truth regression

Guardrail: no `data/applications.md`, local SQLite tracker, or local job pipeline file. All state is in ForgeGraph backend records.

## Risk: Auto-apply behavior

Guardrail: approval service blocks all external side effects unless an explicit approval record/metadata is present. The initial smoke flow must end with `approval_status="pending"`.

## Risk: Too much surface area in first PR

Guardrail: first PR proves pack compile + seed + fake flow. Live scanner adapters, PDF polish, and UI can follow.

## Risk: Vertical-specific core models

Guardrail: use pack YAML and existing generic models first. Add core model fields only if tests prove existing primitives cannot represent required state.

---

# Open questions before implementation

1. Should the seeded local company be named `Mike CareerOps` by default, or should it remain fixture-neutral (`Candidate CareerOps`)?
2. Should the first smoke use Mike-like AI/product roles, or generic fake roles to avoid personal data in tests?
3. Should we create a repo docs copy of the Mermaid graph in the first PR, or keep it under `.hermes/plans` until after the pack compiles? Recommendation: copy into docs in Task 0.1.
4. Should the first external connector target eventually be email, browser automation, or manual checklist only? Recommendation: manual checklist only for v1; no external submission connector.
