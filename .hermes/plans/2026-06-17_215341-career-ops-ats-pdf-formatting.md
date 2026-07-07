# CareerOps ATS-Ready PDF Formatting Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Add ForgeGraph-native ATS-ready resume formatting so each CareerOps tailored resume can be exported as a parseable PDF whose fields/sections are readable by ATS systems, with validation receipts persisted beside the application packet.

**Architecture:** Build a CareerOps-specific formatter that renders the existing source-bounded `tailored_resume` artifact into a deterministic one-column ATS resume text/HTML/PDF package. Do **not** optimize for beauty first. Unlike Atlas client handoff PDFs, the default PDF renderer should prioritize a clean text layer, standard section headings, no tables/images/icons/columns, stable section order, and machine-readability verification. Reuse ForgeGraph artifact/version/deliverable primitives and the existing exact-version approval/readiness gates.

**Tech Stack:** Python/Django backend services, ForgeGraph `Asset`/`AssetVersion`/`ServiceDeliverable`, existing CareerOps packet pipeline, deterministic PDF generation using built-in text PDF primitives (derived from `deliverable_format_renderers.py`), optional HTML preview, host/Docker verification. Reference repos inspected and pinned below.

---

## Reference Implementations Inspected

Fresh upstream checkouts under `/tmp/forgegraph-ats-pdf-refs/`:

1. `https://github.com/sauravhathi/atsresume.git`
   - Commit: `e1db0d31341cda4b1e3cbefef0734241cf1a45ed`
   - Useful pattern: explicit resume section inventory; A4 wrapper; print/export flow via `window.print()`.
   - Cautions for ForgeGraph: profile pictures, icons, social-media grid, draggable UI, and browser-only printing are not the core product pattern we need.

2. `https://github.com/engmaryamameen/cv_maker.git`
   - Commit: `a745ec64bdf4170a52375c35ee8a154ca5c41df9`
   - Useful pattern: README states ATS goal clearly: “Real text, standard sections, no hidden content”; minimal template uses simple headings and inline skills; print CSS hides controls and sets A4 margins.
   - Cautions for ForgeGraph: templates include `dangerouslySetInnerHTML`, profile pictures, watermark, font/theme choices, and visual customization that are lower priority than parseability.

3. `https://github.com/MorphyKutay/ATSResume.git`
   - Commit: `1ec4ef26a26d5bc124402d7de18992e94d6a67a4`
   - Useful pattern: print CSS explicitly targets ATS: standard sections, compact type, links preserved, print-only cleanup, page-break avoidance.
   - Cautions for ForgeGraph: two-column layout, icons, badges, and browser print dialog are not ideal for a backend-owned ATS-safe default.

## Key Product Decision

Atlas “pretty PDF” rendering is not the default for CareerOps resumes. For CareerOps, default export should be:

- one-column
- standard heading order
- selectable/searchable text
- no images/profile photos/icons
- no tables or multi-column layout
- no hidden text
- no CSS-only content that disappears from extracted text
- source-bounded claims only
- exact version approval required before employer-facing use

Chromium/Playwright can still be reused later for an optional human preview PDF, but the first ATS-ready artifact should be a deterministic text-layer PDF that is easy to validate in unit tests and Docker without Poppler being installed in the backend container.

---

## Current ForgeGraph Context

Existing CareerOps artifacts:

- `backend/application/services/career_ops_content_alignment.py`
  - Builds `tailored_resume` with `format="ats_resume_v1"`, `sections`, `plain_text`, `claim_source_map`, source refs, and no-side-effect quality flags.
- `backend/application/services/career_ops_packet_builder.py`
  - Adds `artifacts.tailored_resume`, `cover_letter`, and `ats_simulation` to the application packet.
- `backend/application/services/career_ops_pipeline.py`
  - Persists `tailored_resume_html`, `cover_letter_draft`, `ats_simulation_report`, and `application_packet` deliverables.
- `backend/application/services/career_ops_quality_gates.py`
  - Checks ATS section structure, claim source map, no leakage, ATS simulator thresholds, exact-version approval, side-effect guards.
- `backend/application/services/deliverable_format_renderers.py`
  - Contains deterministic uncompressed text PDF utilities that are more ATS-safe than browser layout for this slice.
