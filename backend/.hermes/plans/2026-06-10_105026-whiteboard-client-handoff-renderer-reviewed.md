# Whiteboard Client Handoff Renderer Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Build a ForgeGraph-native client handoff renderer that turns whiteboard/kanban-backed department deliverables into polished agency-grade packages: executive approval packet first, separate department artifacts second, manifest/provenance/receipts explicit, client ZIP clean by default.

**Architecture:** The backend control plane remains the only source of truth for durable state. `ServiceDeliverable` and source `AssetVersion`s hold canonical work product; rendered HTML/PDF/email/PNG/JSON/ZIP files are derived `AssetVersion`s with renderer/profile/source/quality provenance. Whiteboard/kanban cards, workers, and events reference backend-owned artifacts and stage state; they never become authoritative package state.

**Tech Stack:** Django backend, existing ForgeGraph services/models, `config/format_profiles/*.json`, `application/services/deliverable_format*`, `application/services/work_whiteboards.py`, `application/services/whiteboard_boards.py`, `Asset`/`AssetVersion`, `ServiceDeliverable`, `CompanyProgram`, `ProgramStageState`, `TaskRoutingRecord`, pytest, ruff, `uv`, Windows/Git Bash.

---

## Parent Review Notes / Corrections To Codex Draft

Codex did create a plan, but it could not inspect the repo because its Windows sandbox failed with `windows sandbox: spawn setup refresh`. I reviewed the plan manually and corrected the implementation target against the real repository:

- Runtime invariant doc is at `../docs/architecture/runtime-invariants.md` from `backend/`, not `backend/docs/architecture/runtime-invariants.md`.
- Tests live under `tests/unit/services/`, not `application/tests/services/`.
- Existing formatting profiles already exist under `config/format_profiles/`:
  - `config/format_profiles/default.v1.json`
  - `config/format_profiles/consulting.standard_handoff.v1.json`
  - `config/format_profiles/legacy.client_handoff.v1.json`
- Existing supported formats are currently only `markdown_report`, `pdf_report`, `manifest`, and `zip_package` in `application/services/deliverable_format_profiles.py`.
- Existing rendering service already persists derived artifacts in `format_service_deliverables`; the next work should extend/refactor it, not replace it.
- Existing whiteboard/kanban backend state already exists in `application/services/work_whiteboards.py` and `application/services/whiteboard_boards.py`, backed by `WorkWhiteboard` + `TaskRoutingRecord`.
- The first implementation slice should avoid migrations unless a proof shows current `AssetVersion`/`ProgramStageState` metadata cannot represent package state.

## Product Diagnosis This Fix Addresses

The content quality problem is mostly solved. The remaining gap is package/product expression:

- `application/services/strategy_report_builder.py` produces aligned content but renders it like a plain memo.
- `application/services/deliverable_format_renderers.py` currently aggregates sections into Markdown/PDF/manifest/ZIP, but not a polished executive handoff shell with per-department rendered pages.
- `application/services/atlas_prompt_delivery.py` is closer to the professional package shape, but it is prompt-specific and still risks rendering deliverable bodies as escaped text blocks.
- The whiteboard/kanban should become the client handoff production board: department cards produce deliverables, deliverables become structured artifacts, artifacts become an approval-first package.

The target output shape should match the better handoff package pattern:

```text
Executive / Client Approval Packet
Strategy or Research Brief
Brand Content Pack
Channel Execution Calendar
CRM / WhatsApp Scripts
Measurement Plan
Launch QA Report
Client Email Body
Manifest / Provenance
Client-safe ZIP
Optional campaign/hero/preview assets
```

## Runtime Invariants

Before any implementation, re-read:

- `../docs/architecture/runtime-invariants.md`

Key invariant to preserve:

- backend control plane is the only durable source of truth;
- events are transport/observability, not authoritative state;
- workers/engines execute work and may hold ephemeral state only;
- backend-owned entities must be enough to reconstruct package state after worker restart.

## Hermes Kanban Ideas To Borrow

