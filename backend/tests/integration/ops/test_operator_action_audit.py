from __future__ import annotations

from uuid import uuid4

import pytest
from rest_framework import status

from application.services.event_dead_letters import record_event_dead_letter
from infrastructure.orm.models import AuditLog, EventDeadLetterRecord, OperatorActionLog

pytestmark = pytest.mark.django_db


def _make_event_dead_letter(user) -> EventDeadLetterRecord:
    return record_event_dead_letter(
        source="engine_callback",
        organization=user.default_organization,
        event_id=f"evt-{uuid4()}",
        event_type="run_failed",
        reason="state ordering conflict",
        error_class="RunStateConflict",
        payload={"secret": "hidden"},
    )


def test_ops_dead_letter_resolve_writes_operator_and_audit_logs(
    authenticated_client,
    user,
) -> None:
    dead_letter = _make_event_dead_letter(user)
    idempotency_key = f"ops-resolve-{uuid4()}"

    response = authenticated_client.post(
        f"/api/ops/dead-letters/event:{dead_letter.id}/resolve",
        {"reason": "manual reconciliation completed"},
        format="json",
        HTTP_IDEMPOTENCY_KEY=idempotency_key,
    )

    assert response.status_code == status.HTTP_200_OK
    dead_letter.refresh_from_db()
    assert dead_letter.status == "resolved"
    assert OperatorActionLog.objects.filter(
        organization=user.default_organization,
        action="ops.dead_letter.resolve",
        target_type="event",
        target_id=str(dead_letter.id),
        reason="manual reconciliation completed",
        idempotency_key=idempotency_key,
    ).exists()
    assert AuditLog.objects.filter(
        tenant_id=user.default_organization_id,
        action="operator.ops.dead_letter.resolve",
        resource_type="event",
        resource_id=str(dead_letter.id),
    ).exists()


def test_ops_dead_letter_resolve_is_idempotent(authenticated_client, user) -> None:
    dead_letter = _make_event_dead_letter(user)
    idempotency_key = f"ops-resolve-{uuid4()}"
    payload = {"reason": "manual reconciliation completed"}

    first = authenticated_client.post(
        f"/api/ops/dead-letters/event:{dead_letter.id}/resolve",
        payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY=idempotency_key,
    )
    second = authenticated_client.post(
        f"/api/ops/dead-letters/event:{dead_letter.id}/resolve",
        payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY=idempotency_key,
    )

    assert first.status_code == status.HTTP_200_OK
    assert second.status_code == status.HTTP_200_OK
    assert second.data["meta"]["idempotency"]["status"] == "already_applied"
    assert (
        OperatorActionLog.objects.filter(
            organization=user.default_organization,
            action="ops.dead_letter.resolve",
            target_type="event",
            target_id=str(dead_letter.id),
            idempotency_key=idempotency_key,
        ).count()
        == 1
    )


def test_ops_lag_endpoints_are_read_only(authenticated_client, user) -> None:
    before_actions = OperatorActionLog.objects.count()
    before_dead_letters = EventDeadLetterRecord.objects.count()

    projection_response = authenticated_client.get("/api/ops/projection-lag")
    spool_response = authenticated_client.get("/api/ops/event-spool")
    runtime_response = authenticated_client.get("/api/ops/runtime-intent-lag")

    assert projection_response.status_code == status.HTTP_200_OK
    assert spool_response.status_code == status.HTTP_200_OK
    assert runtime_response.status_code == status.HTTP_200_OK
    assert OperatorActionLog.objects.count() == before_actions
    assert EventDeadLetterRecord.objects.count() == before_dead_letters
