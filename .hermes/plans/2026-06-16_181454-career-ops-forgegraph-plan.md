# Career-Ops-Inspired ForgeGraph Company Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Build a ForgeGraph-native "career operations" company/operating-model pack inspired by `santifer/career-ops`, where a candidate can onboard once, scan/select opportunities, evaluate fit and legitimacy, generate tailored application packets, track applications, prepare interviews, and run follow-up/negotiation loops with backend-owned durable state.

**Architecture:** Do not copy Career-Ops as a local-file CLI app. Transfer the durable product pattern into ForgeGraph primitives: `Graph` as the candidate's career-ops company, an installable `career_ops.v1` operating-model pack, `CompanyProgram`/`ProgramStageState` for the search workflow, `CompanySignal`/`CompanyOpportunity` for job leads, `Asset`/`AssetVersion` for CVs, reports, story bank, and PDFs, `ServiceEngagement`/`ServiceDeliverable` for application packets, `StateProjection` for current candidate profile and pipeline snapshots, and backend-owned runs/tool executions for scans, liveness checks, evaluations, and document generation.

**Tech Stack:** Django/Python backend, ForgeGraph operating-model packs (`operating_model_packs/*` YAML), existing company blueprint APIs, existing service engagement/deliverable primitives, Playwright/browser-rendered PDF where artifacts need PDF output, pytest/ruff/manage.py check for verification.

---

## Reference inspected

- Repository: `https://github.com/santifer/career-ops`
- Fresh checkout commit inspected: `4e05cfda98b5dccfd2c664c12335ee20812b451b`
- Local checkout used for analysis: `C:/Users/mathi/AppData/Local/Temp/tmp.S1lnRuLGme/career-ops`
- Primary source files read:
  - `README.md`
  - `AGENTS.md`
  - `DATA_CONTRACT.md`
  - `docs/ARCHITECTURE.md`
  - `modes/_shared.md`
  - `modes/auto-pipeline.md`
  - `modes/oferta.md`
  - `modes/pdf.md`
  - `modes/scan.md`
  - `config/profile.example.yml`
  - `scan.mjs`
  - `tracker.mjs`
  - `verify-pipeline.mjs`
  - `batch/batch-runner.sh`

## Origin repo pattern summary

Career-Ops is not just "resume generation". The transferable pattern is a local-first, agent-routed job-search operating system:

1. **Two-layer data contract**
   - User layer: `cv.md`, `config/profile.yml`, `modes/_profile.md`, `article-digest.md`, `data/applications.md`, generated reports/PDFs, story bank.
   - System layer: reusable modes, scripts, templates, provider adapters, dashboard.
   - ForgeGraph translation: mutable candidate facts and generated artifacts must live in backend-owned company state, while reusable career-ops methodology lives in the pack.

2. **Onboarding-before-operations**
   - The origin runs a cold-start `doctor` and refuses evaluations until CV/profile/target roles/portals exist.
   - ForgeGraph translation: create a career onboarding service that writes profile/CV/preferences/proof-point state to `StateProjection` and `AssetVersion` records, then gates scan/evaluation operations until required evidence exists.

3. **Selective pipeline, not spray-and-pray**
   - Scores below ~4/5 should generally not be applied to; the system evaluates and recommends, but never submits automatically.
   - ForgeGraph translation: model explicit approval gates before external application or outreach side effects. Generate packets and recommendations, not auto-submit.

4. **Structured A-G evaluation**
   - A: role summary
   - B: CV match with exact evidence
   - C: level/strategy
   - D: compensation and demand research
   - E: CV/personalization plan
   - F: interview plan and STAR+Reflection story mapping
   - G: posting legitimacy/liveness/ghost-job signals
   - ForgeGraph translation: make `job_evaluation_report` a deliverable, backed by evidence links and scoring metadata.

5. **Zero-token scanner before expensive agent work**
   - `scan.mjs` uses provider adapters for Greenhouse, Ashby, Lever, Workable, Workday, Recruitee, SmartRecruiters, etc. It filters by title/location/salary and deduplicates before adding to pipeline.
   - ForgeGraph translation: implement backend-owned provider adapters and `ToolExecution` receipts for scans before launching LLM evaluation runs.

