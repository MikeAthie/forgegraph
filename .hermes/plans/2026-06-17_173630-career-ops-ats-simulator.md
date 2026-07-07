# CareerOps ATS Simulator Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Add a ForgeGraph-native ATS simulator that evaluates each tailored CareerOps resume/application packet before approval/apply, producing deterministic ATS scorecards, keyword gaps, formatting/parseability findings, recruiter-style feedback, and source-backed improvement recommendations.

**Architecture:** Implement a backend-owned deterministic simulator service that consumes the already-persisted CareerOps packet/resume/cover-letter payloads and the job posting metadata, then persists an `ats_simulation_report` deliverable/asset version alongside `tailored_resume_html`, `cover_letter_draft`, and `application_packet`. Keep it no-LLM by default, source-bounded, and fail-closed: it may recommend improvements, but it must not invent candidate facts or enable employer-facing side effects.

**Tech Stack:** Django backend, existing ForgeGraph ORM primitives (`Asset`, `AssetVersion`, `ServiceDeliverable`, `CompanyOpportunity`, `Run`, `TaskRecord`, `DecisionRecord`), current CareerOps services/tests, Python deterministic scoring helpers, host SQLite/locmem test harness, Docker-backed live Postgres verification.

---

## Reference Sources Inspected

Pinned fresh shallow clones under `/tmp/forgegraph-ats-refs`:

| Repo | Commit inspected | Extracted pattern |
|---|---:|---|
| `https://github.com/santifer/career-ops` | `349bacc9d9ad377d6d85ae35fe87625c1b3a6114` | `scan-ats-full.mjs` treats ATS as a provider ecosystem: Greenhouse/Lever/Ashby/Workday directories, safe slug validation, 24h cache, dedupe, freshness filtering, optional Playwright liveness, append to pipeline. For ForgeGraph: use ATS/provider metadata and liveness as provenance/context, not as a resume-scoring black box. |
| `https://github.com/7vik2005/ProHire-Nexus` | `c3a9b905bbdefd38bacec8377c5a8e72162e1308` | `services/utils/src/routes.ts` exposes `/resume-analyser`: JSON schema with `atsScore`, `scoreBreakdown.formatting/keywords/structure/readability`, `suggestions[{category, issue, recommendation, priority}]`, `strengths`, `summary`. Frontend renders score color thresholds. For ForgeGraph: use this user-facing report shape, but generate deterministically and source-bounded. |
| `https://github.com/geeksprep/geeksprep-ats-resume-roast` | `b21c622ccb9b0bef5e14657a61d9419a911de76f` | Static product copy promises ATS score, keyword gaps, line-by-line/recruiter-style critique, and improvement loop. For ForgeGraph: add human-readable “roast” feedback section without being flippant in employer-facing artifacts. |
| `https://github.com/Nimra-Youns/AI-Resume-Optimizer` | `2dd4bad57c10f3d1c992414ccb3dfc80eca4ae90` | `app.py` uses separate actions: analyze resume, extract keywords by category, rewrite professional summary, optimize for ATS, interview prep. For ForgeGraph: split simulator output into keyword extraction, compatibility issues, formatting recommendations, and section-specific optimization suggestions. |

## Current ForgeGraph Context

Current implemented Step 2 files:

- `backend/application/services/career_ops_content_alignment.py`
  - Builds alignment report, ATS-section resume draft, cover letter draft, claim/source maps.
- `backend/application/services/career_ops_packet_builder.py`
  - Builds liveness/evaluation/alignment/application packet payload.
- `backend/application/services/career_ops_artifacts.py`
  - Persists CareerOps deliverables as `Asset` + `AssetVersion` + `ServiceDeliverable`.
- `backend/application/services/career_ops_pipeline.py`
  - Persists liveness/evaluation/tailored resume/cover letter/application packet deliverables.
- `backend/application/services/career_ops_quality_gates.py`
  - Readiness gates already check base CV, source refs, ATS sections, claim source map, internal leakage, exact-version approval, side effects disabled.
- `backend/infrastructure/orm/management/commands/build_career_ops_application_packet.py`
  - Command path for existing opportunities.

Current gap:

- We have an ATS-safe resume draft and readiness gates, but no simulated ATS screen outcome.
- No `atsScore` or score breakdown for operator review.
- No explicit keyword density/coverage diagnostics beyond raw alignment coverage.
- No recruiter-style resume critique/improvement suggestions.
- Readiness does not require an ATS simulation result or threshold.
- The live Docker packet run has four opportunities with packets/resumes/cover letters, which are good fixtures for Docker verification.

