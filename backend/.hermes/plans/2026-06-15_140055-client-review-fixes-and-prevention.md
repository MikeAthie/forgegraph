# Client Review Fixes and Prevention Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Fix the Legacy Optical Noir PDF issues raised by the client and make ForgeGraph/Atlas prevent the same class of issues before future client handoffs.

**Architecture:** Treat the PDF comments as durable client feedback, convert them into typed whiteboard/department cards, then gate future packages on strategy rationale, brand/logo requirements, asset quality, logistics wording, and evidence-backed approval. Borrow the strongest Hermes Kanban primitives: typed cards, explicit lifecycle transitions, evidence links, handoff packets, coordinator reconciliation, and client-deliverable gates.

**Tech Stack:** Django backend, `application.services.atlas_prompt_delivery`, `application.services.work_whiteboards`, department pipeline services, PyMuPDF for PDF comment ingestion if needed, existing pytest/ruff/Django verification flow.

---

## Current Context / Client Comments

Reviewed PDF: `C:\Users\mathi\Downloads\Legacy_Optical_Noir_Handoff_review.pdf`

Extracted comments:

1. Page 1: `Por qué la IA decidió hacer una campaña "Noir" y cosas de noche para lentes de sol?`
   - Root issue: strategy rationale is not explicit enough; campaign theme feels arbitrary.
2. Page 2: `Esta imagen salió culera, no cachó ahí muy bien jaja`
   - Root issue: visual QA accepted at least one weak generated asset.
3. Page 3: `Weekend distribuition esta ligado a un timeline de logistica para los envios?`
   - Root issue: `distribution` language is ambiguous; client read it as shipping/logistics instead of social content distribution.
4. Page 3: `Aqui creo que el todos los posts debe de salir el logo de Legacy para aumentar presencia de marca y posicionamiento`
   - Root issue: brand requirements did not capture logo presence on all posts.
5. Page 4: `Logo Legacy`
   - Root issue: same logo requirement appears again; should be a first-class brand constraint.

Immediate package fixes:

- Replace/retouch weak image(s).
- Add Legacy logo/brand mark treatment across all social posts or, if final logo asset is unavailable, add a visible placeholder requirement/gate that blocks production-ready status until the logo is supplied.
- Rewrite the strategy section to justify or adjust `Optical Noir`:
  - Should not read as `night campaign for sunglasses`.
  - Should explain `Noir` as premium contrast/editorial product photography: black/ivory/copper, reflective lens surfaces, luxury optical retail, no claim that sunglasses are for nighttime use.
- Rename/clarify `weekend distribution` as `weekend social rollout / posting schedule` and explicitly state `not shipping logistics` unless fulfillment details are provided.

Preventive system fixes:

- Productize these as whiteboard/kanban gates, not one-off prompt tweaks.
- Future client packages should not become `ready for review` unless each gate has evidence.

---

## Proposed Whiteboard/Kanban Model

Borrow from Hermes Kanban, but keep ForgeGraph state product-owned:

### Typed Cards

Create or persist cards like:

- `strategy_rationale_review`
- `brand_requirements_review`
- `asset_visual_qa`
- `copy_ambiguity_review`
- `client_feedback_intake`
- `package_regeneration`
- `delivery_verification`

Each card should include:

- `goal`
- `department_slug`
- `owner/source`
- `acceptance_criteria`
- `evidence_links`
- `handoff_target`
- `blocked_reason`, if any

### Explicit Lifecycle

Use auditable transitions:

`proposed -> triaged -> ready -> in_progress -> review -> approved -> delivered -> archived`

Each transition should include:

- actor/source
- timestamp
- reason
- evidence link IDs or artifact references

### Evidence-Backed Readiness

A handoff can only advance when durable evidence exists:

- strategy rationale text included in HTML/PDF
- logo requirement resolved or explicitly blocked
- image QA report with pass/fail per asset
- no ambiguous logistics language
- package hash
- PDF/HTML inspection result
- WhatsApp receipt/message IDs, when sent

### Handoff Packets

Every department transfer should create a compact packet:

- what changed
- what is approved
- open questions
- evidence links
- downstream requirements

### Coordinator Reconciliation

Before package generation, a coordinator gate checks:

- original prompt
- client feedback
- department outputs
- asset quality evidence
- whiteboard acceptance criteria
- package client-safety checks

---

