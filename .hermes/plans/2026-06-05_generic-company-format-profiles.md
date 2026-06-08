# Generic Company Format Profiles Plan

Date: 2026-06-05

Status: plan only. Do not implement from this document until the likely file paths are confirmed with `rg --files` / symbol search.

Repository note: this plan follows `docs/architecture/runtime-invariants.md` as the controlling architecture source. The backend remains the only durable source of truth. Rendered artifacts, PDFs, emails, zips, events, and engine activity are derived outputs or transport artifacts, not authoritative state.

## Verdict

Yes, the proposed architecture is the easiest and safest path, with a few corrections.

The safe path is to keep canonical deliverable content in backend-owned `ServiceDeliverable` records and canonical bytes/derived artifacts in backend-owned `Asset` / `AssetVersion` records. Generic format renderers should produce derived `AssetVersion`s with provenance. Company-specific profiles should start as versioned metadata/config selected by existing company, engagement, program, or pack metadata. This avoids making ForgeGraph Atlas-specific and avoids inventing durable models before query patterns prove they are needed.

Corrections:

- Treat PDFs, handoff emails, zip packages, and manifests as derived artifacts. They must never become the canonical durable representation of a deliverable.
- Renderers may execute in the engine or worker layer, but all durable render state, package readiness, delivery state, snapshots, liveness, and resume metadata must be backend-owned.
- Profiles should be repo/config-owned for slice 1. Runtime requests may reference a profile, but must not supply arbitrary untrusted profile definitions unless the backend validates and snapshots them.
- Quality gates should be backend-orchestrated and persisted as validation results/provenance. Events can announce that gates ran, but events cannot be the source of truth.
- Email handoff should support draft/outbox rendering first. Real delivery may be recorded only when an actual provider accepts the send and returns provider evidence such as a message id.

## Roadmap

### PR 1: Format Profile Schema And Registry

Boundary: no PDF rendering, no email sending, no zip packaging, no UI dependency.

Create a small generic formatting module with typed profile/request/result/provenance shapes and a registry that resolves versioned profiles from config plus existing metadata references.

Expected outputs:

- Default generic profile.
- Legacy profile fixture for Atlas marketing handoff behavior.
- Consulting/non-marketing profile fixture proving the same machinery is business-agnostic.
- Unit tests for profile resolution, inheritance/overrides, and invalid profile rejection.

### PR 2: Quality Gates

Boundary: validation only. No package creation.

Add reusable quality checks that run against rendered text/section models before packaging.

Checks:

- No placeholders or unresolved template tokens.
- No AI/meta language.
- Required sections present.
- Client, company, and engagement naming consistent.
- Evidence/facts separated from recommendations.
- Connector caveats and approval language present when profile or source metadata requires them.

Expected outputs:

- `QualityGateResult` persisted in artifact metadata or linked validation metadata.
- Blocking and warning severities.
- Marketing and consulting tests with both passing and failing fixtures.

### PR 3: Markdown Report, Manifest, And Zip Package

Boundary: text/manifest/package artifacts only. No PDF, no production email.

Implement generic renderers:

- `markdown_report`
- `manifest`
- `zip_package`
- optionally `approval_packet` if it can be represented as markdown + manifest in this slice

Persist each derived artifact as an `AssetVersion` with render provenance. The package manifest must include source deliverable ids, source asset version ids, content hashes, profile id/version/hash, renderer versions, quality gate result ids, and package file hashes.

Expected outputs:

- Legacy handoff package is higher quality and client-ready as markdown + manifest + zip.
- Consulting handoff package uses the same renderers with different sections/voice.
- No UI acceptance requirement.

### PR 4: PDF Renderer Adapter

Boundary: generated PDF artifact only. No email delivery.

Add a generic `pdf_report` renderer through an adapter. Prefer an existing repo PDF/HTML rendering dependency if present. If none exists, introduce a narrow adapter around a production-capable renderer such as Playwright/Chromium or WeasyPrint, chosen after dependency review.

Expected outputs:

- PDF bytes stored as `AssetVersion`.
- PDF render errors are explicit failures, not silent fallbacks.
- PDF provenance records renderer name/version, source hashes, profile hash, and output hash.
- Tests assert a non-empty PDF, expected metadata, and manifest references. Do not make pixel-perfect UI rendering acceptance-critical.

### PR 5: Email Handoff Drafts And Real Provider Boundary

Boundary: email draft/outbox first; real send only behind provider configuration and explicit send command.

Implement `email_handoff` as a renderer that creates a durable draft artifact containing subject, body, attachments, manifest references, and policy warnings. Do not mark anything as sent unless a real provider accepts the message.

Expected outputs:

- Dry-run email draft artifact for Legacy and consulting fixtures.
- Optional provider adapter can produce `accepted`, `rejected`, or `not_configured`.
- Delivery metadata stores provider message id only after acceptance.
- No secrets printed or persisted.

## Exact Likely Files To Create Or Modify

Confirm exact paths before implementation. If the repository uses a different package prefix, locate by symbol names: `ServiceDeliverable`, `Asset`, `AssetVersion`, `CompanyProgram`, `ProgramStageState`, `TaskRoutingRecord`, and `ServiceEngagement`.

Plan artifact already created:

- `.hermes/plans/2026-06-05_generic-company-format-profiles.md`

Likely new docs:

- `docs/architecture/generic-format-profiles.md`
- `docs/architecture/handoff-packaging.md` if an existing handoff doc already exists, update that instead

Corrected for the current ForgeGraph backend layout after read-only path inspection:

Likely new backend formatting module:

- `backend/application/services/deliverable_formatting.py` — orchestration facade for profile resolution, quality gates, renderer dispatch, and persistence.
- `backend/application/services/deliverable_format_profiles.py` — typed profile/request/result/provenance shapes and profile registry.
- `backend/application/services/deliverable_format_quality.py` — deterministic production-quality checks.
- `backend/application/services/deliverable_format_renderers.py` — markdown report, manifest, zip package, email draft, and later PDF renderer adapters. Split into a package only if this file grows too large.

Likely config/profile files:

- `backend/config/format_profiles/default.v1.json`
- `backend/config/format_profiles/legacy.client_handoff.v1.json`
- `backend/config/format_profiles/consulting.standard_handoff.v1.json`

Likely existing model/service integration points:

- `backend/application/services/legacy_weekend_pipeline.py`
- `backend/application/services/company_run_task_routing.py`
- `backend/application/services/department_pipeline.py`
- `backend/application/services/agency_deliverables.py`
- `backend/application/services/agency_deliverable_quality.py`
- `backend/application/services/email_connectors.py`
- `backend/application/services/service_engagements.py`
- `backend/application/services/company_programs.py`
- `backend/infrastructure/orm/models/decisions_assets.py` (`Asset`, `AssetVersion`)
- `backend/infrastructure/orm/models/service_deliverables.py` or the existing model file containing `ServiceDeliverable`.
- `backend/infrastructure/orm/models/routing.py` (`TaskRoutingRecord`)

Likely tests and fixtures:

- `backend/tests/unit/services/test_deliverable_format_profiles.py`
- `backend/tests/unit/services/test_deliverable_format_quality.py`
- `backend/tests/unit/services/test_deliverable_format_renderers.py`
- `backend/tests/unit/services/test_deliverable_formatting.py`
- `backend/tests/fixtures/formatting/legacy_marketing_deliverables.json`
- `backend/tests/fixtures/formatting/consulting_handoff_deliverables.json`
- `backend/tests/fixtures/formatting/profiles/legacy.client_handoff.v1.json`
- `backend/tests/fixtures/formatting/profiles/consulting.standard_handoff.v1.json`

Strategy correction: do not create a new top-level `src/forgegraph` package. Keep the slice inside the existing Django backend service layout under `backend/application/services/`.

## Slice 1 Profile Modeling

Use existing metadata/config first.

Profile definitions:

- Store versioned profile config in repo-owned YAML or JSON.
- Resolve profiles through a backend registry.
- Allow existing durable objects to reference a profile by id/version.
- Snapshot resolved profile hash and selected settings into render provenance.

