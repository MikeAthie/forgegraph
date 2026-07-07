# Whiteboard Client Handoff Renderer Implementation Plan
> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.
**Goal:** Build a generic ForgeGraph-owned client handoff renderer that turns backend-owned deliverables and asset versions into polished agency-grade handoff packages: executive approval packet first, department artifacts second, manifest and receipts explicit, client ZIP clean by default.
**Architecture:** Backend remains the only durable source of truth. `ServiceDeliverable` and `AssetVersion` hold canonical source content; generated HTML/PDF/PNG/JSON/ZIP files are derived `AssetVersion`s with complete provenance. Engines/workers may execute rendering work and hold ephemeral state, but package state, resume state, quality results, manifests, liveness, and recovery remain backend-owned.
**Tech Stack:** Django backend, existing ForgeGraph application services, existing deliverable formatting modules, existing asset/version models, pytest, ruff, `uv`, Windows/Git Bash verification commands.

## Planning Notes

- This plan intentionally does not add a Hermes runtime dependency, shell out to Hermes, or copy Hermes code.
- The first implementation slice must re-open `docs/architecture/runtime-invariants.md` and verify every edit keeps durable package state in the backend.
- The current implementation can wait for Mike to review any existing PR. Keep the first implementation PR narrow and characterization-focused so it can be rebased after that review.
- If the repo has a different test directory layout than the paths below, keep the same test names and move them to the existing local convention after running `rg --files`.

## Current Repo Paths To Inspect First

- `docs/architecture/runtime-invariants.md`
- `application/services/strategy_report_builder.py`
- `application/services/deliverable_formatting.py`
- `application/services/deliverable_format_renderers.py`
- `application/services/deliverable_format_profiles.py`
- `application/services/deliverable_format_quality.py`
- `application/services/atlas_prompt_delivery.py`
- Existing model modules containing `CompanyProgram`, `ProgramStageState`, `ServiceDeliverable`, `Asset`, `AssetVersion`, `TaskRoutingRecord`, and any whiteboard models.
- Existing tests under `application/tests/`, `tests/`, or the repo's current pytest layout.

Useful preflight inspection commands:

```bash
rg --files application docs tests
rg -n "CompanyProgram|ProgramStageState|ServiceDeliverable|AssetVersion|TaskRoutingRecord|whiteboard|kanban|deliverable_format" application tests docs
rg -n "strategy_report_builder|atlas_prompt_delivery|Legacy_Optical_Noir|_markdown_to_html|AssetVersion" application tests
```

## PR Roadmap / Slice Sequence

### PR 0: Review Gate And Characterization

Purpose: make the existing behavior explicit before changing it.

Files likely touched:

- `application/tests/services/test_strategy_report_builder.py`
- `application/tests/services/test_atlas_prompt_delivery.py`
- `application/tests/services/test_deliverable_format_renderers.py`
- `application/tests/services/test_deliverable_format_quality.py`

Tasks:

1. Read `docs/architecture/runtime-invariants.md` and record the invariant-sensitive decisions in test names and comments only where useful.
2. Add characterization tests for the current `strategy_report_builder.py` output:
   - current report is memo-like;
   - `_markdown_to_html` is basic;
   - PDF path uses hand-written text stream;
   - no derived artifact provenance is asserted yet.
3. Add characterization tests for `atlas_prompt_delivery.py`:
   - current path creates HTML, PDF, assets, manifest, ZIP;
   - current `Legacy_Optical_Noir_Handoff.html` behavior is prompt-specific;
   - department deliverables currently render as escaped text blocks.
4. Add tests around existing formatting services so the generic renderer work has a baseline.

