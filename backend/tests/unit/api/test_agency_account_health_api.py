from __future__ import annotations

import json
from typing import cast

import pytest

from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import (
    APIKey,
    GatewayConnection,
    Graph,
    GraphVersion,
    OrganizationMembership,
    ServiceCatalogItem,
    ServiceEngagement,
    User,
)

pytestmark = pytest.mark.django_db


def _company(user: User, *, name: str = "Agency API Client") -> tuple[Graph, GraphVersion]:
    ensure_default_organization(user)
    organization = user.default_organization
    assert organization is not None
    company = cast(
        Graph,
        Graph.objects.create(
            owner=user,
            organization=organization,
            name=name,
            description="API test client.",
        ),
    )
    version = GraphVersion.objects.create(
        graph=company,
        version=1,
        graph_json={"nodes": [], "edges": [], "metadata": {}},
    )
    return company, version


def _engagement(company: Graph, user: User, *, metadata: dict) -> ServiceEngagement:
    organization = company.organization
    assert organization is not None
    catalog = ServiceCatalogItem.objects.create(
        organization=organization,
        slug="digital-marketing-agency-engagement",
        title="Digital Marketing Agency Engagement",
        status="active",
        visibility="customer",
    )
    return ServiceEngagement.objects.create(
        organization=organization,
        company=company,
        catalog_item=catalog,
        status="in_progress",
        customer_status="working",
        metadata_json=metadata,
        requested_by=user,
    )


def test_agency_health_api_allows_viewer_and_returns_safe_read_only_snapshot(
    authenticated_client,
    user,
) -> None:
    company, version = _company(user)
    organization = company.organization
    assert organization is not None
    OrganizationMembership.objects.filter(organization=organization, user=user).update(
        role="viewer"
    )
    credential = APIKey.objects.create(
        organization=organization,
        user=user,
        provider="gmail",
        name="Unsafe API Gmail",
        encrypted_key=b"secret-api-key",
    )
    GatewayConnection.objects.create(
        organization=organization,
        graph_version=version,
        credential=credential,
        platform="email",
        provider="gmail",
        name="Unsafe API connection",
        status="enabled",
        config_json={"access_token": "secret-api-key"},
    )
    _engagement(
        company,
        user,
        metadata={
            "reporting": {"cadences": ["weekly"]},
            "private_api_token": "metadata-api-secret",
        },
    )

    response = authenticated_client.get(
        "/api/company-ops/agency-health",
        {"company_id": str(company.id)},
    )

    assert response.status_code == 200
    payload = response.json()["data"]["agency_health"]
    assert set(payload) >= {
        "profile",
        "health",
        "onboarding_items",
        "connector_readiness",
        "recurring_reporting",
        "growth_signals",
        "risks",
        "opportunities",
        "next_actions",
    }
    assert payload["profile"]["company_id"] == str(company.id)
    assert payload["profile"]["commercial"]["monthly_retainer"]["status"] == "unknown"
    assert payload["recurring_reporting"]["summary"]["cadences_configured"] == 1
    assert payload["growth_signals"]["commercial"]["gross_margin"]["status"] == "unknown"
    rendered = json.dumps(payload, sort_keys=True, default=str)
    assert str(credential.id) not in rendered
    assert "credential_id" not in rendered
    assert "secret-api-key" not in rendered
    assert "access_token" not in rendered
    assert "metadata-api-secret" not in rendered
    assert "private_api_token" not in rendered


def test_agency_health_api_hides_inaccessible_company(authenticated_client, user) -> None:
    other_user = User.objects.create_user(
        email="other-agency-client@example.com",
        password="testpassword123",
    )
    hidden_company, _version = _company(other_user, name="Hidden Agency Client")

    response = authenticated_client.get(
        "/api/company-ops/agency-health",
        {"company_id": str(hidden_company.id)},
    )

    assert response.status_code == 404
