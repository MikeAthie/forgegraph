"""
Integration tests for Run WebSocket updates (Channels).
"""

import pytest
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from rest_framework_simplejwt.tokens import AccessToken

<<<<<<< Updated upstream
=======
from application.services.auth_state import issue_ws_ticket, revoke_access_token
from application.services.run_event_streaming import (
    EVENT_LEVEL_CRITICAL,
    EVENT_LEVEL_DEFAULT,
    EVENT_LEVEL_VERBOSE,
    run_event_group_name,
)
>>>>>>> Stashed changes
from config.asgi import application
from infrastructure.orm.models import Graph, GraphVersion, OrganizationMembership, Run, User

pytestmark = pytest.mark.django_db(transaction=True)


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


<<<<<<< Updated upstream
=======
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
    response = client.post("/api/ws-ticket", {}, format="json")
    assert response.status_code == 201
    return access, response.data["ticket"]


@database_sync_to_async
def _create_same_org_member(user: User) -> User:
    member = User.objects.create_user(email="viewer@example.com", password="password123")
    member.default_organization = user.default_organization
    member.save(update_fields=["default_organization"])
    OrganizationMembership.objects.create(
        organization=user.default_organization,
        user=member,
        role="viewer",
        is_default=True,
    )
    return member


@database_sync_to_async
def _revoke_access(raw_token: str) -> None:
    revoke_access_token(AccessToken(cast(Any, raw_token)))


>>>>>>> Stashed changes
@pytest.mark.asyncio
async def test_run_ws_rejects_missing_token(user):
    run_id = await _create_run_for_user(user=user)

    communicator = WebsocketCommunicator(application, f"/ws/runs/{run_id}/")
    connected, _ = await communicator.connect()
    assert connected is False
    await communicator.disconnect()


@pytest.mark.asyncio
async def test_run_ws_allows_owner_and_receives_broadcast(user):
    run_id = await _create_run_for_user(user=user)

    token = str(AccessToken.for_user(user))
    communicator = WebsocketCommunicator(application, f"/ws/runs/{run_id}/?token={token}")
    connected, _ = await communicator.connect()
    assert connected is True

    first = await communicator.receive_json_from()
    assert first["type"] == "connection_established"
    assert first["run_id"] == str(run_id)
    assert first["payload"]["event_level"] == "default"

    channel_layer = get_channel_layer()
    assert channel_layer is not None

    await channel_layer.group_send(
        f"run_{run_id}",
        {
            "type": "broadcast.message",
            "message": {
                "type": "run.updated",
                "run_id": str(run_id),
<<<<<<< Updated upstream
=======
                "level": "minimal",
>>>>>>> Stashed changes
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

    message = await communicator.receive_json_from()
    assert message["type"] == "run_started"
    assert message["run_id"] == str(run_id)
    assert message["payload"]["run"]["status"] == "running"

    await communicator.disconnect()


@pytest.mark.asyncio
<<<<<<< Updated upstream
async def test_run_ws_rejects_non_owner(user):
=======
@override_settings(CACHES=LOC_MEM_CACHE)
async def test_run_ws_default_subscription_drops_verbose_messages(user):
    run_id = await _create_run_for_user(user=user)

    _, ticket = await _issue_ticket_via_api(user)
    communicator = WebsocketCommunicator(application, f"/ws/runs/{run_id}/?ticket={ticket}")
    connected, _ = await communicator.connect()
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
@override_settings(CACHES=LOC_MEM_CACHE)
async def test_run_ws_verbose_subscription_receives_verbose_messages(user):
    run_id = await _create_run_for_user(user=user)

    _, ticket = await _issue_ticket_via_api(user)
    communicator = WebsocketCommunicator(
        application,
        f"/ws/runs/{run_id}/?ticket={ticket}&event_level=verbose",
    )
    connected, _ = await communicator.connect()
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

    message = await communicator.receive_json_from()
    assert message["type"] == "node_stream_chunk"
    assert message["payload"]["text_preview"] == "hello"
    await communicator.disconnect()


@pytest.mark.asyncio
@override_settings(CACHES=LOC_MEM_CACHE)
async def test_run_ws_allows_same_org_member(user):
    run_id = await _create_run_for_user(user=user)
    member = await _create_same_org_member(user)

    _, ticket = await _issue_ticket_for_user(member)
    communicator = WebsocketCommunicator(application, f"/ws/runs/{run_id}/?ticket={ticket}")
    connected, _ = await communicator.connect()
    assert connected is True
    await communicator.disconnect()


@pytest.mark.asyncio
@override_settings(CACHES=LOC_MEM_CACHE)
async def test_run_ws_rejects_cross_org_user(user):
>>>>>>> Stashed changes
    _, run_id = await _create_other_user_and_run()

    token = str(AccessToken.for_user(user))
    communicator = WebsocketCommunicator(application, f"/ws/runs/{run_id}/?token={token}")
    connected, _ = await communicator.connect()
    assert connected is False
    await communicator.disconnect()
