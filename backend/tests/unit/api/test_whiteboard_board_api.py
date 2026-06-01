from __future__ import annotations

from typing import cast
from uuid import uuid4

import pytest

from infrastructure.orm.models import (
    CompanyAccessPolicy,
    CompanyAssignment,
    DepartmentMembership,
    DepartmentRegistry,
    EvaluationRun,
    Graph,
    Organization,
    OrganizationMembership,
    TaskRoutingRecord,
    User,
    WorkWhiteboard,
)
from tests.helpers.idempotency import assert_response_idempotency
from tests.helpers.organizations import required_company_organization

pytestmark = pytest.mark.django_db


def _user(org: Organization, email: str, role: str = "member") -> User:
    local, _, domain = email.partition("@")
    user = User.objects.create_user(
        email=f"{local}-{uuid4().hex}@{domain or 'example.com'}",
        password="testpassword123",
    )
    user.default_organization = org
    user.save(update_fields=["default_organization"])
    OrganizationMembership.objects.create(organization=org, user=user, role=role, is_default=True)
    return user


def _company(org: Organization, owner: User, *, name: str = "Legacy Eyewear") -> Graph:
    company = cast(
        Graph,
        Graph.objects.create(owner=owner, organization=org, name=name, description="Test company"),
    )
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


def _department(org: Organization, slug: str, department_type: str = "") -> DepartmentRegistry:
    return DepartmentRegistry.objects.create(
        organization=org,
        slug=slug,
        name=slug.replace("-", " ").title(),
        department_type=department_type,
    )


def _department_member(
    org: Organization, department: DepartmentRegistry, user: User, role: str = "member"
) -> None:
    DepartmentMembership.objects.create(
        organization=org,
        department=department,
        user=user,
        role=role,
        status="active",
    )


def _whiteboard(company: Graph, owner: User) -> WorkWhiteboard:
    return WorkWhiteboard.objects.create(
        organization=required_company_organization(company),
        company=company,
        status=WorkWhiteboard.STATUS_ONBOARDING,
        request_type="service_request",
        client_name=company.name,
        request_summary="Generic project request",
        objective="Deliver the project",
        completion_score=45.0,
        created_by=owner,
    )


def _card(
    whiteboard: WorkWhiteboard,
    department: DepartmentRegistry,
    *,
    visible: bool = False,
    status: str = "assigned",
    links: dict[str, str] | None = None,
) -> TaskRoutingRecord:
    return TaskRoutingRecord.objects.create(
        organization=whiteboard.organization,
        company=whiteboard.company,
        to_department=department,
        reason="Internal execution detail",
        status=status,
        metadata_json={
            "whiteboard_id": str(whiteboard.id),
            "title": "Generic board card",
            "customer_visible": visible,
            "links": links or {},
        },
    )


def test_get_board_returns_role_filtered_contract(api_client) -> None:
    org = Organization.objects.create(name="Atlas")
    operator = _user(org, "board-api-operator@example.com", "owner")
    customer = _user(org, "board-api-customer@example.com", "viewer")
    company = _company(org, operator)
    _assign(org, company, operator, "member")
    _assign(org, company, customer, "viewer")
    department = _department(org, "strategy")
    whiteboard = _whiteboard(company, operator)
    internal = _card(whiteboard, department)
    visible = _card(whiteboard, department, visible=True)

    api_client.force_authenticate(user=operator)
    operator_response = api_client.get(f"/api/whiteboards/{whiteboard.id}/board")
    api_client.force_authenticate(user=customer)
    customer_response = api_client.get(f"/api/whiteboards/{whiteboard.id}/board")

    assert operator_response.status_code == 200
    operator_cards = operator_response.json()["data"]["board"]["cards"]
    assert {card["id"] for card in operator_cards} == {str(internal.id), str(visible.id)}
    assert customer_response.status_code == 200
    customer_cards = customer_response.json()["data"]["board"]["cards"]
    assert [card["id"] for card in customer_cards] == [str(visible.id)]
    assert customer_cards[0]["reason"] == ""


