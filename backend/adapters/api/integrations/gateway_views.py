"""Hermes-style gateway webhook ingress adapters."""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.integrations.run_dispatch import (
    finalize_integration_run,
    prepare_integration_run_context,
)
from adapters.api.responses import error_response, success_response
from adapters.api.runs.responses import _queue_payload
from application.services.audit_log import record_audit_log
from application.services.gateway_connectors import normalize_platform
from application.services.gateway_inbound import (
    materialize_gateway_inbound,
    resolve_gateway_connection_for_event,
)
from infrastructure.orm.models import GatewayInboundReceipt, GraphVersion, Run, User

logger = logging.getLogger(__name__)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_str(value: Any) -> str:
    return "" if value is None else str(value).strip()


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
        **_queue_payload(run),
        "started_at": run.started_at,
        "ended_at": run.ended_at,
        "input_json": run.input_json,
        "output_json": run.output_json,
        "error_message": run.error_message,
        "duration_ms": run.duration_ms,
        "trace_id": run.trace_id,
        "node_runs": [],
    }


def _thread_id_for_gateway_source(
    *,
    graph_version_id: UUID,
    platform: str,
    conversation_id: str,
) -> UUID | None:
    value = conversation_id.strip()
    if not value:
        return None
    return uuid5(NAMESPACE_URL, f"gateway:{platform}:{graph_version_id}:{value}")


def _payload_from_request(request: Request) -> dict[str, Any]:
    if isinstance(request.data, dict):
        return {str(key): value for key, value in request.data.items()}
    return {}


def _normalize_gateway_input(platform: str, request: Request) -> dict[str, Any]:
    payload = _payload_from_request(request)
    headers = {str(key).lower(): str(value) for key, value in request.headers.items() if key}
    query = {str(key): values for key, values in request.query_params.lists()}

    if platform == "slack":
        event = _as_dict(payload.get("event"))
        return {
            "channel": "slack",
            "message": _as_str(event.get("text") or payload.get("text")),
            "gateway": {
                "platform": platform,
                "provider": "slack",
                "event_id": _as_str(payload.get("event_id") or event.get("client_msg_id")),
                "conversation_id": _as_str(event.get("channel")),
                "sender": _as_str(event.get("user")),
                "thread_id": _as_str(event.get("thread_ts") or event.get("ts")),
                "attachments": _attachment_values(event.get("files")),
                "payload": payload,
                "headers": headers,
            },
            "payload": payload,
        }

    if platform == "whatsapp":
        value = _first_nested(payload, "entry", "changes", "value")
        message = _first_item(value.get("messages")) if isinstance(value, dict) else {}
        text = _as_dict(message.get("text"))
        return {
            "channel": "whatsapp",
            "message": _as_str(text.get("body")),
            "gateway": {
                "platform": platform,
                "provider": "whatsapp_cloud_api",
                "event_id": _as_str(message.get("id")),
                "conversation_id": _as_str(message.get("from")),
                "sender": _as_str(message.get("from")),
                "attachments": _whatsapp_attachments(message),
                "payload": payload,
                "headers": headers,
            },
            "payload": payload,
        }

    if platform == "sms":
        return {
            "channel": "sms",
            "message": _as_str(payload.get("Body") or payload.get("body")),
            "gateway": {
                "platform": platform,
                "provider": "twilio",
                "event_id": _as_str(payload.get("MessageSid") or payload.get("SmsSid")),
                "conversation_id": _as_str(payload.get("From") or payload.get("from")),
                "sender": _as_str(payload.get("From") or payload.get("from")),
                "payload": payload,
                "headers": headers,
            },
            "payload": payload,
        }

    if platform == "msgraph_webhook":
        notification = _first_item(payload.get("value"))
        return {
            "channel": "microsoft_graph",
            "message": _as_str(notification.get("resource") or "Microsoft Graph notification"),
            "gateway": {
                "platform": platform,
                "provider": "microsoft_graph",
                "event_id": _as_str(notification.get("id") or notification.get("resourceData")),
                "conversation_id": _as_str(notification.get("resource")),
                "sender": "microsoft_graph",
                "payload": payload,
                "headers": headers,
            },
            "payload": payload,
        }

    event_id = _as_str(payload.get("id") or payload.get("event_id") or payload.get("message_id"))
    conversation_id = _as_str(payload.get("conversation_id") or payload.get("thread_id"))
    return {
        "channel": platform,
        "message": _as_str(payload.get("message") or payload.get("text") or payload.get("body")),
        "gateway": {
            "platform": platform,
            "provider": platform,
            "event_id": event_id,
                "conversation_id": conversation_id,
                "sender": _as_str(payload.get("sender") or payload.get("from") or payload.get("user")),
                "attachments": _attachment_values(payload.get("attachments")),
                "payload": payload,
                "headers": headers,
                "query": query,
        },
        "payload": payload,
    }