Borrow these concepts from `https://github.com/NousResearch/hermes-agent` conceptually only. Do not import, shell out to, or depend on Hermes at runtime.

| Hermes kanban idea | ForgeGraph-native implementation choice |
|---|---|
| Durable board/task state | Continue using backend-owned `WorkWhiteboard`, `TaskRoutingRecord`, `CompanyProgram`, and `ProgramStageState`. |
| Lanes / statuses | Map handoff package lifecycle to explicit backend statuses: `planned`, `rendering`, `rendered`, `quality_failed`, `quality_approved`, `packaged`, `delivered_with_receipt`. |
| Worker lanes / specialization | Use existing department/routing concepts and profile metadata; no renderer branch should hardcode Atlas/Legacy. |
| Attachments/artifacts | Use `Asset` + `AssetVersion` for source attachments and derived HTML/PDF/PNG/JSON/ZIP outputs. |
| Task links | Link whiteboard cards to `ServiceDeliverable` IDs, source `AssetVersion` IDs, derived `AssetVersion` IDs, manifest entries, and hashes. |
| Activity/comments/tail | Derive display activity from `TaskRoutingRecord`, `ProgramStageState`, quality results, and artifact provenance; add no new event authority. |
| Completion receipt | Persist package manifest and real connector receipts as backend-owned records/artifacts; without receipts, say only “generated” or “ready for approval.” |

## Layer Split

### Shared platform / backend primitives

- Generic package contract and artifact spec.
- Generic structured HTML renderer.
- Generic package manifest/provenance schema.
- Generic ZIP policy for client-safe vs internal/debug artifacts.
- Generic quality gates.
- Backend persistence of every derived artifact as `AssetVersion`.
- Whiteboard/kanban package status projection from existing backend state.

### Product/profile layer

- Atlas/Legacy names, tone, ordering, labels, palette, typography hints, hero/campaign asset references.
- Which department artifact categories are expected for a specific business/service pack.
- Client-safe wording, approval copy, and connector caveats.
- Optional demo fixture content.

## PR Roadmap

| Order | Branch / PR | Objective | Boundary | Dependencies | Success criteria |
|---:|---|---|---|---|---|
| 0 | `merge/current-pr` | Let Mike finish reviewing the current PR | No new implementation | Current PR review | Current PR merged or explicitly paused; clean branch/worktree for new work |
| 1 | `feat/handoff-format-contract` | Add the generic package contract + profile support | Backend service/test only | PR 0 | Tests prove package spec from real `ServiceDeliverable` metadata and profile config |
| 2 | `feat/handoff-html-renderer` | Add professional HTML/email rendering and client-safe ZIP policy | Renderer/profile/quality only | PR 1 | Smoke output has executive shell + separate department pages; no Markdown in client ZIP by default |
| 3 | `feat/handoff-artifact-persistence` | Persist rendered artifacts and manifests as `AssetVersion`s with provenance/idempotency | Persistence only | PR 2 | Every output has asset/version/provenance; rerun is deterministic/idempotent |
| 4 | `feat/handoff-whiteboard-kanban-state` | Project package status/artifacts onto whiteboard/kanban cards | Backend workflow/projection only | PR 3 | Board can reference package state/artifacts from backend IDs and recover after restart |
| 5 | `feat/handoff-smoke-quality-gates` | Add realistic fixture/smoke package + blocking quality gates | Tests/quality/smoke command | PR 4 | Real fixture package passes programmatic checks and visual/manual inspection path |
| 6 | `refactor/atlas-prompt-delivery-adapter` | Make strategy/Atlas paths thin adapters over generic renderer | Compatibility/adapters only | PR 5 | `strategy_report_builder.py` and `atlas_prompt_delivery.py` no longer own prompt-specific package behavior |

## PR 1: Generic Handoff Package Contract

**Objective:** Define a package spec that can be built from existing backend deliverables without hardcoding Atlas/Legacy.

**Files:**

