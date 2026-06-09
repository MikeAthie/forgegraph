from __future__ import annotations

from typing import cast

import pytest

from application.services.agency_account_catalog import ATLAS_DEPARTMENT_SLUGS
from application.services.agency_connector_readiness import build_connector_readiness
from application.services.agency_onboarding import build_virtual_onboarding_checklist
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import Graph, ServiceCatalogItem, ServiceEngagement, User

pytestmark = pytest.mark.django_db


def _company(user: User) -> Graph:
    ensure_default_organization(user)
    organization = user.default_organization
    assert organization is not None
    return cast(
        Graph,
        Graph.objects.create(
            owner=user,
            organization=organization,
            name="Onboarding Client",
            description="",
        ),
    )


def test_virtual_onboarding_checklist_marks_missing_connectors_blocked(user) -> None:
    company = _company(user)
    readiness = build_connector_readiness(company)

    checklist = build_virtual_onboarding_checklist(company, connector_readiness=readiness)
    by_slug = {item["slug"]: item for item in checklist["items"]}

    assert by_slug["connector_setup"]["status"] == "blocked"
    assert by_slug["client_profile"]["status"] == "not_started"
    assert checklist["summary"]["blocked"] >= 1
    assert {item["owner_department_slug"] for item in checklist["items"]} <= ATLAS_DEPARTMENT_SLUGS


def test_virtual_onboarding_checklist_reflects_active_service_engagement(user) -> None:
    company = _company(user)
    organization = company.organization
    assert organization is not None
    catalog = ServiceCatalogItem.objects.create(
        organization=organization,
        slug="digital-marketing-agency-engagement",
        title="Digital Marketing Agency Engagement",
        status="active",
        visibility="customer",
    )
    ServiceEngagement.objects.create(
        organization=organization,
        company=company,
        catalog_item=catalog,
        status="in_progress",
        customer_status="working",
        requested_by=user,
    )

    checklist = build_virtual_onboarding_checklist(company)
    by_slug = {item["slug"]: item for item in checklist["items"]}

    assert by_slug["service_engagement"]["status"] == "completed"
    assert by_slug["service_engagement"]["owner_department_slug"] == "client_approval_ops"
