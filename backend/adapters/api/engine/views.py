from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import SupportsInt, cast
from uuid import UUID

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.responses import error_response, success_response
from application.services.credential_state import is_credential_revoked, is_oauth_provider
from application.services.oauth import (
    exchange_refresh_token_for_access_token,
    get_oauth_provider_config,
)
from application.services.redaction import redact_payload
from application.services.tenancy import get_tenant_id_for_user
from infrastructure.crypto.encryption import decrypt_api_key, encrypt_api_key
from infrastructure.orm.models import APIKey, NodeRun, NodeRunCache, Run, RunCheckpoint
from infrastructure.security import s2s

logger = logging.getLogger(__name__)
_REFRESH_SKEW = timedelta(minutes=5)


def _parse_expires_at(token_payload: dict[str, object]) -> datetime | None:
    raw_expires_in = token_payload.get("expires_in")
    if raw_expires_in is None:
        return None
    try:
        expires_in = int(cast(str | bytes | SupportsInt, raw_expires_in))
        if expires_in > 0:
            return timezone.now() + timedelta(seconds=expires_in)
    except (TypeError, ValueError):
        return None
    return None


def _refresh_oauth_access_token_if_needed(key: APIKey, tenant_id: str) -> APIKey:
    if not is_oauth_provider(key.provider):
        return key
    if key.encrypted_refresh_token is None:
        return key
    if key.token_expires_at is None:
        return key
    if key.token_expires_at > timezone.now() + _REFRESH_SKEW:
        return key

    with transaction.atomic():
        locked = APIKey.objects.select_for_update().get(id=key.id)
        if locked.encrypted_refresh_token is None:
            return locked
        if locked.token_expires_at is None:
            return locked
        if locked.token_expires_at > timezone.now() + _REFRESH_SKEW:
            return locked

        refresh_token = decrypt_api_key(bytes(locked.encrypted_refresh_token)).strip()
        if not refresh_token:
            return locked

        config, missing_fields = get_oauth_provider_config(tenant_id, locked.provider)
        if config is None:
            raise ValueError(
                f"OAuth provider '{locked.provider}' is not configured ({', '.join(missing_fields)})."
            )

        refreshed = exchange_refresh_token_for_access_token(
            config,
            refresh_token=refresh_token,
        )
        new_access_token = str(refreshed.get("access_token") or "").strip()
        if not new_access_token:
            raise ValueError("OAuth refresh did not return an access_token.")

        update_fields = ["encrypted_key", "token_expires_at", "token_metadata"]
        locked.encrypted_key = encrypt_api_key(new_access_token)
        locked.token_expires_at = _parse_expires_at(refreshed)

        rotated_refresh_token = str(refreshed.get("refresh_token") or "").strip()
        if rotated_refresh_token:
            locked.encrypted_refresh_token = encrypt_api_key(rotated_refresh_token)
            update_fields.append("encrypted_refresh_token")

        metadata = dict(locked.token_metadata) if isinstance(locked.token_metadata, dict) else {}
        metadata["provider"] = locked.provider
        token_type = str(refreshed.get("token_type") or "").strip()
        if token_type:
            metadata["token_type"] = token_type
        scope = refreshed.get("scope")
        if isinstance(scope, str) and scope.strip():
            metadata["scope"] = scope.strip()
        locked.token_metadata = metadata
        locked.save(update_fields=sorted(set(update_fields)))
        return locked


def _verify_engine_request(request: Request) -> Response | None:
    timestamp_header = request.headers.get("X-Forgegraph-Timestamp", "")
    signature_header = request.headers.get("X-Forgegraph-Signature", "")
    ok, reason = s2s.verify_request(
        timestamp_ms=timestamp_header,
        signature=signature_header,
        body=request.body or b"",
    )
    if ok:
        return None
    return Response({"detail": "Unauthorized", "reason": reason}, status=401)


def _get_run_or_404(run_id: UUID) -> Run | Response:
    try:
        return Run.objects.select_related("graph_version").get(id=run_id)
    except Run.DoesNotExist:
        return error_response(
            code="NOT_FOUND",
            message="Run not found",
            status=404,
        )