- Create: `application/services/client_handoff_package.py`
- Test: `tests/unit/services/test_client_handoff_package.py`
- Modify: `application/services/deliverable_format_profiles.py`
- Modify: `config/format_profiles/legacy.client_handoff.v1.json`
- Possibly modify: `config/format_profiles/consulting.standard_handoff.v1.json`

**Implementation notes:**

- Add dataclasses/value objects such as:
  - `ClientHandoffPackageSpec`
  - `ClientHandoffArtifactSpec`
  - `ClientHandoffSourceRef`
  - `ClientHandoffManifestSpec`
  - `ClientHandoffConnectorLimitations`
- The spec builder should accept existing `FormatSource`s or `ServiceDeliverable`s and a `FormatProfile`.
- Extend profile layout/metadata to describe artifact categories and ordering. Keep the renderer generic.
- Do not add a migration in this PR.

**TDD tasks:**

1. Write a failing test that builds a package spec from three generic `ServiceDeliverable`s with roles like `strategy_brief`, `brand_content_pack`, and `measurement_plan`.
2. Assert the first artifact category is `executive_approval_packet` when the profile requests it.
3. Assert Atlas/Legacy strings only appear when they came from profile metadata, not generic renderer constants.
4. Implement the minimal spec builder and profile parsing needed to pass.

**Verification:**

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python -m pytest tests/unit/services/test_client_handoff_package.py tests/unit/services/test_deliverable_format_profiles.py -q
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run ruff check application/services/client_handoff_package.py application/services/deliverable_format_profiles.py tests/unit/services/test_client_handoff_package.py tests/unit/services/test_deliverable_format_profiles.py
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python manage.py check
```

## PR 2: Professional HTML / Email Renderer + Client ZIP Policy

**Objective:** Render executive handoff and department deliverables as structured professional pages, not escaped text blocks or memo Markdown.

**Files:**

- Create: `application/services/client_handoff_rendering.py`
- Test: `tests/unit/services/test_client_handoff_rendering.py`
- Modify: `application/services/deliverable_format_renderers.py`
- Modify: `application/services/deliverable_format_profiles.py`
- Modify: `application/services/deliverable_format_quality.py`
- Modify: `config/format_profiles/legacy.client_handoff.v1.json`

**Implementation notes:**

- Add supported format IDs such as `client_html` and `email_handoff` to `SUPPORTED_FORMATS`.
- Keep `markdown_report` available as an internal/source/debug format, but exclude `.md` from client ZIP by default.
- Render a single executive page with:
  - hero/cover section;
  - decision requested;
  - readiness/approval cards;
  - department artifact index;
  - source/provenance summary link to manifest;
  - connector limitation callout.
- Render each department artifact as its own HTML file under `deliverables/`.
- If a source body is Markdown, convert it into headings, paragraphs, lists, and tables. Do not place whole body content inside escaped `<pre>` blocks or `<br>` dumps.
- CSS/theming should be profile-driven via layout tokens; no Legacy-specific branching in the renderer.

**TDD tasks:**

1. Write a failing test that `client_html` output has `<!doctype html>`, exactly one top-level executive `<h1>`, a deliverable index, and several cards/sections.
2. Write a failing test that separate department HTML pages exist for strategy, content, calendar, CRM, measurement, and QA roles when source deliverables are present.
3. Write a failing test that raw Markdown headings like `# Strategy Brief` are not visible as literal text in client HTML.
4. Write a failing test that escaped `<pre>`/`&lt;h1`/`&lt;table` dumps fail quality.
5. Implement renderer functions and quality gates.

