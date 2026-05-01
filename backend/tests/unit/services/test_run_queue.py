from __future__ import annotations

from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone

from application.services.run_queue import (
    RunQueueSettings,
    claim_next_entry,
    enqueue_run,
    get_run_queue_worker_health,
    mark_failed,
    record_run_queue_worker_heartbeat,
    release_stale_entries,
)
from infrastructure.orm.models import Graph, GraphVersion, Run

pytestmark = pytest.mark.django_db


def _create_run(user, *, status: str = "pending") -> Run:
    graph = Graph.objects.create(owner=user, name=f"Queue Graph {status}")
    version = GraphVersion.objects.create(
        graph=graph,
        version=1,
        graph_json={"nodes": [], "edges": []},
    )
    return Run.objects.create(owner=user, graph_version=version, status=status)


def test_claim_next_entry_defers_when_tenant_is_at_capacity(user) -> None:
    _create_run(user, status="running")
    queued_run = _create_run(user, status="pending")
    entry = enqueue_run(queued_run, tenant_id=str(user.default_organization_id))

    now = timezone.now()
    claimed = claim_next_entry(
        worker_id="worker-1",
        settings_override=RunQueueSettings(
            max_per_tenant=1,
            lock_timeout_seconds=60,
            retry_delay_seconds=45,
        ),
    )

    assert claimed is None

    entry.refresh_from_db()
    assert entry.status == "pending"
    assert entry.available_at >= now + timedelta(seconds=45)


def test_mark_failed_requeues_retryable_entries_until_attempts_are_exhausted(user) -> None:
    queued_run = _create_run(user, status="pending")
    enqueue_run(
        queued_run,
        tenant_id=str(user.default_organization_id),
        max_attempts=2,
    )

    settings = RunQueueSettings(
        max_per_tenant=5,
        lock_timeout_seconds=60,
        retry_delay_seconds=0,
    )
    first_claim = claim_next_entry(worker_id="worker-1", settings_override=settings)
    assert first_claim is not None
    assert first_claim.attempts == 1

    mark_failed(
        first_claim,
        error_message="temporary upstream failure",
        retryable=True,
        settings_override=settings,
    )
    first_claim.refresh_from_db()
    assert first_claim.status == "pending"
    assert first_claim.last_error == "temporary upstream failure"

    second_claim = claim_next_entry(worker_id="worker-2", settings_override=settings)
    assert second_claim is not None
    assert second_claim.attempts == 2

    mark_failed(
        second_claim, error_message="still failing", retryable=True, settings_override=settings
    )
    second_claim.refresh_from_db()
    assert second_claim.status == "failed"
    assert second_claim.last_error == "still failing"


def test_release_stale_entries_returns_processing_runs_to_pending(user) -> None:
    queued_run = _create_run(user, status="pending")
    entry = enqueue_run(queued_run, tenant_id=str(user.default_organization_id))
    entry.status = "processing"
    entry.locked_by = "worker-1"
    entry.locked_at = timezone.now() - timedelta(minutes=10)
    entry.save(update_fields=["status", "locked_by", "locked_at"])

    released = release_stale_entries(lock_timeout_seconds=60)

    assert released == 1

    entry.refresh_from_db()
    assert entry.status == "pending"
    assert entry.locked_at is None
    assert entry.locked_by == ""


def test_claim_next_entry_defers_then_recovers_after_tenant_capacity_frees(user) -> None:
    active_run = _create_run(user, status="running")
    queued_run = _create_run(user, status="pending")
    entry = enqueue_run(queued_run, tenant_id=str(user.default_organization_id))
    settings = RunQueueSettings(
        max_per_tenant=1,
        lock_timeout_seconds=60,
        retry_delay_seconds=0,
    )

    claimed = claim_next_entry(worker_id="worker-1", settings_override=settings)
    assert claimed is None

    entry.refresh_from_db()
    assert entry.status == "pending"

    active_run.status = "succeeded"
    active_run.save(update_fields=["status"])

    claimed = claim_next_entry(worker_id="worker-2", settings_override=settings)

    assert claimed is not None
    assert claimed.id == entry.id
    assert claimed.status == "processing"
    assert claimed.locked_by == "worker-2"


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "run-queue-heartbeat",
        }
    },
    RUN_QUEUE_WORKER_HEARTBEAT_TTL_SECONDS=60,
)
def test_run_queue_worker_heartbeat_reports_active_worker() -> None:
    record_run_queue_worker_heartbeat("worker-a")
    health = get_run_queue_worker_health()

    assert health.active is True
    assert health.worker_id == "worker-a"
    assert health.last_seen_at is not None