- `backend/application/services/atlas_prompt_delivery.py`
  - Contains Playwright/Chromium HTML-to-PDF helper used for pretty Atlas PDFs; useful as a future preview path, not first ATS default.

Tooling observed:

- Host has `pdftotext` and `pdfinfo`.
- Docker backend currently does **not** have `pdftotext`/`pdfinfo`.
- Therefore first implementation should not require Poppler inside Docker for pass/fail validation.

---

## Proposed Artifact Contract

For every unblocked application packet with `tailored_resume` present, create these derived artifacts:

1. `ats_resume_text`
   - MIME: `text/plain`
   - Canonical extracted/expected ATS text.
   - Stored as an exact `AssetVersion` with `provenance_json.inline_content`.

2. `ats_resume_html`
   - MIME: `text/html`
   - Minimal semantic preview HTML.
   - One-column, standard headings, no scripts, no external assets, no images/icons/tables.
   - Stored as an exact `AssetVersion` with `inline_content`.

3. `ats_resume_pdf`
   - MIME: `application/pdf`
   - Deterministic backend-generated text PDF.
   - Store bytes in `inline_content_base64` or content URI pattern consistent with current artifact persistence.
   - Provenance includes source tailored resume version, formatter version, section order, expected text SHA256, and parseability checks.

4. `ats_resume_parseability_report`
   - MIME: `application/json`
   - Validation report proving required fields/headings are present and text matches expected resume text.
   - Should include blocker/warning arrays and `external_side_effects_allowed=false`.

First-slice deliverable types:

```text
ats_resume_text
ats_resume_html
ats_resume_pdf
ats_resume_parseability_report
```

If this feels too many for UI later, we can keep all four as `AssetVersion`s and expose only `ats_resume_pdf` + `ats_resume_parseability_report` as `ServiceDeliverable`s. For now, make all discoverable because CareerOps needs exact-version evidence.

---

## ATS Formatting Rules

Canonical section order:

```text
NAME / CONTACT HEADER
SUMMARY
TECHNICAL SKILLS
SELECTED EXPERIENCE
PROJECTS
EDUCATION
CERTIFICATIONS    optional
LANGUAGES         optional
```

Renderer rules:

- Use normal text nodes, headings, paragraphs, and bullet lists only.
- Avoid profile photos, icons, emoji, SVG, canvas, background images.
- Avoid tables, CSS grid, and multi-column layouts in default ATS output.
- Avoid hidden text, zero-size text, offscreen content, and generated `::before`/`::after` content for important fields.
- Avoid section labels like “Experience” if the simulator expects `SELECTED EXPERIENCE`; keep heading names stable.
- Contact links may render as plain visible text; clickable links are nice but not required for ATS safety.
- Replace fancy bullets with standard hyphen or bullet characters consistently.
- Normalize Unicode to NFKC and strip control characters.
- Keep source refs in provenance, not visible resume text.
- Do not add missing claims to fill layout.

---

## Task 1: Add ATS Resume Formatter Unit Tests

**Objective:** Define the desired ATS formatting contract before production code.

**Files:**

- Create: `backend/tests/unit/services/test_career_ops_resume_formatter.py`
- Create later: `backend/application/services/career_ops_resume_formatter.py`

**Step 1: Write failing tests**

Tests to add:

1. `test_render_ats_resume_text_preserves_standard_section_order`
   - Input: fixture `tailored_resume` payload shaped like current `ats_resume_v1`.
   - Assert text contains headings in this exact order:
     - `SUMMARY`
     - `TECHNICAL SKILLS`
     - `SELECTED EXPERIENCE`
     - `PROJECTS`
     - `EDUCATION`
   - Assert no internal source refs are visible.

2. `test_render_ats_resume_html_uses_semantic_single_column_markup`
   - Assert HTML contains `<h1>`, `<section>`, `<h2>`, `<ul>`, `<li>`.
   - Assert it does **not** contain `<table`, `<img`, `<svg`, `<canvas`, `display:none`, `visibility:hidden`, `grid-template`, `column-count`.
   - Assert section text is present as real HTML text.

