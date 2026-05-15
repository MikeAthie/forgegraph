from __future__ import annotations

from typing import cast

import pytest

from application.services.communications import create_message, create_thread
from application.services.request_router import classify_and_route_request
from application.services.work_whiteboards import mark_whiteboard_ready_for_strategy
from application.services.workstream_gates import complete_workstream
from infrastructure.orm.models import (
    CompanyAccessPolicy,
    CompanyAssignment,
    CompanyOperatingModelInstallation,
    Graph,
    OperatingModelPackRelease,
    Organization,
    OrganizationMembership,
    StateProjection,
    User,
    WorkWhiteboard,
)
from tests.fixtures.deployment_policies import non_marketing_deployment_policy
from tests.fixtures.performance_policies import non_marketing_performance_policy
from tests.fixtures.workstream_phase_policies import atlas_content_production_policy

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


def _phase_definition(phase_id: str = "test_ops.v1.review") -> dict[str, object]:
    return {
        "phase_id": phase_id,
        "source_policy_id": f"{phase_id}.policy",
        "pack_id": "test_ops.v1",
        "phase_name": "Configured Review",
        "set_status_on_start": WorkWhiteboard.STATUS_IN_CONTENT,
        "workstreams": [
            {
                "id": "context_review",
                "name": "Context Review",
                "department": "account-intake",
                "output_type": "memo",
                "required": True,
            }
        ],
        "gate": {
            "gate_id": "configured_review_gate",
            "criteria": [
                {
                    "key": "readiness_score",
                    "value_type": "number",
                    "operator": ">=",
                    "threshold": 90,
                    "required": True,
                }
            ],
            "on_pass": {
                "set_whiteboard_status": WorkWhiteboard.STATUS_IN_APPROVAL,
                "route_to_department": "client-approval",
                "approval_required": True,
            },
            "on_fail": {
                "set_whiteboard_status": WorkWhiteboard.STATUS_IN_CONTENT,
                "route_to_department": "revision",
                "create_signal": True,
            },
        },
    }


def _install_phase(company: Graph, definition: dict[str, object]) -> None:
    pack_id = str(definition["pack_id"])
    release = OperatingModelPackRelease.objects.create(
        pack_id=f"{pack_id}:{company.id}",
        base_pack_id=pack_id,
        version="1.0.0",
        display_name="Test Ops Pack",
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
        base_pack_id=pack_id,
        role="primary",
        status="active",
        public_config_json={"workstream_phases": [definition]},
    )


def _install_deployment_policy(company: Graph, policy: dict[str, object]) -> None:
    release = OperatingModelPackRelease.objects.create(
        pack_id=f"deployment-test:{company.id}",
        base_pack_id=str(policy["pack_id"]),
        version="1.0.0",
        display_name="Deployment Test Pack",
        checksum=str(company.id).replace("-", "")[:64],
        manifest_json={"deployment_policies": [policy]},
        files_json={},
        status="active",
    )
    CompanyOperatingModelInstallation.objects.create(
        organization=company.organization,
        company=company,
        pack_release=release,
        pack_id=release.pack_id,
        base_pack_id=str(policy["pack_id"]),
        role="primary",
        status="active",
        public_config_json={"deployment_policies": [policy]},
    )


def _install_performance_policy(company: Graph, policy: dict[str, object]) -> None:
    release = OperatingModelPackRelease.objects.create(
        pack_id=f"performance-test:{company.id}",
        base_pack_id=str(policy["pack_id"]),
        version="1.0.0",
        display_name="Performance Test Pack",
        checksum=str(company.id).replace("-", "")[:64],
        manifest_json={"performance_policies": [policy]},
        files_json={},
        status="active",
    )
    CompanyOperatingModelInstallation.objects.create(
        organization=company.organization,
        company=company,
        pack_release=release,
        pack_id=release.pack_id,
        base_pack_id=str(policy["pack_id"]),
        role="primary",
        status="active",
        public_config_json={"performance_policies": [policy]},
    )


def _deployment_projection(whiteboard: WorkWhiteboard, *, status: str = "prepared") -> None:
    StateProjection.objects.update_or_create(
        organization=whiteboard.organization,
        company=whiteboard.company,
        program=None,
        projection_type=f"whiteboard_deployment:{whiteboard.id}",
        defaults={
            "display_label": "Whiteboard deployment",
            "source_refs_json": [{"whiteboard_id": str(whiteboard.id)}],
            "json_state": {"whiteboard_id": str(whiteboard.id), "status": status},
            "markdown_summary": "Deployment evidence for performance API tests.",
            "generated_by": "system",
        },
    )


