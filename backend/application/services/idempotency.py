from __future__ import annotations

import copy
import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any, Literal, TypeVar
from uuid import UUID

from django.core.serializers.json import DjangoJSONEncoder
from rest_framework.response import Response

from application.services.metrics import record_service_metric_sample

logger = logging.getLogger(__name__)

IdempotencyStatus = Literal["applied", "already_applied", "rejected", "retry_required"]
T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class IdempotentResult:
    status: IdempotencyStatus
    idempotency_key: str
    resource_type: str = ""
    resource_id: str = ""
    result: Any = None
    duplicate: bool = False


def normalize_idempotency_key(value: object, *, max_length: int = 255) -> str:
    return str(value or "").strip()[:max_length]


def hash_request_payload(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        cls=DjangoJSONEncoder,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def idempotency_metadata(
    *,
    status: IdempotencyStatus,
    idempotency_key: str,
    resource_type: str = "",
    resource_id: str = "",
) -> dict[str, str]:
    return {
        "status": status,
        "idempotency_key": idempotency_key,
        "resource_type": resource_type,
        "resource_id": str(resource_id or ""),
    }


def annotate_response(
    response: Response,
    *,
    status: IdempotencyStatus,
    idempotency_key: str,
    resource_type: str = "",
    resource_id: str = "",
) -> Response:
    if not idempotency_key:
        return response
    metadata = idempotency_metadata(
        status=status,
        idempotency_key=idempotency_key,
        resource_type=resource_type,
        resource_id=resource_id,
    )
    body = response.data
    if isinstance(body, dict):
        meta = body.setdefault("meta", {})
        if isinstance(meta, dict):
            meta["idempotency"] = metadata
            meta["idempotency_key"] = idempotency_key
            if status == "already_applied":
                meta["already_applied"] = True
        data = body.get("data")
        if isinstance(data, dict):
            data["idempotency"] = metadata
            if status == "already_applied":
                data.setdefault("already_applied", True)
                data.setdefault("duplicate", True)
    return response


def annotated_response_from_body(
    body: Any,
    *,
    response_status: int,
    status: IdempotencyStatus,
    idempotency_key: str,
    resource_type: str = "",
    resource_id: str = "",
) -> Response:
    response = Response(copy.deepcopy(body), status=response_status)
    return annotate_response(
        response,
        status=status,
        idempotency_key=idempotency_key,
        resource_type=resource_type,
        resource_id=resource_id,
    )


def response_body(response: Response) -> Any:
    return copy.deepcopy(response.data)


def record_idempotency_observation(
    *,
    boundary: str,
    status: IdempotencyStatus,
    idempotency_key: str = "",
    resource_type: str = "",
    organization_id: object | None = None,
    run_id: object | None = None,
) -> None:
    metric_organization_id = (
        organization_id
        if isinstance(organization_id, (str, UUID))
        else str(organization_id)
        if organization_id is not None
        else None
    )
    metric_run_id = (
        run_id if isinstance(run_id, (str, UUID)) else str(run_id) if run_id is not None else None
    )
    log_payload = {
        "boundary": boundary,
        "status": status,
        "idempotency_key": idempotency_key,
        "resource_type": resource_type,
        "organization_id": str(organization_id or ""),
        "run_id": str(run_id or ""),
    }
    logger.info("idempotency_operation", extra=log_payload)
    record_service_metric_sample(
        metric_name="idempotency_operations_total",
        source="idempotency",
        value=1,
        unit="count",
        organization_id=metric_organization_id,
        run_id=metric_run_id,
        dimensions={
            "boundary": boundary,
            "status": status,
            "resource_type": resource_type,
        },
    )
