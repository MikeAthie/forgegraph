# CareerOps Native URL Pipeline Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Implement the next ForgeGraph-native CareerOps slice: a pasted job URL/JD creates backend-owned execution state (`Run`), observable tasks (`TaskRecord`), scan/tracker records (`CompanySignal`/`CompanyOpportunity`), exact-version approval (`DecisionRecord`), versioned packet artifacts (`AssetVersion`/`ServiceDeliverable`), and rebuildable pipeline projections (`StateProjection`) without any employer-facing side effect.

**Architecture:** Keep ForgeGraph backend as the durable source of truth. The first implementation should be a backend-only URL pipeline service plus CLI/management-command smoke path; UI and live connector/browser submission stay out of scope. Reuse existing primitives (`GraphVersion`, `Run`, `TaskRecord`, `CompanySignal`, `CompanyOpportunity`, `Asset`, `AssetVersion`, `ServiceCatalogItem`, `ServiceEngagement`, `ServiceDeliverable`, `DecisionRecord`, `StateProjection`) before adding migrations or CareerOps-specific tables.

**Tech Stack:** Django/Python services, existing ForgeGraph ORM models, pytest/pytest-django, ruff, SQLite-backed local verification through `UV_PROJECT_ENVIRONMENT=.venv-test-career-ops`, optional Codex concurrent worktrees only after this plan is approved.

---

## Planning-only boundary

Do **not** implement code until Mike approves this plan or a specific PR slice.

This plan intentionally avoids:

- live employer sends/submits/browser form fills,
- portal scanner fan-out,
- dashboard/TUI replication,
- external LLM/job-board integrations,
- new DB migrations unless a later task proves existing primitives cannot model the invariant.

---

## Existing foundation

Already present and verified in the repo:

- `backend/application/services/career_ops_graph_contract.py`
- `backend/application/services/career_ops_opportunities.py`
- `backend/tests/unit/services/test_career_ops_graph_contract.py`
- `backend/tests/unit/services/test_career_ops_opportunities.py`
- `docs/operating-model-packs/career-ops.md`
- `docs/operating-model-packs/career-ops-native-forgegraph-mapping.md`
- `.hermes/plans/2026-06-16_190000-career-ops-native-forgegraph-contract.md`

Current verified command shape:

```bash
cd backend
FORGEGRAPH_ENV_FILE= DEBUG=1 SECRET_KEY=*** USE_SQLITE=true \
  USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 \
  SQLITE_DB_PATH=.hermes/career_ops_test.sqlite3 \
  UV_PROJECT_ENVIRONMENT=.venv-test-career-ops \
  uv run --group dev pytest \
    tests/unit/services/test_career_ops_graph_contract.py \
    tests/unit/services/test_career_ops_opportunities.py \
    -q
```

Expected current baseline:

```text
8 passed
```

---

## Target backend contract for this slice

A single call such as:

```python
run_career_ops_url_pipeline(
    company=company,
    actor=user,
    posting={
        "title": "Senior Product Engineer",
        "company": "Acme AI",
        "url": "https://jobs.example.com/acme/senior-product-engineer?utm_source=x",
        "location": "Remote",
        "description": "...",
        "provider": "manual_url",
    },
    idempotency_key="career-ops:url:<normalized-key>",
    dry_run=True,
)
```

must materialize/replay:

1. `GraphVersion` — latest CareerOps workflow definition or a minimal generated version if none exists.
2. `Run` — input, normalized posting, source refs, dry-run flag, no external side effects.
3. `CompanySignal` — scan/inbox lead from `record_scanned_job`.
4. `CompanyOpportunity` — tracker row from `ensure_opportunity_for_signal`.
5. `TaskRecord` rows for the P0 stages:
   - `stage_03_market_scan`
   - `stage_04_liveness_and_dedupe`
   - `stage_05_fit_evaluation`
   - `stage_06_application_packet`
   - `stage_07_candidate_approval`
   - `stage_08_submission_tracking`
6. `Asset`/`AssetVersion` + `ServiceDeliverable` for at least:
   - `job_liveness_receipt`
   - `job_evaluation_report`
   - `application_packet`
7. `DecisionRecord(decision_type="human_approval", status="pending")` referencing the exact `AssetVersion` IDs for the packet.
8. `StateProjection(projection_type="career_ops:pipeline_snapshot")` rebuilt from durable records.

The call must **not** create any external side effect, and should mark side-effect status as `manual_only` / `blocked_until_approval`.

---

## PR roadmap

| Order | Branch / PR | Objective | Boundary | Dependencies | Success criteria |
|---:|---|---|---|---|---|
| 0 | `docs/career-ops-native-plan` | Land/keep this plan and existing docs contract | Planning only | None | Plan saved; no runtime changes |
| 1 | `feat/career-ops-url-run-tasks` | URL/JD pipeline creates `Run`, scan/tracker state, and `TaskRecord` fan-out | Backend service + tests only | Existing opportunity service | Unit tests prove native records materialize idempotently |
| 2 | `feat/career-ops-packet-approval-projection` | Create fake-safe packet artifacts, pending exact-version approval, and pipeline projection | Backend service + tests only | PR 1 | Tests prove artifacts/approval/projection are durable and replayable |
| 3 | `feat/career-ops-cli-smoke` | Add management command for local dry-run URL pipeline smoke | CLI + tests only | PR 2 | Command returns JSON evidence; no side effects |
| 4 | `feat/career-ops-quality-readiness-foundation` | Add fail-closed packet quality/readiness gates | Backend services + command/tests | PR 2/3 | Missing approval/base CV/live-send config blocks readiness |
| 5 | `feat/career-ops-daily-discovery-adapter` | Add backend-owned daily discovery handler shape or bridge to generic automations if present | Backend handler/tests; no live schedule mutation | PR 1-4 | Handler creates/replays due run summary and respects cooldown/base CV |