def _whiteboard(org: Organization, company: Graph, owner: User) -> WorkWhiteboard:
    _ = org
    thread = create_thread(
        company=company,
        user=owner,
        data={
            "title": "Legacy request",
            "thread_type": "support",
            "visibility_mode": "mixed",
            "source_key": f"whiteboard-api:{company.id}",
        },
    )
    message = create_message(
        thread=thread,
        sender_user=owner,
        message_kind="request",
        body="Please create a new campaign for DEPP GOLD on WhatsApp with a $5000 budget next week.",
        visibility="customer",
        idempotency_key=f"whiteboard-api-message:{company.id}",
        metadata={},
    )
    _classification, whiteboard, _records = classify_and_route_request(message=message)
    assert whiteboard is not None
    whiteboard.assumptions_json = ["Internal category risk"]
    whiteboard.save(update_fields=["assumptions_json", "updated_at"])
    return whiteboard


def test_whiteboard_list_filters_by_company_access_and_role_payload(api_client) -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "whiteboard-owner@example.com", "owner")
    customer = _user(org, "whiteboard-customer@example.com", "viewer")
    other = _user(org, "whiteboard-other@example.com", "viewer")
    company = _company(org, owner)
    other_company = _company(org, owner, name="Other Client")
    _assign(org, company, owner, "member")
    _assign(org, company, customer, "viewer")
    _assign(org, other_company, other, "viewer")
    whiteboard = _whiteboard(org, company, owner)

    api_client.force_authenticate(user=customer)
    customer_response = api_client.get("/api/whiteboards", data={"company_id": str(company.id)})
    detail_response = api_client.get(f"/api/whiteboards/{whiteboard.id}")
    other_response = api_client.get("/api/whiteboards", data={"company_id": str(other_company.id)})

    assert customer_response.status_code == 200
    customer_payload = customer_response.json()["data"]["whiteboards"][0]
    assert customer_payload["id"] == str(whiteboard.id)
    assert "assumptions" not in customer_payload
    assert "routing_records" not in customer_payload
    assert detail_response.status_code == 200
    assert other_response.status_code == 200
    assert other_response.json()["data"]["whiteboards"] == []

    api_client.force_authenticate(user=owner)
    operator_response = api_client.get(f"/api/whiteboards/{whiteboard.id}")
    operator_payload = operator_response.json()["data"]["whiteboard"]
    assert operator_response.status_code == 200
    assert operator_payload["assumptions"] == ["Internal category risk"]
    assert operator_payload["routing_records"]


def test_other_client_cannot_get_whiteboard(api_client) -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "whiteboard-owner-404@example.com", "owner")
    other_user = _user(org, "whiteboard-other-404@example.com", "viewer")
    company = _company(org, owner)
    other_company = _company(org, owner, name="Other Client")
    _assign(org, company, owner, "member")
    _assign(org, other_company, other_user, "viewer")
    whiteboard = _whiteboard(org, company, owner)

    api_client.force_authenticate(user=other_user)
    response = api_client.get(f"/api/whiteboards/{whiteboard.id}")

    assert response.status_code == 404


def test_viewer_cannot_update_whiteboard_but_operator_can_mark_ready(api_client) -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "whiteboard-owner-update@example.com", "owner")
    customer = _user(org, "whiteboard-viewer-update@example.com", "viewer")
    company = _company(org, owner)
    _assign(org, company, owner, "member")
    _assign(org, company, customer, "viewer")
    whiteboard = _whiteboard(org, company, owner)

    api_client.force_authenticate(user=customer)
    viewer_response = api_client.patch(
        f"/api/whiteboards/{whiteboard.id}",
        data={"objective": "Viewer should not mutate internal whiteboard."},
        format="json",
    )

    api_client.force_authenticate(user=owner)
    patch_response = api_client.patch(
        f"/api/whiteboards/{whiteboard.id}",
        data={"objective": "Sell out the DEPP GOLD launch inventory."},
        format="json",
    )
    ready_response = api_client.post(f"/api/whiteboards/{whiteboard.id}/ready-for-strategy")

    assert viewer_response.status_code == 403
    assert patch_response.status_code == 200
    assert patch_response.json()["data"]["whiteboard"]["objective"] == "Sell out the DEPP GOLD launch inventory."
    assert ready_response.status_code == 200
    assert ready_response.json()["data"]["whiteboard"]["status"] == WorkWhiteboard.STATUS_READY_FOR_STRATEGY


