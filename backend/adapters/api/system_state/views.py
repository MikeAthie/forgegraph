"""System state API views."""

from __future__ import annotations

from typing import cast

from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.responses import success_response
from application.services.os_projections import (
    organization_state_summary,
    refresh_phase1_projections,
)
from infrastructure.orm.models import User


class SystemStateOverviewView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        bundle = refresh_phase1_projections(cast(User, request.user))
        return success_response(organization_state_summary(bundle.organization))
