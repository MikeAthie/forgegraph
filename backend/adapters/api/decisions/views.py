"""Decision ledger API views."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from django.db.models import Q
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.responses import error_response, success_response
from application.services.company_access import accessible_company_queryset
from application.services.os_projections import decision_summary, projection_organization_for_user
from infrastructure.orm.models import DecisionRecord, User


class DecisionListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        organization = projection_organization_for_user(user)
        accessible_companies = accessible_company_queryset(user)
        decisions = DecisionRecord.objects.filter(organization=organization).filter(
            Q(execution__graph_version__graph__in=accessible_companies)
            | Q(source_approval_task__run__graph_version__graph__in=accessible_companies)
            | Q(execution__isnull=True, source_approval_task__isnull=True)
        ).select_related(
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
        user = cast(User, request.user)
        organization = projection_organization_for_user(user)
        accessible_companies = accessible_company_queryset(user)
        try:
            decision = DecisionRecord.objects.select_related(
                "execution", "task", "agent", "source_approval_task"
            ).filter(
                Q(execution__graph_version__graph__in=accessible_companies)
                | Q(source_approval_task__run__graph_version__graph__in=accessible_companies)
                | Q(execution__isnull=True, source_approval_task__isnull=True)
            ).get(id=decision_id, organization=organization)
        except DecisionRecord.DoesNotExist:
            return error_response("NOT_FOUND", "Decision not found", status=404)
        return success_response(decision_summary(decision))


class DecisionCountView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        organization = projection_organization_for_user(user)
        accessible_companies = accessible_company_queryset(user)
        count = DecisionRecord.objects.filter(organization=organization, status="pending").filter(
            Q(execution__graph_version__graph__in=accessible_companies)
            | Q(source_approval_task__run__graph_version__graph__in=accessible_companies)
            | Q(execution__isnull=True, source_approval_task__isnull=True)
        ).count()
        return success_response({"count": count})
