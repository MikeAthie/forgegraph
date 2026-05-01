from __future__ import annotations

import hmac
from typing import Any

from django.conf import settings
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from application.services.runtime_web_tools import (
    RuntimeToolError,
    fetch_public_web_content,
    search_public_web,
)


def _is_authorized(request: Request) -> bool:
    expected = str(getattr(settings, "RUNTIME_TOOL_SECRET", "") or "").strip()
    authorization = str(request.headers.get("Authorization") or "").strip()
    scheme, _, credential = authorization.partition(" ")
    provided = credential.strip() if scheme.lower() == "bearer" else ""
    return bool(expected) and hmac.compare_digest(expected, provided)


def _extract_payload(request: Request) -> tuple[dict[str, Any], dict[str, Any]]:
    raw: dict[str, Any]
    if isinstance(request.data, dict):
        raw = request.data
    else:
        raw = {}
    input_payload = raw.get("input")
    config_payload = raw.get("config")
    return (
        input_payload if isinstance(input_payload, dict) else raw,
        config_payload if isinstance(config_payload, dict) else {},
    )


class RuntimeWebFetchView(APIView):
    authentication_classes: list[type] = []
    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        if not _is_authorized(request):
            return Response({"detail": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

        input_payload, config_payload = _extract_payload(request)
        try:
            result = fetch_public_web_content(
                url=str(input_payload.get("url") or ""),
                timeout_seconds=float(config_payload.get("timeout_seconds") or 10),
                max_chars=int(config_payload.get("max_chars") or 12000),
            )
        except RuntimeToolError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        return Response(result)


class RuntimeWebSearchView(APIView):
    authentication_classes: list[type] = []
    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        if not _is_authorized(request):
            return Response({"detail": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

        input_payload, config_payload = _extract_payload(request)
        try:
            result = search_public_web(
                query=str(input_payload.get("query") or ""),
                allowed_domains=_as_str_list(input_payload.get("allowed_domains")),
                blocked_domains=_as_str_list(input_payload.get("blocked_domains")),
                max_results=int(config_payload.get("max_results") or 5),
                timeout_seconds=float(config_payload.get("timeout_seconds") or 10),
            )
        except RuntimeToolError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        return Response(result)


def _as_str_list(value: Any) -> list[str] | None:
    if not isinstance(value, list):
        return None
    return [str(item) for item in value if str(item).strip()]
