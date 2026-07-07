# CareerOps Tailored CV + Cover Letter ATS Alignment Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Build step 2 of the CareerOps flow: for each accepted job opportunity, generate a source-backed content alignment report, ATS-optimized tailored CV draft, and cover letter draft while keeping external side effects disabled and approval-gated.

**Architecture:** Add a deterministic CareerOps alignment layer between fit evaluation and application packet persistence. The layer consumes the base CV asset (`career_ops:cv_source`), opportunity/job description metadata, and existing evaluation matches; it emits structured, source-backed draft content and quality metadata into the existing `Asset` / `AssetVersion` / `ServiceDeliverable` pipeline. Rendering/export can follow later; this slice focuses on content truth, keyword alignment, ATS structure, and exact-version packet readiness.

**Tech Stack:** Django backend, existing ForgeGraph ORM primitives (`Asset`, `AssetVersion`, `ServiceDeliverable`, `CompanyOpportunity`, `Run`, `DecisionRecord`), pytest, ruff, deterministic Python services under `backend/application/services/`.

---

## Product framing

The real CareerOps sequence is:

1. **Find jobs** — already implemented through live discovery / live-search skill.
2. **Create dedicated CV + cover letter** — current task.
3. **Apply** — later; still manual/approval-gated and side-effect disabled by default.

For step 2, optimize first for:

- Content alignment to the actual job posting.
- ATS parseability and keyword coverage.
- Truthfulness / no invented claims.
- Opportunity isolation.
- Review-ready artifacts with exact-version approval gates.

Do **not** implement auto-apply, browser submission, employer email sending, or visual PDF polish in this slice.

---

## Current context from repo inspection

Existing relevant files:

- `backend/application/services/career_ops_packet_builder.py`
  - Currently returns `tailored_resume: None`.
  - Cover letter is `_cover_letter_stub(...)` only.
  - Reads candidate facts from `Asset(source_key="career_ops:cv_source")` metadata: `summary`, `proof_points`.
- `backend/application/services/career_ops_quality_gates.py`
  - Already fail-closes on base CV, source refs, internal leakage, employer identity, exact-version approval, side-effect guard.
  - Does **not yet** validate ATS structure, unsupported claims, keyword alignment, or document-specific content quality.
- `backend/application/services/career_ops_artifacts.py`
  - Persists opportunity-isolated deliverables/assets by `source_key=f"career_ops:{opportunity.id}:{deliverable_type}"`.
- `backend/application/services/career_ops_pipeline.py`
  - Writes liveness, evaluation, and application packet deliverables.
  - Does not yet write standalone `tailored_resume_html` or `cover_letter_draft` deliverables.
- `backend/application/services/career_ops_graph_contract.py`
  - Already declares deliverable types: `tailored_resume_html`, `tailored_resume_pdf`, `cover_letter_draft`, `cover_letter_pdf`, `application_packet`.
- Existing tests:
  - `backend/tests/unit/services/test_career_ops_packet_builder.py`
  - `backend/tests/unit/services/test_career_ops_quality_gates.py`
  - `backend/tests/unit/services/test_career_ops_artifacts.py`
  - `backend/tests/unit/services/test_career_ops_pipeline.py`

Constraints to preserve:

- Base CV is canonical source of candidate truth.
- No unsupported candidate claims.
- No employer-facing side effects.
- One opportunity must not share or overwrite another opportunity's artifacts.
- Exact packet/asset version approval remains required before apply.
- Artifacts can be JSON/HTML drafts in this slice; PDF export is later unless trivial.

---

## Proposed data shape

### Alignment report payload

Create a deterministic intermediate payload shaped like:

```python
{
    "status": "aligned" | "blocked",
    "opportunity": {
        "id": "...",
        "employer_name": "...",
        "role_title": "...",
        "job_url": "...",
    },
    "keyword_alignment": {
        "matched_keywords": [
            {
                "keyword": "FastAPI",
                "job_source": "job_description",
                "cv_source_ref": {"type": "cv_proof_point", "index": 0},
                "evidence": "Built production APIs with Python and FastAPI...",
            }
        ],
        "missing_keywords": [
            {
                "keyword": "AWS Lambda",
                "action": "do_not_claim_without evidence",
            }
        ],
        "coverage_score": 0.0,
    },
    "positioning": {
        "headline": "Backend / AI Platform Engineer",
        "summary_bullets": ["..."],
        "emphasis_order": ["Python/FastAPI", "AI workflows", "PostgreSQL/Redis"],
    },
    "ats": {
        "required_sections": ["Summary", "Skills", "Experience", "Projects", "Education"],
        "warnings": [],
        "pass": True,
    },
    "source_refs": [...],
    "quality": {
        "source_backed_claims": True,
        "no_invented_candidate_facts": True,
        "external_side_effects_allowed": False,
        "live_ready": False,
    },
}
```

### Tailored resume draft payload

Represent the CV as structured text first, not a PDF:

```python
{
    "status": "draft",
    "format": "ats_resume_v1",
    "opportunity": {...},
    "sections": [
        {"heading": "SUMMARY", "items": ["..."]},
        {"heading": "TECHNICAL SKILLS", "items": ["Python", "FastAPI", "Django", "PostgreSQL"]},
        {"heading": "SELECTED EXPERIENCE", "items": [{"text": "...", "source_ref": {...}}]},
        {"heading": "PROJECTS", "items": [...]},
        {"heading": "EDUCATION", "items": [...]},
    ],
    "plain_text": "...",
    "source_refs": [...],
    "ats": {"pass": True, "warnings": []},
    "quality": {...},
}
```

### Cover letter draft payload

```python
{
    "status": "draft",
    "format": "cover_letter_v1",
    "opportunity": {...},
    "paragraphs": [
        "Opening aligned to role/company.",
        "Evidence paragraph using only CV proof points.",
        "Closing with availability/interest, no unsupported visa/salary claims.",
    ],
    "source_refs": [...],
    "quality": {...},
}
```

---

## Task 1: Add deterministic alignment service tests

**Objective:** Define the behavior for content alignment before production code exists.

**Files:**

- Create: `backend/tests/unit/services/test_career_ops_content_alignment.py`
- Create later: `backend/application/services/career_ops_content_alignment.py`

**Step 1: Write failing tests**

Add tests for:

1. `build_career_ops_alignment_report(...)` matches job keywords only when supported by CV proof points.
2. Unsupported job keywords become `missing_keywords`, not invented resume claims.
3. Location/work-authorization facts must only appear if present in candidate facts/constraints.
4. ATS sections are present and ordered.
5. Internal terms like `Hermes`, `ForgeGraph`, `metadata_json`, `prompt`, `provenance_json` are absent from external-facing text.

Representative test skeleton:

```python
from __future__ import annotations

from application.services.career_ops_content_alignment import build_career_ops_alignment_report


def test_alignment_report_matches_supported_keywords_and_flags_gaps() -> None:
    candidate = {
        "summary": "Backend engineer building Python APIs and AI workflow systems.",
        "proof_points": [
            "Built production APIs using Python, FastAPI, PostgreSQL, and Redis.",
            "Delivered RAG and LangGraph-style agentic workflow prototypes with observability.",
        ],
    }
    posting = {
        "title": "Backend Engineer, AI Platform",
        "company": "Acme AI",
        "url": "https://jobs.example.test/acme/backend-ai",
        "description": "Python FastAPI PostgreSQL AWS Lambda backend engineer for RAG workflows.",
    }

    report = build_career_ops_alignment_report(candidate_facts=candidate, posting=posting)

    matched = {item["keyword"] for item in report["keyword_alignment"]["matched_keywords"]}
    missing = {item["keyword"] for item in report["keyword_alignment"]["missing_keywords"]}
    assert {"Python", "FastAPI", "PostgreSQL", "RAG"} <= matched
    assert "AWS Lambda" in missing
    assert report["quality"]["no_invented_candidate_facts"] is True
    assert report["quality"]["external_side_effects_allowed"] is False
```

**Step 2: Run test to verify RED**

```bash
cd backend
FORGEGRAPH_ENV_FILE= DEBUG=1 SECRET_KEY='***' USE_SQLITE=true USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 SQLITE_DB_PATH=.hermes/career_ops_alignment.sqlite3 UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest tests/unit/services/test_career_ops_content_alignment.py -q
```

