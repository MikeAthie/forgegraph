from __future__ import annotations

import copy
import logging
import socket
import time
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import OperationalError, transaction
from django.utils import timezone

from adapters.gateways.grpc_engine_client import (
    EngineConnectionError,
    EngineExecutionError,
    GrpcEngineClient,
)
from adapters.ws.runs.broadcast import broadcast_run_updated
from application.services.company_archive import ContextPackService
from application.services.engine_selection import resolve_engine_callback_url, select_engine_target
from application.services.llm_access import (
    LLMAccessValidationError,
    engine_input_with_llm_access,
    engine_llm_access_from_graph,
)
from application.services.metrics import record_run_completed, record_run_started
from application.services.run_liveness import (
    reconcile_stale_runs,
    recovery_state_for_status,
    touch_run_liveness,
)
from application.services.run_preparation import (
    PromptTemplateResolutionError,
    SubgraphResolutionError,
    build_memory_config_json,
    prepare_graph_for_engine,
    validate_prompt_credentials,
)
from application.services.run_queue import (
    claim_next_entry,
    get_run_queue_settings,
    mark_completed,
    mark_failed,
    record_run_queue_worker_heartbeat,
    release_stale_entries,
)
from application.services.run_state_machine import (
    TERMINAL_RUN_STATUSES,
    apply_run_status_transition,
)
from application.services.task_lifecycle import (
    mark_run_tasks_terminal,
    record_retry_operation,
    transition_task_lifecycle,
)
from application.services.tenancy import get_tenant_id_for_user
from application.services.tool_executions import (
    ToolExecutionDispatchBlocked,
    prepare_tool_executions_for_dispatch,
)
from application.services.trace_context import ensure_trace_context
from infrastructure.orm.models import RunQueueEntry

logger = logging.getLogger(__name__)

_DEADLOCK_RETRY_ATTEMPTS = 3


def get_engine_client(
    callback_url: str = "",
    *,
    host: str | None = None,
    port: int | None = None,
) -> GrpcEngineClient:
    return GrpcEngineClient(
        host=host or settings.ENGINE_HOST,
        port=port or settings.ENGINE_PORT,
        callback_url=callback_url,
    )


def _run_has_context_pack(run: Any) -> bool:
    input_json = run.input_json if isinstance(run.input_json, dict) else {}
    if input_json.get("context_pack_id"):
        return True
    metadata = (
        run.dispatch_graph_json.get("metadata")
        if isinstance(run.dispatch_graph_json, dict)
        else None
    )
    return isinstance(metadata, dict) and bool(metadata.get("context_pack_id"))


def _is_deadlock(exc: OperationalError) -> bool:
    return "deadlock detected" in str(exc).lower()


