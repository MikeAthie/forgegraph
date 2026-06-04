# Atlas Deliverable Assembly Layer Implementation Plan

> **For Hermes/Codex:** Implement this plan with strict TDD. Preserve Mike's existing dirty working tree; do not reset, checkout, stash, or overwrite unrelated files. Keep connector production work out of scope.

**Goal:** Add a backend deliverable assembly layer that turns Atlas whiteboard phase/deployment/performance state into durable, customer-facing `ServiceDeliverable` records backed by `Asset`/`AssetVersion` content.

**Architecture:** Reuse existing ForgeGraph primitives instead of adding schema: `ServiceCatalogItem`, `ServiceEngagement`, `ServiceDeliverable`, `Asset`, `AssetVersion`, `WorkWhiteboard`, `StateProjection`, and current archive services. The new layer should be deterministic and idempotent: repeated assembly for the same whiteboard and deliverable type updates/reuses the same engagement/assets/deliverables and only creates a new asset version if content changes.

**Tech Stack:** Django ORM, pytest-django, DRF-adjacent service payload helpers, existing backend services under `backend/application/services`, tests under `backend/tests/unit/services`.

---

## Non-goals

- Do not implement production social/email/WhatsApp connector fixes.
- Do not add frontend UI in this first pass.
- Do not add PDF/export/share links yet.
- Do not add database migrations unless strictly required; prefer metadata/source-key reuse.
- Do not rework existing service-engagement APIs.

---

## Current primitives to reuse

Known files:

- `backend/application/services/service_engagements.py`
  - `service_deliverable_payload(deliverable)` exists but does not include metadata or latest asset version yet.
  - `create_service_catalog_item`, `create_service_engagement`, deliverable create/update helpers exist.
- `backend/application/services/company_archive.py`
  - `ArchiveService.create_asset(...)`
  - `ArchiveService.create_asset_version(...)`
  - Content hashes already dedupe versions.
- `backend/infrastructure/orm/models/operating_models.py`
  - `ServiceCatalogItem`, `ServiceEngagement`, `ServiceDeliverable`.
  - `ServiceDeliverable.engagement` is required.
- `backend/infrastructure/orm/models/decisions_assets.py`
  - `Asset`, `AssetVersion`.
- `backend/application/services/deployment_orchestration.py`
  - Deployment state/contracts already expose executed/blocked channels and receipts.
- `backend/application/services/performance_orchestration.py`
  - Performance state/contracts expose `metric_snapshot_id`, `report_run_id`, `evaluation_id`.
- `backend/tests/unit/services/test_deployment_orchestration.py`
- `backend/tests/unit/services/test_performance_orchestration.py`
- `backend/tests/unit/api/test_service_engagements_api.py`

---

## Deliverable MVP scope

Implement a service that can assemble these 10 deliverable types:

1. `client_brief`
2. `strategy_brief`
3. `message_house`
4. `launch_readiness_checklist`
5. `connector_gap_report`
6. `measurement_plan`
7. `approval_packet`
8. `execution_receipt`
9. `performance_report`
10. `campaign_launch_package`

Each type should have canonical metadata:

- `type`
- `label`
- `group`
- `owner_department_slug`
- `visibility`
- `requires_approval`
- `source_kinds` e.g. `whiteboard`, `phase`, `deployment`, `performance`, `approval`, `package`

---

## Data conventions

### Source keys

Use deterministic source keys:

```text
atlas-deliverable:{whiteboard_id}:{deliverable_type}
atlas-engagement:{whiteboard_id}
atlas-catalog:digital-marketing-agency-engagement
```

### Asset metadata

Asset metadata should include:

```json
{
  "source": "atlas_deliverable_assembly",
  "whiteboard_id": "...",
  "deliverable_type": "strategy_brief",
  "owner_department_slug": "strategy_research",
  "visibility": "customer"
}
```

### ServiceDeliverable metadata

`ServiceDeliverable.metadata_json` should include:

```json
{
  "source": "atlas_deliverable_assembly",
  "whiteboard_id": "...",
  "deliverable_type": "strategy_brief",
  "owner_department_slug": "strategy_research",
  "asset_version_id": "...",
  "source_refs": {...},
  "blocked_by": [],
  "evidence": []
}
```