Expected: FAIL because `career_ops_content_alignment.py` does not exist.

---

## Task 2: Implement `career_ops_content_alignment.py`

**Objective:** Add deterministic source-backed alignment primitives.

**Files:**

- Create: `backend/application/services/career_ops_content_alignment.py`
- Test: `backend/tests/unit/services/test_career_ops_content_alignment.py`

**Implementation requirements:**

- No LLM calls in this slice.
- Extract job keywords from title/description using a curated set plus existing keywords from `career_ops_evaluation.py` if useful.
- Match keywords against candidate `summary` and `proof_points`.
- Return source refs with proof point indexes.
- Missing keywords should produce mitigation notes, not resume claims.
- Compute a simple deterministic `coverage_score`.
- Build ATS warnings from structure/content only.

**Suggested minimal constants:**

```python
ATS_REQUIRED_SECTIONS = ("SUMMARY", "TECHNICAL SKILLS", "SELECTED EXPERIENCE", "PROJECTS", "EDUCATION")
INTERNAL_LEAKAGE_TOKENS = ("hermes", "forgegraph", "metadata_json", "provenance_json", "prompt", "raw tool")
CAREER_OPS_KEYWORDS = (
    "Python", "FastAPI", "Django", "PostgreSQL", "Redis", "Celery", "RAG", "LangGraph",
    "agentic workflows", "AI", "backend", "API", "microservices", "observability",
    "AWS", "AWS Lambda", "serverless", "TypeScript", "React", "Next.js",
)
```

**Step 1:** Implement helper functions:

- `_candidate_fact_texts(candidate_facts)`
- `_extract_job_keywords(posting)`
- `_match_keyword(keyword, fact_texts)`
- `_internal_leakage(text)`
- `_coverage_score(matched, total)`

**Step 2:** Implement:

```python
def build_career_ops_alignment_report(*, candidate_facts: dict[str, Any], posting: dict[str, Any]) -> dict[str, Any]:
    ...
```

**Step 3: Verify GREEN**

Run the same focused test command. Expected: PASS.

---

## Task 3: Generate tailored ATS resume draft payload

**Objective:** Replace `tailored_resume: None` with a structured, ATS-friendly resume draft backed by the alignment report.

**Files:**

- Modify: `backend/application/services/career_ops_content_alignment.py`
- Modify: `backend/tests/unit/services/test_career_ops_content_alignment.py`
- Later integrate: `backend/application/services/career_ops_packet_builder.py`

**Tests to add first:**

1. Resume draft includes required ATS sections in order.
2. Resume draft includes matched keywords only if source-backed.
3. Resume draft excludes unsupported job keywords.
4. Resume draft plain text has no placeholders and no internal leakage.
5. Resume draft quality has `live_ready=False` and `external_side_effects_allowed=False`.

**API:**

```python
def build_tailored_resume_draft(*, candidate_facts: dict[str, Any], posting: dict[str, Any], alignment: dict[str, Any]) -> dict[str, Any]:
    ...
```

**Content rules:**

- Summary: 2-3 bullets max, aligned to role archetype and matched evidence.
- Skills: include matched supported skills first, then safe base skills from CV facts.
- Experience/projects: use proof points verbatim or lightly reframed, but keep a `source_ref` per bullet.
- Do not add metrics unless the base CV/proof point contains them.
- Do not add visa/work-auth claims unless candidate facts explicitly include them.
- Do not include styling tables, columns, images, icons, or hidden text.

**Run:**

```bash
cd backend
FORGEGRAPH_ENV_FILE= DEBUG=1 SECRET_KEY='***' USE_SQLITE=true USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 SQLITE_DB_PATH=.hermes/career_ops_alignment.sqlite3 UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest tests/unit/services/test_career_ops_content_alignment.py -q
```

---

## Task 4: Generate source-backed cover letter draft payload

**Objective:** Create a role-specific cover letter draft that uses the same evidence discipline as the tailored CV.

**Files:**

- Modify: `backend/application/services/career_ops_content_alignment.py`
- Modify: `backend/tests/unit/services/test_career_ops_content_alignment.py`

**Tests to add first:**