Recommended implementation order: PR 1 and PR 2 are sequential. PR 3 can begin after PR 1 with stubs but should merge after PR 2. PR 4 can be worked concurrently with PR 2 once artifact metadata shape is agreed. PR 5 should wait until PR 1 and base CV blocking behavior are stable.

---

## Concurrent Codex execution plan after approval

If Mike approves using concurrent Codex calls, run isolated worktrees/lane prompts rather than multiple agents editing the same checkout.

### Codex Lane A — Native URL pipeline state

**Scope:** PR 1 only.

**Files:**

- Create `backend/application/services/career_ops_pipeline.py`
- Create `backend/application/services/career_ops_tasks.py`
- Create `backend/tests/unit/services/test_career_ops_pipeline.py`

**Acceptance:** URL/JD pipeline creates/replays `Run`, `CompanySignal`, `CompanyOpportunity`, and `TaskRecord` rows.

### Codex Lane B — Artifacts, approval, projection

**Scope:** PR 2 only, based on Lane A interface.

**Files:**

- Create `backend/application/services/career_ops_artifacts.py`
- Create `backend/application/services/career_ops_approvals.py`
- Create `backend/application/services/career_ops_projections.py`
- Create `backend/tests/unit/services/test_career_ops_artifacts.py`
- Create `backend/tests/unit/services/test_career_ops_approvals.py`
- Create `backend/tests/unit/services/test_career_ops_projections.py`

**Acceptance:** fake-safe packet versions and pending approval decision exist; projection is rebuildable.

### Codex Lane C — Readiness gates and command surface

**Scope:** PR 3/4 after Lane A interface exists.

**Files:**

- Create `backend/infrastructure/orm/management/commands/run_career_ops_url_pipeline.py`
- Create `backend/infrastructure/orm/management/commands/check_career_ops_live_readiness.py`
- Create `backend/application/services/career_ops_quality_gates.py`
- Create `backend/tests/unit/management/test_run_career_ops_url_pipeline.py`
- Create `backend/tests/unit/management/test_check_career_ops_live_readiness.py`
- Create `backend/tests/unit/services/test_career_ops_quality_gates.py`

**Acceptance:** CLI dry-run evidence exists; readiness fails closed by default.

Hermes must verify every lane independently: inspect diffs, run tests, run ruff/check, and only then reconcile/merge.

---

# Detailed implementation tasks

## PR 1 — Native URL pipeline state materialization

### Task 1: Add pipeline result dataclasses and constants

**Objective:** Define a small typed return contract so later services do not pass loose dictionaries.

**Files:**

- Create: `backend/application/services/career_ops_pipeline.py`
- Test: `backend/tests/unit/services/test_career_ops_pipeline.py`

**Step 1: Write failing test**

Add a test that imports `CareerOpsPipelineResult` and asserts fields are present:

```python
from application.services.career_ops_pipeline import CareerOpsPipelineResult


def test_pipeline_result_contract_has_native_ids():
    fields = set(CareerOpsPipelineResult.__dataclass_fields__)
    assert {
        "run_id",
        "signal_id",
        "opportunity_id",
        "task_ids",
        "decision_id",
        "deliverable_ids",
        "projection_id",
        "blocked_reasons",
    }.issubset(fields)
```

**Step 2: Run failure**

```bash
cd backend
FORGEGRAPH_ENV_FILE= DEBUG=1 SECRET_KEY=*** USE_SQLITE=true \
  USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 \
  SQLITE_DB_PATH=.hermes/career_ops_pipeline_test.sqlite3 \
  UV_PROJECT_ENVIRONMENT=.venv-test-career-ops \
  uv run --group dev pytest tests/unit/services/test_career_ops_pipeline.py::test_pipeline_result_contract_has_native_ids -q
```

Expected: import failure because the module/class does not exist.

**Step 3: Minimal implementation**

Create:

```python
"""ForgeGraph-native CareerOps URL/JD pipeline orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class CareerOpsPipelineResult:
    run_id: str
    signal_id: str | None = None
    opportunity_id: str | None = None
    task_ids: list[str] = field(default_factory=list)
    decision_id: str | None = None
    deliverable_ids: list[str] = field(default_factory=list)
    projection_id: str | None = None
    blocked_reasons: list[str] = field(default_factory=list)
```

**Step 4: Run pass**

Same command; expected: pass.

---

### Task 2: Add CareerOps graph-version resolver

**Objective:** Ensure URL pipeline can always create a `Run` against a backend-owned workflow version.

**Files:**

- Modify: `backend/application/services/career_ops_pipeline.py`
- Test: `backend/tests/unit/services/test_career_ops_pipeline.py`

**Design rule:** Use the latest `GraphVersion` when present. Only create a minimal CareerOps graph version if the company has no versions. Do not introduce migrations.