Verification:

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python -m pytest application/tests/services/test_strategy_report_builder.py application/tests/services/test_atlas_prompt_delivery.py -q
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python -m pytest application/tests/services/test_deliverable_format_renderers.py application/tests/services/test_deliverable_format_quality.py -q
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run ruff check application/tests/services/test_strategy_report_builder.py application/tests/services/test_atlas_prompt_delivery.py application/tests/services/test_deliverable_format_renderers.py application/tests/services/test_deliverable_format_quality.py
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python manage.py check
```

### PR 1: Generic Handoff Package Contract

Purpose: define package shape without binding it to Atlas, Legacy Optical Noir, Hermes, or a specific agency prompt.

Files likely created:

- `application/services/client_handoff_package.py`
- `application/tests/services/test_client_handoff_package.py`

Files likely modified:

- `application/services/deliverable_format_profiles.py`
- `application/services/deliverable_formatting.py`

Contract to add:

- `ClientHandoffPackageSpec`
- `ClientHandoffArtifactSpec`
- `ClientHandoffSourceRef`
- `ClientHandoffManifest`
- `ClientHandoffProvenance`
- `ClientHandoffConnectorLimitations`

Required artifact categories:

- executive approval packet;
- strategy or research brief;
- brand content pack;
- channel calendar;
- CRM/WhatsApp scripts;
- measurement plan;
- QA report;
- client email body;
- manifest JSON;
- client-safe ZIP;
- optional campaign/hero assets.

Rules:

- Profile metadata may select labels, ordering, visual treatment, and artifact inclusion.
- Renderers must stay generic and business-agnostic.
- Atlas, Legacy, agency tone, and client-specific styling live in profile/config/metadata, not renderer branches.
- Connector limitations are represented separately from deliverable planning and never treated as proof of live delivery.

TDD tasks:

1. Write a failing test that builds a `ClientHandoffPackageSpec` from generic deliverable metadata and profile metadata.
2. Write a failing test that rejects profile logic trying to create durable state outside backend-owned models.
3. Implement only the dataclasses/value objects and profile resolution needed to pass those tests.

Verification:

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python -m pytest application/tests/services/test_client_handoff_package.py -q
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run ruff check application/services/client_handoff_package.py application/services/deliverable_format_profiles.py application/services/deliverable_formatting.py application/tests/services/test_client_handoff_package.py
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python manage.py check
```

### PR 2: Render Department Artifacts With Existing Formatting Infrastructure

Purpose: replace memo/escaped text output with polished rendered artifacts using the newer generic formatting stack.

Files likely created:

- `application/services/client_handoff_rendering.py`
- `application/tests/services/test_client_handoff_rendering.py`

Files likely modified:

- `application/services/deliverable_format_renderers.py`
- `application/services/deliverable_format_quality.py`
- `application/services/strategy_report_builder.py`
- `application/services/atlas_prompt_delivery.py`

Renderer behavior:

- Render each department deliverable as its own artifact.
- Convert canonical source content into structured HTML through `deliverable_formatting.py` and `deliverable_format_renderers.py`.
- Do not render department bodies as escaped text blocks.
- Keep Markdown as source content only when that is already canonical in `ServiceDeliverable` or `AssetVersion`; do not include Markdown in the client ZIP by default.
- Produce client-facing HTML and PDF outputs, with PNG hero/campaign assets when source assets or profile config request them.
- Keep `strategy_report_builder.py` as a compatibility entry point that delegates to the generic handoff renderer when a handoff profile is requested.
- Refactor `atlas_prompt_delivery.py` into a profile-backed compatibility shim or mark it as legacy while reusing generic rendering functions.

TDD tasks:

1. Write a failing test where a strategy brief, content pack, and measurement plan render as separate HTML artifacts.
2. Write a failing test that department HTML contains structured headings/sections and not escaped `<pre>`-style Markdown dumps.
3. Write a failing test that a default client ZIP plan excludes `.md` files.
4. Implement generic rendering glue using existing formatting modules.

