# CareerOps Outcome Tracking PR 1 Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Add a ForgeGraph-native CareerOps outcome tracking slice inspired by `MadsLorentzen/ai-job-search` `/outcome`: record application/interview/rejection/offer/no-response outcomes against `CompanyOpportunity`, persist an exact outcome deliverable, update backend-owned pipeline projections, and expose a management command for operator use.

**Architecture:** Keep durable state in existing ForgeGraph backend primitives. Do **not** add a CSV, local markdown archive, or new application table in PR 1. Store the latest normalized outcome in `CompanyOpportunity.metadata_json["career_ops"]`, append event history in the same metadata block, persist an `application_outcome_report` as `ServiceDeliverable`/`AssetVersion`, create a backend `Run` receipt, and rematerialize `StateProjection` through `materialize_career_ops_pipeline_projection()`.

**Tech Stack:** Django ORM, existing `CompanyOpportunity`, `Run`, `ServiceDeliverable`, `Asset`, `AssetVersion`, `StateProjection`, pytest, Django management command, existing CareerOps services.

---

## Current Context

Existing CareerOps files to reuse:

- `backend/application/services/career_ops_opportunities.py`
  - Existing `update_application_status()` updates `application_status`, `applied_at`, and opportunity `status`.
  - Existing statuses already include `applied`, `rejected`, `discarded`, `skip` behavior.
- `backend/application/services/career_ops_tracker.py`
  - Existing canonical statuses: `evaluated`, `applied`, `responded`, `interview`, `offer`, `rejected`, `discarded`, `skip`.
  - Existing `normalize_career_ops_status()` and integrity checks.
- `backend/application/services/career_ops_artifacts.py`
  - Existing `write_career_ops_deliverable()` can persist JSON deliverables against an opportunity and asset version.
- `backend/application/services/career_ops_engagements.py`
  - Existing `ensure_career_ops_application_engagement()` owns CareerOps application deliverables.
- `backend/application/services/career_ops_projections.py`
  - Existing pipeline projection rows should be extended with outcome fields.
- `backend/application/services/career_ops_pipeline.py`
  - Existing pipeline already marks `approval_pending` and updates projection.
- Management command pattern:
  - `backend/infrastructure/orm/management/commands/build_career_ops_application_packet.py`
  - Test: `backend/tests/unit/management/test_build_career_ops_application_packet.py`

Reference repo idea being ported:

- `MadsLorentzen/ai-job-search` `/outcome` writes outcome status, interview stages, notes, and calibration data.
- ForgeGraph adaptation: backend-owned durable state only; no local `job_search_tracker.csv` or `documents/applications/*` source of truth.

---

## Scope

### In PR 1

Implement the minimum useful outcome loop:

1. Service function to record an outcome event for an existing CareerOps opportunity.
2. Exact JSON deliverable: `application_outcome_report`.
3. Opportunity metadata update:
   - `application_status`
   - `tracker_status`
   - `outcome_status`
   - `outcome_history`
   - `interview_stages`
   - `last_outcome_note`
   - `resolved_at` where applicable
   - `external_side_effects_allowed: false`
4. Pipeline projection includes outcome summary and next action.
5. Management command for operator usage.
6. Unit tests.

### Not in PR 1

- No public API endpoint.
- No frontend UI.
- No automatic calibration rewrite of scoring framework.
- No auto-apply or external side effects.
- No new DB table unless implementation uncovers an existing constraint that makes JSON metadata insufficient.
- No portal scanning changes.
- No WhatsApp delivery changes.

---

## Outcome Contract

Create a small contract in `backend/application/services/career_ops_outcomes.py`.

Supported outcome statuses for PR 1:

```python
CAREER_OPS_OUTCOME_STATUSES = {
    "in_progress",
    "applied",
    "responded",
    "interview",
    "offer",
    "hired",
    "offer_declined",
    "rejected",
    "no_response",
    "withdrawn",
}
```

Map to existing opportunity `status`:

```python
OPPORTUNITY_STATUS_BY_OUTCOME = {
    "in_progress": "qualified",
    "applied": "converted",
    "responded": "follow_up",
    "interview": "follow_up",
    "offer": "follow_up",
    "hired": "converted",
    "offer_declined": "lost",
    "rejected": "lost",
    "no_response": "lost",
    "withdrawn": "lost",
}
```

Map to tracker/integrity status:

```python
TRACKER_STATUS_BY_OUTCOME = {
    "in_progress": "applied",
    "applied": "applied",
    "responded": "responded",
    "interview": "interview",
    "offer": "offer",
    "hired": "offer",
    "offer_declined": "rejected",
    "rejected": "rejected",
    "no_response": "discarded",
    "withdrawn": "discarded",
}
```

This avoids expanding `career_ops_tracker.CANONICAL_STATUSES` in PR 1. The richer `outcome_status` remains in CareerOps metadata while integrity uses existing tracker canonical values.

Outcome payload shape:

