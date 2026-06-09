"""Backend-owned gateway automation schedule materialization."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from adapters.api.runs.responses import _attach_operation_context_pack
from application.services.domain_event_outbox import sanitize_outbox_payload
from application.services.run_preparation import (
    PromptTemplateResolutionError,
    SubgraphResolutionError,
    prepare_graph_for_engine,
)
from application.services.run_queue import enqueue_run
from application.services.trace_context import ensure_trace_context
from infrastructure.orm.models import (
    GatewayAutomationSchedule,
    GatewayConnection,
    GraphVersion,
    Run,
    User,
)


class GatewayScheduleError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class GatewayScheduleRunResult:
    schedule_id: str
    run_id: str
    fire_key: str
    next_run_at: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "schedule_id": self.schedule_id,
            "run_id": self.run_id,
            "fire_key": self.fire_key,
            "next_run_at": self.next_run_at,
        }


def schedule_payload(schedule: GatewayAutomationSchedule) -> dict[str, Any]:
    return {
        "id": str(schedule.id),
        "organization_id": str(schedule.organization_id),
        "graph_version_id": str(schedule.graph_version_id),
        "connection_id": str(schedule.connection_id) if schedule.connection_id else None,
        "last_materialized_run_id": (
            str(schedule.last_materialized_run_id) if schedule.last_materialized_run_id else None
        ),
        "platform": schedule.platform,
        "provider": schedule.provider,
        "name": schedule.name,
        "status": schedule.status,
        "schedule_type": schedule.schedule_type,
        "schedule": sanitize_outbox_payload(schedule.schedule_json or {}),
        "timezone": schedule.timezone,
        "input_template": sanitize_outbox_payload(schedule.input_template_json or {}),
        "next_run_at": schedule.next_run_at.isoformat() if schedule.next_run_at else None,
        "last_run_at": schedule.last_run_at.isoformat() if schedule.last_run_at else None,
        "last_fire_key": schedule.last_fire_key,
        "last_error_code": schedule.last_error_code,
        "last_error_message": schedule.last_error_message,
        "created_at": schedule.created_at.isoformat(),
        "updated_at": schedule.updated_at.isoformat(),
    }


def create_schedule(
    *,
    graph_version: GraphVersion,
    user: User,
    platform: str,
    provider: str,
    name: str,
    schedule_type: str,
    schedule_json: dict[str, Any],
    input_template_json: dict[str, Any],
    connection: GatewayConnection | None = None,
    timezone_name: str = "UTC",
    status: str = "enabled",
) -> GatewayAutomationSchedule:
    _validate_schedule_type(schedule_type)
    organization = graph_version.graph.organization or user.default_organization
    if organization is None:
        raise GatewayScheduleError(
            "organization_required", "Gateway schedules require an organization."
        )
    now = timezone.now()
    next_run_at = compute_next_run_at(
        schedule_type=schedule_type,
        schedule_json=schedule_json,
        timezone_name=timezone_name,
        base_time=now,
        previous_run_at=None,
    )
    schedule = GatewayAutomationSchedule.objects.create(
        organization=organization,
        graph_version=graph_version,
        connection=connection,
        created_by=user,
        platform=str(platform or "").strip()[:64],
        provider=str(provider or "").strip()[:64],
        name=str(name or "").strip()[:160],
        status=status if status in {"enabled", "disabled"} else "enabled",
        schedule_type=schedule_type,
        schedule_json=sanitize_outbox_payload(schedule_json),
        timezone=timezone_name or "UTC",
        input_template_json=sanitize_outbox_payload(input_template_json),
        next_run_at=next_run_at if status == "enabled" else None,
    )
    return schedule


def update_schedule(
    schedule: GatewayAutomationSchedule,
    *,
    status: str | None = None,
    schedule_json: dict[str, Any] | None = None,
    input_template_json: dict[str, Any] | None = None,
    timezone_name: str | None = None,
) -> GatewayAutomationSchedule:
    update_fields: list[str] = []
    if status is not None:
        schedule.status = status if status in {"enabled", "disabled", "error"} else "error"
        update_fields.append("status")
    if schedule_json is not None:
        schedule.schedule_json = sanitize_outbox_payload(schedule_json)
        schedule.next_run_at = compute_next_run_at(
            schedule_type=schedule.schedule_type,
            schedule_json=schedule.schedule_json,
            timezone_name=timezone_name or schedule.timezone,
            base_time=timezone.now(),
            previous_run_at=schedule.last_run_at,
        )
        update_fields.extend(["schedule_json", "next_run_at"])
    if input_template_json is not None:
        schedule.input_template_json = sanitize_outbox_payload(input_template_json)
        update_fields.append("input_template_json")
    if timezone_name is not None:
        schedule.timezone = timezone_name or "UTC"
        update_fields.append("timezone")
    if schedule.status != "enabled":
        schedule.next_run_at = None
        update_fields.append("next_run_at")
    if update_fields:
        schedule.save(update_fields=sorted({*update_fields, "updated_at"}))
    return schedule


def run_due_schedules(
    *, limit: int = 50, now: datetime | None = None
) -> list[GatewayScheduleRunResult]:
    effective_now = now or timezone.now()
    results: list[GatewayScheduleRunResult] = []
    schedule_ids: list[UUID] = list(
        GatewayAutomationSchedule.objects.filter(
            status="enabled",
            next_run_at__isnull=False,
            next_run_at__lte=effective_now,
        )
        .order_by("next_run_at", "created_at")
        .values_list("id", flat=True)[:limit]
    )
    for schedule_id in schedule_ids:
        result = run_schedule(schedule_id=schedule_id, fire_time=effective_now)
        if result is not None:
            results.append(result)
    return results


def run_schedule(
    *,
    schedule_id: UUID | str,
    fire_time: datetime | None = None,
    force: bool = False,
) -> GatewayScheduleRunResult | None:
    effective_fire_time = fire_time or timezone.now()
    with transaction.atomic():
        schedule = (
            GatewayAutomationSchedule.objects.select_for_update(of=("self",))
            .select_related(
                "graph_version__graph__owner", "graph_version__graph__organization", "connection"
            )
            .get(id=schedule_id)
        )
        if schedule.status != "enabled" and not force:
            return None
        if schedule.next_run_at and schedule.next_run_at > effective_fire_time and not force:
            return None
        fire_key = _fire_key(schedule, effective_fire_time)
        if schedule.last_fire_key == fire_key and schedule.last_materialized_run_id:
            return GatewayScheduleRunResult(
                schedule_id=str(schedule.id),
                run_id=str(schedule.last_materialized_run_id),
                fire_key=fire_key,
                next_run_at=schedule.next_run_at.isoformat() if schedule.next_run_at else None,
            )
        try:
            run = _materialize_schedule_run(
                schedule=schedule, fire_key=fire_key, fire_time=effective_fire_time
            )
        except Exception as exc:
            schedule.status = "error"
            schedule.last_error_code = "schedule_materialization_failed"
            schedule.last_error_message = str(exc.__class__.__name__)[:500]
            schedule.last_error_json = {"error_class": exc.__class__.__name__}
            schedule.save(
                update_fields=[
                    "status",
                    "last_error_code",
                    "last_error_message",
                    "last_error_json",
                    "updated_at",
                ]
            )
            raise
        next_run_at = compute_next_run_at(
            schedule_type=schedule.schedule_type,
            schedule_json=schedule.schedule_json,
            timezone_name=schedule.timezone,
            base_time=effective_fire_time,
            previous_run_at=effective_fire_time,
        )
        schedule.last_run_at = effective_fire_time
        schedule.last_fire_key = fire_key
        schedule.last_materialized_run = run
        schedule.next_run_at = next_run_at
        schedule.last_error_code = ""
        schedule.last_error_message = ""
        schedule.last_error_json = {}
        update_fields = [
            "last_run_at",
            "last_fire_key",
            "last_materialized_run",
            "next_run_at",
            "last_error_code",
            "last_error_message",
            "last_error_json",
            "updated_at",
        ]
        if schedule.schedule_type == "once":
            schedule.status = "disabled"
            update_fields.append("status")
        schedule.save(update_fields=update_fields)
        enqueue_run(run, tenant_id=str(schedule.organization_id))
        return GatewayScheduleRunResult(
            schedule_id=str(schedule.id),
            run_id=str(run.id),
            fire_key=fire_key,
            next_run_at=next_run_at.isoformat() if next_run_at else None,
        )


def compute_next_run_at(
    *,
    schedule_type: str,
    schedule_json: dict[str, Any],
    timezone_name: str,
    base_time: datetime,
    previous_run_at: datetime | None,
) -> datetime | None:
    _validate_schedule_type(schedule_type)
    if timezone.is_naive(base_time):
        base_time = timezone.make_aware(base_time, UTC)
    if schedule_type == "once":
        if previous_run_at is not None:
            return None
        return _parse_run_at(schedule_json.get("run_at") or schedule_json.get("at"))
    if schedule_type == "interval":
        seconds = int(schedule_json.get("seconds") or schedule_json.get("interval_seconds") or 0)
        if seconds <= 0:
            raise GatewayScheduleError(
                "invalid_interval", "Interval schedules require positive seconds."
            )
        return base_time + timedelta(seconds=seconds)
    return _next_cron_time(
        schedule_json=schedule_json, timezone_name=timezone_name, base_time=base_time
    )


def _materialize_schedule_run(
    *,
    schedule: GatewayAutomationSchedule,
    fire_key: str,
    fire_time: datetime,
) -> Run:
    graph_version = schedule.graph_version
    owner = graph_version.graph.owner
    trace_context = ensure_trace_context()
    input_json = {
        **(schedule.input_template_json if isinstance(schedule.input_template_json, dict) else {}),
        "gateway": {
            **(
                schedule.input_template_json.get("gateway", {})
                if isinstance(schedule.input_template_json, dict)
                and isinstance(schedule.input_template_json.get("gateway"), dict)
                else {}
            ),
            "schedule_id": str(schedule.id),
            "schedule_name": schedule.name,
            "platform": schedule.platform,
            "provider": schedule.provider,
            "connection_id": str(schedule.connection_id or ""),
            "fire_key": fire_key,
            "fired_at": fire_time.isoformat(),
        },
    }
    try:
        prepared_graph = prepare_graph_for_engine(
            graph_version.graph_json,
            owner,
            company_id=graph_version.graph_id,
            traceparent=trace_context["traceparent"],
            tracestate=trace_context["tracestate"],
        )
    except (PromptTemplateResolutionError, SubgraphResolutionError, ValueError) as exc:
        raise GatewayScheduleError("graph_preparation_failed", str(exc)) from exc
    run = Run.objects.create(
        owner=owner,
        graph_version=graph_version,
        thread_id=None,
        status="pending",
        started_at=timezone.now(),
        ended_at=None,
        input_json=sanitize_outbox_payload(input_json),
        dispatch_graph_json=prepared_graph,
        output_json=None,
        error_message="",
        trace_id=trace_context["trace_id"],
    )
    outbound_graph = _attach_operation_context_pack(run, prepared_graph)
    if outbound_graph is not None:
        run.dispatch_graph_json = outbound_graph
        run.save(update_fields=["dispatch_graph_json"])
    return run


def _next_cron_time(
    *,
    schedule_json: dict[str, Any],
    timezone_name: str,
    base_time: datetime,
) -> datetime:
    minute = schedule_json.get("minute", "*")
    hour = schedule_json.get("hour", "*")
    tz = _zoneinfo(timezone_name)
    local_base = base_time.astimezone(tz).replace(second=0, microsecond=0) + timedelta(minutes=1)
    for offset in range(0, 366 * 24 * 60):
        candidate = local_base + timedelta(minutes=offset)
        if _matches_cron_field(candidate.minute, minute) and _matches_cron_field(
            candidate.hour, hour
        ):
            return candidate.astimezone(UTC)
    raise GatewayScheduleError("invalid_cron", "Could not compute next cron run within one year.")


def _matches_cron_field(value: int, raw: Any) -> bool:
    if raw in (None, "", "*"):
        return True
    try:
        return int(raw) == value
    except (TypeError, ValueError):
        return False


def _parse_run_at(raw: Any) -> datetime:
    parsed = parse_datetime(str(raw or ""))
    if parsed is None:
        raise GatewayScheduleError(
            "invalid_run_at", "Once schedules require a valid run_at datetime."
        )
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, UTC)
    return parsed


def _fire_key(schedule: GatewayAutomationSchedule, fire_time: datetime) -> str:
    return f"gateway_schedule:{schedule.id}:{fire_time.replace(microsecond=0).isoformat()}"[:255]


def _zoneinfo(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _validate_schedule_type(schedule_type: str) -> None:
    if schedule_type not in {"once", "interval", "cron"}:
        raise GatewayScheduleError("invalid_schedule_type", "Unsupported gateway schedule type.")
