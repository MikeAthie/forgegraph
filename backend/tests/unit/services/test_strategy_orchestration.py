from __future__ import annotations

from typing import cast

import pytest

from application.services.communications import create_message, create_thread
from application.services.request_router import classify_and_route_request
from application.services.strategy_orchestration import (
    complete_strategy_workstream,
    evaluate_strategy_gate,
    list_strategy_workstreams,
    start_strategy_for_whiteboard,
    strategy_state_payload,
    synthesize_strategy,
)
from application.services.work_whiteboards import mark_whiteboard_ready_for_strategy
from infrastructure.orm.models import (
    CompanyAccessPolicy,
    CompanyAssignment,
    CompanyOperatingModelInstallation,
    Graph,
    OperatingModelPackRelease,
    Organization,
    OrganizationMembership,
    TaskRoutingRecord,
    User,
    WorkWhiteboard,
)

pytestmark = pytest.mark.django_db


def _user(org: Organization, email: str, role: str = "member") -> User:
    user = User.objects.create_user(email=email, password="testpassword123")
    user.default_organization = org
    user.save(update_fields=["default_organization"])
    OrganizationMembership.objects.create(organization=org, user=user, role=role, is_default=True)
    return user


def _company(org: Organization, owner: User, *, name: str = "Legacy Eyewear") -> Graph:
    company = cast(Graph, Graph.objects.create(owner=owner, organization=org, name=name, description="Test company"))
    CompanyAccessPolicy.objects.create(
        organization=org,
        company=company,
        assignment_required=True,
        org_admin_access_enabled=True,
    )
    return company


def _assign(org: Organization, company: Graph, user: User, role: str = "member") -> None:
    CompanyAssignment.objects.create(
        organization=org,
        company=company,
        user=user,
        role=role,
        status="active",
    )


def _strategy_definition() -> dict[str, object]:
    return {
        "phase_id": "strategy",
        "source_policy_id": "test_ops.strategy",
        "pack_id": "test_ops.v1",
        "phase_name": "Strategy",
        "whiteboard_required_status": WorkWhiteboard.STATUS_READY_FOR_STRATEGY,
        "set_status_on_start": WorkWhiteboard.STATUS_IN_STRATEGY,
        "workstreams": [
            {
                "id": "research",
                "name": "Research",
                "department": "strategy",
                "required": True,
                "output_type": "memo",
            },
            {
                "id": "plan",
                "name": "Plan",
                "department": "strategy",
                "required": True,
                "output_type": "memo",
            },
        ],
        "gate": {
            "gate_id": "strategy_gate",
            "criteria": [
                {
                    "key": "quality_score",
                    "value_type": "number",
                    "operator": ">=",
                    "threshold": 90,
                    "required": True,
                }
            ],
            "on_pass": {
                "set_whiteboard_status": WorkWhiteboard.STATUS_IN_CONTENT,
                "route_to_department": "next-phase",
            },
            "on_fail": {
                "set_whiteboard_status": WorkWhiteboard.STATUS_IN_STRATEGY,
                "route_to_department": "revision",
                "create_signal": True,
            },
        },
    }


def _install_strategy(company: Graph) -> None:
    definition = _strategy_definition()
    release = OperatingModelPackRelease.objects.create(
        pack_id=f"test_ops.strategy:{company.id}",
        base_pack_id="test_ops",
        version="1.0.0",
        display_name="Test Ops Strategy",
        checksum=str(company.id).replace("-", "")[:64],
        manifest_json={"workstream_phases": [definition]},
        files_json={},
        status="active",
    )
    CompanyOperatingModelInstallation.objects.create(
        organization=company.organization,
        company=company,
        pack_release=release,
        pack_id=release.pack_id,
        base_pack_id="test_ops",
        role="primary",
        status="active",
        public_config_json={"workstream_phases": [definition]},
    )


def _ready_whiteboard(company: Graph, owner: User) -> WorkWhiteboard:
    thread = create_thread(
        company=company,
        user=owner,
        data={
            "title": "Strategy request",
            "thread_type": "support",
            "visibility_mode": "mixed",
            "source_key": f"strategy-whiteboard:{company.id}",
        },
    )
    message = create_message(
        thread=thread,
        sender_user=owner,
        message_kind="request",
        body="Create a new plan for DEPP GOLD with $5000 budget next week.",
        visibility="customer",
        idempotency_key=f"strategy-message:{company.id}",
        metadata={},
    )
    _classification, whiteboard, _records = classify_and_route_request(message=message)
    assert whiteboard is not None
    mark_whiteboard_ready_for_strategy(user=owner, whiteboard=whiteboard)
    whiteboard.refresh_from_db()
    return whiteboard


def test_strategy_wrappers_delegate_to_pack_defined_phase_idempotently() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "strategy-start@example.com", "owner")
    company = _company(org, owner)
    _assign(org, company, owner, "member")
    _install_strategy(company)
    whiteboard = _ready_whiteboard(company, owner)

    first = start_strategy_for_whiteboard(user=owner, whiteboard=whiteboard)
    second = start_strategy_for_whiteboard(user=owner, whiteboard=whiteboard)
    whiteboard.refresh_from_db()

    assert whiteboard.status == WorkWhiteboard.STATUS_IN_STRATEGY
    assert len(first["workstreams"]) == 2
    assert len(second["workstreams"]) == 2
    assert TaskRoutingRecord.objects.filter(
        company=company,
        metadata_json__whiteboard_id=str(whiteboard.id),
        metadata_json__phase_id="strategy",
    ).count() == 2


def test_strategy_wrapper_gate_uses_configured_score_key() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "strategy-pass@example.com", "owner")
    company = _company(org, owner)
    _assign(org, company, owner, "member")
    _install_strategy(company)
    whiteboard = _ready_whiteboard(company, owner)
    start_strategy_for_whiteboard(user=owner, whiteboard=whiteboard)
    for workstream in ("research", "plan"):
        complete_strategy_workstream(
            user=owner,
            whiteboard=whiteboard,
            workstream=workstream,
            result={"summary": f"{workstream} complete"},
        )

    synthesize_strategy(user=owner, whiteboard=whiteboard)
    evaluation = evaluate_strategy_gate(user=owner, whiteboard=whiteboard, scores={"quality_score": 92})
    whiteboard.refresh_from_db()
    state = strategy_state_payload(whiteboard)

    assert evaluation.status == "PASS"
    assert whiteboard.status == WorkWhiteboard.STATUS_IN_CONTENT
    assert state["gate"]["gate_passed"] is True
    assert {item["workstream"] for item in list_strategy_workstreams(whiteboard=whiteboard)} == {"research", "plan"}
