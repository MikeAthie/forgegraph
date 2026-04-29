"""Post-operation report builder API views."""

from __future__ import annotations

from typing import cast

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.reports.serializers import StrategyReportRequestSerializer
from adapters.api.responses import error_response, success_response
from application.services.strategy_report_builder import (
    ReportBuilderError,
    ReportStateNotFound,
    ReportTraceabilityError,
    generate_strategy_report,
)
from infrastructure.orm.models import Graph, Run, User


class StrategyReportGenerateView(APIView):
    """Generate a client-ready strategy report from completed operation state."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = StrategyReportRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                code="VALIDATION_ERROR",
                message="The request contains invalid fields.",
                status=status.HTTP_400_BAD_REQUEST,
                details=[
                    {"field": field, "issue": ", ".join(errors)}
                    for field, errors in serializer.errors.items()
                ],
            )

        user = cast(User, request.user)
        company_id = serializer.validated_data["company_id"]
        operation_id = serializer.validated_data["operation_id"]
        company = Graph.objects.for_user(user).filter(id=company_id).first()
        if company is None:
            return error_response(
                code="NOT_FOUND",
                message="Company was not found or you do not have access to it.",
                status=status.HTTP_404_NOT_FOUND,
            )
        operation = Run.objects.filter(id=operation_id, graph_version__graph=company).first()
        if operation is None:
            return error_response(
                code="NOT_FOUND",
                message="Operation was not found for the requested company.",
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            artifact = generate_strategy_report(
                company_id=str(company_id),
                operation_id=str(operation_id),
                audience=serializer.validated_data["audience"],
                format=serializer.validated_data["format"],
            )
        except ReportStateNotFound as exc:
            return error_response("NOT_FOUND", str(exc), status=status.HTTP_404_NOT_FOUND)
        except ReportTraceabilityError as exc:
            return error_response(
                "REPORT_NOT_TRACEABLE", str(exc), status=status.HTTP_422_UNPROCESSABLE_ENTITY
            )
        except ReportBuilderError as exc:
            return error_response("VALIDATION_ERROR", str(exc), status=status.HTTP_400_BAD_REQUEST)

        return success_response(artifact.api_payload())