3. `test_render_ats_resume_pdf_has_valid_pdf_bytes_and_expected_text_shadow`
   - Assert PDF starts with `%PDF-` and ends with `%%EOF`.
   - Assert PDF provenance/check result contains expected text SHA256.
   - Assert deterministic renderer does not compress text streams for the default backend path.

4. `test_validate_ats_resume_parseability_blocks_missing_section`
   - Remove `EDUCATION` from fixture.
   - Assert validation report status is `blocked` with blocker `missing_section:EDUCATION`.

5. `test_validate_ats_resume_parseability_blocks_internal_leakage`
   - Add `metadata_json` or `ForgeGraph internal prompt` to visible text.
   - Assert validation blocks.

**Step 2: Run RED**

```bash
cd backend
FORGEGRAPH_ENV_FILE= DEBUG=1 SECRET_KEY='***' USE_SQLITE=true USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 SQLITE_DB_PATH=.hermes/career_ops_ats_pdf_red.sqlite3 UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest tests/unit/services/test_career_ops_resume_formatter.py -q
```

Expected: fail because `career_ops_resume_formatter` does not exist.

---

## Task 2: Implement `career_ops_resume_formatter.py`

**Objective:** Add deterministic text, HTML, PDF, and validation functions for ATS-ready resumes.

**Files:**

- Create: `backend/application/services/career_ops_resume_formatter.py`

**Core API:**

```python
@dataclass(frozen=True, slots=True)
class CareerOpsATSResumeArtifacts:
    text: str
    html: str
    pdf_bytes: bytes
    parseability_report: dict[str, Any]


def render_career_ops_ats_resume(
    *,
    tailored_resume: dict[str, Any],
    opportunity: dict[str, Any],
    candidate_identity: dict[str, Any] | None = None,
) -> CareerOpsATSResumeArtifacts:
    ...
```

**Implementation notes:**

- Normalize the current `tailored_resume["sections"]` into canonical ordered sections.
- Use `tailored_resume["plain_text"]` as a fallback, not as the only source.
- Candidate identity should be source-bounded:
  - name/title/contact only if present in CV source metadata or explicitly extracted from base CV.
  - If contact fields are absent, omit them; do not invent email/phone/linkedin.
- HTML should be a complete standalone document:
  - `<meta charset="utf-8">`
  - minimal CSS
  - `@page { size: Letter; margin: 0.5in; }` or A4 if we choose A4 consistently
  - `font-family: Arial, Helvetica, sans-serif`
  - no scripts/assets.
- PDF should use a deterministic text PDF generator copied/adapted from `deliverable_format_renderers.py` so Docker tests do not need Poppler.
- Keep renderer version constant, e.g. `CAREER_OPS_ATS_RESUME_FORMATTER_VERSION = "1"`.

**Validation report shape:**

```json
{
  "status": "passed|blocked",
  "format": "career_ops_ats_resume_parseability_v1",
  "checks": {
    "required_sections_present": "pass|blocked",
    "section_order": "pass|blocked",
    "no_internal_leakage": "pass|blocked",
    "no_tables_images_icons": "pass|blocked",
    "pdf_bytes_valid": "pass|blocked",
    "expected_text_embedded": "pass|blocked"
  },
  "blockers": [],
  "warnings": [],
  "expected_text_sha256": "...",
  "external_side_effects_allowed": false
}
```

---

## Task 3: Persist ATS Resume Formatting Artifacts

**Objective:** Make ATS formatted outputs first-class ForgeGraph artifacts/deliverables.

**Files:**

- Modify: `backend/application/services/career_ops_artifacts.py`
- Modify: `backend/application/services/career_ops_pipeline.py`
- Modify: `backend/tests/unit/services/test_career_ops_pipeline.py`

**Approach:**

Current `write_career_ops_deliverable()` assumes JSON-ish payloads. For PDF bytes, add either:

Option A — extend existing writer safely:

```python
def write_career_ops_binary_deliverable(..., payload: dict[str, Any], content_bytes: bytes, mime_type: str, content_uri_suffix: str) -> tuple[ServiceDeliverable, AssetVersion]
```

Option B — add CareerOps-specific wrapper:

```python
def write_career_ops_resume_file_deliverable(...)
```