Recommended metadata references:

```json
{
  "formatting": {
    "profile_ref": "format_profile:legacy.client_handoff@1",
    "default_formats": ["markdown_report", "manifest", "zip_package"],
    "required_gate_set": "client_handoff@1"
  }
}
```

Where to place references:

- `ServiceEngagement.metadata.formatting.profile_ref` for engagement-specific handoff preferences.
- `CompanyProgram.metadata.formatting.profile_ref` for program-level defaults.
- `ServiceDeliverable.metadata.formatting.source_role` for section mapping hints, not final rendered state.
- Existing pack/handoff metadata, if present, for package-level requested formats.

Resolution order:

1. Explicit `FormatRequest.profile_ref`.
2. `ServiceEngagement` formatting metadata.
3. `CompanyProgram` formatting metadata.
4. Company metadata, if already available.
5. Generic default profile.

Do not add a new `FormatProfile` database model in slice 1. Add one later only if operations need queryable profile lifecycle, approval workflows, per-tenant editing, or audit history beyond what config hash/provenance provides.

## Minimal Data Shapes

### FormatProfile

```json
{
  "profile_id": "legacy.client_handoff",
  "version": 1,
  "display_name": "Legacy Client Handoff",
  "business_domain": "marketing",
  "formats": ["markdown_report", "manifest", "zip_package"],
  "voice": {
    "audience": "client_executive",
    "tone": "direct, polished, evidence-led",
    "forbidden_phrases": ["as an AI", "I cannot", "placeholder"],
    "naming": {
      "client_display_name": "Legacy",
      "provider_display_name": "Atlas"
    }
  },
  "sections": [
    {
      "id": "executive_summary",
      "title": "Executive Summary",
      "required": true,
      "source_roles": ["summary", "strategy"]
    },
    {
      "id": "evidence",
      "title": "Evidence",
      "required": true,
      "source_roles": ["source", "finding"]
    },
    {
      "id": "recommendations",
      "title": "Recommendations",
      "required": true,
      "source_roles": ["recommendation"]
    }
  ],
  "quality_gates": ["client_handoff@1"],
  "connector_policy": {
    "require_caveats_for_unverified_sources": true,
    "require_approval_language": true
  },
  "layout": {
    "heading_style": "professional_report",
    "include_manifest_link": true
  }
}
```

For consulting, only profile config changes: `business_domain`, display names, section labels, voice, and required source roles. Renderer code remains generic.

### FormatRequest

```json
{
  "request_id": "fmtreq_...",
  "company_id": "...",
  "service_engagement_id": "...",
  "company_program_id": "...",
  "program_stage_state_id": "...",
  "source_service_deliverable_ids": ["..."],
  "source_asset_version_ids": ["..."],
  "profile_ref": "format_profile:legacy.client_handoff@1",
  "requested_formats": ["markdown_report", "manifest", "zip_package"],
  "package_options": {
    "include_pdf": false,
    "include_email_draft": true
  },
  "requested_by": "system_or_user_id",
  "idempotency_key": "handoff:engagement:stage:profile:v1",
  "dry_run": true
}
```

### RenderResult

```json
{
  "request_id": "fmtreq_...",
  "format": "markdown_report",
  "status": "succeeded",
  "asset_id": "...",
  "asset_version_id": "...",
  "filename": "legacy-client-handoff.md",
  "mime_type": "text/markdown",
  "bytes_sha256": "...",
  "quality_gate_result_id": "...",
  "warnings": [],
  "created_at": "2026-06-05T00:00:00Z"
}
```

### QualityGateResult

```json
{
  "gate_set": "client_handoff@1",
  "status": "passed",
  "checks": [
    {
      "id": "no_placeholders",
      "status": "passed",
      "severity": "blocker",
      "evidence": []
    },
    {
      "id": "evidence_recommendation_separation",
      "status": "passed",
      "severity": "blocker",
      "evidence": ["sections:evidence", "sections:recommendations"]
    }
  ],
  "blocked_reasons": [],
  "warnings": []
}
```

### Provenance

