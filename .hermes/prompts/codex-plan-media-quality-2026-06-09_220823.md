You are Codex running in PLAN MODE for ForgeGraph.

IMPORTANT CONSTRAINTS:
- Planning only. Do not implement code changes.
- Do not edit any project files except the final markdown plan file requested below.
- Focus EXCLUSIVELY on media quality. Do not solve the client report/presentation issue except where it intersects with media QA status wording.
- Keep ForgeGraph generic/business-agnostic. Do not hardcode Legacy or Optical Noir as permanent product behavior.
- Prefer existing ForgeGraph primitives (`MediaGenerationJob`, `Asset`, `AssetVersion`, `ServiceDeliverable`, provenance/metadata) before new models/migrations.
- The goal is product-quality media delivery: real image artifacts, provider capability contracts, quality gates, and safe fallback behavior.

CONTEXT:
We ran two variants of an Atlas/ForgeGraph campaign flow for a sunglasses launch.

1. ForgeGraph internal run produced poor media:
   - Provider path: `codex_spec_renderer`.
   - `CodexMediaWorker` asks Codex for strict JSON art direction.
   - ForgeGraph then calls `render_codex_image_spec_png()` which draws deterministic rectangles/ellipses.
   - Result: doodle/vector placeholder sunglasses, repeated/generic compositions.
   - This path has now been marked placeholder-quality in code: `quality_tier=placeholder`, `production_quality=False`.

2. External Atlas/Hermes spike produced much better media:
   - It called a real image artifact tool directly (`image_generate`) six times with rich visual prompts.
   - Results looked like product photography/editorial still-life.
   - Full comparison is saved at `spikes/001-atlas-external-run/README.md` and prompt/tool log at `spikes/001-atlas-external-run/prompts_and_tool_log.json`.

Current diagnosis:
- The quality gap is mainly the tool boundary, not just prompt wording.
- ForgeGraph currently reduces Codex to JSON art direction, then discards prompt richness through a simple local renderer.
- Production-quality output requires either:
  A) ForgeGraph MediaGenerationJob routes to a real image provider (FAL/OpenAI/Gemini/etc. through existing abstraction if present), or
  B) Codex runs as an artifact-producing agent that writes/exports real images, not a JSON-only spec.
- `codex_spec_renderer` must remain placeholder-only and must not be allowed to satisfy client-ready media gates.

RELEVANT ISSUE:
- GitHub #74: "Atlas delivery can send placeholder codex_spec_renderer media as client-ready handoff".

RELEVANT FILES TO INSPECT:
- `backend/application/services/codex_media_worker.py`
- `backend/application/services/atlas_prompt_delivery.py` (only media generation, media package, and QA/delivery gating sections)
- `backend/application/services/gemini_media.py`
- `backend/tests/unit/services/test_codex_media_worker.py`
- `backend/tests/unit/services/test_atlas_prompt_delivery_quality.py`
- `backend/infrastructure/orm/models/decisions_assets.py` for MediaGenerationJob / AssetVersion metadata shape
- `spikes/001-atlas-external-run/README.md`
- `spikes/001-atlas-external-run/prompts_and_tool_log.json`

TASK:
Inspect the repo and write an implementation plan to fix ForgeGraph media quality. Save it to:

`.hermes/plans/2026-06-09_220823-forgegraph-media-quality-plan.md`

PLAN REQUIREMENTS:
- Start with the standard plan header:
  `# ForgeGraph Media Quality Implementation Plan`
  plus Goal, Architecture, Tech Stack.
- Keep it focused exclusively on media quality.
- Include a phased approach that starts with safety gates before adding real providers.
- Include exact files likely to change.
- Include bite-sized tasks with TDD-style steps.
- Include test names/locations and verification commands for Mike's Windows/Git Bash setup:
  `cd backend`
  `USE_SQLITE=1 USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 DEBUG=0 UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run pytest ... -q`
  `uv run ruff check ...`
  `uv run python manage.py check`
- Include acceptance criteria that would prevent the doodle outputs from being sent as client-ready.
- Include a provider capability contract design: provider declares whether it is production-quality capable, artifact kind, and QA requirements.
- Include how to adapt the existing `MediaGenerationJob`/`AssetVersion` metadata instead of adding migrations unless absolutely necessary.
- Include how ForgeGraph should use a real image provider path when configured, and how it should fail/hold when only `codex_spec_renderer` is available.
- Include manual visual QA hooks/contact-sheet idea, but do not require subjective QA as the only gate.
- Include open questions/tradeoffs: which real provider to wire first, whether Codex artifact-producing agent is allowed, cost/rate limits, deterministic tests for image quality.

DO NOT:
- Implement the plan.
- Open PRs.
- Modify tests/code.
- Focus on the report issue (#77) beyond noting that QA status should reflect media quality.
