from __future__ import annotations

import json
from typing import cast
from uuid import uuid4

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from application.services.agency_deliverable_catalog import MVP_DELIVERABLE_TYPES
from application.services.agency_deliverables import assemble_atlas_mvp_deliverables
from application.services.agency_launch_readiness import CampaignLaunchReadiness
from infrastructure.orm.models import (
    Asset,
    AssetVersion,
    Graph,
    Organization,
    OrganizationMembership,
    ProcessedCommand,
    ServiceDeliverable,
    StateProjection,
    User,
    WorkWhiteboard,
)

pytestmark = pytest.mark.django_db


def _user(org: Organization, email: str = "atlas-launch-readiness@example.com") -> User:
    user = User.objects.create_user(email=email, password="testpassword123")
    user.default_organization = org
    user.save(update_fields=["default_organization"])
    OrganizationMembership.objects.create(organization=org, user=user, role="owner", is_default=True)
    return user


def _company(org: Organization, owner: User) -> Graph:
    return cast(
        Graph,
        Graph.objects.create(
            owner=owner,
            organization=org,
            name="Atlas Launch Client",
            description="Digital marketing client.",
        ),
    )


def _whiteboard(company: Graph, owner: User, *, idempotency_key: str = "") -> WorkWhiteboard:
    org = company.organization
    assert org is not None
    return WorkWhiteboard.objects.create(
        organization=org,
        company=company,
        status=WorkWhiteboard.STATUS_IN_DEPLOYMENT,
        work_status=WorkWhiteboard.WORK_STATUS_DELIVERY,
        request_type="service_request",
        project_name="Summer Launch",
        client_name=company.name,
        request_summary="Launch a summer campaign across email, WhatsApp, and social.",
        objective="Increase repeat purchases for summer accessories.",
        idempotency_key=idempotency_key,
        created_by=owner,
    )


def _projection(whiteboard: WorkWhiteboard, suffix: str, state: dict[str, object]) -> None:
    StateProjection.objects.update_or_create(
        organization=whiteboard.organization,
        company=whiteboard.company,
        program=None,
        projection_type=f"whiteboard_{suffix}:{whiteboard.id}",
        defaults={
            "display_label": f"Whiteboard {suffix}",
            "json_state": state,
        },
    )


def _connector_inventory(whiteboard: WorkWhiteboard, *connectors: str) -> None:
    _projection(
        whiteboard,
        "connector_inventory",
        {
            "connector_inventory": {
                connector: {"status": "ready", "secret": f"{connector}-secret"}
                for connector in connectors
            }
        },
    )


def _approval(whiteboard: WorkWhiteboard, *, status: str = "approved") -> None:
    _projection(
        whiteboard,
        "approval",
        {
            "status": status,
            "approval_id": f"approval-{uuid4()}",
            "api_key": "approval-secret",
        },
    )


def _qa(whiteboard: WorkWhiteboard, *, status: str = "passed") -> None:
    _projection(
        whiteboard,
        "qa",
        {
            "status": status,
            "passed": status == "passed",
            "private_note": "qa-secret",
        },
    )


def _tracking(whiteboard: WorkWhiteboard, *, status: str = "ready") -> None:
    _projection(
        whiteboard,
        "tracking",
        {
            "status": status,
            "tracking_configured": status == "ready",
            "tracking_plan_id": "tracking-plan-v1",
            "access_token": "tracking-secret",
        },
    )


def _ready_launch_whiteboard(*, idempotency_key: str = "launch-ready-key") -> tuple[User, WorkWhiteboard]:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, f"atlas-launch-{uuid4().hex}@example.com")
    company = _company(org, owner)
    whiteboard = _whiteboard(company, owner, idempotency_key=idempotency_key)
    _connector_inventory(
        whiteboard,
        "email_connector",
        "whatsapp_connector",
        "social_connector",
        "analytics_connector",
    )
    _approval(whiteboard)
    _qa(whiteboard)
    _tracking(whiteboard)
    assemble_atlas_mvp_deliverables(whiteboard=whiteboard, user=owner)
    return owner, whiteboard


def _codes(items: list[dict[str, object]]) -> set[str]:
    return {str(item.get("code") or "") for item in items}


def test_happy_dry_run_readiness_passes_without_side_effects() -> None:
    _owner, whiteboard = _ready_launch_whiteboard()

    readiness = CampaignLaunchReadiness().evaluate(whiteboard=whiteboard)

    assert readiness["status"] == "ready"
    assert readiness["passed"] is True
    assert readiness["dry_run"] is True
    assert readiness["live_execution_enabled"] is False
    assert readiness["blockers"] == []
    assert readiness["connector_readiness"]["status"] == "ready"
    assert readiness["approval_state"]["status"] == "approved"
    assert readiness["deliverable_state"]["required_count"] == len(MVP_DELIVERABLE_TYPES)
    assert readiness["tracking_state"]["status"] == "ready"
    assert readiness["side_effect_readiness"]["status"] == "dry_run"
    assert ServiceDeliverable.objects.filter(deliverable_type="campaign_launch_receipt").count() == 0


