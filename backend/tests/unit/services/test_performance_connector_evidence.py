from __future__ import annotations

from typing import Any, cast

import pytest

from application.services.operating_model_packs import install_pack_for_company
from application.services.performance_orchestration import (
    PerformanceOrchestrationError,
    start_performance_review_for_whiteboard,
)
from infrastructure.orm.models import (
    CompanyAccessPolicy,
    CompanyAssignment,
    Graph,
    MetricSnapshot,
    Organization,
    OrganizationMembership,
    ReportRun,
    StateProjection,
    User,
    WorkWhiteboard,
)
from tests.fixtures.performance_policies import atlas_launch_performance_policy
from tests.helpers.organizations import required_company_organization

pytestmark = pytest.mark.django_db


def _user(org: Organization, email: str) -> User:
    user = User.objects.create_user(email=email, password="testpassword123")
    user.default_organization = org
    user.save(update_fields=["default_organization"])
    OrganizationMembership.objects.create(
        organization=org, user=user, role="owner", is_default=True
    )
    return user


def _company(org: Organization, owner: User, *, name: str) -> Graph:
    company = cast(Graph, Graph.objects.create(owner=owner, organization=org, name=name))
    CompanyAccessPolicy.objects.create(
        organization=org,
        company=company,
        assignment_required=True,
        org_admin_access_enabled=True,
    )
    CompanyAssignment.objects.create(
        organization=org,
        company=company,
        user=owner,
        role="member",
        status="active",
    )
    return company


def _whiteboard(company: Graph, owner: User) -> WorkWhiteboard:
    return WorkWhiteboard.objects.create(
        organization=required_company_organization(company),
        company=company,
        status=WorkWhiteboard.STATUS_IN_APPROVAL,
        request_type="service_request",
        client_name=company.name,
        request_summary="Connector evidence performance review.",
        objective="Verify connector evidence gates performance.",
        completion_score=100,
        created_by=owner,
    )


def _install_performance_policy(
    company: Graph, owner: User, *, sandbox_allowed: bool, manual_allowed: bool = False
) -> None:
    policy = atlas_launch_performance_policy()
    policy["allow_sandbox_deployment_evidence"] = sandbox_allowed
    policy["allow_manual_publish_deployment_evidence"] = manual_allowed
    install_pack_for_company(
        company=company,
        user=owner,
        pack_id="digital_marketing_pro.v1",
        config={
            "skip_graph_version": True,
            "performance_policies": [policy],
            "available_connectors": ["email_connector"],
        },
        role="primary",
    )


def _deployment_projection(whiteboard: WorkWhiteboard, *, channel: dict[str, Any]) -> None:
    StateProjection.objects.update_or_create(
        organization=whiteboard.organization,
        company=whiteboard.company,
        program=None,
        projection_type=f"whiteboard_deployment:{whiteboard.id}",
        defaults={
            "display_label": "Whiteboard deployment",
            "source_refs_json": [{"whiteboard_id": str(whiteboard.id)}],
            "json_state": {
                "whiteboard_id": str(whiteboard.id),
                "status": "partial",
                "channels": [channel],
                "policy": {"channels": [channel]},
            },
            "markdown_summary": "Connector evidence projection.",
            "generated_by": "system",
        },
    )


def test_sandbox_connector_evidence_unlocks_performance_only_when_policy_allows() -> None:
    org = Organization.objects.create(name="Performance Connector Org")
    owner = _user(org, "performance-sandbox-contract@example.com")
    blocked_company = _company(org, owner, name="Sandbox Disallowed")
    _install_performance_policy(blocked_company, owner, sandbox_allowed=False)
    blocked_whiteboard = _whiteboard(blocked_company, owner)
    _deployment_projection(
        blocked_whiteboard,
        channel={
            "id": "email",
            "status": "executed",
            "tool_id": "email.send_dry_run",
            "allow_sandbox_evidence": False,
            "receipt": {
                "result": {
                    "provider": "fake",
                    "mode": "dry_run",
                    "evidence_mode": "sandbox",
                    "status": "dry_run",
                }
            },
        },
    )

    with pytest.raises(PerformanceOrchestrationError, match="status"):
        start_performance_review_for_whiteboard(user=owner, whiteboard=blocked_whiteboard)
    assert not MetricSnapshot.objects.filter(company=blocked_company).exists()

    allowed_company = _company(org, owner, name="Sandbox Allowed")
    _install_performance_policy(allowed_company, owner, sandbox_allowed=True)
    allowed_whiteboard = _whiteboard(allowed_company, owner)
    _deployment_projection(
        allowed_whiteboard,
        channel={
            "id": "email",
            "status": "executed",
            "tool_id": "email.send_dry_run",
            "allow_sandbox_evidence": True,
            "receipt": {
                "result": {
                    "provider": "fake",
                    "mode": "dry_run",
                    "evidence_mode": "sandbox",
                    "status": "dry_run",
                }
            },
        },
    )

    contract = start_performance_review_for_whiteboard(user=owner, whiteboard=allowed_whiteboard)

    assert contract["current_state"]["metric_snapshot_id"]
    assert MetricSnapshot.objects.filter(company=allowed_company).exists()


def test_manual_connector_evidence_unlocks_performance_only_when_policy_allows() -> None:
    org = Organization.objects.create(name="Performance Manual Connector Org")
    owner = _user(org, "performance-manual-contract@example.com")
    company = _company(org, owner, name="Manual Evidence Allowed")
    _install_performance_policy(company, owner, sandbox_allowed=False, manual_allowed=True)
    whiteboard = _whiteboard(company, owner)
    _deployment_projection(
        whiteboard,
        channel={
            "id": "community_notice",
            "status": "executed",
            "tool_id": "social.manual_publish_record",
            "allow_manual_publish_evidence": True,
            "receipt": {
                "result": {
                    "provider": "manual",
                    "mode": "manual_publish_record",
                    "evidence_mode": "manual_publish",
                    "status": "recorded",
                    "asset_count": 1,
                }
            },
        },
    )

    contract = start_performance_review_for_whiteboard(user=owner, whiteboard=whiteboard)

    assert contract["current_state"]["metric_snapshot_id"]
    assert MetricSnapshot.objects.filter(company=company).exists()


def test_blocked_or_failed_connector_evidence_never_unlocks_metrics_or_reports() -> None:
    org = Organization.objects.create(name="Performance Failed Connector Org")
    owner = _user(org, "performance-failed-contract@example.com")
    company = _company(org, owner, name="Failed Evidence")
    _install_performance_policy(company, owner, sandbox_allowed=True, manual_allowed=True)
    whiteboard = _whiteboard(company, owner)
    _deployment_projection(
        whiteboard,
        channel={
            "id": "email",
            "status": "blocked",
            "tool_id": "email.send_dry_run",
            "allow_sandbox_evidence": True,
            "receipt": {
                "result": {
                    "provider": "fake",
                    "mode": "dry_run",
                    "evidence_mode": "sandbox",
                    "status": "failed",
                }
            },
        },
    )

    with pytest.raises(PerformanceOrchestrationError, match="status"):
        start_performance_review_for_whiteboard(user=owner, whiteboard=whiteboard)

    assert not MetricSnapshot.objects.filter(company=company).exists()
    assert not ReportRun.objects.filter(company=company).exists()
