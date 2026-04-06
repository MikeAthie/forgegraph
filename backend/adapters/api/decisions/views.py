"""Decision ledger API views."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.responses import error_response, success_response
from application.services.os_projections import decision_summary, refresh_phase1_projections
from infrastructure.orm.models import DecisionRecord, User


class DecisionListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        bundle = refresh_phase1_projections(cast(User, request.user))
        decisions = DecisionRecord.objects.filter(organization=bundle.organization).select_related(
            "execution", "task", "agent", "source_approval_task"
        )
        status_filter = request.query_params.get("status")
        if status_filter and status_filter != "all":
            decisions = decisions.filter(status=status_filter)
        return success_response(
            [
                decision_summary(decision)
                for decision in decisions.order_by("-requested_at", "-created_at")
            ]
        )


class DecisionDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, decision_id: UUID) -> Response:
        bundle = refresh_phase1_projections(cast(User, request.user))
        try:
            decision = DecisionRecord.objects.select_related(
                "execution", "task", "agent", "source_approval_task"
            ).get(id=decision_id, organization=bundle.organization)
        except DecisionRecord.DoesNotExist:
            return error_response("NOT_FOUND", "Decision not found", status=404)
        return success_response(decision_summary(decision))


class DecisionCountView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        bundle = refresh_phase1_projections(cast(User, request.user))
        count = DecisionRecord.objects.filter(
            organization=bundle.organization, status="pending"
        ).count()
        return success_response({"count": count})
