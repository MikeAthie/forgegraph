"""Company API aliases backed by existing Graph storage."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from django.db import transaction
from django.db.models import QuerySet
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.companies.serializers import (
    CompanyCreateSerializer,
    CompanyOperatingModelVersionCreateSerializer,
    CompanyOperatingModelVersionSerializer,
    CompanySerializer,
    CompanyUpdateSerializer,
)
from adapters.api.responses import error_response, success_response
from application.services.company_access import (
    accessible_company_queryset,
    ensure_default_company_access_policy,
    has_company_access,
)
from application.services.rbac import has_min_role
from domain.services.graph_validator import GraphValidator
from infrastructure.orm.models import Graph, GraphVersion, MemoryConfiguration, User


def _create_company_memory_config(company: Graph, user: User) -> None:
    default_config = MemoryConfiguration.objects.filter(user=user).first()
    if default_config:
        MemoryConfiguration.objects.create(
            graph=company,
            buffer_enabled=default_config.buffer_enabled,
            buffer_size=default_config.buffer_size,
            auto_prepend=default_config.auto_prepend,
            redis_enabled=default_config.redis_enabled,
            redis_summary_ttl=default_config.redis_summary_ttl,
            redis_facts_ttl=default_config.redis_facts_ttl,
            vector_enabled=default_config.vector_enabled,
            vector_top_k=default_config.vector_top_k,
            vector_threshold=default_config.vector_threshold,
            vector_recency_weight=default_config.vector_recency_weight,
            embedding_model=default_config.embedding_model,
        )
        return
    MemoryConfiguration.objects.create(graph=company)


def _companies_for_user(user: User, *, minimum_role: str = "viewer") -> QuerySet[Graph]:
    return accessible_company_queryset(user, minimum_role=minimum_role)


def _company_for_user(company_id: UUID, user: User, *, minimum_role: str = "viewer") -> Graph | None:
    company = (
        _companies_for_user(user, minimum_role=minimum_role)
        .filter(id=company_id)
        .select_related("organization")
        .first()
    )
    if company is None:
        return None
    if not has_company_access(user, company, minimum_role=minimum_role):
        return None
    return company


def _company_payload(company: Graph) -> dict[str, Any]:
    latest_version = company.versions.order_by("-version").first()
    return {
        "id": company.id,
        "company_id": company.id,
        "workflow_definition_id": company.id,
        "storage_model": "Graph",
        "organization_id": company.organization_id,
        "name": company.name,
        "description": company.description,
        "created_at": company.created_at,
        "updated_at": company.updated_at,
        "setup_version_count": company.versions.count(),
        "latest_setup_version": latest_version.version if latest_version else None,
    }


def _version_payload(version: GraphVersion) -> dict[str, Any]:
    return {
        "id": version.id,
        "company_id": version.graph_id,
        "workflow_definition_id": version.graph_id,
        "version": version.version,
        "model_json": version.graph_json,
        "checksum": version.checksum,
        "created_at": version.created_at,
    }


def _validation_error(details: Any) -> Response:
    return error_response(
        code="VALIDATION_ERROR",
        message="The request contains invalid fields.",
        status=status.HTTP_400_BAD_REQUEST,
        details=[
            {"field": field, "issue": ", ".join(errors)}
            for field, errors in dict(details).items()
        ],
    )


def _not_found(company_id: UUID) -> Response:
    return error_response(
        code="NOT_FOUND",
        message=f"Company with id '{company_id}' not found or you do not have access to it.",
        status=status.HTTP_404_NOT_FOUND,
    )


class CompanyListCreateView(APIView):
    """List and create companies through a company-facing alias."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        companies = _companies_for_user(user).order_by("-updated_at")
        payload = [_company_payload(company) for company in companies]
        return success_response(CompanySerializer(payload, many=True).data)

    def post(self, request: Request) -> Response:
        user = cast(User, request.user)
        if not has_min_role(user, "member"):
            return error_response(
                code="FORBIDDEN",
                message="You don't have permission to create companies in this organization.",
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = CompanyCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)

        with transaction.atomic():
            company = Graph.objects.create(
                owner=user,
                organization=user.default_organization,
                name=serializer.validated_data["name"],
                description=serializer.validated_data.get("description", ""),
            )
            _create_company_memory_config(company, user)
            ensure_default_company_access_policy(company)

        payload = CompanySerializer(_company_payload(company)).data
        return success_response(payload, status=status.HTTP_201_CREATED)


class CompanyDetailView(APIView):
    """Get or update company metadata through the company alias."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, company_id: UUID) -> Response:
        company = _company_for_user(company_id, cast(User, request.user))
        if company is None:
            return _not_found(company_id)
        return success_response(CompanySerializer(_company_payload(company)).data)

    def patch(self, request: Request, company_id: UUID) -> Response:
        user = cast(User, request.user)
        company = _company_for_user(company_id, user, minimum_role="member")
        if company is None:
            return _not_found(company_id)

        serializer = CompanyUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)

        if "name" in serializer.validated_data:
            company.name = serializer.validated_data["name"]
        if "description" in serializer.validated_data:
            company.description = serializer.validated_data["description"]
        company.save()

        return success_response(CompanySerializer(_company_payload(company)).data)


class CompanyOperatingModelVersionCreateView(APIView):
    """Create a saved operating model version for a company."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request, company_id: UUID) -> Response:
        user = cast(User, request.user)
        company = _company_for_user(company_id, user, minimum_role="member")
        if company is None:
            return _not_found(company_id)

        serializer = CompanyOperatingModelVersionCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)

        model_json = serializer.validated_data["model_json"]
        validator = GraphValidator()
        issues = validator.validate(model_json, require_entry_exit=False)
        errors = [issue for issue in issues if issue.get("severity") != "warning"]
        if errors:
            return error_response(
                code="OPERATING_MODEL_VALIDATION_ERROR",
                message="Operating model validation failed.",
                status=status.HTTP_400_BAD_REQUEST,
                details=errors,
            )

        latest = company.versions.order_by("-version").first()
        next_version = (latest.version + 1) if latest else 1
        version = GraphVersion.objects.create(
            graph=company,
            version=next_version,
            graph_json=model_json,
        )
        company.save()

        payload = CompanyOperatingModelVersionSerializer(_version_payload(version)).data
        return success_response(payload, status=status.HTTP_201_CREATED)


class CompanyOperatingModelVersionLatestView(APIView):
    """Get the latest saved operating model version for a company."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, company_id: UUID) -> Response:
        company = _company_for_user(company_id, cast(User, request.user))
        if company is None:
            return _not_found(company_id)

        version = company.versions.order_by("-version").first()
        if version is None:
            return error_response(
                code="NOT_FOUND",
                message=f"No operating model versions found for company '{company_id}'.",
                status=status.HTTP_404_NOT_FOUND,
            )

        payload = CompanyOperatingModelVersionSerializer(_version_payload(version)).data
        return success_response(payload)