---

## Proposed ATS Simulator Contract

Add a report payload shaped like:

```json
{
  "status": "simulated",
  "format": "career_ops_ats_simulation_v1",
  "opportunity": {
    "id": "<opportunity-id>",
    "employer_name": "...",
    "role_title": "...",
    "job_url": "...",
    "ats_provider_hint": "greenhouse|lever|ashby|workday|linkedin|aggregator|unknown"
  },
  "atsScore": 88,
  "scoreBand": "send_ready|human_review|improvement_review|blocked",
  "thresholds": {
    "send_ready": 90,
    "human_review": 85,
    "improvement_review": 70
  },
  "scoreBreakdown": {
    "formatting": { "score": 18, "max": 20, "feedback": "..." },
    "keywords": { "score": 28, "max": 35, "feedback": "..." },
    "structure": { "score": 18, "max": 20, "feedback": "..." },
    "readability": { "score": 12, "max": 15, "feedback": "..." },
    "risk": { "score": 9, "max": 10, "feedback": "..." }
  },
  "keywordAnalysis": {
    "matched": [{ "keyword": "Python", "resume_count": 2, "job_count": 1, "source_refs": [...] }],
    "missing": [{ "keyword": "AWS Lambda", "severity": "medium", "recommendation": "Do not add unless CV source supports it." }],
    "overused": [],
    "coverage": 0.78
  },
  "parseability": {
    "required_sections": ["SUMMARY", "TECHNICAL SKILLS", "SELECTED EXPERIENCE", "PROJECTS", "EDUCATION"],
    "present_sections": ["..."],
    "flags": []
  },
  "suggestions": [
    {
      "category": "Keywords",
      "issue": "FastAPI appears in JD but only once in resume.",
      "recommendation": "If source-backed, mirror FastAPI in summary and selected experience.",
      "priority": "medium",
      "safe_to_apply_automatically": false,
      "requires_source_fact": true
    }
  ],
  "strengths": ["Standard ATS section order is present."],
  "roast": ["Good structure, but the resume undersells backend API evidence for this JD."],
  "quality": {
    "source_backed_claims": true,
    "no_invented_candidate_facts": true,
    "external_side_effects_allowed": false,
    "live_ready": false
  },
  "source_refs": [...]
}
```

Scoring proposal:

| Category | Max | Deterministic rules |
|---|---:|---|
| Formatting / parseability | 20 | Plain text exists; no tables/columns/images markers; standard headings; reasonable length; no internal leakage. |
| Keywords | 35 | Required/job keywords covered, weighted by source-backed matches. Missing unsupported keywords reduce score but do not recommend invention. Penalize stuffing/overuse. |
| Structure | 20 | Required ATS sections in exact order, source maps for experience/projects/education, role-specific summary, clear skills section. |
| Readability | 15 | Bullet length, action-verbs, concise summary, no huge paragraphs, no repeated filler. |
| Risk/compliance | 10 | No invented work authorization/location/salary claims, no employer mismatch, exact opportunity isolation, side effects disabled. |

Score bands:

- `send_ready`: `>= 90` — eligible for send/apply only after exact-version candidate approval and all side-effect gates pass.
- `human_review`: `85-89` — good enough for candidate/operator review, but still not send/apply-ready.
- `improvement_review`: `70-84` — useful simulator feedback, but packet should remain blocked from human review until improved.
- `blocked`: `< 70` or hard fail such as missing resume/source refs/internal leakage.

---

## Implementation Tasks

### Task 1: Add simulator unit tests first

**Objective:** Define the ATS simulator output contract and edge behavior before implementation.

**Files:**

- Create: `backend/tests/unit/services/test_career_ops_ats_simulator.py`
- Later create: `backend/application/services/career_ops_ats_simulator.py`

**Test cases:**

1. `test_ats_simulator_scores_well_structured_source_backed_resume`
   - Build a fake tailored resume with all required sections and Python/FastAPI/RAG/PostgreSQL coverage.
   - Assert:
     - `format == "career_ops_ats_simulation_v1"`
     - `status == "simulated"`
     - `atsScore >= 85`
     - all `scoreBreakdown` categories exist
     - matched keywords include Python/FastAPI/RAG/PostgreSQL
     - `quality.external_side_effects_allowed is False`

2. `test_ats_simulator_flags_missing_job_keywords_without_inventing_claims`
   - JD includes `AWS Lambda`; resume/CV does not.
   - Assert missing keyword has `requires_source_fact=True` and recommendation says not to add unless source-backed.
   - Assert resume text does not get modified by the simulator.

