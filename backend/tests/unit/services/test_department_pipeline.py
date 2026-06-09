from __future__ import annotations

from typing import cast
from uuid import uuid4

import pytest

from application.services.department_pipeline import (
    DepartmentPipelineError,
    attach_asset_to_stage,
    attach_deliverable_to_stage,
    complete_stage,
    create_pipeline_for_engagement,
    get_pipeline_snapshot,
    skip_stage,
    stage_state_for_engagement,
    start_stage,
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
)

pytestmark = pytest.mark.django_db

_STAGE_SLUGS = [
    "strategy_research",
    "brand_content",
    "channel_execution",
    "crm_lifecycle",
    "analytics_performance",
    "qa_compliance",
    "client_approval_ops",
]


def _organization(user: User) -> Organization:
    ensure_default_organization(user)
    organization = user.default_organization
    assert organization is not None
    return organization


def _company(user: User, name: str = "Legacy") -> Graph:
    organization = _organization(user)
    return cast(
        Graph,
        Graph.objects.create(
            owner=user,
            organization=organization,
            name=name,
            description="Marketing client.",
        ),
    )


def _catalog_item(user: User) -> ServiceCatalogItem:
    organization = _organization(user)
    return ServiceCatalogItem.objects.create(
        organization=organization,
        slug=f"weekend-social-{uuid4().hex}",
        title="Weekend Social Launch",
        description="Fast social launch package.",
        status="active",
        visibility="customer",
        created_by=user,
    )


def _engagement(user: User, company: Graph) -> ServiceEngagement:
    return ServiceEngagement.objects.create(
        organization=company.organization,
        company=company,
        catalog_item=_catalog_item(user),
        status="in_progress",
        customer_status="working",
        public_summary="Create Legacy social launch deliverables.",
        requested_by=user,
    )


def _departments(user: User) -> dict[str, DepartmentRegistry]:
    organization = _organization(user)
    departments: dict[str, DepartmentRegistry] = {}
    for slug in _STAGE_SLUGS:
        departments[slug] = DepartmentRegistry.objects.create(
            organization=organization,
            slug=slug,
            name=slug.replace("_", " ").title(),
            department_type="atlas_agency",
            service_tags_json=["atlas", "digital_marketing_pro"],
        )
    return departments


def test_create_pipeline_reuses_existing_program_and_stage_primitives(user):
    _departments(user)
    engagement = _engagement(user, _company(user))

    program = create_pipeline_for_engagement(engagement, created_by=user)
    again = create_pipeline_for_engagement(engagement, created_by=user)

    assert program.id == again.id
    assert CompanyProgram.objects.filter(company=engagement.company).count() == 1
    routing_records = list(TaskRoutingRecord.objects.filter(company=engagement.company))
    assert len(routing_records) == 7
    stages = list(ProgramStageState.objects.filter(program=program).order_by("sequence"))
    assert [stage.stage_id for stage in stages] == [
        "strategy_research",
        "brand_content",
        "crm_lifecycle",
        "analytics_performance",
        "channel_execution",
        "qa_compliance",
        "client_approval_ops",
    ]
    assert stages[1].state_json["dependencies"] == ["strategy_research"]
    assert stages[-1].state_json["department_slug"] == "client_approval_ops"
    assert stages[0].state_json["company_run_task"]["status"] == "ready"
    assert stages[0].state_json["company_run_task"]["routing_record_id"]
    assert {record.metadata_json["company_run_task"]["stage_id"] for record in routing_records} == {
        stage.stage_id for stage in stages
    }


def test_create_pipeline_requires_all_atlas_departments(user):
    _organization(user)
    engagement = _engagement(user, _company(user))

    with pytest.raises(DepartmentPipelineError) as exc_info:
        create_pipeline_for_engagement(engagement, created_by=user)

    assert exc_info.value.code == "MISSING_DEPARTMENTS"
    assert "strategy_research" in exc_info.value.details[0]["missing_department_slugs"]


def test_stage_dependencies_allow_parallel_work_after_strategy(user):
    _departments(user)
    engagement = _engagement(user, _company(user))
    create_pipeline_for_engagement(engagement, created_by=user)

    brand = stage_state_for_engagement(engagement, "brand_content")
    with pytest.raises(DepartmentPipelineError) as exc_info:
        start_stage(brand, actor=user)
    assert exc_info.value.code == "DEPENDENCY_NOT_SATISFIED"

    strategy = stage_state_for_engagement(engagement, "strategy_research")
    start_stage(strategy, actor=user)
    complete_stage(strategy, outputs=[{"kind": "brief", "id": "strategy-brief"}], actor=user)

    brand_ready = stage_state_for_engagement(engagement, "brand_content")
    assert brand_ready.state_json["company_run_task"]["status"] == "ready"
    brand_route = TaskRoutingRecord.objects.get(
        id=brand_ready.state_json["company_run_task"]["routing_record_id"]
    )
    assert brand_route.metadata_json["company_run_task"]["status"] == "ready"

    for stage_id in ["brand_content", "crm_lifecycle", "analytics_performance"]:
        stage = stage_state_for_engagement(engagement, stage_id)
        start_stage(stage, actor=user)
        assert ProgramStageState.objects.get(id=stage.id).status == "in_progress"

    channel = stage_state_for_engagement(engagement, "channel_execution")
    with pytest.raises(DepartmentPipelineError):
        start_stage(channel, actor=user)


