from __future__ import annotations

from typing import cast

import pytest

from application.services.career_ops_engagements import ensure_career_ops_application_engagement
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import Graph, ServiceCatalogItem, ServiceEngagement, User

pytestmark = pytest.mark.django_db


def _create_company(user: User) -> Graph:
    ensure_default_organization(user)
    organization = user.default_organization
    assert organization is not None
    return cast(
        Graph,
        Graph.objects.create(owner=user, organization=organization, name="CareerOps Engagement Co"),
    )


def test_ensure_career_ops_application_engagement_is_idempotent(user: User) -> None:
    company = _create_company(user)

    first = ensure_career_ops_application_engagement(company=company, actor=user)
    second = ensure_career_ops_application_engagement(company=company, actor=user)

    assert second.id == first.id
    assert (
        ServiceCatalogItem.objects.filter(
            organization=company.organization, slug="career-ops-application-packet"
        ).count()
        == 1
    )
    assert (
        ServiceEngagement.objects.filter(
            company=company, source_key=f"career-ops:{company.id}:application-pipeline"
        ).count()
        == 1
    )
    assert first.required_pack_ids_json == ["career_ops.v1"]