```json
{
  "format": "career_ops_application_outcome_v1",
  "opportunity_id": "...",
  "employer_name": "...",
  "role_title": "...",
  "job_url": "...",
  "outcome_status": "interview",
  "tracker_status": "interview",
  "stage": "technical_interview",
  "stage_status": "scheduled",
  "event_date": "2026-07-07",
  "resolved_at": null,
  "notes": "Phone screen scheduled for next week.",
  "feedback": "",
  "interview_stages": [
    {
      "stage": "phone_screen",
      "status": "completed",
      "date": "2026-07-06",
      "notes": "..."
    }
  ],
  "next_action": "Prepare for technical_interview.",
  "calibration_signal": {
    "resolved": false,
    "positive_signal": true,
    "negative_signal": false,
    "interview_reached": true,
    "offer_reached": false
  },
  "external_side_effects_allowed": false
}
```

---

## Task 1: Add Failing Service Tests for Outcome Recording

**Objective:** Define expected behavior before implementation.

**Files:**

- Create: `backend/tests/unit/services/test_career_ops_outcomes.py`
- Uses existing helpers/patterns from:
  - `backend/tests/unit/services/test_career_ops_pipeline.py`
  - `backend/tests/unit/management/test_build_career_ops_application_packet.py`

**Step 1: Create test file with helpers**

Add helpers similar to existing CareerOps tests:

```python
from __future__ import annotations

from typing import cast

import pytest

from application.services.career_ops_opportunities import ensure_opportunity_for_signal, record_scanned_job
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import Graph, GraphVersion, ServiceDeliverable, StateProjection, User

pytestmark = pytest.mark.django_db


def _create_company(user: User) -> Graph:
    ensure_default_organization(user)
    organization = user.default_organization
    assert organization is not None
    company = cast(Graph, Graph.objects.create(owner=user, organization=organization, name="CareerOps Outcome Co"))
    GraphVersion.objects.create(graph=company, version=1, graph_json={"nodes": [], "edges": [], "metadata": {}})
    return company


def _opportunity(company: Graph, user: User):
    signal = record_scanned_job(
        company=company,
        user=user,
        posting={
            "title": "Backend Engineer",
            "company": "Acme AI",
            "url": "https://jobs.example.test/acme/backend",
            "location": "Remote",
            "description": "Python backend role.",
            "provider": "fixture",
        },
    )
    opportunity = ensure_opportunity_for_signal(signal=signal, user=user)
    assert opportunity is not None
    return opportunity
```

**Step 2: Add core outcome test**

```python
def test_record_career_ops_outcome_updates_opportunity_and_persists_deliverable(user: User) -> None:
    from application.services.career_ops_outcomes import record_career_ops_outcome

    company = _create_company(user)
    opportunity = _opportunity(company, user)

    result = record_career_ops_outcome(
        company=company,
        actor=user,
        opportunity=opportunity,
        outcome_status="interview",
        stage="phone_screen",
        stage_status="scheduled",
        notes="Recruiter screen booked for Friday.",
        feedback="",
        event_date="2026-07-07",
        idempotency_key="outcome:test:interview",
    )

    opportunity.refresh_from_db()
    career_ops = opportunity.metadata_json["career_ops"]
    assert result.outcome_asset_version_id
    assert result.projection_id
    assert career_ops["outcome_status"] == "interview"
    assert career_ops["tracker_status"] == "interview"
    assert career_ops["application_status"] == "interview"
    assert career_ops["external_side_effects_allowed"] is False
    assert career_ops["interview_stages"][0]["stage"] == "phone_screen"
    assert career_ops["outcome_history"][0]["outcome_status"] == "interview"

    deliverable = ServiceDeliverable.objects.get(company=company, deliverable_type="application_outcome_report")
    payload = deliverable.artifact.versions.latest("created_at").provenance_json["career_ops"]
    assert payload["format"] == "career_ops_application_outcome_v1"
    assert payload["external_side_effects_allowed"] is False
    assert payload["calibration_signal"]["interview_reached"] is True
    assert StateProjection.objects.get(id=result.projection_id).projection_type == "career_ops:pipeline_snapshot"
```

**Step 3: Add append/idempotency test**

```python
def test_record_career_ops_outcome_appends_history_without_duplicate_for_same_idempotency_key(user: User) -> None:
    from application.services.career_ops_outcomes import record_career_ops_outcome

    company = _create_company(user)
    opportunity = _opportunity(company, user)

    first = record_career_ops_outcome(
        company=company,
        actor=user,
        opportunity=opportunity,
        outcome_status="interview",
        stage="phone_screen",
        stage_status="scheduled",
        notes="First note.",
        idempotency_key="outcome:test:same",
    )
    second = record_career_ops_outcome(
        company=company,
        actor=user,
        opportunity=opportunity,
        outcome_status="interview",
        stage="phone_screen",
        stage_status="scheduled",
        notes="First note.",
        idempotency_key="outcome:test:same",
    )

    opportunity.refresh_from_db()
    history = opportunity.metadata_json["career_ops"]["outcome_history"]
    assert first.run_id != second.run_id
    assert len(history) == 1
```

**Step 4: Add resolution mapping test**

```python
def test_record_career_ops_outcome_maps_rejection_to_lost_and_resolved_metadata(user: User) -> None:
    from application.services.career_ops_outcomes import record_career_ops_outcome

    company = _create_company(user)
    opportunity = _opportunity(company, user)

    record_career_ops_outcome(
        company=company,
        actor=user,
        opportunity=opportunity,
        outcome_status="rejected",
        notes="Rejected after technical screen.",
        feedback="They wanted deeper Kubernetes experience.",
        event_date="2026-07-07",
        idempotency_key="outcome:test:rejected",
    )

    opportunity.refresh_from_db()
    career_ops = opportunity.metadata_json["career_ops"]
    assert opportunity.status == "lost"
    assert career_ops["outcome_status"] == "rejected"
    assert career_ops["tracker_status"] == "rejected"
    assert career_ops["resolved_at"] == "2026-07-07"
    assert career_ops["calibration_signal"]["negative_signal"] is True
```

