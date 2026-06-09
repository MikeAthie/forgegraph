from __future__ import annotations

from typing import cast

import pytest
from django.utils import timezone

from application.services.gateway_media import normalize_gateway_attachments
from application.services.gateway_registry import (
    capability_payload,
    connection_diagnostics,
    get_capability,
)
from application.services.gateway_schedules import create_schedule, run_schedule
from infrastructure.orm.models import (
    GatewayConnection,
    GatewayMediaArtifact,
    Graph,
    GraphVersion,
    Organization,
    Run,
    RunQueueEntry,
    User,
)

pytestmark = pytest.mark.django_db


def _company_version() -> tuple[Organization, User, Graph, GraphVersion]:
    org = Organization.objects.create(name="Gateway Platform Org")
    user = User.objects.create_user(
        email="gateway-platform@example.com", password="testpassword123"
    )
    user.default_organization = org
    user.save(update_fields=["default_organization"])
    company = cast(
        Graph, Graph.objects.create(owner=user, organization=org, name="Gateway Platform Co")
    )
    version = GraphVersion.objects.create(
        graph=company,
        version=1,
        graph_json={"nodes": [], "edges": []},
    )
    return org, user, company, version


def test_capability_registry_fallback_payload_and_connection_diagnostics() -> None:
    org, _user, _company, version = _company_version()
    connection = GatewayConnection.objects.create(
        organization=org,
        graph_version=version,
        platform="telegram",
        provider="telegram",
        name="Telegram",
        status="enabled",
    )

    capability = get_capability(platform="telegram", provider="telegram")
    payload = capability_payload(capability)
    diagnostics = connection_diagnostics(connection).as_dict()

    assert payload is not None
    assert payload["runtime_tool_id"] == "gateway.telegram.send"
    assert diagnostics["capability"]["platform"] == "telegram"
    assert any(check["code"] == "credential_missing" for check in diagnostics["checks"])


def test_media_normalization_redacts_raw_provider_urls_and_tokens() -> None:
    org, _user, _company, _version = _company_version()

    artifacts = normalize_gateway_attachments(
        organization=org,
        platform="telegram",
        provider="telegram",
        direction="inbound",
        attachments=[
            {
                "url": "https://provider.example/download/private?token=secret",
                "token": "secret-token",
                "content_type": "audio/ogg",
                "size": 1024,
                "filename": "voice.ogg",
            }
        ],
    )

    assert len(artifacts) == 1
    artifact = GatewayMediaArtifact.objects.get(id=artifacts[0].id)
    assert artifact.content_type == "audio/ogg"
    assert artifact.size_bytes == 1024
    assert artifact.metadata_json["url_hash"].startswith("sha256:")
    assert "url" not in artifact.metadata_json
    assert artifact.metadata_json["token_configured"] is True


def test_gateway_schedule_run_now_materializes_run_and_queue_entry() -> None:
    _org, user, _company, version = _company_version()
    schedule = create_schedule(
        graph_version=version,
        user=user,
        platform="telegram",
        provider="telegram",
        name="Daily Telegram Check",
        schedule_type="interval",
        schedule_json={"seconds": 300},
        input_template_json={"message": "scheduled"},
        timezone_name="UTC",
    )

    result = run_schedule(schedule_id=schedule.id, fire_time=timezone.now(), force=True)

    assert result is not None
    run = Run.objects.get(id=result.run_id)
    schedule.refresh_from_db()
    assert run.input_json["gateway"]["schedule_id"] == str(schedule.id)
    assert schedule.last_materialized_run_id == run.id
    assert schedule.next_run_at is not None
    assert RunQueueEntry.objects.filter(run=run, status="pending").exists()