1. Cover letter references correct employer and role.
2. Cover letter contains at least one evidence-backed paragraph.
3. Cover letter does not mention unsupported skills from missing keywords.
4. Cover letter does not include internal leakage tokens.
5. Cover letter keeps side effects disabled.

**API:**

```python
def build_cover_letter_draft(*, candidate_facts: dict[str, Any], posting: dict[str, Any], alignment: dict[str, Any]) -> dict[str, Any]:
    ...
```

**Content structure:**

- Opening: role/company + concise positioning.
- Evidence paragraph: 1-2 source-backed proof points aligned to role needs.
- Gap-safe paragraph: if important gaps exist, avoid pretending; emphasize adjacent supported evidence only.
- Closing: interest + manual next step, no auto-apply language.

---

## Task 5: Integrate drafts into packet builder

**Objective:** Make the existing packet builder produce a tailored resume and cover letter instead of stubs.

**Files:**

- Modify: `backend/application/services/career_ops_packet_builder.py`
- Modify: `backend/tests/unit/services/test_career_ops_packet_builder.py`

**Tests to add first:**

1. With base CV/proof points, `payloads.packet["artifacts"]["tailored_resume"]` is a draft payload, not `None`.
2. Cover letter status changes from `draft_stub` to `draft`.
3. Packet includes `alignment_report` or equivalent under `packet["alignment"]`.
4. Packet remains `status="draft"`, `live_ready=False`, `requires_candidate_approval=True`.
5. Without base CV, packet remains blocked and does not fabricate a resume.

**Implementation:**

In `build_career_ops_packet_payloads(...)`:

1. Build `posting` as now.
2. Read `candidate_facts` as now.
3. If candidate facts exist and posting is not expired:
   - `alignment = build_career_ops_alignment_report(...)`
   - `tailored_resume = build_tailored_resume_draft(...)`
   - `cover_letter = build_cover_letter_draft(...)`
4. If missing CV or expired posting, keep drafts absent/blocked.
5. Include source refs from alignment in packet source refs.

---

## Task 6: Persist standalone resume and cover letter deliverables in pipeline

**Objective:** Store tailored resume and cover letter as their own opportunity-isolated deliverables, not only embedded inside `application_packet`.

**Files:**

- Modify: `backend/application/services/career_ops_pipeline.py`
- Modify: `backend/tests/unit/services/test_career_ops_pipeline.py`
- Possibly modify: `backend/tests/unit/services/test_career_ops_artifacts.py`

**Tests to add first:**

1. Running `run_career_ops_url_pipeline(...)` with base CV creates deliverables:
   - `job_liveness_receipt`
   - `job_evaluation_report`
   - `tailored_resume_html` or `tailored_resume_draft` if choosing JSON-first naming
   - `cover_letter_draft`
   - `application_packet`
2. The resume and cover letter deliverables have `metadata_json["career_ops"]["opportunity_id"]` equal to the target opportunity.
3. Two opportunities get separate resume and cover letter assets.
4. `external_side_effects_allowed=False` on all deliverables/assets.

**Implementation:**

After evaluation and before application packet write:

```python
resume_deliverable, resume_version = write_career_ops_deliverable(
    engagement=engagement,
    run=run,
    task=tasks_by_stage.get("stage_06_application_packet"),
    opportunity=opportunity,
    deliverable_type="tailored_resume_html",
    title=f"Tailored resume — {opportunity.title}",
    payload=payloads.packet["artifacts"]["tailored_resume"],
)

cover_deliverable, cover_version = write_career_ops_deliverable(
    engagement=engagement,
    run=run,
    task=tasks_by_stage.get("stage_06_application_packet"),
    opportunity=opportunity,
    deliverable_type="cover_letter_draft",
    title=f"Cover letter — {opportunity.title}",
    payload=payloads.packet["artifacts"]["cover_letter"],
)
```

Include both versions in `deliverable_versions` passed to `request_packet_approval(...)`.

---

## Task 7: Extend quality gates for ATS/content readiness

**Objective:** Make readiness fail closed on ATS/document-content problems, not just base CV and approval.

**Files:**

- Modify: `backend/application/services/career_ops_quality_gates.py`
- Modify: `backend/tests/unit/services/test_career_ops_quality_gates.py`