## Implementation Plan

### Task 1: Add regression tests for the client feedback failures

**Objective:** Capture the exact failures from the reviewed PDF as unit tests before changing production code.

**Files:**

- Modify: `backend/tests/unit/services/test_atlas_prompt_delivery_quality.py`

**Step 1: Add tests for strategy rationale and logistics wording**

Add tests that assert generated client copy:

- explains `Noir` as an editorial/product contrast direction, not nighttime use
- does not use ambiguous `distribution` without clarifying social rollout
- does not imply shipping/fulfillment logistics unless that data exists

Suggested tests:

```python
def test_legacy_strategy_copy_explains_noir_without_nighttime_sunglasses_confusion() -> None:
    content = atlas_prompt_delivery._message_house(  # noqa: SLF001
        "Create a client-ready Legacy Optical Noir weekend social launch package."
    )

    lowered = content.lower()
    assert "editorial" in lowered or "contrast" in lowered
    assert "nighttime" not in lowered
    assert "usar lentes de sol de noche" not in lowered


def test_legacy_measurement_and_channel_copy_distinguishes_social_rollout_from_shipping() -> None:
    content = atlas_prompt_delivery._measurement_plan()  # noqa: SLF001

    lowered = content.lower()
    assert "social" in lowered or "posting" in lowered or "rollout" in lowered
    assert "shipping" not in lowered
    assert "fulfillment" not in lowered
```

**Step 2: Add tests for logo requirement in media prompts/manifest metadata**

Assert future assets require a Legacy logo/brand mark treatment by default or explicitly block production if logo source is missing.

```python
def test_media_prompts_include_legacy_brand_presence_requirement() -> None:
    prompts = atlas_prompt_delivery._media_prompts(  # noqa: SLF001
        "Create Legacy social posts with logo on each post."
    )

    assert prompts
    assert all("Legacy" in prompt for prompt in prompts)
    assert all("logo" in prompt.lower() or "brand mark" in prompt.lower() for prompt in prompts)
```

**Step 3: Add tests for asset QA blocking weak/placeholder visuals**

Extend or add tests around `_client_package_media_content` / QA report behavior so `production_quality=True` is not enough by itself when a client feedback item flags an asset.

At minimum, add a test for a future helper such as `_client_feedback_quality_gates()` or `_asset_quality_gate_status()`.

**Step 4: Run tests and verify failure**

Run:

```bash
cd /c/Users/mathi/projects/forgegraph/backend
DEBUG=1 USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 UV_PROJECT_ENVIRONMENT=.venv-test-legacy-whatsapp-e2e UV_LINK_MODE=copy uv run python -m pytest tests/unit/services/test_atlas_prompt_delivery_quality.py -q
```

Expected: new tests fail before implementation.

---

### Task 2: Update strategy and copy generation so the PDF answers the client’s strategic objection

**Objective:** Make the client-facing handoff explain the creative territory clearly and avoid the `night sunglasses` confusion.

**Files:**

- Modify: `backend/application/services/atlas_prompt_delivery.py`
- Test: `backend/tests/unit/services/test_atlas_prompt_delivery_quality.py`

**Implementation guidance:**

Update `_message_house()` from a generic `Legacy Optical Noir Message House` to something like:

```python
def _message_house(prompt: str) -> str:
    _ = prompt
    return "\n".join(
        [
            "Legacy Optical Noir Message House",
            "Strategic rationale: Optical Noir is a premium contrast system for product photography, not a literal night-use claim for sunglasses.",
            "Why it works: black, ivory, copper, and controlled reflections make frames and lenses feel sharper, more editorial, and easier to remember in-feed.",
            "Positioning: lujo usable para CDMX; editorial, sobrio, accesible-premium.",
            "Brand presence: every social post should carry a Legacy logo or approved brand mark treatment unless the client explicitly requests clean product-only assets.",
            "Primary CTA: revisar estilos y aprobar piezas antes de publicar.",
            "Tone: Spanish-first, concrete, low-hype, confident.",
        ]
    )
```

Avoid exposing `Source request:` in client-visible source content.

**Verification:**

Run:

```bash
DEBUG=1 USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 UV_PROJECT_ENVIRONMENT=.venv-test-legacy-whatsapp-e2e UV_LINK_MODE=copy uv run python -m pytest tests/unit/services/test_atlas_prompt_delivery_quality.py -q
```