**Test behavior:**

- Given a company with an existing `GraphVersion`, resolver returns it without creating another.
- Given a company without versions, resolver creates version `1` with `metadata.pack_id == career_ops.v1` and stage node IDs from `CAREER_OPS_STAGE_SEQUENCE`.

**Implementation sketch:**

```python
from django.db import transaction
from infrastructure.orm.models import Graph, GraphVersion
from application.services.career_ops_graph_contract import (
    CAREER_OPS_PACK_ID,
    CAREER_OPS_STAGE_LABELS,
    CAREER_OPS_STAGE_SEQUENCE,
)


def ensure_career_ops_graph_version(*, company: Graph) -> GraphVersion:
    latest = company.versions.order_by("-version").first()
    if latest is not None:
        return latest
    with transaction.atomic():
        latest = GraphVersion.objects.filter(graph=company).order_by("-version").first()
        if latest is not None:
            return latest
        return GraphVersion.objects.create(
            graph=company,
            version=1,
            external_idempotency_key=f"career-ops:{company.id}:initial-graph",
            graph_json={
                "nodes": [
                    {"id": stage, "type": "career_ops_stage", "label": CAREER_OPS_STAGE_LABELS[stage]}
                    for stage in CAREER_OPS_STAGE_SEQUENCE
                ],
                "edges": [
                    {"source": src, "target": dst}
                    for src, dst in zip(CAREER_OPS_STAGE_SEQUENCE, CAREER_OPS_STAGE_SEQUENCE[1:], strict=False)
                ],
                "metadata": {"pack_id": CAREER_OPS_PACK_ID, "source": "career_ops_pipeline"},
            },
        )
```

**Verification:** focused pytest for the resolver.

---

### Task 3: Create `Run` for URL pipeline without engine dispatch

**Objective:** Materialize the URL/JD intake as a backend `Run` so it can be tracked and associated with tasks/artifacts.

**Files:**

- Modify: `backend/application/services/career_ops_pipeline.py`
- Test: `backend/tests/unit/services/test_career_ops_pipeline.py`

**Key behavior:**

- `Run.owner` is the actor for manual URL pipelines.
- `Run.status` should start as `running` and end as `succeeded` for synchronous dry-run orchestration.
- `Run.input_json` includes `career_ops`, normalized posting, `idempotency_key`, `dry_run=true`, and `external_side_effects_allowed=false`.
- No engine call occurs in this slice.

**Implementation sketch:**

```python
from django.utils import timezone
from infrastructure.orm.models import Graph, Run, User


def create_career_ops_run(*, company: Graph, actor: User, posting: dict, idempotency_key: str) -> Run:
    graph_version = ensure_career_ops_graph_version(company=company)
    now = timezone.now()
    return Run.objects.create(
        owner=actor,
        organization=company.organization,
        graph_version=graph_version,
        status="running",
        started_at=now,
        last_progress_at=now,
        recovery_policy="resume",
        input_json={
            "career_ops": {
                "pipeline": "url_intake",
                "idempotency_key": idempotency_key,
                "posting": posting,
                "submit_mode": "manual_only",
                "dry_run": True,
                "external_side_effects_allowed": False,
            }
        },
    )
```

**Idempotency note:** `Run` has no unique idempotency key today. PR 1 should rely on idempotent downstream records (`CompanySignal`, `CompanyOpportunity`, `TaskRecord`) and include `idempotency_key` in `Run.input_json`. If repeated identical calls create multiple `Run` records, tests should assert downstream state is replayed/updated rather than duplicated. A future generic automation/idempotency table can own cross-surface run replay.

---

### Task 4: Materialize P0 `TaskRecord` rows

**Objective:** Make URL pipeline progress visible as native tasks rather than hidden service work.

**Files:**

- Create: `backend/application/services/career_ops_tasks.py`
- Modify: `backend/application/services/career_ops_pipeline.py`
- Test: `backend/tests/unit/services/test_career_ops_tasks.py`
- Test: `backend/tests/unit/services/test_career_ops_pipeline.py`

**Task stages:**

```python
CAREER_OPS_URL_PIPELINE_TASK_STAGES = (
    "stage_03_market_scan",
    "stage_04_liveness_and_dedupe",
    "stage_05_fit_evaluation",
    "stage_06_application_packet",
    "stage_07_candidate_approval",
    "stage_08_submission_tracking",
)
```

**Implementation rules:**

- Use `TaskRecord.objects.update_or_create(organization=..., external_key=...)` because `TaskRecord` is unique on `(organization, external_key)`.
- External key shape: `career_ops:url_pipeline:<opportunity_external_key>:<stage_id>`.
- `execution` should be updated to the latest pipeline `Run` on replay.
- `source_node_id` should be the stage ID.
- Department lookup is optional but should use `DepartmentRegistry.slug == CAREER_OPS_STAGE_TO_DEPARTMENT[stage_id]` when available.

**Implementation sketch:**

