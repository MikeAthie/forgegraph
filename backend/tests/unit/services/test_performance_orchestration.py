from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from application.services.operating_model_packs import install_pack_for_company
from application.services.performance_orchestration import (
    PerformanceOrchestrationError,
    create_performance_report,
    evaluate_performance,
    list_performance_state,
    start_performance_review_for_whiteboard,
)
from infrastructure.orm.models import (
    CompanyAccessPolicy,
    CompanyAssignment,
    CompanyOperatingModelInstallation,
    CompanySignal,
    Graph,
    MetricSnapshot,
    OperatingModelPackRelease,
    Organization,
    OrganizationMembership,
    ReportRun,
    StateProjection,
    TaskRoutingRecord,
    ToolExecution,
    User,
    WorkWhiteboard,
)
from tests.fixtures.performance_policies import (
    atlas_launch_performance_policy,
    non_marketing_performance_policy,
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


def _whiteboard(company: Graph, owner: User, *, status: str = WorkWhiteboard.STATUS_IN_APPROVAL) -> WorkWhiteboard:
    return WorkWhiteboard.objects.create(
        organization=company.organization,
        company=company,
        status=status,
        request_type="service_request",
        client_name=company.name,
        request_summary="Review configured performance.",
        objective="Measure and route optimization through configured policy.",
        completion_score=100,
        created_by=owner,
    )


def _deployment_projection(whiteboard: WorkWhiteboard, *, status: str = "partial") -> None:
    StateProjection.objects.update_or_create(
        organization=whiteboard.organization,
        company=whiteboard.company,
        program=None,
        projection_type=f"whiteboard_deployment:{whiteboard.id}",
        defaults={
            "display_label": "Whiteboard deployment",
            "source_refs_json": [{"whiteboard_id": str(whiteboard.id)}],
            "json_state": {"whiteboard_id": str(whiteboard.id), "status": status},
            "markdown_summary": "Deployment evidence for performance tests.",
            "generated_by": "system",
        },
    )


def _install_policy_pack(
    *,
    company: Graph,
    user: User,
    policy: dict[str, object],
    connectors: list[str] | None = None,
) -> None:
    install_pack_for_company(
        company=company,
        user=user,
        pack_id="digital_marketing_pro.v1",
        config={
            "skip_graph_version": True,
            "performance_policies": [policy],
            "available_connectors": list(connectors or []),
        },
        role="primary",
    )


def _install_synthetic_policy(company: Graph, policy: dict[str, object]) -> None:
    release = OperatingModelPackRelease.objects.create(
        pack_id=f"synthetic-performance-pack:{company.id}",
        base_pack_id=str(policy["pack_id"]),
        version="1.0.0",
        display_name="Synthetic Performance Pack",
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


def test_atlas_policy_collects_available_source_and_blocks_missing_connectors() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "performance-atlas@example.com", "owner")
    company = _company(org, owner)
    _assign(org, company, owner, "member")
    policy = atlas_launch_performance_policy()
    _install_policy_pack(company=company, user=owner, policy=policy, connectors=["email_service_connector"])
    whiteboard = _whiteboard(company, owner)
    _deployment_projection(whiteboard, status="partial")

    contract = start_performance_review_for_whiteboard(user=owner, whiteboard=whiteboard)
    sources = {item["id"]: item for item in contract["sources"]}

    assert contract["policy_id"] == policy["policy_id"]
    assert contract["status"] == "partial"
    assert sources["email"]["status"] == "collected"
    assert sources["email"]["tool_execution_id"]
    assert sources["email"]["metrics"]["execution_completeness"] == 86
    assert sources["whatsapp"]["status"] == "blocked"
    assert sources["whatsapp"]["blocked_reason_code"] == "missing_metric_connector"
    assert ToolExecution.objects.filter(tool_name="dmp.email_draft_send_schedule").count() == 1
    assert MetricSnapshot.objects.filter(company=company, metric_sources_json__whiteboard_id=str(whiteboard.id)).count() == 1
    assert CompanySignal.objects.filter(company=company, metadata_json__reason_code="missing_metric_connector").exists()
    assert TaskRoutingRecord.objects.filter(company=company, metadata_json__blocked_reason_code="missing_metric_connector").exists()
    assert not ToolExecution.objects.exclude(tool_name="dmp.email_draft_send_schedule").exists()


def test_report_evaluation_and_routing_are_created_from_policy() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "performance-eval@example.com", "owner")
    company = _company(org, owner)
    _assign(org, company, owner, "member")
    policy = atlas_launch_performance_policy()
    _install_policy_pack(company=company, user=owner, policy=policy, connectors=["email_service_connector"])
    whiteboard = _whiteboard(company, owner)
    _deployment_projection(whiteboard, status="prepared")

    start_performance_review_for_whiteboard(user=owner, whiteboard=whiteboard)
    reported = create_performance_report(user=owner, whiteboard=whiteboard)
    evaluation = evaluate_performance(
        user=owner,
        whiteboard=whiteboard,
        scorecard={"conditions": ["poor_audience_fit"]},
    )
    state = list_performance_state(user=owner, whiteboard=whiteboard)

    assert reported["current_state"]["report_run_id"]
    assert evaluation.status == "PASS"
    assert state["current_state"]["evaluation_id"] == str(evaluation.id)
    assert ReportRun.objects.filter(company=company).count() == 1
    assert TaskRoutingRecord.objects.filter(
        company=company,
        metadata_json__condition="poor_audience_fit",
        to_department__slug="strategy",
    ).exists()
    assert TaskRoutingRecord.objects.filter(
        company=company,
        metadata_json__condition="missing_metric_connector",
        to_department__slug="deployment-ops",
    ).exists()