**Verification:**

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python -m pytest tests/unit/services/test_client_handoff_rendering.py tests/unit/services/test_deliverable_format_renderers.py tests/unit/services/test_deliverable_format_quality.py -q
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run ruff check application/services/client_handoff_rendering.py application/services/deliverable_format_renderers.py application/services/deliverable_format_profiles.py application/services/deliverable_format_quality.py tests/unit/services/test_client_handoff_rendering.py
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python manage.py check
```

## PR 3: Persist Derived Artifacts As AssetVersions

**Objective:** Ensure every client-facing output is persisted, traceable, and idempotent.

**Files:**

- Create: `application/services/client_handoff_artifacts.py`
- Test: `tests/unit/services/test_client_handoff_artifacts.py`
- Modify: `application/services/deliverable_formatting.py`
- Modify: `application/services/client_handoff_package.py`
- Modify: `application/services/client_handoff_rendering.py`

**Implementation notes:**

- Reuse the existing persistence pattern in `format_service_deliverables()` and `_persist_artifact()`.
- Persist each rendered artifact as a derived `AssetVersion`:
  - executive HTML;
  - department HTML files;
  - PDF;
  - email body text/html;
  - manifest;
  - ZIP;
  - optional preview/hero assets if generated by ForgeGraph.
- Provenance must include:
  - renderer name/version;
  - profile ref/hash;
  - package request/idempotency key;
  - source `ServiceDeliverable` IDs;
  - source `AssetVersion` IDs;
  - source hashes;
  - output hash;
  - quality result;
  - connector limitations;
  - receipt references if delivery happened.

**TDD tasks:**

1. Write a failing test that executive HTML, manifest, and ZIP each get `asset_version_id` values.
2. Write a failing test that provenance has all required fields above.
3. Write a failing test that rerunning with the same idempotency key and unchanged source hashes does not duplicate package state.
4. Implement the persistence/idempotency helper.

**Verification:**

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python -m pytest tests/unit/services/test_client_handoff_artifacts.py tests/unit/services/test_deliverable_formatting.py -q
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run ruff check application/services/client_handoff_artifacts.py application/services/deliverable_formatting.py application/services/client_handoff_package.py application/services/client_handoff_rendering.py tests/unit/services/test_client_handoff_artifacts.py
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python manage.py check
```

## PR 4: Whiteboard / Kanban Package State Projection

**Objective:** Make handoff packaging visible and recoverable from the ForgeGraph whiteboard/kanban without making the board authoritative.

**Files:**

- Create: `application/services/client_handoff_workflow.py`
- Test: `tests/unit/services/test_client_handoff_workflow.py`
- Modify: `application/services/work_whiteboards.py`
- Modify: `application/services/whiteboard_boards.py`
- Possibly modify: `tests/unit/services/test_whiteboard_board.py`
- Possibly modify: `tests/unit/services/test_whiteboard_board_kafka.py`

**Implementation notes:**

- Use existing backend entities:
  - `WorkWhiteboard` for engagement/project board context;
  - `TaskRoutingRecord` for cards/worker dispatch and artifact links;
  - `CompanyProgram` and `ProgramStageState` for durable handoff lifecycle state;
  - `ServiceDeliverable` for department work products;
  - `AssetVersion` for source/derived artifacts.
- Add package-specific metadata/projection payloads, not new durable authority in events or Redis.
- Update board card payloads only to expose safe artifact links and package status derived from DB.

**TDD tasks:**

1. Write a failing test that a handoff workflow updates stage state to `planned`, `rendering`, `quality_approved`, and `packaged` using backend-owned records.
2. Write a failing test that `build_whiteboard_board_snapshot()` can expose package artifact links from DB state.
3. Write a failing test that Redis/event snapshots are reconstructable from DB after cache loss.
4. Implement workflow projection and board payload additions.

