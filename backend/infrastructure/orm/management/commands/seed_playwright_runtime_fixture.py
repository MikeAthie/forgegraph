"""
Seed a deterministic runtime marketplace fixture for Playwright E2E.

This command creates:
- a fixed owner user
- a fixed organization / tenant id
- an approved runtime marketplace package release

It intentionally does not install the package. Browser E2E should prove the
real install -> runtime delivery -> execute path through the product UI.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from infrastructure.orm.models import (
    NodePackageInstallation,
    NodeRegistryPackage,
    NodeRegistryRelease,
    Organization,
    OrganizationMembership,
    User,
)

DEFAULT_EMAIL = "playwright-runtime@example.com"
DEFAULT_PASSWORD = "ForgeGraphTest!12345"
DEFAULT_TENANT_ID = "00000000-0000-0000-0000-00000000e2e1"
DEFAULT_TENANT_NAME = "Playwright Runtime Workspace"
DEFAULT_PACKAGE_SLUG = "playwright-runtime-health-check"
DEFAULT_PACKAGE_NAME = "Playwright Runtime Health Check"
DEFAULT_TOOL_NAME = "playwright_runtime_health_check"
DEFAULT_RUNTIME_URL = "http://127.0.0.1:8002/health"


class Command(BaseCommand):
    help = "Seed a deterministic runtime marketplace fixture for Playwright."

    def add_arguments(self, parser):
        parser.add_argument("--email", default=DEFAULT_EMAIL)
        parser.add_argument("--password", default=DEFAULT_PASSWORD)
        parser.add_argument("--tenant-id", default=DEFAULT_TENANT_ID)
        parser.add_argument("--tenant-name", default=DEFAULT_TENANT_NAME)
        parser.add_argument("--package-slug", default=DEFAULT_PACKAGE_SLUG)
        parser.add_argument("--package-name", default=DEFAULT_PACKAGE_NAME)
        parser.add_argument("--tool-name", default=DEFAULT_TOOL_NAME)
        parser.add_argument("--runtime-url", default=DEFAULT_RUNTIME_URL)

    def handle(self, *args, **options):
        email = str(options["email"]).strip().lower()
        password = str(options["password"])
        tenant_id = str(options["tenant_id"]).strip()
        tenant_name = str(options["tenant_name"]).strip() or DEFAULT_TENANT_NAME
        package_slug = str(options["package_slug"]).strip()
        package_name = str(options["package_name"]).strip() or DEFAULT_PACKAGE_NAME
        tool_name = str(options["tool_name"]).strip() or DEFAULT_TOOL_NAME
        runtime_url = str(options["runtime_url"]).strip() or DEFAULT_RUNTIME_URL

        with transaction.atomic():
            user, created = User.objects.get_or_create(
                email=email,
                defaults={"is_active": True},
            )
            if created or not user.check_password(password):
                user.set_password(password)
                user.save(update_fields=["password"])

            organization, _ = Organization.objects.update_or_create(
                id=tenant_id,
                defaults={"name": tenant_name},
            )

            OrganizationMembership.objects.filter(user=user, is_default=True).exclude(
                organization=organization
            ).update(is_default=False)

            membership, _ = OrganizationMembership.objects.update_or_create(
                organization=organization,
                user=user,
                defaults={"role": "owner", "is_default": True},
            )
            if membership.role != "owner" or not membership.is_default:
                membership.role = "owner"
                membership.is_default = True
                membership.save(update_fields=["role", "is_default", "updated_at"])

            if user.default_organization_id != organization.id:
                user.default_organization = organization
                user.save(update_fields=["default_organization"])

            package, _ = NodeRegistryPackage.objects.update_or_create(
                slug=package_slug,
                defaults={
                    "name": package_name,
                    "summary": "Deterministic runtime tool fixture for browser E2E.",
                    "category": "developer",
                    "icon": "sparkles",
                    "owner_organization": organization,
                    "created_by": user,
                    "is_active": True,
                },
            )

            release, _ = NodeRegistryRelease.objects.update_or_create(
                package=package,
                version="1.0.0",
                defaults={
                    "status": "approved",
                    "package_kind": "runtime_tool",
                    "execution_node_type": "tool",
                    "ui_schema": {
                        "label": package_name,
                        "description": "Browser E2E runtime health check tool",
                        "category": "integration",
                    },
                    "config_schema": {"type": "object"},
                    "config_defaults": {"tool": tool_name},
                    "runtime_manifest": {
                        "name": tool_name,
                        "version": "1.0.0",
                        "kind": "http",
                        "description": "Calls the backend health endpoint for E2E proof.",
                        "http": {
                            "url": runtime_url,
                            "method": "GET",
                        },
                    },
                    "manifest_version": 1,
                    "cloud_allowed": True,
                    "review_notes": "Auto-approved Playwright runtime fixture.",
                    "reviewed_by": user,
                    "reviewed_at": timezone.now(),
                    "created_by": user,
                },
            )

            NodePackageInstallation.objects.filter(
                organization=organization,
                package=package,
            ).delete()

        self.stdout.write(
            self.style.SUCCESS(
                "Seeded Playwright runtime fixture "
                f"(user={email}, tenant_id={tenant_id}, package={package_slug}, release={release.version})"
            )
        )
