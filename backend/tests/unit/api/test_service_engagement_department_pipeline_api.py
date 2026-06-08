from __future__ import annotations

from typing import cast
from uuid import uuid4

import pytest

from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import (
    DepartmentRegistry,
    Graph,
    Organization,
    ProgramStageState,
    ServiceCatalogItem,
    ServiceEngagement,
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


def _company(user: User) -> Graph:
    organization = _organization(user)
    return cast(
        Graph,
        Graph.objects.create(
            owner=user,
            organization=organization,
            name="Legacy",
            description="Glasswear client.",
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
        public_summary="Legacy weekend marketing sprint.",
        requested_by=user,
    )


def _departments(user: User) -> None:
    organization = _organization(user)
    for slug in _STAGE_SLUGS:
        DepartmentRegistry.objects.create(
            organization=organization,
            slug=slug,
            name=slug.replace("_", " ").title(),
            department_type="atlas_agency",
            service_tags_json=["atlas", "digital_marketing_pro"],
        )


def test_department_pipeline_api_create_get_and_transition(authenticated_client, user):
    _departments(user)
    engagement = _engagement(user, _company(user))

    create_response = authenticated_client.post(
        f"/api/service-engagements/{engagement.id}/department-pipeline",
        {},
        format="json",
    )
    assert create_response.status_code == 201
    created = create_response.data["data"]["department_pipeline"]
    assert created["created"] is True
    assert [stage["stage_id"] for stage in created["stages"]] == [
        "strategy_research",
        "brand_content",
        "crm_lifecycle",
        "analytics_performance",
        "channel_execution",
        "qa_compliance",
        "client_approval_ops",
    ]

    blocked_brand = authenticated_client.post(
        f"/api/service-engagements/{engagement.id}/department-pipeline/stages/brand_content/start",
        {},
        format="json",
    )
    assert blocked_brand.status_code == 400
    assert blocked_brand.data["error"]["code"] == "DEPENDENCY_NOT_SATISFIED"

    start_strategy = authenticated_client.post(
        f"/api/service-engagements/{engagement.id}/department-pipeline/stages/strategy_research/start",
        {},
        format="json",
    )
    assert start_strategy.status_code == 200
    strategy_stage = next(
        stage
        for stage in start_strategy.data["data"]["department_pipeline"]["stages"]
        if stage["stage_id"] == "strategy_research"
    )
    assert strategy_stage["status"] == "in_progress"

    complete_strategy = authenticated_client.post(
        f"/api/service-engagements/{engagement.id}/department-pipeline/stages/strategy_research/complete",
        {"outputs": [{"kind": "brief", "id": "legacy-strategy"}]},
        format="json",
    )
    assert complete_strategy.status_code == 200
    strategy = ProgramStageState.objects.get(program__company=engagement.company, stage_id="strategy_research")
    assert strategy.status == "completed"
    assert strategy.state_json["outputs"] == [{"kind": "brief", "id": "legacy-strategy"}]

    start_brand = authenticated_client.post(
        f"/api/service-engagements/{engagement.id}/department-pipeline/stages/brand_content/start",
        {},
        format="json",
    )
    assert start_brand.status_code == 200
    brand_stage = next(
        stage
        for stage in start_brand.data["data"]["department_pipeline"]["stages"]
        if stage["stage_id"] == "brand_content"
    )
    assert brand_stage["status"] == "in_progress"

    get_response = authenticated_client.get(
        f"/api/service-engagements/{engagement.id}/department-pipeline"
    )
    assert get_response.status_code == 200
    pipeline = get_response.data["data"]["department_pipeline"]
    assert pipeline["program"]["current_stage_id"] == "brand_content"


def test_department_pipeline_api_skip_requires_reason(authenticated_client, user):
    _departments(user)
    engagement = _engagement(user, _company(user))
    authenticated_client.post(
        f"/api/service-engagements/{engagement.id}/department-pipeline",
        {},
        format="json",
    )
    authenticated_client.post(
        f"/api/service-engagements/{engagement.id}/department-pipeline/stages/strategy_research/start",
        {},
        format="json",
    )
    authenticated_client.post(
        f"/api/service-engagements/{engagement.id}/department-pipeline/stages/strategy_research/complete",
        {},
        format="json",
    )

    missing_reason = authenticated_client.post(
        f"/api/service-engagements/{engagement.id}/department-pipeline/stages/crm_lifecycle/skip",
        {},
        format="json",
    )
    assert missing_reason.status_code == 400
    assert missing_reason.data["error"]["code"] == "VALIDATION_ERROR"

    skipped = authenticated_client.post(
        f"/api/service-engagements/{engagement.id}/department-pipeline/stages/crm_lifecycle/skip",
        {"reason": "No CRM connector in weekend MVP."},
        format="json",
    )
    assert skipped.status_code == 200
    crm_stage = next(
        stage
        for stage in skipped.data["data"]["department_pipeline"]["stages"]
        if stage["stage_id"] == "crm_lifecycle"
    )
    assert crm_stage["status"] == "completed"
    assert crm_stage["skipped"] is True
    assert crm_stage["skipped_reason"] == "No CRM connector in weekend MVP."