**Step 5: Run test to verify failure**

Run from `backend/`:

```bash
FORGEGRAPH_ENV_FILE= DEBUG=0 SECRET_KEY=*** USE_SQLITE=true USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 SQLITE_DB_PATH=.hermes/career_ops_outcomes_test.sqlite3 UV_PROJECT_ENVIRONMENT=.venv-test-career-ops-e2e uv run --group dev pytest tests/unit/services/test_career_ops_outcomes.py -q --tb=short --disable-warnings
```

Expected: FAIL because `application.services.career_ops_outcomes` does not exist.

---

## Task 2: Implement `career_ops_outcomes.py`

**Objective:** Add the service that records outcome events using backend-owned state.

**Files:**

- Create: `backend/application/services/career_ops_outcomes.py`

**Step 1: Add dataclass and constants**

```python
"""CareerOps application outcome recording and calibration signals."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.utils import timezone

from application.services.career_ops_artifacts import write_career_ops_deliverable
from application.services.career_ops_engagements import ensure_career_ops_application_engagement
from application.services.career_ops_pipeline import ensure_career_ops_graph_version
from application.services.career_ops_projections import materialize_career_ops_pipeline_projection
from infrastructure.orm.models import CompanyOpportunity, Graph, Run, User

CAREER_OPS_OUTCOME_STATUSES = {
    "in_progress",
    "applied",
    "responded",
    "interview",
    "offer",
    "hired",
    "offer_declined",
    "rejected",
    "no_response",
    "withdrawn",
}

RESOLVED_OUTCOME_STATUSES = {"hired", "offer_declined", "rejected", "no_response", "withdrawn"}

OPPORTUNITY_STATUS_BY_OUTCOME = {
    "in_progress": "qualified",
    "applied": "converted",
    "responded": "follow_up",
    "interview": "follow_up",
    "offer": "follow_up",
    "hired": "converted",
    "offer_declined": "lost",
    "rejected": "lost",
    "no_response": "lost",
    "withdrawn": "lost",
}

TRACKER_STATUS_BY_OUTCOME = {
    "in_progress": "applied",
    "applied": "applied",
    "responded": "responded",
    "interview": "interview",
    "offer": "offer",
    "hired": "offer",
    "offer_declined": "rejected",
    "rejected": "rejected",
    "no_response": "discarded",
    "withdrawn": "discarded",
}


@dataclass(frozen=True, slots=True)
class CareerOpsOutcomeResult:
    run_id: str
    opportunity_id: str
    outcome_deliverable_id: str
    outcome_asset_version_id: str
    projection_id: str
    external_side_effects_allowed: bool = False
```

**Step 2: Add helper functions**

```python
def _career_ops_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    career_ops = (metadata or {}).get("career_ops", {})
    return dict(career_ops) if isinstance(career_ops, dict) else {}


def _event_date(value: str | None) -> str:
    return str(value or timezone.now().date().isoformat())


def _calibration_signal(outcome_status: str, stage: str) -> dict[str, Any]:
    interview_reached = outcome_status in {"interview", "offer", "hired"} or bool(stage)
    offer_reached = outcome_status in {"offer", "hired", "offer_declined"}
    resolved = outcome_status in RESOLVED_OUTCOME_STATUSES
    return {
        "resolved": resolved,
        "positive_signal": outcome_status in {"interview", "offer", "hired"} or interview_reached,
        "negative_signal": outcome_status in {"rejected", "no_response", "withdrawn", "offer_declined"},
        "interview_reached": interview_reached,
        "offer_reached": offer_reached,
    }


def _next_action_for_outcome(outcome_status: str, stage: str) -> str:
    if outcome_status == "interview":
        return f"Prepare for {stage}." if stage else "Prepare for the interview stage."
    if outcome_status == "responded":
        return "Reply to employer/recruiter and clarify next step."
    if outcome_status == "offer":
        return "Prepare offer evaluation and negotiation notes."
    if outcome_status == "hired":
        return "Archive accepted offer and update CareerOps calibration."
    if outcome_status in {"rejected", "no_response", "withdrawn", "offer_declined"}:
        return "Archive outcome and use it for future calibration."
    if outcome_status == "applied":
        return "Wait for response or schedule follow-up."
    return "Keep application in progress."
```

**Step 3: Implement main service**