6. **Liveness gate before full evaluation**
   - URL inputs must be checked for active/closed posting evidence before spending tokens on reports/PDFs.
   - ForgeGraph translation: liveness check is a required stage and produces a durable signal; closed postings do not proceed to evaluation.

7. **Application packet generation**
   - Tailored ATS CV PDF through HTML + Playwright, optional cover letter with user approval, application form answers for high-score opportunities.
   - ForgeGraph translation: generate `tailored_resume`, `cover_letter_draft`, `application_answers`, `application_packet` deliverables with approval status and PDF/HTML artifact versions.

8. **Tracker integrity and dashboard**
   - Origin uses markdown tracker as source of truth, derived SQLite index, dedupe/merge/normalize/verify scripts, and a Go TUI dashboard.
   - ForgeGraph translation: backend DB already becomes the source of truth. Expose a candidate pipeline API/view backed by `CompanyOpportunity`, `ServiceDeliverable`, `CompanySignal`, and `StateProjection`, with integrity tests instead of markdown repairs.

9. **Batch/resume behavior**
   - Origin batch runner has locks, state file, retries, rate-limit handling, and worker logs.
   - ForgeGraph translation: use backend-owned `Run`, task lifecycle, liveness/recovery invariants, idempotency keys, and `ToolExecution` receipts. Do not store durable batch state in an engine/local worker.

10. **Interview/negotiation memory**
    - Story bank accumulates STAR+Reflection examples and negotiation scripts across evaluations.
    - ForgeGraph translation: story bank is a versioned `Asset` and/or `StateProjection` fed by evaluated jobs and interview prep deliverables.

## ForgeGraph constraints discovered

- `docs/architecture/runtime-invariants.md` is canonical: backend control plane is the only durable source of truth; engine state is ephemeral; events are not authoritative state.
- Existing company creation path supports pack-backed companies through:
  - `POST /api/company-blueprints/compile`
  - `POST /api/companies/from-blueprint`
- Existing DMP pack structure lives under `operating_model_packs/digital_marketing_pro/` with `manifest.yml`, `departments.yml`, `programs.yml`, `stages.yml`, `artifacts.yml`, etc.
- Existing pack compiler currently defaults to `digital_marketing_pro.v1` in `backend/application/services/company_blueprints.py` and aliases only marketing/growth labels.
- Existing generic primitives are sufficient for the first slice:
  - `CompanyProgram` / `ProgramStageState`
  - `ServiceCatalogItem` / `ServiceEngagement` / `ServiceDeliverable`
  - `CompanySignal` / `CompanyOpportunity`
  - `Asset` / `AssetVersion`
  - `StateProjection`
  - `ToolExecution`
  - `Run` / task lifecycle
- Avoid `/api/career/*` as a first move unless there is a clear product/API need. Prefer generic company blueprint + service engagement APIs, then add a thin `company-ops` helper endpoint if needed.

## Proposed ForgeGraph product shape

### Company identity

- Pack id: `career_ops.v1`
- Base pack id: `career_ops`
- Display name: `Career Operations`
- Company type label: `Career Operations Company`
- Example company name: `Mike CareerOps` or `{Candidate Name} CareerOps`
- Objective template: `Run a selective, evidence-backed job search operation that finds high-fit roles, generates truthful application packets, tracks outcomes, and improves interview readiness.`

### Departments

Create `operating_model_packs/career_ops/departments.yml` with:

1. `candidate_profile_strategy` — owns CV, target roles, constraints, positioning, proof points.
2. `market_role_discovery` — owns portal scanning, provider adapters, source reliability, dedupe.
3. `opportunity_evaluation` — owns A-G evaluation, scoring, legitimacy, compensation evidence.
4. `application_packet_studio` — owns tailored resume, cover letter, answers, ATS/PDF checks.
5. `application_operations` — owns tracker status, submission readiness, follow-ups, receipts.
6. `interview_negotiation_prep` — owns story bank, company-specific prep, negotiation scripts.
7. `pipeline_integrity_analytics` — owns dedupe, normalization, conversion metrics, periodic reports.
8. `candidate_approval_governance` — owns human approvals, ethics/no-auto-submit policy, privacy controls.