**Tests to add first:**

1. `test_packet_readiness_blocks_missing_tailored_resume`
2. `test_packet_readiness_blocks_resume_without_required_ats_sections`
3. `test_packet_readiness_blocks_unsupported_candidate_claim`
4. `test_packet_readiness_blocks_internal_leakage_in_resume_text`
5. `test_packet_readiness_still_blocks_without_exact_version_approval_even_when_content_quality_passes`

**Implementation strategy:**

Add checks:

```python
checks["ats_resume_structure"] = "pass" | "blocked"
checks["claim_source_map"] = "pass" | "blocked"
checks["cover_letter_present"] = "pass" | "blocked"
checks["no_document_internal_leakage"] = "pass" | "blocked"
```

For this slice, inspect `packet_version.provenance_json["career_ops"]` and embedded artifact payloads. Later, if standalone deliverables become source of truth, the readiness command can resolve versions via `deliverable_versions`.

---

## Task 8: Add command/API ergonomics for step 2 review

**Objective:** Make it easy to generate/review the dedicated CV + cover letter for accepted opportunities before applying.

**Files:**

- Existing likely command: `backend/infrastructure/orm/management/commands/run_career_ops_url_pipeline.py`
- Consider create: `backend/infrastructure/orm/management/commands/build_career_ops_application_packet.py`
- Tests: `backend/tests/unit/management/test_build_career_ops_application_packet.py`

**Recommendation:** Prefer a new explicit command if we want to regenerate packets for already-discovered `CompanyOpportunity` records, rather than re-scanning URLs.

Command shape:

```bash
python manage.py build_career_ops_application_packet \
  --company-id <company_id> \
  --opportunity-id <opportunity_id> \
  --idempotency-key career-ops-packet:<opportunity_id>:v1 \
  --dry-run
```

JSON output should include:

```json
{
  "status": "ok",
  "opportunity_id": "...",
  "tailored_resume_asset_version_id": "...",
  "cover_letter_asset_version_id": "...",
  "packet_asset_version_id": "...",
  "readiness": {"status": "blocked", "checks": {...}},
  "external_side_effects_allowed": false
}
```

Do this only after Tasks 1-7 pass.

---

## Task 9: Docker verification with real persisted opportunities

**Objective:** Prove the step-2 flow runs against the existing Docker ForgeGraph stack and the 4 live-search-skill opportunities.

**Files:**

- Create verification script: `backend/.hermes/verify_career_ops_application_packets.py`
- Save command output under: `backend/.hermes/career_ops_application_packets_<timestamp>.json`

**Procedure:**

1. Use the company/opportunity IDs from the latest live-search-skill run or query opportunities by `posting_source_mode=live_search_skill`.
2. For each of the 4 opportunities:
   - Generate packet/drafts.
   - Verify tailored resume and cover letter deliverables exist.
   - Verify source refs and opportunity isolation.
   - Verify readiness remains blocked pending exact candidate approval.
   - Verify `external_side_effects_allowed=False`.
3. Do **not** apply.

Docker command style on Mike's Windows/Git Bash:

```bash
cd /c/Users/mathi/projects/forgegraph
MSYS_NO_PATHCONV=1 docker compose exec -T backend sh -lc '/app/.venv/bin/python3 manage.py build_career_ops_application_packet ...'
```

If running tests in Docker:

```bash
MSYS_NO_PATHCONV=1 docker compose exec -T backend sh -lc 'UV_PROJECT_ENVIRONMENT=/tmp/forgegraph-career-ops-packet-test-venv uv run --group dev pytest tests/unit/services/test_career_ops_content_alignment.py tests/unit/services/test_career_ops_packet_builder.py tests/unit/services/test_career_ops_quality_gates.py tests/unit/services/test_career_ops_pipeline.py -q'
```

---

## Acceptance criteria for this slice

- Each accepted opportunity can produce a distinct tailored CV draft and cover letter draft.
- Drafts are source-backed by the base CV/proof points and job posting metadata.
- Unsupported job requirements are flagged as gaps; they are not invented into the CV or cover letter.
- CV draft includes ATS-friendly required sections and plain text.
- Internal leakage checks cover generated document text, not only provenance metadata.
- `ServiceDeliverable` / `Asset` / `AssetVersion` rows are opportunity-isolated.
- `application_packet` includes exact versions for tailored resume and cover letter.
- Readiness remains `blocked` until exact-version approval, even when content checks pass.
- External side effects remain disabled everywhere.
- Host test suite and Docker-focused verification pass.

