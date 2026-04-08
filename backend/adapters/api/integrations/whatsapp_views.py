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
from django.utils import timezone
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.responses import error_response, success_response
from adapters.api.runs import views as run_views
from adapters.api.runs.serializers import RunDetailWithNodeRunsSerializer
from adapters.gateways.grpc_engine_client import EngineConnectionError, EngineExecutionError
from adapters.ws.runs.broadcast import broadcast_run_updated
from application.services.audit_log import record_audit_log
from application.services.credential_state import is_credential_revoked
from application.services.metrics import record_run_completed, record_run_started
from application.services.run_preparation import (
    PromptTemplateResolutionError,
    SubgraphResolutionError,
    build_memory_config_json,
    prepare_graph_for_engine,
    upsert_memory_session,
    validate_prompt_credentials,
)
from application.services.run_queue import enqueue_run
from application.services.schema_validation import (
    SchemaError,
    extract_schema_metadata,
    validate_json_schema,
)
from application.services.telemetry import start_backend_span
from application.services.trace_context import ensure_trace_context
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

        tenant_id = run_views.get_tenant_id_for_user(owner)
        rate_limit_response = run_views._apply_rate_limit(
            scope="run_start",
            tenant_id=tenant_id,
            limit=getattr(settings, "RUN_START_RATE_LIMIT_PER_MIN", 0),
            window_seconds=getattr(settings, "RUN_RATE_LIMIT_WINDOW_SECONDS", 60),
        )
        if rate_limit_response is not None:
            return rate_limit_response

        entitlement_response = run_views.check_entitlements(owner)
        if entitlement_response is not None:
            return entitlement_response

        quota_response = run_views.check_llm_quota(owner)
        if quota_response is not None:
            return quota_response

        budget_response = run_views.check_llm_budget(owner)
        if budget_response is not None:
            return budget_response

        input_json = _normalize_whatsapp_input(
            payload=payload,
            owner=owner,
            whatsapp_config=whatsapp_config,
        )

        input_schema, _, _, _ = extract_schema_metadata(graph_version.graph_json)
        if input_schema:
            try:
                schema_errors = validate_json_schema(input_json, input_schema)
            except SchemaError as exc:
                return error_response(
                    code="INVALID_SCHEMA",
                    message="Input schema is invalid.",
                    status=status.HTTP_400_BAD_REQUEST,
                    details=[{"message": str(exc)}],
                )

            if schema_errors:
                return error_response(
                    code="INVALID_INPUT_SCHEMA",
                    message="Input does not match the required schema.",
                    status=status.HTTP_400_BAD_REQUEST,
                    details=schema_errors,
                )

        try:
            prepared_graph = prepare_graph_for_engine(
                graph_version.graph_json,
                owner,
                traceparent=request.headers.get("traceparent"),
                tracestate=request.headers.get("tracestate"),
            )
        except (PromptTemplateResolutionError, SubgraphResolutionError, ValueError) as exc:
            return run_views._run_preparation_error_response(exc)
        trace_metadata = ensure_trace_context(
            traceparent=str(
                prepared_graph.get("metadata", {}).get("trace", {}).get("traceparent", "")
            ).strip()
            or None,
            tracestate=str(
                prepared_graph.get("metadata", {}).get("trace", {}).get("tracestate", "")
            ).strip()
            or None,
        )

        credential_errors = validate_prompt_credentials(prepared_graph, owner)
        if credential_errors:
            return error_response(
                code="INVALID_CREDENTIALS",
                message="Prompt node credentials are missing or invalid.",
                status=status.HTTP_400_BAD_REQUEST,
                details=credential_errors,
            )

        thread_id = _thread_id_for_whatsapp_sender(
            graph_version_id=graph_version.id,
            sender=_as_str(input_json.get("chat_id")),
        )
        session_id = str(thread_id) if thread_id else None

        run = Run.objects.create(
            owner=owner,
            graph_version=graph_version,
            thread_id=thread_id,
            status="pending",
            started_at=timezone.now(),
            ended_at=None,
            input_json=input_json,
            output_json=None,
            error_message="",
            trace_id=trace_metadata["trace_id"],
        )
        broadcast_run_updated(run)
        record_audit_log(
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
        )

        upsert_memory_session(owner, session_id)

        if getattr(settings, "RUN_QUEUE_ENABLED", False):
            queue_entry = enqueue_run(run, tenant_id=tenant_id)
            serialized_data = RunDetailWithNodeRunsSerializer(
                {
                    **_run_payload(run, graph_version),
                    "queue_status": queue_entry.status,
                    "queue_attempts": queue_entry.attempts,
                    "queue_available_at": queue_entry.available_at,
                }
            ).data
            return success_response(
                serialized_data,
                status=status.HTTP_202_ACCEPTED,
                meta={"queued": True, "channel": "whatsapp"},
            )

        callback_url = run_views.resolve_engine_callback_url(run_id=str(run.id))
        memory_config_json = build_memory_config_json(
            graph_version.graph,
            owner,
            session_id=session_id,
        )
        try:
            with start_backend_span(
                "integrations.whatsapp.start",
                traceparent=trace_metadata["traceparent"],
                tracestate=trace_metadata["tracestate"],
                attributes={
                    "forgegraph.run_id": str(run.id),
                    "forgegraph.graph_version_id": str(graph_version.id),
                    "forgegraph.channel": "whatsapp",
                },
            ):
                selected_engine_id, engine_client = run_views.get_engine_assignment(
                    run_id=str(run.id),
                    callback_url=callback_url,
                )
                with engine_client as engine:
                    engine.start_run(
                        run_id=run.id,
                        graph_json=prepared_graph,
                        input_json=input_json,
                        memory_config_json=memory_config_json,
                        tenant_id=tenant_id,
                        session_id=session_id,
                        traceparent=trace_metadata["traceparent"],
                        tracestate=trace_metadata["tracestate"],
                    )
                    run.status = "running"
                    update_fields = ["status"]
                    update_fields.extend(
                        run_views.touch_run_liveness(
                            run,
                            recovery_state=run_views.recovery_state_for_status("running"),
                            engine_instance_id=selected_engine_id,
                        )
                    )
                    run.save(update_fields=sorted(set(update_fields)))
                    record_run_started()
                    broadcast_run_updated(run)
        except EngineConnectionError as exc:
            logger.error("Engine connection failed for WhatsApp run %s: %s", run.id, exc)
            run.status = "failed"
            run.ended_at = timezone.now()
            run.error_message = f"Engine connection failed: {exc}"
            run.save(update_fields=["status", "ended_at", "error_message"])
            record_run_completed("failed", run.duration_ms)
            broadcast_run_updated(run)
            return error_response(
                code="ENGINE_UNAVAILABLE",
                message="The execution engine is not available. Please try again later.",
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except EngineExecutionError as exc:
            logger.error("Engine rejected WhatsApp run %s: %s", run.id, exc)
            run.status = "failed"
            run.ended_at = timezone.now()
            run.error_message = f"Engine rejected run: {exc}"
            run.save(update_fields=["status", "ended_at", "error_message"])
            record_run_completed("failed", run.duration_ms)
            broadcast_run_updated(run)
            return error_response(
                code="ENGINE_ERROR",
                message=str(exc),
                status=status.HTTP_400_BAD_REQUEST,
            )

        serialized_data = RunDetailWithNodeRunsSerializer(_run_payload(run, graph_version)).data
        return success_response(
            serialized_data,
            status=status.HTTP_202_ACCEPTED,
            meta={"channel": "whatsapp"},
        )
