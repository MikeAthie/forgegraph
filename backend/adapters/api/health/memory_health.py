"""
Memory health endpoints.

Checks Redis connectivity used for caching/channels.
"""

import time

from django.core.cache import cache
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class MemoryHealthView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
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
