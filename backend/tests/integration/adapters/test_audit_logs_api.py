from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework import status

from application.services.audit_log import record_audit_log
from infrastructure.orm.models import AuditLog

pytestmark = pytest.mark.django_db


def test_audit_logs_support_operational_filters(authenticated_client, user):
    tenant_id = str(user.default_organization_id)
    run_one = "11111111-1111-1111-1111-111111111111"
    run_two = "22222222-2222-2222-2222-222222222222"

    record_audit_log(
        actor=user,
        tenant_id=tenant_id,
        action="run.started",
        resource_type="run",
        resource_id=run_one,
        metadata={"run_id": run_one, "status": "running"},
    )
    record_audit_log(
        actor=user,
        tenant_id=tenant_id,
        action="run.replayed",
        resource_type="run",
        resource_id=run_two,
        metadata={"source_run_id": run_one, "status": "failed"},
    )

    response = authenticated_client.get(
        f"/api/audit-logs/?action_prefix=run.&run_id={run_one}&q=started"
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.data["data"]
    assert len(data) == 1
    assert data[0]["action"] == "run.started"
    assert data[0]["resource_id"] == run_one


def test_audit_logs_reject_invalid_created_from(authenticated_client):
    response = authenticated_client.get("/api/audit-logs/?created_from=not-a-date")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["error"]["code"] == "VALIDATION_ERROR"


def test_audit_logs_metadata_is_redacted(authenticated_client, user):
    record_audit_log(
        actor=user,
        tenant_id=str(user.default_organization_id),
        action="credential.created",
        resource_type="credential",
        resource_id="cred-1",
        metadata={
            "api_key": "should-not-leak",
            "authorization": "Bearer top-secret-token",
            "safe": "ok",
            "created_at": timezone.now().isoformat(),
        },
    )

    response = authenticated_client.get("/api/audit-logs/?resource_type=credential")
    assert response.status_code == status.HTTP_200_OK
    row = response.data["data"][0]
    assert row["metadata"]["api_key"] == "***REDACTED***"
    assert row["metadata"]["authorization"] == "***REDACTED***"
    assert row["metadata"]["safe"] == "ok"


def test_audit_logs_support_date_range_and_human_description(authenticated_client, user):
    tenant_id = str(user.default_organization_id)
    older = record_audit_log(
        actor=user,
        tenant_id=tenant_id,
        action="credential.created",
        resource_type="credential",
        resource_id="cred-1",
        metadata={"provider": "openai", "name": "primary key"},
    )
    newer = record_audit_log(
        actor=user,
        tenant_id=tenant_id,
        action="memory.observation_created",
        resource_type="memory_observation",
        resource_id="obs-1",
        metadata={"type": "fact", "title": "VIP preference", "scope": "graph"},
    )
    AuditLog.objects.filter(id=older.id).update(created_at=timezone.now() - timedelta(days=3))
    AuditLog.objects.filter(id=newer.id).update(created_at=timezone.now() - timedelta(hours=2))

    created_from = (timezone.now() - timedelta(days=1)).isoformat()
    response = authenticated_client.get("/api/audit-logs/", data={"created_from": created_from})

    assert response.status_code == status.HTTP_200_OK
    data = response.data["data"]
    assert len(data) == 1
    assert data[0]["action"] == "memory.observation_created"
    assert data[0]["description"] == "Created graph fact observation 'VIP preference'."


def test_memory_observation_api_writes_audit_events(authenticated_client):
    create_response = authenticated_client.post(
        "/api/memory/observations",
        data={
            "type": "fact",
            "title": "Support Preference",
            "content": "Prefers concise replies.",
            "scope": "graph",
            "graph_id": "11111111-1111-1111-1111-111111111111",
            "session_id": "22222222-2222-2222-2222-222222222222",
        },
        format="json",
    )
    observation_id = create_response.json()["data"]["id"]

    authenticated_client.patch(
        f"/api/memory/observations/{observation_id}",
        data={"title": "Updated Support Preference"},
        format="json",
    )
    authenticated_client.delete(f"/api/memory/observations/{observation_id}")

    response = authenticated_client.get("/api/audit-logs/?action_prefix=memory.")

    assert response.status_code == status.HTTP_200_OK
    actions = [item["action"] for item in response.data["data"]]
    assert actions == [
        "memory.observation_deleted",
        "memory.observation_updated",
        "memory.observation_created",
    ]
    assert response.data["data"][1]["description"].startswith("Updated graph fact observation")
