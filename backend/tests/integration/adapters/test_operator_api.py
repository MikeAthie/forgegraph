from __future__ import annotations

from uuid import uuid4

import pytest
from rest_framework import status

from application.services.event_dead_letters import record_event_dead_letter
from application.services.task_lifecycle import (
    dead_letter_task,
    transition_task_lifecycle,
)
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import (
    AuditLog,
    Graph,
    GraphVersion,
    Run,
    TaskLifecycleRecord,
    User,
)

pytestmark = pytest.mark.django_db


def _make_run(user: User, *, status_value: str = "running") -> Run:
    ensure_default_organization(user)
    graph = Graph.objects.create(
        owner=user,
        organization=user.default_organization,
        name=f"Operator Graph {uuid4().hex[:8]}",
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


def test_operator_run_state_explains_stuck_run(authenticated_client, user) -> None:
    run = _make_run(user)
    transition = transition_task_lifecycle(
        run=run,
        node_id="task_1",
        node_type="agent",
        to_status="running",
        attempt_number=1,
        source="test",
        idempotency_key="operator:test:running",
        reason="node started",
    )
    dead_letter_task(
        task=transition.lifecycle_task,
        reason="retry exhausted",
        last_error="provider timeout",
        attempt_count=1,
        recovery_options=["replay_intent", "force_fail_run"],
        idempotency_key="operator:test:dead-letter",
        source="test",
    )

    response = authenticated_client.get(f"/api/operator/runs/{run.id}/state")

    assert response.status_code == status.HTTP_200_OK
    payload = response.data["data"]
    assert payload["run"]["id"] == str(run.id)
    assert payload["dead_letter_count"] == 1
    assert payload["tasks"][0]["status"] == "dead_lettered"
    assert payload["tasks"][0]["dead_letter"]["reason"] == "retry exhausted"
    assert payload["unresolved_errors"]


def test_operator_force_fail_marks_nonterminal_tasks_and_audits(authenticated_client, user) -> None:
    run = _make_run(user)
    transition_task_lifecycle(
        run=run,
        node_id="task_1",
        node_type="agent",
        to_status="running",
        attempt_number=1,
        source="test",
        idempotency_key="operator:test:force-fail-running",
        reason="node started",
    )

    response = authenticated_client.post(
        f"/api/operator/runs/{run.id}/force-fail",
        {"reason": "operator confirmed poison work"},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    run.refresh_from_db()
    assert run.status == "failed"
    assert TaskLifecycleRecord.objects.get(run=run, source_node_id="task_1").status == "failed"
    assert AuditLog.objects.filter(
        resource_id=str(run.id),
        action="operator.run_force_failed",
    ).exists()


def test_operator_run_state_is_org_scoped(authenticated_client, user) -> None:
    other_user = User.objects.create_user(
        email=f"operator-other-{uuid4().hex}@example.com",
        password="password123",
    )
    run = _make_run(other_user)

    response = authenticated_client.get(f"/api/operator/runs/{run.id}/state")

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_operator_event_dead_letters_are_visible_and_audited(authenticated_client, user) -> None:
    run = _make_run(user)
    dead_letter = record_event_dead_letter(
        source="engine_callback",
        run=run,
        organization=run.organization,
        event_id="evt-poison",
        event_type="run_completed",
        reason="run state ordering conflict",
        error_class="run_state_ordering_conflict",
        payload={"event_id": "evt-poison", "secret": "hidden"},
    )

    list_response = authenticated_client.get("/api/operator/dead-letters")

    assert list_response.status_code == status.HTTP_200_OK
    payload = list_response.data["data"]
    assert payload["event_dead_letters"][0]["id"] == str(dead_letter.id)
    assert payload["event_dead_letters"][0]["payload"]["secret"] == "***REDACTED***"

    replay_response = authenticated_client.post(
        f"/api/operator/event-dead-letters/{dead_letter.id}/replay",
        {"reason": "backend projection fixed"},
        format="json",
    )

    assert replay_response.status_code == status.HTTP_200_OK
    assert replay_response.data["data"]["status"] == "replay_requested"
    assert AuditLog.objects.filter(
        resource_id=str(dead_letter.id),
        action="operator.event_dead_letter_replay_requested",
    ).exists()

    acknowledge_response = authenticated_client.post(
        f"/api/operator/event-dead-letters/{dead_letter.id}/acknowledge",
        {"reason": "manual replay completed"},
        format="json",
    )

    assert acknowledge_response.status_code == status.HTTP_200_OK
    assert acknowledge_response.data["data"]["status"] == "acknowledged"