def test_duplicate_start_is_idempotent() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "performance-idempotent@example.com", "owner")
    company = _company(org, owner)
    _assign(org, company, owner, "member")
    _install_policy_pack(
        company=company,
        user=owner,
        policy=atlas_launch_performance_policy(),
        connectors=["email_service_connector"],
    )
    whiteboard = _whiteboard(company, owner)
    _deployment_projection(whiteboard, status="executed")

    first = start_performance_review_for_whiteboard(user=owner, whiteboard=whiteboard)
    second = start_performance_review_for_whiteboard(user=owner, whiteboard=whiteboard)

    assert first["current_state"]["metric_snapshot_id"] == second["current_state"]["metric_snapshot_id"]
    assert ToolExecution.objects.filter(tool_name="dmp.email_draft_send_schedule").count() == 1
    assert MetricSnapshot.objects.filter(company=company).count() == 1


def test_other_client_cannot_access_performance_state() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "performance-owner@example.com", "owner")
    other = _user(org, "performance-other@example.com", "viewer")
    company = _company(org, owner)
    other_company = _company(org, owner, name="Other Client")
    _assign(org, company, owner, "member")
    _assign(org, other_company, other, "viewer")
    _install_policy_pack(company=company, user=owner, policy=atlas_launch_performance_policy())
    whiteboard = _whiteboard(company, owner)

    with pytest.raises(PerformanceOrchestrationError, match="access"):
        list_performance_state(user=other, whiteboard=whiteboard)


def test_non_marketing_policy_works_without_metric_specific_logic() -> None:
    org = Organization.objects.create(name="Legal Ops")
    owner = _user(org, "performance-legal@example.com", "owner")
    company = _company(org, owner, name="Legal Client")
    _assign(org, company, owner, "member")
    policy = non_marketing_performance_policy()
    _install_synthetic_policy(company, policy)
    whiteboard = _whiteboard(company, owner)
    _deployment_projection(whiteboard, status="prepared")

    start_performance_review_for_whiteboard(user=owner, whiteboard=whiteboard)
    evaluation = evaluate_performance(user=owner, whiteboard=whiteboard)

    assert evaluation.status == "PASS"
    snapshot = MetricSnapshot.objects.get(company=company)
    assert snapshot.metric_values_json["review_completion_score"] == 96
    assert not CompanySignal.objects.filter(company=company).exists()


def test_status_gate_blocks_without_required_status_or_deployment_evidence() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "performance-status@example.com", "owner")
    company = _company(org, owner)
    _assign(org, company, owner, "member")
    _install_policy_pack(company=company, user=owner, policy=atlas_launch_performance_policy())
    whiteboard = _whiteboard(company, owner, status=WorkWhiteboard.STATUS_IN_APPROVAL)

    with pytest.raises(PerformanceOrchestrationError, match="status"):
        start_performance_review_for_whiteboard(user=owner, whiteboard=whiteboard)


def test_core_performance_service_has_no_policy_metric_literals() -> None:
    service_path = Path(__file__).resolve().parents[3] / "application" / "services" / "performance_orchestration.py"
    service_text = service_path.read_text(encoding="utf-8")

    for forbidden in (
        "atlas_agency_ops",
        "open_rate",
        "click_rate",
        "unsubscribe_rate",
        "whatsapp",
        "instagram",
        "landing_page",
        "email_service_connector",
        "social_analytics_connector",
        "channel_signal_quality",
        "optimization_confidence",
    ):
        assert forbidden not in service_text