def test_viewer_can_read_safe_phase_contract_but_cannot_start_phase(api_client) -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "whiteboard-strategy-owner@example.com", "owner")
    customer = _user(org, "whiteboard-strategy-viewer@example.com", "viewer")
    company = _company(org, owner)
    _assign(org, company, owner, "member")
    _assign(org, company, customer, "viewer")
    definition = _phase_definition()
    _install_phase(company, definition)
    whiteboard = _whiteboard(org, company, owner)
    mark_whiteboard_ready_for_strategy(user=owner, whiteboard=whiteboard)
    phase_id = str(definition["phase_id"])

    api_client.force_authenticate(user=customer)
    viewer_response = api_client.get(f"/api/whiteboards/{whiteboard.id}/phases/{phase_id}")
    viewer_start_response = api_client.post(f"/api/whiteboards/{whiteboard.id}/phases/{phase_id}/start")

    api_client.force_authenticate(user=owner)
    start_response = api_client.post(f"/api/whiteboards/{whiteboard.id}/phases/{phase_id}/start")
    detail_response = api_client.get(f"/api/whiteboards/{whiteboard.id}/phases/{phase_id}")

    assert viewer_response.status_code == 200
    viewer_contract = viewer_response.json()["data"]["whiteboard_phase_contract"]
    assert viewer_contract["gate"]["result"] == "pending"
    assert "criteria" not in viewer_contract["gate"]
    assert viewer_contract["allowed_actions"] == []
    assert viewer_start_response.status_code == 403
    assert start_response.status_code == 200
    contract = start_response.json()["data"]["whiteboard_phase_contract"]
    assert len(contract["workstreams"]) == 1
    assert start_response.json()["data"]["whiteboard"]["status"] == WorkWhiteboard.STATUS_IN_CONTENT
    assert detail_response.status_code == 200
    assert detail_response.json()["data"]["whiteboard_phase_contract"]["current_state"]["all_workstreams_completed"] is False


def test_viewer_can_read_deployment_contract_but_cannot_prepare(api_client) -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "whiteboard-deploy-owner@example.com", "owner")
    customer = _user(org, "whiteboard-deploy-viewer@example.com", "viewer")
    company = _company(org, owner)
    _assign(org, company, owner, "member")
    _assign(org, company, customer, "viewer")
    policy = non_marketing_deployment_policy()
    _install_deployment_policy(company, policy)
    whiteboard = _whiteboard(org, company, owner)

    api_client.force_authenticate(user=customer)
    detail_response = api_client.get(f"/api/whiteboards/{whiteboard.id}/deployment")
    prepare_response = api_client.post(f"/api/whiteboards/{whiteboard.id}/deployment/prepare", data={}, format="json")

    assert detail_response.status_code == 200
    contract = detail_response.json()["data"]["deployment_contract"]
    assert contract["policy_id"] == "legal_ops.v1.contract_delivery"
    assert contract["allowed_actions"] == []
    assert "tool_id" not in contract["channels"][0]
    assert prepare_response.status_code == 403


def test_other_client_cannot_get_whiteboard_deployment(api_client) -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "whiteboard-deploy-owner-404@example.com", "owner")
    other_user = _user(org, "whiteboard-deploy-other-404@example.com", "viewer")
    company = _company(org, owner)
    other_company = _company(org, owner, name="Other Client")
    _assign(org, company, owner, "member")
    _assign(org, other_company, other_user, "viewer")
    _install_deployment_policy(company, non_marketing_deployment_policy())
    whiteboard = _whiteboard(org, company, owner)

    api_client.force_authenticate(user=other_user)
    response = api_client.get(f"/api/whiteboards/{whiteboard.id}/deployment")

    assert response.status_code == 404


def test_viewer_can_read_performance_contract_but_cannot_start(api_client) -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "whiteboard-performance-owner@example.com", "owner")
    customer = _user(org, "whiteboard-performance-viewer@example.com", "viewer")
    company = _company(org, owner)
    _assign(org, company, owner, "member")
    _assign(org, company, customer, "viewer")
    policy = non_marketing_performance_policy()
    _install_performance_policy(company, policy)
    whiteboard = _whiteboard(org, company, owner)
    _deployment_projection(whiteboard)

    api_client.force_authenticate(user=customer)
    detail_response = api_client.get(f"/api/whiteboards/{whiteboard.id}/performance")
    start_response = api_client.post(f"/api/whiteboards/{whiteboard.id}/performance/start", data={}, format="json")

    assert detail_response.status_code == 200
    contract = detail_response.json()["data"]["performance_contract"]
    assert contract["policy_id"] == "legal_ops.v1.contract_outcome_review"
    assert contract["allowed_actions"] == []
    assert "tool_id" not in contract["sources"][0]
    assert start_response.status_code == 403