def _first_nested(payload: dict[str, Any], *keys: str) -> dict[str, Any]:
    current: Any = payload
    for key in keys:
        if isinstance(current, list):
            current = _first_item(current)
        if not isinstance(current, dict):
            return {}
        current = current.get(key)
    if isinstance(current, list):
        current = _first_item(current)
    return current if isinstance(current, dict) else {}


def _first_item(value: Any) -> dict[str, Any]:
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return value[0]
    return {}


def _attachment_values(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [{str(key): item for key, item in raw.items()} for raw in value if isinstance(raw, dict)]


def _whatsapp_attachments(message: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for media_kind in ("image", "audio", "video", "document", "sticker"):
        media = message.get(media_kind)
        if isinstance(media, dict):
            result.append({"media_kind": media_kind, **{str(key): value for key, value in media.items()}})
    return result


def _external_event_id(platform: str, input_json: dict[str, Any], body: bytes) -> str:
    gateway = _as_dict(input_json.get("gateway"))
    explicit = _as_str(gateway.get("event_id"))
    if explicit:
        return explicit[:255]
    digest = hashlib.sha256(body or repr(input_json).encode("utf-8")).hexdigest()
    return f"{platform}:{digest}"[:255]


def _verify_gateway_request(platform: str, request: Request, payload: dict[str, Any]) -> bool:
    if platform == "slack":
        secret = _as_str(getattr(settings, "SLACK_SIGNING_SECRET", ""))
        timestamp = _as_str(request.headers.get("X-Slack-Request-Timestamp"))
        signature = _as_str(request.headers.get("X-Slack-Signature"))
        base = f"v0:{timestamp}:{request.body.decode('utf-8', errors='replace')}"
        digest = hmac.new(secret.encode("utf-8"), base.encode("utf-8"), hashlib.sha256).hexdigest()
        return bool(secret and signature and hmac.compare_digest(signature, f"v0={digest}"))
    if platform == "whatsapp":
        app_secret = _as_str(getattr(settings, "WHATSAPP_APP_SECRET", ""))
        signature = _as_str(request.headers.get("X-Hub-Signature-256"))
        if app_secret and signature:
            digest = hmac.new(app_secret.encode("utf-8"), request.body, hashlib.sha256).hexdigest()
            return hmac.compare_digest(signature, f"sha256={digest}")
        token = _as_str(getattr(settings, "WHATSAPP_VERIFY_TOKEN", ""))
        provided = _as_str(request.headers.get("X-Forgegraph-Webhook-Secret"))
        return not token or hmac.compare_digest(provided, token)
    if platform == "sms":
        auth_token = _as_str(getattr(settings, "TWILIO_AUTH_TOKEN", ""))
        signature = _as_str(request.headers.get("X-Twilio-Signature"))
        if not auth_token or not signature:
            return not auth_token
        signed_url = request.build_absolute_uri()
        form_items = payload.items() if isinstance(payload, dict) else []
        base = signed_url + "".join(f"{key}{value}" for key, value in sorted(form_items))
        digest = hmac.new(auth_token.encode("utf-8"), base.encode("utf-8"), hashlib.sha1).digest()
        expected = base64.b64encode(digest).decode("ascii")
        return hmac.compare_digest(signature, expected)
    if platform == "msgraph_webhook":
        expected = _as_str(getattr(settings, "MSGRAPH_CLIENT_STATE", ""))
        if not expected:
            return True
        notifications = payload.get("value") if isinstance(payload.get("value"), list) else []
        return any(hmac.compare_digest(_as_str(item.get("clientState")), expected) for item in notifications if isinstance(item, dict))
    expected_secret = _as_str(getattr(settings, "GENERIC_WEBHOOK_SECRET", ""))
    if not expected_secret:
        return True
    provided_secret = _as_str(request.headers.get("X-Forgegraph-Webhook-Secret"))
    return bool(provided_secret and hmac.compare_digest(provided_secret, expected_secret))


class GatewayWebhookView(APIView):
    """Receive gateway platform payloads and dispatch graph runs."""

    permission_classes = [AllowAny]

    def get(self, request: Request, platform: str, graph_version_id: UUID) -> Response:
        selected_platform = normalize_platform(platform)
        if selected_platform == "whatsapp":
            expected = _as_str(getattr(settings, "WHATSAPP_VERIFY_TOKEN", ""))
            mode = _as_str(request.query_params.get("hub.mode"))
            token = _as_str(request.query_params.get("hub.verify_token"))
            challenge = _as_str(request.query_params.get("hub.challenge"))
            if mode == "subscribe" and expected and hmac.compare_digest(token, expected):
                return Response(challenge, status=status.HTTP_200_OK, content_type="text/plain")
            return error_response(
                code="FORBIDDEN",
                message="Webhook verification failed.",
                status=status.HTTP_403_FORBIDDEN,
            )
        if selected_platform == "msgraph_webhook":
            validation_token = _as_str(request.query_params.get("validationToken"))
            if validation_token:
                return Response(
                    validation_token,
                    status=status.HTTP_200_OK,
                    content_type="text/plain",
                )
        return success_response(
            {"platform": selected_platform, "graph_version_id": str(graph_version_id)},
            status=status.HTTP_200_OK,
        )

    def post(self, request: Request, platform: str, graph_version_id: UUID) -> Response:
        selected_platform = normalize_platform(platform)
        payload = _payload_from_request(request)
        if selected_platform == "slack" and payload.get("type") == "url_verification":
            return Response({"challenge": payload.get("challenge")}, status=status.HTTP_200_OK)

        if not _verify_gateway_request(selected_platform, request, payload):
            return error_response(
                code="FORBIDDEN",
                message="Gateway webhook verification failed.",
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            graph_version = GraphVersion.objects.select_related("graph__owner", "graph__organization").get(
                id=graph_version_id
            )
        except GraphVersion.DoesNotExist:
            return error_response(
                code="NOT_FOUND",
                message=f"GraphVersion with id '{graph_version_id}' was not found.",
                status=status.HTTP_404_NOT_FOUND,
            )

        owner = cast(User, graph_version.graph.owner)
        organization = graph_version.graph.organization
        if organization is None:
            return error_response(
                code="CONFIG_ERROR",
                message="Gateway webhook graph is missing an organization.",
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        input_json = _normalize_gateway_input(selected_platform, request)
        gateway = _as_dict(input_json.get("gateway"))
        connection = resolve_gateway_connection_for_event(
            organization=organization,
            graph_version=graph_version,
            platform=selected_platform,
            provider=_as_str(gateway.get("provider")),
        )
        external_event_id = _external_event_id(selected_platform, input_json, request.body)
        conversation_id = _as_str(gateway.get("conversation_id") or external_event_id)
        idempotency_key = f"{selected_platform}:{external_event_id}"[:255]

        with transaction.atomic():
            receipt, created = GatewayInboundReceipt.objects.select_for_update().get_or_create(
                organization=organization,
                platform=selected_platform,
                idempotency_key=idempotency_key,
                defaults={
                    "connection": connection,
                    "provider": _as_str(gateway.get("provider"))[:64],
                    "external_event_id": external_event_id,
                    "external_conversation_id": conversation_id[:255],
                    "status": "received",
                    "event_json": input_json,
                },
            )
            if receipt.connection_id is None and connection is not None:
                receipt.connection = connection
            if not created and receipt.status in {"accepted", "ignored"}:
                return success_response(
                    {
                        "status": "duplicate",
                        "receipt_id": str(receipt.id),
                        "run_id": str(receipt.run_id or ""),
                    },
                    status=status.HTTP_202_ACCEPTED,
                )
            receipt.status = "processing"
            receipt.event_json = input_json
            receipt.save(update_fields=["connection", "status", "event_json", "updated_at"])

        thread_id = _thread_id_for_gateway_source(
            graph_version_id=graph_version.id,
            platform=selected_platform,
            conversation_id=conversation_id,
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
            GatewayInboundReceipt.objects.filter(id=receipt.id).update(
                status="failed",
                error_json={"status_code": context.status_code},
                processed_at=timezone.now(),
            )
            return context

        GatewayInboundReceipt.objects.filter(id=receipt.id).update(
            status="accepted",
            run=context.run,
            processed_at=timezone.now(),
        )
        receipt.status = "accepted"
        receipt.run = context.run
        receipt.processed_at = timezone.now()
        materialize_gateway_inbound(
            receipt=receipt,
            graph_version=graph_version,
            owner=owner,
            run=context.run,
            input_json=input_json,
            thread_id=thread_id,
        )
        return finalize_integration_run(
            context=context,
            graph_version=graph_version,
            owner=owner,
            session_id=session_id,
            input_json=input_json,
            channel=selected_platform,
            span_name=f"integrations.gateway.{selected_platform}.start",
            log_label=f"gateway.{selected_platform}",
            logger=logger,
            run_payload=_run_payload,
            record_audit=lambda run, tenant_id: record_audit_log(
                actor=owner,
                tenant_id=tenant_id,
                action="run.started.gateway_webhook",
                resource_type="run",
                resource_id=str(run.id),
                metadata={
                    "channel": selected_platform,
                    "graph_version_id": str(graph_version.id),
                    "gateway_receipt_id": str(receipt.id),
                },
            ),
        )
