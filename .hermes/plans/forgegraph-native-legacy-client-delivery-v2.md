# ForgeGraph-native Legacy client delivery v2

## Problem

The second Legacy package had the right client quality bar, but it was produced by Hermes directly:

- strategy was local JSON;
- image generation was direct tool use;
- PDF/HTML/ZIP assembly was a local script;
- WhatsApp delivery was direct bridge calls;
- ForgeGraph did not own the engagement, department stages, assets, deliverables, approval/readiness state, or send receipts.

That means the result was good agency work, but not proof that ForgeGraph can produce the work.

## Product requirement

A comparable run must be executed through ForgeGraph backend-owned state and then rendered/exported for delivery.

Minimum invariant: every client-facing artifact in the final package must be traceable to a ForgeGraph `ServiceEngagement`, department pipeline stage, `ServiceDeliverable`, `Asset`/`AssetVersion`, and delivery/send receipt.

## Existing repo primitives to use

Already present:

- `backend/application/services/department_pipeline.py`
  - `CompanyProgram` + `ProgramStageState` department pipeline
  - `start_stage`, `complete_stage`, `attach_deliverable_to_stage`, `attach_asset_to_stage`
- `backend/application/services/legacy_weekend_pipeline.py`
  - pipeline-aware Legacy fixture, but still file/Markdown-oriented and not the new client-quality run
- `backend/application/services/agency_deliverables.py`
  - backend-owned Atlas deliverable assembly
  - currently writes Markdown asset versions (`mime_type="text/markdown"`), which should become internal/source only, not client delivery
- `ServiceEngagement`, `ServiceDeliverable`, `Asset`, `AssetVersion`, `MediaGenerationJob`, `TaskRoutingRecord`, `CompanySignal`/`StateProjection`

## Proposed slice

### 1. Add a ForgeGraph-native run service

Create:

```text
backend/application/services/legacy_client_delivery_run.py
```

Responsibilities:

1. Ensure/reuse Legacy company, service catalog item, service engagement, whiteboard, operating pack, departments.
2. Create/reuse department pipeline for the engagement.
3. Execute stages in backend-owned order:
   - `strategy_research`: produce strategy constraints and account/context/strategy deliverables.
   - `brand_content`: produce message house, creative prompts, copy system.
   - `channel_execution`: create channel plan, publication-ready drafts, and export-ready assets.
   - `qa_compliance`: validate no Markdown in client package, freshness/provenance of media, factual claims, dimensions.
   - `client_approval_ops`: assemble PDF/HTML/ZIP and record WhatsApp send intent/receipt.
4. Persist every output as `ServiceDeliverable` and/or `AssetVersion` with `provenance_json` referencing upstream stage outputs.

For this first slice, skip CRM/analytics explicitly with reasons because the requested scope excludes them.

### 2. Move strategy-before-media into durable state

`strategy_research` stage writes:

```json
{
  "campaign": "Optical Noir",
  "objective": "...",
  "message_platform": "La noche empieza antes de salir.",
  "visual_constraints": {...},
  "asset_generation_policy": "generate_after_strategy"
}
```

Then `brand_content` and `channel_execution` must read that state to generate prompts/assets. Tests should fail if media generation starts without strategy constraints.

### 3. Backend-owned media generation job records

For each asset:

- create `MediaGenerationJob` before generation;
- store prompt, strategy hash, requested dimensions, provider/mode metadata;
- create `Asset` + `AssetVersion` when generation completes;
- attach asset to `channel_execution` stage;
- mark originals/source references separately from final generated assets.

If the current media generation implementation cannot call the configured AI provider inside ForgeGraph yet, first implementation can accept operator-supplied generated files, but must still record them as imported completion of `MediaGenerationJob` with provenance. The product target remains backend-owned generation.

### 4. Client-ready renderer/exporter

Add or extend a generic renderer so the client package is derived from ForgeGraph state:

```text
backend/application/services/client_delivery_renderer.py
```

Outputs:

- PDF handoff
- polished HTML handoff
- ZIP containing only:
  - `deliverables/*.pdf`
  - `deliverables/*.html`
  - `assets/*.png`
  - `manifest.json`

Rules:

- no `.md` files in client ZIP;
- Markdown can be stored only as internal source/provenance;
- manifest includes deliverable IDs, asset version IDs, stage IDs, quality gate results, and send receipt IDs.

### 5. WhatsApp delivery through ForgeGraph connector path

Do not call `http://127.0.0.1:3008` directly from Hermes as the final product path.

Add/extend a backend service that:

- builds a send request from the approved package;
- uses configured WhatsApp connector policy;
- persists attempt and receipt as backend state;
- records `messageId`, recipient, attachment filename, package hash;
- returns a safe summary.

Hermes may trigger the ForgeGraph API locally, but the durable attempt/receipt must be in ForgeGraph.

### 6. Whiteboard/Kanban representation

Whiteboard cards should render from backend pipeline state, not local Hermes todos:

- Strategy & Research — completed, outputs: account brief, strategy constraints
- Brand & Content — completed, outputs: message house, prompts/copy
- Channel Execution — completed, outputs: channel plan, 6 generated assets, captions
- QA & Compliance — completed, outputs: client ZIP checks, no Markdown, dimensions, claims
- Client / Approval Ops — completed, outputs: PDF/HTML/ZIP, WhatsApp receipt
- CRM/Analytics — skipped with scope reason

Each card should show evidence links, output counts, blockers, owner department, and downstream handoff.

## Tests / acceptance criteria

Add targeted tests around the new service:

```text
backend/tests/unit/services/test_legacy_client_delivery_run.py
backend/tests/unit/services/test_client_delivery_renderer.py
backend/tests/unit/api/test_service_engagement_client_delivery_api.py  # if API added in same slice
```

Acceptance criteria:

1. Running the service creates/reuses one `ServiceEngagement` for Legacy.
2. Department pipeline stages are created and progressed by the service.
3. Strategy stage completes before any media job/asset version is created.
4. All six requested deliverables exist as `ServiceDeliverable` records with owner department metadata.
5. Six final generated assets exist as `AssetVersion` records linked to channel execution.
6. Client ZIP contains PDF/HTML/assets/manifest only and zero Markdown files.
7. Manifest references ForgeGraph IDs and stage lineage, not just filesystem paths.
8. WhatsApp send attempt/receipt is persisted in ForgeGraph before reporting success.
9. Whiteboard/task snapshot can be rendered from backend state and shows stage outputs.

## Commands for verification

Use Mike's Windows/Git Bash backend env pattern:

```bash
cd backend
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run --group dev pytest tests/unit/services/test_legacy_client_delivery_run.py tests/unit/services/test_client_delivery_renderer.py -q
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run ruff check application/services/legacy_client_delivery_run.py application/services/client_delivery_renderer.py tests/unit/services/test_legacy_client_delivery_run.py tests/unit/services/test_client_delivery_renderer.py
DEBUG=1 USE_SQLITE=1 USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python manage.py check
```

## Implementation order

1. Plan/review this approach.
2. TDD service test for strategy-before-assets and no Markdown client ZIP.
3. Implement `legacy_client_delivery_run.py` with existing primitives.
4. Implement/extend renderer/exporter.
5. Add connector receipt persistence path.
6. Add API endpoint only after service semantics are solid.
7. Verify, then run a third package generation by calling ForgeGraph backend, not direct Hermes scripts.
