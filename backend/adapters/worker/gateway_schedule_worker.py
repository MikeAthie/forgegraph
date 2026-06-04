from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar, cast

from adapters.worker.celery_app import celery_app
from application.services.gateway_schedules import run_due_schedules

F = TypeVar("F", bound=Callable[..., Any])
celery_task = cast(Callable[..., Callable[[F], F]], celery_app.task)


@celery_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def run_gateway_due_schedules(self: Any) -> dict[str, Any]:
    results = run_due_schedules()
    return {
        "processed": len(results),
        "runs": [result.as_dict() for result in results],
    }
