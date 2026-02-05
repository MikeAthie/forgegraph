"""Marketplace API views."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from django.db import models
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
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
from application.services.rbac import has_min_role
from application.services.tenancy import get_tenant_id_for_user
from infrastructure.orm.models import (
    NodePackageInstallation,
    NodeRegistryPackage,
    NodeRegistryRelease,
    User,
)


def _serialize_release(release: NodeRegistryRelease | None) -> dict[str, Any] | None:
    if release is None:
        return None
    return {
        "id": str(release.id),
        "version": release.version,
        "changelog": release.changelog,
        "status": release.status,
        "execution_node_type": release.execution_node_type,
        "ui_schema": release.ui_schema,
        "config_schema": release.config_schema,
        "config_defaults": release.config_defaults,
        "created_at": release.created_at,
    }


def _serialize_package(
    package: NodeRegistryPackage,
    *,
    latest_release: NodeRegistryRelease | None,
    installed_release: NodeRegistryRelease | None = None,
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

        install, _ = NodePackageInstallation.objects.update_or_create(
            organization=org,
            package=package,
            defaults={
                "release": release,
                "installed_by": user,
                "is_active": True,
                "install_metadata": {"source": "marketplace"},
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
                "execution_node_type": release.execution_node_type,
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
            execution_node_type=payload["execution_node_type"],
            ui_schema=payload.get("ui_schema") or {},
            config_schema=payload.get("config_schema") or {},
            config_defaults=payload.get("config_defaults") or {},
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
        release.status = decision
        release.reviewed_by = user
        release.reviewed_at = timezone.now()
        release.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])

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
                "reviewed_at": release.reviewed_at,
            }
        )
