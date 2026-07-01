import pytest
from django.test import override_settings

from application.services.backend_watchdog import evaluate_backend_watchdog
from application.services.metrics import record_api_request
from infrastructure.orm.models import RunQueueEntry

pytestmark = pytest.mark.django_db


@override_settings(
    BACKEND_WATCHDOG_ENABLED=True,
    BACKEND_WATCHDOG_REQUEST_TIMEOUTS_PER_MINUTE=1,
    BACKEND_WATCHDOG_QUEUE_BACKLOG_THRESHOLD=1000,
)
def test_backend_watchdog_triggers_on_timeout_like_request_rate():
    record_api_request(
        status_code=200,
        duration_ms=6000,
        timeout_like=True,
        timeout_threshold_ms=5000,
    )

    snapshot = evaluate_backend_watchdog()

    assert snapshot.healthy is False
    assert "request_timeout_rate" in snapshot.triggers
    assert snapshot.recovery_action == "container_restart"


@override_settings(BACKEND_WATCHDOG_ENABLED=False)
def test_backend_watchdog_can_be_disabled():
    snapshot = evaluate_backend_watchdog()

    assert snapshot.enabled is False
    assert snapshot.healthy is True
    assert snapshot.triggers == []


@override_settings(
    BACKEND_WATCHDOG_ENABLED=True,
    BACKEND_WATCHDOG_REQUEST_TIMEOUTS_PER_MINUTE=1000,
    BACKEND_WATCHDOG_QUEUE_BACKLOG_THRESHOLD=1000,
)
def test_backend_watchdog_errors_mark_health_unhealthy(monkeypatch):
    def fail_count(_self: object) -> int:
        raise RuntimeError("postgres probe failed")

    probe_type = type("Probe", (), {"count": fail_count})
    monkeypatch.setattr(RunQueueEntry.objects, "filter", lambda **_kwargs: probe_type())

    snapshot = evaluate_backend_watchdog()

    assert snapshot.healthy is False
    assert snapshot.triggers == ["watchdog_probe_error"]
    assert "postgres probe failed" in snapshot.errors