Prefer Option A if it stays generic and small.

**Persistence requirements:**

- `AssetVersion.content_hash` is SHA256 of actual PDF bytes for `ats_resume_pdf`.
- `AssetVersion.mime_type == "application/pdf"`.
- `AssetVersion.provenance_json["career_ops"]` includes:
  - `deliverable_type="ats_resume_pdf"`
  - source `tailored_resume` asset version id if available
  - `expected_text_sha256`
  - parseability report id/hash
  - `external_side_effects_allowed=false`
- `ServiceDeliverable.deliverable_type == "ats_resume_pdf"`.

**Pipeline integration:**

In `_write_application_draft_deliverables()`:

1. If `artifacts.tailored_resume` is present, render ATS artifacts.
2. Persist in order:
   - existing `tailored_resume_html`
   - new `ats_resume_text`
   - new `ats_resume_html`
   - new `ats_resume_pdf`
   - new `ats_resume_parseability_report`
   - existing `cover_letter_draft`
   - existing `ats_simulation_report`
3. Add all generated asset version IDs to `content_versions_by_type`.

**Tests:**

Extend `test_url_pipeline_with_base_cv_persists_resume_and_cover_letter_deliverables` to assert deliverable types include:

```python
{
  "ats_resume_text",
  "ats_resume_html",
  "ats_resume_pdf",
  "ats_resume_parseability_report",
}
```

Assert PDF version:

```python
assert pdf_version.mime_type == "application/pdf"
assert pdf_version.content_hash
assert pdf_version.provenance_json["career_ops"]["external_side_effects_allowed"] is False
```

---

## Task 4: Add Readiness Gates for ATS PDF Parseability

**Objective:** Block send/apply readiness unless the exact packet has a parseable ATS PDF artifact.

**Files:**

- Modify: `backend/application/services/career_ops_quality_gates.py`
- Modify: `backend/tests/unit/services/test_career_ops_quality_gates.py`

**New readiness checks:**

```text
ats_resume_pdf_present
ats_resume_pdf_mime_type
ats_resume_parseability_passed
ats_resume_pdf_exact_version_bound
```

**Rules:**

- Human review may pass without PDF if we explicitly want content review first, but send readiness must fail without PDF.
- Because current readiness status is binary, add these checks as blockers by default for packet readiness, unless the command has a `--content-only` mode later.
- `live_send_allowed` remains false until exact approval and side-effect flags pass.

**Tests:**

1. Missing PDF deliverable blocks `ats_resume_pdf_present`.
2. Parseability report status `blocked` blocks `ats_resume_parseability_passed`.
3. Wrong company PDF/version blocks exact-version binding.
4. Valid PDF + valid report passes ATS PDF checks but still blocks exact approval.

---

## Task 5: Extend Management Command Output

**Objective:** Make ATS PDF artifact IDs visible in command output and Docker verification.

**Files:**

- Modify: `backend/application/services/career_ops_pipeline.py`
- Modify: `backend/infrastructure/orm/management/commands/build_career_ops_application_packet.py`
- Modify: `backend/tests/unit/management/test_build_career_ops_application_packet.py`

**Output fields:**

```json
{
  "ats_resume_text_asset_version_id": "...",
  "ats_resume_html_asset_version_id": "...",
  "ats_resume_pdf_asset_version_id": "...",
  "ats_resume_parseability_report_asset_version_id": "..."
}
```

**Test assertions:**

- IDs exist.
- `ats_resume_pdf_asset_version_id` resolves to `AssetVersion` with MIME `application/pdf`.
- Readiness includes ATS PDF checks.

---

## Task 6: Host Smoke Artifact Verification

**Objective:** Prove the generated PDF has extractable text on Mike’s host where Poppler is available.

**Files:**

- Create: `backend/.hermes/run_career_ops_ats_pdf_packets.py`
- Create: `backend/.hermes/verify_career_ops_ats_pdf_packets.py`

**Host verification commands:**