def test_crm_can_be_skipped_with_reason_and_qa_waits_for_dependencies(user):
    _departments(user)
    engagement = _engagement(user, _company(user))
    create_pipeline_for_engagement(engagement, created_by=user)

    strategy = stage_state_for_engagement(engagement, "strategy_research")
    start_stage(strategy, actor=user)
    complete_stage(strategy, actor=user)

    crm = stage_state_for_engagement(engagement, "crm_lifecycle")
    skip_stage(crm, reason="No CRM connector for weekend MVP.", actor=user)
    crm.refresh_from_db()
    assert crm.status == "completed"
    assert crm.state_json["skipped"] is True
    assert crm.state_json["skipped_reason"] == "No CRM connector for weekend MVP."

    qa = stage_state_for_engagement(engagement, "qa_compliance")
    with pytest.raises(DepartmentPipelineError):
        start_stage(qa, actor=user)

    brand = stage_state_for_engagement(engagement, "brand_content")
    start_stage(brand, actor=user)
    complete_stage(brand, actor=user)
    channel = stage_state_for_engagement(engagement, "channel_execution")
    start_stage(channel, actor=user)
    complete_stage(channel, actor=user)
    analytics = stage_state_for_engagement(engagement, "analytics_performance")
    start_stage(analytics, actor=user)
    complete_stage(analytics, actor=user)

    start_stage(qa, actor=user)
    assert ProgramStageState.objects.get(id=qa.id).status == "in_progress"


def test_approval_requires_completed_qa(user):
    _departments(user)
    engagement = _engagement(user, _company(user))
    create_pipeline_for_engagement(engagement, created_by=user)

    strategy = stage_state_for_engagement(engagement, "strategy_research")
    start_stage(strategy, actor=user)
    complete_stage(strategy, actor=user)
    brand = stage_state_for_engagement(engagement, "brand_content")
    start_stage(brand, actor=user)
    complete_stage(brand, actor=user)
    crm = stage_state_for_engagement(engagement, "crm_lifecycle")
    skip_stage(crm, reason="manual sales scripts deferred", actor=user)
    analytics = stage_state_for_engagement(engagement, "analytics_performance")
    start_stage(analytics, actor=user)
    complete_stage(analytics, actor=user)
    channel = stage_state_for_engagement(engagement, "channel_execution")
    start_stage(channel, actor=user)
    complete_stage(channel, actor=user)

    approval = stage_state_for_engagement(engagement, "client_approval_ops")
    with pytest.raises(DepartmentPipelineError):
        start_stage(approval, actor=user)

    qa = stage_state_for_engagement(engagement, "qa_compliance")
    start_stage(qa, actor=user)
    complete_stage(qa, actor=user)
    start_stage(approval, actor=user)
    complete_stage(approval, actor=user)
    assert ProgramStageState.objects.get(id=approval.id).status == "completed"


def test_attach_deliverable_and_asset_records_lineage(user):
    departments = _departments(user)
    company = _company(user)
    engagement = _engagement(user, company)
    create_pipeline_for_engagement(engagement, created_by=user)
    strategy = stage_state_for_engagement(engagement, "strategy_research")

    asset = Asset.objects.create(
        organization=company.organization,
        company=company,
        title="Legacy strategy brief",
        asset_type="document",
        created_by_type="system",
    )
    version = AssetVersion.objects.create(
        asset=asset,
        version_number=1,
        content_uri="file://legacy_strategy.md",
        content_hash="abc123",
        mime_type="text/markdown",
        size_bytes=128,
        provenance_json={"source": "test"},
    )
    deliverable = ServiceDeliverable.objects.create(
        organization=company.organization,
        company=company,
        engagement=engagement,
        title="Legacy strategy brief",
        deliverable_type="strategy_brief",
        artifact=asset,
        created_by=user,
    )

    attach_asset_to_stage(asset, strategy, output_kind="strategy_input")
    attach_deliverable_to_stage(deliverable, strategy, output_kind="strategy_brief")

    asset.refresh_from_db()
    version.refresh_from_db()
    deliverable.refresh_from_db()
    strategy.refresh_from_db()
    assert deliverable.department_id == departments["strategy_research"].id
    assert deliverable.metadata_json["department_pipeline"]["stage_id"] == "strategy_research"
    assert deliverable.metadata_json["task_routing"]["stage_id"] == "strategy_research"
    assert deliverable.metadata_json["task_routing"]["routing_record_id"]
    assert asset.metadata_json["department_pipeline"]["stage_state_id"] == str(strategy.id)
    assert version.provenance_json["department_pipeline"]["program_id"] == str(strategy.program_id)
    assert version.provenance_json["task_routing"]["stage_state_id"] == str(strategy.id)
    assert {item["id"] for item in strategy.state_json["outputs"]} == {
        str(asset.id),
        str(deliverable.id),
    }


def test_pipeline_snapshot_contains_renderable_stage_state(user):
    _departments(user)
    engagement = _engagement(user, _company(user))
    create_pipeline_for_engagement(engagement, created_by=user)

    snapshot = get_pipeline_snapshot(engagement)

    assert snapshot["created"] is True
    assert snapshot["program"]["template_id"] == "digital_marketing_pro.weekend_social_launch.v1"
    assert len(snapshot["stages"]) == 7
    assert snapshot["stages"][0]["stage_id"] == "strategy_research"
    assert snapshot["stages"][0]["outputs"] == []