3. `test_ats_simulator_blocks_internal_leakage`
   - Resume plain text includes `metadata_json` or `ForgeGraph`.
   - Assert `status == "blocked"`, `scoreBand == "blocked"`, risk score low/zero.

4. `test_ats_simulator_penalizes_missing_required_sections`
   - Remove `EDUCATION` or reorder sections.
   - Assert formatting/structure penalties and suggestion priority high.

5. `test_ats_simulator_detects_keyword_stuffing`
   - Repeat `Python` 12 times with little evidence.
   - Assert `keywordAnalysis.overused` includes Python and score is lower than clean fixture.

**Expected RED command:**

```bash
cd backend
FORGEGRAPH_ENV_FILE= DEBUG=1 SECRET_KEY='***' USE_SQLITE=true USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 SQLITE_DB_PATH=.hermes/career_ops_ats_sim_red.sqlite3 \
  UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest tests/unit/services/test_career_ops_ats_simulator.py -q
```

Expected: FAIL because `application.services.career_ops_ats_simulator` does not exist.

### Task 2: Implement `career_ops_ats_simulator.py`

**Objective:** Add pure deterministic ATS simulation helpers.

**Files:**

- Create: `backend/application/services/career_ops_ats_simulator.py`

**Public function:**

```python
def simulate_career_ops_ats(
    *,
    packet: dict[str, Any],
    posting: dict[str, Any],
    candidate_facts: dict[str, Any],
) -> dict[str, Any]:
    """Return deterministic ATS simulation for a CareerOps packet/resume."""
```

**Implementation details:**

- Reuse constants from `career_ops_content_alignment.py`:
  - `ATS_REQUIRED_SECTIONS`
  - `INTERNAL_LEAKAGE_TOKENS`
- Reuse or mirror keyword extraction logic carefully. Prefer exporting a small safe helper from `career_ops_content_alignment.py` only if necessary; otherwise duplicate a narrow private keyword extractor in the simulator to avoid widening existing module API.
- Inputs:
  - `packet["artifacts"]["tailored_resume"]`
  - `packet["alignment"]`
  - `packet["source_refs"]`
  - `posting` from `_posting_from_metadata`
  - `candidate_facts`
- Do **not** mutate packet/resume.
- Do **not** call LLMs or external APIs.
- Do **not** recommend adding unsupported/missing keywords as claims; recommendations must say “only add if CV source supports it.”
- Detect ATS/provider hint from `posting["url"]` / `posting["provider"]` / source mode:
  - `greenhouse`, `lever`, `ashby`, `workday`, `linkedin`, `aggregator`, `unknown`
- Keep output JSON-serializable and stable for snapshot-like tests.

### Task 3: Integrate ATS simulation into packet builder

**Objective:** Every generated packet should include the ATS simulator result.

**Files:**

- Modify: `backend/application/services/career_ops_packet_builder.py`
- Modify tests:
  - `backend/tests/unit/services/test_career_ops_packet_builder.py`
  - `backend/tests/unit/services/test_career_ops_content_alignment.py` only if helper exports change

**Implementation:**

- Import `simulate_career_ops_ats`.
- After tailored resume + cover letter are built, call simulator if not blocked:

```python
ats_simulation = None
if not blocked_reasons and tailored_resume:
    packet_seed = {
        "status": status,
        "opportunity": {...},
        "alignment": alignment,
        "artifacts": {"tailored_resume": tailored_resume, "cover_letter": cover_letter},
        "source_refs": source_refs,
        "quality": quality,
    }
    ats_simulation = simulate_career_ops_ats(
        packet=packet_seed,
        posting=posting,
        candidate_facts=candidate_facts,
    )
```

- Add to packet:

```python
"artifacts": {
    "tailored_resume": tailored_resume,
    "cover_letter": cover_letter,
    "ats_simulation": ats_simulation,
    "application_answers": ...,
}
```

- Add packet quality fields:

```python
"ats_score": ats_simulation.get("atsScore") if ats_simulation else None,
"ats_human_review_minimum_passed": bool(ats_simulation and ats_simulation["atsScore"] >= 85),
"ats_send_minimum_passed": bool(ats_simulation and ats_simulation["atsScore"] >= 90),
```

**Tests:**

- Existing packet builder draft test should assert:
  - `packet["artifacts"]["ats_simulation"]["atsScore"] >= 0`
  - `scoreBreakdown` exists
  - `external_side_effects_allowed=False`