```python
from infrastructure.orm.models import DepartmentRegistry, Graph, Run, TaskRecord
from application.services.career_ops_graph_contract import CAREER_OPS_STAGE_LABELS, CAREER_OPS_STAGE_TO_DEPARTMENT


def materialize_url_pipeline_tasks(*, company: Graph, run: Run, opportunity_external_key: str) -> list[TaskRecord]:
    organization = company.organization
    departments = {
        item.slug: item
        for item in DepartmentRegistry.objects.filter(
            organization=organization,
            slug__in=set(CAREER_OPS_STAGE_TO_DEPARTMENT.values()),
        )
    }
    tasks = []
    for stage_id in CAREER_OPS_URL_PIPELINE_TASK_STAGES:
        department_slug = CAREER_OPS_STAGE_TO_DEPARTMENT[stage_id]
        status = "waiting_for_decision" if stage_id == "stage_07_candidate_approval" else "pending"
        task, _ = TaskRecord.objects.update_or_create(
            organization=organization,
            external_key=f"career_ops:url_pipeline:{opportunity_external_key}:{stage_id}",
            defaults={
                "execution": run,
                "department": departments.get(department_slug),
                "source_node_id": stage_id,
                "title": f"CareerOps — {CAREER_OPS_STAGE_LABELS[stage_id]}",
                "status": status,
                "priority": "high" if stage_id in {"stage_07_candidate_approval", "stage_08_submission_tracking"} else "normal",
                "summary": f"{CAREER_OPS_STAGE_LABELS[stage_id]} for CareerOps opportunity {opportunity_external_key}.",
            },
        )
        tasks.append(task)
    return tasks
```

**Tests:**

- Creates exactly six tasks.
- Re-running with same opportunity key does not create duplicates.
- Approval task has `status == "waiting_for_decision"`.
- All tasks point at the latest `Run` after replay.

---

### Task 5: Orchestrate URL intake through scan/tracker/tasks

**Objective:** Implement the first functional `run_career_ops_url_pipeline` service.

**Files:**

- Modify: `backend/application/services/career_ops_pipeline.py`
- Test: `backend/tests/unit/services/test_career_ops_pipeline.py`

**Service behavior:**

1. Validate `company.organization` and `actor` are present.
2. Create `Run`.
3. Call `record_scanned_job`.
4. Call `ensure_opportunity_for_signal`.
5. Call `materialize_url_pipeline_tasks`.
6. Mark run `succeeded` with output IDs.
7. Return `CareerOpsPipelineResult`.

**Implementation sketch:**

```python
from django.db import transaction
from django.utils import timezone
from application.services.career_ops_opportunities import ensure_opportunity_for_signal, record_scanned_job
from application.services.career_ops_tasks import materialize_url_pipeline_tasks


def run_career_ops_url_pipeline(*, company: Graph, actor: User, posting: dict, idempotency_key: str) -> CareerOpsPipelineResult:
    if company.organization_id is None:
        raise ValueError("CareerOps URL pipeline requires an organization-scoped company.")
    if actor is None:
        raise ValueError("CareerOps URL pipeline requires an actor for Run.owner.")
    with transaction.atomic():
        run = create_career_ops_run(company=company, actor=actor, posting=posting, idempotency_key=idempotency_key)
        signal = record_scanned_job(company=company, user=actor, posting=posting)
        opportunity = ensure_opportunity_for_signal(signal=signal, user=actor)
        if opportunity is None:
            raise ValueError("CareerOps signal did not produce an opportunity.")
        tasks = materialize_url_pipeline_tasks(
            company=company,
            run=run,
            opportunity_external_key=opportunity.external_key,
        )
        run.status = "succeeded"
        run.ended_at = timezone.now()
        run.output_json = {
            "career_ops": {
                "signal_id": str(signal.id),
                "opportunity_id": str(opportunity.id),
                "task_ids": [str(task.id) for task in tasks],
                "external_side_effects_allowed": False,
            }
        }
        run.save(update_fields=["status", "ended_at", "output_json", "updated_at"] if hasattr(run, "updated_at") else ["status", "ended_at", "output_json"])
    return CareerOpsPipelineResult(
        run_id=str(run.id),
        signal_id=str(signal.id),
        opportunity_id=str(opportunity.id),
        task_ids=[str(task.id) for task in tasks],
    )
```

**Implementation correction:** `Run` currently does not have an `updated_at` field in the inspected model. Do not include `updated_at` in `Run.save(update_fields=...)` unless the model changes. Use:

```python
run.save(update_fields=["status", "ended_at", "output_json"])
```

**Tests:**

- `test_url_pipeline_materializes_native_forgegraph_records`
- `test_url_pipeline_replay_does_not_duplicate_signal_opportunity_or_tasks`
- `test_url_pipeline_run_records_no_external_side_effects`
- `test_url_pipeline_respects_recent_application_cooldown_metadata`

---

## PR 2 — Packet artifact, approval, and projection

### Task 6: Add CareerOps service catalog/engagement resolver

**Objective:** Ensure `ServiceDeliverable` rows can be created without manually pre-seeding catalog state.

**Files:**

- Create: `backend/application/services/career_ops_engagements.py`
- Test: `backend/tests/unit/services/test_career_ops_engagements.py`

**Model constraints:**

- `ServiceEngagement.catalog_item` is required.
- `ServiceEngagement.source_key` is unique per company when non-empty.
- `ServiceCatalogItem.slug` is unique per organization.

**Implementation behavior:**

- Get/create `ServiceCatalogItem(slug="career-ops-application-packet")`.
- Get/create `ServiceEngagement(source_key=f"career-ops:{company.id}:application-pipeline")`.
- Mark engagement `in_progress`, `customer_status="working"`.
- Required pack IDs includes `career_ops.v1`.

