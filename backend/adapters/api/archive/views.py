"""Company archive API views."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from django.http import HttpResponse
from rest_framework import status as http_status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.archive.serializers import (
    AssetListQuerySerializer,
    EvidenceLinkQuerySerializer,
    MediaGenerationCreateSerializer,
)
from adapters.api.responses import error_response, success_response
from application.services.company_archive import (
    ArchiveService,
    asset_payload,
    asset_version_payload,
    context_pack_payload,
    evidence_link_payload,
)
from application.services.gemini_media import (
    GeminiMediaError,
    MediaGenerationService,
    media_generation_job_payload,
    read_media_asset_version_content,
)
from application.services.rbac import has_min_role
from infrastructure.orm.models import (
    APIKey,
    Asset,
    AssetVersion,
    ContextPack,
    EvidenceLink,
    Graph,
    MediaGenerationJob,
    User,
)


class AssetListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        serializer = AssetListQuerySerializer(data=request.query_params)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        user = cast(User, request.user)
        company = _get_company(user, serializer.validated_data["company_id"])
        if company is None:
            return _not_found("Company was not found or you do not have access to it.")
        if not _has_company_role(user, company, "viewer"):
            return _forbidden("You do not have permission to view this archive.")

        assets = ArchiveService().get_company_assets(
            company=company,
            asset_type=_blank_to_none(serializer.validated_data.get("asset_type")),
            status=_blank_to_none(serializer.validated_data.get("status")),
            operation_id=serializer.validated_data.get("operation_id"),
        )
        return success_response({"assets": [asset_payload(asset) for asset in assets]})


class AssetDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, asset_id: UUID) -> Response:
        user = cast(User, request.user)
        asset = _get_asset_for_user(user=user, asset_id=asset_id)
        if asset is None:
            return _not_found("Asset was not found.")
        if not _has_company_role(user, asset.company, "viewer"):
            return _forbidden("You do not have permission to view this asset.")
        return success_response({"asset": asset_payload(asset)})


class AssetVersionListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, asset_id: UUID) -> Response:
        user = cast(User, request.user)
        asset = _get_asset_for_user(user=user, asset_id=asset_id)
        if asset is None:
            return _not_found("Asset was not found.")
        if not _has_company_role(user, asset.company, "viewer"):
            return _forbidden("You do not have permission to view this asset.")
        versions = AssetVersion.objects.filter(asset=asset).order_by("-version_number")
        return success_response(
            {"versions": [asset_version_payload(version) for version in versions]}
        )


class AssetVersionContentView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, asset_id: UUID, version_id: UUID) -> HttpResponse | Response:
        user = cast(User, request.user)
        asset = _get_asset_for_user(user=user, asset_id=asset_id)
        if asset is None:
            return _not_found("Asset was not found.")
        if not _has_company_role(user, asset.company, "viewer"):
            return _forbidden("You do not have permission to view this asset.")
        version = AssetVersion.objects.filter(id=version_id, asset=asset).first()
        if version is None:
            return _not_found("Asset version was not found.")
        try:
            content, mime_type, filename = read_media_asset_version_content(version)
        except FileNotFoundError:
            return _not_found("Asset content was not found.")
        except PermissionError:
            return _forbidden("Asset content path is not allowed.")
        response = HttpResponse(content, content_type=mime_type)
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class MediaGenerationCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = MediaGenerationCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        user = cast(User, request.user)
        company = _get_company(user, serializer.validated_data["company_id"])
        if company is None:
            return _not_found("Company was not found or you do not have access to it.")
        if company.organization_id is None:
            return _not_found("Company organization was not found.")
        if not _has_company_role(user, company, "member"):
            return _forbidden("You do not have permission to generate media for this company.")

        credential = APIKey.objects.filter(
            id=serializer.validated_data["credential_id"],
            organization_id=company.organization_id,
            provider__in=["google", "openrouter"],
        ).first()
        if credential is None:
            return _not_found("Media generation credential was not found for this company.")

        try:
            job = MediaGenerationService().create_job(
                user=user,
                company=company,
                credential=credential,
                modality=str(serializer.validated_data["modality"]),
                prompt=str(serializer.validated_data["prompt"]),
                idempotency_key=str(serializer.validated_data.get("idempotency_key") or ""),
                model=str(serializer.validated_data.get("model") or ""),
            )
        except GeminiMediaError as exc:
            return error_response(
                code=exc.code.upper(),
                message=exc.message,
                status=http_status.HTTP_400_BAD_REQUEST,
            )
        return success_response(
            {"media_generation": media_generation_job_payload(job)},
            status=http_status.HTTP_201_CREATED,
        )


class MediaGenerationDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, job_id: UUID) -> Response:
        user = cast(User, request.user)
        job = _get_media_job_for_user(user=user, job_id=job_id)
        if job is None:
            return _not_found("Media generation job was not found.")
        if not _has_company_role(user, job.company, "viewer"):
            return _forbidden("You do not have permission to view this media generation job.")
        return success_response({"media_generation": media_generation_job_payload(job)})


class MediaGenerationPollView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, job_id: UUID) -> Response:
        user = cast(User, request.user)
        job = _get_media_job_for_user(user=user, job_id=job_id)
        if job is None:
            return _not_found("Media generation job was not found.")
        if not _has_company_role(user, job.company, "member"):
            return _forbidden("You do not have permission to poll this media generation job.")
        try:
            job = MediaGenerationService().poll_video_job(job=job)
        except GeminiMediaError as exc:
            return error_response(
                code=exc.code.upper(),
                message=exc.message,
                status=http_status.HTTP_400_BAD_REQUEST,
            )
        return success_response({"media_generation": media_generation_job_payload(job)})


class ContextPackDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, context_pack_id: UUID) -> Response:
        user = cast(User, request.user)
        context_pack = (
            ContextPack.objects.select_related("company")
            .filter(id=context_pack_id, company__in=Graph.objects.for_user(user))
            .first()
        )
        if context_pack is None:
            return _not_found("Context pack was not found.")
        if not _has_company_role(user, context_pack.company, "viewer"):
            return _forbidden("You do not have permission to view this context pack.")
        return success_response({"context_pack": context_pack_payload(context_pack)})


class EvidenceLinkListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        serializer = EvidenceLinkQuerySerializer(data=request.query_params)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        user = cast(User, request.user)
        company = _get_company(user, serializer.validated_data["company_id"])
        if company is None:
            return _not_found("Company was not found or you do not have access to it.")
        if not _has_company_role(user, company, "viewer"):
            return _forbidden("You do not have permission to view evidence links.")

        queryset = EvidenceLink.objects.filter(company=company).select_related(
            "asset",
            "asset_version",
            "asset_extract",
            "context_pack",
        )
        operation_id = serializer.validated_data.get("operation_id")
        task_id = serializer.validated_data.get("task_id")
        decision_id = serializer.validated_data.get("decision_id")
        if operation_id:
            queryset = queryset.filter(operation_id=operation_id)
        if task_id:
            queryset = queryset.filter(task_id=task_id)
        if decision_id:
            queryset = queryset.filter(decision_id=decision_id)
        return success_response(
            {"evidence_links": [evidence_link_payload(link) for link in queryset[:100]]}
        )


def _get_company(user: User, company_id: UUID) -> Graph | None:
    return cast(Graph | None, Graph.objects.for_user(user).filter(id=company_id).first())


def _get_asset_for_user(*, user: User, asset_id: UUID) -> Asset | None:
    return (
        Asset.objects.select_related("company", "organization")
        .filter(id=asset_id, company__in=Graph.objects.for_user(user))
        .first()
    )


def _get_media_job_for_user(*, user: User, job_id: UUID) -> MediaGenerationJob | None:
    return (
        MediaGenerationJob.objects.select_related(
            "company",
            "organization",
            "credential",
            "output_asset",
            "output_asset_version",
        )
        .filter(id=job_id, company__in=Graph.objects.for_user(user))
        .first()
    )


def _has_company_role(user: User, company: Graph, role: str) -> bool:
    return bool(company.organization_id) and has_min_role(user, role, str(company.organization_id))


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _validation_error(errors: dict[str, Any]) -> Response:
    return error_response(
        code="VALIDATION_ERROR",
        message="The request contains invalid fields.",
        status=http_status.HTTP_400_BAD_REQUEST,
        details=[
            {"field": field, "issue": ", ".join(str(error) for error in field_errors)}
            for field, field_errors in errors.items()
        ],
    )


def _not_found(message: str) -> Response:
    return error_response("NOT_FOUND", message, status=http_status.HTTP_404_NOT_FOUND)


def _forbidden(message: str) -> Response:
    return error_response("FORBIDDEN", message, status=http_status.HTTP_403_FORBIDDEN)