def _parse_optional_datetime(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        parsed = parse_datetime(value)
        if parsed is not None:
            return parsed
    raise ValueError("invalid datetime")


def _serialize_run(run: Run) -> dict[str, object]:
    return {
        "id": str(run.id),
        "graph_version_id": str(run.graph_version_id),
        "status": run.status,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "ended_at": run.ended_at.isoformat() if run.ended_at else None,
        "input_json": redact_payload(run.input_json),
        "output_json": redact_payload(run.output_json),
        "error_message": redact_payload(run.error_message),
        "trace_id": run.trace_id,
    }


def _serialize_node_run(node_run: NodeRun) -> dict[str, object]:
    return {
        "id": str(node_run.id),
        "run_id": str(node_run.run_id),
        "node_id": node_run.node_id,
        "node_type": node_run.node_type,
        "status": node_run.status,
        "attempt": node_run.attempt,
        "started_at": node_run.started_at.isoformat() if node_run.started_at else None,
        "ended_at": node_run.ended_at.isoformat() if node_run.ended_at else None,
        "duration_ms": node_run.duration_ms,
        "input_json": redact_payload(node_run.input_json),
        "output_json": redact_payload(node_run.output_json),
        "error_json": redact_payload(node_run.error_json),
        "trace_id": node_run.trace_id,
        "span_id": node_run.span_id,
    }


def _serialize_checkpoint(checkpoint: RunCheckpoint) -> dict[str, object]:
    graph_json = checkpoint.graph_json
    if not isinstance(graph_json, str):
        graph_json = json.dumps(graph_json)
    return {
        "node_id": checkpoint.node_id,
        "step_index": checkpoint.step_index,
        "state_snapshot": redact_payload(checkpoint.state_json),
        "completed_nodes": list(checkpoint.completed_nodes or []),
        "skipped_nodes": list(checkpoint.skipped_nodes or []),
        "graph_json": graph_json,
    }


def _validate_status(value: object, *, allowed: set[str], field: str) -> str:
    status_value = str(value or "").strip()
    if status_value not in allowed:
        raise ValueError(f"{field} must be one of {sorted(allowed)}")
    return status_value


def _decode_graph_json(raw_value: object) -> object:
    if isinstance(raw_value, (dict, list)):
        return raw_value
    if isinstance(raw_value, str):
        text = raw_value.strip()
        if not text:
            return {}
        return json.loads(text)
    raise ValueError("graph_json must be a JSON object, array, or JSON-encoded string")


class EngineCredentialDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request: Request, credential_id: UUID) -> Response:
        auth_error = _verify_engine_request(request)
        if auth_error is not None:
            return auth_error

        tenant_id = request.query_params.get("tenant_id", "")
        if not tenant_id:
            return error_response(
                code="VALIDATION_ERROR",
                message="tenant_id is required",
                status=400,
            )

        try:
            key = APIKey.objects.select_related("user", "organization").get(id=credential_id)
        except APIKey.DoesNotExist:
            return error_response(
                code="NOT_FOUND",
                message="Credential not found",
                status=404,
            )

        owner_tenant_id = get_tenant_id_for_user(key.user)
        if key.organization_id and str(key.organization_id) != tenant_id:
            return error_response(
                code="FORBIDDEN",
                message="Credential does not belong to tenant",
                status=403,
            )
        if not key.organization_id and owner_tenant_id != tenant_id:
            return error_response(
                code="FORBIDDEN",
                message="Credential does not belong to tenant",
                status=403,
            )
        if is_credential_revoked(key.token_metadata):
            return error_response(
                code="CREDENTIAL_REVOKED",
                message="Credential has been revoked. Rotate or reconnect it before use.",
                status=410,
            )

        try:
            key = _refresh_oauth_access_token_if_needed(key, tenant_id)
            api_key = decrypt_api_key(bytes(key.encrypted_key))
        except ValueError as exc:
            logger.warning(
                "oauth_credential_refresh_failed",
                extra={
                    "credential_id": str(key.id),
                    "provider": key.provider,
                    "tenant_id": tenant_id,
                    "error": str(exc),
                },
            )
            return error_response(
                code="CREDENTIAL_REFRESH_FAILED",
                message=(
                    "OAuth access token refresh failed. Reconnect this credential in the Credentials page."
                ),
                status=401,
            )
        except Exception:
            return error_response(
                code="DECRYPTION_ERROR",
                message="Failed to decrypt credential",
                status=500,
            )

        return success_response(
            {
                "credential_id": str(key.id),
                "provider": key.provider,
                "api_key": api_key,
            }
        )


class EngineRunDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request: Request, run_id: UUID) -> Response:
        auth_error = _verify_engine_request(request)
        if auth_error is not None:
            return auth_error

        run = _get_run_or_404(run_id)
        if isinstance(run, Response):
            return run
        return success_response(_serialize_run(run))

    def patch(self, request: Request, run_id: UUID) -> Response:
        auth_error = _verify_engine_request(request)
        if auth_error is not None:
            return auth_error

        run = _get_run_or_404(run_id)
        if isinstance(run, Response):
            return run

        payload = request.data if isinstance(request.data, dict) else {}
        update_fields: list[str] = []

        try:
            if "status" in payload:
                run.status = _validate_status(
                    payload.get("status"),
                    allowed={"pending", "running", "paused", "succeeded", "failed", "canceled"},
                    field="status",
                )
                update_fields.append("status")
            if "started_at" in payload:
                run.started_at = _parse_optional_datetime(payload.get("started_at"))
                update_fields.append("started_at")
            if "ended_at" in payload:
                run.ended_at = _parse_optional_datetime(payload.get("ended_at"))
                update_fields.append("ended_at")
            if "output_json" in payload:
                run.output_json = redact_payload(payload.get("output_json"))
                update_fields.append("output_json")
            if "error_message" in payload:
                run.error_message = str(redact_payload(payload.get("error_message") or ""))
                update_fields.append("error_message")
            if "trace_id" in payload:
                run.trace_id = str(payload.get("trace_id") or "")
                update_fields.append("trace_id")
        except ValueError as exc:
            return error_response(
                code="VALIDATION_ERROR",
                message=str(exc),
                status=400,
            )

        if update_fields:
            run.save(update_fields=sorted(set(update_fields)))

        return success_response(_serialize_run(run))


class EngineRunPauseStateView(APIView):
    permission_classes = [AllowAny]

    def get(self, request: Request, run_id: UUID) -> Response:
        auth_error = _verify_engine_request(request)
        if auth_error is not None:
            return auth_error

        run = _get_run_or_404(run_id)
        if isinstance(run, Response):
            return run

        if not run.paused_node_id or not isinstance(run.pause_state_json, dict):
            return error_response(
                code="INVALID_STATE",
                message="Run is not paused.",
                status=409,
            )

        pause_state = dict(run.pause_state_json)
        return success_response(
            {
                "paused_node_id": run.paused_node_id,
                "state_snapshot": redact_payload(pause_state.get("state_snapshot") or {}),
                "completed_nodes": list(pause_state.get("completed_nodes") or []),
                "skipped_nodes": list(pause_state.get("skipped_nodes") or []),
                "graph_json": str(pause_state.get("graph_json") or ""),
                "tenant_id": str(pause_state.get("tenant_id") or ""),
            }
        )

    def put(self, request: Request, run_id: UUID) -> Response:
        auth_error = _verify_engine_request(request)
        if auth_error is not None:
            return auth_error

        run = _get_run_or_404(run_id)
        if isinstance(run, Response):
            return run

        payload = request.data if isinstance(request.data, dict) else {}
        paused_node_id = str(payload.get("paused_node_id") or "").strip()
        if not paused_node_id:
            return error_response(
                code="VALIDATION_ERROR",
                message="paused_node_id is required",
                status=400,
            )

        pause_state = {
            "state_snapshot": redact_payload(payload.get("state_snapshot") or {}),
            "completed_nodes": list(payload.get("completed_nodes") or []),
            "skipped_nodes": list(payload.get("skipped_nodes") or []),
            "graph_json": str(payload.get("graph_json") or ""),
            "tenant_id": str(payload.get("tenant_id") or ""),
        }
        run.paused_node_id = paused_node_id
        run.pause_state_json = pause_state
        run.save(update_fields=["paused_node_id", "pause_state_json"])

        return success_response(
            {
                "paused_node_id": run.paused_node_id,
                "state_snapshot": pause_state["state_snapshot"],
                "completed_nodes": pause_state["completed_nodes"],
                "skipped_nodes": pause_state["skipped_nodes"],
                "graph_json": pause_state["graph_json"],
                "tenant_id": pause_state["tenant_id"],
            }
        )

    def delete(self, request: Request, run_id: UUID) -> Response:
        auth_error = _verify_engine_request(request)
        if auth_error is not None:
            return auth_error

        run = _get_run_or_404(run_id)
        if isinstance(run, Response):
            return run

        run.paused_node_id = None
        run.pause_state_json = None
        run.save(update_fields=["paused_node_id", "pause_state_json"])
        return success_response({"cleared": True})