### Content format

Create Markdown content for each asset version. The content can be deterministic and concise; it does not need LLM polish yet.

Minimum Markdown structure:

```markdown
# <Deliverable label>

## Client Summary
...

## Source Evidence
...

## Status
...
```

For connector-gap/execution receipt deliverables, include channel status details from deployment state if available.
For performance-report deliverables, include report/evaluation/metric IDs if available.
For campaign-launch-package, include a grouped list of included deliverables and their statuses.

---

## Task 1: Add deliverable catalog constants

**Objective:** Create canonical deliverable definitions with no database writes.

**Files:**
- Create: `backend/application/services/agency_deliverable_catalog.py`
- Create: `backend/tests/unit/services/test_agency_deliverable_catalog.py`

**TDD:**

1. Write tests that assert:
   - all 10 MVP types are present,
   - each type has label/group/owner department/visibility/requires approval,
   - `get_deliverable_definition("strategy_brief")` returns owner `strategy_research`,
   - unknown type raises/returns `None` predictably.
2. Run targeted test and verify RED.
3. Implement the catalog.
4. Run targeted test and verify GREEN.

Suggested API:

```python
@dataclass(frozen=True)
class DeliverableDefinition:
    type: str
    label: str
    group: str
    owner_department_slug: str
    visibility: str = "customer"
    requires_approval: bool = False
    source_kinds: tuple[str, ...] = ()

MVP_DELIVERABLE_TYPES = (...)
DELIVERABLE_DEFINITIONS = {...}

def list_deliverable_definitions() -> tuple[DeliverableDefinition, ...]: ...
def get_deliverable_definition(deliverable_type: str) -> DeliverableDefinition | None: ...
```

---

## Task 2: Add assembly service skeleton and engagement/catalog upsert

**Objective:** Add idempotent helper to find/create the required catalog item and service engagement for a whiteboard.

**Files:**
- Create: `backend/application/services/agency_deliverables.py`
- Create/extend: `backend/tests/unit/services/test_agency_deliverables.py`

**TDD:**

1. Test `ensure_atlas_service_engagement(whiteboard, user)` creates one `ServiceCatalogItem` and one `ServiceEngagement`.
2. Test calling it twice returns the same engagement and does not duplicate records.
3. Test engagement includes source key `atlas-engagement:{whiteboard.id}`, required pack `digital_marketing_pro.v1`, public summary from whiteboard request/objective.
4. Run RED.
5. Implement minimal helper.
6. Run GREEN.

Implementation notes:

- Use `ServiceCatalogItem.objects.get_or_create(organization=..., slug="digital-marketing-agency-engagement")`.
- Use `ServiceEngagement.objects.get_or_create(company=whiteboard.company, source_key=f"atlas-engagement:{whiteboard.id}")`.
- `ServiceEngagement.catalog_item` is required, so catalog upsert comes first.

---

## Task 3: Add single-deliverable assembly

**Objective:** Assemble one deliverable type into `Asset`, `AssetVersion`, and `ServiceDeliverable`.

**Files:**
- Modify: `backend/application/services/agency_deliverables.py`
- Modify: `backend/tests/unit/services/test_agency_deliverables.py`

**TDD:**

1. Test assembling `client_brief` creates:
   - one active `Asset` with source key `atlas-deliverable:{whiteboard.id}:client_brief`,
   - one `AssetVersion` with `text/markdown`,
   - one `ServiceDeliverable` with type `client_brief`, status `ready`, visibility `customer`, linked artifact.
2. Test repeated assembly does not create a second `Asset`, `AssetVersion`, `ServiceDeliverable`, or `ServiceEngagement` if content is unchanged.
3. Test `metadata_json` includes whiteboard id, deliverable type, owner department, and asset version id.
4. Run RED then GREEN.

Suggested API:

```python
def assemble_atlas_deliverable(
    *,
    whiteboard: WorkWhiteboard,
    user: User | None,
    deliverable_type: str,
    source_state: dict[str, Any] | None = None,
) -> ServiceDeliverable:
    ...
```

---

## Task 4: Add MVP batch assembly

