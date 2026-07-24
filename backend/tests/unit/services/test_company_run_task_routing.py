from __future__ import annotations

from typing import cast

import pytest

from application.services.company_run_task_routing import (
    TASK_METADATA_KEY,
    TASK_ROUTING_PROVENANCE_KEY,
    TASK_SNAPSHOT_METADATA_KEY,
    attach_deliverable_to_stage_task,
    bootstrap_task_routing_for_program,
    mark_task_completed,
    mark_task_failed,
    mark_task_running,
)
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import (
    Asset,
    AssetVersion,
    CompanyProgram,
    DepartmentRegistry,
    Graph,
    Organization,
    ProgramStageState,
    ServiceCatalogItem,
    ServiceDeliverable,
    ServiceEngagement,
    TaskRoutingRecord,
    User,
    WorkWhiteboard,
)

pytestmark = pytest.mark.django_db


def _organization(user: User) -> Organization:
    ensure_default_organization(user)
    organization = user.default_organization
    assert organization is not None
    return organization


def _company(user: User) -> Graph:
    organization = _organization(user)
    return cast(
        Graph,
        Graph.objects.create(
            owner=user,
            organization=organization,
            name="Northstar Advisory",
            description="Consulting client.",
        ),
    )


def _engagement(user: User, company: Graph) -> ServiceEngagement:
    organization = _organization(user)
    catalog = ServiceCatalogItem.objects.create(
        organization=organization,
        slug="consulting-assessment",
        title="Consulting Assessment",
        status="active",
        visibility="organization",
        created_by=user,
    )
    return ServiceEngagement.objects.create(
        organization=organization,
        company=company,
        catalog_item=catalog,
        status="in_progress",
        customer_status="working",
        public_summary="Assess operations and recommend improvements.",
        requested_by=user,
    )


def _program(user: User, company: Graph, engagement: ServiceEngagement) -> CompanyProgram:
    organization = _organization(user)
    program = CompanyProgram.objects.create(
        organization=organization,
        company=company,
        template_id="consulting.assessment.v1",
        display_label="Company Run",
        title="Operations Assessment",
        objective="Turn a single consulting prompt into staged work.",
        status="active",
        current_stage_id="discovery",
        external_key="consulting-assessment-test",
        metadata_json={"service_engagement_id": str(engagement.id)},
        created_by=user,
    )
    ProgramStageState.objects.create(
        organization=organization,
        company=company,
        program=program,
        stage_id="discovery",
        label="Discovery",
        sequence=1,
        status="not_started",
        state_json={
            "task_title": "Scope Discovery",
            "department_slug": "advisory-intake",
        },
    )
    ProgramStageState.objects.create(
        organization=organization,
        company=company,
        program=program,
        stage_id="analysis",
        label="Analysis",
        sequence=2,
        status="not_started",
        state_json={},
    )
    ProgramStageState.objects.create(
        organization=organization,
        company=company,
        program=program,
        stage_id="recommendation",
        label="Recommendation",
        sequence=3,
        status="not_started",
        state_json={"metadata": {"title": "Recommendation Brief"}},
    )
    return program


def _whiteboard(user: User, company: Graph, engagement: ServiceEngagement) -> WorkWhiteboard:
    organization = _organization(user)
    return WorkWhiteboard.objects.create(
        organization=organization,
        company=company,
        service_engagement=engagement,
        status=WorkWhiteboard.STATUS_IN_STRATEGY,
        work_status=WorkWhiteboard.WORK_STATUS_PLANNING,
        request_type="consulting_assessment",
        project_name="Operations Assessment",
        objective="Assess current operations and recommend changes.",
        created_by=user,
    )


