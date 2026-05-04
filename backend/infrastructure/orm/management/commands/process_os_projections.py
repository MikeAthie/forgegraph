from __future__ import annotations

import time
from typing import Any
from uuid import UUID

from django.core.management.base import BaseCommand
from django.db.models import QuerySet
from django.utils import timezone

from application.services.metrics import record_service_metric_sample
from application.services.os_projections import (
    projection_metadata,
    refresh_phase1_projections_for_organization,
)
from infrastructure.orm.models import Organization


class Command(BaseCommand):
    help = "Refresh backend-owned OS read models outside user request paths."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--organization-id",
            type=str,
            default="",
            help="Refresh projections for a single organization.",
        )
        parser.add_argument(
            "--once",
            action="store_true",
            help="Run one projection pass and exit.",
        )
        parser.add_argument(
            "--sleep",
            type=float,
            default=5.0,
            help="Seconds to sleep between projection passes when not using --once.",
        )
        parser.add_argument(
            "--max-organizations",
            type=int,
            default=0,
            help="Maximum organizations to refresh per pass. Defaults to all.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        organization_id = str(options.get("organization_id") or "").strip()
        run_once = bool(options.get("once"))
        sleep_seconds = max(float(options.get("sleep") or 0), 0.1)
        max_organizations = max(int(options.get("max_organizations") or 0), 0)

        self.stdout.write(self.style.SUCCESS("OS projection worker starting."))

        while True:
            refreshed = self._refresh_once(
                organization_id=organization_id,
                max_organizations=max_organizations,
            )
            self.stdout.write(
                self.style.SUCCESS(f"Refreshed OS projections for {refreshed} organization(s).")
            )

            if run_once:
                return
            time.sleep(sleep_seconds)

    def _refresh_once(
        self,
        *,
        organization_id: str = "",
        max_organizations: int = 0,
    ) -> int:
        organizations = self._organization_queryset(organization_id=organization_id)
        if max_organizations > 0:
            organizations = organizations[:max_organizations]

        refreshed = 0
        for organization in organizations.iterator():
            started_at = timezone.now()
            refresh_phase1_projections_for_organization(organization)
            metadata = projection_metadata(organization)
            refreshed += 1
            duration_ms = int((timezone.now() - started_at).total_seconds() * 1000)
            record_service_metric_sample(
                metric_name="os_projection_refresh_duration_ms",
                source="process_os_projections",
                value=duration_ms,
                unit="ms",
                organization_id=organization.id,
                dimensions={"organization_id": str(organization.id)},
            )
            lag_ms = metadata.get("projection_lag_ms")
            if isinstance(lag_ms, (int, float)):
                record_service_metric_sample(
                    metric_name="os_projection_lag_ms",
                    source="process_os_projections",
                    value=float(lag_ms),
                    unit="ms",
                    organization_id=organization.id,
                    dimensions={"organization_id": str(organization.id)},
                )
        return refreshed

    def _organization_queryset(self, *, organization_id: str = "") -> QuerySet[Organization]:
        queryset = Organization.objects.order_by("-created_at", "-id")
        if organization_id:
            queryset = queryset.filter(id=UUID(organization_id))
        return queryset
