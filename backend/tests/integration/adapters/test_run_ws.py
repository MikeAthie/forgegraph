"""
Integration tests for Run WebSocket updates (Channels).
"""

import pytest
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from rest_framework_simplejwt.tokens import AccessToken

from config.asgi import application
from infrastructure.orm.models import Graph, GraphVersion, Run, User

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
    assert first["type"] == "connected"
    assert first["run_id"] == str(run_id)

    channel_layer = get_channel_layer()
    assert channel_layer is not None

    await channel_layer.group_send(
        f"run_{run_id}",
        {
            "type": "broadcast.message",
            "message": {
                "type": "run.updated",
                "run_id": str(run_id),
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
    assert message["type"] == "run.updated"
    assert message["run_id"] == str(run_id)

    await communicator.disconnect()


@pytest.mark.asyncio
async def test_run_ws_rejects_non_owner(user):
    _, run_id = await _create_other_user_and_run()

    token = str(AccessToken.for_user(user))
    communicator = WebsocketCommunicator(application, f"/ws/runs/{run_id}/?token={token}")
    connected, _ = await communicator.connect()
    assert connected is False
    await communicator.disconnect()
