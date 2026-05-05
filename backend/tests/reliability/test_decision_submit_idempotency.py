from __future__ import annotations

import pytest

from infrastructure.orm.models import (
    ApprovalTask,
    Graph,
    GraphVersion,
    ProcessedDecisionSubmission,
    Run,
)

pytestmark = pytest.mark.django_db


def test_decision_submit_id_replays_already_applied_response(
    authenticated_client,
    mock_engine_client,
    user,
) -> None:
    graph = Graph.objects.create(owner=user, name="Decision Idempotency Graph")
    version = GraphVersion.objects.create(
        graph=graph,
        version=1,
        graph_json={"nodes": [], "edges": []},
    )
    run = Run.objects.create(
        owner=user, graph_version=version, status="paused", paused_node_id="gate"
    )
    ApprovalTask.objects.create(
        run=run,
        node_id="gate",
        assignee=user,
        status="pending",
        payload={"prompt_message": "Approve?"},
    )
    payload = {
        "node_id": "gate",
        "submit_id": "decision-submit-1",
        "input_json": {"approved": True, "feedback": "Ship it"},
    }

    first = authenticated_client.post(f"/api/runs/{run.id}/resume", payload, format="json")
    second = authenticated_client.post(f"/api/runs/{run.id}/resume", payload, format="json")

    assert first.status_code == 200
    assert first.data["data"]["idempotency"]["status"] == "applied"
    assert second.status_code == 200
    assert second.data["data"]["idempotency"]["status"] == "already_applied"
    assert second.data["data"]["duplicate"] is True
    assert (
        ProcessedDecisionSubmission.objects.filter(
            organization=user.default_organization,
            submit_id="decision-submit-1",
        ).count()
        == 1
    )
    resume_calls = [call for call in mock_engine_client.calls if call[0] == "resume_run"]
    assert len(resume_calls) == 1


def test_decision_submit_id_rejects_conflicting_payload(authenticated_client, user) -> None:
    graph = Graph.objects.create(owner=user, name="Decision Conflict Graph")
    version = GraphVersion.objects.create(
        graph=graph,
        version=1,
        graph_json={"nodes": [], "edges": []},
    )
    run = Run.objects.create(
        owner=user, graph_version=version, status="paused", paused_node_id="gate"
    )
    ApprovalTask.objects.create(
        run=run,
        node_id="gate",
        assignee=user,
        status="pending",
        payload={"prompt_message": "Approve?"},
    )

    first = authenticated_client.post(
        f"/api/runs/{run.id}/resume",
        {
            "node_id": "gate",
            "submit_id": "decision-submit-conflict",
            "input_json": {"approved": True},
        },
        format="json",
    )
    second = authenticated_client.post(
        f"/api/runs/{run.id}/resume",
        {
            "node_id": "gate",
            "submit_id": "decision-submit-conflict",
            "input_json": {"approved": False},
        },
        format="json",
    )

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.data["error"]["code"] == "IDEMPOTENCY_CONFLICT"
