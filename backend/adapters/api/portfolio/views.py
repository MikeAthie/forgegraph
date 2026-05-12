"""Generic portfolio read-model and company assignment APIs."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from rest_framework import status as http_status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.portfolio.serializers import (
    CompanyAssignmentCreateSerializer,
    CompanyAssignmentPatchSerializer,
    CompanyAssignmentQuerySerializer,
    CrossCompanyQueueQuerySerializer,
)
from adapters.api.responses import error_response, success_response
from application.services.audit_log import record_audit_log
from application.services.company_access import accessible_company_queryset, has_company_access
from application.services.portfolio_read_models import (
    company_assignment_payload,
    credential_health_payload,
    cross_company_queues_payload,
    portfolio_health_payload,
    portfolio_views_payload,
    portfolios_payload,
)
from application.services.rbac import has_min_role
from infrastructure.orm.models import (
    CompanyAssignment,
    Graph,
    OrganizationMembership,
    User,
)


class PortfolioListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        if not has_min_role(user, "viewer"):
            return _forbidden("You do not have permission to view portfolios.")
        return success_response(portfolios_payload(user))


class PortfolioViewListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        if not has_min_role(user, "viewer"):
            return _forbidden("You do not have permission to view portfolio views.")
        return success_response(portfolio_views_payload(user))


class PortfolioHealthView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        if not has_min_role(user, "viewer"):
            return _forbidden("You do not have permission to view portfolio health.")
        return success_response(portfolio_health_payload(user))


class CrossCompanyQueuesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        if not has_min_role(user, "viewer"):
            return _forbidden("You do not have permission to view cross-company queues.")
        serializer = CrossCompanyQueueQuerySerializer(data=request.query_params)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        return success_response(
            cross_company_queues_payload(
                user,
                queue_type=str(serializer.validated_data.get("type") or "all"),
            )
        )


class CredentialHealthView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        if not has_min_role(user, "viewer"):
            return _forbidden("You do not have permission to view credential health.")
        return success_response(credential_health_payload(user))


class CompanyAssignmentListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        serializer = CompanyAssignmentQuerySerializer(data=request.query_params)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        company_id = serializer.validated_data.get("company_id")
        companies = accessible_company_queryset(user, minimum_role="admin")
        if company_id:
            companies = companies.filter(id=company_id)
        assignments = (
            CompanyAssignment.objects.filter(company__in=companies)
            .select_related("company", "user")
            .order_by("company__name", "user__email")
        )
        return success_response(
            {"assignments": [company_assignment_payload(item) for item in assignments]}
        )

    def post(self, request: Request) -> Response:
        user = cast(User, request.user)
        serializer = CompanyAssignmentCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        company = _company_for_admin(user, serializer.validated_data["company_id"])
        if company is None:
            return _not_found("Company was not found or you do not have access to manage it.")
        target_user = _target_user_for_assignment(serializer.validated_data)
        if target_user is None:
            return _not_found("Assigned user was not found.")
        if not OrganizationMembership.objects.filter(
            organization=company.organization,
            user=target_user,
        ).exists():
            return error_response(
                "NOT_ORG_MEMBER",
                "Assigned user must belong to the company organization.",
                status=http_status.HTTP_400_BAD_REQUEST,
            )
        assignment, created = CompanyAssignment.objects.update_or_create(
            company=company,
            user=target_user,
            defaults={
                "organization": company.organization,
                "role": serializer.validated_data["role"],
                "status": serializer.validated_data["status"],
                "expires_at": serializer.validated_data.get("expires_at"),
                "created_by": user,
            },
        )
        record_audit_log(
            actor=user,
            tenant_id=str(company.organization_id),
            action="company_assignment.created" if created else "company_assignment.updated",
            resource_type="company_assignment",
            resource_id=str(assignment.id),
            metadata={
                "company_id": str(company.id),
                "user_id": str(target_user.id),
                "role": assignment.role,
                "status": assignment.status,
            },
        )
        return success_response(
            {"assignment": company_assignment_payload(assignment)},
            status=http_status.HTTP_201_CREATED if created else http_status.HTTP_200_OK,
        )


class CompanyAssignmentDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request: Request, assignment_id: UUID) -> Response:
        user = cast(User, request.user)
        serializer = CompanyAssignmentPatchSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        assignment = (
            CompanyAssignment.objects.select_related("company", "company__organization", "user")
            .filter(id=assignment_id)
            .first()
        )
        if assignment is None or not has_company_access(user, assignment.company, minimum_role="admin"):
            return _not_found("Company assignment was not found.")
        update_fields: list[str] = ["updated_at"]
        if "role" in serializer.validated_data:
            assignment.role = serializer.validated_data["role"]
            update_fields.append("role")
        if "status" in serializer.validated_data:
            assignment.status = serializer.validated_data["status"]
            update_fields.append("status")
        if "expires_at" in serializer.validated_data:
            assignment.expires_at = serializer.validated_data["expires_at"]
            update_fields.append("expires_at")
        assignment.save(update_fields=sorted(set(update_fields)))
        record_audit_log(
            actor=user,
            tenant_id=str(assignment.organization_id),
            action="company_assignment.updated",
            resource_type="company_assignment",
            resource_id=str(assignment.id),
            metadata={
                "company_id": str(assignment.company_id),
                "user_id": str(assignment.user_id),
                "role": assignment.role,
                "status": assignment.status,
            },
        )
        return success_response({"assignment": company_assignment_payload(assignment)})


def _company_for_admin(user: User, company_id: UUID) -> Graph | None:
    return cast(
        Graph | None,
        accessible_company_queryset(user, minimum_role="admin")
        .filter(id=company_id)
        .select_related("organization")
        .first(),
    )


def _target_user_for_assignment(validated_data: dict[str, Any]) -> User | None:
    user_id = validated_data.get("user_id")
    if user_id:
        return User.objects.filter(id=user_id).first()
    email = str(validated_data.get("email") or "").lower().strip()
    if not email:
        return None
    return User.objects.filter(email=email).first()


def _validation_error(details: Any) -> Response:
    return error_response(
        "VALIDATION_ERROR",
        "Request validation failed.",
        status=http_status.HTTP_400_BAD_REQUEST,
        details=[{"field": key, "errors": value} for key, value in dict(details).items()],
    )


def _not_found(message: str) -> Response:
    return error_response("NOT_FOUND", message, status=http_status.HTTP_404_NOT_FOUND)


def _forbidden(message: str) -> Response:
    return error_response("FORBIDDEN", message, status=http_status.HTTP_403_FORBIDDEN)