def test_operator_can_start_report_and_evaluate_performance(api_client) -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "whiteboard-performance-api-owner@example.com", "owner")
    company = _company(org, owner)
    _assign(org, company, owner, "member")
    policy = non_marketing_performance_policy()
    _install_performance_policy(company, policy)
    whiteboard = _whiteboard(org, company, owner)
    _deployment_projection(whiteboard)

    api_client.force_authenticate(user=owner)
    start_response = api_client.post(f"/api/whiteboards/{whiteboard.id}/performance/start", data={}, format="json")
    report_response = api_client.post(f"/api/whiteboards/{whiteboard.id}/performance/report", data={}, format="json")
    eval_response = api_client.post(
        f"/api/whiteboards/{whiteboard.id}/performance/evaluate",
        data={},
        format="json",
    )

    assert start_response.status_code == 200
    assert start_response.json()["data"]["performance_contract"]["current_state"]["metric_snapshot_id"]
    assert report_response.status_code == 200
    assert report_response.json()["data"]["performance_contract"]["current_state"]["report_run_id"]
    assert eval_response.status_code == 200
    assert eval_response.json()["data"]["performance_contract"]["current_state"]["evaluation_id"]


def test_other_client_cannot_get_whiteboard_performance(api_client) -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "whiteboard-performance-owner-404@example.com", "owner")
    other_user = _user(org, "whiteboard-performance-other-404@example.com", "viewer")
    company = _company(org, owner)
    other_company = _company(org, owner, name="Other Client")
    _assign(org, company, owner, "member")
    _assign(org, other_company, other_user, "viewer")
    _install_performance_policy(company, non_marketing_performance_policy())
    whiteboard = _whiteboard(org, company, owner)

    api_client.force_authenticate(user=other_user)
    response = api_client.get(f"/api/whiteboards/{whiteboard.id}/performance")

    assert response.status_code == 404


def test_phase_synthesize_and_evaluate_uses_pack_defined_gate(api_client) -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "whiteboard-strategy-synth@example.com", "owner")
    company = _company(org, owner)
    _assign(org, company, owner, "member")
    definition = _phase_definition()
    _install_phase(company, definition)
    whiteboard = _whiteboard(org, company, owner)
    mark_whiteboard_ready_for_strategy(user=owner, whiteboard=whiteboard)
    phase_id = str(definition["phase_id"])

    api_client.force_authenticate(user=owner)
    start_response = api_client.post(f"/api/whiteboards/{whiteboard.id}/phases/{phase_id}/start")
    assert start_response.status_code == 200
    complete_workstream(
        user=owner,
        whiteboard=whiteboard,
        phase_id=phase_id,
        workstream_id="context_review",
        result={"summary": "Context reviewed."},
    )

    synth_response = api_client.post(
        f"/api/whiteboards/{whiteboard.id}/phases/{phase_id}/synthesize",
        data={},
        format="json",
    )
    eval_response = api_client.post(
        f"/api/whiteboards/{whiteboard.id}/phases/{phase_id}/evaluate",
        data={"scorecard": {"readiness_score": 94}},
        format="json",
    )

    assert synth_response.status_code == 200
    assert eval_response.status_code == 200
    payload = eval_response.json()["data"]
    assert payload["whiteboard"]["status"] == WorkWhiteboard.STATUS_IN_APPROVAL
    assert payload["whiteboard_phase_contract"]["gate"]["latest_evaluation"]["status"] == "PASS"
    assert payload["whiteboard_phase_contract"]["current_state"]["gate"]["result"] == "pass"


def test_wrong_company_user_cannot_read_phase_contract(api_client) -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "whiteboard-phase-owner-404@example.com", "owner")
    other_user = _user(org, "whiteboard-phase-other-404@example.com", "viewer")
    company = _company(org, owner)
    other_company = _company(org, owner, name="Other Client")
    _assign(org, company, owner, "member")
    _assign(org, other_company, other_user, "viewer")
    definition = _phase_definition()
    _install_phase(company, definition)
    whiteboard = _whiteboard(org, company, owner)

    api_client.force_authenticate(user=other_user)
    response = api_client.get(f"/api/whiteboards/{whiteboard.id}/phases/{definition['phase_id']}")

    assert response.status_code == 404


def test_other_client_cannot_read_atlas_content_phase_contract(api_client) -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "whiteboard-atlas-owner-404@example.com", "owner")
    other_user = _user(org, "whiteboard-atlas-other-404@example.com", "viewer")
    company = _company(org, owner)
    other_company = _company(org, owner, name="Other Client")
    _assign(org, company, owner, "member")
    _assign(org, other_company, other_user, "viewer")
    definition = atlas_content_production_policy()
    _install_phase(company, definition)
    whiteboard = _whiteboard(org, company, owner)
    mark_whiteboard_ready_for_strategy(user=owner, whiteboard=whiteboard)

    api_client.force_authenticate(user=other_user)
    response = api_client.get(f"/api/whiteboards/{whiteboard.id}/phases/{definition['phase_id']}")

    assert response.status_code == 404