def test_routing_department_can_create_card_through_generic_route(api_client) -> None:
    org = Organization.objects.create(name="Atlas")
    operator = _user(org, "board-api-routing@example.com", "member")
    company = _company(org, operator)
    _assign(org, company, operator, "member")
    routing = _department(org, "traffic", "traffic")
    strategy = _department(org, "strategy")
    _department_member(org, routing, operator, "lead")
    whiteboard = _whiteboard(company, operator)

    api_client.force_authenticate(user=operator)
    response = api_client.post(
        f"/api/whiteboards/{whiteboard.id}/board/cards",
        data={
            "department_id": str(strategy.id),
            "title": "Create project card",
            "priority": "high",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="api-create-card",
    )

    assert response.status_code == 201
    board = response.json()["data"]["board"]
    assert board["cards"][0]["title"] == "Create project card"
    assert board["cards"][0]["priority"] == "high"
    assert_response_idempotency(response, status="applied", idempotency_key="api-create-card")


def test_board_card_create_retry_returns_idempotency_metadata_and_conflict(api_client) -> None:
    org = Organization.objects.create(name="Atlas")
    operator = _user(org, "board-api-idempotent@example.com", "member")
    company = _company(org, operator)
    _assign(org, company, operator, "member")
    routing = _department(org, "traffic", "traffic")
    strategy = _department(org, "strategy")
    _department_member(org, routing, operator, "lead")
    whiteboard = _whiteboard(company, operator)
    payload = {
        "department_id": str(strategy.id),
        "title": "Retry-safe project card",
        "priority": "high",
    }

    api_client.force_authenticate(user=operator)
    first = api_client.post(
        f"/api/whiteboards/{whiteboard.id}/board/cards",
        data=payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY="api-create-card-retry",
    )
    second = api_client.post(
        f"/api/whiteboards/{whiteboard.id}/board/cards",
        data=payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY="api-create-card-retry",
    )
    conflict = api_client.post(
        f"/api/whiteboards/{whiteboard.id}/board/cards",
        data={**payload, "title": "Changed card body"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="api-create-card-retry",
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert conflict.status_code == 409
    assert_response_idempotency(first, status="applied", idempotency_key="api-create-card-retry")
    assert_response_idempotency(
        second, status="already_applied", idempotency_key="api-create-card-retry"
    )
    assert second.json()["data"]["duplicate"] is True
    assert TaskRoutingRecord.objects.filter(company=company).count() == 1


def test_assigned_department_can_update_own_card_but_customer_cannot_mutate(api_client) -> None:
    org = Organization.objects.create(name="Atlas")
    owner = _user(org, "board-api-owner@example.com", "owner")
    department_user = _user(org, "board-api-dept@example.com", "member")
    customer = _user(org, "board-api-viewer@example.com", "viewer")
    company = _company(org, owner)
    _assign(org, company, owner, "member")
    _assign(org, company, department_user, "member")
    _assign(org, company, customer, "viewer")
    strategy = _department(org, "strategy")
    _department_member(org, strategy, department_user, "member")
    whiteboard = _whiteboard(company, owner)
    card = _card(whiteboard, strategy)

    api_client.force_authenticate(user=department_user)
    response = api_client.patch(
        f"/api/whiteboards/{whiteboard.id}/board/cards/{card.id}",
        data={"status": "in_progress"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="api-start-card",
    )
    api_client.force_authenticate(user=customer)
    customer_response = api_client.patch(
        f"/api/whiteboards/{whiteboard.id}/board/cards/{card.id}",
        data={"status": "in_progress"},
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["data"]["board"]["cards"][0]["status"] == "in_progress"
    assert customer_response.status_code == 403


def test_customer_safe_board_hides_internal_review_links(api_client) -> None:
    org = Organization.objects.create(name="Atlas")
    owner = _user(org, "board-api-review-owner@example.com", "owner")
    customer = _user(org, "board-api-review-viewer@example.com", "viewer")
    company = _company(org, owner)
    _assign(org, company, owner, "member")
    _assign(org, company, customer, "viewer")
    strategy = _department(org, "strategy")
    whiteboard = _whiteboard(company, owner)
    evaluation = EvaluationRun.objects.create(
        organization=org,
        company=company,
        profile_key="project-readiness",
        status="RUNNING",
        created_by=owner,
    )
    _card(
        whiteboard,
        strategy,
        visible=True,
        status="ready_for_review",
        links={"evaluation_run_id": str(evaluation.id)},
    )

    api_client.force_authenticate(user=owner)
    operator_response = api_client.get(f"/api/whiteboards/{whiteboard.id}/board")
    api_client.force_authenticate(user=customer)
    customer_response = api_client.get(f"/api/whiteboards/{whiteboard.id}/board")

    assert operator_response.status_code == 200
    operator_card = operator_response.json()["data"]["board"]["cards"][0]
    assert operator_card["review_kind"] == "automated_gate"
    assert operator_card["links"]["evaluation_run_id"] == str(evaluation.id)

    assert customer_response.status_code == 200
    customer_text = str(customer_response.json()).lower()
    customer_card = customer_response.json()["data"]["board"]["cards"][0]
    assert customer_card["review_kind"] == "department"
    assert "evaluation_run_id" not in customer_card["links"]
    assert str(evaluation.id) not in customer_text


def test_other_client_cannot_access_board_or_update_wrong_company_card(api_client) -> None:
    org = Organization.objects.create(name="Atlas")
    owner = _user(org, "board-api-scope-owner@example.com", "owner")
    other_user = _user(org, "board-api-scope-other@example.com", "viewer")
    company = _company(org, owner)
    other_company = _company(org, owner, name="Other Client")
    _assign(org, company, owner, "member")
    _assign(org, other_company, other_user, "member")
    strategy = _department(org, "strategy")
    whiteboard = _whiteboard(company, owner)
    leaked_link = str(uuid4())
    card = _card(
        whiteboard,
        strategy,
        status="ready_for_review",
        links={"evaluation_run_id": leaked_link},
    )

    api_client.force_authenticate(user=other_user)
    get_response = api_client.get(f"/api/whiteboards/{whiteboard.id}/board")
    patch_response = api_client.patch(
        f"/api/whiteboards/{whiteboard.id}/board/cards/{card.id}",
        data={"status": "in_progress"},
        format="json",
    )

    assert get_response.status_code == 404
    assert patch_response.status_code == 404
    assert leaked_link not in str(get_response.content)