**Test behavior:**

- Resolver is idempotent.
- Catalog item has `status="active"` and `visibility="internal"` or `organization`.
- Engagement is tied to the target company and organization.

---

### Task 7: Add fake-safe artifact writer

**Objective:** Persist deterministic non-live CareerOps artifacts as `Asset`/`AssetVersion` and `ServiceDeliverable` records.

**Files:**

- Create: `backend/application/services/career_ops_artifacts.py`
- Test: `backend/tests/unit/services/test_career_ops_artifacts.py`

**Key rule:** Do **not** generate polished CV/cover content in this PR. Write deterministic fake-safe placeholder content that proves ownership, refs, and gates without risking real employer use.

**Deliverable types for this PR:**

- `job_liveness_receipt`
- `job_evaluation_report`
- `application_packet`

**Asset choices:**

- Use `Asset.asset_type="document"` for textual outputs because `Asset.asset_type` choices do not include CareerOps-specific strings.
- Put CareerOps-specific type in `Asset.source_key`, `Asset.metadata_json["career_ops"]["deliverable_type"]`, and `ServiceDeliverable.deliverable_type`.

**Implementation sketch:**

```python
import hashlib
import json
from infrastructure.orm.models import Asset, AssetVersion, ServiceDeliverable


def write_career_ops_deliverable(*, engagement, run, task, opportunity, deliverable_type: str, title: str, payload: dict) -> tuple[ServiceDeliverable, AssetVersion]:
    content = json.dumps(payload, sort_keys=True, indent=2)
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    source_key = f"career_ops:{opportunity.id}:{deliverable_type}"
    asset, _ = Asset.objects.get_or_create(
        company=engagement.company,
        source_key=source_key,
        defaults={
            "organization": engagement.organization,
            "title": title,
            "asset_type": "document",
            "origin_operation": run,
            "origin_task": task,
            "created_by_type": "system",
            "metadata_json": {},
        },
    )
    asset.organization = engagement.organization
    asset.title = title
    asset.asset_type = "document"
    asset.origin_operation = run
    asset.origin_task = task
    asset.metadata_json = {
        "career_ops": {
            "deliverable_type": deliverable_type,
            "opportunity_id": str(opportunity.id),
            "live_ready": False,
            "external_side_effects_allowed": False,
        }
    }
    asset.save()
    version = AssetVersion.objects.filter(asset=asset, content_hash=digest).first()
    if version is None:
        latest = AssetVersion.objects.filter(asset=asset).order_by("-version_number").values_list("version_number", flat=True).first() or 0
        version = AssetVersion.objects.create(
            asset=asset,
            version_number=latest + 1,
            content_uri=f"forgegraph://career-ops/{opportunity.id}/{deliverable_type}.json",
            content_hash=digest,
            mime_type="application/json",
            size_bytes=len(content.encode("utf-8")),
            provenance_json={"career_ops": payload},
        )
    deliverable, _ = ServiceDeliverable.objects.get_or_create(
        engagement=engagement,
        deliverable_type=deliverable_type,
        defaults={
            "organization": engagement.organization,
            "company": engagement.company,
            "title": title,
            "visibility": "operator",
        },
    )
    deliverable.artifact = asset
    deliverable.status = "in_review"
    deliverable.summary = f"CareerOps {deliverable_type} for {opportunity.title}."
    deliverable.metadata_json = {
        "career_ops": {
            "asset_version_id": str(version.id),
            "opportunity_id": str(opportunity.id),
            "live_ready": False,
        }
    }
    deliverable.save()
    return deliverable, version
```

**Tests:**

- Rewriting same payload reuses same `AssetVersion` by content hash.
- Changing payload creates next version number.
- Metadata contains `live_ready=False` and `external_side_effects_allowed=False`.
- `ServiceDeliverable.visibility == "operator"` until quality gates pass.

---

### Task 8: Add deterministic liveness/evaluation/packet stub builder

**Objective:** Produce safe structured payloads that simulate the pipeline without pretending to have real source-backed CV tailoring yet.

**Files:**

- Create: `backend/application/services/career_ops_packet_builder.py`
- Test: `backend/tests/unit/services/test_career_ops_packet_builder.py`

**Behavior:**

- Input: company, opportunity, posting metadata, base CV status.
- Output: three payload dictionaries for liveness, A-G evaluation, and packet manifest.
- If `cv_source` is missing, packet payload has `status="blocked"`, `blocked_reasons=["missing_cv_source"]`, and no tailored resume text.
- Evaluation includes Block G posting legitimacy status from available URL/provider fields.

**Minimum payload shape:**

```json
{
  "status": "blocked",
  "blocked_reasons": ["missing_cv_source"],
  "source_refs": [
    {"type": "opportunity", "id": "..."},
    {"type": "job_url", "url": "..."}
  ],
  "quality": {
    "live_ready": false,
    "requires_candidate_approval": true,
    "external_side_effects_allowed": false
  }
}
```

**Tests:**

- Missing base CV blocks packet.
- Payload never includes `live_ready=True` in this PR.
- Payload includes opportunity/job source refs.

---

### Task 9: Add exact-version approval decision writer

**Objective:** Create a pending human approval decision tied to exact packet asset-version IDs.

**Files:**

- Create: `backend/application/services/career_ops_approvals.py`
- Test: `backend/tests/unit/services/test_career_ops_approvals.py`

