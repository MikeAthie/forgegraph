from __future__ import annotations

from typing import cast

import pytest

from application.services.product_operations import (
    begin_product_operation,
    complete_product_operation,
    contract_operation_metadata,
    fail_product_operation,
    get_product_operation_for_user,
    operation_payload,
)
from infrastructure.orm.models import (
    CompanyAccessPolicy,
    CompanyAssignment,
    Graph,
    Organization,
    OrganizationMembership,
    ProductOperation,
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


def _whiteboard(company: Graph, owner: User) -> WorkWhiteboard:
    organization = company.organization
    assert organization is not None
    return WorkWhiteboard.objects.create(
        organization=organization,
        company=company,
        status=WorkWhiteboard.STATUS_READY_FOR_STRATEGY,
        request_type="service_request",
        client_name=company.name,
        request_summary="Track durable operation lifecycle.",
        objective="Expose operation readiness.",
        completion_score=100,
        created_by=owner,
    )


def test_begin_product_operation_is_created_and_idempotent() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "product-operation-owner@example.com", "owner")
    company = _company(org, owner)
    _assign(org, company, owner, "member")
    whiteboard = _whiteboard(company, owner)

    first, first_created = begin_product_operation(
        user=owner,
        whiteboard=whiteboard,
        kind="phase_start",
        target_type="phase_contract",
        target_id="digital_marketing_pro.v1.atlas_agency_work_graph",
        idempotency_key="phase-start-1",
    )
    second, second_created = begin_product_operation(
        user=owner,
        whiteboard=whiteboard,
        kind="phase_start",
        target_type="phase_contract",
        target_id="digital_marketing_pro.v1.atlas_agency_work_graph",
        idempotency_key="phase-start-1",
    )

    assert first_created is True
    assert second_created is False
    assert second.id == first.id
    assert first.status == ProductOperation.STATUS_RUNNING
    assert first.organization == org
    assert first.company == company
    assert first.whiteboard == whiteboard


def test_complete_product_operation_advances_contract_revision_and_counts() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "product-operation-complete@example.com", "owner")
    company = _company(org, owner)
    _assign(org, company, owner, "member")
    whiteboard = _whiteboard(company, owner)
    operation, _created = begin_product_operation(
        user=owner,
        whiteboard=whiteboard,
        kind="deployment_prepare",
        target_type="deployment_contract",
        target_id="digital_marketing_pro.v1.atlas_launch_deployment",
        idempotency_key="deployment-prepare-1",
    )

    complete_product_operation(operation, metadata={"receipt": "prepared"})
    operation.refresh_from_db()
    metadata = contract_operation_metadata(
        whiteboard=whiteboard,
        target_type="deployment_contract",
        target_id="digital_marketing_pro.v1.atlas_launch_deployment",
    )

    assert operation.status == ProductOperation.STATUS_COMPLETED
    assert operation.contract_revision_at_accept == 0
    assert operation.contract_revision_at_completion == 1
    assert operation.metadata_json["receipt"] == "prepared"
    assert metadata["contract_revision"] == 1
    assert metadata["last_operation_id"] == str(operation.id)
    assert metadata["terminal"] is True
    assert metadata["running_count"] == 0
    assert metadata["completed_count"] == 1


def test_failed_product_operation_records_error_payload() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "product-operation-failed@example.com", "owner")
    company = _company(org, owner)
    _assign(org, company, owner, "member")
    whiteboard = _whiteboard(company, owner)
    operation, _created = begin_product_operation(
        user=owner,
        whiteboard=whiteboard,
        kind="performance_start",
        target_type="performance_contract",
        target_id="digital_marketing_pro.v1.atlas_performance_review",
        idempotency_key="performance-start-1",
    )

    fail_product_operation(
        operation,
        error_code="performance_deployment_required",
        error_message="Deployment evidence is required before performance review.",
    )
    operation.refresh_from_db()
    payload = operation_payload(operation)

    assert operation.status == ProductOperation.STATUS_FAILED
    assert operation.failed_at is not None
    assert operation.contract_revision_at_completion == 1
    assert payload["error"] == {
        "code": "performance_deployment_required",
        "message": "Deployment evidence is required before performance review.",
    }


def test_product_operation_lookup_is_company_scoped() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "product-operation-scope-owner@example.com", "owner")
    other_user = _user(org, "product-operation-scope-other@example.com", "viewer")
    company = _company(org, owner)
    other_company = _company(org, owner, name="Other Client")
    _assign(org, company, owner, "member")
    _assign(org, other_company, other_user, "viewer")
    whiteboard = _whiteboard(company, owner)
    operation, _created = begin_product_operation(
        user=owner,
        whiteboard=whiteboard,
        kind="phase_synthesize",
        target_type="phase_contract",
        target_id="digital_marketing_pro.v1.atlas_agency_work_graph",
        idempotency_key="phase-synthesize-1",
    )

    visible = get_product_operation_for_user(
        user=owner,
        whiteboard=whiteboard,
        operation_id=str(operation.id),
    )
    hidden = get_product_operation_for_user(
        user=other_user,
        whiteboard=whiteboard,
        operation_id=str(operation.id),
    )

    assert visible == operation
    assert hidden is None
