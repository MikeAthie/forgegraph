# ForgeGraph Media Quality Implementation Plan

## Goal

Fix ForgeGraph media delivery so client-ready media packages can only contain real image artifacts from production-quality-capable provider paths. Placeholder-quality outputs from `codex_spec_renderer` may still be generated for previews, debugging, or development, but they must fail or hold any client-ready media gate.

This plan is exclusively about media quality: provider capability contracts, artifact persistence, media QA status, and safe fallback behavior. It does not solve report or presentation defects except where delivery status must accurately say media is blocked or QA-failed.

## Architecture

Follow `docs/architecture/runtime-invariants.md` strictly:

- Backend durable state remains authoritative for `MediaGenerationJob`, `Asset`, `AssetVersion`, `ServiceDeliverable`, QA status, and resume state.
- Media workers and providers may execute generation work and hold ephemeral execution state, but they do not own durable state.
- Events may report progress and observability, but client-ready eligibility is derived only from backend-owned records and metadata.
- Snapshots, liveness, recovery, and durable resume behavior stay backend-owned.

The implementation should adapt existing ForgeGraph primitives before considering migrations. Provider capability snapshots, artifact metadata, and QA results should live in existing metadata/provenance fields on `MediaGenerationJob`, `AssetVersion`, and `ServiceDeliverable` unless inspection proves a field is missing.

## Tech Stack

- Python backend services under `backend/application/services/`
- Django ORM models under `backend/infrastructure/orm/models/`
- Existing durable primitives: `MediaGenerationJob`, `Asset`, `AssetVersion`, `ServiceDeliverable`
- Unit tests with `pytest`
- Static checks with `ruff`
- Local verification through `uv` on Mike's Windows/Git Bash setup

## Non-Goals

- Do not hardcode Atlas, Legacy, Optical Noir, or sunglasses-specific behavior as permanent product logic.
- Do not treat Codex JSON art direction as a production image artifact.
- Do not make the engine, Codex, or any client authoritative for durable media readiness.
- Do not fix GitHub #77/report presentation except for wording that accurately reflects media QA state.
- Do not add migrations unless metadata fields cannot safely express provider capability and QA state.

## Current Problem To Preserve In Tests

The failing behavior is:

- ForgeGraph selects `codex_spec_renderer`.
- `CodexMediaWorker` asks Codex for strict JSON art direction.
- ForgeGraph calls `render_codex_image_spec_png()`, which produces deterministic rectangle/ellipse placeholder PNGs.
- The generated media can be packaged as client-ready despite being doodle/vector placeholder quality.

The desired behavior is:

- `codex_spec_renderer` is permanently classified as placeholder-only.
- Placeholder media can be stored for traceability, but it cannot satisfy client-ready gates.
- When a production-quality provider is configured, ForgeGraph stores real image artifacts and gates them through backend-owned QA metadata.
- When only placeholder providers are available, ForgeGraph holds/fails media delivery with explicit QA status instead of silently shipping placeholders.

## Files Likely To Change

Primary service files:

- `backend/application/services/codex_media_worker.py`
- `backend/application/services/atlas_prompt_delivery.py`
- `backend/application/services/gemini_media.py`

Likely new focused helpers, if no equivalent exists:

- `backend/application/services/media_provider_capabilities.py`
- `backend/application/services/media_quality.py`

Model file to inspect but avoid schema changes unless required:

- `backend/infrastructure/orm/models/decisions_assets.py`

Tests:

- `backend/tests/unit/services/test_codex_media_worker.py`
- `backend/tests/unit/services/test_atlas_prompt_delivery_quality.py`
- `backend/tests/unit/services/test_gemini_media.py` if present or create it if needed
- `backend/tests/unit/services/test_media_provider_capabilities.py`
- `backend/tests/unit/services/test_media_quality.py`

Spike references for manual comparison only:

- `spikes/001-atlas-external-run/README.md`
- `spikes/001-atlas-external-run/prompts_and_tool_log.json`

## Provider Capability Contract

Add a small backend service contract that every media provider path must declare before a job is considered for client-ready delivery.

Suggested shape:

```python
@dataclass(frozen=True)
class MediaProviderCapabilities:
    provider_key: str
    artifact_kind: Literal["image/png", "image/jpeg", "image/webp", "image_spec_json", "placeholder_png"]
    production_quality_capable: bool
    quality_tier: Literal["placeholder", "draft", "production"]
    requires_external_artifact: bool
    qa_requirements: tuple[MediaQARequirement, ...]
```

