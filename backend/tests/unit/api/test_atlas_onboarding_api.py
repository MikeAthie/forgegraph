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


def _company(user: User, *, name: str = "Atlas Onboarding Client") -> tuple[Graph, GraphVersion]:
    ensure_default_organization(user)
    organization = user.default_organization
    assert organization is not None
    company = cast(
        Graph,
        Graph.objects.create(
            owner=user,
            organization=organization,
            name=name,
            description="Atlas onboarding API test client.",
        ),
    )
    version = GraphVersion.objects.create(
        graph=company,
        version=1,
        graph_json={"nodes": [], "edges": [], "metadata": {}},
    )
    return company, version


def _valid_payload(company: Graph) -> dict[str, object]:
    return {
        "company_id": str(company.id),
        "client_name": "Signal House",
        "contact_name": "Alex Client",
        "contact_email": "ALEX@CLIENT.EXAMPLE",
        "website_url": "https://signal.example",
        "business_summary": "Retail brand expanding owned-channel demand.",
        "goals": ["Increase repeat purchases", "Improve launch reporting"],
        "target_audience": {"segments": ["repeat buyers", "vip customers"]},
        "brand_voice": "Direct, useful, premium.",
        "constraints": ["No discount-led messaging"],
        "approved_channels": ["email", "whatsapp"],
        "blocked_channels": ["tiktok"],
        "success_metrics": ["repeat purchase rate", "campaign revenue"],
        "budget_range": "$5k-$10k monthly",
        "timeline": "Launch in July",
        "service_slug": "digital-marketing-agency-engagement",
        "service_package": "Atlas growth operator package",
        "notes": "Operator-mediated intake.",
        "source": "hermes",
    }


def test_atlas_onboarding_get_allows_viewer_and_returns_safe_contract(
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
        name="Unsafe Atlas Gmail",
        encrypted_key=b"secret-api-key",
    )
    GatewayConnection.objects.create(
        organization=organization,
        graph_version=version,
        credential=credential,
        platform="email",
        provider="gmail",
        name="Unsafe Atlas connection",
        status="enabled",
        config_json={"access_token": "secret-api-key"},
    )

    response = authenticated_client.get(
        "/api/company-ops/atlas-onboarding",
        {"company_id": str(company.id)},
    )

    assert response.status_code == 200
    contract = response.json()["data"]["atlas_onboarding"]
    assert contract["company_id"] == str(company.id)
    assert contract["contract_version"] == "atlas_onboarding.v1"
    assert set(contract) >= {
        "generated_at",
        "onboarding",
        "connector_readiness",
        "required_fields",
        "missing_required_fields",
        "operator_next_steps",
        "latest_engagement",
    }
    assert set(contract["onboarding"]) >= {"summary", "items"}
    assert contract["latest_engagement"] is None
    rendered = json.dumps(contract, sort_keys=True, default=str)
    assert str(credential.id) not in rendered
    assert "credential_id" not in rendered
    assert "secret-api-key" not in rendered
    assert "access_token" not in rendered


def test_atlas_onboarding_get_hides_inaccessible_company(authenticated_client, user) -> None:
    other_user = User.objects.create_user(
        email="hidden-atlas-client@example.com",
        password="testpassword123",
    )
    hidden_company, _version = _company(other_user, name="Hidden Atlas Client")

    response = authenticated_client.get(
        "/api/company-ops/atlas-onboarding",
        {"company_id": str(hidden_company.id)},
    )

    assert response.status_code == 404