**DecisionRecord constraints:**

- `decision_type="human_approval"`
- `status="pending"`
- `external_key=f"career_ops:packet:{opportunity.id}:approval:{packet_version.id}"`
- `context_json` includes `opportunity_id`, `packet_asset_id`, `packet_asset_version_id`, and all deliverable/version refs.

**Implementation sketch:**

```python
from django.utils import timezone
from infrastructure.orm.models import DecisionRecord


def request_packet_approval(*, run, approval_task, opportunity, packet_version, deliverable_versions: list[dict]) -> DecisionRecord:
    decision, _ = DecisionRecord.objects.update_or_create(
        organization=run.organization,
        external_key=f"career_ops:packet:{opportunity.id}:approval:{packet_version.id}",
        defaults={
            "execution": run,
            "task": approval_task,
            "decision_type": "human_approval",
            "status": "pending",
            "requested_at": timezone.now(),
            "context_json": {
                "career_ops": {
                    "approval_type": "application_packet",
                    "opportunity_id": str(opportunity.id),
                    "packet_asset_id": str(packet_version.asset_id),
                    "packet_asset_version_id": str(packet_version.id),
                    "deliverable_versions": deliverable_versions,
                    "external_side_effects_allowed": False,
                }
            },
        },
    )
    approval_task.current_decision = decision
    approval_task.status = "waiting_for_decision"
    approval_task.save(update_fields=["current_decision", "status", "updated_at"])
    return decision
```

**Tests:**

- Decision references exact packet version.
- Replaying same packet version does not create duplicate decision.
- New packet version creates a new decision.
- Approval task points at `current_decision`.

---

### Task 10: Materialize pipeline snapshot projection

**Objective:** Make tracker state rebuildable from durable records.

**Files:**

- Create: `backend/application/services/career_ops_projections.py`
- Test: `backend/tests/unit/services/test_career_ops_projections.py`

**Projection type:**

```text
career_ops:pipeline_snapshot
```

**Projection content:**

```json
{
  "generated_at": "...",
  "opportunities": [
    {
      "id": "...",
      "external_key": "...",
      "employer_name": "...",
      "role_title": "...",
      "application_status": "approval_pending",
      "recent_application_cooldown": {"skip": false},
      "task_ids": ["..."],
      "decision_ids": ["..."],
      "deliverable_ids": ["..."],
      "next_action": "Review exact packet version before applying."
    }
  ],
  "counts": {"discovered": 1, "approval_pending": 1},
  "external_side_effects_allowed": false
}
```

**Implementation rule:** Use `StateProjection.objects.update_or_create(company=company, program=None, projection_type="career_ops:pipeline_snapshot")`.

**Tests:**

- Projection contains opportunity, tasks, decisions, deliverables.
- Projection can be rebuilt after data updates.
- Projection does not include raw prompt/model metadata or internal provenance blobs.

---

### Task 11: Extend orchestrator to create artifacts, approval, projection

**Objective:** Complete the P0 backend-native URL pipeline.

**Files:**

- Modify: `backend/application/services/career_ops_pipeline.py`
- Test: `backend/tests/unit/services/test_career_ops_pipeline.py`

**Flow extension:**

After tasks are materialized:

1. Resolve service engagement.
2. Build deterministic fake-safe payloads.
3. Write liveness/evaluation/packet deliverables.
4. Request exact-version packet approval.
5. Mark opportunity metadata `application_status="approval_pending"` unless blocked by missing CV/cooldown.
6. Materialize `career_ops:pipeline_snapshot`.
7. Put all IDs in `Run.output_json` and `CareerOpsPipelineResult`.

**Acceptance test:** `test_url_pipeline_end_to_end_materializes_native_contract` asserts all native surfaces exist.

---

## PR 3 — Management command smoke path

### Task 12: Add dry-run URL pipeline command

**Objective:** Let operators exercise the backend slice without writing API/UI first.

**Files:**

- Create: `backend/infrastructure/orm/management/commands/run_career_ops_url_pipeline.py`
- Test: `backend/tests/unit/management/test_run_career_ops_url_pipeline.py`

**Command shape:**

```bash
uv run python manage.py run_career_ops_url_pipeline \
  --company-id <uuid> \
  --user-id <uuid> \
  --title "Senior Product Engineer" \
  --company-name "Acme AI" \
  --url "https://jobs.example.com/acme/senior-product-engineer" \
  --location "Remote" \
  --provider manual_url \
  --idempotency-key "manual:test" \
  --json
```

**Output shape:**

```json
{
  "status": "ok",
  "run_id": "...",
  "signal_id": "...",
  "opportunity_id": "...",
  "task_ids": ["..."],
  "decision_id": "...",
  "deliverable_ids": ["..."],
  "projection_id": "...",
  "external_side_effects_allowed": false,
  "blocked_reasons": ["missing_cv_source"]
}
```

**Tests:**

- Command returns JSON.
- Command creates native records.
- Command rejects missing company/user.
- Command never allows external side effects.

---

## PR 4 — Pre-live quality/readiness foundation

### Task 13: Add fail-closed quality gate service

**Objective:** Prevent generated packets from being mistaken for employer-ready output.

**Files:**

- Create: `backend/application/services/career_ops_quality_gates.py`
- Test: `backend/tests/unit/services/test_career_ops_quality_gates.py`