Expected: strategy rationale tests pass.

---

### Task 3: Replace ambiguous “distribution” wording with “social rollout / posting schedule”

**Objective:** Prevent clients from interpreting marketing/channel execution as shipping logistics.

**Files:**

- Modify: `backend/application/services/atlas_prompt_delivery.py`
- Test: `backend/tests/unit/services/test_atlas_prompt_delivery_quality.py`

**Implementation guidance:**

Update `_measurement_plan()`, `_stage_prompt()`, and any visible copy that says `distribution` without context.

Suggested `_measurement_plan()` replacement:

```python
def _measurement_plan() -> str:
    return (
        "Track the weekend social rollout: post saves, replies, profile visits, link clicks, DMs, holds, "
        "sold/blocked status, and next action every 24h. This is a posting/review cadence, not a shipping "
        "or fulfillment timeline unless the client provides logistics details. Hold live claims until connector evidence exists."
    )
```

Also update strategy/channel wording to use:

- `weekend social rollout`
- `posting cadence`
- `review window`

Avoid or qualify:

- `distribution`
- `envíos`
- `shipping`
- `fulfillment`

**Verification:**

Run the quality test suite and inspect generated fallback text for the terms above.

---

### Task 4: Make logo/brand-presence a first-class brand requirement

**Objective:** Ensure all future Legacy posts include a logo/brand mark requirement, instead of relying on ad-hoc client comments.

**Files:**

- Modify: `backend/application/services/atlas_prompt_delivery.py`
- Possibly create: `backend/application/services/atlas_brand_requirements.py`
- Test: `backend/tests/unit/services/test_atlas_prompt_delivery_quality.py`

**Implementation options:**

#### Simple first pass

Update `_media_prompts()` so every prompt includes the logo requirement:

```python
"include an approved Legacy logo or brand mark treatment in a clean corner lockup; no fake brand marks; no unrelated text"
```

But be careful: current code says `no visible words, no logos`. That directly conflicts with the client’s feedback. Replace it with:

```python
"approved Legacy logo/brand mark only; no unrelated visible words, no fake brand marks, no people"
```

#### Better productized version

Introduce a requirements helper:

```python
def _legacy_brand_requirements() -> dict[str, Any]:
    return {
        "logo_required_on_posts": True,
        "logo_policy": "approved_legacy_logo_or_operator_supplied_brand_mark_required",
        "block_production_without_logo_asset": True,
    }
```

Add the requirements to package manifest metadata and QA report.

**Acceptance criteria:**

- Media prompts no longer say `no logos` for Legacy.
- Prompts require `approved Legacy logo or brand mark`.
- Manifest records `logo_required_on_posts: true`.
- QA report blocks `ready` if logo required but logo asset/source is missing.

---

### Task 5: Add an asset QA gate that can fail individual images before package readiness

**Objective:** Avoid sending a package where one image is obviously poor/off-target.

**Files:**

- Modify: `backend/application/services/atlas_prompt_delivery.py`
- Possibly modify: `backend/application/services/codex_media_worker.py`
- Test: `backend/tests/unit/services/test_atlas_prompt_delivery_quality.py`
- Possibly test: `backend/tests/unit/services/test_codex_media_worker.py`

**Implementation guidance:**

Add a deterministic metadata-driven gate first; later it can be backed by vision review.

Suggested helper:

```python
def _asset_quality_gate_status(media_manifest: list[dict[str, Any]], *, logo_required: bool) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    for item in media_manifest:
        if not item.get("production_quality"):
            issues.append({"post": item.get("post"), "code": "not_production_quality"})
        if logo_required and not item.get("brand_mark_applied"):
            issues.append({"post": item.get("post"), "code": "missing_brand_mark"})
        if item.get("client_flagged_bad"):
            issues.append({"post": item.get("post"), "code": "client_flagged_bad"})
    return {"ready": not issues, "issues": issues}
```

Then include this in:

- `manifest.json`
- visible QA section
- package readiness decision

**Acceptance criteria:**

- A client-flagged or missing-logo asset blocks `ready for review`.
- QA evidence lists the exact post index and issue code.
- The package can still be generated as a draft, but not labeled production-ready.

---

### Task 6: Add PDF/client-feedback ingestion as a durable whiteboard event

**Objective:** Convert reviewed PDF annotations into product-owned state instead of losing them in chat context.