### Program stages

Create `operating_model_packs/career_ops/stages.yml` with stages:

1. `stage_01_candidate_onboarding`
2. `stage_02_search_strategy`
3. `stage_03_market_scan`
4. `stage_04_liveness_and_dedupe`
5. `stage_05_fit_evaluation`
6. `stage_06_application_packet`
7. `stage_07_candidate_approval`
8. `stage_08_submission_tracking`
9. `stage_09_interview_prep`
10. `stage_10_followup_negotiation`
11. `stage_11_pipeline_review`
12. `stage_12_learning_update`

This mirrors the Career-Ops lifecycle while using backend-owned stage state instead of local markdown/checklists.

### Deliverables/artifacts

Add artifact schemas and deliverable definitions for:

- `candidate_profile_snapshot`
- `cv_source`
- `proof_point_digest`
- `target_role_strategy`
- `portal_scan_result`
- `job_liveness_receipt`
- `job_evaluation_report`
- `posting_legitimacy_report`
- `tailored_resume_html`
- `tailored_resume_pdf`
- `cover_letter_draft`
- `cover_letter_pdf`
- `application_answers`
- `application_packet`
- `interview_story_bank`
- `company_interview_prep`
- `negotiation_script`
- `followup_plan`
- `pipeline_health_report`

For the first PR, do not build all renderers. Define the pack and compile/install path, then implement one end-to-end application packet against a fake job fixture.

### Data mapping

| Career-Ops local file/object | ForgeGraph owner |
| --- | --- |
| `cv.md` | `Asset(asset_type="career_profile")` + `AssetVersion(mime_type="text/markdown")` |
| `config/profile.yml` | `StateProjection(projection_type="career_candidate_profile")` + sanitized engagement intake |
| `modes/_profile.md` | `StateProjection(projection_type="career_positioning")` and/or versioned profile asset |
| `article-digest.md` | `Asset(asset_type="proof_point_digest")` |
| `portals.yml` | Pack config / company installation config, not global local file |
| `data/pipeline.md` | `CompanyOpportunity` records with `metadata_json.career_ops` |
| `data/applications.md` | `CompanyOpportunity` + `ServiceEngagement` statuses, backend DB source of truth |
| `reports/*.md` | `ServiceDeliverable(deliverable_type="job_evaluation_report")` + `AssetVersion` |
| `output/*.pdf` | `AssetVersion(mime_type="application/pdf")` |
| `interview-prep/story-bank.md` | `Asset`/`StateProjection` for interview story bank |
| scanner provider output | `ToolExecution` + `CompanySignal(signal_kind="opportunity")` |
| liveness check | `CompanySignal(signal_kind="risk"/"milestone")` + `ToolExecution` receipt |

---

## Implementation tasks

### Task 1: Add the Career Operations operating-model pack skeleton

**Objective:** Add a compileable `career_ops.v1` pack with manifest, departments, programs, stages, artifacts, operations, policies, signals, dashboards, and reports.

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

**Step 1: Write failing tests**

Add tests that load/compile `career_ops.v1`, validate graph JSON, and assert department/stage/artifact labels are present.

Expected assertions:

```python
from application.services.operating_model_packs import compile_pack, load_pack_definition
from domain.services.graph_validator import GraphValidator


def test_career_ops_pack_loads_and_compiles_valid_graph_json():
    definition = load_pack_definition("career_ops.v1")
    assert definition.base_pack_id == "career_ops"
    assert definition.company_type_label == "Career Operations Company"

    compiled = compile_pack(
        pack_id="career_ops.v1",
        company_name="Candidate CareerOps",
        objective="Run a selective evidence-backed job search.",
        autonomy_mode="assisted",
        ai_access_mode="managed",
        intelligence_provider="openai",
        selected_services=["job evaluation", "application packets"],
        regions=["remote"],
    )

    assert GraphValidator().validate(compiled.graph_json, strict=True, require_entry_exit=True) == []
    profile = compiled.graph_json["metadata"]["company_profile"]
    assert profile["companyType"] == "Career Operations Company"
    assert [department["label"] for department in profile["departments"]] == [
        "Candidate Profile & Strategy",
        "Market & Role Discovery",
        "Opportunity Evaluation",
        "Application Packet Studio",
        "Application Operations",
        "Interview & Negotiation Prep",
        "Pipeline Integrity & Analytics",
        "Candidate Approval & Governance",
    ]
```

**Step 2: Run test to verify failure**

