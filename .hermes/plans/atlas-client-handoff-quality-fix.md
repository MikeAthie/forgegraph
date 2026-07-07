# Atlas Client Handoff Quality Fix Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task after product review.

**Goal:** Turn Atlas prompt delivery output from an internal lineage dump into a genuinely client-ready approval package, while preventing placeholder/doodle media from being labeled ready.

**Architecture:** Split internal ForgeGraph lineage from the client presentation layer. Internal deliverables, raw prompts, UUIDs, and stage evidence stay in manifest/provenance; HTML/PDF render from a client-safe handoff view model with explicit quality gates.

**Tech Stack:** Django/Python, existing `atlas_prompt_delivery.py`, existing PDF renderer in `deliverable_format_renderers.py`, pytest quality tests.

---

## Root Cause Summary

Current code fixed “empty package” by piping raw `inline_content` from internal deliverables into `_client_html()` and `_client_package_text()`. That makes the PDF/HTML substantive, but not client-ready: it leaks Markdown syntax, source prompt text, internal department/stage naming, media job UUIDs, asset IDs, and QA implementation details.

Separately, media QA only checks job success, not visual/client quality, so placeholder `codex_spec_renderer` outputs can still be packaged and sent.

---

## PR 1 — Separate Client Presentation From Internal Lineage

### Task 1: Add failing report-safety tests

**Files:**
- Modify: `backend/tests/unit/services/test_atlas_prompt_delivery_quality.py`

**Test intent:**
Create a synthetic internal deliverable containing markdown headings, `media_job=...`, UUIDs, `Source prompt`, and `strategy_research`; assert the client package text/HTML does not expose them.

Expected RED failure today: raw internals appear in client text.

### Task 2: Add a client handoff view model

**Files:**
- Modify: `backend/application/services/atlas_prompt_delivery.py`

Add a small internal structure/function:

```py
def _client_handoff_sections(*, prompt: str, manifest: dict[str, Any], deliverable_sections: list[dict[str, str]], media_quality: dict[str, Any]) -> list[dict[str, str]]:
    ...
```

It should return polished sections only:

1. `Resumen ejecutivo`
2. `Concepto creativo`
3. `Dirección visual`
4. `Assets para aprobación`
5. `Copy y respuestas sugeridas`
6. `Checklist de lanzamiento`
7. `Decisión solicitada`

Do not copy raw section content wholesale. Extract/summarize safe ideas, or use deterministic curated copy from the run prompt and known campaign parameters.

### Task 3: Keep lineage in manifest/provenance only

**Files:**
- Modify: `backend/application/services/atlas_prompt_delivery.py`

Update `manifest.json` to preserve internal IDs and raw deliverable references under an explicit audit key, e.g.:

```json
"forgegraph_lineage": {
  "engagement_id": "...",
  "whiteboard_id": "...",
  "deliverables": [...],
  "media_jobs": [...]
}
```

The visible PDF/HTML may show short lineage IDs in an appendix only if labeled “ForgeGraph audit appendix”; not in main client content.

### Task 4: Render HTML/PDF from client-safe sections

**Files:**
- Modify: `backend/application/services/atlas_prompt_delivery.py`

Change `_client_html()` and `_client_package_text()` to consume the client handoff view model, not raw `deliverable_sections`.

Replace labels like:

```text
Department deliverables
Source prompt
```

with client-facing labels:

```text
Resumen
Concepto
Galería de assets
Copys sugeridos
Aprobación requerida
```

### Task 5: Add visible-text quality gate

**Files:**
- Modify: `backend/application/services/atlas_prompt_delivery.py`
- Modify: `backend/tests/unit/services/test_atlas_prompt_delivery_quality.py`

Add `_assert_client_report_quality(text: str)` and call it before writing HTML/PDF.

Fail on visible text containing:

- `Source prompt:`
- `Department deliverables:`
- `media_job=`
- `asset=` followed by UUID-like text
- `strategy_research`, `brand_content`, `qa_compliance`
- Markdown heading patterns like `# Strategy Brief` / `## Engagement`
- internal-only phrases like `Intended use: Internal lineage`

---

## PR 2 — Enforce Media Quality Before Delivery

### Task 6: Add media quality summary

**Files:**
- Modify: `backend/application/services/atlas_prompt_delivery.py`

Add:

```py
def _media_quality_summary(media_jobs: list) -> dict[str, Any]:
    ...
```

It should inspect `job.output_asset.metadata_json` for:

- `quality_tier`
- `production_quality`
- `quality_contract.renderer`

### Task 7: Block client-ready delivery on placeholder media

**Files:**
- Modify: `backend/application/services/atlas_prompt_delivery.py`
- Modify: `backend/tests/unit/services/test_atlas_prompt_delivery_quality.py`

If prompt/run is client-ready and any packaged media has `production_quality is False`, either:

- raise before delivery, or
- mark package as `internal_review_only` and WhatsApp copy as a test/review package, not client-ready.

Preferred for production: raise before sending.

### Task 8: Fix QA report semantics

**Files:**
- Modify: `backend/application/services/atlas_prompt_delivery.py`

Change `_qa_report()` from job-success-only:

```text
Decision: ready for review
```

to quality-aware:

```text
Decision: hold — media assets are placeholder quality
```

unless all required checks pass.

---

## PR 3 — Real Media Provider / Codex Artifact Path

### Task 9: Define provider capability contract

**Files:**
- Modify/Create service near `codex_media_worker.py` or existing provider abstraction.

Providers should declare:

```json
{
  "provider": "codex_spec_renderer",
  "production_quality_capable": false,
  "output_kind": "deterministic_placeholder_png"
}
```

Real image provider / Codex artifact agent path should declare production capability only when it actually writes evaluated image artifacts.

### Task 10: Add acceptance tests for non-doodle diversity

**Files:**
- Modify: `backend/tests/unit/services/test_codex_media_worker.py`

Basic automated checks cannot prove taste, but should catch the current failure:

- no five identical small PNG sizes in a six-image set
- no repeated identical perceptual hash among most assets
- manifest reports placeholder quality unless real provider used

Manual visual QA remains required before client delivery.

---

## Verification Commands

Run from `backend/`:

```bash
USE_SQLITE=1 USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 DEBUG=0 \
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline \
uv run pytest tests/unit/services/test_atlas_prompt_delivery_quality.py tests/unit/services/test_codex_media_worker.py -q

USE_SQLITE=1 USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 DEBUG=0 \
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline \
uv run ruff check application/services/atlas_prompt_delivery.py application/services/codex_media_worker.py tests/unit/services/test_atlas_prompt_delivery_quality.py tests/unit/services/test_codex_media_worker.py

USE_SQLITE=1 USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 DEBUG=0 \
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline \
uv run python manage.py check
```

Docker dry-run before any send:

```bash
MSYS_NO_PATHCONV=1 docker compose exec -T \
  -e FORGEGRAPH_HOST_BACKEND_PATH=C:/Users/mathi/projects/forgegraph/backend \
  backend python manage.py run_atlas_prompt_delivery \
  --prompt-file /app/.hermes/docker_atlas_prompt.txt \
  --phone '<recipient>' \
  --whatsapp-bridge-url http://host.docker.internal:3008 \
  --codex-workdir /app/.hermes/codex_media_workdir \
  --codex-timeout-seconds 600 \
  --no-send \
  --json
```

Manual verification:

1. Unzip package.
2. Read PDF/HTML as a client.
3. Confirm no internal raw notes or prompts leaked.
4. Confirm manifest contains lineage.
5. Inspect image contact sheet.
6. Send only if both report and media pass client-ready quality.