```python
def record_career_ops_outcome(
    *,
    company: Graph,
    actor: User,
    opportunity: CompanyOpportunity,
    outcome_status: str,
    idempotency_key: str,
    stage: str = "",
    stage_status: str = "",
    notes: str = "",
    feedback: str = "",
    event_date: str | None = None,
) -> CareerOpsOutcomeResult:
    """Record a CareerOps application outcome without external side effects."""

    if opportunity.company_id != company.id:
        raise ValueError("CareerOps outcome opportunity must belong to the target company.")
    normalized_status = outcome_status.strip().casefold()
    if normalized_status not in CAREER_OPS_OUTCOME_STATUSES:
        raise ValueError(f"Unsupported CareerOps outcome status: {outcome_status}")
    if not idempotency_key.strip():
        raise ValueError("CareerOps outcome requires an idempotency key.")

    with transaction.atomic():
        graph_version = ensure_career_ops_graph_version(company=company)
        now = timezone.now()
        run = Run.objects.create(
            owner=actor,
            organization=company.organization,
            graph_version=graph_version,
            status="running",
            started_at=now,
            last_progress_at=now,
            recovery_policy="resume",
            input_json={
                "career_ops": {
                    "pipeline": "application_outcome_recording",
                    "idempotency_key": idempotency_key,
                    "opportunity_id": str(opportunity.id),
                    "outcome_status": normalized_status,
                    "external_side_effects_allowed": False,
                }
            },
        )
        career_ops = _career_ops_metadata(opportunity.metadata_json)
        event_date_value = _event_date(event_date)
        tracker_status = TRACKER_STATUS_BY_OUTCOME[normalized_status]
        stage_event = {
            "stage": stage.strip(),
            "status": stage_status.strip(),
            "date": event_date_value,
            "notes": notes.strip(),
        }
        outcome_event = {
            "idempotency_key": idempotency_key,
            "outcome_status": normalized_status,
            "tracker_status": tracker_status,
            "stage": stage.strip(),
            "stage_status": stage_status.strip(),
            "event_date": event_date_value,
            "notes": notes.strip(),
            "feedback": feedback.strip(),
            "recorded_at": now.isoformat(),
            "run_id": str(run.id),
        }

        history = list(career_ops.get("outcome_history") or [])
        if not any(item.get("idempotency_key") == idempotency_key for item in history if isinstance(item, dict)):
            history.append(outcome_event)

        interview_stages = list(career_ops.get("interview_stages") or [])
        if stage_event["stage"] and not any(
            isinstance(item, dict)
            and item.get("stage") == stage_event["stage"]
            and item.get("date") == stage_event["date"]
            for item in interview_stages
        ):
            interview_stages.append(stage_event)

        calibration_signal = _calibration_signal(normalized_status, stage_event["stage"])
        payload = {
            "format": "career_ops_application_outcome_v1",
            "opportunity_id": str(opportunity.id),
            "employer_name": career_ops.get("employer_name", opportunity.contact_alias),
            "role_title": career_ops.get("role_title", opportunity.title),
            "job_url": career_ops.get("job_url", ""),
            "outcome_status": normalized_status,
            "tracker_status": tracker_status,
            "stage": stage_event["stage"],
            "stage_status": stage_event["status"],
            "event_date": event_date_value,
            "resolved_at": event_date_value if normalized_status in RESOLVED_OUTCOME_STATUSES else None,
            "notes": notes.strip(),
            "feedback": feedback.strip(),
            "interview_stages": interview_stages,
            "next_action": _next_action_for_outcome(normalized_status, stage_event["stage"]),
            "calibration_signal": calibration_signal,
            "external_side_effects_allowed": False,
        }

        career_ops.update(
            {
                "application_status": normalized_status,
                "tracker_status": tracker_status,
                "outcome_status": normalized_status,
                "last_outcome_note": notes.strip(),
                "last_outcome_feedback": feedback.strip(),
                "last_outcome_at": event_date_value,
                "outcome_history": history,
                "interview_stages": interview_stages,
                "calibration_signal": calibration_signal,
                "external_side_effects_allowed": False,
            }
        )
        if normalized_status in RESOLVED_OUTCOME_STATUSES:
            career_ops["resolved_at"] = event_date_value

        opportunity.status = OPPORTUNITY_STATUS_BY_OUTCOME[normalized_status]
        opportunity.next_action = payload["next_action"]
        opportunity.metadata_json = {**(opportunity.metadata_json or {}), "career_ops": career_ops}
        opportunity.save(update_fields=["status", "next_action", "metadata_json", "updated_at"])

        engagement = ensure_career_ops_application_engagement(company=company, actor=actor)
        deliverable, version = write_career_ops_deliverable(
            engagement=engagement,
            run=run,
            task=None,
            opportunity=opportunity,
            deliverable_type="application_outcome_report",
            title=f"Application outcome — {opportunity.title}",
            payload=payload,
        )
        projection = materialize_career_ops_pipeline_projection(company=company)
        run.status = "succeeded"
        run.ended_at = timezone.now()
        run.output_json = {
            "career_ops": {
                "opportunity_id": str(opportunity.id),
                "outcome_deliverable_id": str(deliverable.id),
                "outcome_asset_version_id": str(version.id),
                "projection_id": str(projection.id),
                "external_side_effects_allowed": False,
            }
        }
        run.save(update_fields=["status", "ended_at", "output_json"])

    return CareerOpsOutcomeResult(
        run_id=str(run.id),
        opportunity_id=str(opportunity.id),
        outcome_deliverable_id=str(deliverable.id),
        outcome_asset_version_id=str(version.id),
        projection_id=str(projection.id),
    )
```

**Step 4: Run service tests**

```bash
FORGEGRAPH_ENV_FILE= DEBUG=0 SECRET_KEY=*** USE_SQLITE=true USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 SQLITE_DB_PATH=.hermes/career_ops_outcomes_test.sqlite3 UV_PROJECT_ENVIRONMENT=.venv-test-career-ops-e2e uv run --group dev pytest tests/unit/services/test_career_ops_outcomes.py -q --tb=short --disable-warnings
```