def test_bootstrap_creates_agnostic_stage_task_cards_and_whiteboard_snapshot(user):
    company = _company(user)
    organization = _organization(user)
    engagement = _engagement(user, company)
    whiteboard = _whiteboard(user, company, engagement)
    DepartmentRegistry.objects.create(
        organization=organization,
        slug="advisory-intake",
        name="Advisory Intake",
        department_type="consulting",
    )
    program = _program(user, company, engagement)

    records = bootstrap_task_routing_for_program(
        program,
        whiteboard=whiteboard,
        created_by=user,
        run_context={"source": "synthetic_test", "runtime_provider": "local_runner"},
    )
    again = bootstrap_task_routing_for_program(program, whiteboard=whiteboard, created_by=user)

    assert len(records) == 3
    assert {record.id for record in records} == {record.id for record in again}
    assert TaskRoutingRecord.objects.filter(company=company).count() == 3
    by_stage = {record.metadata_json[TASK_METADATA_KEY]["stage_id"]: record for record in records}
    assert by_stage["discovery"].metadata_json["title"] == "Scope Discovery"
    assert by_stage["analysis"].to_department.slug == "analysis"
    assert by_stage["recommendation"].metadata_json["title"] == "Recommendation Brief"
    assert by_stage["discovery"].metadata_json[TASK_METADATA_KEY]["status"] == "ready"
    assert by_stage["analysis"].metadata_json[TASK_METADATA_KEY]["dependencies"] == ["discovery"]
    assert by_stage["analysis"].metadata_json[TASK_METADATA_KEY]["status"] == "blocked"
    assert by_stage["recommendation"].metadata_json[TASK_METADATA_KEY]["dependencies"] == [
        "analysis"
    ]
    assert DepartmentRegistry.objects.filter(
        organization=organization,
        slug="analysis",
        department_type="program_stage",
    ).exists()

    for stage in ProgramStageState.objects.filter(program=program):
        task_state = stage.state_json[TASK_METADATA_KEY]
        assert task_state["routing_record_id"]
        assert task_state["status"] in {"ready", "blocked"}

    whiteboard.refresh_from_db()
    snapshot = whiteboard.metadata_json[TASK_SNAPSHOT_METADATA_KEY]
    assert snapshot["program_id"] == str(program.id)
    assert [task["stage_id"] for task in snapshot["tasks"]] == [
        "discovery",
        "analysis",
        "recommendation",
    ]


def test_stage_task_status_and_deliverable_provenance_are_linked(user):
    company = _company(user)
    organization = _organization(user)
    engagement = _engagement(user, company)
    whiteboard = _whiteboard(user, company, engagement)
    program = _program(user, company, engagement)
    bootstrap_task_routing_for_program(program, whiteboard=whiteboard, created_by=user)
    stage = ProgramStageState.objects.get(program=program, stage_id="discovery")

    running = mark_task_running(stage, actor=user)
    running.refresh_from_db()
    assert running.status == "in_progress"
    assert running.metadata_json[TASK_METADATA_KEY]["status"] == "running"

    asset = Asset.objects.create(
        organization=organization,
        company=company,
        title="Discovery notes",
        asset_type="document",
        created_by_type="system",
    )
    version = AssetVersion.objects.create(
        asset=asset,
        version_number=1,
        content_uri="forgegraph://synthetic/discovery.md",
        content_hash="discovery-hash",
        mime_type="text/markdown",
        size_bytes=128,
        provenance_json={"source": "synthetic"},
    )
    deliverable = ServiceDeliverable.objects.create(
        organization=organization,
        company=company,
        engagement=engagement,
        title="Discovery Notes",
        deliverable_type="discovery_notes",
        artifact=asset,
        created_by=user,
    )

    attach_deliverable_to_stage_task(
        stage,
        deliverable,
        asset_versions=[version],
        runtime_provider="synthetic_runtime",
    )
    completed = mark_task_completed(stage, actor=user)

    deliverable.refresh_from_db()
    version.refresh_from_db()
    completed.refresh_from_db()
    provenance = deliverable.metadata_json[TASK_ROUTING_PROVENANCE_KEY]
    assert provenance["routing_record_id"] == str(running.id)
    assert provenance["runtime_provider"] == "synthetic_runtime"
    assert version.provenance_json[TASK_ROUTING_PROVENANCE_KEY]["stage_id"] == "discovery"
    assert completed.metadata_json[TASK_METADATA_KEY]["status"] == "completed"

    failed = mark_task_failed(stage, "retryable downstream error", actor=user)
    failed.refresh_from_db()
    assert failed.metadata_json[TASK_METADATA_KEY]["status"] == "failed"
    assert "retryable downstream error" in failed.resolution_json["error_message"]
