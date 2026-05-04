from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Any

from rest_framework.response import Response

from infrastructure.orm.models import Organization, ProcessedCommand

IDEMPOTENCY_HEADER = "Idempotency-Key"


class IdempotencyConflict(ValueError):
    def __init__(self, *, action: str, idempotency_key: str) -> None:
        self.action = action
        self.idempotency_key = idempotency_key
        super().__init__("Idempotency-Key was already used with a different request body.")


@dataclass(frozen=True)
class IdempotencyContext:
    organization: Organization
    action: str
    idempotency_key: str
    request_hash: str


def idempotency_key_from_request(request: Any) -> str:
    return str(getattr(request, "headers", {}).get(IDEMPOTENCY_HEADER) or "").strip()


def build_idempotency_context(
    *,
    request: Any,
    organization: Organization | None,
    action: str,
    request_payload: Any,
) -> IdempotencyContext | None:
    key = idempotency_key_from_request(request)
    if not key or organization is None:
        return None
    return IdempotencyContext(
        organization=organization,
        action=action,
        idempotency_key=key,
        request_hash=hash_request_payload(request_payload),
    )


def replay_processed_command(context: IdempotencyContext | None) -> Response | None:
    if context is None:
        return None
    record = ProcessedCommand.objects.filter(
        organization=context.organization,
        action=context.action,
        idempotency_key=context.idempotency_key,
    ).first()
    if record is None:
        return None
    if record.request_hash != context.request_hash:
        raise IdempotencyConflict(
            action=context.action,
            idempotency_key=context.idempotency_key,
        )
    body = copy.deepcopy(record.response_body)
    if isinstance(body, dict):
        meta = body.setdefault("meta", {})
        if isinstance(meta, dict):
            meta["already_applied"] = True
            meta["idempotency_key"] = context.idempotency_key
        data = body.get("data")
        if isinstance(data, dict):
            data.setdefault("already_applied", True)
    return Response(body, status=record.response_status)


def record_processed_command(
    *,
    context: IdempotencyContext | None,
    response: Response,
    resource_type: str = "",
    resource_id: str = "",
) -> Response:
    if context is None or response.status_code >= 400:
        return response
    response_body = copy.deepcopy(response.data)
    ProcessedCommand.objects.update_or_create(
        organization=context.organization,
        action=context.action,
        idempotency_key=context.idempotency_key,
        defaults={
            "request_hash": context.request_hash,
            "response_status": response.status_code,
            "response_body": response_body,
            "resource_type": resource_type,
            "resource_id": str(resource_id or ""),
        },
    )
    return response


def hash_request_payload(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()
