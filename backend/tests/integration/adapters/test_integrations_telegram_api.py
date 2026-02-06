"""Integration tests for Telegram webhook APIs."""

from __future__ import annotations

from typing import Any, cast

import pytest
from django.test import override_settings
from rest_framework import status

from infrastructure.orm.models import Graph, GraphVersion, Run

pytestmark = pytest.mark.django_db


def _create_graph_version(user: Any, *, metadata: dict[str, Any] | None = None) -> GraphVersion:
    graph = Graph.objects.create(owner=user, name="Telegram Graph")
    graph_json: dict[str, Any] = {"nodes": [], "edges": []}
    if metadata is not None:
        graph_json["metadata"] = metadata
    return cast(
        GraphVersion,
        GraphVersion.objects.create(graph=graph, version=1, graph_json=graph_json),
    )


@override_settings(TELEGRAM_WEBHOOK_SECRET="")
def test_telegram_webhook_requires_secret_configuration(api_client, user):
    version = _create_graph_version(user)

    response = api_client.post(
        f"/api/integrations/telegram/webhook/{version.id}",
        {
            "update_id": 100,
            "message": {"message_id": 10, "chat": {"id": 123}, "from": {"id": 1}, "text": "hi"},
        },
        format="json",
    )

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.data["error"]["code"] == "CONFIG_ERROR"
    assert Run.objects.count() == 0


def test_telegram_webhook_rejects_invalid_secret(api_client, user):
    version = _create_graph_version(
        user,
        metadata={"integrations": {"telegram": {"webhook_secret": "secret-123"}}},
    )

    response = api_client.post(
        f"/api/integrations/telegram/webhook/{version.id}",
        {
            "update_id": 101,
            "message": {"message_id": 11, "chat": {"id": 456}, "from": {"id": 2}, "text": "hello"},
        },
        format="json",
        HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="wrong-secret",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.data["error"]["code"] == "FORBIDDEN"
    assert Run.objects.count() == 0


@override_settings(RUN_QUEUE_ENABLED=False)
def test_telegram_webhook_creates_and_starts_run_for_text_message(
    api_client, user, mock_engine_client
):
    version = _create_graph_version(
        user,
        metadata={"integrations": {"telegram": {"webhook_secret": "secret-123"}}},
    )

    response = api_client.post(
        f"/api/integrations/telegram/webhook/{version.id}",
        {
            "update_id": 102,
            "message": {
                "message_id": 12,
                "chat": {"id": 777, "type": "private", "username": "alice"},
                "from": {"id": 3, "username": "alice"},
                "text": "Hello ForgeGraph",
            },
        },
        format="json",
        HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="secret-123",
    )

    assert response.status_code == status.HTTP_202_ACCEPTED
    run_id = response.data["data"]["id"]
    run = Run.objects.get(id=run_id)
    assert run.status == "running"
    assert run.thread_id is not None
    assert run.input_json["channel"] == "telegram"
    assert run.input_json["message"] == "Hello ForgeGraph"
    assert run.input_json["chat_id"] == 777
    assert run.input_json["telegram"]["message_type"] == "message"

    start_calls = [call for call in mock_engine_client.calls if call[0] == "start_run"]
    assert len(start_calls) == 1
    assert start_calls[0][1]["run_id"] == run.id
    assert start_calls[0][1]["input_json"]["message"] == "Hello ForgeGraph"


@override_settings(RUN_QUEUE_ENABLED=False)
def test_telegram_webhook_voice_path_populates_transcription(
    api_client, user, mock_engine_client, monkeypatch
):
    from adapters.api.integrations import telegram_views

    def _fake_transcribe(**_: Any) -> dict[str, Any]:
        return {
            "status": "completed",
            "text": "Transcribed voice message",
            "provider": "mock",
            "model": "mock-v1",
        }

    monkeypatch.setattr(telegram_views, "_transcribe_telegram_voice", _fake_transcribe)

    version = _create_graph_version(
        user,
        metadata={
            "integrations": {
                "telegram": {
                    "webhook_secret": "secret-voice",
                    "voice_transcription": {"enabled": True},
                }
            }
        },
    )

    response = api_client.post(
        f"/api/integrations/telegram/webhook/{version.id}",
        {
            "update_id": 103,
            "message": {
                "message_id": 13,
                "chat": {"id": 888, "type": "private"},
                "from": {"id": 4, "username": "voice-user"},
                "voice": {
                    "file_id": "voice-file-1",
                    "file_unique_id": "uniq-1",
                    "duration": 4,
                    "mime_type": "audio/ogg",
                },
            },
        },
        format="json",
        HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="secret-voice",
    )

    assert response.status_code == status.HTTP_202_ACCEPTED
    run = Run.objects.get(id=response.data["data"]["id"])
    assert run.input_json["message"] == "Transcribed voice message"
    assert run.input_json["telegram"]["voice"]["file_id"] == "voice-file-1"
    assert run.input_json["telegram"]["voice_transcription"]["status"] == "completed"
    assert run.input_json["telegram"]["voice_transcription"]["text"] == "Transcribed voice message"

    start_calls = [call for call in mock_engine_client.calls if call[0] == "start_run"]
    assert len(start_calls) == 1


def test_telegram_webhook_ignores_unsupported_updates(api_client, user):
    version = _create_graph_version(
        user,
        metadata={"integrations": {"telegram": {"webhook_secret": "secret-123"}}},
    )

    response = api_client.post(
        f"/api/integrations/telegram/webhook/{version.id}",
        {
            "update_id": 104,
            "callback_query": {"id": "cb-1", "data": "noop"},
        },
        format="json",
        HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="secret-123",
    )

    assert response.status_code == status.HTTP_202_ACCEPTED
    assert response.data["data"]["accepted"] is True
    assert response.data["data"]["ignored"] is True
    assert response.data["data"]["reason"] == "unsupported_update_type"
    assert Run.objects.count() == 0