class EngineRunCheckpointView(APIView):
    permission_classes = [AllowAny]

    def get(self, request: Request, run_id: UUID) -> Response:
        auth_error = _verify_engine_request(request)
        if auth_error is not None:
            return auth_error

        run = _get_run_or_404(run_id)
        if isinstance(run, Response):
            return run

        try:
            checkpoint = run.checkpoint
        except RunCheckpoint.DoesNotExist:
            return error_response(
                code="NO_CHECKPOINT",
                message="Checkpoint not found",
                status=404,
            )

        return success_response(_serialize_checkpoint(checkpoint))

    def put(self, request: Request, run_id: UUID) -> Response:
        auth_error = _verify_engine_request(request)
        if auth_error is not None:
            return auth_error

        run = _get_run_or_404(run_id)
        if isinstance(run, Response):
            return run

        payload = request.data if isinstance(request.data, dict) else {}
        node_id = str(payload.get("node_id") or "").strip()
        if not node_id:
            return error_response(
                code="VALIDATION_ERROR",
                message="node_id is required",
                status=400,
            )

        try:
            step_index = int(payload.get("step_index") or 0)
            checkpoint_graph_json = _decode_graph_json(payload.get("graph_json"))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            return error_response(
                code="VALIDATION_ERROR",
                message=str(exc),
                status=400,
            )

        with transaction.atomic():
            checkpoint, created = RunCheckpoint.objects.select_for_update().get_or_create(
                run=run,
                defaults={
                    "node_id": node_id,
                    "step_index": step_index,
                    "state_json": redact_payload(payload.get("state_snapshot") or {}),
                    "completed_nodes": list(payload.get("completed_nodes") or []),
                    "skipped_nodes": list(payload.get("skipped_nodes") or []),
                    "graph_json": checkpoint_graph_json,
                },
            )
            if not created and checkpoint.step_index <= step_index:
                checkpoint.node_id = node_id
                checkpoint.step_index = step_index
                checkpoint.state_json = redact_payload(payload.get("state_snapshot") or {})
                checkpoint.completed_nodes = list(payload.get("completed_nodes") or [])
                checkpoint.skipped_nodes = list(payload.get("skipped_nodes") or [])
                checkpoint.graph_json = checkpoint_graph_json
                checkpoint.save(
                    update_fields=[
                        "node_id",
                        "step_index",
                        "state_json",
                        "completed_nodes",
                        "skipped_nodes",
                        "graph_json",
                        "updated_at",
                    ]
                )

        return success_response(_serialize_checkpoint(checkpoint))

    def delete(self, request: Request, run_id: UUID) -> Response:
        auth_error = _verify_engine_request(request)
        if auth_error is not None:
            return auth_error

        run = _get_run_or_404(run_id)
        if isinstance(run, Response):
            return run

        deleted, _ = RunCheckpoint.objects.filter(run=run).delete()
        if deleted == 0:
            return error_response(
                code="NO_CHECKPOINT",
                message="Checkpoint not found",
                status=404,
            )
        return success_response({"cleared": True})


class EngineRunNodeRunListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request: Request, run_id: UUID) -> Response:
        auth_error = _verify_engine_request(request)
        if auth_error is not None:
            return auth_error

        run = _get_run_or_404(run_id)
        if isinstance(run, Response):
            return run

        node_runs = run.node_runs.order_by("started_at", "attempt", "id")
        return success_response([_serialize_node_run(node_run) for node_run in node_runs])


class EngineRunNodeRunDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request: Request, run_id: UUID, node_id: str) -> Response:
        auth_error = _verify_engine_request(request)
        if auth_error is not None:
            return auth_error

        run = _get_run_or_404(run_id)
        if isinstance(run, Response):
            return run

        attempt_param = request.query_params.get("attempt")
        node_runs = NodeRun.objects.filter(run=run, node_id=node_id)
        if attempt_param:
            try:
                node_runs = node_runs.filter(attempt=int(attempt_param))
            except (TypeError, ValueError):
                return error_response(
                    code="VALIDATION_ERROR",
                    message="attempt must be an integer",
                    status=400,
                )
        node_run = node_runs.order_by("-attempt", "-started_at", "-id").first()
        if node_run is None:
            return error_response(
                code="NOT_FOUND",
                message="Node run not found",
                status=404,
            )
        return success_response(_serialize_node_run(node_run))

    def put(self, request: Request, run_id: UUID, node_id: str) -> Response:
        auth_error = _verify_engine_request(request)
        if auth_error is not None:
            return auth_error

        run = _get_run_or_404(run_id)
        if isinstance(run, Response):
            return run

        payload = request.data if isinstance(request.data, dict) else {}
        try:
            attempt = int(payload.get("attempt") or 1)
            node_type = str(payload.get("node_type") or "").strip()
            status_value = _validate_status(
                payload.get("status"),
                allowed={"pending", "running", "waiting", "succeeded", "failed", "skipped"},
                field="status",
            )
            started_at = _parse_optional_datetime(payload.get("started_at"))
            ended_at = _parse_optional_datetime(payload.get("ended_at"))
        except ValueError as exc:
            return error_response(
                code="VALIDATION_ERROR",
                message=str(exc),
                status=400,
            )

        if not node_type:
            return error_response(
                code="VALIDATION_ERROR",
                message="node_type is required",
                status=400,
            )

        node_run_id = None
        raw_node_run_id = str(payload.get("id") or "").strip()
        if raw_node_run_id:
            try:
                node_run_id = UUID(raw_node_run_id)
            except ValueError:
                node_run_id = None

        with transaction.atomic():
            defaults: dict[str, object] = {
                "node_type": node_type,
                "status": status_value,
            }
            if node_run_id is not None:
                defaults["id"] = node_run_id
            node_run, _ = NodeRun.objects.get_or_create(
                run=run,
                node_id=node_id,
                attempt=attempt,
                defaults=defaults,
            )

            update_fields: list[str] = []
            if node_run.node_type != node_type:
                node_run.node_type = node_type
                update_fields.append("node_type")
            if node_run.status != status_value:
                node_run.status = status_value
                update_fields.append("status")
            if started_at is not None or payload.get("started_at") in (None, ""):
                node_run.started_at = started_at
                update_fields.append("started_at")
            if ended_at is not None or payload.get("ended_at") in (None, ""):
                node_run.ended_at = ended_at
                update_fields.append("ended_at")
            if "input_json" in payload:
                node_run.input_json = redact_payload(payload.get("input_json") or {})
                update_fields.append("input_json")
            if "output_json" in payload:
                node_run.output_json = redact_payload(payload.get("output_json"))
                update_fields.append("output_json")
            if "error_json" in payload:
                node_run.error_json = redact_payload(payload.get("error_json"))
                update_fields.append("error_json")
            if "trace_id" in payload:
                node_run.trace_id = str(payload.get("trace_id") or "")
                update_fields.append("trace_id")
            if "span_id" in payload:
                node_run.span_id = str(payload.get("span_id") or "")
                update_fields.append("span_id")

            if update_fields:
                node_run.save(update_fields=sorted(set(update_fields)))

        return success_response(_serialize_node_run(node_run))


class EngineNodeCacheDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request: Request, cache_key: str) -> Response:
        auth_error = _verify_engine_request(request)
        if auth_error is not None:
            return auth_error

        cache_entry = NodeRunCache.objects.filter(cache_key=cache_key).first()
        if cache_entry is None or cache_entry.expires_at <= timezone.now():
            NodeRunCache.objects.filter(cache_key=cache_key).delete()
            return error_response(
                code="NOT_FOUND",
                message="Cache entry not found",
                status=404,
            )

        return success_response(
            {
                "cache_key": cache_entry.cache_key,
                "output": redact_payload(cache_entry.output_json),
                "expires_at": cache_entry.expires_at.isoformat(),
            }
        )

    def put(self, request: Request, cache_key: str) -> Response:
        auth_error = _verify_engine_request(request)
        if auth_error is not None:
            return auth_error

        payload = request.data if isinstance(request.data, dict) else {}
        try:
            ttl_seconds = int(payload.get("ttl_seconds") or 0)
        except (TypeError, ValueError):
            return error_response(
                code="VALIDATION_ERROR",
                message="ttl_seconds must be an integer",
                status=400,
            )

        if ttl_seconds <= 0:
            return success_response({"cache_key": cache_key, "stored": False})

        expires_at = timezone.now() + timedelta(seconds=ttl_seconds)
        cache_entry, _ = NodeRunCache.objects.update_or_create(
            cache_key=cache_key,
            defaults={
                "output_json": redact_payload(payload.get("output")),
                "expires_at": expires_at,
            },
        )
        return success_response(
            {
                "cache_key": cache_entry.cache_key,
                "output": redact_payload(cache_entry.output_json),
                "expires_at": cache_entry.expires_at.isoformat(),
                "stored": True,
            }
        )