```json
{
  "renderer": {
    "name": "markdown_report",
    "version": "1"
  },
  "profile": {
    "profile_ref": "format_profile:legacy.client_handoff@1",
    "profile_sha256": "..."
  },
  "sources": {
    "service_deliverable_ids": ["..."],
    "asset_version_ids": ["..."],
    "source_hashes": ["..."]
  },
  "request": {
    "request_id": "fmtreq_...",
    "idempotency_key": "handoff:engagement:stage:profile:v1"
  },
  "quality": {
    "gate_result_id": "...",
    "status": "passed"
  },
  "output": {
    "asset_version_id": "...",
    "bytes_sha256": "..."
  },
  "runtime": {
    "created_by": "backend_formatting_service",
    "created_at": "2026-06-05T00:00:00Z"
  }
}
```

Persist provenance under `AssetVersion.metadata.render_provenance`. Optionally add lightweight backlink metadata on `ServiceDeliverable.metadata.formatted_artifacts` listing latest derived artifacts by format. The backlink is convenience metadata only; the `AssetVersion` remains the artifact record.

## Avoiding Atlas Or Marketing Hardcoding

- Renderer names stay generic: `markdown_report`, `pdf_report`, `executive_memo`, `approval_packet`, `email_handoff`, `zip_package`, `manifest`.
- Section ids stay domain-neutral: `executive_summary`, `context`, `findings`, `evidence`, `recommendations`, `approval_items`, `risks`, `next_steps`, `appendix`.
- Profiles provide labels, voice, naming, ordering, and section requirements. Renderer code never checks for `Atlas`, `Legacy`, `marketing`, campaigns, ads, or creative concepts.
- Source mapping uses deliverable roles and metadata, not product-specific classes.
- Tests must include both `legacy.client_handoff` and `consulting.standard_handoff`; the same renderer and quality gate tests should pass for both.
- Atlas can remain a product/user of the primitives by selecting a profile and providing source deliverables. ForgeGraph does not learn Atlas-specific semantics.

## Email And PDF Handling

PDF:

- Render through a backend-owned adapter.
- Store successful PDF bytes as an `AssetVersion`.
- Record renderer/tool versions, profile hash, source hashes, and output hash.
- Treat render failures as explicit failed `RenderResult`s.
- Do not make visual UI rendering acceptance-critical; use content, metadata, non-empty bytes, and manifest/hash assertions.

Email:

- `email_handoff` first renders a durable draft artifact: subject, body, attachment refs, manifest refs, caveats, and approval wording.
- Dry-run output must be clearly marked as draft/not sent.
- Production send requires a configured provider adapter and an explicit send command.
- Record `sent` only after the provider accepts the message and returns evidence such as provider name, message id, accepted recipients, and timestamp.
- If provider is missing, return `not_configured`; do not claim delivery.
- Never store or print provider secrets.

## Test Plan

Unit tests:

- Profile schema validation rejects unknown renderer ids, missing required sections, duplicate section ids, and unsafe profile refs.
- Profile resolution follows request, engagement, program, company, default precedence.
- Provenance hash changes when profile config or source asset versions change.
- Quality gates block placeholders, AI/meta language, missing sections, naming drift, and missing connector caveats.
- Quality gates allow consulting-specific labels without marketing assumptions.

Renderer tests:

- `markdown_report` renders required sections in configured order for Legacy and consulting fixtures.
- `manifest` includes all source and output asset version ids plus hashes.
- `zip_package` contains only approved artifacts and a manifest.
- `pdf_report`, once added, produces non-empty PDF bytes and manifest/provenance references.
- `email_handoff` produces a draft with subject/body/attachment refs and never marks dry-run output as sent.

Integration tests:

- Existing flow: `CompanyProgram` + `ProgramStageState` creates `TaskRoutingRecord` cards, stage execution produces `ServiceDeliverable` + `AssetVersion`, then formatting creates derived artifacts and package manifest.
- Legacy marketing fixture proves improved handoff quality.
- Consulting fixture proves non-marketing handoff quality with the same renderers and gate set.
- Engine/worker execution never owns durable render status; persisted state is backend-owned.

Regression tests:

- Events emitted during formatting are observability/transport only.
- Package readiness can be reconstructed from backend records, not from event history.
- Resume/retry uses backend-owned request/result/provenance records and idempotency keys.

## Verification Commands

For Mike's Windows Git Bash setup:

```bash
cd backend
export UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline
uv run python -m pytest tests/unit/services/test_deliverable_format_profiles.py tests/unit/services/test_deliverable_format_quality.py tests/unit/services/test_deliverable_format_renderers.py tests/unit/services/test_deliverable_formatting.py -q
```

Targeted commands after each slice:

```bash
cd backend
export UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline
uv run python -m pytest tests/unit/services/test_deliverable_format_profiles.py -q
uv run python -m pytest tests/unit/services/test_deliverable_format_quality.py -q
uv run python -m pytest tests/unit/services/test_deliverable_format_renderers.py -q
uv run python -m pytest tests/unit/services/test_deliverable_formatting.py -q
uv run ruff check application/services/deliverable_format_profiles.py application/services/deliverable_format_quality.py application/services/deliverable_format_renderers.py application/services/deliverable_formatting.py tests/unit/services/test_deliverable_format_profiles.py tests/unit/services/test_deliverable_format_quality.py tests/unit/services/test_deliverable_format_renderers.py tests/unit/services/test_deliverable_formatting.py
uv run python manage.py check
```

If the current repo keeps pipeline tests elsewhere, add the existing department pipeline regression command, for example:

```bash
export UV_PROJECT_ENVIRONMENT=.venv-test-department-pipeline
uv run python -m pytest tests -q -k "department_pipeline or company_program or handoff or service_deliverable"
```

PowerShell equivalent:

```powershell
$env:UV_PROJECT_ENVIRONMENT = ".venv-test-department-pipeline"
uv run python -m pytest tests/formatting -q
```

## Acceptance Criteria

- Canonical content remains in `ServiceDeliverable` and source `AssetVersion`s.
- Every formatted artifact is stored as a derived `AssetVersion` with render provenance.
- A package manifest identifies source deliverables, source asset versions, output asset versions, hashes, profile id/version/hash, renderer versions, and gate results.
- Output contains no unresolved placeholders, template tokens, or AI/meta language.
- Required sections are present and ordered according to the selected profile.
- Client/company/provider naming is consistent throughout the artifact.
- Evidence/facts are clearly separated from recommendations.
- Connector caveats and approval language appear when source/profile policy requires them.
- Legacy handoff package is client-ready without making renderer code Atlas/marketing-specific.
- Consulting fixture produces a client-ready non-marketing handoff using the same generic renderers.
- Email drafts are not reported as sent. Real email delivery is recorded only with provider acceptance evidence.
- UI rendering is not acceptance-critical.

## Risks And Tradeoffs

- Metadata/config profiles are fastest and safest for slice 1, but may become awkward if users need profile search, approval workflows, or live editing. Defer a DB model until those needs are real.
- Quality gates can produce false positives or miss subtle quality issues. Keep deterministic checks as blockers and use any model-assisted review only as advisory unless separately validated.
- Snapshot tests can become brittle. Prefer semantic assertions for sections, hashes, provenance, and gate outcomes.
- PDF rendering dependencies can add operational complexity. Hide them behind an adapter and fail explicitly when unavailable.
- Zip packages can accidentally include stale or unapproved artifacts. Build packages only from backend-approved `RenderResult`s and manifest entries.
- Profile flexibility can drift into a template DSL. Keep slice 1 profiles declarative: sections, labels, ordering, voice rules, quality gates, and renderer options only.

## Do Not Build Yet

- A visual profile editor or WYSIWYG formatting UI.
- New database models for profiles unless metadata/config cannot satisfy slice 1.
- Atlas-specific or marketing-specific renderer classes.
- Engine-owned durable package state, delivery state, or resume state.
- Arbitrary user-authored templates executed at runtime.
- Production email sending without a real provider adapter and acceptance evidence.
- A PDF-as-source workflow.
- Event-sourced package readiness.
- Broad UI changes; handoff quality and packaging are the priority.
