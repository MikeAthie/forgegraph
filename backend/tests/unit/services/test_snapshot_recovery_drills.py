from __future__ import annotations

import json
from uuid import uuid4

import pytest
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone

from application.services.snapshot_recovery_drills import (
    run_checkpoint_recovery_drill,
    run_whiteboard_snapshot_recovery_drill,
)
from application.services.whiteboard_boards import whiteboard_board_snapshot_key
from application.services.work_whiteboards import whiteboard_snapshot_key
from infrastructure.orm.models import (
    DepartmentRegistry,
    Graph,
    GraphVersion,
    Organization,
    OrganizationMembership,
    Run,
    TaskRoutingRecord,
    User,
    WorkWhiteboard,
)

pytestmark = pytest.mark.django_db


LOC_MEM_CACHE = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "snapshot-recovery-drill-tests",
    }
}


def _company_with_whiteboard() -> tuple[Graph, WorkWhiteboard]:
    org = Organization.objects.create(name="Atlas Snapshot Tests")
    user = User.objects.create_user(
        email=f"snapshot-drill-{uuid4().hex}@example.com",
        password="password123",
    )
    user.default_organization = org
    user.save(update_fields=["default_organization"])
    OrganizationMembership.objects.create(
        organization=org,
        user=user,
        role="owner",
        is_default=True,
    )
    company = Graph.objects.create(
        owner=user,
        organization=org,
        name="Legacy Snapshot Company",
    )
    department = DepartmentRegistry.objects.create(
        organization=org,
        slug="strategy-research",
        name="Strategy & Research",
        department_type="strategy",
    )
    whiteboard = WorkWhiteboard.objects.create(
        organization=org,
        company=company,
        status=WorkWhiteboard.STATUS_ONBOARDING,
        request_type="service_request",
        client_name=company.name,
        request_summary="Recover whiteboard snapshots from durable backend state.",
        objective="Prove cache corruption does not own Atlas state.",
        completion_score=42,
        created_by=user,
    )
    TaskRoutingRecord.objects.create(
        organization=org,
        company=company,
        to_department=department,
        status="queued",
        priority="normal",
        due_at=timezone.now(),
        reason="Snapshot recovery drill card.",
        metadata_json={
            "whiteboard_id": str(whiteboard.id),
            "title": "Snapshot recovery drill card",
            "customer_visible": False,
        },
    )
    return company, whiteboard


@override_settings(CACHES=LOC_MEM_CACHE)
def test_whiteboard_snapshot_recovery_rebuilds_corrupted_cache_from_db():
    cache.clear()
    _company, whiteboard = _company_with_whiteboard()
    whiteboard_key = whiteboard_snapshot_key(whiteboard)
    board_key = whiteboard_board_snapshot_key(whiteboard)

    evidence = run_whiteboard_snapshot_recovery_drill(whiteboard.id)

    assert evidence["available"] is True
    assert evidence["authoritative_state_source"] == "backend_db"
    assert evidence["cache_role"] == "cache_transport_only"
    assert evidence["engine_durable_ownership"] is False
    assert evidence["whiteboard_snapshot"]["cache_key"] == whiteboard_key
    assert evidence["whiteboard_snapshot"]["snapshot_source"] == "db"
    assert evidence["whiteboard_snapshot"]["snapshot_version"] == "work_whiteboard_v1"
    assert evidence["board_snapshot"]["cache_key"] == board_key
    assert evidence["board_snapshot"]["snapshot_source"] == "db"
    assert evidence["board_snapshot"]["snapshot_version"] == "whiteboard_board_v1"
    assert evidence["board_snapshot"]["card_count"] == 1

    whiteboard_cached = json.loads(cache.get(whiteboard_key))
    board_cached = json.loads(cache.get(board_key))
    assert whiteboard_cached["id"] == str(whiteboard.id)
    assert whiteboard_cached["snapshot_source"] == "db"
    assert board_cached["whiteboard_id"] == str(whiteboard.id)
    assert board_cached["snapshot_source"] == "db"
    assert board_cached["cards"][0]["title"] == "Snapshot recovery drill card"


@override_settings(CACHES=LOC_MEM_CACHE)
def test_run_checkpoint_recovery_drill_fails_closed_then_uses_backend_checkpoint():
    cache.clear()
    company, _whiteboard = _company_with_whiteboard()
    version = GraphVersion.objects.create(
        graph=company,
        version=1,
        graph_json={"nodes": [], "edges": []},
    )
    run = Run.objects.create(
        owner=company.owner,
        organization=company.organization,
        graph_version=version,
        status="running",
        recovery_policy="resume",
    )

    evidence = run_checkpoint_recovery_drill(
        run.id,
        active_attempt_id="attempt-valid",
        stale_attempt_id="attempt-stale",
    )

    assert evidence["available"] is True
    assert evidence["authoritative_state_source"] == "backend_snapshot_store"
    assert evidence["engine_durable_ownership"] is False
    assert evidence["missing_checkpoint_fails_closed"] is True
    assert evidence["valid_checkpoint_can_drive_recovery"] is True
    assert evidence["stale_attempt_rejected_by_attempt_match"] is True
    assert evidence["checkpoint"]["attempt_id"] == "attempt-valid"
    assert evidence["checkpoint"]["next_node"] == "after_snapshot_recovery_drill"