Suggested QA requirement enum:

```python
class MediaQARequirement(StrEnum):
    NON_PLACEHOLDER_PROVIDER = "non_placeholder_provider"
    REAL_IMAGE_ARTIFACT = "real_image_artifact"
    VALID_MIME_TYPE = "valid_mime_type"
    MIN_DIMENSIONS = "min_dimensions"
    PROMPT_PROVENANCE = "prompt_provenance"
    PROVIDER_PROVENANCE = "provider_provenance"
```

Provider declarations:

- `codex_spec_renderer`: `artifact_kind="placeholder_png"`, `quality_tier="placeholder"`, `production_quality_capable=False`, cannot satisfy `NON_PLACEHOLDER_PROVIDER`.
- Real image providers such as Gemini, OpenAI image generation, FAL, or a Codex artifact-producing path: `artifact_kind` must be a real raster MIME type, `production_quality_capable=True`, and must require actual image artifact persistence.
- A provider that only returns JSON, prompts, SVG sketches, or local geometric renderings is not production-quality capable.

Persist a snapshot of these capabilities into job/version metadata at generation time so later delivery decisions do not depend on mutable provider code or config.

## Metadata Design Without Migrations

Prefer existing metadata/provenance fields:

`MediaGenerationJob` metadata:

```json
{
  "media_provider": {
    "provider_key": "codex_spec_renderer",
    "artifact_kind": "placeholder_png",
    "quality_tier": "placeholder",
    "production_quality_capable": false,
    "qa_requirements": ["non_placeholder_provider", "real_image_artifact"]
  },
  "requested_use": "client_ready_media",
  "client_ready_eligible": false,
  "blocked_reason": "provider_not_production_quality_capable"
}
```

`AssetVersion` metadata:

```json
{
  "media": {
    "provider_key": "gemini_image",
    "artifact_kind": "image/png",
    "quality_tier": "production",
    "production_quality": true,
    "width": 1536,
    "height": 1024
  },
  "provenance": {
    "prompt_hash": "...",
    "provider_request_id": "...",
    "generation_job_id": "..."
  },
  "qa": {
    "status": "passed",
    "checks": {
      "non_placeholder_provider": "passed",
      "real_image_artifact": "passed",
      "valid_mime_type": "passed",
      "min_dimensions": "passed"
    }
  }
}
```

`ServiceDeliverable` metadata:

```json
{
  "media_package": {
    "client_ready": false,
    "qa_status": "blocked",
    "blocked_reasons": ["provider_not_production_quality_capable"],
    "asset_version_ids": ["..."]
  }
}
```

Only add a migration if these metadata paths cannot be represented, queried, or recovered safely with the current model fields.

## Phased Approach

### Phase 1: Safety Gates Before Real Providers

Objective: make the current placeholder path safe even before a real provider is wired.

Tasks:

1. Add tests proving `codex_spec_renderer` cannot be client-ready.
   - Red test: a `MediaGenerationJob` completed through `CodexMediaWorker` with `codex_spec_renderer` produces an `AssetVersion` but marks `quality_tier=placeholder`, `production_quality=False`, and `client_ready_eligible=False`.
   - Red test: `atlas_prompt_delivery` refuses to package placeholder media as client-ready.
   - Red test: delivery status says media is blocked or QA-failed for media quality, not "ready".

2. Add a media QA gate in the delivery packaging path.
   - Gate on provider capability snapshot, not event messages.
   - Require `production_quality_capable=True`.
   - Require non-placeholder `quality_tier`.
   - Require an actual image artifact MIME type and persisted artifact metadata.
   - If the gate fails, keep the backend deliverable in `blocked`, `needs_media_provider`, or existing equivalent status.

3. Keep placeholder artifacts observable.
   - Store the placeholder `AssetVersion` if current behavior already does.
   - Preserve provenance for debugging.
   - Mark it explicitly as non-client-ready.

Suggested tests:

- `backend/tests/unit/services/test_codex_media_worker.py::test_codex_spec_renderer_marks_placeholder_not_production_quality`
- `backend/tests/unit/services/test_atlas_prompt_delivery_quality.py::test_placeholder_media_is_not_client_ready`
- `backend/tests/unit/services/test_atlas_prompt_delivery_quality.py::test_delivery_holds_when_only_placeholder_media_available`
- `backend/tests/unit/services/test_atlas_prompt_delivery_quality.py::test_media_qa_status_explains_provider_quality_block`

### Phase 2: Provider Capability Registry

Objective: make provider quality a first-class backend contract.

Tasks:

1. Introduce `MediaProviderCapabilities` in a small service module or existing media provider abstraction.
   - Start with static declarations for existing paths.
   - Avoid coupling the contract to Atlas-specific campaign language.

2. Snapshot provider capabilities onto `MediaGenerationJob` and `AssetVersion` metadata.
   - The backend persists what provider was used and what quality it declared at the time.
   - Delivery reads persisted metadata first.

3. Add contract tests.
   - Every registered provider declares `provider_key`, `artifact_kind`, `quality_tier`, `production_quality_capable`, and `qa_requirements`.
   - Placeholder providers cannot declare `production_quality_capable=True`.
   - Production providers must declare real raster artifact kinds and QA requirements.

Suggested tests:

- `backend/tests/unit/services/test_media_provider_capabilities.py::test_codex_spec_renderer_capabilities_are_placeholder_only`
- `backend/tests/unit/services/test_media_provider_capabilities.py::test_production_capable_provider_requires_real_image_artifact`
- `backend/tests/unit/services/test_media_provider_capabilities.py::test_provider_capabilities_are_snapshotted_to_job_metadata`
- `backend/tests/unit/services/test_media_provider_capabilities.py::test_delivery_gate_uses_persisted_capability_snapshot`

### Phase 3: Real Image Provider Path

Objective: route configured production media jobs to a provider that returns real image artifacts.

Tasks:

1. Inspect `backend/application/services/gemini_media.py` and any existing provider abstraction.
   - If Gemini already supports image artifact output, adapt it first.
   - If it only supports prompt/text flows, add a real image provider behind the same contract rather than expanding `codex_spec_renderer`.

2. Configure provider selection.
   - Add or use existing config such as `MEDIA_IMAGE_PROVIDER`.
   - Production/client-ready media requests should prefer production-capable providers.
   - If no production-capable provider is configured, create/hold the backend job with `blocked_reason="no_production_media_provider_configured"`.

3. Persist real artifacts through existing asset primitives.
   - Store raster bytes or durable artifact references as `Asset`/`AssetVersion`.
   - Persist MIME type, dimensions, prompt/provenance hash, provider request id, and capability snapshot.
   - Do not use events as the authoritative source of artifact readiness.

4. Preserve prompt richness.
   - Pass full visual prompts and constraints to the real provider.
   - Avoid reducing rich art direction to JSON that is later rendered by local geometric code.
   - Keep prompts generic and user/request-derived, not Legacy/Optical Noir-specific.

5. Add fake-provider tests for deterministic behavior.
   - Use a fake production-capable provider returning a small valid PNG/JPEG fixture.
   - Assert that successful media passes gates because the provider contract and artifact metadata are valid, not because subjective visual judgment passed.

Suggested tests:

- `backend/tests/unit/services/test_gemini_media.py::test_gemini_image_provider_declares_production_capabilities`
- `backend/tests/unit/services/test_atlas_prompt_delivery_quality.py::test_real_provider_media_can_be_packaged_client_ready`
- `backend/tests/unit/services/test_atlas_prompt_delivery_quality.py::test_no_production_provider_holds_delivery_instead_of_falling_back_to_placeholder`
- `backend/tests/unit/services/test_media_quality.py::test_valid_real_image_artifact_passes_required_quality_checks`
- `backend/tests/unit/services/test_media_quality.py::test_json_or_placeholder_artifact_fails_real_image_requirement`

### Phase 4: Objective Media QA Checks

Objective: add deterministic checks that catch placeholder or malformed media before manual review.

Tasks:

1. Validate artifact existence and kind.
   - Artifact exists in backend-owned asset storage.
   - MIME type is allowed for client-ready image packages.
   - File size is above a conservative minimum.

2. Validate dimensions.
   - Use a small image parser to read width and height from bytes or stored metadata.
   - Enforce minimum dimensions appropriate for deliverables.
   - Store measured dimensions in `AssetVersion` metadata.