**Objective:** Assemble all 10 MVP deliverables for a whiteboard.

**Files:**
- Modify: `backend/application/services/agency_deliverables.py`
- Modify: `backend/tests/unit/services/test_agency_deliverables.py`

**TDD:**

1. Test `assemble_atlas_mvp_deliverables(whiteboard, user)` returns 10 deliverables with expected types.
2. Test calling it twice remains idempotent.
3. Test campaign launch package content references the other deliverable labels/types.
4. Run RED then GREEN.

Suggested API:

```python
def assemble_atlas_mvp_deliverables(
    *,
    whiteboard: WorkWhiteboard,
    user: User | None,
    source_state: dict[str, Any] | None = None,
) -> list[ServiceDeliverable]:
    ...
```

---

## Task 5: Add state extraction from whiteboard projections

**Objective:** Let the assembly service pull deployment/performance state from existing projections when source_state is not passed.

**Files:**
- Modify: `backend/application/services/agency_deliverables.py`
- Modify: `backend/tests/unit/services/test_agency_deliverables.py`

**TDD:**

1. Create a `StateProjection` for `whiteboard_deployment:{whiteboard.id}` with executed and blocked channels.
2. Assemble `connector_gap_report` and `execution_receipt`.
3. Assert Markdown/metadata includes executed channel names and blocked/missing connector channel names.
4. Create a performance projection or state with report/evaluation IDs if existing service uses projections; otherwise pass explicit `source_state` for test and make extractor tolerant.
5. Assert `performance_report` metadata/content includes report/evaluation IDs.
6. Run RED then GREEN.

Implementation notes:

- Keep extraction tolerant; missing projections should not fail assembly.
- Store source summary in `ServiceDeliverable.metadata_json["source_refs"]`.

---

## Task 6: Add payload helper for latest version/metadata

**Objective:** Make service-layer payloads useful for future API/frontend without changing frontend yet.

**Files:**
- Modify: `backend/application/services/service_engagements.py`
- Create/modify test in `backend/tests/unit/services/test_agency_deliverables.py` or existing service-engagement API tests.

**TDD:**

1. Test `service_deliverable_payload(deliverable)` includes:
   - `metadata`,
   - `latest_asset_version_id`,
   - `latest_asset_version_uri`,
   - `latest_asset_version_mime_type`.
2. Run RED then GREEN.

Compatibility requirement:

- Preserve all existing response keys.
- Do not leak private/internal metadata; if existing tests assert no private data leakage, keep respecting that. If metadata could include internal notes, filter only safe keys or include metadata only from assembly service. Prefer safe filtering:
  - exclude keys containing `private`, `secret`, `token`, `credential`, `password`, `api_key`.

---

## Task 7: Run verification

Run these commands from repo root or backend root, depending on project conventions:

```bash
cd backend && pytest tests/unit/services/test_agency_deliverable_catalog.py -q
cd backend && pytest tests/unit/services/test_agency_deliverables.py -q
cd backend && pytest tests/unit/api/test_service_engagements_api.py -q
```

If import path requires repo root, use the existing convention from current tests and adapt.

Also run:

```bash
git diff --stat
```

---

## Acceptance criteria

- [ ] New catalog service defines the 10 MVP deliverables.
- [ ] New assembly service creates/reuses `ServiceCatalogItem` and `ServiceEngagement` per whiteboard.
- [ ] Single deliverable assembly creates/reuses `Asset`, `AssetVersion`, `ServiceDeliverable`.
- [ ] Batch assembly creates all 10 MVP deliverables.
- [ ] Assembly is idempotent for unchanged content.
- [ ] Deployment/performance evidence is reflected when available, without requiring connector fixes.
- [ ] Payload helper includes safe metadata and latest asset version info.
- [ ] Targeted tests pass.

---

## Codex guardrails

- Work in `C:/Users/mathi/projects/forgegraph`.
- There are many unrelated modified files in the working tree. Do not touch them unless necessary for this plan.
- Do not run destructive git commands.
- Do not commit unless explicitly requested after verification.
- Keep implementation backend-only for this first pass.
- Follow TDD: write tests first, run them to verify failure, then implement.
