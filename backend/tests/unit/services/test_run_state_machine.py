from __future__ import annotations

import pytest

from application.services.run_state_machine import (
    RUN_STATUS_TRANSITIONS,
    RunTransitionConflict,
    apply_run_status_transition,
    assert_run_transition_allowed,
)
from infrastructure.orm.models import Run


@pytest.mark.parametrize(
    ("current", "requested"),
    [
        (current, requested)
        for current, requested_statuses in RUN_STATUS_TRANSITIONS.items()
        for requested in sorted(requested_statuses)
    ],
)
def test_run_state_machine_allows_declared_transitions(current: str, requested: str) -> None:
    assert_run_transition_allowed(current, requested)


@pytest.mark.parametrize(
    ("current", "requested"),
    [
        ("pending", "succeeded"),
        ("paused", "running"),
        ("resume_requested", "paused"),
        ("succeeded", "running"),
        ("failed", "pending"),
        ("canceled", "running"),
    ],
)
def test_run_state_machine_rejects_invalid_transitions(current: str, requested: str) -> None:
    with pytest.raises(RunTransitionConflict) as exc_info:
        assert_run_transition_allowed(current, requested)

    payload = exc_info.value.as_payload()
    assert payload["decision"] == "retry_required"
    assert payload["conflict_code"] == "409_RUN_STATE_TRANSITION_CONFLICT"
    assert payload["current_status"] == current
    assert payload["requested_status"] == requested


def test_run_state_machine_is_the_only_mutator_for_run_status() -> None:
    run = Run(status="pending")

    result = apply_run_status_transition(run, "running")

    assert run.status == "running"
    assert result.changed is True
    assert result.update_fields == ["status"]


def test_backend_requeue_requires_explicit_state_machine_exception() -> None:
    with pytest.raises(RunTransitionConflict):
        assert_run_transition_allowed("running", "pending")

    assert_run_transition_allowed("running", "pending", allow_backend_requeue=True)
