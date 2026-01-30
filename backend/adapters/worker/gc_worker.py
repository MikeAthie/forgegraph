from __future__ import annotations

import os

from adapters.worker.celery_app import celery_app
from application.services.memory_gc import MemoryGCService


def _parse_tenant_ids(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def run_memory_gc(self) -> dict[str, int | bool]:
    retention_days = int(os.getenv("MEMORY_RETENTION_DAYS", "30"))
    reindex = os.getenv("MEMORY_GC_REINDEX", "false").lower() in {"1", "true", "yes"}
    tenant_ids = _parse_tenant_ids(os.getenv("MEMORY_GC_TENANT_IDS"))
    prune_missing_users = os.getenv("MEMORY_GC_PRUNE_MISSING_USERS", "false").lower() in {
        "1",
        "true",
        "yes",
    }

    service = MemoryGCService()
    return service.cleanup(
        retention_days=retention_days,
        tenant_ids_to_delete=tenant_ids,
        prune_missing_users=prune_missing_users,
        reindex=reindex,
    )
