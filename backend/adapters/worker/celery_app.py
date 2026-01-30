from __future__ import annotations

import os

from celery import Celery
from celery.schedules import crontab


def create_celery_app() -> Celery:
    broker_url = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
    backend_url = os.getenv("CELERY_RESULT_BACKEND", broker_url)

    app = Celery("forgegraph", broker=broker_url, backend=backend_url)
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        beat_schedule={
            "memory-gc-daily": {
                "task": "adapters.worker.gc_worker.run_memory_gc",
                "schedule": crontab(hour=3, minute=0),
            },
        },
    )
    app.autodiscover_tasks(["adapters.worker"])
    return app


celery_app = create_celery_app()