**Verification:**

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python -m pytest tests/unit/services/test_client_handoff_workflow.py tests/unit/services/test_whiteboard_board.py tests/unit/services/test_whiteboard_board_kafka.py -q
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run ruff check application/services/client_handoff_workflow.py application/services/work_whiteboards.py application/services/whiteboard_boards.py tests/unit/services/test_client_handoff_workflow.py
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python manage.py check
```

## PR 5: Smoke Fixture + Blocking Quality Gates

**Objective:** Prove ForgeGraph can generate the professional package shape and fail closed when output is not client-safe.

**Files:**

- Create: `tests/fixtures/client_handoff/agency_handoff_smoke.json`
- Create: `tests/unit/services/test_client_handoff_smoke_package.py`
- Modify: `application/services/deliverable_format_quality.py`
- Modify: `application/services/client_handoff_rendering.py`
- Modify: `application/services/client_handoff_artifacts.py`
- Possibly create: `infrastructure/orm/management/commands/run_client_handoff_package.py`

**Quality gates:**

- Expected artifact set exists for selected profile.
- Executive approval packet is first in manifest/order.
- Department deliverables render as separate client-facing artifacts.
- Client ZIP contains no `.md` files by default.
- Client HTML has polished structure: doctype, hero/cover, cards/sections, artifact index, approval callout.
- No raw internal tokens in client-facing HTML/PDF/email: `GraphVersion`, `NodeRun`, `TaskRoutingRecord`, `Internal lineage`, `codex_media_spec`, `placeholder`, etc.
- No escaped Markdown/HTML dumps.
- Manifest includes hashes, source refs, profile hash, quality result, connector limitations, and output list.
- Output hashes match persisted bytes.
- Delivery/publishing/sending claims require real receipt references.

**TDD tasks:**

1. Build a realistic generic agency fixture with strategy, content, calendar, CRM, measurement, QA, and email body sources.
2. Write a failing smoke test that renders the whole package and opens the ZIP.
3. Write failing tests for each quality gate above.
4. Implement gates and optional management command.

**Verification:**

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python -m pytest tests/unit/services/test_client_handoff_smoke_package.py -q
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python -m pytest tests/unit/services/test_client_handoff_package.py tests/unit/services/test_client_handoff_rendering.py tests/unit/services/test_client_handoff_artifacts.py tests/unit/services/test_client_handoff_workflow.py tests/unit/services/test_client_handoff_smoke_package.py -q
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run ruff check application/services/client_handoff_package.py application/services/client_handoff_rendering.py application/services/client_handoff_artifacts.py application/services/client_handoff_workflow.py application/services/deliverable_format_quality.py tests/unit/services/test_client_handoff_smoke_package.py
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python manage.py check
```

If a command is added:

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python manage.py run_client_handoff_package --fixture tests/fixtures/client_handoff/agency_handoff_smoke.json --no-send
```

## PR 6: Strategy / Atlas Compatibility Adapters

**Objective:** Keep existing entrypoints working while delegating actual client package rendering to the generic handoff renderer.

**Files:**

- Modify: `application/services/strategy_report_builder.py`
- Modify: `application/services/atlas_prompt_delivery.py`
- Modify: `infrastructure/orm/management/commands/run_atlas_prompt_delivery.py`
- Test: `tests/unit/services/test_strategy_report_builder.py`
- Test: `tests/unit/services/test_atlas_prompt_delivery_quality.py`

**Implementation notes:**

- `strategy_report_builder.py` can keep producing Markdown report artifacts where needed, but client handoff requests should route through the generic client handoff renderer.
- `atlas_prompt_delivery.py` should become a compatibility adapter that supplies a profile/ref/source bundle and calls the generic renderer.
- Keep `--no-send` dry-run behavior.
- Do not send WhatsApp/email unless package quality passes and real connector receipt handling is enabled.

**TDD tasks:**

1. Write a failing test that strategy report client handoff path returns `client_html`/PDF/manifest/ZIP derived artifacts.
2. Write a failing test that Atlas prompt delivery no longer emits raw internal Markdown content into visible client HTML/PDF.
3. Write a failing test that placeholder media or missing receipts downgrades status to review/draft, not client-ready/live-sent.
4. Refactor entrypoints to delegate.

**Verification:**

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python -m pytest tests/unit/services/test_strategy_report_builder.py tests/unit/services/test_atlas_prompt_delivery_quality.py -q
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run ruff check application/services/strategy_report_builder.py application/services/atlas_prompt_delivery.py infrastructure/orm/management/commands/run_atlas_prompt_delivery.py tests/unit/services/test_strategy_report_builder.py tests/unit/services/test_atlas_prompt_delivery_quality.py
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python manage.py check
```