---

## Verification commands

Focused host tests:

```bash
cd /c/Users/mathi/projects/forgegraph/backend
FORGEGRAPH_ENV_FILE= DEBUG=1 SECRET_KEY='***' USE_SQLITE=true USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 SQLITE_DB_PATH=.hermes/career_ops_step2.sqlite3 UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest \
  tests/unit/services/test_career_ops_content_alignment.py \
  tests/unit/services/test_career_ops_packet_builder.py \
  tests/unit/services/test_career_ops_artifacts.py \
  tests/unit/services/test_career_ops_quality_gates.py \
  tests/unit/services/test_career_ops_pipeline.py \
  -q
```

Ruff:

```bash
cd /c/Users/mathi/projects/forgegraph/backend
UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run ruff check \
  application/services/career_ops_content_alignment.py \
  application/services/career_ops_packet_builder.py \
  application/services/career_ops_pipeline.py \
  application/services/career_ops_quality_gates.py \
  tests/unit/services/test_career_ops_content_alignment.py \
  tests/unit/services/test_career_ops_packet_builder.py \
  tests/unit/services/test_career_ops_pipeline.py \
  tests/unit/services/test_career_ops_quality_gates.py
```

Django check:

```bash
cd /c/Users/mathi/projects/forgegraph/backend
FORGEGRAPH_ENV_FILE= DEBUG=1 SECRET_KEY='***' USE_SQLITE=true USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 SQLITE_DB_PATH=.hermes/career_ops_step2_check.sqlite3 UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run python manage.py check
```

Docker focused tests:

```bash
cd /c/Users/mathi/projects/forgegraph
MSYS_NO_PATHCONV=1 docker compose exec -T backend sh -lc 'UV_PROJECT_ENVIRONMENT=/tmp/forgegraph-career-ops-step2-test-venv uv run --group dev pytest tests/unit/services/test_career_ops_content_alignment.py tests/unit/services/test_career_ops_packet_builder.py tests/unit/services/test_career_ops_quality_gates.py tests/unit/services/test_career_ops_pipeline.py -q'
```

---

## Risks and tradeoffs

1. **Base CV metadata may be too sparse.** Current `_candidate_facts` only reads summary and proof points. If Miguel's full CV text is not stored as structured metadata, alignment will be limited. The safe approach is to block or produce sparse drafts rather than invent.
2. **ATS optimization can become fake keyword stuffing.** We should score coverage and include supported keywords only; missing keywords stay gaps.
3. **PDF export is tempting but premature.** Content correctness should land first. PDF/HTML rendering can be a follow-up once drafts are trustworthy.
4. **LLM generation would improve prose but increase risk.** Start deterministic. Later, an LLM can rephrase only within a source-ref constrained schema and must pass claim validation.
5. **Opportunity isolation matters.** Every generated CV/cover letter must be keyed by opportunity, not just engagement, to prevent employer mix-ups.

---

## Open questions for Mike before implementation

1. Should the first implementation generate **structured JSON + plain text only**, or also simple HTML for the tailored CV?
2. Should we tailor based only on the existing base CV metadata/proof points, or should we first promote the full `miguel-athie-cv.txt` into a richer structured `cv_source` asset?
3. For cover letters, do you want a concise modern note (~250 words) or a more formal full-page letter?
4. Should each of the 4 current opportunities get packets immediately after implementation, or should we build/review one exemplar first and then batch the rest?

---

## Recommended execution order

1. Implement Tasks 1-5 first: alignment + tailored resume + cover letter embedded in packet.
2. Run focused tests and inspect one generated packet payload.
3. Implement Tasks 6-7: standalone deliverables + quality gates.
4. Add Task 8 command only if we need packet generation from existing opportunities without re-running URL intake.
5. Verify against Docker with the 4 persisted live-search opportunities.
6. Only after review/approval: plan apply/submission workflow.
