from __future__ import annotations

import json
from typing import cast

import pytest

from application.services.agency_connector_readiness import build_connector_readiness
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import (
    APIKey,
    GatewayConnection,
    Graph,
    GraphVersion,
    StateProjection,
    User,
)

pytestmark = pytest.mark.django_db


def _company(user: User) -> tuple[Graph, GraphVersion]:
    ensure_default_organization(user)
    organization = user.default_organization
    assert organization is not None
    company = cast(
        Graph,
        Graph.objects.create(
            owner=user,
            organization=organization,
            name="Atlas Client",
            description="Digital marketing client.",
        ),
    )
    version = GraphVersion.objects.create(
        graph=company,
        version=1,
        graph_json={"nodes": [], "edges": [], "metadata": {}},
    )
    return company, version


def test_connector_readiness_normalizes_gateway_connections_without_secret_material(user) -> None:
    company, version = _company(user)
    organization = company.organization
    assert organization is not None
    credential = APIKey.objects.create(
        organization=organization,
        user=user,
        provider="gmail",
        name="Agency Gmail",
        encrypted_key=b"secret-api-key",
        token_metadata={"scope": "mail.send"},
    )
    GatewayConnection.objects.create(
        organization=organization,
        graph_version=version,
        credential=credential,
        platform="email",
        provider="gmail",
        name="Client Email",
        status="enabled",
        config_json={
            "access_token": "secret-api-key",
            "raw_provider_config": {"api_key": "secret-api-key"},
        },
    )

    readiness = build_connector_readiness(company)
    by_slug = {item["slug"]: item for item in readiness["connectors"]}

    assert by_slug["email_connector"]["status"] == "ready"
    assert by_slug["email_connector"]["readiness"] == "ready"
    assert by_slug["whatsapp_connector"]["status"] == "missing"
    assert readiness["summary"]["ready"] == 1
    assert readiness["summary"]["missing"] >= 1
    rendered = json.dumps(readiness, sort_keys=True, default=str)
    assert str(credential.id) not in rendered
    assert "credential_id" not in rendered
    assert "secret-api-key" not in rendered
    assert "raw_provider_config" not in rendered
    assert "access_token" not in rendered


def test_connector_readiness_uses_backend_projection_inventory_safely(user) -> None:
    company, _version = _company(user)
    organization = company.organization
    assert organization is not None
    StateProjection.objects.create(
        organization=organization,
        company=company,
        projection_type=f"whiteboard_deployment:{company.id}",
        display_label="Deployment readiness",
        json_state={
            "available_connectors": [
                {
                    "id": "analytics_connector",
                    "status": "ready",
                    "credential_id": "credential-should-not-leak",
                    "secret": "analytics-secret",
                },
                {
                    "connector": "social_connector",
                    "active": False,
                    "raw_provider_config": {"token": "social-secret"},
                },
            ]
        },
    )

    readiness = build_connector_readiness(company)
    by_slug = {item["slug"]: item for item in readiness["connectors"]}

    assert by_slug["analytics_connector"]["status"] == "ready"
    assert by_slug["social_connector"]["status"] == "missing"
    rendered = json.dumps(readiness, sort_keys=True, default=str)
    assert "credential-should-not-leak" not in rendered
    assert "analytics-secret" not in rendered
    assert "social-secret" not in rendered
    assert "raw_provider_config" not in rendered
