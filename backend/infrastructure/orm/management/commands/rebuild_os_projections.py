from __future__ import annotations

from typing import Any
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError

from application.services.os_projection_rebuild import rebuild_os_projections_for_organization
from infrastructure.orm.models import Organization


class Command(BaseCommand):
    help = "Rebuild backend-owned OS read models from domain events."

    def add_arguments(self, parser: Any) -> None:
        scope = parser.add_mutually_exclusive_group(required=True)
        scope.add_argument("--organization-id", type=str, default="")
        scope.add_argument("--all", action="store_true", dest="all_organizations")
        parser.add_argument("--batch-size", type=int, default=100)

    def handle(self, *args: Any, **options: Any) -> None:
        batch_size = max(int(options.get("batch_size") or 1), 1)
        organizations = self._organizations(options)
        for organization in organizations:
            result = rebuild_os_projections_for_organization(
                organization,
                batch_size=batch_size,
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Rebuilt OS projections for {result.organization_id}: "
                    f"backfilled={result.backfilled_events}, replayed={result.replayed_events}, "
                    f"duration={result.duration_seconds:.3f}s, counts={result.read_model_counts}"
                )
            )

    def _organizations(self, options: dict[str, Any]) -> list[Organization]:
        if bool(options.get("all_organizations")):
            return list(Organization.objects.order_by("id"))
        organization_id = str(options.get("organization_id") or "").strip()
        if not organization_id:
            raise CommandError("--organization-id or --all is required.")
        organization = Organization.objects.filter(id=UUID(organization_id)).first()
        if organization is None:
            raise CommandError(f"Organization not found: {organization_id}")
        return [organization]
