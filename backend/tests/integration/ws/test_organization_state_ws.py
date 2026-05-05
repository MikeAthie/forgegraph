from __future__ import annotations

from typing import Any, cast

import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.test import override_settings
from rest_framework_simplejwt.tokens import AccessToken

from application.services.auth_state import issue_ws_ticket
from application.services.organization_state_feed import (
    publish_organization_state_feed_event,
    record_organization_state_feed_event,
)
from application.services.tenancy import ensure_default_organization
from config.asgi import application
from infrastructure.orm.models import OrganizationStateFeedEvent, User

pytestmark = pytest.mark.django_db(transaction=True)

LOC_MEM_CACHE = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "organization-ws-tests",
    }
}
LOC_MEM_CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    }
}


def _ws(user: User, url: str) -> WebsocketCommunicator:
    communicator = WebsocketCommunicator(application, url)
    assert user.default_organization is not None, "User must have a default organization"
    scope = cast(dict[str, Any], communicator.scope)
    scope.update(
        {
            "user": user,
            "organization_id": str(user.default_organization.id),
            "permissions": ["organizations:state:view", "runs:view"],
        }
    )
    return communicator


async def _connect(communicator: WebsocketCommunicator) -> tuple[bool, int | str | None]:
    return cast(tuple[bool, int | str | None], await communicator.connect(timeout=5))


@database_sync_to_async
def _issue_ticket_for_user(user: User) -> str:
    access_token = AccessToken.for_user(user)
    ticket, _ = issue_ws_ticket(user=user, access_token=access_token)
    return ticket


@database_sync_to_async
def _record_event(
    user: User, *, event_id: str, event_type: str = "overview.updated"
) -> dict[str, Any]:
    assert user.default_organization is not None
    return record_organization_state_feed_event(
        organization=user.default_organization,
        event_type=event_type,
        event_id=event_id,
        resource_type="overview",
        resource_id=str(user.default_organization.id),
    )


@database_sync_to_async
def _publish_event(
    user: User, *, event_id: str, event_type: str = "overview.updated"
) -> dict[str, Any]:
    assert user.default_organization is not None
    return publish_organization_state_feed_event(
        organization=user.default_organization,
        event_type=event_type,
        event_id=event_id,
        resource_type="overview",
        resource_id=str(user.default_organization.id),
    )


@database_sync_to_async
def _delete_state_version(user: User, state_version: int) -> None:
    assert user.default_organization is not None
    OrganizationStateFeedEvent.objects.filter(
        organization=user.default_organization,
        state_version=state_version,
    ).delete()


@database_sync_to_async
def _create_other_user() -> User:
    other = User.objects.create_user(email="org-ws-other@example.com", password="password123")
    ensure_default_organization(other)
    return other


@pytest.mark.asyncio
@override_settings(CACHES=LOC_MEM_CACHE, CHANNEL_LAYERS=LOC_MEM_CHANNEL_LAYERS)
async def test_organization_state_ws_receives_backend_broadcast(user):
    organization_id = str(user.default_organization_id)
    ticket = await _issue_ticket_for_user(user)
    communicator = _ws(user, f"/ws/organizations/{organization_id}/state/?ticket={ticket}")
    connected, _ = await _connect(communicator)
    assert connected is True

    connected_message = await communicator.receive_json_from(timeout=5)
    assert connected_message["type"] == "connection_established"
    assert connected_message["organization_id"] == organization_id

    await _publish_event(user, event_id="evt-live", event_type="decision.created")

    message = await communicator.receive_json_from(timeout=5)
    assert message["type"] == "decision.created"
    assert message["event_type"] == "decision.created"
    assert message["requires_refetch"] is True
    assert message["organization_id"] == organization_id
    await communicator.disconnect()


@pytest.mark.asyncio
@override_settings(CACHES=LOC_MEM_CACHE, CHANNEL_LAYERS=LOC_MEM_CHANNEL_LAYERS)
async def test_organization_state_ws_replays_after_last_seen_version(user):
    organization_id = str(user.default_organization_id)
    await _record_event(user, event_id="evt-1")
    await _record_event(user, event_id="evt-2", event_type="accounting.updated")

    ticket = await _issue_ticket_for_user(user)
    communicator = _ws(
        user,
        f"/ws/organizations/{organization_id}/state/?ticket={ticket}&last_seen_state_version=1",
    )
    connected, _ = await _connect(communicator)
    assert connected is True

    connected_message = await communicator.receive_json_from(timeout=5)
    assert connected_message["payload"]["replayed_count"] == 1
    replayed = await communicator.receive_json_from(timeout=5)
    assert replayed["event_id"] == "evt-2"
    assert replayed["state_version"] == 2
    await communicator.disconnect()


@pytest.mark.asyncio
@override_settings(CACHES=LOC_MEM_CACHE, CHANNEL_LAYERS=LOC_MEM_CHANNEL_LAYERS)
async def test_organization_state_ws_resume_reports_full_resync_on_gap(user):
    organization_id = str(user.default_organization_id)
    await _record_event(user, event_id="evt-1")
    await _record_event(user, event_id="evt-2")
    await _record_event(user, event_id="evt-3")
    await _delete_state_version(user, 2)

    ticket = await _issue_ticket_for_user(user)
    communicator = _ws(user, f"/ws/organizations/{organization_id}/state/?ticket={ticket}")
    connected, _ = await _connect(communicator)
    assert connected is True
    await communicator.receive_json_from(timeout=5)

    await communicator.send_json_to({"type": "resume", "last_seen_state_version": 1})
    message = await communicator.receive_json_from(timeout=5)
    assert message["type"] == "full_resync_required"
    assert message["reason"] == "replay_window_expired"
    assert message["payload"]["full_resync_required"] is True
    await communicator.disconnect()


@pytest.mark.asyncio
@override_settings(CACHES=LOC_MEM_CACHE, CHANNEL_LAYERS=LOC_MEM_CHANNEL_LAYERS)
async def test_organization_state_ws_rejects_cross_org_ticket(user):
    other = await _create_other_user()
    ticket = await _issue_ticket_for_user(user)
    communicator = _ws(
        user, f"/ws/organizations/{other.default_organization_id}/state/?ticket={ticket}"
    )
    connected, _ = await _connect(communicator)
    assert connected is False
    await communicator.disconnect()