Verification:

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python -m pytest application/tests/services/test_client_handoff_rendering.py application/tests/services/test_deliverable_format_renderers.py -q
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run ruff check application/services/client_handoff_rendering.py application/services/deliverable_format_renderers.py application/services/deliverable_format_quality.py application/services/strategy_report_builder.py application/services/atlas_prompt_delivery.py application/tests/services/test_client_handoff_rendering.py
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python manage.py check
```

### PR 3: Persist Derived Artifacts As AssetVersions With Provenance

Purpose: make rendered handoff artifacts durable, queryable, resumable, and auditable in ForgeGraph.

Files likely created:

- `application/services/client_handoff_artifacts.py`
- `application/tests/services/test_client_handoff_artifacts.py`

Files likely modified:

- `application/services/client_handoff_package.py`
- `application/services/client_handoff_rendering.py`
- Existing asset persistence service module, if present after preflight inspection.

Persistence rules:

- Use existing `Asset` and `AssetVersion` primitives before adding any model or migration.
- Each derived artifact gets a real `AssetVersion`.
- Temporary files may be used only during rendering/packaging and are not the source of truth.
- The manifest itself is a derived `AssetVersion`.
- The ZIP is a derived `AssetVersion`.
- Idempotent requests should either reuse matching derived outputs or create a new version with an explicit reason.

Required provenance fields:

- renderer name;
- renderer version;
- profile ref;
- profile hash;
- source `ServiceDeliverable` IDs;
- source `AssetVersion` IDs;
- source content hashes;
- request ID or idempotency key;
- quality gate result ID or embedded summary;
- output content hash;
- connector limitation summary;
- receipt references if live delivery happened elsewhere.

TDD tasks:

1. Write a failing test that a rendered HTML artifact is persisted as an `AssetVersion` with provenance.
2. Write a failing test that manifest and ZIP are persisted as derived `AssetVersion`s.
3. Write a failing test that re-running with the same idempotency key does not create duplicate durable package state unless source hashes changed.
4. Implement the persistence helper around existing asset/version APIs.

Verification:

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python -m pytest application/tests/services/test_client_handoff_artifacts.py -q
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run ruff check application/services/client_handoff_artifacts.py application/services/client_handoff_package.py application/services/client_handoff_rendering.py application/tests/services/test_client_handoff_artifacts.py
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python manage.py check
```

### PR 4: Whiteboard / Kanban-Compatible Backend State

Purpose: make handoff packaging visible and resumable from ForgeGraph whiteboard/kanban flows while preserving backend ownership.

Files likely created:

- `application/services/client_handoff_workflow.py`
- `application/tests/services/test_client_handoff_workflow.py`

Files likely modified:

- Existing whiteboard service modules, after preflight inspection.
- Existing task routing modules containing `TaskRoutingRecord`, after preflight inspection.
- `application/services/client_handoff_package.py`
- `application/services/client_handoff_artifacts.py`

Backend-native workflow mapping:

- `CompanyProgram`: parent durable scope for a client/campaign/program handoff.
- `ProgramStageState`: lane/status/checkpoint state for planning, rendering, quality review, approval, packaged, and delivered-with-receipt stages.
- `ServiceDeliverable`: canonical department work products.
- `Asset` / `AssetVersion`: source attachments and derived rendered artifacts.
- `TaskRoutingRecord`: worker dispatch and execution boundary, not durable package truth by itself.
- Existing whiteboard models: references, layout, and user-facing board placement only, not authoritative artifact state.

TDD tasks:

1. Write a failing test that a handoff package creates or updates backend-owned stage state for planned/rendering/quality-approved/packaged.
2. Write a failing test that worker dispatch state can be reconstructed from backend entities after an engine restart.
3. Write a failing test that whiteboard cards link to package artifacts and source deliverables without becoming the canonical source.
4. Implement workflow glue using existing models and services.

