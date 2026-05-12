from __future__ import annotations

from typing import cast
from uuid import uuid4

import pytest
from django.utils import timezone

from application.services.tenancy import ensure_default_organization
from infrastructure.crypto.encryption import encrypt_api_key
from infrastructure.orm.models import (
    APIKey,
    ApprovalTask,
    CompanyAccessPolicy,
    CompanyAssignment,
    Graph,
    GraphVersion,
    OrganizationMembership,
    PeriodicReviewDefinition,
    Run,
    TaskRecord,
    User,
)

pytestmark = pytest.mark.django_db


def _company(user: User, name: str) -> Graph:
    organization = user.default_organization
    assert organization is not None
    return cast(
        Graph,
        Graph.objects.create(
            owner=user,
            organization=organization,
            name=name,
            description=f"{name} operating company.",
        ),
    )


def _member_in_org(owner: User, *, role: str = "viewer") -> User:
    organization = owner.default_organization
    assert organization is not None
    member = User.objects.create_user(
        email=f"member-{uuid4().hex}@example.com",
        password="testpassword123",
    )
    ensure_default_organization(member)
    member.default_organization = organization
    member.save(update_fields=["default_organization"])
    OrganizationMembership.objects.update_or_create(
        organization=organization,
        user=member,
        defaults={"role": role, "is_default": True},
    )
    return member


def _run_for_company(owner: User, company: Graph, *, status: str = "running") -> Run:
    version = GraphVersion.objects.create(
        graph=company,
        version=1,
        graph_json={"nodes": [], "edges": [], "metadata": {}},
    )
    return Run.objects.create(
        owner=owner,
        organization=company.organization,
        graph_version=version,
        status=status,
        started_at=timezone.now(),
    )


def _add_company_operating_records(owner: User, company: Graph) -> None:
    run = _run_for_company(owner, company)
    ApprovalTask.objects.create(
        run=run,
        node_id="human_gate",
        assignee=owner,
        status="pending",
        payload={"prompt_message": "Approve next step"},
    )
    TaskRecord.objects.create(
        organization=company.organization,
        execution=run,
        source_node_id="planning",
        external_key=f"{run.id}:planning",
        title="Planning task",
        status="waiting_for_decision",
        priority="high",
        summary="Waiting for a company decision.",
    )
    PeriodicReviewDefinition.objects.create(
        organization=company.organization,
        company=company,
        pack_id="generic_ops.v1",
        template_id=f"review-{company.id}",
        display_name=f"{company.name} monthly review",
        cadence="monthly",
        enabled=True,
    )


def test_portfolio_health_and_queues_are_company_assignment_filtered(api_client, user):
    allowed = _company(user, "Allowed Client")
    hidden = _company(user, "Hidden Client")
    member = _member_in_org(user)
    CompanyAccessPolicy.objects.create(
        organization=allowed.organization,
        company=allowed,
        assignment_required=True,
        org_admin_access_enabled=False,
    )
    CompanyAccessPolicy.objects.create(
        organization=hidden.organization,
        company=hidden,
        assignment_required=True,
        org_admin_access_enabled=False,
    )
    CompanyAssignment.objects.create(
        organization=allowed.organization,
        company=allowed,
        user=member,
        role="viewer",
        status="active",
        created_by=user,
    )
    _add_company_operating_records(user, allowed)
    _add_company_operating_records(user, hidden)

    api_client.force_authenticate(user=member)
    health_response = api_client.get("/api/portfolio-health")
    assert health_response.status_code == 200
    health = health_response.data["data"]
    company_ids = {row["company_id"] for row in health["companies"]}
    assert company_ids == {str(allowed.id)}
    allowed_row = health["companies"][0]
    assert allowed_row["pending_approval_count"] == 1
    assert allowed_row["pending_task_count"] == 1
    assert allowed_row["metric_gap_count"] == 1
    assert allowed_row["credential_health"]["status"] == "missing"
    assert health["summary"]["total_companies"] == 1

    queue_response = api_client.get("/api/cross-company-queues", {"type": "all"})
    assert queue_response.status_code == 200
    queues = queue_response.data["data"]["queues"]
    for rows in queues.values():
        assert {row["company_id"] for row in rows} <= {str(allowed.id)}
    assert queues["approvals"][0]["approval_id"]
    assert queues["metric_gaps"][0]["gap"] == "missing_metric_snapshot"
    assert queues["credentials"][0]["status"] == "missing"


def test_company_assignment_create_and_revoke_changes_company_access_immediately(api_client, user):
    company = _company(user, "Restricted Client")
    member = _member_in_org(user)
    CompanyAccessPolicy.objects.create(
        organization=company.organization,
        company=company,
        assignment_required=True,
        org_admin_access_enabled=True,
    )

    api_client.force_authenticate(user=member)
    hidden_response = api_client.get(f"/api/graphs/{company.id}")
    assert hidden_response.status_code == 404

    api_client.force_authenticate(user=user)
    create_response = api_client.post(
        "/api/company-assignments",
        {
            "company_id": str(company.id),
            "user_id": str(member.id),
            "role": "viewer",
            "status": "active",
        },
        format="json",
    )
    assert create_response.status_code == 201
    assignment = create_response.data["data"]["assignment"]

    api_client.force_authenticate(user=member)
    visible_response = api_client.get(f"/api/graphs/{company.id}")
    assert visible_response.status_code == 200

    api_client.force_authenticate(user=user)
    revoke_response = api_client.patch(
        f"/api/company-assignments/{assignment['id']}",
        {"status": "inactive"},
        format="json",
    )
    assert revoke_response.status_code == 200

    api_client.force_authenticate(user=member)
    revoked_response = api_client.get(f"/api/graphs/{company.id}")
    assert revoked_response.status_code == 404


def test_credential_health_never_exposes_secret_material(authenticated_client, user):
    organization = user.default_organization
    assert organization is not None
    company = _company(user, "Credential Client")
    APIKey.objects.create(
        organization=organization,
        user=user,
        provider="openai",
        name="OpenAI",
        encrypted_key=encrypt_api_key("sk-test-secret"),
    )

    response = authenticated_client.get("/api/credential-health")
    assert response.status_code == 200
    payload = response.data["data"]
    company_health = next(item for item in payload["companies"] if item["company_id"] == str(company.id))
    assert company_health["status"] == "healthy"
    serialized = str(payload)
    assert "sk-test-secret" not in serialized
    assert "key_hint" not in serialized