- Missing CV / expired cases should keep `ats_simulation is None`.

### Task 4: Persist `ats_simulation_report` as first-class deliverable

**Objective:** Store ATS simulator output as its own ForgeGraph artifact/deliverable for review and audit.

**Files:**

- Modify: `backend/application/services/career_ops_pipeline.py`
- Modify tests:
  - `backend/tests/unit/services/test_career_ops_pipeline.py`
  - `backend/tests/unit/services/test_career_ops_artifacts.py` if needed
  - `backend/tests/unit/management/test_build_career_ops_application_packet.py`

**Implementation:**

- Extend `_write_application_draft_deliverables(...)` to read:

```python
ats_simulation = artifacts.get("ats_simulation")
```

- If dict, call `write_career_ops_deliverable(...)` with:

```python
deliverable_type="ats_simulation_report"
title=f"ATS simulation — {opportunity.title}"
payload=ats_simulation
```

- Ensure both paths persist it:
  - `run_career_ops_url_pipeline(...)`
  - `build_career_ops_application_packet_for_opportunity(...)`

**Expected management command output additions:**

- `ats_simulation_asset_version_id`
- `ats_score`
- `ats_score_band`

### Task 5: Extend readiness gates

**Objective:** ATS simulator becomes a pre-apply gate, while exact candidate approval remains the final blocker.

**Files:**

- Modify: `backend/application/services/career_ops_quality_gates.py`
- Modify: `backend/tests/unit/services/test_career_ops_quality_gates.py`

**New checks:**

```text
ats_simulation_present
ats_human_review_minimum
ats_send_minimum
ats_simulation_no_internal_leakage
ats_simulation_side_effect_guard_disabled
```

**Rules:**

- `ats_simulation_present`: packet artifact exists and status is `simulated` or `blocked`.
- `ats_human_review_minimum`: pass only if `atsScore >= 85` and `scoreBand` is `human_review` or `send_ready`.
- `ats_send_minimum`: pass only if `atsScore >= 90` and `scoreBand == "send_ready"`.
- `ats_simulation_no_internal_leakage`: scan simulator payload just like packet/resume/cover letter.
- `ats_simulation_side_effect_guard_disabled`: `quality.external_side_effects_allowed is False`.

**Important:** Readiness should still report `live_send_allowed=False` until exact-version approval + all other gates pass. Do not let a high ATS score enable any send/apply path.
An ATS score from 85-89 permits human review only; it must keep send/apply readiness blocked until the packet reaches 90+.

### Task 6: Update command output and Docker verification script

**Objective:** Operators can run packet generation and immediately see ATS scores for each opportunity.

**Files:**

- Modify: `backend/infrastructure/orm/management/commands/build_career_ops_application_packet.py`
- Create/update temp verification script during implementation:
  - `backend/.hermes/verify_career_ops_ats_simulation.py`

**Command output additions:**

```json
{
  "ats_simulation_asset_version_id": "...",
  "ats": {
    "score": 88,
    "band": "human_review",
    "human_review_minimum_passed": true,
    "send_minimum_passed": false,
    "top_missing_keywords": ["AWS Lambda"]
  }
}
```

**Docker verification target:**

- Existing company with 4 opportunities: use latest CareerOps company with `live_search_skill` opportunities.
- Run `build_career_ops_application_packet` for each opportunity.
- Verify each opportunity has deliverable types:

```text
application_packet
ats_simulation_report
cover_letter_draft
job_evaluation_report
job_liveness_receipt
tailored_resume_html
```

- Verify each packet readiness is blocked only by expected gates:
  - `exact_version_approval_present`
  - `ats_send_minimum` for packets scoring 85-89, because those are human-review-ready but not send-ready.
  - `ats_human_review_minimum` for packets below 85; report this as useful simulator feedback, not a test failure, unless deterministic fixture expected pass.

### Task 7: Documentation/skill update

**Objective:** Preserve the ATS simulator pattern for future CareerOps runs.

**Files:**

- Patch skill reference:
  - `forgegraph-company-setup` → `references/career-ops-live-discovery-first-prompt.md`
- Optional docs:
  - `docs/operating-model-packs/career-ops.md`

**Add notes:**

- ATS simulator is deterministic and source-bounded; LLM-based resume roasts from other repos are inspiration only.
- `atsScore` is advisory until exact-version approval; it never enables side effects by itself.
- Missing keywords are not instructions to invent facts.
- Public ATS board/provider hints are provenance and compatibility context, not proof of employer-side ATS ranking.

