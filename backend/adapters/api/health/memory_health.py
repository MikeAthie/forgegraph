"""
Memory health endpoints.

Checks Redis connectivity used for caching/channels.
"""

import os
import time
from typing import Any

import grpc
from django.core.cache import cache
from grpc_health.v1 import health_pb2, health_pb2_grpc
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView


class MemoryHealthView(APIView):
    permission_classes = [AllowAny]

    def get(self, request: Request) -> Response:
        start = time.time()
        key = "memory_health_check"
        try:
            cache.set(key, "ok", timeout=5)
            value = cache.get(key)
            healthy = value == "ok"
            latency_ms = int((time.time() - start) * 1000)
            payload = {
                "redis": {
                    "healthy": healthy,
                    "latency_ms": latency_ms,
                }
            }
            payload["grpc"] = _check_memory_grpc()
            payload["metrics"] = _get_memory_metrics()
            status_code = status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE
            return Response(payload, status=status_code)
        except Exception as exc:  # noqa: BLE001
            latency_ms = int((time.time() - start) * 1000)
            return Response(
                {
                    "redis": {
                        "healthy": False,
                        "latency_ms": latency_ms,
                        "error": str(exc),
                    }
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )


def _check_memory_grpc() -> dict[str, Any]:
    host = os.getenv("MEMORY_GRPC_HOST", "")
    port = os.getenv("MEMORY_GRPC_PORT", "")
    if not host or not port:
        return {"configured": False}

    target = f"{host}:{port}"
    try:
        with grpc.insecure_channel(target) as channel:
            stub = health_pb2_grpc.HealthStub(channel)
            response = stub.Check(health_pb2.HealthCheckRequest(service="memory"), timeout=0.2)
            healthy = response.status == health_pb2.HealthCheckResponse.SERVING
            return {"configured": True, "healthy": healthy}
    except Exception as exc:  # noqa: BLE001
        return {"configured": True, "healthy": False, "error": str(exc)}


def _get_memory_metrics() -> dict[str, Any]:
    from django.core.cache import cache

    return {
        "memory_gc_deleted_retention_total": cache.get("memory_gc_deleted_retention_total", 0),
        "memory_gc_deleted_tenant_total": cache.get("memory_gc_deleted_tenant_total", 0),
        "memory_gc_deleted_missing_users_total": cache.get(
            "memory_gc_deleted_missing_users_total", 0
        ),
        "memory_gc_last_run_at": cache.get("memory_gc_last_run_at"),
        "memory_gc_last_reindex": cache.get("memory_gc_last_reindex"),
        "memory_grpc_requests_total": cache.get("memory_grpc_requests_total", 0),
        "memory_grpc_errors_total": cache.get("memory_grpc_errors_total", 0),
        "memory_observation_index_jobs_total": cache.get("memory_observation_index_jobs_total", 0),
        "memory_observation_index_success_total": cache.get(
            "memory_observation_index_success_total", 0
        ),
        "memory_observation_index_delete_total": cache.get(
            "memory_observation_index_delete_total", 0
        ),
        "memory_observation_index_enqueue_errors_total": cache.get(
            "memory_observation_index_enqueue_errors_total", 0
        ),
        "memory_observation_delete_enqueue_errors_total": cache.get(
            "memory_observation_delete_enqueue_errors_total", 0
        ),
    }