def test_atlas_onboarding_post_member_upserts_idempotent_engagement(
    authenticated_client,
    user,
) -> None:
    company, _version = _company(user)
    organization = company.organization
    assert organization is not None
    OrganizationMembership.objects.filter(organization=organization, user=user).update(
        role="member"
    )
    payload = _valid_payload(company)

    first = authenticated_client.post(
        "/api/company-ops/atlas-onboarding",
        data=payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY="atlas-onboarding-create",
    )
    replay = authenticated_client.post(
        "/api/company-ops/atlas-onboarding",
        data=payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY="atlas-onboarding-create",
    )
    updated_payload = {**payload, "goals": ["Launch lifecycle program"], "timeline": "August"}
    update = authenticated_client.post(
        "/api/company-ops/atlas-onboarding",
        data=updated_payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY="atlas-onboarding-update",
    )

    assert first.status_code == 201
    assert replay.status_code == 201
    assert replay.json()["data"]["duplicate"] is True
    assert update.status_code == 200
    assert ServiceEngagement.objects.filter(company=company).count() == 1
    engagement = ServiceEngagement.objects.get(company=company)
    assert engagement.source_key == f"atlas-onboarding:{company.id}"
    assert engagement.status == "intake"
    assert engagement.customer_status == "intake_needed"
    assert engagement.intake_data_json["contact_email"] == "alex@client.example"
    assert engagement.intake_data_json["goals"] == ["Launch lifecycle program"]
    assert engagement.intake_data_json["timeline"] == "August"
    assert ServiceCatalogItem.objects.filter(
        organization=organization,
        slug="atlas-operator-onboarding",
    ).exists()
    contract = update.json()["data"]["atlas_onboarding"]
    assert contract["latest_engagement"]["id"] == str(engagement.id)
    assert contract["latest_engagement"]["status"] == "intake"
    assert contract["latest_engagement"]["intake_data_summary"]["service_slug"] == (
        "digital-marketing-agency-engagement"
    )


def test_atlas_onboarding_post_omits_credential_like_metadata(
    authenticated_client,
    user,
) -> None:
    company, _version = _company(user)
    payload = {
        **_valid_payload(company),
        "metadata": {
            "api_key": "secret-api-key",
            "nested": {
                "password": "do-not-store",
                "safe_context": "visible",
            },
            "credential_id": "cred-123",
        },
    }

    response = authenticated_client.post(
        "/api/company-ops/atlas-onboarding",
        data=payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY="atlas-onboarding-secret-strip",
    )

    assert response.status_code == 201
    engagement = ServiceEngagement.objects.get(company=company)
    rendered_response = json.dumps(response.json(), sort_keys=True, default=str)
    rendered_stored = json.dumps(
        {
            "intake": engagement.intake_data_json,
            "metadata": engagement.metadata_json,
        },
        sort_keys=True,
        default=str,
    )
    assert "safe_context" in rendered_response
    assert "safe_context" in rendered_stored
    for unsafe in ["secret-api-key", "do-not-store", "credential_id", "api_key", "password"]:
        assert unsafe not in rendered_response
        assert unsafe not in rendered_stored


def test_atlas_onboarding_post_rejects_top_level_credential_fields(
    authenticated_client,
    user,
) -> None:
    company, _version = _company(user)
    payload = {**_valid_payload(company), "api_key": "secret-api-key"}

    response = authenticated_client.post(
        "/api/company-ops/atlas-onboarding",
        data=payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY="atlas-onboarding-reject-secret",
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert ServiceEngagement.objects.filter(company=company).count() == 0


def test_atlas_onboarding_keeps_connector_readiness_out_of_intake(
    authenticated_client,
    user,
) -> None:
    company, _version = _company(user)

    response = authenticated_client.post(
        "/api/company-ops/atlas-onboarding",
        data=_valid_payload(company),
        format="json",
        HTTP_IDEMPOTENCY_KEY="atlas-onboarding-connectors-separate",
    )

    assert response.status_code == 201
    contract = response.json()["data"]["atlas_onboarding"]
    engagement = ServiceEngagement.objects.get(company=company)
    assert "connector_readiness" in contract
    assert "connector_readiness" not in contract["latest_engagement"]["intake_data_summary"]
    assert "connector_readiness" not in engagement.intake_data_json
    assert "connectors" not in engagement.intake_data_json
    assert "deliverables" not in engagement.intake_data_json