Verification:

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python -m pytest application/tests/services/test_client_handoff_workflow.py -q
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run ruff check application/services/client_handoff_workflow.py application/services/client_handoff_package.py application/services/client_handoff_artifacts.py application/tests/services/test_client_handoff_workflow.py
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python manage.py check
```

### PR 5: Quality Gates And Smoke Package Fixture

Purpose: enforce client-facing quality programmatically and prove the package flow with a real fixture.

Files likely created:

- `application/tests/fixtures/client_handoff/agency_handoff_smoke.json`
- `application/tests/services/test_client_handoff_smoke_package.py`

Files likely modified:

- `application/services/deliverable_format_quality.py`
- `application/services/client_handoff_rendering.py`
- `application/services/client_handoff_artifacts.py`
- `application/services/client_handoff_workflow.py`

Quality checks:

- expected artifact set exists for the selected profile;
- executive approval packet appears first in manifest/order;
- department deliverables are separate rendered artifacts;
- no Markdown files in client ZIP by default;
- no escaped HTML/Markdown dumps in rendered department pages;
- manifest contains artifact hashes, source refs, source hashes, provenance, profile hash, quality result, and connector limitations;
- ZIP includes only client-safe artifacts unless an internal/debug option is explicitly requested;
- live-send/delivery claims appear only when receipt `AssetVersion`s or connector receipt records exist;
- output hashes match persisted bytes.

TDD tasks:

1. Build the smoke fixture from realistic strategy/research/content/calendar/CRM/measurement/QA/email inputs.
2. Write a failing smoke test that produces the full package and opens the ZIP manifest.
3. Write failing quality tests for missing provenance, leaked Markdown, escaped department blocks, and false delivery claims.
4. Implement gates in `deliverable_format_quality.py` and package orchestration.

Verification:

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python -m pytest application/tests/services/test_client_handoff_smoke_package.py -q
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python -m pytest application/tests/services/test_client_handoff_package.py application/tests/services/test_client_handoff_rendering.py application/tests/services/test_client_handoff_artifacts.py application/tests/services/test_client_handoff_workflow.py application/tests/services/test_client_handoff_smoke_package.py -q
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run ruff check application/services/client_handoff_package.py application/services/client_handoff_rendering.py application/services/client_handoff_artifacts.py application/services/client_handoff_workflow.py application/services/deliverable_format_quality.py application/tests/services/test_client_handoff_smoke_package.py
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python manage.py check
```

### PR 6: Replace Prompt-Specific Atlas Path With Profile Configuration

Purpose: keep the polished Atlas/Legacy look available without hardcoding it into runtime behavior.

Files likely modified:

- `application/services/atlas_prompt_delivery.py`
- `application/services/strategy_report_builder.py`
- `application/services/deliverable_format_profiles.py`
- `application/services/deliverable_format_renderers.py`
- Existing docs describing strategy report or Atlas delivery, after preflight inspection.

Tasks:

1. Move Atlas/Legacy/agency labels, ordering, typography hints, and artifact selection into profile metadata.
2. Keep `atlas_prompt_delivery.py` as a thin compatibility adapter if callers still import it.
3. Make `strategy_report_builder.py` delegate to the generic handoff package builder for client handoff requests.
4. Document the generic profile extension points and the invariant that renderers do not own durable state.