class Command(BaseCommand):
    help = "Process queued runs and dispatch to the engine."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--once", action="store_true", help="Process a single entry and exit.")
        parser.add_argument(
            "--sleep",
            type=int,
            default=2,
            help="Sleep interval (seconds) when queue is empty.",
        )
        parser.add_argument(
            "--worker-id",
            type=str,
            default="",
            help="Worker identifier (default: hostname).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        worker_id = options.get("worker_id") or socket.gethostname()
        run_once = bool(options.get("once"))
        sleep_seconds = int(options.get("sleep") or 2)

        if not getattr(settings, "RUN_QUEUE_ENABLED", False):
            self.stdout.write(self.style.WARNING("RUN_QUEUE_ENABLED is false; exiting."))
            return

        queue_settings = get_run_queue_settings()
        record_run_queue_worker_heartbeat(worker_id)
        self.stdout.write(
            self.style.SUCCESS(
                f"Run queue worker '{worker_id}' starting (max_per_tenant={queue_settings.max_per_tenant})."
            )
        )

        while True:
            record_run_queue_worker_heartbeat(worker_id)
            release_stale_entries(lock_timeout_seconds=queue_settings.lock_timeout_seconds)
            reconcile_stale_runs()
            entry = claim_next_entry(worker_id=worker_id, settings_override=queue_settings)
            if entry is None:
                if run_once:
                    return
                time.sleep(sleep_seconds)
                continue

            self._process_entry(entry, queue_settings)

            if run_once:
                return

    def _process_entry(self, entry: RunQueueEntry, queue_settings: Any) -> None:
        run = entry.run
        if run.status in TERMINAL_RUN_STATUSES:
            logger.info(
                "Skipping stale run queue entry %s for terminal run %s (%s).",
                entry.id,
                run.id,
                run.status,
            )
            mark_completed(entry)
            return

        user = run.owner
        tenant_id = get_tenant_id_for_user(user)
        session_id = str(run.thread_id) if run.thread_id else None
        graph_version = run.graph_version
        for lifecycle_task in run.task_lifecycle_records.exclude(
            status__in=["completed", "failed", "dead_lettered", "cancelled"]
        ):
            try:
                self._transition_task_lifecycle_with_deadlock_retry(
                    run=run,
                    node_id=lifecycle_task.source_node_id,
                    node_type=lifecycle_task.node_type,
                    to_status="claimed",
                    attempt_number=max(lifecycle_task.current_attempt, entry.attempts or 1),
                    source="run_queue_worker",
                    idempotency_key=(
                        f"task:{run.id}:{lifecycle_task.source_node_id}:"
                        f"claimed:{entry.id}:{entry.attempts}"
                    ),
                    reason=f"claimed by run queue worker {entry.locked_by}",
                )
            except OperationalError as exc:
                if not _is_deadlock(exc):
                    raise
                logger.warning(
                    "run_queue_task_claim_deadlock_retry_exhausted",
                    extra={
                        "run_id": str(run.id),
                        "queue_entry_id": str(entry.id),
                        "task_id": str(lifecycle_task.id),
                    },
                )
                mark_failed(
                    entry,
                    error_message="Deadlock while claiming run lifecycle tasks.",
                    retryable=True,
                    settings_override=queue_settings,
                )
                return

        checkpoint = None
        try:
            checkpoint = run.checkpoint
        except Exception:
            checkpoint = None

        checkpoint_graph_json = checkpoint.graph_json if checkpoint is not None else None
        if isinstance(checkpoint_graph_json, dict):
            prepared_graph = copy.deepcopy(checkpoint_graph_json)
        elif isinstance(run.dispatch_graph_json, dict):
            prepared_graph = copy.deepcopy(run.dispatch_graph_json)
        else:
            try:
                prepared_graph = prepare_graph_for_engine(
                    graph_version.graph_json,
                    user,
                    company_id=graph_version.graph_id,
                )
            except PromptTemplateResolutionError as exc:
                self._fail_run(entry, run, f"Invalid prompt configuration: {exc}")
                return
            except (SubgraphResolutionError, ValueError) as exc:
                self._fail_run(entry, run, f"Invalid subgraph: {exc}")
                return

        try:
            outbound_graph = prepare_tool_executions_for_dispatch(
                run=run,
                graph_json=prepared_graph,
            )
            if not _run_has_context_pack(run):
                _, outbound_with_context = ContextPackService().attach_context_pack_to_run(
                    run=run,
                    outbound_graph=outbound_graph,
                )
                run.save(update_fields=["dispatch_graph_json"])
                outbound_graph = outbound_with_context or outbound_graph
        except ToolExecutionDispatchBlocked as exc:
            self._fail_run(entry, run, f"Tool execution dispatch blocked: {exc}")
            return

        try:
            llm_access = engine_llm_access_from_graph(prepared_graph, user)
        except LLMAccessValidationError as exc:
            self._fail_run(entry, run, f"LLM access is invalid: {exc.details}")
            return

        credential_errors = validate_prompt_credentials(
            prepared_graph,
            user,
            llm_access=llm_access,
        )
        if credential_errors:
            self._fail_run(entry, run, "Prompt credentials are missing or invalid.")
            return

        callback_url = resolve_engine_callback_url(run_id=str(run.id))
        memory_config_json = build_memory_config_json(
            graph_version.graph, user, session_id=session_id
        )
        trace_context = ensure_trace_context(trace_id=run.trace_id or None)
        if not run.trace_id:
            run.trace_id = trace_context["trace_id"]
            run.save(update_fields=["trace_id"])

        try:
            target = select_engine_target(run_id=str(run.id))
            engine_input_json = engine_input_with_llm_access(run.input_json, llm_access)
            with get_engine_client(callback_url, host=target.host, port=target.port) as engine:
                engine.start_run(
                    run_id=run.id,
                    graph_json=outbound_graph,
                    input_json=engine_input_json,
                    memory_config_json=memory_config_json,
                    tenant_id=tenant_id,
                    session_id=session_id,
                    traceparent=trace_context["traceparent"],
                    tracestate=trace_context["tracestate"],
                )
        except EngineConnectionError as exc:
            logger.error("Engine connection failed for run %s: %s", run.id, exc)
            self._fail_run(entry, run, f"Engine connection failed: {exc}", retryable=True)
            return
        except EngineExecutionError as exc:
            logger.error("Engine rejected run %s: %s", run.id, exc)
            self._fail_run(entry, run, f"Engine rejected run: {exc}")
            return

        should_mark_tasks_queued = self._complete_engine_dispatch(
            entry=entry,
            run=run,
            engine_instance_id=target.engine_id,
        )
        if not should_mark_tasks_queued:
            return

        for lifecycle_task in run.task_lifecycle_records.exclude(
            status__in=["completed", "failed", "dead_lettered", "cancelled"]
        ):
            try:
                self._transition_task_lifecycle_with_deadlock_retry(
                    run=run,
                    node_id=lifecycle_task.source_node_id,
                    node_type=lifecycle_task.node_type,
                    to_status="queued",
                    attempt_number=max(lifecycle_task.current_attempt, entry.attempts or 1),
                    source="run_queue_worker",
                    idempotency_key=(
                        f"task:{run.id}:{lifecycle_task.source_node_id}:"
                        f"engine_dispatched:{entry.id}:{entry.attempts}"
                    ),
                    reason="run dispatched to engine; waiting for node-level lifecycle",
                )
            except OperationalError as exc:
                if not _is_deadlock(exc):
                    raise
                logger.warning(
                    "run_queue_task_queued_deadlock_retry_exhausted",
                    extra={
                        "run_id": str(run.id),
                        "queue_entry_id": str(entry.id),
                        "task_id": str(lifecycle_task.id),
                    },
                )

    def _complete_engine_dispatch(
        self,
        *,
        entry: RunQueueEntry,
        run: Any,
        engine_instance_id: str,
    ) -> bool:
        for attempt in range(_DEADLOCK_RETRY_ATTEMPTS):
            try:
                return self._complete_engine_dispatch_once(
                    entry=entry,
                    run=run,
                    engine_instance_id=engine_instance_id,
                )
            except OperationalError as exc:
                if not _is_deadlock(exc) or attempt >= _DEADLOCK_RETRY_ATTEMPTS - 1:
                    raise
                logger.warning(
                    "run_queue_dispatch_finalize_deadlock_retry",
                    extra={
                        "run_id": str(run.id),
                        "queue_entry_id": str(entry.id),
                        "attempt": attempt + 1,
                    },
                )
                time.sleep(0.05 * (attempt + 1))
                run.refresh_from_db()
                entry.refresh_from_db()
        raise RuntimeError("unreachable run queue dispatch retry state")

    def _transition_task_lifecycle_with_deadlock_retry(self, **kwargs: Any) -> Any:
        for attempt in range(_DEADLOCK_RETRY_ATTEMPTS):
            try:
                return transition_task_lifecycle(**kwargs)
            except OperationalError as exc:
                if not _is_deadlock(exc) or attempt >= _DEADLOCK_RETRY_ATTEMPTS - 1:
                    raise
                logger.warning(
                    "run_queue_task_lifecycle_deadlock_retry",
                    extra={
                        "run_id": str(getattr(kwargs.get("run"), "id", "")),
                        "node_id": str(kwargs.get("node_id") or ""),
                        "to_status": str(kwargs.get("to_status") or ""),
                        "attempt": attempt + 1,
                    },
                )
                time.sleep(0.05 * (attempt + 1))
        raise RuntimeError("unreachable task lifecycle retry state")

    def _complete_engine_dispatch_once(
        self,
        *,
        entry: RunQueueEntry,
        run: Any,
        engine_instance_id: str,
    ) -> bool:
        with transaction.atomic():
            run = type(run).objects.select_for_update(of=("self",)).get(id=run.id)
            entry = RunQueueEntry.objects.select_for_update(of=("self",)).get(id=entry.id)

            if run.status in TERMINAL_RUN_STATUSES:
                mark_completed(entry)
                return False

            transition = apply_run_status_transition(run, "running")
            update_fields = transition.update_fields
            update_fields.extend(
                touch_run_liveness(
                    run,
                    recovery_state=recovery_state_for_status("running"),
                    engine_instance_id=engine_instance_id,
                )
            )
            run.save(update_fields=sorted(set(update_fields)))
            mark_completed(entry)
            transaction.on_commit(record_run_started)
            transaction.on_commit(lambda: broadcast_run_updated(run))
        return True

    def _fail_run(
        self, entry: RunQueueEntry, run: Any, message: str, retryable: bool = False
    ) -> None:
        if retryable:
            if run.status in TERMINAL_RUN_STATUSES:
                mark_completed(entry)
                return

            run.error_message = message
            run.save(update_fields=["error_message"])
            mark_failed(entry, error_message=message, retryable=True)
            for lifecycle_task in run.task_lifecycle_records.exclude(
                status__in=["completed", "failed", "dead_lettered", "cancelled"]
            ):
                record_retry_operation(
                    run=run,
                    operation_type="run_queue_dispatch",
                    idempotency_key=f"retry:{run.id}:{lifecycle_task.source_node_id}:queue:{entry.attempts}",
                    attempt_number=max(entry.attempts, 1),
                    max_attempts=max(entry.max_attempts, 1),
                    retry_delay_ms=get_run_queue_settings().retry_delay_seconds * 1000,
                    retry_reason=message,
                    last_error=message,
                    owning_component="backend_run_queue",
                    retry_class="transport",
                    terminal_fallback="dead_letter",
                    node_id=lifecycle_task.source_node_id,
                    node_type=lifecycle_task.node_type,
                    parent_attempt_number=max(entry.attempts - 1, 1)
                    if entry.attempts > 1
                    else None,
                )
            return

        now = timezone.now()
        if run.status in TERMINAL_RUN_STATUSES:
            mark_completed(entry)
            return

        if not run.started_at:
            run.started_at = now
        transition = apply_run_status_transition(run, "failed")
        run.ended_at = now
        run.error_message = message
        run.save(
            update_fields=sorted(
                set(transition.update_fields + ["started_at", "ended_at", "error_message"])
            )
        )
        mark_run_tasks_terminal(
            run=run,
            status_value="failed",
            source="run_queue_worker",
            reason=message,
        )
        record_run_completed("failed", run.duration_ms)
        broadcast_run_updated(run)
        mark_failed(entry, error_message=message, retryable=False)
