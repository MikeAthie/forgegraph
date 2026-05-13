"""WhatsApp (Twilio) integration webhook adapters."""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid5

import requests
from django.conf import settings
from django.core.exceptions import ValidationError
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.integrations.run_dispatch import (
    finalize_integration_run,
    prepare_integration_run_context,
)
from adapters.api.responses import error_response, success_response
from adapters.api.runs import views as run_views
from application.services.audit_log import record_audit_log
from application.services.credential_state import is_credential_revoked
from infrastructure.crypto.encryption import decrypt_api_key
from infrastructure.orm.models import APIKey, GraphVersion, Run, User

logger = logging.getLogger(__name__)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _extract_whatsapp_config(graph_json: dict[str, Any]) -> dict[str, Any]:
    metadata = _as_dict(graph_json.get("metadata"))
    integrations = _as_dict(metadata.get("integrations"))
    return _as_dict(integrations.get("whatsapp"))


def _resolve_twilio_auth_token(owner: User, whatsapp_config: dict[str, Any]) -> str:
    auth_token = _as_str(whatsapp_config.get("auth_token"))
    if auth_token:
        return auth_token

    credential_id = _as_str(
        whatsapp_config.get("auth_token_credential_id") or whatsapp_config.get("credential_id")
    )
    if not credential_id or not owner.default_organization_id:
        return ""

    try:
        credential = APIKey.objects.filter(
            id=credential_id,
            organization_id=owner.default_organization_id,
            provider="twilio",
        ).first()
    except (ValidationError, ValueError):
        return ""
    if credential is None:
        return ""
    if is_credential_revoked(credential.token_metadata):
        return ""

    try:
        return decrypt_api_key(bytes(credential.encrypted_key)).strip()
    except Exception:
        return ""


def _twilio_signature_payload(url: str, form_data: dict[str, Any]) -> str:
    sorted_items = sorted((key, _as_str(value)) for key, value in form_data.items())
    return url + "".join(f"{key}{value}" for key, value in sorted_items)


def _is_valid_twilio_signature(
    *,
    auth_token: str,
    provided_signature: str,
    request_url: str,
    form_data: dict[str, Any],
) -> bool:
    if not auth_token or not provided_signature:
        return False

    payload = _twilio_signature_payload(request_url, form_data)
    digest = hmac.new(auth_token.encode("utf-8"), payload.encode("utf-8"), hashlib.sha1).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected, provided_signature.strip())


def _extract_voice_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    num_media_raw = _as_str(payload.get("NumMedia"))
    try:
        num_media = int(num_media_raw or "0")
    except ValueError:
        num_media = 0

    if num_media <= 0:
        return None

    media_url = _as_str(payload.get("MediaUrl0"))
    media_content_type = _as_str(payload.get("MediaContentType0"))
    if not media_url:
        return None
    if not media_content_type.startswith("audio/"):
        return None

    return {
        "media_url": media_url,
        "content_type": media_content_type,
        "num_media": num_media,
    }


def _extract_external_transcript(payload: dict[str, Any]) -> str:
    for key in ("SpeechResult", "VoiceTranscript", "TranscriptionText"):
        candidate = _as_str(payload.get(key))
        if candidate:
            return candidate
    return ""


