"""
Integration tests for Run WebSocket updates (Channels).
"""

from typing import Any, cast

import pytest
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.test import override_settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from application.services.auth_state import issue_ws_ticket, revoke_access_token
from application.services.run_event_streaming import (
    EVENT_LEVEL_DEFAULT,
    EVENT_LEVEL_MINIMAL,
    EVENT_LEVEL_VERBOSE,
    run_event_group_name,
)
from config.asgi import application
from infrastructure.orm.models import Graph, GraphVersion, OrganizationMembership, Run, User

pytestmark = pytest.mark.django_db(transaction=True)

LOC_MEM_CACHE = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "ws-tests",
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
            "permissions": ["runs:view"],
        }
    )

    return communicator


async def _connect(communicator: WebsocketCommunicator) -> tuple[bool, int | str | None]:
    return cast(tuple[bool, int | str | None], await communicator.connect(timeout=5))


@database_sync_to_async
def _create_run_for_user(*, user: User, status: str = "running") -> str:
    graph = Graph.objects.create(owner=user, name="My Graph")
    version = GraphVersion.objects.create(
        graph=graph, version=1, graph_json={"nodes": [], "edges": []}
    )
    run = Run.objects.create(owner=user, graph_version=version, status=status)
    return str(run.id)


@database_sync_to_async
def _create_other_user_and_run() -> tuple[User, str]:
    other_user = User.objects.create_user(email="other@example.com", password="password123")
    graph = Graph.objects.create(owner=other_user, name="Other Graph")
    version = GraphVersion.objects.create(
        graph=graph, version=1, graph_json={"nodes": [], "edges": []}
    )
    run = Run.objects.create(owner=other_user, graph_version=version, status="running")
    return other_user, str(run.id)


@database_sync_to_async
def _issue_ticket_for_user(user: User) -> tuple[str, str]:
    access_token = AccessToken.for_user(user)
    ticket, _ = issue_ws_ticket(user=user, access_token=access_token)
    return str(access_token), ticket