Verification:

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python -m pytest application/tests/services/test_strategy_report_builder.py application/tests/services/test_atlas_prompt_delivery.py application/tests/services/test_client_handoff_smoke_package.py -q
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run ruff check application/services/atlas_prompt_delivery.py application/services/strategy_report_builder.py application/services/deliverable_format_profiles.py application/services/deliverable_format_renderers.py
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python manage.py check
```

## Hermes Kanban Ideas To Borrow

| Hermes idea | ForgeGraph-native implementation choice |
| --- | --- |
| Durable board/task state | Use backend-owned `CompanyProgram` and `ProgramStageState`; do not let an engine, worker, client, or event stream own durable package state. |
| Task links | Link `ServiceDeliverable`, source `AssetVersion`s, derived `AssetVersion`s, and manifest entries by backend IDs and hashes. |
| Comments, tail, activity | Represent as backend-owned status/activity records if such models already exist; otherwise derive display activity from `ProgramStageState`, `TaskRoutingRecord`, and persisted artifact provenance. |
| Worker dispatch boundaries | Use `TaskRoutingRecord` for dispatch/execution metadata only. The package can be resumed from backend state even if workers restart. |
| Attachments and artifacts | Use `Asset` and `AssetVersion` for source attachments and derived HTML/PDF/PNG/JSON/ZIP outputs. |
| Task status transitions | Map to explicit package stages: planned, rendering, rendered, quality_failed, quality_approved, packaged, delivered_with_receipt. |
| Profile/lane specialization | Use `deliverable_format_profiles.py` metadata and `ProgramStageState` stage/lane names; do not fork renderers by client or prompt. |
| Final completion receipts | Persist manifest and any real delivery receipts as `AssetVersion`s or existing receipt records. Without receipts, only claim "package generated", not "sent" or "published". |

## What Not To Do

- Do not hardcode Legacy Optical Noir, Atlas, or agency-specific decisions into renderers, models, or workflow state.
- Do not include Markdown in client ZIPs by default. Markdown may remain canonical source content in `ServiceDeliverable` or `AssetVersion`.
- Do not add a Hermes runtime dependency, import Hermes modules, shell out to Hermes, or require Hermes data stores.
- Do not make engines, clients, events, snapshots, or transport streams authoritative for durable handoff package state.
- Do not treat events as authoritative state; use them only for transport and observability.
- Do not store generated HTML/PDF/ZIP files as loose files only. Persist every client-facing derived artifact as an `AssetVersion`.
- Do not claim live publishing, email delivery, WhatsApp delivery, CRM sync, or ad/channel publication unless a real connector receipt exists and is linked in provenance.
- Do not mix connector limitations into deliverable planning. Surface limitations as explicit metadata and quality context.
- Do not add migrations until preflight proves existing primitives cannot represent the state safely.

## Acceptance Criteria

- A smoke fixture can generate a complete client handoff package from backend-owned source deliverables and source asset versions.
- The package contains an executive/client approval packet first, then separate department artifacts: strategy/research brief, brand content pack, channel calendar, CRM/WhatsApp scripts, measurement plan, QA report, email body, manifest, ZIP, and optional campaign/hero assets.
- Rendered department artifacts are polished HTML/PDF-style outputs, not escaped text blocks or Markdown dumps.
- Client ZIP contains HTML/PDF/PNG/JSON manifest artifacts by default and no `.md` files unless explicitly requested.
- Every generated client-facing artifact, including manifest and ZIP, is persisted as a real `AssetVersion`.
- Provenance includes renderer name/version, profile ref/hash, source deliverable IDs, source asset version IDs/hashes, request or idempotency key, quality gate result, connector limitations, and output hash.
- Re-running the same package request with unchanged sources and idempotency metadata is deterministic and does not create duplicate durable state.
- Quality gates fail on missing provenance, missing expected artifacts, Markdown leakage in default ZIPs, escaped department blocks, hash mismatch, or false live-send claims.
- Whiteboard/kanban views can reference package state and artifacts through backend-owned IDs without becoming the durable source of truth.
- `strategy_report_builder.py` and `atlas_prompt_delivery.py` no longer own prompt-specific client package behavior; they delegate to generic package/profile services or remain thin compatibility shims.

## Full Verification Set

Run from the backend repo in Windows Git Bash:

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python -m pytest application/tests/services/test_client_handoff_package.py -q
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python -m pytest application/tests/services/test_client_handoff_rendering.py -q
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python -m pytest application/tests/services/test_client_handoff_artifacts.py -q
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python -m pytest application/tests/services/test_client_handoff_workflow.py -q
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python -m pytest application/tests/services/test_client_handoff_smoke_package.py -q
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python -m pytest application/tests/services/test_strategy_report_builder.py application/tests/services/test_atlas_prompt_delivery.py application/tests/services/test_deliverable_format_renderers.py application/tests/services/test_deliverable_format_quality.py -q
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run ruff check application/services/client_handoff_package.py application/services/client_handoff_rendering.py application/services/client_handoff_artifacts.py application/services/client_handoff_workflow.py application/services/strategy_report_builder.py application/services/atlas_prompt_delivery.py application/services/deliverable_formatting.py application/services/deliverable_format_renderers.py application/services/deliverable_format_profiles.py application/services/deliverable_format_quality.py application/tests/services/test_client_handoff_package.py application/tests/services/test_client_handoff_rendering.py application/tests/services/test_client_handoff_artifacts.py application/tests/services/test_client_handoff_workflow.py application/tests/services/test_client_handoff_smoke_package.py
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python manage.py check
```
