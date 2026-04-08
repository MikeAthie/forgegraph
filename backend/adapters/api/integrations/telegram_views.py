"""Telegram integration webhook adapters."""

from __future__ import annotations

import hmac
import logging
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid5

import requests
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework import status
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


def _extract_telegram_config(graph_json: dict[str, Any]) -> dict[str, Any]:
    metadata = _as_dict(graph_json.get("metadata"))
    integrations = _as_dict(metadata.get("integrations"))
    return _as_dict(integrations.get("telegram"))


def _extract_telegram_message(update: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    for key in ("message", "edited_message", "channel_post", "edited_channel_post"):
        message = update.get(key)
        if isinstance(message, dict):
            return message, key
    return None, None


def _extract_voice_payload(message: dict[str, Any]) -> dict[str, Any] | None:
    voice = message.get("voice")
    if not isinstance(voice, dict):
        return None
    return {
        "file_id": voice.get("file_id"),
        "file_unique_id": voice.get("file_unique_id"),
        "duration_seconds": voice.get("duration"),
        "mime_type": voice.get("mime_type"),
        "file_size": voice.get("file_size"),
    }


def _extract_external_transcript(update: dict[str, Any], message: dict[str, Any]) -> str:
    candidates: list[Any] = [
        message.get("voice_transcript"),
        _as_dict(message.get("voice_transcription")).get("text"),
        _as_dict(update.get("forgegraph")).get("voice_transcript"),
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return ""


def _resolve_telegram_bot_token(owner: User, telegram_config: dict[str, Any]) -> str:
    token = telegram_config.get("bot_token")
    if isinstance(token, str) and token.strip():
        return token.strip()

    credential_id = str(
        telegram_config.get("bot_token_credential_id") or telegram_config.get("credential_id") or ""
    ).strip()
    if not credential_id or not owner.default_organization_id:
        return ""

    try:
        credential = APIKey.objects.filter(
            id=credential_id,
            organization_id=owner.default_organization_id,
            provider="telegram",
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


def _transcribe_telegram_voice(
    *,
    bot_token: str,
    file_id: str,
    mime_type: str | None,
) -> dict[str, Any]:
    if not bot_token:
        return {"status": "skipped", "reason": "missing_bot_token"}

    openai_api_key = str(getattr(settings, "OPENAI_API_KEY", "")).strip()
    if not openai_api_key:
        return {"status": "skipped", "reason": "missing_openai_api_key"}

    timeout_seconds = int(getattr(settings, "TELEGRAM_WEBHOOK_REQUEST_TIMEOUT_SECONDS", 15))
    model = str(getattr(settings, "TELEGRAM_VOICE_TRANSCRIPTION_MODEL", "whisper-1"))

    try:
        get_file_response = requests.get(
            f"https://api.telegram.org/bot{bot_token}/getFile",
            params={"file_id": file_id},
            timeout=timeout_seconds,
        )
        get_file_response.raise_for_status()
        get_file_payload = _as_dict(get_file_response.json())
        result = _as_dict(get_file_payload.get("result"))
        file_path = str(result.get("file_path") or "").strip()
        if not file_path:
            return {"status": "failed", "reason": "missing_file_path"}

        file_response = requests.get(
            f"https://api.telegram.org/file/bot{bot_token}/{file_path}",
            timeout=timeout_seconds,
        )
        file_response.raise_for_status()

        filename = file_path.rsplit("/", maxsplit=1)[-1] or "voice.ogg"
        files = {
            "file": (
                filename,
                file_response.content,
                mime_type or "audio/ogg",
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
        text = str(openai_payload.get("text") or "").strip()
        if not text:
            return {"status": "failed", "reason": "empty_transcript"}
        return {"status": "completed", "text": text, "provider": "openai", "model": model}
    except requests.RequestException as exc:
        logger.warning("Telegram voice transcription failed: %s", exc)
        return {"status": "failed", "reason": "request_error"}


def _normalize_telegram_input(
    *,
    update: dict[str, Any],
    message: dict[str, Any],
    message_type: str,
    owner: User,
    telegram_config: dict[str, Any],
) -> dict[str, Any]:
    chat = _as_dict(message.get("chat"))
    sender = _as_dict(message.get("from"))
    voice_payload = _extract_voice_payload(message)

    text_message = str(message.get("text") or message.get("caption") or "").strip()

    transcription_cfg = _as_dict(telegram_config.get("voice_transcription"))
    transcription_enabled = bool(transcription_cfg.get("enabled"))
    transcription_result: dict[str, Any] = {
        "enabled": transcription_enabled,
        "status": "disabled",
        "text": None,
        "reason": None,
    }

    if voice_payload and transcription_enabled:
        transcript = _extract_external_transcript(update, message)
        if transcript:
            transcription_result = {
                "enabled": True,
                "status": "completed",
                "text": transcript,
                "provider": "external",
                "reason": None,
            }
        else:
            bot_token = _resolve_telegram_bot_token(owner, telegram_config)
            transcription = _transcribe_telegram_voice(
                bot_token=bot_token,
                file_id=str(voice_payload.get("file_id") or ""),
                mime_type=cast(str | None, voice_payload.get("mime_type")),
            )
            transcription_result = {
                "enabled": True,
                "status": transcription.get("status") or "failed",
                "text": transcription.get("text"),
                "provider": transcription.get("provider"),
                "model": transcription.get("model"),
                "reason": transcription.get("reason"),
            }

    final_message = text_message
    if not final_message and isinstance(transcription_result.get("text"), str):
        final_message = str(transcription_result["text"])

    return {
        "channel": "telegram",
        "message": final_message,
        "chat_id": chat.get("id"),
        "chat_type": chat.get("type"),
        "message_id": message.get("message_id"),
        "user_id": sender.get("id"),
        "telegram": {
            "update_id": update.get("update_id"),
            "message_type": message_type,
            "chat": {
                "id": chat.get("id"),
                "type": chat.get("type"),
                "title": chat.get("title"),
                "username": chat.get("username"),
            },
            "sender": {
                "id": sender.get("id"),
                "is_bot": sender.get("is_bot"),
                "first_name": sender.get("first_name"),
                "last_name": sender.get("last_name"),
                "username": sender.get("username"),
                "language_code": sender.get("language_code"),
            },
            "message": {
                "id": message.get("message_id"),
                "date": message.get("date"),
                "text": text_message,
                "caption": message.get("caption"),
                "is_voice": voice_payload is not None,
            },
            "voice": voice_payload,
            "voice_transcription": transcription_result,
        },
    }


def _thread_id_for_telegram_chat(*, graph_version_id: UUID, chat_id: Any) -> UUID | None:
    if chat_id in (None, ""):
        return None
    return uuid5(NAMESPACE_URL, f"telegram:{graph_version_id}:{chat_id}")


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


class TelegramWebhookView(APIView):
    """Receive Telegram updates and dispatch graph runs."""

    permission_classes = [AllowAny]

    def post(self, request: Request, graph_version_id: UUID) -> Response:
        payload = request.data
        if not isinstance(payload, dict):
            return error_response(
                code="VALIDATION_ERROR",
                message="Telegram webhook payload must be a JSON object.",
                status=status.HTTP_400_BAD_REQUEST,
            )

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

        telegram_config = _extract_telegram_config(graph_version.graph_json)
        expected_secret = str(
            telegram_config.get("webhook_secret")
            or getattr(settings, "TELEGRAM_WEBHOOK_SECRET", "")
        ).strip()
        if not expected_secret:
            return error_response(
                code="CONFIG_ERROR",
                message="Telegram webhook secret is not configured for this graph.",
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        provided_secret = str(request.headers.get("X-Telegram-Bot-Api-Secret-Token") or "").strip()
        if not provided_secret or not hmac.compare_digest(provided_secret, expected_secret):
            return error_response(
                code="FORBIDDEN",
                message="Telegram webhook secret verification failed.",
                status=status.HTTP_403_FORBIDDEN,
            )

        message, message_type = _extract_telegram_message(payload)
        if message is None or message_type is None:
            return success_response(
                {
                    "accepted": True,
                    "ignored": True,
                    "reason": "unsupported_update_type",
                },
                status=status.HTTP_202_ACCEPTED,
            )

        owner = cast(User, graph_version.graph.owner)
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

        input_json = _normalize_telegram_input(
            update=payload,
            message=message,
            message_type=message_type,
            owner=owner,
            telegram_config=telegram_config,
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

        thread_id = _thread_id_for_telegram_chat(
            graph_version_id=graph_version.id,
            chat_id=input_json.get("chat_id"),
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
            action="run.started.telegram_webhook",
            resource_type="run",
            resource_id=str(run.id),
            metadata={
                "graph_id": str(graph_version.graph_id),
                "channel": "telegram",
                "update_id": payload.get("update_id"),
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
                meta={"queued": True, "channel": "telegram"},
            )

        callback_url = run_views.resolve_engine_callback_url(run_id=str(run.id))
        memory_config_json = build_memory_config_json(
            graph_version.graph,
            owner,
            session_id=session_id,
        )
        try:
            with start_backend_span(
                "integrations.telegram.start",
                traceparent=trace_metadata["traceparent"],
                tracestate=trace_metadata["tracestate"],
                attributes={
                    "forgegraph.run_id": str(run.id),
                    "forgegraph.graph_version_id": str(graph_version.id),
                    "forgegraph.channel": "telegram",
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
            logger.error("Engine connection failed for Telegram run %s: %s", run.id, exc)
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
            logger.error("Engine rejected Telegram run %s: %s", run.id, exc)
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
            meta={"channel": "telegram"},
        )