```bash
cd backend
FORGEGRAPH_ENV_FILE= DEBUG=1 SECRET_KEY='***' USE_SQLITE=true USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run --group dev pytest tests/unit/services/test_career_ops_resume_formatter.py tests/unit/services/test_career_ops_pipeline.py tests/unit/services/test_career_ops_quality_gates.py tests/unit/management/test_build_career_ops_application_packet.py -q
UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run ruff check application/services/career_ops_resume_formatter.py application/services/career_ops_pipeline.py application/services/career_ops_quality_gates.py tests/unit/services/test_career_ops_resume_formatter.py
FORGEGRAPH_ENV_FILE= DEBUG=1 SECRET_KEY='***' USE_SQLITE=true USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run python manage.py check
```

If a PDF file is written to `.hermes/`, additionally run on host:

```bash
pdfinfo backend/.hermes/<sample>.pdf
pdftotext backend/.hermes/<sample>.pdf - | sed -n '1,120p'
```

Expected extracted text includes section headings and bullet content in canonical order.

---

## Task 7: Docker Verification Against the 4 Persisted Opportunities

**Objective:** Prove ForgeGraph Docker backend can produce the ATS PDF artifacts for the existing four CareerOps opportunities.

**Target company currently used for packetized opportunities:**

```text
f950d3ae-ca93-41a3-9d00-0ca3e12e3f50
```

**Docker command shape:**

```bash
cd /c/Users/mathi/projects/forgegraph
MSYS_NO_PATHCONV=1 docker compose ps
MSYS_NO_PATHCONV=1 docker compose exec -T backend python manage.py shell < backend/.hermes/run_career_ops_ats_pdf_packets.py
MSYS_NO_PATHCONV=1 docker compose exec -T backend python manage.py shell < backend/.hermes/verify_career_ops_ats_pdf_packets.py
```

**Docker verification should assert:**

- 4 opportunities processed.
- Each opportunity has deliverable types:
  - `application_packet`
  - `tailored_resume_html`
  - `ats_resume_text`
  - `ats_resume_html`
  - `ats_resume_pdf`
  - `ats_resume_parseability_report`
  - `ats_simulation_report`
  - `cover_letter_draft`
- PDF version MIME is `application/pdf`.
- Parseability report status is `passed`.
- Readiness has ATS PDF checks passing.
- Readiness still blocks `exact_version_approval_present` until the candidate approves the exact version.
- No employer-facing side effects occurred.

---

## Risks / Tradeoffs

1. **Pretty vs parseable:** Browser/Chromium PDFs can look better but may introduce layout complexity. First slice intentionally uses deterministic text PDF.
2. **Contact extraction:** Current base CV asset may not expose structured name/email/phone. Do not invent contact fields. Add a later parser or operator-supplied candidate profile state if needed.
3. **PDF text extraction in Docker:** Docker lacks Poppler. Use deterministic PDF generation and internal validation for Docker; host can use `pdftotext` as an additional smoke check.
4. **Too many deliverables:** Multiple ATS artifacts may clutter UI. This is acceptable for backend proof; UI can later collapse them into one “ATS Resume Package”.
5. **Existing `tailored_resume_html` naming:** It currently stores JSON payload, not literal HTML. New `ats_resume_html` should be literal standalone HTML to avoid semantic confusion.
6. **Exact approval binding:** Approval should bind to both application packet version and ATS PDF version before live send/apply.

---

## Acceptance Criteria

- Unit tests prove ATS text/HTML/PDF renderer behavior and parseability validation.
- Pipeline persists ATS PDF and parseability report as ForgeGraph-owned exact asset versions.
- Command output exposes ATS PDF/report asset version IDs.
- Readiness checks fail closed when ATS PDF is missing or unparseable.
- Docker verification against the 4 persisted opportunities creates valid ATS PDF artifacts without employer-facing side effects.
- Host smoke extraction via `pdftotext` confirms real extracted text includes all required resume sections.
- `ruff check` and `manage.py check` pass.

---

## Suggested First Implementation Order

1. Add `test_career_ops_resume_formatter.py` RED tests.
2. Implement pure renderer/validator service.
3. Add binary artifact persistence helper.
4. Integrate into pipeline and command output.
5. Add readiness checks.
6. Run focused host tests/lint/check.
7. Run Docker generation/verification against the 4 opportunities.
8. Only after this passes, consider optional browser-rendered human preview.
