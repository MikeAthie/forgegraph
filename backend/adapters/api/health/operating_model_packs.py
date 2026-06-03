"""
Operating model pack health API.
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from application.services.operating_model_packs import build_operating_model_pack_health_payload


class OperatingModelPackHealthView(APIView):
    permission_classes = [AllowAny]
    throttle_classes: list[type] = []

    def get(self, request: Request) -> Response:
        payload = build_operating_model_pack_health_payload()
        status_code = (
            status.HTTP_200_OK
            if payload.get("status") == "ok"
            else status.HTTP_503_SERVICE_UNAVAILABLE
        )
        return Response(payload, status=status_code)
