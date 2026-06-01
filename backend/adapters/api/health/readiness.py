"""
Backend readiness checks.
"""

from __future__ import annotations

import time
from typing import Any

from django.conf import settings
from django.db import connection
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.runs.views import get_engine_client
from application.services.communication_kafka import build_communication_kafka_readiness_payload
from application.services.runtime_transport_observability import (
    get_runtime_transport_observability_snapshot,
)
from config.runtime_validation import collect_runtime_validation_errors


def build_readiness_payload() -> tuple[dict[str, Any], int]:
    checks: dict[str, dict[str, Any]] = {}
    runtime_errors = collect_runtime_validation_errors(strict=True)
    checks["runtime"] = {
        "ready": not runtime_errors,
        "errors": runtime_errors,
    }

    db_start = time.perf_counter()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        checks["database"] = {
            "ready": True,
            "latency_ms": int((time.perf_counter() - db_start) * 1000),
        }
    except Exception as exc:  # noqa: BLE001
        checks["database"] = {
            "ready": False,
            "latency_ms": int((time.perf_counter() - db_start) * 1000),
            "error": str(exc),
        }

    cache_start = time.perf_counter()
    try:
        from django.core.cache import cache

        cache_key = "forgegraph:readiness"
        cache.set(cache_key, "ok", timeout=5)
        checks["cache"] = {
            "ready": cache.get(cache_key) == "ok",
            "latency_ms": int((time.perf_counter() - cache_start) * 1000),
        }
    except Exception as exc:  # noqa: BLE001
        checks["cache"] = {
            "ready": False,
            "latency_ms": int((time.perf_counter() - cache_start) * 1000),
            "error": str(exc),
        }

    if getattr(settings, "READINESS_REQUIRE_ENGINE", False):
        engine_start = time.perf_counter()
        try:
            with get_engine_client() as engine_client:
                engine_ready = bool(engine_client.ping())
            checks["engine"] = {
                "ready": engine_ready,
                "latency_ms": int((time.perf_counter() - engine_start) * 1000),
            }
        except Exception as exc:  # noqa: BLE001
            checks["engine"] = {
                "ready": False,
                "latency_ms": int((time.perf_counter() - engine_start) * 1000),
                "error": str(exc),
            }

    if getattr(settings, "READINESS_REQUIRE_RUNTIME_TRANSPORT", False):
        transport_start = time.perf_counter()
        try:
            transport = get_runtime_transport_observability_snapshot()
            backlog_threshold = int(getattr(settings, "SLO_QUEUE_MAX_DEPTH", 500) or 0)
            backlog_ready = backlog_threshold <= 0 or transport.backlog <= backlog_threshold
            checks["runtime_transport"] = {
                "ready": bool(
                    transport.error == "" and transport.dead_letter_count == 0 and backlog_ready
                ),
                "latency_ms": int((time.perf_counter() - transport_start) * 1000),
                "source": transport.source,
                "stream_length": transport.stream_length,
                "pending": transport.pending,
                "lag": transport.lag,
                "backlog": transport.backlog,
                "backlog_threshold": backlog_threshold,
                "dead_letter_count": transport.dead_letter_count,
                "consumer_idle_ms": transport.consumer_idle_ms,
                "oldest_pending_idle_ms": transport.oldest_pending_idle_ms,
                "error": transport.error,
            }
        except Exception as exc:  # noqa: BLE001
            checks["runtime_transport"] = {
                "ready": False,
                "latency_ms": int((time.perf_counter() - transport_start) * 1000),
                "error": str(exc),
            }

    if getattr(settings, "READINESS_REQUIRE_COMMUNICATION_KAFKA", False):
        try:
            checks["communication_kafka"] = build_communication_kafka_readiness_payload()
        except Exception as exc:  # noqa: BLE001
            checks["communication_kafka"] = {
                "ready": False,
                "error": str(exc),
            }

    ready = all(bool(check.get("ready")) for check in checks.values())
    status_code = status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ready" if ready else "not_ready", "checks": checks}, status_code


class ReadinessView(APIView):
    permission_classes = [AllowAny]

    def get(self, request: Request) -> Response:
        payload, status_code = build_readiness_payload()
        return Response(payload, status=status_code)