---

## Verification Commands

Focused simulator tests:

```bash
cd C:/Users/mathi/projects/forgegraph/backend
FORGEGRAPH_ENV_FILE= DEBUG=1 SECRET_KEY='***' USE_SQLITE=true USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 SQLITE_DB_PATH=.hermes/career_ops_ats_simulator.sqlite3 \
  UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest tests/unit/services/test_career_ops_ats_simulator.py -q
```

Focused Step 2 + ATS suite:

```bash
cd C:/Users/mathi/projects/forgegraph/backend
FORGEGRAPH_ENV_FILE= DEBUG=1 SECRET_KEY='***' USE_SQLITE=true USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 SQLITE_DB_PATH=.hermes/career_ops_ats_step2.sqlite3 \
  UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest \
  tests/unit/services/test_career_ops_ats_simulator.py \
  tests/unit/services/test_career_ops_content_alignment.py \
  tests/unit/services/test_career_ops_packet_builder.py \
  tests/unit/services/test_career_ops_artifacts.py \
  tests/unit/services/test_career_ops_quality_gates.py \
  tests/unit/services/test_career_ops_pipeline.py \
  tests/unit/management/test_build_career_ops_application_packet.py -q
```

Broader CareerOps regression:

```bash
cd C:/Users/mathi/projects/forgegraph/backend
FORGEGRAPH_ENV_FILE= DEBUG=1 SECRET_KEY='***' USE_SQLITE=true USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 SQLITE_DB_PATH=.hermes/career_ops_ats_all.sqlite3 \
  UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest tests/unit/services/test_career_ops_*.py tests/unit/management/test_*career_ops*.py tests/unit/management/test_build_career_ops_application_packet.py -q
```

Lint/check:

```bash
cd C:/Users/mathi/projects/forgegraph/backend
UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run ruff check \
  application/services/career_ops_ats_simulator.py \
  application/services/career_ops_packet_builder.py \
  application/services/career_ops_pipeline.py \
  application/services/career_ops_quality_gates.py \
  infrastructure/orm/management/commands/build_career_ops_application_packet.py \
  tests/unit/services/test_career_ops_ats_simulator.py

FORGEGRAPH_ENV_FILE= DEBUG=1 SECRET_KEY='***' USE_SQLITE=true USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 SQLITE_DB_PATH=.hermes/career_ops_ats_check.sqlite3 \
  UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run python manage.py check
```

Docker verification:

```bash
cd C:/Users/mathi/projects/forgegraph
MSYS_NO_PATHCONV=1 docker compose exec -T backend sh -lc '/app/.venv/bin/python3 manage.py shell < /app/.hermes/verify_career_ops_ats_simulation.py'
```

---

## Acceptance Criteria

- ATS simulator report exists and is deterministic for fixed packet/posting/CV input.
- Report includes `atsScore`, score band, breakdown, keyword analysis, parseability findings, suggestions, strengths, and recruiter-style feedback.
- Simulator does not call LLMs, external APIs, browser automation, or mutate documents.
- Missing JD keywords are framed as gaps and source-required improvements, not invented claims.
- `ats_simulation_report` is persisted as a `ServiceDeliverable`/`AssetVersion` per opportunity.
- Packet readiness includes ATS simulator presence, 85+ human-review gate, and 90+ send/apply gate.
- Existing exact-version approval and `external_side_effects_allowed=false` gates remain mandatory.
- Focused ATS/Step 2 tests, broader CareerOps slice, ruff, and Django check pass.
- Docker verification proves the four persisted live-search opportunities get ATS simulation reports.

## Risks / Tradeoffs

- Deterministic ATS scoring is a simulator, not a real employer ATS ranking. The report must say this clearly.
- Sparse job snippets may produce lower keyword scores than full JDs. The simulator should identify “insufficient JD detail” separately from resume weakness where possible.
- If a resume under-scores because the source CV lacks evidence for a JD keyword, the correct output is a gap/blocker, not an invented resume bullet.
- Keep thresholds strict from the start: `85` minimum for human review and `90` minimum for send/apply readiness. Tune only after reviewing real generated reports and approval outcomes.

## Open Questions for Review

1. Should `ats_send_minimum` be enforced before candidate approval, or should 85-89 packets enter human review with an explicit “not send-ready” blocker?
2. Should the simulator score the JSON/plain-text ATS resume only in this slice, or should we wait to also score the rendered PDF in the next PDF polish slice?
3. Should “roast” feedback use a neutral professional tone by default, with a more candid/operator-only mode later?