Run from `backend/`:

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest tests/unit/services/test_career_ops_pack.py -q
```

Expected: FAIL because `career_ops.v1` does not exist.

**Step 3: Add pack YAML**

Follow `operating_model_packs/digital_marketing_pro/*` structure, but use neutral career-ops labels. Keep pack-specific terms in pack YAML, not core models.

**Step 4: Run test to verify pass**

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest tests/unit/services/test_career_ops_pack.py -q
```

Expected: PASS.

---

### Task 2: Teach company blueprints about `career_ops.v1`

**Objective:** Allow `POST /api/company-blueprints/compile` and `POST /api/companies/from-blueprint` to use `career_ops.v1` and aliases like `career-ops`.

**Files:**
- Modify: `backend/application/services/company_blueprints.py`
- Modify: `backend/tests/unit/services/test_company_blueprints.py`
- Test: `backend/tests/unit/api/test_company_blueprints_api.py`

**Step 1: Write failing service/API tests**

Add tests asserting:

- `CompanyBlueprintCompiler().compile(..., blueprint_id="career_ops.v1")` works.
- `blueprint_id="career-ops"` aliases to `career_ops.v1`.
- `POST /api/company-blueprints/compile` returns `metadata.operating_model_pack.pack_id == "career_ops.v1"`.
- `POST /api/companies/from-blueprint` creates a `Graph`, `GraphVersion`, and `CompanyOperatingModelInstallation` for `career_ops.v1`.

**Step 2: Run test to verify failure**

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest tests/unit/services/test_company_blueprints.py tests/unit/api/test_company_blueprints_api.py -q
```

Expected: FAIL due unknown alias/pack handling.

**Step 3: Minimal implementation**

Update `_BLUEPRINT_ALIASES` in `company_blueprints.py`:

```python
_BLUEPRINT_ALIASES = {
    # existing aliases...
    "career_ops.v1": "career_ops.v1",
    "career_ops": "career_ops.v1",
    "career-ops": "career_ops.v1",
    "career operations": "career_ops.v1",
    "job_search_ops": "career_ops.v1",
    "job-search-ops": "career_ops.v1",
}
```

Do not change `DEFAULT_BLUEPRINT_ID` yet unless product wants CareerOps to become the default.

**Step 4: Verify pass**

Same pytest command as Step 2.

---

### Task 3: Add career deliverable catalog and assembly service

**Objective:** Create a backend service that assembles a first career-ops application packet from existing backend state, using `ServiceEngagement`, `ServiceDeliverable`, `Asset`, and `AssetVersion`.

**Files:**
- Create: `backend/application/services/career_ops_deliverable_catalog.py`
- Create: `backend/application/services/career_ops_deliverables.py`
- Create: `backend/tests/unit/services/test_career_ops_deliverables.py`

**Step 1: Write failing tests**

Test cases:

1. `ensure_career_ops_service_engagement(...)` creates one idempotent catalog item and engagement with `required_pack_ids_json == ["career_ops.v1"]`.
2. `assemble_career_ops_deliverable(..., deliverable_type="job_evaluation_report")` creates one `AssetVersion` and one `ServiceDeliverable` with owner department `opportunity_evaluation`.
3. `assemble_career_ops_application_packet(...)` returns a package containing report + resume draft + cover letter draft + approval checklist.
4. Re-running assembly is idempotent for unchanged source state.
5. Metadata includes source refs: opportunity id, liveness receipt id if available, candidate profile projection id, and pack id.

**Step 2: Run test to verify failure**

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest tests/unit/services/test_career_ops_deliverables.py -q
```

Expected: FAIL because service/catalog does not exist.

**Step 3: Implement first slice**

Mirror the shape of `application/services/agency_deliverables.py`, but avoid Atlas-specific constants.

Suggested constants:

```python
ASSEMBLY_SOURCE = "career_ops_deliverable_assembly"
CATALOG_SLUG = "career-ops-application-engagement"
CATALOG_SOURCE_KEY = "career-ops-catalog:application-engagement"
REQUIRED_PACK_ID = "career_ops.v1"
```

Initial MVP deliverables:

```python
MVP_DELIVERABLE_TYPES = (
    "candidate_profile_snapshot",
    "job_liveness_receipt",
    "job_evaluation_report",
    "tailored_resume_draft",
    "cover_letter_draft",
    "application_answers",
    "application_packet",
    "interview_prep_brief",
    "followup_plan",
    "pipeline_health_report",
)
```

**Step 4: Verify pass**

Same pytest command as Step 2.

---

### Task 4: Add career opportunity normalization service

**Objective:** Model scanned jobs and application statuses in backend-owned generic state instead of markdown tables.

**Files:**
- Create: `backend/application/services/career_ops_opportunities.py`
- Create: `backend/tests/unit/services/test_career_ops_opportunities.py`

**Step 1: Write failing tests**

Test cases:

- `record_scanned_job(...)` creates/updates a `CompanySignal` with unique `source="career_ops_scan"` and `external_key=<normalized url/hash>`.
- A relevant active job creates/updates a `CompanyOpportunity` tied to the signal.
- Duplicate URLs and duplicate company+role normalize to one current opportunity.
- Closed/expired postings produce a risk/milestone signal but do not advance to evaluation-ready status.
- `metadata_json.career_ops` stores normalized title, company, location, source provider, posting URL, discovered_at, liveness status, score, and application status.

**Step 2: Run test to verify failure**

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest tests/unit/services/test_career_ops_opportunities.py -q
```

Expected: FAIL because service does not exist.

**Step 3: Implement minimal service**

Use existing `CompanySignal` and `CompanyOpportunity` fields. Do not add DB models in the first slice unless existing statuses prove insufficient.

**Step 4: Verify pass**

Same pytest command as Step 2.

---

### Task 5: Add scanner provider skeleton with fake provider tests

**Objective:** Transfer Career-Ops' zero-token scanner pattern into a backend-owned service with provider adapters and durable receipts.

**Files:**
- Create: `backend/application/services/career_ops_scanner.py`
- Create: `backend/application/services/career_ops_scan_providers.py`
- Create: `backend/tests/unit/services/test_career_ops_scanner.py`

**Step 1: Write failing tests**

Use a fake provider returning Greenhouse/Ashby/Lever-shaped normalized jobs. Assert:

- Scanner returns normalized `{title, company, url, location, provider}` rows.
- Title/location/salary filters behave like the origin scanner: missing location/salary passes conservatively; block list wins unless always-allow applies.
- Results are deduped before persistence.
- A `ToolExecution` or equivalent receipt is persisted for the scan batch.

**Step 2: Run test to verify failure**

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest tests/unit/services/test_career_ops_scanner.py -q
```

**Step 3: Implement fake-provider-first scanner**

Do not scrape live sites yet. Build provider interface and test against fixtures first.

Provider interface:

```python
class CareerOpsScanProvider(Protocol):
    id: str
    def fetch(self, config: dict[str, Any]) -> list[CareerOpsJobPosting]: ...
```

**Step 4: Verify pass**

Same pytest command as Step 2.

---

### Task 6: Implement liveness gate and A-G evaluation contract

**Objective:** Make liveness a required precondition and define a stable job evaluation payload, without relying on local markdown reports.

**Files:**
- Create: `backend/application/services/career_ops_evaluation.py`
- Create: `backend/tests/unit/services/test_career_ops_evaluation.py`

**Step 1: Write failing tests**

Test cases:

- Closed posting input returns `status="closed"`, blocks evaluation, and records a signal.
- Active posting fixture produces sections `A` through `G` with required keys.
- Score below threshold marks recommendation as `do_not_apply` or `hold`, not packet-ready.
- Score above threshold marks packet-ready but still requires candidate approval before any external side effect.
- Evaluation uses exact source refs for candidate profile/CV/proof points and never invents claims.

**Step 2: Run test to verify failure**

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest tests/unit/services/test_career_ops_evaluation.py -q
```

**Step 3: Implement deterministic fixture evaluator first**

For the first PR, use deterministic rule-based payload assembly around fixtures and source refs. LLM-backed evaluation can be a later operation template once the contract is stable.

**Step 4: Verify pass**

Same pytest command as Step 2.

---

### Task 7: Add PDF/application packet renderer smoke

**Objective:** Reuse ForgeGraph's browser-rendered HTML/PDF handoff pattern for career packets.

**Files:**
- Create/modify renderer service only after checking existing `deliverable_formatting` / report renderer code.
- Create: `backend/tests/unit/services/test_career_ops_packet_renderer.py`

**Step 1: Write failing smoke test**

The test should create a fake profile + job evaluation + resume draft and assert:

- HTML artifact exists and contains no internal leakage (`model`, `prompt`, `provenance_json`, `Hermes`, raw tool calls).
- PDF bytes start with `%PDF` when renderer is available.
- Packet manifest lists all included artifacts and source refs.
- Markdown source is internal-only and not included in the client/candidate-facing ZIP.

**Step 2: Implement minimal renderer**

Use existing ForgeGraph package rendering patterns; do not hand-roll PDF bytes.

**Step 3: Verify**

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest tests/unit/services/test_career_ops_packet_renderer.py -q
```

---

### Task 8: Add API/read model for career pipeline dashboard

**Objective:** Provide the backend shape needed for a future TUI/web dashboard without building UI first.

**Files:**
- Create: `backend/application/services/career_ops_pipeline.py`
- Optionally create: `backend/adapters/api/company_ops/career_ops.py` or extend existing company-ops views if there is a clean pattern.
- Test: `backend/tests/unit/services/test_career_ops_pipeline.py`
- Test: `backend/tests/unit/api/test_career_ops_pipeline_api.py` if an API is added.

**Step 1: Write failing tests**

Assert pipeline summary includes:

- counts by status (`discovered`, `evaluated`, `packet_ready`, `applied`, `interview`, `offer`, `rejected`, `skip`)
- top opportunities by score
- stale follow-ups
- broken/missing artifact warnings
- duplicate warnings
- approval-required packets

**Step 2: Implement read model over existing primitives**

No new durable source of truth; compute from backend records and persist snapshots only as optional `StateProjection` if needed.

**Step 3: Verify**

Run focused service/API tests.

---

### Task 9: Management command or seed script for a local CareerOps company

**Objective:** Let Mike create a local test company with realistic fixture data from the backend, not from Hermes/local files.

**Files:**
- Create: `backend/infrastructure/orm/management/commands/seed_career_ops_company.py`
- Create: `backend/tests/unit/management/test_seed_career_ops_company.py`

**Step 1: Write failing test**

Assert command creates:

- one `Graph` company
- one `GraphVersion`
- one `CompanyOperatingModelInstallation(pack_id="career_ops.v1")`
- one `CompanyProgram` with 12 stages
- candidate profile `StateProjection`
- CV/proof-point `AssetVersion`
- one fake scanned opportunity
- one liveness receipt
- one evaluation report deliverable
- one application packet deliverable

**Step 2: Implement idempotent command**

Use `--email`, `--company-name`, `--dry-run` arguments. Make it safe to rerun without duplicates.

**Step 3: Verify**

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest tests/unit/management/test_seed_career_ops_company.py -q
```

---

## Verification commands for the full first slice

Run from `C:\Users\mathi\projects\forgegraph\backend`:

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest \
  tests/unit/services/test_career_ops_pack.py \
  tests/unit/services/test_company_blueprints.py \
  tests/unit/api/test_company_blueprints_api.py \
  tests/unit/services/test_career_ops_deliverables.py \
  tests/unit/services/test_career_ops_opportunities.py \
  tests/unit/services/test_career_ops_scanner.py \
  tests/unit/services/test_career_ops_evaluation.py \
  tests/unit/management/test_seed_career_ops_company.py \
  -q

UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run ruff check \
  application/services/company_blueprints.py \
  application/services/career_ops_deliverable_catalog.py \
  application/services/career_ops_deliverables.py \
  application/services/career_ops_opportunities.py \
  application/services/career_ops_scanner.py \
  application/services/career_ops_scan_providers.py \
  application/services/career_ops_evaluation.py \
  infrastructure/orm/management/commands/seed_career_ops_company.py \
  tests/unit/services/test_career_ops_pack.py \
  tests/unit/services/test_career_ops_deliverables.py \
  tests/unit/services/test_career_ops_opportunities.py \
  tests/unit/services/test_career_ops_scanner.py \
  tests/unit/services/test_career_ops_evaluation.py \
  tests/unit/management/test_seed_career_ops_company.py

DEBUG=1 USE_SQLITE=1 USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run python manage.py check
```

If route/API files are added, also run the route security matrix tests before pushing:

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest tests/integration/adapters/test_security_matrix.py -q
```

## First PR acceptance criteria

- `career_ops.v1` exists and compiles through the existing operating-model pack compiler.
- Company blueprint compile/from-blueprint supports `career_ops.v1` and `career-ops` alias.
- A seed command can create a ForgeGraph CareerOps company with backend-owned candidate profile, one scanned opportunity, one liveness gate, one evaluation report, and one application packet.
- No local markdown/SQLite file is the source of truth.
- No external application submission is performed.
- Human approval is explicit before any future external send/submit side effect.
- Tests prove idempotency and deduplication for company setup, opportunity recording, and deliverable assembly.
- Runtime invariants remain true: backend owns durable state; worker/engine state is ephemeral.

## Risks and tradeoffs

1. **Vertical-specific core code creep**
   - Keep career-specific concepts in pack YAML and service metadata first. Add core models only after generic primitives cannot support the workflow.

2. **Status mismatch**
   - `CompanyOpportunity.status` is commercial-funnel oriented. In the first slice, keep career application status in `metadata_json.career_ops.application_status`; only add a new status model if query/API ergonomics suffer.

3. **PDF rendering scope**
   - Do not start by matching Career-Ops' polished resume rendering exactly. First prove provenance, packet shape, and PDF smoke. Polish second.

4. **Live job portal fragility**
   - Start with provider fixture tests and fake provider. Then add one live provider adapter at a time with explicit receipts and rate-limit/error handling.

5. **Trademark/brand**
   - Treat `Career-Ops` as the inspected reference. The ForgeGraph pack should be named `career_ops` or `career_search_ops` and should not reuse upstream branding, logos, docs copy, or trademarked presentation.

6. **Ethics/no-auto-apply**
   - Preserve the origin's human-in-the-loop stance. ForgeGraph should recommend and prepare packets, not mass-submit applications.

## Open questions before implementation

1. Should the visible product name be `CareerOps`, `Career Search Ops`, or something ForgeGraph-branded?
2. Should the first local company be for Mike personally, or a generic demo candidate fixture?
3. Should `career_ops.v1` be a separate pack or a `digital_marketing_pro`-style pack plus service package? I recommend separate pack.
4. Should we prioritize backend API + seed command first, or also include a lightweight dashboard/read-model endpoint in PR 1? I recommend backend + seed command first, dashboard read model second.