def _transcribe_whatsapp_voice(
    *,
    auth_token: str,
    account_sid: str,
    media_url: str,
    content_type: str,
) -> dict[str, Any]:
    if not auth_token or not account_sid:
        return {"status": "skipped", "reason": "missing_twilio_credentials"}

    openai_api_key = _as_str(getattr(settings, "OPENAI_API_KEY", ""))
    if not openai_api_key:
        return {"status": "skipped", "reason": "missing_openai_api_key"}

    timeout_seconds = int(getattr(settings, "WHATSAPP_WEBHOOK_REQUEST_TIMEOUT_SECONDS", 15))
    model = (
        _as_str(getattr(settings, "WHATSAPP_VOICE_TRANSCRIPTION_MODEL", "whisper-1")) or "whisper-1"
    )

    try:
        media_response = requests.get(
            media_url,
            auth=(account_sid, auth_token),
            timeout=timeout_seconds,
        )
        media_response.raise_for_status()

        filename = "voice"
        if content_type == "audio/ogg":
            filename = "voice.ogg"
        elif content_type == "audio/mpeg":
            filename = "voice.mp3"
        elif content_type == "audio/wav":
            filename = "voice.wav"

        files = {
            "file": (
                filename,
                media_response.content,
                content_type,
            )
        }
        openai_response = requests.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {openai_api_key}"},
            data={"model": model},
            files=files,
            timeout=timeout_seconds,
        )
        openai_response.raise_for_status()
        openai_payload = _as_dict(openai_response.json())
        text = _as_str(openai_payload.get("text"))
        if not text:
            return {"status": "failed", "reason": "empty_transcript"}
        return {"status": "completed", "text": text, "provider": "openai", "model": model}
    except requests.RequestException as exc:
        logger.warning("WhatsApp voice transcription failed: %s", exc)
        return {"status": "failed", "reason": "request_error"}


def _normalize_whatsapp_input(
    *,
    payload: dict[str, Any],
    owner: User,
    whatsapp_config: dict[str, Any],
) -> dict[str, Any]:
    body_text = _as_str(payload.get("Body"))
    from_number = _as_str(payload.get("From"))
    to_number = _as_str(payload.get("To"))
    message_sid = _as_str(payload.get("MessageSid"))
    account_sid = _as_str(payload.get("AccountSid"))
    profile_name = _as_str(payload.get("ProfileName"))
    voice_payload = _extract_voice_payload(payload)

    transcription_cfg = _as_dict(whatsapp_config.get("voice_transcription"))
    transcription_enabled = bool(transcription_cfg.get("enabled"))
    transcription_result: dict[str, Any] = {
        "enabled": transcription_enabled,
        "status": "disabled",
        "text": None,
        "reason": None,
    }

    if voice_payload and transcription_enabled:
        external_transcript = _extract_external_transcript(payload)
        if external_transcript:
            transcription_result = {
                "enabled": True,
                "status": "completed",
                "text": external_transcript,
                "provider": "twilio",
                "reason": None,
            }
        else:
            auth_token = _resolve_twilio_auth_token(owner, whatsapp_config)
            transcription = _transcribe_whatsapp_voice(
                auth_token=auth_token,
                account_sid=account_sid,
                media_url=_as_str(voice_payload.get("media_url")),
                content_type=_as_str(voice_payload.get("content_type")),
            )
            transcription_result = {
                "enabled": True,
                "status": transcription.get("status") or "failed",
                "text": transcription.get("text"),
                "provider": transcription.get("provider"),
                "model": transcription.get("model"),
                "reason": transcription.get("reason"),
            }

    final_message = body_text
    if not final_message and isinstance(transcription_result.get("text"), str):
        final_message = str(transcription_result["text"])

    return {
        "channel": "whatsapp",
        "message": final_message,
        "chat_id": from_number,
        "message_id": message_sid,
        "whatsapp": {
            "from": from_number,
            "to": to_number,
            "account_sid": account_sid,
            "message_sid": message_sid,
            "profile_name": profile_name,
            "num_media": _as_str(payload.get("NumMedia")),
            "voice": voice_payload,
            "voice_transcription": transcription_result,
            "raw": payload,
        },
    }


def _thread_id_for_whatsapp_sender(*, graph_version_id: UUID, sender: str) -> UUID | None:
    if not sender:
        return None
    return uuid5(NAMESPACE_URL, f"whatsapp:{graph_version_id}:{sender}")