@database_sync_to_async
def _issue_ticket_via_api(user: User) -> tuple[str, str]:
    client = APIClient()
    login_response = client.post(
        "/api/auth/login",
        {"email": user.email, "password": "testpassword123"},
        format="json",
    )
    access = login_response.data["access"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    response = client.post("/api/auth/ws-ticket", {}, format="json")
    assert response.status_code == 201
    return access, response.data["ticket"]


@database_sync_to_async
def _create_same_org_member(user: User) -> User:
    member = User.objects.create_user(email="viewer@example.com", password="password123")

    organization = user.default_organization
    assert organization is not None, "User must have a default organization"

    member.default_organization = organization
    member.save(update_fields=["default_organization"])

    OrganizationMembership.objects.create(
        organization=organization,
        user=member,
        role="viewer",
        is_default=True,
    )
    return member


@database_sync_to_async
def _revoke_access(raw_token: str) -> None:
    revoke_access_token(AccessToken(cast(Any, raw_token)))


@pytest.mark.asyncio
async def test_run_ws_rejects_unauthenticated_user(user):
    run_id = await _create_run_for_user(user=user)

    communicator = WebsocketCommunicator(application, f"/ws/runs/{run_id}/")
    connected, _ = await _connect(communicator)

    assert connected is False
    await communicator.disconnect()


@pytest.mark.asyncio
@override_settings(CACHES=LOC_MEM_CACHE, CHANNEL_LAYERS=LOC_MEM_CHANNEL_LAYERS)
async def test_run_ws_allows_owner_with_ticket_and_receives_broadcast(user):
    run_id = await _create_run_for_user(user=user)

    _, ticket = await _issue_ticket_via_api(user)
    communicator = _ws(user, f"/ws/runs/{run_id}/?ticket={ticket}")
    connected, _ = await _connect(communicator)
    assert connected is True

    first = await communicator.receive_json_from()
    assert first["type"] == "connection_established"
    assert first["run_id"] == str(run_id)
    assert first["payload"]["event_level"] == "default"

    channel_layer = get_channel_layer()
    assert channel_layer is not None

    await channel_layer.group_send(
        run_event_group_name(run_id=str(run_id), level=EVENT_LEVEL_MINIMAL),
        {
            "type": "broadcast.message",
            "message": {
                "type": "run.updated",
                "run_id": str(run_id),
                "level": "minimal",
                "run": {
                    "id": str(run_id),
                    "status": "running",
                    "started_at": None,
                    "ended_at": None,
                    "duration_ms": None,
                    "output_json": None,
                    "error_message": "",
                },
            },
        },
    )

    message = await communicator.receive_json_from(timeout=5)
    assert message["type"] == "run_started"
    assert message["run_id"] == str(run_id)
    assert message["payload"]["run"]["status"] == "running"

    await communicator.disconnect()


@pytest.mark.asyncio
@override_settings(CACHES=LOC_MEM_CACHE, CHANNEL_LAYERS=LOC_MEM_CHANNEL_LAYERS)
async def test_run_ws_default_subscription_drops_verbose_messages(user):
    run_id = await _create_run_for_user(user=user)

    _, ticket = await _issue_ticket_via_api(user)
    communicator = _ws(user, f"/ws/runs/{run_id}/?ticket={ticket}")
    connected, _ = await _connect(communicator)
    assert connected is True

    await communicator.receive_json_from()

    channel_layer = get_channel_layer()
    assert channel_layer is not None

    await channel_layer.group_send(
        run_event_group_name(run_id=str(run_id), level=EVENT_LEVEL_VERBOSE),
        {
            "type": "broadcast.message",
            "message": {
                "type": "node_stream.chunk",
                "run_id": str(run_id),
                "level": "verbose",
                "node_stream": {
                    "node_id": "prompt_1",
                    "node_type": "prompt",
                    "attempt": 1,
                    "chunk": "hello",
                    "chunk_index": 1,
                },
            },
        },
    )

    assert await communicator.receive_nothing(timeout=0.1) is True
    await communicator.disconnect()


@pytest.mark.asyncio
@override_settings(CACHES=LOC_MEM_CACHE, CHANNEL_LAYERS=LOC_MEM_CHANNEL_LAYERS)
async def test_run_ws_filters_by_requested_event_type(user):
    run_id = await _create_run_for_user(user=user)

    _, ticket = await _issue_ticket_via_api(user)
    communicator = _ws(user, f"/ws/runs/{run_id}/?ticket={ticket}&event_types=run_completed")
    connected, _ = await _connect(communicator)
    assert connected is True

    await communicator.receive_json_from()

    channel_layer = get_channel_layer()
    assert channel_layer is not None

    await channel_layer.group_send(
        run_event_group_name(run_id=str(run_id), level=EVENT_LEVEL_MINIMAL),
        {
            "type": "broadcast.message",
            "message": {
                "event_id": "evt-filter-running",
                "type": "run.updated",
                "run_id": str(run_id),
                "level": "minimal",
                "run": {
                    "id": str(run_id),
                    "status": "running",
                    "started_at": None,
                    "ended_at": None,
                    "duration_ms": None,
                    "output_json": None,
                    "error_message": "",
                },
            },
        },
    )
    assert await communicator.receive_nothing(timeout=0.1) is True

    await channel_layer.group_send(
        run_event_group_name(run_id=str(run_id), level=EVENT_LEVEL_MINIMAL),
        {
            "type": "broadcast.message",
            "message": {
                "event_id": "evt-filter-completed",
                "type": "run.updated",
                "run_id": str(run_id),
                "level": "minimal",
                "run": {
                    "id": str(run_id),
                    "status": "succeeded",
                    "started_at": None,
                    "ended_at": None,
                    "duration_ms": None,
                    "output_json": None,
                    "error_message": "",
                },
            },
        },
    )

    message = await communicator.receive_json_from(timeout=5)
    assert message["type"] == "run_completed"
    assert message["event_id"] == "evt-filter-completed"
    await communicator.disconnect()


@pytest.mark.asyncio
@override_settings(CACHES=LOC_MEM_CACHE, CHANNEL_LAYERS=LOC_MEM_CHANNEL_LAYERS)
async def test_run_ws_resync_request_returns_backend_refetch_signal(user):
    run_id = await _create_run_for_user(user=user)

    _, ticket = await _issue_ticket_via_api(user)
    communicator = _ws(user, f"/ws/runs/{run_id}/?ticket={ticket}&last_event_id=evt-old")
    connected, _ = await _connect(communicator)
    assert connected is True

    connected_message = await communicator.receive_json_from(timeout=5)
    assert connected_message["payload"]["resync_required"] is True
    assert connected_message["payload"]["full_resync_required"] is True
    assert connected_message["payload"]["replay_supported"] is True
    assert connected_message["payload"]["last_seen_event_id"] == "evt-old"

    await communicator.send_json_to({"type": "resync"})
    resync = await communicator.receive_json_from(timeout=5)
    assert resync["type"] == "full_resync_required"
    assert resync["payload"]["replay_supported"] is True
    assert resync["payload"]["full_resync_required"] is True
    await communicator.disconnect()


@pytest.mark.asyncio
@override_settings(CACHES=LOC_MEM_CACHE, CHANNEL_LAYERS=LOC_MEM_CHANNEL_LAYERS)
async def test_run_ws_verbose_subscription_receives_verbose_messages(user):
    run_id = await _create_run_for_user(user=user)

    _, ticket = await _issue_ticket_via_api(user)
    communicator = _ws(
        user,
        f"/ws/runs/{run_id}/?ticket={ticket}&event_level=verbose",
    )
    connected, _ = await _connect(communicator)
    assert connected is True

    connected_message = await communicator.receive_json_from()
    assert connected_message["payload"]["event_level"] == "verbose"

    channel_layer = get_channel_layer()
    assert channel_layer is not None

    await channel_layer.group_send(
        run_event_group_name(run_id=str(run_id), level=EVENT_LEVEL_DEFAULT),
        {
            "type": "broadcast.message",
            "message": {
                "type": "node_stream.summary",
                "run_id": str(run_id),
                "level": "default",
                "node_stream": {
                    "node_id": "prompt_1",
                    "node_type": "prompt",
                    "attempt": 1,
                    "text_preview": "hello",
                    "chunk_count": 1,
                    "new_chunks": 1,
                    "final": False,
                },
            },
        },
    )

    message = await communicator.receive_json_from(timeout=5)
    assert message["type"] == "node_stream_chunk"
    assert message["payload"]["text_preview"] == "hello"
    await communicator.disconnect()


@pytest.mark.asyncio
@override_settings(CACHES=LOC_MEM_CACHE, CHANNEL_LAYERS=LOC_MEM_CHANNEL_LAYERS)
async def test_run_ws_allows_same_org_member(user):
    run_id = await _create_run_for_user(user=user)
    member = await _create_same_org_member(user)

    _, ticket = await _issue_ticket_for_user(member)
    communicator = _ws(member, f"/ws/runs/{run_id}/?ticket={ticket}")
    connected, _ = await _connect(communicator)
    assert connected is True
    await communicator.disconnect()


@pytest.mark.asyncio
@override_settings(
    CACHES=LOC_MEM_CACHE,
    CHANNEL_LAYERS=LOC_MEM_CHANNEL_LAYERS,
    RUN_WS_MAX_CONNECTIONS_PER_USER=1,
    RUN_WS_MAX_CONNECTIONS_PER_ORG=10,
)
async def test_run_ws_enforces_user_connection_limit(user):
    run_id = await _create_run_for_user(user=user)

    _, first_ticket = await _issue_ticket_for_user(user)
    first = _ws(user, f"/ws/runs/{run_id}/?ticket={first_ticket}")
    connected, _ = await _connect(first)
    assert connected is True
    await first.receive_json_from()

    _, second_ticket = await _issue_ticket_for_user(user)
    second = _ws(user, f"/ws/runs/{run_id}/?ticket={second_ticket}")
    connected, _ = await _connect(second)
    assert connected is False

    await second.disconnect()
    await first.disconnect()


@pytest.mark.asyncio
@override_settings(CACHES=LOC_MEM_CACHE, CHANNEL_LAYERS=LOC_MEM_CHANNEL_LAYERS)
async def test_run_ws_rejects_cross_org_user(user):
    _, run_id = await _create_other_user_and_run()

    _, ticket = await _issue_ticket_for_user(user)
    communicator = _ws(user, f"/ws/runs/{run_id}/?ticket={ticket}")
    connected, _ = await _connect(communicator)
    assert connected is False
    await communicator.disconnect()


@pytest.mark.asyncio
@override_settings(CACHES=LOC_MEM_CACHE, CHANNEL_LAYERS=LOC_MEM_CHANNEL_LAYERS)
async def test_run_ws_ticket_is_single_use(user):
    run_id = await _create_run_for_user(user=user)

    _, ticket = await _issue_ticket_for_user(user)

    first = _ws(user, f"/ws/runs/{run_id}/?ticket={ticket}")
    connected, _ = await _connect(first)
    assert connected is True
    await first.disconnect()

    second = _ws(user, f"/ws/runs/{run_id}/?ticket={ticket}")
    connected, _ = await _connect(second)
    assert connected is False
    await second.disconnect()


@pytest.mark.asyncio
@override_settings(CACHES=LOC_MEM_CACHE, CHANNEL_LAYERS=LOC_MEM_CHANNEL_LAYERS)
async def test_run_ws_rejects_ticket_when_access_token_revoked(user):
    run_id = await _create_run_for_user(user=user)

    access, ticket = await _issue_ticket_for_user(user)
    await _revoke_access(access)

    communicator = _ws(user, f"/ws/runs/{run_id}/?ticket={ticket}")
    connected, _ = await _connect(communicator)
    assert connected is False
    await communicator.disconnect()
