"""Agent registry API views."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.responses import error_response, success_response
from application.services.os_projections import agent_summary, refresh_phase1_projections
from infrastructure.orm.models import AgentRegistryEntry, User


class AgentListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        bundle = refresh_phase1_projections(cast(User, request.user))
        return success_response([agent_summary(agent) for agent in bundle.agents])


class AgentDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, agent_id: UUID) -> Response:
        bundle = refresh_phase1_projections(cast(User, request.user))
        try:
            agent = AgentRegistryEntry.objects.get(id=agent_id, organization=bundle.organization)
        except AgentRegistryEntry.DoesNotExist:
            return error_response("NOT_FOUND", "Agent not found", status=404)
        return success_response(agent_summary(agent))
