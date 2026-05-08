from __future__ import annotations

from typing import cast

import pytest
from django.utils import timezone

from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import (
    Graph,
    GraphVersion,
    NodeRun,
    OrganizationMembership,
    Run,
    TaskJudge,
    TaskRecord,
    User,
)

pytestmark = pytest.mark.django_db


def _create_task(
    user: User,
    *,
    title: str = "Planning task",
    include_current_step: bool = True,
) -> TaskRecord:
    ensure_default_organization(user)
    organization = user.default_organization
    assert organization is not None
    graph = cast(
        Graph,
        Graph.objects.create(
            owner=user,
            organization=organization,
            name=f"{title} graph",
            description="Task judge test graph.",
        ),
    )
    version = GraphVersion.objects.create(
        graph=graph,
        version=1,
        graph_json={"nodes": [], "edges": [], "metadata": {}},
    )
    run = Run.objects.create(
        owner=user,
        organization=organization,
        graph_version=version,
        status="succeeded",
        started_at=timezone.now(),
        ended_at=timezone.now(),
        output_json={
            "final": "Strategy baseline includes KPIs, visual list, goals, and next run plan.",
        },
    )
    node_run = (
        NodeRun.objects.create(
            run=run,
            node_id="planning",
            node_type="agent",
            status="succeeded",
            started_at=run.started_at,
            ended_at=run.ended_at,
            output_json={
                "summary": "Produced a strategy baseline with KPIs and visual content needed.",
            },
        )
        if include_current_step
        else None
    )
    return TaskRecord.objects.create(
        organization=organization,
        execution=run,
        source_node_id="planning",
        external_key=f"{run.id}:planning",
        title=title,
        status="completed",
        priority="normal",
        summary="Produced strategy baseline with KPIs, visual list, and next run plan.",
        current_step=node_run,
        started_at=run.started_at,
        ended_at=run.ended_at,
    )


def test_task_judge_api_configures_and_evaluates(authenticated_client, user):
    task = _create_task(user)

    create_response = authenticated_client.put(
        f"/api/tasks/{task.id}/judge",
        data={
            "title": "Strategy Baseline Judge",
            "instructions": "Score whether the task produced a usable strategy baseline.",
            "criteria": [
                "strategy baseline",
                "KPIs",
                "visual content needed",
                "next run plan",
            ],
            "pass_threshold": 75,
        },
        format="json",
    )
    detail_response = authenticated_client.get(f"/api/tasks/{task.id}")
    evaluate_response = authenticated_client.post(f"/api/tasks/{task.id}/judge/evaluate")

    assert create_response.status_code == 201
    assert create_response.json()["data"]["judge"]["status"] == "pending"
    assert detail_response.status_code == 200
    assert detail_response.json()["data"]["judge"]["criteria_count"] == 4
    assert evaluate_response.status_code == 200
    judge = evaluate_response.json()["data"]["judge"]
    assert judge["status"] == "passed"
    assert judge["score"] >= 75
    assert judge["result"]["algorithm"] == "deterministic_keyword_v1"
    assert TaskJudge.objects.get(task=task).status == "passed"


def test_task_judge_api_uses_backend_evidence_snapshot(authenticated_client, user):
    task = _create_task(user, title="Legacy Phase 6 task")

    create_response = authenticated_client.put(
        f"/api/tasks/{task.id}/judge",
        data={
            "title": "Legacy Phase 6 Judge",
            "criteria": [
                "operator_surface_verified",
                "stock_semantics_consistent",
                "approval_gates_present",
                "evidence_packet_complete",
            ],
            "pass_threshold": 85,
            "evidence_snapshot": {
                "operator_surface_verified": True,
                "stock_semantics_consistent": True,
                "approval_gates_present": True,
                "evidence_packet_complete": True,
            },
        },
        format="json",
    )
    evaluate_response = authenticated_client.post(f"/api/tasks/{task.id}/judge/evaluate")

    assert create_response.status_code == 201
    judge = evaluate_response.json()["data"]["judge"]
    assert evaluate_response.status_code == 200
    assert judge["status"] == "passed"
    assert judge["score"] >= 85
    assert judge["result"]["evidence_snapshot"]["operator_surface_verified"] is True


def test_task_judge_api_evaluates_snapshot_when_current_step_is_missing(authenticated_client, user):
    task = _create_task(user, title="Legacy projected task", include_current_step=False)

    create_response = authenticated_client.put(
        f"/api/tasks/{task.id}/judge",
        data={
            "title": "Legacy Phase 6 Judge",
            "criteria": [
                "operator_surface_verified",
                "stock_semantics_consistent",
                "approval_gates_present",
            ],
            "pass_threshold": 85,
            "evidence_snapshot": {
                "operator_surface_verified": True,
                "stock_semantics_consistent": True,
                "approval_gates_present": True,
            },
        },
        format="json",
    )
    evaluate_response = authenticated_client.post(f"/api/tasks/{task.id}/judge/evaluate")

    assert create_response.status_code == 201
    assert evaluate_response.status_code == 200
    judge = evaluate_response.json()["data"]["judge"]
    assert judge["status"] == "passed"
    assert judge["score"] >= 85
    sources = judge["result"]["evidence_sources"]
    current_step_output = next(item for item in sources if item["source"] == "current_step_output")
    assert current_step_output["available"] is False


def test_task_judge_api_requires_member_for_mutation(authenticated_client, user):
    task = _create_task(user)
    OrganizationMembership.objects.filter(
        organization=user.default_organization,
        user=user,
    ).update(role="viewer")

    response = authenticated_client.put(
        f"/api/tasks/{task.id}/judge",
        data={
            "criteria": ["strategy baseline"],
            "pass_threshold": 80,
        },
        format="json",
    )

    assert response.status_code == 403
    assert TaskJudge.objects.filter(task=task).count() == 0


def test_task_judge_api_hides_other_organization_task(authenticated_client):
    other_user = User.objects.create_user(email="task-judge-other@example.com", password="pw123456")
    task = _create_task(other_user, title="Other org task")

    response = authenticated_client.get(f"/api/tasks/{task.id}/judge")

    assert response.status_code == 404
