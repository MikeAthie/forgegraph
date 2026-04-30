from __future__ import annotations

from typing import cast

import pytest
from django.utils import timezone

from application.services.interaction import (
    ProjectManager,
    brief_from_record,
    process_user_interaction,
)
from domain.entities.interaction import (
    InteractionActor,
    InteractionEvent,
    InteractionEventType,
    OperatingBrief,
    ProjectManagerAction,
)
from infrastructure.orm.models import Graph, GraphVersion, InteractionEventRecord, Run


def _create_company(user) -> Graph:
    organization = user.default_organization
    assert organization is not None
    company = cast(
        Graph,
        Graph.objects.create(
            owner=user,
            organization=organization,
            name="Atlas Growth Agency OS",
            description="Operate growth systems for clients.",
        ),
    )
    GraphVersion.objects.create(
        graph=company,
        version=1,
        graph_json={
            "nodes": [],
            "edges": [],
            "metadata": {
                "company_profile": {
                    "companyName": "Atlas Growth Agency OS",
                    "objective": "Operate growth systems for clients.",
                    "autonomyMode": "assisted",
                }
            },
        },
    )
    return company


def test_apply_event_supports_partial_updates_and_preserves_existing_fields():
    pm = ProjectManager()
    brief = OperatingBrief(
        objective="Build a lead gen system",
        constraints=["Use CRM"],
        success_criteria=["Qualified leads"],
    )
    event = InteractionEvent(
        type=InteractionEventType.CONSTRAINT,
        delta={
            "append": {
                "constraints": ["Cannot use paid ads", "Use CRM"],
            }
        },
        actor=InteractionActor.USER,
        timestamp=timezone.now(),
    )

    updated = pm.apply_event(brief=brief, event=event)

    assert updated.objective == "Build a lead gen system"
    assert updated.success_criteria == ["Qualified leads"]
    assert updated.constraints == ["Use CRM", "Cannot use paid ads"]
    assert brief.constraints == ["Use CRM"]


@pytest.mark.django_db
def test_required_example_flow_mutates_one_persistent_operating_brief(user):
    company = _create_company(user)

    first = process_user_interaction(
        user=user,
        company=company,
        operation=None,
        user_input="Build a lead gen system",
    )
    second = process_user_interaction(
        user=user,
        company=company,
        operation=None,
        user_input="Actually target enterprise clients",
    )
    third = process_user_interaction(
        user=user,
        company=company,
        operation=None,
        user_input="We can't use paid ads",
    )
    fourth = process_user_interaction(
        user=user,
        company=company,
        operation=None,
        user_input="Speed matters more than cost",
    )

    assert (
        first.brief_record.id
        == second.brief_record.id
        == third.brief_record.id
        == fourth.brief_record.id
    )
    brief = brief_from_record(fourth.brief_record)
    assert brief.objective == "Build a lead gen system"
    assert brief.deliverable == "Lead gen system"
    assert "Enterprise clients" in brief.stakeholders
    assert "Cannot use paid ads" in brief.constraints
    assert brief.priority_frame.speed == 0.9
    assert brief.priority_frame.cost == 0.3
    assert fourth.decision.action == ProjectManagerAction.ASSUME_AND_CONTINUE
    assert InteractionEventRecord.objects.filter(brief=fourth.brief_record).count() == 4


@pytest.mark.django_db
def test_approve_returns_execute_readiness_without_starting_a_run(user):
    company = _create_company(user)
    process_user_interaction(
        user=user,
        company=company,
        operation=None,
        user_input="Build a lead gen system",
    )

    result = process_user_interaction(
        user=user,
        company=company,
        operation=None,
        user_input="Approved, go ahead",
    )

    assert result.decision.action == ProjectManagerAction.EXECUTE
    assert result.plan_implications["execution_ready"] is True
    assert Run.objects.count() == 0


@pytest.mark.django_db
def test_mid_execution_mutation_is_operation_scoped_and_marks_plan_revision(user):
    company = _create_company(user)
    version = company.versions.first()
    assert version is not None
    operation = Run.objects.create(
        owner=user,
        organization=company.organization,
        graph_version=version,
        status="running",
        input_json={"operation_brief": "Launch a private fitting pilot."},
    )

    result = process_user_interaction(
        user=user,
        company=company,
        operation=operation,
        user_input="We can't use paid ads",
    )

    assert result.brief_record.operation == operation
    assert result.plan_implications["requires_plan_revision"] is True
    assert result.plan_implications["should_interrupt_active_operation"] is False
    assert "Cannot use paid ads" in result.brief.constraints
