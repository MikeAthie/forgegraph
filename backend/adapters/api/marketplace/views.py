"""Marketplace API views."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from django.conf import settings
from django.db import models
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.marketplace.serializers import (
    MarketplaceInstallSerializer,
    MarketplaceReleaseCreateSerializer,
    MarketplaceReleaseReviewSerializer,
)
from adapters.api.responses import error_response, success_response
from application.services.audit_log import record_audit_log
from application.services.gateway_registry import capability_for_tool_id, capability_payload
from application.services.marketplace_runtime import (
    build_install_metadata,
    build_runtime_delivery_state,
    build_runtime_manifest_payload,
    is_release_installable_in_runtime_mode,
)
from application.services.rbac import has_min_role
from application.services.tenancy import get_tenant_id_for_user
from infrastructure.orm.models import (
    NodePackageInstallation,
    NodeRegistryPackage,
    NodeRegistryRelease,
    User,
)
from infrastructure.security import s2s


def _serialize_release(release: NodeRegistryRelease | None) -> dict[str, Any] | None:
    if release is None:
        return None
    runtime_manifest = (
        release.runtime_manifest if isinstance(release.runtime_manifest, dict) else {}
    )
    tool_id = str(
        runtime_manifest.get("name")
        or (runtime_manifest.get("execution") or {}).get("local", {}).get("handler")
        or release.config_defaults.get("tool_id")
        or release.config_defaults.get("tool")
        or ""
    )
    return {
        "id": str(release.id),
        "version": release.version,
        "changelog": release.changelog,
        "status": release.status,
        "package_kind": release.package_kind,
        "execution_node_type": release.execution_node_type,
        "ui_schema": release.ui_schema,
        "config_schema": release.config_schema,
        "config_defaults": release.config_defaults,
        "runtime_manifest": release.runtime_manifest,
        "gateway_capability": capability_payload(capability_for_tool_id(tool_id)),
        "manifest_version": release.manifest_version,
        "cloud_allowed": release.cloud_allowed,
        "review_notes": release.review_notes,
        "created_at": release.created_at,
    }


def _serialize_package(
    package: NodeRegistryPackage,
    *,
    latest_release: NodeRegistryRelease | None,
    installed_release: NodeRegistryRelease | None = None,
    install_metadata: dict[str, Any] | None = None,
    runtime_mode: str,
) -> dict[str, Any]:
    return {
        "id": str(package.id),
        "slug": package.slug,
        "name": package.name,
        "summary": package.summary,
        "category": package.category,
        "icon": package.icon,
        "docs_url": package.docs_url,
        "homepage_url": package.homepage_url,
        "latest_release": _serialize_release(latest_release),
        "installed_release": _serialize_release(installed_release),
        "install_metadata": install_metadata,
        "runtime_delivery": (
            build_runtime_delivery_state(installed_release, runtime_mode)
            if installed_release is not None
            else (
                build_runtime_delivery_state(latest_release, runtime_mode)
                if latest_release is not None
                else None
            )
        ),
    }


def _latest_approved_release(package: NodeRegistryPackage) -> NodeRegistryRelease | None:
    return package.releases.filter(status="approved").order_by("-created_at").first()


class MarketplaceCatalogView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        if not has_min_role(user, "member"):
            return error_response(
                code="FORBIDDEN",
                message="You don't have permission to view marketplace packages.",
                status=status.HTTP_403_FORBIDDEN,
            )

        org = user.default_organization
        runtime_mode = settings.FORGEGRAPH_RUNTIME_MODE
        installations_by_package: dict[UUID, NodeRegistryRelease] = {}
        if org is not None:
            installs = NodePackageInstallation.objects.filter(
                organization=org, is_active=True
            ).select_related("release", "package")
            installations_by_package = {install.package_id: install.release for install in installs}

        packages = NodeRegistryPackage.objects.filter(is_active=True).order_by("name")
        data: list[dict[str, Any]] = []
        for package in packages:
            latest = _latest_approved_release(package)
            if latest is None:
                continue
            installed = installations_by_package.get(package.id)
            data.append(
                _serialize_package(
                    package,
                    latest_release=latest,
                    installed_release=installed,
                    runtime_mode=runtime_mode,
                )
            )
        return success_response(data)


class MarketplaceInstalledView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        if not has_min_role(user, "member"):
            return error_response(
                code="FORBIDDEN",
                message="You don't have permission to view installed packages.",
                status=status.HTTP_403_FORBIDDEN,
            )

        org = user.default_organization
        runtime_mode = settings.FORGEGRAPH_RUNTIME_MODE
        if org is None:
            return success_response([])

        installs = (
            NodePackageInstallation.objects.filter(organization=org, is_active=True)
            .select_related("package", "release")
            .order_by("package__name")
        )

        data = [
            {
                **_serialize_package(
                    install.package,
                    latest_release=_latest_approved_release(install.package),
                    installed_release=install.release,
                    install_metadata=install.install_metadata,
                    runtime_mode=runtime_mode,
                ),
                "installed_at": install.installed_at,
            }
            for install in installs
        ]
        return success_response(data)


class MarketplaceInstallView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, package_slug: str) -> Response:
        serializer = MarketplaceInstallSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                code="VALIDATION_ERROR",
                message="The request contains invalid fields",
                status=status.HTTP_400_BAD_REQUEST,
                details=[
                    {"field": field, "issue": ", ".join(errors)}
                    for field, errors in serializer.errors.items()
                ],
            )

        user = cast(User, request.user)
        if not has_min_role(user, "admin"):
            return error_response(
                code="FORBIDDEN",
                message="You don't have permission to install marketplace packages.",
                status=status.HTTP_403_FORBIDDEN,
            )

        org = user.default_organization
        runtime_mode = settings.FORGEGRAPH_RUNTIME_MODE
        if org is None:
            return error_response(
                code="FORBIDDEN",
                message="No organization found for this user.",
                status=status.HTTP_403_FORBIDDEN,
            )

        package = NodeRegistryPackage.objects.filter(slug=package_slug, is_active=True).first()
        if package is None:
            return error_response(
                code="NOT_FOUND",
                message=f"Package '{package_slug}' not found.",
                status=status.HTTP_404_NOT_FOUND,
            )

        requested_version = serializer.validated_data.get("version")
        release_query = package.releases.filter(status="approved")
        if requested_version:
            release_query = release_query.filter(version=requested_version)
        release = release_query.order_by("-created_at").first()
        if release is None:
            return error_response(
                code="NOT_FOUND",
                message="No approved release found for this package/version.",
                status=status.HTTP_404_NOT_FOUND,
            )

        installable, delivery = is_release_installable_in_runtime_mode(release, runtime_mode)
        if not installable:
            record_audit_log(
                actor=user,
                tenant_id=get_tenant_id_for_user(user),
                action="marketplace.package_install_blocked",
                resource_type="node_release",
                resource_id=str(release.id),
                metadata={
                    "package_slug": package.slug,
                    "release_version": release.version,
                    "runtime_mode": runtime_mode,
                    "delivery_state": delivery["state"],
                    "delivery_reason": delivery["reason"],
                },
            )
            return error_response(
                code="POLICY_DENIED",
                message=(
                    f"Package '{package.slug}' cannot be installed in {runtime_mode} mode: "
                    f"{delivery['reason']}."
                ),
                status=status.HTTP_409_CONFLICT,
            )

        install, _ = NodePackageInstallation.objects.update_or_create(
            organization=org,
            package=package,
            defaults={
                "release": release,
                "installed_by": user,
                "is_active": True,
                "install_metadata": build_install_metadata(release, runtime_mode),
            },
        )

        record_audit_log(
            actor=user,
            tenant_id=get_tenant_id_for_user(user),
            action="marketplace.package_installed",
            resource_type="node_package",
            resource_id=str(package.id),
            metadata={
                "package_slug": package.slug,
                "release_version": release.version,
                "organization_id": str(org.id),
            },
        )

        return success_response(
            {
                **_serialize_package(
                    package,
                    latest_release=_latest_approved_release(package),
                    installed_release=release,
                    install_metadata=install.install_metadata,
                    runtime_mode=runtime_mode,
                ),
                "installed_at": install.installed_at,
            },
            status=status.HTTP_201_CREATED,
        )


class MarketplaceReleaseListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        if not has_min_role(user, "admin"):
            return error_response(
                code="FORBIDDEN",
                message="You don't have permission to view package releases.",
                status=status.HTTP_403_FORBIDDEN,
            )

        org = user.default_organization
        if org is None:
            return success_response([])

        releases = (
            NodeRegistryRelease.objects.select_related("package")
            .filter(models.Q(package__owner_organization=org) | models.Q(status="pending_review"))
            .order_by("-created_at")
        )
        data = [
            {
                "id": str(release.id),
                "package_slug": release.package.slug,
                "package_name": release.package.name,
                "version": release.version,
                "status": release.status,
                "package_kind": release.package_kind,
                "execution_node_type": release.execution_node_type,
                "cloud_allowed": release.cloud_allowed,
                "created_at": release.created_at,
            }
            for release in releases
        ]
        return success_response(data)

    def post(self, request: Request) -> Response:
        serializer = MarketplaceReleaseCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                code="VALIDATION_ERROR",
                message="The request contains invalid fields",
                status=status.HTTP_400_BAD_REQUEST,
                details=[
                    {"field": field, "issue": ", ".join(errors)}
                    for field, errors in serializer.errors.items()
                ],
            )

        user = cast(User, request.user)
        if not has_min_role(user, "admin"):
            return error_response(
                code="FORBIDDEN",
                message="You don't have permission to publish package releases.",
                status=status.HTTP_403_FORBIDDEN,
            )

        org = user.default_organization
        if org is None:
            return error_response(
                code="FORBIDDEN",
                message="No organization found for this user.",
                status=status.HTTP_403_FORBIDDEN,
            )

        payload = serializer.validated_data
        package_slug = payload["package_slug"]

        package = NodeRegistryPackage.objects.filter(slug=package_slug).first()
        if package is None:
            package_name = payload.get("package_name")
            if not package_name:
                return error_response(
                    code="VALIDATION_ERROR",
                    message="package_name is required when creating a new package.",
                    status=status.HTTP_400_BAD_REQUEST,
                )
            package = NodeRegistryPackage.objects.create(
                slug=package_slug,
                name=package_name,
                summary=payload.get("package_summary") or "",
                category=payload.get("package_category") or "other",
                icon=payload.get("package_icon") or "",
                owner_organization=org,
                created_by=user,
            )
        elif package.owner_organization_id not in {None, org.id} and not has_min_role(
            user, "owner"
        ):
            return error_response(
                code="FORBIDDEN",
                message="You don't have permission to publish releases for this package.",
                status=status.HTTP_403_FORBIDDEN,
            )

        if package.owner_organization_id is None:
            package.owner_organization = org
            package.save(update_fields=["owner_organization"])

        release = NodeRegistryRelease.objects.create(
            package=package,
            version=payload["version"],
            changelog=payload.get("changelog") or "",
            status="pending_review",
            package_kind=payload["package_kind"],
            execution_node_type=payload["execution_node_type"],
            ui_schema=payload.get("ui_schema") or {},
            config_schema=payload.get("config_schema") or {},
            config_defaults=payload.get("config_defaults") or {},
            runtime_manifest=payload.get("runtime_manifest"),
            manifest_version=payload.get("manifest_version") or 1,
            cloud_allowed=payload.get("cloud_allowed", True),
            review_notes=payload.get("review_notes") or "",
            created_by=user,
        )

        record_audit_log(
            actor=user,
            tenant_id=get_tenant_id_for_user(user),
            action="marketplace.release_submitted",
            resource_type="node_release",
            resource_id=str(release.id),
            metadata={
                "package_slug": package.slug,
                "version": release.version,
            },
        )

        return success_response(
            {
                "id": str(release.id),
                "package_slug": package.slug,
                "version": release.version,
                "status": release.status,
                "package_kind": release.package_kind,
            },
            status=status.HTTP_201_CREATED,
        )


class MarketplaceReleaseReviewView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request: Request, release_id: UUID) -> Response:
        serializer = MarketplaceReleaseReviewSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                code="VALIDATION_ERROR",
                message="The request contains invalid fields",
                status=status.HTTP_400_BAD_REQUEST,
                details=[
                    {"field": field, "issue": ", ".join(errors)}
                    for field, errors in serializer.errors.items()
                ],
            )

        user = cast(User, request.user)
        if not has_min_role(user, "owner"):
            return error_response(
                code="FORBIDDEN",
                message="Only organization owners can review releases.",
                status=status.HTTP_403_FORBIDDEN,
            )

        release = (
            NodeRegistryRelease.objects.select_related("package").filter(id=release_id).first()
        )
        if release is None:
            return error_response(
                code="NOT_FOUND",
                message=f"Release '{release_id}' not found.",
                status=status.HTTP_404_NOT_FOUND,
            )

        decision = serializer.validated_data["decision"]
        runtime_mode = settings.FORGEGRAPH_RUNTIME_MODE
        if decision == "approved":
            installable, delivery = is_release_installable_in_runtime_mode(release, runtime_mode)
            if not installable:
                record_audit_log(
                    actor=user,
                    tenant_id=get_tenant_id_for_user(user),
                    action="marketplace.release_review_blocked",
                    resource_type="node_release",
                    resource_id=str(release.id),
                    metadata={
                        "package_slug": release.package.slug,
                        "decision": decision,
                        "runtime_mode": runtime_mode,
                        "delivery_state": delivery["state"],
                        "delivery_reason": delivery["reason"],
                    },
                )
                return error_response(
                    code="POLICY_DENIED",
                    message=(
                        f"Release '{release.package.slug}@{release.version}' cannot be approved in "
                        f"{runtime_mode} mode: {delivery['reason']}."
                    ),
                    status=status.HTTP_409_CONFLICT,
                )

        release.status = decision
        release.reviewed_by = user
        release.reviewed_at = timezone.now()
        release.review_notes = serializer.validated_data.get("review_notes") or release.review_notes
        release.save(
            update_fields=["status", "reviewed_by", "reviewed_at", "review_notes", "updated_at"]
        )

        record_audit_log(
            actor=user,
            tenant_id=get_tenant_id_for_user(user),
            action="marketplace.release_reviewed",
            resource_type="node_release",
            resource_id=str(release.id),
            metadata={
                "package_slug": release.package.slug,
                "decision": decision,
            },
        )

        return success_response(
            {
                "id": str(release.id),
                "status": release.status,
                "review_notes": release.review_notes,
                "reviewed_at": release.reviewed_at,
            }
        )


class MarketplaceRuntimeManifestView(APIView):
    permission_classes = [AllowAny]

    def get(self, request: Request) -> Response:
        timestamp_header = request.headers.get("X-Forgegraph-Timestamp", "")
        signature_header = request.headers.get("X-Forgegraph-Signature", "")
        ok, reason = s2s.verify_request(
            timestamp_ms=timestamp_header,
            signature=signature_header,
            body=request.body or b"",
        )
        if not ok:
            return Response({"detail": "Unauthorized", "reason": reason}, status=401)

        tenant_id = (request.query_params.get("tenant_id") or "").strip()
        if not tenant_id:
            return error_response(
                code="VALIDATION_ERROR",
                message="tenant_id is required",
                status=status.HTTP_400_BAD_REQUEST,
            )

        company_id = (request.query_params.get("company_id") or "").strip() or None
        payload = build_runtime_manifest_payload(
            tenant_id,
            settings.FORGEGRAPH_RUNTIME_MODE,
            company_id=company_id,
        )
        checksum = str(payload["checksum"])
        if_none_match = (request.headers.get("If-None-Match") or "").strip().strip('"')
        if if_none_match == checksum:
            response = Response(status=status.HTTP_304_NOT_MODIFIED)
            response["ETag"] = checksum
            response["Cache-Control"] = "private, max-age=30"
            return response

        response = success_response(payload)
        response["ETag"] = checksum
        response["Cache-Control"] = "private, max-age=30"
        return response


class MarketplaceRuntimeManifestPreviewView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        if not has_min_role(user, "admin"):
            return error_response(
                code="FORBIDDEN",
                message="You don't have permission to view runtime manifest delivery.",
                status=status.HTTP_403_FORBIDDEN,
            )

        org = user.default_organization
        if org is None:
            return success_response(
                {
                    "tenant_id": "",
                    "manifest_version": 2,
                    "checksum": "",
                    "generated_at": timezone.now().isoformat(),
                    "packages": [],
                    "tools": [],
                }
            )

        company_id = (request.query_params.get("company_id") or "").strip() or None
        return success_response(
            build_runtime_manifest_payload(
                org.id,
                settings.FORGEGRAPH_RUNTIME_MODE,
                company_id=company_id,
            )
        )