## What Not To Do

- Do not hardcode Legacy Optical Noir, Atlas, agency-specific copy, or client-specific palette inside generic renderer modules.
- Do not put Markdown files in client ZIPs by default.
- Do not remove canonical Markdown/source content from `ServiceDeliverable` or `AssetVersion`; just keep it internal/source-side.
- Do not add a Hermes runtime dependency, import Hermes modules, shell out to Hermes, or use Hermes stores.
- Do not make Redis/Kafka/events/whiteboard snapshots authoritative for package state.
- Do not store generated client artifacts only as loose files.
- Do not claim publishing/email/WhatsApp delivery without real receipt records/artifacts.
- Do not mix connector limitations into deliverable planning; keep them explicit in quality/provenance/client caveats.
- Do not add DB migrations until existing primitives are proven insufficient.

## Acceptance Criteria

- ForgeGraph can generate a complete client handoff package from backend-owned deliverables and assets.
- Package contains executive approval packet first, then separate department artifacts, email body, manifest, PDF, ZIP, and optional hero/preview assets.
- Client ZIP defaults to HTML/PDF/PNG/JSON/email-safe files and excludes `.md` files.
- Rendered client artifacts look like structured professional handoff pages, not plain memos or escaped Markdown dumps.
- Every generated client-facing artifact is persisted as an `AssetVersion` with full provenance.
- Provenance includes renderer name/version, profile ref/hash, source IDs/hashes, idempotency key, quality result, connector limitations, output hash, and receipt refs if any.
- Whiteboard/kanban state can reference generated packages and artifact links using backend-owned IDs.
- Package state can be reconstructed from DB after cache/worker restart.
- Quality gates fail on missing artifacts, Markdown leakage, internal token leakage, escaped content dumps, hash mismatch, missing provenance, placeholder-only media marked client-ready, or false delivery claims.
- Existing `format_service_deliverables`, `strategy_report_builder`, and `atlas_prompt_delivery` tests continue to pass after adapter refactors.

## Full Verification Set

Run from `C:/Users/mathi/projects/forgegraph/backend` in Git Bash:

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python -m pytest tests/unit/services/test_client_handoff_package.py -q
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python -m pytest tests/unit/services/test_client_handoff_rendering.py -q
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python -m pytest tests/unit/services/test_client_handoff_artifacts.py -q
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python -m pytest tests/unit/services/test_client_handoff_workflow.py -q
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python -m pytest tests/unit/services/test_client_handoff_smoke_package.py -q
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python -m pytest tests/unit/services/test_deliverable_formatting.py tests/unit/services/test_deliverable_format_renderers.py tests/unit/services/test_deliverable_format_profiles.py tests/unit/services/test_deliverable_format_quality.py -q
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python -m pytest tests/unit/services/test_strategy_report_builder.py tests/unit/services/test_atlas_prompt_delivery_quality.py tests/unit/services/test_whiteboard_board.py tests/unit/services/test_whiteboard_board_kafka.py -q
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run ruff check application/services/client_handoff_package.py application/services/client_handoff_rendering.py application/services/client_handoff_artifacts.py application/services/client_handoff_workflow.py application/services/deliverable_formatting.py application/services/deliverable_format_renderers.py application/services/deliverable_format_profiles.py application/services/deliverable_format_quality.py application/services/strategy_report_builder.py application/services/atlas_prompt_delivery.py application/services/work_whiteboards.py application/services/whiteboard_boards.py tests/unit/services/test_client_handoff_package.py tests/unit/services/test_client_handoff_rendering.py tests/unit/services/test_client_handoff_artifacts.py tests/unit/services/test_client_handoff_workflow.py tests/unit/services/test_client_handoff_smoke_package.py
UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline uv run python manage.py check
```

## Implementation Handoff

After Mike approves the plan, implement PR 1 first. Keep implementation TDD and narrow. After each Codex implementation run, parent agent must inspect `git status`, inspect diffs for strategy drift, run focused tests/ruff/`manage.py check`, and only then report progress.
