"""Generic webhook integration adapters."""

from __future__ import annotations

import hmac
import logging
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from django.conf import settings
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.integrations.run_dispatch import (
    finalize_integration_run,
    prepare_integration_run_context,
)
from adapters.api.responses import error_response
from adapters.api.runs import views as run_views
from application.services.audit_log import record_audit_log
from infrastructure.orm.models import GraphVersion, Run, User

logger = logging.getLogger(__name__)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _extract_webhook_config(graph_json: dict[str, Any]) -> dict[str, Any]:
    metadata = _as_dict(graph_json.get("metadata"))
    integrations = _as_dict(metadata.get("integrations"))
    return _as_dict(integrations.get("webhook"))


def _thread_id_for_webhook_source(*, graph_version_id: UUID, raw_value: str) -> UUID | None:
    value = raw_value.strip()
    if not value:
        return None
    return uuid5(NAMESPACE_URL, f"webhook:{graph_version_id}:{value}")


def _normalize_webhook_input(request: Request) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if isinstance(request.data, dict):
        payload = {str(key): value for key, value in request.data.items()}

    query = {str(key): values for key, values in request.query_params.lists()}
    headers = {str(key).lower(): str(value) for key, value in request.headers.items() if key}

    return {
        "channel": "webhook",
        "message": _as_str(payload.get("message") or payload.get("text")),
        "webhook": {
            "method": request.method,
            "path": request.path,
            "query": query,
            "headers": headers,
            "payload": payload,
        },
        "payload": payload,
    }


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


class GenericWebhookView(APIView):
    """Receive generic webhook payloads and dispatch graph runs."""

    permission_classes = [AllowAny]

    def post(self, request: Request, graph_version_id: UUID) -> Response:
        payload_raw = request.data
        if payload_raw not in ({}, None) and not isinstance(payload_raw, dict):
            return error_response(
                code="VALIDATION_ERROR",
                message="Webhook payload must be a JSON object.",
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

        webhook_config = _extract_webhook_config(graph_version.graph_json)
        expected_secret = _as_str(
            webhook_config.get("secret") or getattr(settings, "GENERIC_WEBHOOK_SECRET", "")
        )
        if not expected_secret:
            return error_response(
                code="CONFIG_ERROR",
                message="Webhook secret is not configured for this graph.",
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        provided_secret = _as_str(request.headers.get("X-Forgegraph-Webhook-Secret"))
        if not provided_secret or not hmac.compare_digest(provided_secret, expected_secret):
            return error_response(
                code="FORBIDDEN",
                message="Webhook secret verification failed.",
                status=status.HTTP_403_FORBIDDEN,
            )

        owner = cast(User, graph_version.graph.owner)
        input_json = _normalize_webhook_input(request)
        thread_hint = _as_str(
            request.headers.get("X-Thread-Id")
            or _as_dict(input_json.get("payload")).get("thread_id")
            or _as_dict(input_json.get("payload")).get("session_id")
        )
        thread_id = _thread_id_for_webhook_source(
            graph_version_id=graph_version.id,
            raw_value=thread_hint,
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
            channel="webhook",
            span_name="integrations.webhook.start",
            log_label="webhook",
            logger=logger,
            run_payload=_run_payload,
            record_audit=lambda run, tenant_id: record_audit_log(
                actor=owner,
                tenant_id=tenant_id,
                action="run.started.generic_webhook",
                resource_type="run",
                resource_id=str(run.id),
                metadata={
                    "graph_id": str(graph_version.graph_id),
                    "channel": "webhook",
                    "path": request.path,
                },
            ),
        )
