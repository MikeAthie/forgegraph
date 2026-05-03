"""
Request/response metrics middleware.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse

from application.services.metrics import record_api_request


class RequestMetricsMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        started_at = time.perf_counter()
        method = request.method or ""
        timeout_threshold_ms = int(getattr(settings, "BACKEND_WATCHDOG_REQUEST_TIMEOUT_MS", 5000))
        try:
            response = self.get_response(request)
        except Exception:
            duration_ms = int((time.perf_counter() - started_at) * 1000)
            record_api_request(
                status_code=500,
                duration_ms=duration_ms,
                timeout_like=duration_ms >= timeout_threshold_ms,
                timeout_threshold_ms=timeout_threshold_ms,
                path=request.path_info,
                method=method,
            )
            raise

        duration_ms = int((time.perf_counter() - started_at) * 1000)
        record_api_request(
            status_code=response.status_code,
            duration_ms=duration_ms,
            timeout_like=duration_ms >= timeout_threshold_ms,
            timeout_threshold_ms=timeout_threshold_ms,
            path=request.path_info,
            method=method,
        )
        return response