**Files:**

- Create: `backend/application/services/client_review_feedback.py`
- Create or modify tests: `backend/tests/unit/services/test_client_review_feedback.py`
- Possibly modify: `backend/infrastructure/orm/models.py` only if an existing model cannot represent feedback.

**Implementation guidance:**

Start with a service that accepts extracted annotations as structured input. Do not require PDF parsing in the core service yet.

Suggested shape:

```python
@dataclass(frozen=True)
class ClientReviewComment:
    page: int
    comment_type: str
    content: str
    rect: list[float] | None = None
    created_at: str = ""
```

Classifier output:

```python
{
    "category": "strategy_rationale" | "asset_quality" | "logistics_ambiguity" | "brand_logo_requirement",
    "department_slug": "strategy_research" | "brand_content" | "channel_execution" | "qa_compliance",
    "severity": "blocker" | "revision" | "note",
    "acceptance_criteria": [...],
}
```

Persist into whiteboard metadata first if schema work is too large:

```python
whiteboard.metadata_json["client_feedback"] = {
    "source": "reviewed_pdf_annotations",
    "comments": [...],
    "cards": [...],
}
```

Longer term, use real `Card`, `CardTransition`, and `HandoffPacket` models.

**Acceptance criteria:**

- PDF comments can be recorded against a `WorkWhiteboard`.
- Each comment maps to a department card.
- Each card has acceptance criteria and status `proposed` or `triaged`.
- No client feedback depends only on an LLM/chat summary.

---

### Task 7: Add whiteboard cards/gates for future packages

**Objective:** Make the whiteboard better than a generic Kanban by tying cards to actual deliverable quality gates.

**Files:**

- Modify: `backend/application/services/work_whiteboards.py`
- Modify or create: `backend/application/services/whiteboard_boards.py`
- Modify: `backend/application/services/company_run_task_routing.py`
- Test: `backend/tests/unit/services/test_whiteboard_board.py`
- Test: `backend/tests/unit/services/test_company_run_task_routing.py`

**Card examples to auto-create for Atlas client packages:**

1. `Strategy rationale approved`
   - Owner: `strategy_research`
   - Evidence: strategy section in handoff
   - Acceptance: creative territory explains why it fits product/category/client
2. `Brand requirements locked`
   - Owner: `brand_content`
   - Evidence: logo/brand constraints in manifest
   - Acceptance: logo policy resolved
3. `Assets pass visual QA`
   - Owner: `qa_compliance`
   - Evidence: per-asset QA status
   - Acceptance: no bad/placeholder/missing-logo assets
4. `Channel wording unambiguous`
   - Owner: `channel_execution`
   - Evidence: social rollout copy
   - Acceptance: no shipping implication unless logistics exists
5. `Client package safe`
   - Owner: `client_approval_ops`
   - Evidence: ZIP hash, no Markdown, no internal IDs, PDF generated from HTML
6. `Delivery receipt captured`
   - Owner: `client_approval_ops`
   - Evidence: WhatsApp IDs and receipt IDs

**Acceptance criteria:**

- Cards are self-contained and scoped.
- Cards have concrete evidence requirements.
- Status cannot move to `approved` without evidence.
- Whiteboard snapshot/cache reflects durable DB state, not vice versa.

---

### Task 8: Add coordinator reconciliation before final package/send

**Objective:** Prevent direct generation/send when known feedback or gate failures exist.

**Files:**

- Modify: `backend/application/services/atlas_prompt_delivery.py`
- Possibly create: `backend/application/services/atlas_client_package_gates.py`
- Test: `backend/tests/unit/services/test_atlas_prompt_delivery_quality.py`

**Implementation guidance:**

Add a pre-send gate:

```python
def _client_package_gate_report(*, manifest: dict[str, Any], deliverable_sections: list[dict[str, str]]) -> dict[str, Any]:
    issues = []
    # strategy rationale present
    # logo requirement resolved
    # asset QA ready
    # no ambiguous channel/logistics wording
    # no internal IDs / markdown leaks
    return {"ready": not issues, "issues": issues}
```

Then:

- Always write gate report into `manifest.json`.
- If `send=True` and gate report is not ready, raise a clear error unless an explicit operator override is passed.
- If `send=False`, generate package as draft with `status: blocked_for_revision`.

**Acceptance criteria:**