**Gates for first slice:**

- `base_cv_present`
- `source_refs_present`
- `no_internal_leakage`
- `employer_identity_matches`
- `exact_version_approval_present`
- `side_effect_guard_disabled`

**Default result:** blocked.

**Data class shape:**

```python
@dataclass(frozen=True, slots=True)
class CareerOpsReadinessResult:
    status: str  # "blocked" | "ready"
    checks: dict[str, str]
    blockers: list[str]
    live_send_allowed: bool = False
```

**Tests:**

- Missing base CV blocks.
- Missing exact approval blocks.
- Live send disabled blocks external send even if artifact checks pass.
- Internal leakage tokens such as `prompt`, `metadata_json`, `provenance_json`, `Hermes`, `ForgeGraph implementation` block customer-facing content.

---

### Task 14: Add readiness command

**Objective:** Provide a read-only pre-live check that fails closed.

**Files:**

- Create: `backend/infrastructure/orm/management/commands/check_career_ops_live_readiness.py`
- Test: `backend/tests/unit/management/test_check_career_ops_live_readiness.py`

**Command shape:**

```bash
uv run python manage.py check_career_ops_live_readiness \
  --company-id <uuid> \
  --packet-version-id <uuid> \
  --json
```

**Output shape:**

```json
{
  "status": "blocked",
  "company_id": "...",
  "packet_version_id": "...",
  "checks": {
    "base_cv_present": "blocked",
    "source_refs_present": "pass",
    "no_internal_leakage": "pass",
    "employer_identity_matches": "pass",
    "exact_version_approval_present": "blocked",
    "side_effect_guard_disabled": "pass"
  },
  "live_send_allowed": false
}
```

---

## PR 5 — Daily discovery handler shape

### Task 15: Add daily discovery service wrapper

**Objective:** Prepare for daily 10:00 AM backend-owned automation while preserving cron as a wake-up adapter only.

**Files:**

- Create: `backend/application/services/career_ops_daily_discovery.py`
- Test: `backend/tests/unit/services/test_career_ops_daily_discovery.py`

**Function shape:**

```python
def run_career_ops_daily_discovery(
    *,
    company: Graph,
    actor: User,
    postings: list[dict],
    idempotency_key: str,
    max_new_options: int = 10,
    max_evaluations: int = 5,
    cooldown_days: int = CAREER_OPS_APPLIED_COOLDOWN_DAYS,
) -> dict[str, Any]:
    ...
```

**Behavior:**

- Does not fetch the web yet; accepts postings passed by test/adapter.
- Requires base CV/profile before packet generation; otherwise creates blocked setup tasks.
- Runs `run_career_ops_url_pipeline` for at most `max_evaluations` postings.
- Respects cooldown metadata from `career_ops_opportunities.py`.
- Writes/updates `pipeline_health_report` deliverable or `StateProjection` summary.
- Never submits applications.

**Tests:**

- Empty postings returns quiet/no-op summary.
- More than `max_evaluations` postings only pipelines top N.
- Recent application cooldown prevents packet readiness.
- Missing base CV creates blocked setup summary.

### Task 16: Optional generic automation registration

**Objective:** If generic ForgeGraph automations already exist by the time this PR starts, register `career_ops.daily_discovery`; otherwise keep this as a service-only handler and document external cron as a temporary wake-up adapter.

**Files if generic automations exist:**

- Modify relevant automation handler registry file discovered at implementation time.
- Test relevant automation handler registry tests.

**Do not:** add a CareerOps-specific scheduler table.

---

## API/UI deferral note

The first implementation should be backend/command only. Add API after the native state contract is proven.

When API is added later, preferred endpoint shape:

```text
POST /api/company-ops/career-ops/url-pipeline
GET  /api/company-ops/career-ops/pipeline-snapshot?company_id=<uuid>
POST /api/company-ops/career-ops/packets/<packet_version_id>/approval
GET  /api/company-ops/career-ops/live-readiness?company_id=<uuid>&packet_version_id=<uuid>
```

Every POST must require:

- auth,
- company access,
- `Idempotency-Key`,
- route-security-matrix coverage for `/api` and `/api/v1` if that repo convention applies.

---

## Verification commands

### Focused CareerOps backend gate

```bash
cd backend
FORGEGRAPH_ENV_FILE= DEBUG=1 SECRET_KEY=*** USE_SQLITE=true \
  USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 \
  SQLITE_DB_PATH=.hermes/career_ops_test.sqlite3 \
  UV_PROJECT_ENVIRONMENT=.venv-test-career-ops \
  uv run --group dev pytest \
    tests/unit/services/test_career_ops_graph_contract.py \
    tests/unit/services/test_career_ops_opportunities.py \
    tests/unit/services/test_career_ops_pipeline.py \
    tests/unit/services/test_career_ops_tasks.py \
    tests/unit/services/test_career_ops_engagements.py \
    tests/unit/services/test_career_ops_artifacts.py \
    tests/unit/services/test_career_ops_approvals.py \
    tests/unit/services/test_career_ops_projections.py \
    tests/unit/services/test_career_ops_quality_gates.py \
    tests/unit/management/test_run_career_ops_url_pipeline.py \
    tests/unit/management/test_check_career_ops_live_readiness.py \
    -q
```

### Ruff

