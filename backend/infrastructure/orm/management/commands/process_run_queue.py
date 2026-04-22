from __future__ import annotations

import logging
import socket
import time
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from adapters.gateways.grpc_engine_client import (
    EngineConnectionError,
    EngineExecutionError,
    GrpcEngineClient,
)
from adapters.ws.runs.broadcast import broadcast_run_updated
from application.services.engine_selection import resolve_engine_callback_url, select_engine_target
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
    release_stale_entries,
)
from application.services.tenancy import get_tenant_id_for_user
from application.services.trace_context import ensure_trace_context
from infrastructure.orm.models import RunQueueEntry

logger = logging.getLogger(__name__)


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
        self.stdout.write(
            self.style.SUCCESS(
                f"Run queue worker '{worker_id}' starting (max_per_tenant={queue_settings.max_per_tenant})."
            )
        )

        while True:
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
        user = run.owner
        tenant_id = get_tenant_id_for_user(user)
        session_id = str(run.thread_id) if run.thread_id else None
        graph_version = run.graph_version

        checkpoint = None
        try:
            checkpoint = run.checkpoint
        except Exception:
            checkpoint = None

        checkpoint_graph_json = checkpoint.graph_json if checkpoint is not None else None
        if isinstance(checkpoint_graph_json, dict):
            prepared_graph = checkpoint_graph_json
        elif isinstance(run.dispatch_graph_json, dict):
            prepared_graph = run.dispatch_graph_json
        else:
            try:
                prepared_graph = prepare_graph_for_engine(graph_version.graph_json, user)
            except PromptTemplateResolutionError as exc:
                self._fail_run(entry, run, f"Invalid prompt configuration: {exc}")
                return
            except (SubgraphResolutionError, ValueError) as exc:
                self._fail_run(entry, run, f"Invalid subgraph: {exc}")
                return
            run.dispatch_graph_json = prepared_graph
            run.save(update_fields=["dispatch_graph_json"])

        credential_errors = validate_prompt_credentials(prepared_graph, user)
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
            with get_engine_client(callback_url, host=target.host, port=target.port) as engine:
                engine.start_run(
                    run_id=run.id,
                    graph_json=prepared_graph,
                    input_json=run.input_json,
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

        with transaction.atomic():
            run.status = "running"
            update_fields = ["status"]
            update_fields.extend(
                touch_run_liveness(
                    run,
                    recovery_state=recovery_state_for_status("running"),
                    engine_instance_id=target.engine_id,
                )
            )
            run.save(update_fields=sorted(set(update_fields)))
            record_run_started()
            broadcast_run_updated(run)
            mark_completed(entry)

    def _fail_run(
        self, entry: RunQueueEntry, run: Any, message: str, retryable: bool = False
    ) -> None:
        if retryable:
            run.error_message = message
            run.save(update_fields=["error_message"])
            mark_failed(entry, error_message=message, retryable=True)
            return

        now = timezone.now()
        if not run.started_at:
            run.started_at = now
        run.status = "failed"
        run.ended_at = now
        run.error_message = message
        run.save(update_fields=["status", "started_at", "ended_at", "error_message"])
        record_run_completed("failed", run.duration_ms)
        broadcast_run_updated(run)
        mark_failed(entry, error_message=message, retryable=False)
