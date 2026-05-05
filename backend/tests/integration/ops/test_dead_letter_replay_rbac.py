from __future__ import annotations

from uuid import uuid4

import pytest
from rest_framework import status

from application.services.event_dead_letters import record_event_dead_letter
from application.services.task_lifecycle import dead_letter_task, transition_task_lifecycle
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import (
    EventDeadLetterRecord,
    Graph,
    GraphVersion,
    OperatorActionLog,
    OrganizationMembership,
    Run,
    User,
)

pytestmark = pytest.mark.django_db


def _make_run(user: User, *, status_value: str = "running") -> Run:
    ensure_default_organization(user)
    graph = Graph.objects.create(
        owner=user,
        organization=user.default_organization,
        name=f"Ops Graph {uuid4().hex[:8]}",
    )
    version = GraphVersion.objects.create(
        graph=graph,
        version=1,
        graph_json={
            "nodes": [{"id": "task_1", "type": "agent", "name": "Research"}],
            "edges": [],
        },
    )
    return Run.objects.create(
        owner=user,
        organization=user.default_organization,
        graph_version=version,
        status=status_value,
        dispatch_graph_json={"metadata": {"backend_attempt_id": "attempt-1"}},
    )


def _make_task_dead_letter(run: Run):
    transition = transition_task_lifecycle(
        run=run,
        node_id="task_1",
        node_type="agent",
        to_status="running",
        attempt_number=1,
        source="test",
        idempotency_key=f"ops:test:running:{run.id}",
        reason="node started",
    )
    return dead_letter_task(
        task=transition.lifecycle_task,
        reason="retry exhausted",
        last_error="provider timeout",
        attempt_count=1,
        recovery_options=["resolve"],
        idempotency_key=f"ops:test:dead-letter:{run.id}",
        source="test",
    )


def _make_event_dead_letter(user: User) -> EventDeadLetterRecord:
    return record_event_dead_letter(
        source="engine_callback",
        organization=user.default_organization,
        event_id=f"evt-{uuid4()}",
        event_type="run_failed",
        reason="state ordering conflict",
        error_class="RunStateConflict",
        payload={"secret": "hidden", "safe": "visible"},
    )


def test_ops_dead_letters_require_authentication(api_client) -> None:
    response = api_client.get("/api/ops/dead-letters")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_ops_dead_letters_require_admin_or_owner(authenticated_client, user) -> None:
    OrganizationMembership.objects.filter(
        user=user,
        organization=user.default_organization,
    ).update(role="member")

    response = authenticated_client.get("/api/ops/dead-letters")

    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_ops_dead_letter_list_unifies_failure_records(authenticated_client, user) -> None:
    run = _make_run(user)
    task_dead_letter = _make_task_dead_letter(run)
    event_dead_letter = _make_event_dead_letter(user)

    response = authenticated_client.get("/api/ops/dead-letters")

    assert response.status_code == status.HTTP_200_OK
    ids = {item["id"] for item in response.data["data"]["items"]}
    assert f"task:{task_dead_letter.id}" in ids
    assert f"event:{event_dead_letter.id}" in ids
    assert response.data["data"]["counts"]["active"] >= 2


def test_ops_dead_letter_detail_is_org_scoped(authenticated_client, user) -> None:
    other = User.objects.create_user(
        email=f"ops-other-{uuid4().hex}@example.com",
        password="password123",
    )
    ensure_default_organization(other)
    dead_letter = _make_event_dead_letter(other)

    response = authenticated_client.get(f"/api/ops/dead-letters/event:{dead_letter.id}")

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_ops_event_replay_requires_idempotency_key(authenticated_client, user) -> None:
    dead_letter = _make_event_dead_letter(user)

    response = authenticated_client.post(
        f"/api/ops/dead-letters/event:{dead_letter.id}/replay",
        {"reason": "checking replay"},
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"


def test_ops_event_replay_rejects_unavailable_payload_and_audits(
    authenticated_client,
    user,
) -> None:
    dead_letter = _make_event_dead_letter(user)

    response = authenticated_client.post(
        f"/api/ops/dead-letters/event:{dead_letter.id}/replay",
        {"reason": "projection payload is not retained"},
        format="json",
        HTTP_IDEMPOTENCY_KEY=f"ops-replay-{uuid4()}",
    )

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.data["error"]["code"] == "REPLAY_UNAVAILABLE"
    assert OperatorActionLog.objects.filter(
        organization=user.default_organization,
        action="ops.dead_letter.replay",
        target_type="event",
        target_id=str(dead_letter.id),
        status="rejected",
    ).exists()
