"""Interaction layer API views."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.interaction.serializers import (
    CurrentBriefQuerySerializer,
    InteractionEventCreateSerializer,
)
from adapters.api.responses import error_response, success_response
from application.services.interaction import (
    brief_payload,
    current_brief_payload,
    decision_payload,
    event_payload,
    interpretation_payload,
    process_user_interaction,
)
from application.services.rbac import has_min_role
from infrastructure.orm.models import Graph, OperatingBriefRecord, Run, User


class CurrentOperatingBriefView(APIView):
    """Return the current backend-owned operating brief for a company/operation scope."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        serializer = CurrentBriefQuerySerializer(data=request.query_params)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)

        user = cast(User, request.user)
        company = _get_company(user, serializer.validated_data["company_id"])
        if company is None:
            return error_response(
                "NOT_FOUND",
                "Company was not found or you do not have access to it.",
                status=status.HTTP_404_NOT_FOUND,
            )
        if not has_min_role(user, "viewer", str(company.organization_id)):
            return error_response(
                "FORBIDDEN",
                "You do not have permission to view this operating brief.",
                status=status.HTTP_403_FORBIDDEN,
            )

        operation = _get_operation(company, serializer.validated_data.get("operation_id"))
        if serializer.validated_data.get("operation_id") and operation is None:
            return error_response(
                "NOT_FOUND",
                "Operation was not found for the requested company.",
                status=status.HTTP_404_NOT_FOUND,
            )

        return success_response(
            {"brief": current_brief_payload(company=company, operation=operation)}
        )


class InteractionEventCreateView(APIView):
    """Accept free-form user input and persist a structured brief mutation."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = InteractionEventCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)

        user = cast(User, request.user)
        company = _get_company(user, serializer.validated_data["company_id"])
        if company is None:
            return error_response(
                "NOT_FOUND",
                "Company was not found or you do not have access to it.",
                status=status.HTTP_404_NOT_FOUND,
            )
        if not has_min_role(user, "member", str(company.organization_id)):
            return error_response(
                "FORBIDDEN",
                "You do not have permission to mutate this operating brief.",
                status=status.HTTP_403_FORBIDDEN,
            )

        operation = _get_operation(company, serializer.validated_data.get("operation_id"))
        if serializer.validated_data.get("operation_id") and operation is None:
            return error_response(
                "NOT_FOUND",
                "Operation was not found for the requested company.",
                status=status.HTTP_404_NOT_FOUND,
            )

        brief_id = serializer.validated_data.get("brief_id")
        if brief_id is not None and not _brief_matches_scope(
            brief_id=brief_id,
            company=company,
            operation=operation,
        ):
            return error_response(
                "NOT_FOUND",
                "Operating brief was not found for the requested scope.",
                status=status.HTTP_404_NOT_FOUND,
            )

        result = process_user_interaction(
            user=user,
            company=company,
            operation=operation,
            user_input=serializer.validated_data["input"],
        )

        return success_response(
            {
                "brief": brief_payload(result.brief, record=result.brief_record),
                "event": event_payload(result.event_record),
                "interpretation": interpretation_payload(result.interpretation),
                "pm_action": decision_payload(result.decision),
                "plan_implications": result.plan_implications,
            },
            status=status.HTTP_201_CREATED,
        )


def _get_company(user: User, company_id: UUID) -> Graph | None:
    return cast(Graph | None, Graph.objects.for_user(user).filter(id=company_id).first())


def _get_operation(company: Graph, operation_id: UUID | None) -> Run | None:
    if operation_id is None:
        return None
    return Run.objects.filter(id=operation_id, graph_version__graph=company).first()


def _brief_matches_scope(
    *,
    brief_id: UUID,
    company: Graph,
    operation: Run | None,
) -> bool:
    return OperatingBriefRecord.objects.filter(
        id=brief_id,
        organization=company.organization,
        company=company,
        operation=operation,
    ).exists()


def _validation_error(errors: dict[str, Any]) -> Response:
    return error_response(
        code="VALIDATION_ERROR",
        message="The request contains invalid fields.",
        status=status.HTTP_400_BAD_REQUEST,
        details=[
            {"field": field, "issue": ", ".join(str(error) for error in field_errors)}
            for field, field_errors in errors.items()
        ],
    )
