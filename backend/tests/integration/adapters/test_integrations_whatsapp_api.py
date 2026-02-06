"""Integration tests for WhatsApp (Twilio) webhook APIs."""

from __future__ import annotations

import base64
import hashlib
import hmac
from typing import Any, cast

import pytest
from rest_framework import status

from infrastructure.orm.models import Graph, GraphVersion, Run

pytestmark = pytest.mark.django_db


def _create_graph_version(user: Any, *, metadata: dict[str, Any] | None = None) -> GraphVersion:
    graph = Graph.objects.create(owner=user, name="WhatsApp Graph")
    graph_json: dict[str, Any] = {"nodes": [], "edges": []}
    if metadata is not None:
        graph_json["metadata"] = metadata
    return cast(
        GraphVersion,
        GraphVersion.objects.create(graph=graph, version=1, graph_json=graph_json),
    )


def _twilio_signature(url: str, payload: dict[str, Any], auth_token: str) -> str:
    sorted_items = sorted((key, str(value)) for key, value in payload.items())
    data = url + "".join(f"{key}{value}" for key, value in sorted_items)
    digest = hmac.new(auth_token.encode("utf-8"), data.encode("utf-8"), hashlib.sha1).digest()
    return base64.b64encode(digest).decode("utf-8")


def _webhook_url(version: GraphVersion) -> str:
    return f"http://testserver/api/integrations/whatsapp/webhook/{version.id}"


def test_whatsapp_webhook_requires_auth_token_configuration(api_client, user):
    version = _create_graph_version(
        user,
        metadata={"integrations": {"whatsapp": {"verify_signature": True}}},
    )
    payload = {
        "From": "whatsapp:+15551234567",
        "Body": "hello",
        "MessageSid": "SM123",
        "AccountSid": "AC123",
    }

    response = api_client.post(
        f"/api/integrations/whatsapp/webhook/{version.id}",
        payload,
    )

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.data["error"]["code"] == "CONFIG_ERROR"
    assert Run.objects.count() == 0


def test_whatsapp_webhook_rejects_invalid_signature(api_client, user):
    version = _create_graph_version(
        user,
        metadata={
            "integrations": {
                "whatsapp": {
                    "auth_token": "token-123",
                    "verify_signature": True,
                }
            }
        },
    )
    payload = {
        "From": "whatsapp:+15551234567",
        "Body": "hello",
        "MessageSid": "SM124",
        "AccountSid": "AC124",
    }

    response = api_client.post(
        f"/api/integrations/whatsapp/webhook/{version.id}",
        payload,
        HTTP_X_TWILIO_SIGNATURE="bad-signature",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.data["error"]["code"] == "FORBIDDEN"
    assert Run.objects.count() == 0


def test_whatsapp_webhook_creates_and_starts_run_for_text_message(
    api_client, user, mock_engine_client
):
    version = _create_graph_version(
        user,
        metadata={
            "integrations": {
                "whatsapp": {
                    "auth_token": "token-456",
                    "verify_signature": True,
                }
            }
        },
    )
    payload = {
        "From": "whatsapp:+15550001111",
        "To": "whatsapp:+15559990000",
        "Body": "Hello from WhatsApp",
        "MessageSid": "SM125",
        "AccountSid": "AC125",
        "ProfileName": "Test User",
    }
    signature = _twilio_signature(_webhook_url(version), payload, "token-456")

    response = api_client.post(
        f"/api/integrations/whatsapp/webhook/{version.id}",
        payload,
        HTTP_X_TWILIO_SIGNATURE=signature,
    )

    assert response.status_code == status.HTTP_202_ACCEPTED
    run = Run.objects.get(id=response.data["data"]["id"])
    assert run.status == "running"
    assert run.thread_id is not None
    assert run.input_json["channel"] == "whatsapp"
    assert run.input_json["message"] == "Hello from WhatsApp"
    assert run.input_json["chat_id"] == "whatsapp:+15550001111"
    assert run.input_json["whatsapp"]["message_sid"] == "SM125"

    start_calls = [call for call in mock_engine_client.calls if call[0] == "start_run"]
    assert len(start_calls) == 1
    assert start_calls[0][1]["run_id"] == run.id
    assert start_calls[0][1]["input_json"]["channel"] == "whatsapp"


def test_whatsapp_webhook_voice_path_populates_transcription(
    api_client, user, mock_engine_client, monkeypatch
):
    from adapters.api.integrations import whatsapp_views

    def _fake_transcribe(**_: Any) -> dict[str, Any]:
        return {
            "status": "completed",
            "text": "Transcribed WhatsApp voice message",
            "provider": "mock",
            "model": "mock-v1",
        }

    monkeypatch.setattr(whatsapp_views, "_transcribe_whatsapp_voice", _fake_transcribe)

    version = _create_graph_version(
        user,
        metadata={
            "integrations": {
                "whatsapp": {
                    "auth_token": "token-789",
                    "verify_signature": True,
                    "voice_transcription": {"enabled": True},
                }
            }
        },
    )
    payload = {
        "From": "whatsapp:+15558887777",
        "To": "whatsapp:+15556665555",
        "Body": "",
        "MessageSid": "SM126",
        "AccountSid": "AC126",
        "NumMedia": "1",
        "MediaUrl0": "https://api.twilio.com/media/voice-1",
        "MediaContentType0": "audio/ogg",
    }
    signature = _twilio_signature(_webhook_url(version), payload, "token-789")

    response = api_client.post(
        f"/api/integrations/whatsapp/webhook/{version.id}",
        payload,
        HTTP_X_TWILIO_SIGNATURE=signature,
    )

    assert response.status_code == status.HTTP_202_ACCEPTED
    run = Run.objects.get(id=response.data["data"]["id"])
    assert run.input_json["message"] == "Transcribed WhatsApp voice message"
    assert (
        run.input_json["whatsapp"]["voice"]["media_url"] == "https://api.twilio.com/media/voice-1"
    )
    assert run.input_json["whatsapp"]["voice_transcription"]["status"] == "completed"
    assert (
        run.input_json["whatsapp"]["voice_transcription"]["text"]
        == "Transcribed WhatsApp voice message"
    )

    start_calls = [call for call in mock_engine_client.calls if call[0] == "start_run"]
    assert len(start_calls) == 1