- Actual WhatsApp send cannot happen with known client-feedback blockers.
- Dry run can still produce a package for review.
- Gate failures are visible and department-owned.

---

### Task 9: Regenerate corrected Legacy package and inspect before sending

**Objective:** Produce a corrected package that directly addresses all five comments.

**Files / artifacts:**

- Output under: `backend/.hermes/forgegraph_atlas_prompt_runs/...`
- Optional updated AI assets under: `backend/.hermes/legacy_optical_noir_review_assets_ai_v2/`

**Required content changes:**

- Strategy section explains `Optical Noir` rationale.
- Bad image replaced.
- All posts have Legacy logo/brand mark treatment.
- Copy says `weekend social rollout/posting schedule`, not ambiguous `distribution`.
- Manifest includes brand/logo policy and QA gates.

**Run dry first:**

```bash
cd /c/Users/mathi/projects/forgegraph/backend
DEBUG=1 USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 UV_PROJECT_ENVIRONMENT=.venv-test-legacy-whatsapp-e2e UV_LINK_MODE=copy uv run python infrastructure/orm/management/commands/run_atlas_prompt_delivery.py \
  --no-send \
  --codex-command 'C:\Users\mathi\AppData\Roaming\npm\codex.cmd'
```

Adjust command path if the management command is invoked via `manage.py` in the current branch.

**Inspect package:**

- No Markdown files.
- No internal IDs visible.
- PDF generated via Chromium/Playwright.
- Comments addressed in visible PDF text.
- Logo/brand mark visible on each asset.
- Weak image replaced.

Only after inspection should a send be considered.

---

### Task 10: Verification commands

**Objective:** Verify code and package quality with real tool output.

Run from `backend`:

```bash
DEBUG=1 USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 UV_PROJECT_ENVIRONMENT=.venv-test-legacy-whatsapp-e2e UV_LINK_MODE=copy uv run python -m pytest tests/unit/services/test_atlas_prompt_delivery_quality.py -q
```

```bash
DEBUG=1 USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 UV_PROJECT_ENVIRONMENT=.venv-test-legacy-whatsapp-e2e UV_LINK_MODE=copy uv run python -m pytest tests/unit/services/test_whiteboard_board.py tests/unit/services/test_company_run_task_routing.py -q
```

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-legacy-whatsapp-e2e UV_LINK_MODE=copy uv run ruff check application/services/atlas_prompt_delivery.py application/services/work_whiteboards.py tests/unit/services/test_atlas_prompt_delivery_quality.py
```

```bash
DEBUG=1 USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 UV_PROJECT_ENVIRONMENT=.venv-test-legacy-whatsapp-e2e UV_LINK_MODE=copy uv run python manage.py check
```

---

## Risks / Tradeoffs

- **Logo in generated images:** AI image generation may mangle text/logo. Best approach is likely post-compositing an approved logo overlay onto generated imagery, not asking the image model to render the logo. If no official logo asset exists, block production-ready and request/attach logo source.
- **Too many gates can slow delivery:** Keep gates lightweight and evidence-backed; do not create bureaucracy without artifact checks.
- **Whiteboard schema scope:** If adding real card tables is too much for this PR, start by storing `client_feedback` and `quality_gates` in `WorkWhiteboard.metadata_json`, then migrate to first-class models later.
- **Client language:** The handoff should be Spanish-first and concise. Avoid internal terms like `Codex`, `stage`, `run`, `department slug`, and `distribution` unless translated into client-facing language.

---

## Open Questions

1. Do we have an approved Legacy logo file to composite onto each post?
2. Should `Optical Noir` remain the creative territory after clarification, or should we rename it to something less night-coded?
3. Should the corrected package be sent immediately after dry-run verification, or should Mike review the corrected PDF first?
4. Should PDF annotation ingestion be a backend service now, or is manual structured feedback intake enough for this PR?

---

## Recommended Execution Order

1. Tests for client feedback failures.
2. Copy/strategy/logistics wording fixes.
3. Brand/logo requirement and QA gate.
4. Whiteboard feedback/cards metadata.
5. Coordinator pre-send gate.
6. Regenerate dry-run package.
7. Inspect package visually/textually.
8. Only then send if approved.

This handles the immediate client comments and upgrades ForgeGraph’s whiteboard from “status board” to “evidence-backed client-deliverable operating system.”