Expected: PASS.

---

## Task 3: Extend Pipeline Projection with Outcome Fields

**Objective:** Make recorded outcomes visible in `career_ops:pipeline_snapshot`.

**Files:**

- Modify: `backend/application/services/career_ops_projections.py:55-85`
- Test: `backend/tests/unit/services/test_career_ops_outcomes.py`

**Step 1: Add projection assertions to service test**

Append to `test_record_career_ops_outcome_updates_opportunity_and_persists_deliverable`:

```python
projection = StateProjection.objects.get(id=result.projection_id)
row = projection.json_state["opportunities"][0]
assert row["outcome_status"] == "interview"
assert row["tracker_status"] == "interview"
assert row["last_outcome_note"] == "Recruiter screen booked for Friday."
assert row["interview_stage_count"] == 1
```

Run test. Expected: FAIL because projection row does not include these keys.

**Step 2: Modify `_opportunity_row()`**

In `backend/application/services/career_ops_projections.py`, extend the returned dict:

```python
    return {
        "id": str(opportunity.id),
        "external_key": opportunity.external_key,
        "employer_name": career_ops.get("employer_name", ""),
        "role_title": career_ops.get("role_title", ""),
        "application_status": career_ops.get("application_status", "discovered"),
        "tracker_status": career_ops.get("tracker_status", career_ops.get("application_status", "discovered")),
        "outcome_status": career_ops.get("outcome_status", ""),
        "resolved_at": career_ops.get("resolved_at"),
        "last_outcome_at": career_ops.get("last_outcome_at"),
        "last_outcome_note": career_ops.get("last_outcome_note", ""),
        "interview_stage_count": len(career_ops.get("interview_stages") or []),
        "calibration_signal": career_ops.get("calibration_signal", {}),
        "recent_application_cooldown": career_ops.get("recent_application_cooldown", {"skip": False}),
        "task_ids": [str(task.id) for task in tasks],
        "decision_ids": [str(decision.id) for decision in decisions],
        "deliverable_ids": [str(deliverable.id) for deliverable in deliverables],
        "next_action": _next_action(career_ops),
    }
```

**Step 3: Update `_next_action()`**

Replace the function body with outcome-aware logic:

```python
def _next_action(career_ops: dict[str, Any]) -> str:
    if career_ops.get("recent_application_cooldown", {}).get("skip"):
        return "Skip due to recent same-employer same-role application cooldown."
    if career_ops.get("next_action"):
        return str(career_ops["next_action"])
    outcome_status = career_ops.get("outcome_status")
    if outcome_status == "interview":
        return "Prepare for the interview stage."
    if outcome_status == "offer":
        return "Prepare offer evaluation and negotiation notes."
    if outcome_status in {"rejected", "no_response", "withdrawn", "offer_declined"}:
        return "Archive outcome and use it for future calibration."
    if career_ops.get("application_status") == "approval_pending":
        return "Review exact packet version before applying."
    return "Run CareerOps review."
```

Note: in Task 2 the service sets `opportunity.next_action`, not `career_ops["next_action"]`; either add `career_ops["next_action"] = payload["next_action"]` in Task 2 or make projection read `opportunity.next_action`. Prefer adding `career_ops["next_action"]` in Task 2 for consistent metadata snapshots.

**Step 4: Run tests**

```bash
FORGEGRAPH_ENV_FILE= DEBUG=0 SECRET_KEY=*** USE_SQLITE=true USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 SQLITE_DB_PATH=.hermes/career_ops_outcomes_test.sqlite3 UV_PROJECT_ENVIRONMENT=.venv-test-career-ops-e2e uv run --group dev pytest tests/unit/services/test_career_ops_outcomes.py tests/unit/services/test_career_ops_projections.py -q --tb=short --disable-warnings
```

Expected: PASS.

---

## Task 4: Add Management Command `record_career_ops_outcome`

**Objective:** Provide an operator-facing command to record outcomes without writing ad hoc shell scripts.

**Files:**

- Create: `backend/infrastructure/orm/management/commands/record_career_ops_outcome.py`
- Create: `backend/tests/unit/management/test_record_career_ops_outcome.py`

**Step 1: Write failing command test**

Create `backend/tests/unit/management/test_record_career_ops_outcome.py`:

```python
from __future__ import annotations

import json
from io import StringIO
from typing import cast

import pytest
from django.core.management import call_command

from application.services.career_ops_opportunities import ensure_opportunity_for_signal, record_scanned_job
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import Graph, GraphVersion, ServiceDeliverable, User

pytestmark = pytest.mark.django_db


def _create_company(user: User) -> Graph:
    ensure_default_organization(user)
    organization = user.default_organization
    assert organization is not None
    company = cast(Graph, Graph.objects.create(owner=user, organization=organization, name="CareerOps Outcome Command Co"))
    GraphVersion.objects.create(graph=company, version=1, graph_json={"nodes": [], "edges": [], "metadata": {}})
    return company


def test_record_career_ops_outcome_command_records_interview(user: User) -> None:
    company = _create_company(user)
    signal = record_scanned_job(
        company=company,
        user=user,
        posting={
            "title": "Backend Engineer",
            "company": "Acme AI",
            "url": "https://jobs.example.test/acme/backend",
            "location": "Remote",
            "description": "Python backend role.",
            "provider": "fixture",
        },
    )
    opportunity = ensure_opportunity_for_signal(signal=signal, user=user)
    assert opportunity is not None
    out = StringIO()

    call_command(
        "record_career_ops_outcome",
        company_id=str(company.id),
        user_id=str(user.id),
        opportunity_id=str(opportunity.id),
        outcome_status="interview",
        stage="phone_screen",
        stage_status="scheduled",
        notes="Recruiter screen scheduled.",
        event_date="2026-07-07",
        idempotency_key="outcome-command:test",
        stdout=out,
    )

    payload = json.loads(out.getvalue())
    assert payload["status"] == "ok"
    assert payload["opportunity_id"] == str(opportunity.id)
    assert payload["outcome_asset_version_id"]
    assert payload["projection_id"]
    assert payload["external_side_effects_allowed"] is False
    opportunity.refresh_from_db()
    assert opportunity.metadata_json["career_ops"]["outcome_status"] == "interview"
    assert ServiceDeliverable.objects.filter(company=company, deliverable_type="application_outcome_report").exists()
```

Run command test. Expected: FAIL because command does not exist.

**Step 2: Implement command**

Create `backend/infrastructure/orm/management/commands/record_career_ops_outcome.py`:

```python
"""Record a CareerOps application outcome for an existing opportunity."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandParser

from application.services.career_ops_outcomes import CAREER_OPS_OUTCOME_STATUSES, record_career_ops_outcome
from infrastructure.orm.models import CompanyOpportunity, Graph, User


class Command(BaseCommand):
    help = "Record a backend-owned CareerOps application outcome and rematerialize the pipeline projection."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--company-id", required=True)
        parser.add_argument("--user-id", required=True)
        parser.add_argument("--opportunity-id", required=True)
        parser.add_argument("--outcome-status", required=True, choices=sorted(CAREER_OPS_OUTCOME_STATUSES))
        parser.add_argument("--idempotency-key", required=True)
        parser.add_argument("--stage", default="")
        parser.add_argument("--stage-status", default="")
        parser.add_argument("--notes", default="")
        parser.add_argument("--feedback", default="")
        parser.add_argument("--event-date", default=None)

    def handle(self, *args: object, **options: object) -> None:
        company = Graph.objects.get(id=options["company_id"])
        user = User.objects.get(id=options["user_id"])
        opportunity = CompanyOpportunity.objects.get(id=options["opportunity_id"], company=company)
        result = record_career_ops_outcome(
            company=company,
            actor=user,
            opportunity=opportunity,
            outcome_status=str(options["outcome_status"]),
            stage=str(options["stage"]),
            stage_status=str(options["stage_status"]),
            notes=str(options["notes"]),
            feedback=str(options["feedback"]),
            event_date=options["event_date"],
            idempotency_key=str(options["idempotency_key"]),
        )
        payload = {
            "status": "ok",
            "run_id": result.run_id,
            "opportunity_id": result.opportunity_id,
            "outcome_deliverable_id": result.outcome_deliverable_id,
            "outcome_asset_version_id": result.outcome_asset_version_id,
            "projection_id": result.projection_id,
            "external_side_effects_allowed": result.external_side_effects_allowed,
        }
        self.stdout.write(json.dumps(payload, sort_keys=True))
```

**Step 3: Run command test**

```bash
FORGEGRAPH_ENV_FILE= DEBUG=0 SECRET_KEY=*** USE_SQLITE=true USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 SQLITE_DB_PATH=.hermes/career_ops_outcomes_command_test.sqlite3 UV_PROJECT_ENVIRONMENT=.venv-test-career-ops-e2e uv run --group dev pytest tests/unit/management/test_record_career_ops_outcome.py -q --tb=short --disable-warnings
```

Expected: PASS.

---

## Task 5: Update Tracker Integrity Tests for Outcome Statuses

**Objective:** Ensure outcome metadata remains compatible with existing canonical tracker integrity.

**Files:**

- Modify: `backend/tests/unit/services/test_career_ops_tracker.py`
- Maybe modify: `backend/application/services/career_ops_tracker.py`

**Step 1: Inspect existing tracker tests**

Read:

```bash
# use read_file, not cat
backend/tests/unit/services/test_career_ops_tracker.py
```

**Step 2: Add a test that `outcome_status` does not break integrity**

Expected test shape:

```python
def test_pipeline_integrity_uses_tracker_status_when_outcome_status_is_richer(user: User) -> None:
    company = _create_company(user)
    opportunity = _opportunity(company, user)
    opportunity.metadata_json = {
        "career_ops": {
            **opportunity.metadata_json["career_ops"],
            "application_status": "rejected",
            "tracker_status": "rejected",
            "outcome_status": "offer_declined",
        }
    }
    opportunity.save(update_fields=["metadata_json", "updated_at"])

    result = check_career_ops_pipeline_integrity(company=company)

    assert result["status"] == "ok"
    assert result["canonical_counts"]["rejected"] == 1
```

If existing helper names differ, adapt to local helper style.

**Step 3: Run tracker tests**

```bash
FORGEGRAPH_ENV_FILE= DEBUG=0 SECRET_KEY=*** USE_SQLITE=true USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 SQLITE_DB_PATH=.hermes/career_ops_tracker_test.sqlite3 UV_PROJECT_ENVIRONMENT=.venv-test-career-ops-e2e uv run --group dev pytest tests/unit/services/test_career_ops_tracker.py -q --tb=short --disable-warnings
```