def test_missing_connector_is_blocker_even_in_dry_run() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "atlas-missing-connector@example.com")
    company = _company(org, owner)
    whiteboard = _whiteboard(company, owner, idempotency_key="missing-connector-key")
    _connector_inventory(whiteboard, "email_connector", "social_connector", "analytics_connector")
    _approval(whiteboard)
    _qa(whiteboard)
    _tracking(whiteboard)
    assemble_atlas_mvp_deliverables(whiteboard=whiteboard, user=owner)

    readiness = CampaignLaunchReadiness().evaluate(whiteboard=whiteboard)

    assert readiness["status"] == "blocked"
    assert readiness["passed"] is False
    assert "connector_not_ready" in _codes(readiness["blockers"])
    assert readiness["connector_readiness"]["status"] == "blocked"


def test_missing_approval_blocks_launch_readiness() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "atlas-missing-approval@example.com")
    company = _company(org, owner)
    whiteboard = _whiteboard(company, owner, idempotency_key="missing-approval-key")
    _connector_inventory(
        whiteboard,
        "email_connector",
        "whatsapp_connector",
        "social_connector",
        "analytics_connector",
    )
    _qa(whiteboard)
    _tracking(whiteboard)
    assemble_atlas_mvp_deliverables(whiteboard=whiteboard, user=owner)

    readiness = CampaignLaunchReadiness().evaluate(whiteboard=whiteboard)

    assert readiness["status"] == "blocked"
    assert "approval_missing" in _codes(readiness["blockers"])
    assert readiness["approval_state"]["status"] == "missing"


def test_missing_idempotency_key_blocks_live_mode_only() -> None:
    _owner, whiteboard = _ready_launch_whiteboard(idempotency_key="")

    dry_run = CampaignLaunchReadiness().evaluate(whiteboard=whiteboard)
    live_mode = CampaignLaunchReadiness().evaluate(whiteboard=whiteboard, live_mode=True)

    assert "idempotency_key_required" not in _codes(dry_run["blockers"])
    assert live_mode["status"] == "blocked"
    assert "idempotency_key_required" in _codes(live_mode["blockers"])
    assert live_mode["side_effect_readiness"]["status"] == "blocked"


def test_missing_tracking_warns_in_dry_run_and_blocks_live_mode() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "atlas-missing-tracking@example.com")
    company = _company(org, owner)
    whiteboard = _whiteboard(company, owner, idempotency_key="missing-tracking-key")
    _connector_inventory(
        whiteboard,
        "email_connector",
        "whatsapp_connector",
        "social_connector",
        "analytics_connector",
    )
    _approval(whiteboard)
    _qa(whiteboard)
    assemble_atlas_mvp_deliverables(whiteboard=whiteboard, user=owner)

    dry_run = CampaignLaunchReadiness().evaluate(whiteboard=whiteboard)
    live_mode = CampaignLaunchReadiness().evaluate(whiteboard=whiteboard, live_mode=True)

    assert dry_run["status"] == "warning"
    assert "tracking_missing" in _codes(dry_run["warnings"])
    assert "tracking_missing" not in _codes(dry_run["blockers"])
    assert live_mode["status"] == "blocked"
    assert "tracking_missing" in _codes(live_mode["blockers"])


def test_launch_receipt_deliverable_is_backend_owned_sanitized_and_idempotent() -> None:
    owner, whiteboard = _ready_launch_whiteboard()
    service = CampaignLaunchReadiness()

    first = service.evaluate(whiteboard=whiteboard, user=owner, create_receipt=True)
    second = service.evaluate(whiteboard=whiteboard, user=owner, create_receipt=True)

    first_receipt = first["receipt_deliverable"]
    second_receipt = second["receipt_deliverable"]
    deliverable = ServiceDeliverable.objects.get(id=first_receipt["id"])
    asset = Asset.objects.get(source_key=f"atlas-launch-readiness:{whiteboard.id}:receipt")
    version = AssetVersion.objects.get(asset=asset)
    rendered = json.dumps(first, sort_keys=True, default=str)

    assert first_receipt["id"] == second_receipt["id"]
    assert deliverable.deliverable_type == "campaign_launch_receipt"
    assert deliverable.artifact == asset
    assert deliverable.metadata_json["source"] == "atlas_launch_readiness"
    assert deliverable.metadata_json["dry_run"] is True
    assert deliverable.metadata_json["ready"] is True
    assert deliverable.metadata_json["blocked"] is False
    assert deliverable.metadata_json["live_execution_enabled"] is False
    assert version.mime_type == "application/json"
    assert Asset.objects.filter(source_key=f"atlas-launch-readiness:{whiteboard.id}:receipt").count() == 1
    assert ServiceDeliverable.objects.filter(deliverable_type="campaign_launch_receipt").count() == 1
    assert AssetVersion.objects.filter(asset=asset).count() == 1
    assert "secret" not in rendered
    assert "api_key" not in rendered
    assert "access_token" not in rendered