```bash
cd backend
UV_PROJECT_ENVIRONMENT=.venv-test-career-ops uv run ruff check \
  application/services/career_ops_graph_contract.py \
  application/services/career_ops_opportunities.py \
  application/services/career_ops_pipeline.py \
  application/services/career_ops_tasks.py \
  application/services/career_ops_engagements.py \
  application/services/career_ops_artifacts.py \
  application/services/career_ops_packet_builder.py \
  application/services/career_ops_approvals.py \
  application/services/career_ops_projections.py \
  application/services/career_ops_quality_gates.py \
  application/services/career_ops_daily_discovery.py \
  infrastructure/orm/management/commands/run_career_ops_url_pipeline.py \
  infrastructure/orm/management/commands/check_career_ops_live_readiness.py \
  tests/unit/services/test_career_ops_*.py \
  tests/unit/management/test_*career_ops*.py
```

### Django check

```bash
cd backend
FORGEGRAPH_ENV_FILE= DEBUG=1 SECRET_KEY=*** USE_SQLITE=true \
  USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 \
  SQLITE_DB_PATH=.hermes/career_ops_check.sqlite3 \
  UV_PROJECT_ENVIRONMENT=.venv-test-career-ops \
  uv run python manage.py check
```

### Migration check

Run if a PR unexpectedly touches models:

```bash
cd backend
FORGEGRAPH_ENV_FILE= DEBUG=1 SECRET_KEY=*** USE_SQLITE=true \
  USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 \
  SQLITE_DB_PATH=.hermes/career_ops_migrations.sqlite3 \
  UV_PROJECT_ENVIRONMENT=.venv-test-career-ops \
  uv run python manage.py makemigrations --check --dry-run
```

Expected for PR 1/2/3/4/5: no model changes, no migrations.

---

## Acceptance criteria

The implementation is acceptable when all of these are true:

- A URL/JD pipeline creates a `Run`.
- It creates/replays one `CompanySignal` and one `CompanyOpportunity` for the normalized job.
- It creates/replays stage `TaskRecord` rows for scan, liveness, evaluation, packet, approval, and tracking.
- It creates versioned fake-safe artifacts for liveness/evaluation/packet.
- It creates a pending `DecisionRecord` for the exact packet `AssetVersion`.
- It materializes `career_ops:pipeline_snapshot` as a `StateProjection` from durable records.
- Missing base CV blocks live readiness.
- Recent same employer+role application within 30 days blocks packet readiness.
- No code path submits applications, sends email, fills forms, or marks `external_side_effects_allowed=true`.
- Focused pytest, ruff, and `manage.py check` pass under the Windows/Git-Bash-safe env.

---

## Risks and mitigations

1. **Run idempotency is not native yet.**
   - Mitigation: keep run replay out of scope, but make all downstream durable records idempotent by stable external keys. Add generic automation/idempotency later.

2. **`ServiceDeliverable` requires `ServiceEngagement.catalog_item`.**
   - Mitigation: PR 2 includes an engagement resolver using `ServiceCatalogItem` and `ServiceEngagement` source keys.

3. **Fake-safe packet could be misread as employer-ready.**
   - Mitigation: metadata and readiness gates always set `live_ready=false`, `visibility="operator"`, and `external_side_effects_allowed=false` until pre-live gates pass.

4. **Task external keys are globally unique per organization.**
   - Mitigation: include opportunity external key and stage ID; update existing tasks on replay.

5. **Automation schedule could drift into Hermes ownership.**
   - Mitigation: PR 5 registers a backend handler shape only; Hermes/cron remains wake-up adapter.

6. **Too much scope in one PR.**
   - Mitigation: keep PR 1 state-only, PR 2 artifacts/approval/projection, PR 3 command, PR 4 readiness, PR 5 daily discovery.

---

## Open questions for implementation review

1. Should repeated URL pipeline calls create a new `Run` every time while replaying downstream records, or should we add a generic run idempotency primitive before PR 1? Recommendation: avoid migration now; replay downstream records.
2. Should CareerOps command require a real `User` for automation runs, or should the future automation layer supply a system actor? Recommendation: PR 1 requires `actor`; PR 5 can define system actor policy.
3. Should `application_packet` be stored as JSON first or rendered HTML immediately? Recommendation: JSON first for source/gate tests; HTML/PDF after quality gates.
4. Should API endpoints be part of PR 3? Recommendation: no; command first keeps backend contract stable.

---

## Suggested first Codex prompt after approval

```text
You are implementing PR 1 from .hermes/plans/2026-06-16_204843-career-ops-native-url-pipeline-implementation.md.

Scope only:
- backend/application/services/career_ops_pipeline.py
- backend/application/services/career_ops_tasks.py
- backend/tests/unit/services/test_career_ops_pipeline.py
- backend/tests/unit/services/test_career_ops_tasks.py

Do not implement artifacts, approvals, projections, management commands, daily discovery, API, UI, migrations, or live side effects.

Acceptance:
- URL/JD pipeline creates a Run, CompanySignal, CompanyOpportunity, and six TaskRecord rows.
- Replaying same posting does not duplicate signal/opportunity/tasks.
- Run input/output explicitly has external_side_effects_allowed=false.
- Use existing career_ops_opportunities.py and career_ops_graph_contract.py.
- Verify with focused pytest + ruff + manage.py check commands from the plan.
```