Expected: PASS. If it fails because `check_career_ops_pipeline_integrity()` prefers `application_status` over `tracker_status`, modify `backend/application/services/career_ops_tracker.py:73` to keep current behavior:

```python
raw_status = career_ops.get("tracker_status") or career_ops.get("application_status") or "evaluated"
```

This already appears to be the current code, so no service change may be needed.

---

## Task 6: Update CareerOps Deliverable Catalog Constants

**Objective:** Add outcome report to CareerOps deliverable vocabulary without changing DB schema.

**Files:**

- Modify: `backend/application/services/career_ops_graph_contract.py`
- Test: `backend/tests/unit/services/test_career_ops_graph_contract.py`

**Step 1: Add failing assertion**

In `backend/tests/unit/services/test_career_ops_graph_contract.py`, add or extend an existing deliverable-type test:

```python
def test_career_ops_deliverables_include_application_outcome_report() -> None:
    from application.services.career_ops_graph_contract import CAREER_OPS_DELIVERABLE_TYPES

    assert "application_outcome_report" in CAREER_OPS_DELIVERABLE_TYPES
```

Run test. Expected: FAIL if constant missing.

**Step 2: Add constant value**

In `backend/application/services/career_ops_graph_contract.py`, add to `CAREER_OPS_DELIVERABLE_TYPES` near other tracker/application artifacts:

```python
    "application_outcome_report",
```

Likely location: after `application_packet` or near submission/tracking deliverables.

**Step 3: Run graph contract test**

```bash
FORGEGRAPH_ENV_FILE= DEBUG=0 SECRET_KEY=*** USE_SQLITE=true USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 SQLITE_DB_PATH=.hermes/career_ops_graph_contract_test.sqlite3 UV_PROJECT_ENVIRONMENT=.venv-test-career-ops-e2e uv run --group dev pytest tests/unit/services/test_career_ops_graph_contract.py -q --tb=short --disable-warnings
```

Expected: PASS.

---

## Task 7: Focused Regression Run

**Objective:** Verify PR 1 did not break packet generation, projections, tracker integrity, or management commands.

**Files:** no code changes.

Run from `backend/`:

```bash
FORGEGRAPH_ENV_FILE= DEBUG=0 SECRET_KEY=*** USE_SQLITE=true USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 SQLITE_DB_PATH=.hermes/career_ops_pr1_regression.sqlite3 UV_PROJECT_ENVIRONMENT=.venv-test-career-ops-e2e uv run --group dev pytest \
  tests/unit/services/test_career_ops_outcomes.py \
  tests/unit/management/test_record_career_ops_outcome.py \
  tests/unit/services/test_career_ops_projections.py \
  tests/unit/services/test_career_ops_tracker.py \
  tests/unit/services/test_career_ops_pipeline.py \
  tests/unit/management/test_build_career_ops_application_packet.py \
  -q --tb=short --disable-warnings
```

Expected: PASS.

---

## Task 8: Static Checks

**Objective:** Verify syntax, import ordering/lint, and Django system check.

Run from `backend/`:

```bash
python -m py_compile \
  application/services/career_ops_outcomes.py \
  application/services/career_ops_projections.py \
  infrastructure/orm/management/commands/record_career_ops_outcome.py \
  tests/unit/services/test_career_ops_outcomes.py \
  tests/unit/management/test_record_career_ops_outcome.py
```

Then:

```bash
UV_PROJECT_ENVIRONMENT=.venv-test-career-ops-e2e uv run ruff check \
  application/services/career_ops_outcomes.py \
  application/services/career_ops_projections.py \
  infrastructure/orm/management/commands/record_career_ops_outcome.py \
  tests/unit/services/test_career_ops_outcomes.py \
  tests/unit/management/test_record_career_ops_outcome.py
```

Then:

```bash
FORGEGRAPH_ENV_FILE= DEBUG=0 SECRET_KEY=*** USE_SQLITE=true USE_IN_MEMORY_CACHE=1 USE_IN_MEMORY_CHANNEL_LAYER=1 SQLITE_DB_PATH=.hermes/career_ops_pr1_check.sqlite3 UV_PROJECT_ENVIRONMENT=.venv-test-career-ops-e2e uv run python manage.py check
```

Expected:

- `py_compile`: no output, exit 0.
- `ruff`: no errors.
- Django check: `System check identified no issues`.

---

## Task 9: Manual Docker Smoke Test

**Objective:** Verify the command works against the real Docker-backed ForgeGraph backend, not only SQLite unit tests.

**Prerequisite:** Docker Desktop running.

Run from repo root `C:\Users\mathi\projects\forgegraph`:

```bash
docker compose start postgres redis memory-grpc engine backend backend-run-queue backend-os-projections backend-runtime-intents
```

Create or reuse an existing opportunity. For smoke test, use an opportunity ID from the CareerOps company. If needed, create one with existing `run_career_ops_url_pipeline` command.

Example command shape:

```bash
MSYS_NO_PATHCONV=1 docker compose exec -T backend python manage.py record_career_ops_outcome \
  --company-id '<company-id>' \
  --user-id '<user-id>' \
  --opportunity-id '<opportunity-id>' \
  --outcome-status interview \
  --stage phone_screen \
  --stage-status scheduled \
  --notes 'Smoke test outcome recording.' \
  --event-date '2026-07-07' \
  --idempotency-key 'outcome:smoke:2026-07-07:<opportunity-id>'
```

Expected JSON:

```json
{
  "status": "ok",
  "run_id": "...",
  "opportunity_id": "...",
  "outcome_deliverable_id": "...",
  "outcome_asset_version_id": "...",
  "projection_id": "...",
  "external_side_effects_allowed": false
}
```

Verify DB readback:

```bash
docker compose exec -T backend python manage.py shell -c "import json; from infrastructure.orm.models import CompanyOpportunity, ServiceDeliverable; opp=CompanyOpportunity.objects.get(id='<opportunity-id>'); print(json.dumps(opp.metadata_json['career_ops'], indent=2)); print(ServiceDeliverable.objects.filter(company=opp.company, deliverable_type='application_outcome_report', metadata_json__career_ops__opportunity_id=str(opp.id)).count())"
```

Expected:

- `outcome_status` is `interview`.
- `tracker_status` is `interview`.
- deliverable count >= 1.
- `external_side_effects_allowed` is false.

---

## Task 10: PR Hygiene

**Objective:** Prepare the PR without capturing unrelated local work.

**Important current worktree note:** At planning time, `git status --short` showed untracked directories:

```text
?? .hermes/codex_media_workdir/
?? backend/.hermes/codex_media_workdir/
?? backend/.hermes/docker_smoke/
```

Do not add these to the PR unless Mike explicitly wants them. Stage exact paths only.

**Expected changed files for PR 1:**

```text
backend/application/services/career_ops_outcomes.py
backend/application/services/career_ops_projections.py
backend/application/services/career_ops_graph_contract.py
backend/infrastructure/orm/management/commands/record_career_ops_outcome.py
backend/tests/unit/services/test_career_ops_outcomes.py
backend/tests/unit/management/test_record_career_ops_outcome.py
backend/tests/unit/services/test_career_ops_tracker.py                  # only if needed
backend/tests/unit/services/test_career_ops_graph_contract.py           # if adding constant test
```

Before committing:

```bash
git status --short
```

Stage exact files:

```bash
git add \
  backend/application/services/career_ops_outcomes.py \
  backend/application/services/career_ops_projections.py \
  backend/application/services/career_ops_graph_contract.py \
  backend/infrastructure/orm/management/commands/record_career_ops_outcome.py \
  backend/tests/unit/services/test_career_ops_outcomes.py \
  backend/tests/unit/management/test_record_career_ops_outcome.py \
  backend/tests/unit/services/test_career_ops_graph_contract.py
```

If `test_career_ops_tracker.py` changed, add it explicitly.

Commit message:

```bash
git commit -m "feat(career-ops): record application outcomes"
```

PR description should include:

```markdown
## Summary
- Adds backend-owned CareerOps application outcome recording for existing opportunities.
- Persists `application_outcome_report` deliverables with exact `AssetVersion` provenance.
- Updates opportunity metadata and pipeline projection with outcome/interview/calibration fields.
- Adds `record_career_ops_outcome` management command.

## Safety
- No employer-facing side effects.
- `external_side_effects_allowed=false` in run input/output, deliverables, and metadata.
- No local CSV/markdown state source of truth.

## Tests
- [paste focused pytest command output]
- [paste ruff/check output]
```

---

## Risks and Tradeoffs

1. **JSON metadata vs. new model:** PR 1 uses `CompanyOpportunity.metadata_json` to avoid schema churn. This is acceptable for the first slice, but if outcome history becomes heavily queried, a dedicated `CareerOpsOutcomeEvent` model may be warranted later.
2. **Idempotency semantics:** PR 1 creates a `Run` on replay but avoids duplicate `outcome_history` entries for the same idempotency key. This preserves auditability while keeping opportunity history clean.
3. **Tracker status compression:** Rich outcomes like `offer_declined` map to existing canonical tracker statuses for integrity. The richer value remains in `outcome_status`.
4. **No calibration yet:** PR 1 records calibration signals but does not update scoring weights. A later PR should consume these signals to adjust fit/recruiter scoring and STAR story prep.
5. **No API/UI:** Management command is enough for operator workflow. Add API only after backend contract stabilizes.

---

## Acceptance Criteria

- A CareerOps opportunity can be updated with an outcome through service and management command.
- Outcome updates persist in `CompanyOpportunity.metadata_json["career_ops"]`.
- Outcome history appends, but identical idempotency keys do not duplicate history items.
- An `application_outcome_report` deliverable and exact asset version are persisted.
- `career_ops:pipeline_snapshot` projection includes outcome fields.
- Existing packet generation tests still pass.
- No employer-facing side effects are introduced.
- Focused test suite, ruff, py_compile, and Django check pass.

---

## Follow-up PRs

After PR 1 lands:

1. **PR 2:** CareerOps competency expansion from GitHub/docs/certs into source-tagged candidate profile/proof map.
2. **PR 3:** Rank-before-generate shortlist service for daily discovery.
3. **PR 4:** Upskill heatmap and learning plan from tracked opportunities/outcomes.
4. **PR 5:** API/UI/WhatsApp commands for recording outcomes conversationally.
