from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any, TypeVar, cast

from adapters.worker.celery_app import celery_app
from application.services.retention import DataRetentionService

F = TypeVar("F", bound=Callable[..., Any])
celery_task = cast(Callable[..., Callable[[F], F]], celery_app.task)


def _parse_tenant_ids(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


@celery_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def run_retention_cleanup(self: Any) -> dict[str, Any]:
    dry_run = os.getenv("RETENTION_DRY_RUN", "false").lower() in {"1", "true", "yes"}
    tenant_ids = _parse_tenant_ids(os.getenv("RETENTION_TENANT_IDS"))
    service = DataRetentionService()
    return service.cleanup_all(tenant_ids=tenant_ids or None, dry_run=dry_run)
