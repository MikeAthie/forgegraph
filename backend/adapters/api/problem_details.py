from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from rest_framework.response import Response


def problem_response(
    *,
    type_uri: str,
    title: str,
    status: int,
    detail: str,
    instance: str | None = None,
    extensions: dict[str, Any] | None = None,
) -> Response:
    payload: dict[str, Any] = {
        "type": type_uri,
        "title": title,
        "status": status,
        "detail": detail,
        "timestamp": datetime.now(UTC).isoformat() + "Z",
    }
    if instance:
        payload["instance"] = instance
    if extensions:
        payload.update(extensions)
    response = Response(payload, status=status, content_type="application/problem+json")
    return response