3. Validate provider/provenance.
   - Require provider capability snapshot.
   - Require prompt hash or equivalent provenance.
   - Require job id linkage.

4. Detect known placeholder paths.
   - Hard fail `provider_key="codex_spec_renderer"` for client-ready use.
   - Optionally add deterministic checks for local renderer signatures if the output metadata exposes them.

Suggested tests:

- `backend/tests/unit/services/test_media_quality.py::test_rejects_missing_artifact_bytes`
- `backend/tests/unit/services/test_media_quality.py::test_rejects_invalid_mime_type`
- `backend/tests/unit/services/test_media_quality.py::test_rejects_below_minimum_dimensions`
- `backend/tests/unit/services/test_media_quality.py::test_rejects_known_placeholder_provider_even_if_png_exists`
- `backend/tests/unit/services/test_media_quality.py::test_records_check_results_in_asset_version_metadata`

### Phase 5: Manual Visual QA Hooks

Objective: make human review practical without making subjective review the only gate.

Tasks:

1. Add a contact-sheet helper for generated media packages.
   - Produce a contact sheet artifact from candidate `AssetVersion` records.
   - Store it as a review/support artifact, not as proof of client readiness.
   - Include provider key, dimensions, QA status, and short prompt label per image.

2. Add optional manual QA metadata.
   - Suggested values: `manual_review.status = pending|approved|rejected|not_required`.
   - Keep objective gates mandatory regardless of manual review.
   - If manual review is required by config or deliverable type, client-ready requires both objective gates and approval.

3. Keep the contact sheet business-agnostic.
   - It should work for any campaign/product/use case.
   - It should not encode sunglasses-specific labels or expected compositions.

Suggested tests:

- `backend/tests/unit/services/test_media_quality.py::test_contact_sheet_is_review_artifact_not_client_ready_evidence`
- `backend/tests/unit/services/test_atlas_prompt_delivery_quality.py::test_manual_rejection_blocks_media_package`
- `backend/tests/unit/services/test_atlas_prompt_delivery_quality.py::test_manual_approval_cannot_override_placeholder_provider_failure`

### Phase 6: Rollout, Observability, And Recovery

Objective: deploy safely without allowing silent fallback to placeholder output.

Tasks:

1. Add status wording for held media packages.
   - Example: `Media delivery blocked: no production-quality media provider configured`.
   - Example: `Media QA failed: provider codex_spec_renderer is placeholder-only`.

2. Add observability events after backend state changes.
   - Emit progress/diagnostic events only after durable backend records are updated.
   - Events should include job id and QA status, but they do not determine readiness.

3. Add recovery behavior.
   - On resume, recompute package readiness from backend-owned `MediaGenerationJob` and `AssetVersion` metadata.
   - Do not infer readiness from worker memory, client state, or event stream history.

4. Add rollout guardrails.
   - Default to fail/hold when provider capability is missing.
   - Feature flag or config-gate new providers.
   - Add metrics/logs for blocked media delivery counts and provider QA failures.

Suggested tests:

- `backend/tests/unit/services/test_atlas_prompt_delivery_quality.py::test_resume_recomputes_media_readiness_from_backend_metadata`
- `backend/tests/unit/services/test_atlas_prompt_delivery_quality.py::test_missing_provider_capabilities_fail_closed`
- `backend/tests/unit/services/test_atlas_prompt_delivery_quality.py::test_status_copy_names_media_quality_block`

## TDD Task Checklist

1. Write failing tests for placeholder rejection in `test_codex_media_worker.py` and `test_atlas_prompt_delivery_quality.py`.
2. Implement the smallest delivery gate that blocks placeholder `AssetVersion` records from client-ready packages.
3. Write failing tests for provider capability declarations.
4. Add the provider capability contract and static declarations for current providers.
5. Write failing tests for metadata snapshots on `MediaGenerationJob` and `AssetVersion`.
6. Persist capability snapshots and QA results through existing metadata fields.
7. Write fake production-provider tests for a valid real image artifact.
8. Wire the first real provider path behind config.
9. Add fail-closed behavior when no production provider is configured.
10. Add deterministic artifact QA checks and contact-sheet review artifact support.
11. Add resume/recovery tests that recompute readiness from backend metadata.
12. Run targeted tests, ruff, and Django checks.

## Verification Commands

Use Mike's Windows/Git Bash setup:

```bash
cd backend
USE_SQLITE=1 USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 DEBUG=0 UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run pytest tests/unit/services/test_codex_media_worker.py -q
```

```bash
cd backend
USE_SQLITE=1 USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 DEBUG=0 UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run pytest tests/unit/services/test_atlas_prompt_delivery_quality.py -q
```

```bash
cd backend
USE_SQLITE=1 USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 DEBUG=0 UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run pytest tests/unit/services/test_media_provider_capabilities.py tests/unit/services/test_media_quality.py -q
```

If `test_gemini_media.py` exists or is added:

```bash
cd backend
USE_SQLITE=1 USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 DEBUG=0 UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run pytest tests/unit/services/test_gemini_media.py -q
```

Ruff:

```bash
cd backend
uv run ruff check application/services/codex_media_worker.py application/services/atlas_prompt_delivery.py application/services/gemini_media.py application/services/media_provider_capabilities.py application/services/media_quality.py tests/unit/services/test_codex_media_worker.py tests/unit/services/test_atlas_prompt_delivery_quality.py tests/unit/services/test_media_provider_capabilities.py tests/unit/services/test_media_quality.py
```

Django check:

```bash
cd backend
USE_SQLITE=1 USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 DEBUG=0 UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python manage.py check
```

## Acceptance Criteria

- `codex_spec_renderer` is always declared placeholder-only and `production_quality_capable=False`.
- A PNG created by the local spec renderer cannot be marked client-ready, even if it has valid bytes and dimensions.
- `atlas_prompt_delivery` refuses to create a client-ready media package when all available media is placeholder-quality.
- When only `codex_spec_renderer` is available, ForgeGraph holds or fails media delivery with a backend-owned QA status and explicit blocked reason.
- When a configured production-capable provider returns a valid raster artifact, ForgeGraph stores it as `Asset`/`AssetVersion` with provider capability snapshot, provenance, dimensions, and QA results.
- Delivery readiness is computed from backend-owned job/version/deliverable metadata, not from events, worker memory, or client state.
- Resume/recovery recomputes media readiness from durable backend records.
- Manual visual QA can block or approve media when configured, but it cannot override objective failure of placeholder provider gates.
- The implementation remains business-agnostic and does not encode Legacy, Optical Noir, sunglasses, or campaign-specific assumptions.

## Hermes Agent Codex Image Generation Addendum

A follow-up investigation found a copyable upstream Hermes implementation for Codex-backed image generation:

```text
.hermes/plans/codex-image-generation-hermes-findings.md
```

Key update: ForgeGraph should add a ForgeGraph-owned production provider equivalent to Hermes' `plugins/image_gen/openai-codex/` path: ForgeGraph-managed Codex OAuth/config → `POST https://chatgpt.com/backend-api/codex/responses` → required Responses `image_generation` tool → `gpt-image-2` PNG bytes → ForgeGraph `AssetVersion` persistence. Hermes is reference code only; ForgeGraph production must not depend on Hermes tools, profiles, cache paths, gateways, or auth files.

Provider policy: `openai_codex_image_generation` is the primary production media path. If it is not configured, ForgeGraph should enter a configuration-required/blocked state with setup guidance. Gemini may exist as redundancy only when Codex is configured but temporarily unavailable/failing, not as an automatic switch that hides missing Codex setup.

Important correction: the previous external Atlas spike used `fal.media` URLs, so it proved the workflow/tool-boundary issue, not that those specific images were Codex-generated. The Hermes Agent repo nevertheless has the Codex-backed implementation we can adapt.

## Open Questions And Tradeoffs

- How should ForgeGraph-owned Codex OAuth/config be stored, refreshed, validated, and surfaced to operators without depending on Hermes credentials?
- What exact setup flow should move `openai_codex_image_generation` from `configuration_required` to `available`?
- Under what runtime failure conditions should Gemini redundancy activate, and how should the package record that Gemini was used as fallback evidence?
- What cost, concurrency, and rate-limit policy should govern production image generation?
- What minimum dimensions and MIME types should be required for each deliverable class?
- Should manual review be required for all client-ready media at first rollout, or only for high-risk deliverable types?
- How should deterministic tests approximate image quality without brittle subjective assertions?
- Should old placeholder media be backfilled with explicit QA-failed metadata, or is fail-closed delivery gating sufficient for existing records?