def _run_payload(run: Run, graph_version: GraphVersion) -> dict[str, Any]:
    return {
        "id": run.id,
        "owner_id": run.owner_id,
        "thread_id": run.thread_id,
        "graph_id": graph_version.graph_id,
        "graph_name": graph_version.graph.name,
        "graph_version_id": graph_version.id,
        "graph_version": graph_version.version,
        "status": run.status,
        **run_views._queue_payload(run),
        "started_at": run.started_at,
        "ended_at": run.ended_at,
        "input_json": run.input_json,
        "output_json": run.output_json,
        "error_message": run.error_message,
        "duration_ms": run.duration_ms,
        "trace_id": run.trace_id,
        "node_runs": [],
    }


class WhatsAppWebhookView(APIView):
    """Receive Twilio WhatsApp webhooks and dispatch graph runs."""

    permission_classes = [AllowAny]
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def post(self, request: Request, graph_version_id: UUID) -> Response:
        payload_raw = request.data
        if not isinstance(payload_raw, dict):
            return error_response(
                code="VALIDATION_ERROR",
                message="WhatsApp webhook payload must be an object.",
                status=status.HTTP_400_BAD_REQUEST,
            )
        payload = {str(key): value for key, value in payload_raw.items()}

        try:
            graph_version = GraphVersion.objects.select_related("graph__owner").get(
                id=graph_version_id
            )
        except GraphVersion.DoesNotExist:
            return error_response(
                code="NOT_FOUND",
                message=f"GraphVersion with id '{graph_version_id}' was not found.",
                status=status.HTTP_404_NOT_FOUND,
            )

        owner = cast(User, graph_version.graph.owner)
        whatsapp_config = _extract_whatsapp_config(graph_version.graph_json)

        verify_signature = bool(whatsapp_config.get("verify_signature", True))
        if verify_signature:
            auth_token = _resolve_twilio_auth_token(owner, whatsapp_config)
            if not auth_token:
                return error_response(
                    code="CONFIG_ERROR",
                    message="Twilio auth token is not configured for this graph.",
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )

            provided_signature = _as_str(request.headers.get("X-Twilio-Signature"))
            request_url = request.build_absolute_uri()
            if not _is_valid_twilio_signature(
                auth_token=auth_token,
                provided_signature=provided_signature,
                request_url=request_url,
                form_data=payload,
            ):
                return error_response(
                    code="FORBIDDEN",
                    message="Twilio webhook signature verification failed.",
                    status=status.HTTP_403_FORBIDDEN,
                )

        from_number = _as_str(payload.get("From"))
        body_text = _as_str(payload.get("Body"))
        if not from_number and not body_text:
            return success_response(
                {
                    "accepted": True,
                    "ignored": True,
                    "reason": "unsupported_message_payload",
                },
                status=status.HTTP_202_ACCEPTED,
            )

        input_json = _normalize_whatsapp_input(
            payload=payload,
            owner=owner,
            whatsapp_config=whatsapp_config,
        )
        thread_id = _thread_id_for_whatsapp_sender(
            graph_version_id=graph_version.id,
            sender=_as_str(input_json.get("chat_id")),
        )
        session_id = str(thread_id) if thread_id else None

        context = prepare_integration_run_context(
            graph_version=graph_version,
            owner=owner,
            request=request,
            input_json=input_json,
            thread_id=thread_id,
        )
        if isinstance(context, Response):
            return context

        return finalize_integration_run(
            context=context,
            graph_version=graph_version,
            owner=owner,
            session_id=session_id,
            input_json=input_json,
            channel="whatsapp",
            span_name="integrations.whatsapp.start",
            log_label="WhatsApp",
            logger=logger,
            run_payload=_run_payload,
            record_audit=lambda run, tenant_id: record_audit_log(
                actor=owner,
                tenant_id=tenant_id,
                action="run.started.whatsapp_webhook",
                resource_type="run",
                resource_id=str(run.id),
                metadata={
                    "graph_id": str(graph_version.graph_id),
                    "channel": "whatsapp",
                    "message_sid": _as_str(payload.get("MessageSid")),
                },
            ),
        )
