from __future__ import annotations

from collections.abc import Callable

from django.conf import settings
from django.http import HttpRequest, JsonResponse

from application.services.metrics import record_api_request, record_service_metric_sample


class ApiRequestSizeLimitMiddleware:
    """Reject oversized API request bodies before DRF parses them."""

    _BODY_METHODS = {"POST", "PUT", "PATCH"}

    def __init__(self, get_response: Callable[[HttpRequest], object]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> object:
        method = request.method or ""
        if request.path_info.startswith("/api/") and method.upper() in self._BODY_METHODS:
            content_length = _content_length(request)
            limit = _limit_for_path(request.path_info)
            if content_length is not None and content_length > limit:
                record_api_request(
                    status_code=413,
                    duration_ms=0,
                    path=request.path_info,
                    method=method,
                )
                record_service_metric_sample(
                    metric_name="api_request_oversized",
                    source="api_request_size_middleware",
                    value=content_length,
                    unit="bytes",
                    dimensions={
                        "path": request.path_info,
                        "method": method.upper(),
                        "limit": limit,
                    },
                )
                return JsonResponse(
                    {
                        "success": False,
                        "error": {
                            "code": "REQUEST_TOO_LARGE",
                            "message": "Request body exceeds the configured API size limit.",
                            "max_bytes": limit,
                        },
                    },
                    status=413,
                )
        return self.get_response(request)


def _content_length(request: HttpRequest) -> int | None:
    raw = request.META.get("CONTENT_LENGTH")
    if not isinstance(raw, str) or raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _limit_for_path(path: str) -> int:
    normalized = path.rstrip("/")
    run_input_paths = (
        "/api/runs/start",
        "/api/runs/invoke",
        "/api/executions/start",
        "/api/executions/invoke",
        "/api/v1/runs/start",
        "/api/v1/runs/invoke",
        "/api/v1/executions/start",
        "/api/v1/executions/invoke",
    )
    if normalized in run_input_paths:
        return _settings_int("RUN_INPUT_MAX_BYTES", 256 * 1024)
    return _settings_int("API_REQUEST_MAX_BYTES", 1024 * 1024)


def _settings_int(name: str, default: int) -> int:
    value = getattr(settings, name, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