def test_api_dry_run_returns_client_safe_payload_without_receipt() -> None:
    owner, whiteboard = _ready_launch_whiteboard()
    client = APIClient()
    client.force_authenticate(user=owner)

    response = client.post(
        reverse("whiteboard-atlas-launch-readiness", kwargs={"whiteboard_id": whiteboard.id}),
        {"mode": "dry_run"},
        format="json",
    )

    assert response.status_code == 200
    readiness = response.data["data"]["readiness"]
    rendered = json.dumps(readiness, sort_keys=True, default=str)
    assert readiness["status"] == "ready"
    assert readiness["dry_run"] is True
    assert "receipt_deliverable" not in response.data["data"]
    assert ServiceDeliverable.objects.filter(deliverable_type="campaign_launch_receipt").count() == 0
    assert "secret" not in rendered
    assert "api_key" not in rendered
    assert "access_token" not in rendered


def test_api_live_unsafe_launch_is_hard_blocked_without_receipt_or_command() -> None:
    org = Organization.objects.create(name="ATLAS")
    owner = _user(org, "atlas-live-block@example.com")
    company = _company(org, owner)
    whiteboard = _whiteboard(company, owner, idempotency_key="live-block-key")
    _connector_inventory(
        whiteboard,
        "email_connector",
        "whatsapp_connector",
        "social_connector",
        "analytics_connector",
    )
    _qa(whiteboard)
    _tracking(whiteboard)
    assemble_atlas_mvp_deliverables(whiteboard=whiteboard, user=owner)
    client = APIClient()
    client.force_authenticate(user=owner)

    response = client.post(
        reverse("whiteboard-atlas-launch-readiness", kwargs={"whiteboard_id": whiteboard.id}),
        {"mode": "live", "create_receipt": True},
        format="json",
        HTTP_IDEMPOTENCY_KEY="live-block-key",
    )

    assert response.status_code == 409
    error = response.data["error"]
    assert error["code"] == "ATLAS_LIVE_LAUNCH_BLOCKED"
    readiness = error["details"][0]["readiness"]
    assert readiness["requested_execution_mode"] == "live"
    assert "approval_missing" in _codes(readiness["blockers"])
    assert ServiceDeliverable.objects.filter(deliverable_type="campaign_launch_receipt").count() == 0
    assert ProcessedCommand.objects.count() == 0


def test_api_receipt_creation_replays_idempotently_and_conflicts_on_body_change() -> None:
    owner, whiteboard = _ready_launch_whiteboard()
    client = APIClient()
    client.force_authenticate(user=owner)
    url = reverse("whiteboard-atlas-launch-readiness", kwargs={"whiteboard_id": whiteboard.id})
    payload = {"mode": "dry_run", "create_receipt": True}

    first = client.post(url, payload, format="json", HTTP_IDEMPOTENCY_KEY="receipt-replay-key")
    second = client.post(url, payload, format="json", HTTP_IDEMPOTENCY_KEY="receipt-replay-key")
    conflict = client.post(
        url,
        {"mode": "dry_run", "dry_run": True, "create_receipt": True},
        format="json",
        HTTP_IDEMPOTENCY_KEY="receipt-replay-key",
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert conflict.status_code == 409
    assert first.data["data"]["idempotency"]["status"] == "applied"
    assert second.data["data"]["idempotency"]["status"] == "already_applied"
    assert conflict.data["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert first.data["data"]["receipt_deliverable"]["id"] == second.data["data"]["receipt_deliverable"]["id"]
    assert ServiceDeliverable.objects.filter(deliverable_type="campaign_launch_receipt").count() == 1
    assert ProcessedCommand.objects.count() == 1


def test_api_launch_readiness_is_scoped_to_whiteboard_organization() -> None:
    _owner, whiteboard = _ready_launch_whiteboard()
    other_org = Organization.objects.create(name="OTHER")
    outsider = _user(other_org, "atlas-launch-outsider@example.com")
    client = APIClient()
    client.force_authenticate(user=outsider)

    response = client.post(
        reverse("whiteboard-atlas-launch-readiness", kwargs={"whiteboard_id": whiteboard.id}),
        {"mode": "dry_run"},
        format="json",
    )

    assert response.status_code == 404
    assert response.data["error"]["code"] == "NOT_FOUND"
