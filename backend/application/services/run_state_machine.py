from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.utils import timezone

from infrastructure.orm.models import GraphVersion, Organization, Run, User

RUN_STATUSES = {
    "pending",
    "running",
    "paused",
    "resume_requested",
    "succeeded",
    "failed",
    "canceled",
}
TERMINAL_RUN_STATUSES = {"succeeded", "failed", "canceled"}
RUN_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"pending", "running", "failed", "canceled"},
    "running": {"running", "paused", "resume_requested", "succeeded", "failed", "canceled"},
    "paused": {"paused", "resume_requested", "failed", "canceled"},
    "resume_requested": {"resume_requested", "running", "failed", "canceled"},
    "succeeded": {"succeeded"},
    "failed": {"failed"},
    "canceled": {"canceled"},
}


@dataclass(frozen=True)
class RunTransitionResult:
    from_status: str
    to_status: str
    changed: bool
    update_fields: list[str]


class RunTransitionConflict(ValueError):
    def __init__(self, *, current_status: str, requested_status: str, reason: str = "") -> None:
        self.current_status = current_status
        self.requested_status = requested_status
        self.reason = (
            reason or f"invalid run status transition: {current_status} -> {requested_status}"
        )
        super().__init__(self.reason)

    def as_payload(self) -> dict[str, Any]:
        return {
            "decision": "retry_required",
            "reason": self.reason,
            "conflict_code": "409_RUN_STATE_TRANSITION_CONFLICT",
            "current_status": self.current_status,
            "requested_status": self.requested_status,
        }


def assert_run_transition_allowed(
    current_status: str,
    requested_status: str,
    *,
    allow_backend_requeue: bool = False,
) -> None:
    current = normalize_run_status(current_status)
    requested = normalize_run_status(requested_status)
    if (
        allow_backend_requeue
        and requested == "pending"
        and current in {"running", "resume_requested"}
    ):
        return
    if requested not in RUN_STATUS_TRANSITIONS.get(current, {current}):
        raise RunTransitionConflict(current_status=current, requested_status=requested)


def apply_run_status_transition(
    run: Run,
    requested_status: str,
    *,
    allow_backend_requeue: bool = False,
) -> RunTransitionResult:
    current = normalize_run_status(run.status)
    requested = normalize_run_status(requested_status)
    assert_run_transition_allowed(
        current,
        requested,
        allow_backend_requeue=allow_backend_requeue,
    )
    changed = current != requested
    update_fields: list[str] = []
    if changed:
        run.status = requested
        update_fields.append("status")
    return RunTransitionResult(
        from_status=current,
        to_status=requested,
        changed=changed,
        update_fields=update_fields,
    )


def normalize_run_status(status: object) -> str:
    value = str(status or "").strip().lower()
    if value not in RUN_STATUSES:
        raise RunTransitionConflict(
            current_status=value or "unknown",
            requested_status=value or "unknown",
            reason=f"unsupported run status: {value or 'empty'}",
        )
    return value


def create_backend_owned_run(
    *,
    owner: User,
    organization: Organization | None,
    graph_version: GraphVersion,
    input_json: dict[str, Any],
    dispatch_graph_json: dict[str, Any],
    status: str = "pending",
    started_at: datetime | None = None,
    output_json: dict[str, Any] | None = None,
    error_message: str = "",
) -> Run:
    """Create a durable run from the approved backend runtime write boundary."""

    return Run.objects.create(
        owner=owner,
        organization=organization,
        graph_version=graph_version,
        status=normalize_run_status(status),
        started_at=started_at or timezone.now(),
        input_json=dict(input_json),
        dispatch_graph_json=dict(dispatch_graph_json),
        output_json=output_json,
        error_message=error_message,
    )


def merge_run_input_json(run: Run, values: dict[str, Any]) -> Run:
    """Persist backend-owned additions to a run input payload."""

    input_json = dict(run.input_json or {})
    input_json.update(values)
    run.input_json = input_json
    run.save(update_fields=["input_json"])
    return run
