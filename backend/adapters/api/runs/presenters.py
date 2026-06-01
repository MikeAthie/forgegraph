"""Run API presenter helpers."""

# ruff: noqa: F401,F403,F405,I001

from adapters.api.runs.common_base import *  # noqa: F403
from adapters.api.runs.agent_payloads import *  # noqa: F403


def _serialize_node_run_for_detail(
    *,
    node_run: NodeRun,
    agent_events_by_node: dict[tuple[str, int], list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    payload = {
        "id": node_run.id,
        "node_id": node_run.node_id,
        "node_type": node_run.node_type,
        "status": node_run.status,
        "attempt": node_run.attempt,
        "started_at": node_run.started_at,
        "ended_at": node_run.ended_at,
        "duration_ms": node_run.duration_ms,
        "input_json": _expand_dotted_payload(redact_payload(node_run.input_json)),
        "output_json": redact_payload(node_run.output_json),
        "error_json": redact_payload(node_run.error_json),
        "trace_id": node_run.trace_id,
        "span_id": node_run.span_id,
        "memory_activity": derive_node_memory_activity(
            node_type=str(node_run.node_type),
            output_json=node_run.output_json,
        ),
    }
    if agent_events_by_node is not None:
        payload["agent_trace"] = _derive_agent_trace(
            node_run=node_run,
            agent_events_by_node=agent_events_by_node,
        )
    return payload


def _timeline_status_from_payload(event_type: str, payload: dict[str, Any]) -> str | None:
    if isinstance(payload.get("status"), str):
        return str(payload["status"])
    nested_status = _nested_timeline_status(payload)
    if nested_status is not None:
        return nested_status
    suffix_statuses = {
        "_failed": "failed",
        "_completed": "succeeded",
        "_started": "running",
    }
    for suffix, status_value in suffix_statuses.items():
        if event_type.endswith(suffix):
            return status_value
    return {
        "run_paused": "paused",
        "run.resume_requested": "resume_requested",
        "run_resumed": "running",
        "node_retrying": "retrying",
    }.get(event_type)


def _nested_timeline_status(payload: dict[str, Any]) -> str | None:
    for key in ("run", "node_run"):
        nested = payload.get(key)
        if isinstance(nested, dict) and isinstance(nested.get("status"), str):
            return str(nested["status"])
    return None


def _timeline_node_id_from_payload(payload: dict[str, Any]) -> str | None:
    for key in ("node_id",):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    for key in ("node_run", "payload", "output"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            value = nested.get("node_id")
            if isinstance(value, str) and value:
                return value
    return None


def _timeline_message_for_event(event_type: str, payload: dict[str, Any]) -> str:
    node_id = _timeline_node_id_from_payload(payload)
    if event_type == "run_failed":
        return str(payload.get("error") or payload.get("error_message") or "Run failed.")
    run_messages = {
        "run_started": "Run started.",
        "run_completed": "Run completed successfully.",
        "run_paused": "Run paused for a decision boundary.",
        "run.resume_requested": "Resume requested and waiting for engine acknowledgment.",
        "run_resumed": "Run resumed after a decision.",
        "run_canceled": "Run canceled.",
        "run.schema_validation": "Run output schema validation reported issues.",
    }
    if event_type in run_messages:
        return run_messages[event_type]
    if node_id:
        node_messages = {
            "node_started": f"{node_id} started.",
            "node_completed": f"{node_id} completed.",
            "node_failed": f"{node_id} failed.",
            "node_retrying": f"{node_id} is retrying.",
            "node_skipped": f"{node_id} was skipped.",
        }
        if event_type in node_messages:
            return node_messages[event_type]
    return event_type.replace(".", " ").replace("_", " ")


def _run_status_from_event(event_type: str, payload: dict[str, Any]) -> str | None:
    if event_type == "run.updated":
        status_value = payload.get("status")
        if isinstance(status_value, str):
            return status_value
        run_payload = payload.get("run")
        if isinstance(run_payload, dict):
            status_value = run_payload.get("status")
            if isinstance(status_value, str):
                return status_value

    if event_type.startswith("run_") or event_type == "run.resume_requested":
        status_value = _timeline_status_from_payload(event_type, payload)
        if isinstance(status_value, str) and status_value in {
            "pending",
            "running",
            "paused",
            "resume_requested",
            "succeeded",
            "failed",
            "canceled",
        }:
            return status_value

    return None


_STATUS_HISTORY_EVENT_ORDER = {
    "run_started": 10,
    "run_paused": 20,
    "run.resume_requested": 30,
    "run_resumed": 40,
    "run_completed": 90,
    "run_failed": 90,
    "run_canceled": 90,
}
_STATUS_HISTORY_STATUS_ORDER = {
    "pending": 0,
    "running": 10,
    "paused": 20,
    "resume_requested": 30,
    "succeeded": 90,
    "failed": 90,
    "canceled": 90,
}


def _build_run_status_history(*, run: Run) -> list[str]:
    history: list[str] = []

    def append_status(status_value: str | None) -> None:
        if not status_value:
            return
        if history and history[-1] == status_value:
            return
        history.append(status_value)

    append_status("pending")

    event_rows = list(
        RunEvent.objects.filter(run=run).order_by("created_at", "id").only("event_type", "payload")
    )
    events: list[tuple[RunEvent, dict[str, Any], str | None]] = []
    for event_row in event_rows:
        payload = redact_payload(event_row.payload or {})
        payload_dict = payload if isinstance(payload, dict) else {}
        events.append(
            (event_row, payload_dict, _run_status_from_event(event_row.event_type, payload_dict))
        )

    for _, _, status_value in sorted(
        events,
        key=lambda item: (
            item[0].created_at,
            _STATUS_HISTORY_EVENT_ORDER.get(
                item[0].event_type,
                _STATUS_HISTORY_STATUS_ORDER.get(item[2] or "", 50),
            ),
            str(item[0].id),
        ),
    ):
        append_status(status_value)

    append_status(str(run.status or "").strip() or None)
    return history


def _validate_run_event_transition(*, current_status: str, event_type: str) -> None:
    normalized = str(current_status or "").strip().lower()
    requested_status = _run_status_from_event(event_type, {})
    if requested_status is None:
        return
    try:
        assert_run_transition_allowed(normalized, requested_status)
    except RunTransitionConflict as exc:
        raise ValueError(f"invalid run event transition: {exc}") from exc


def _build_run_timeline(*, run: Run) -> list[dict[str, Any]]:
    timeline: list[dict[str, Any]] = []
    ignored_event_types = {"run.updated", "node_run.updated", "node_stream.chunk"}

    event_rows = (
        RunEvent.objects.filter(run=run)
        .order_by("created_at", "id")
        .only("id", "event_type", "payload", "created_at", "trace_id")
    )
    for event_row in event_rows:
        if event_row.event_type in ignored_event_types or event_row.event_type.startswith("agent."):
            continue

        payload = redact_payload(event_row.payload or {})
        status_value = _timeline_status_from_payload(event_row.event_type, payload)
        node_id = _timeline_node_id_from_payload(payload)
        error_message = (
            payload.get("error") or payload.get("error_message") or payload.get("message")
            if event_row.event_type in {"run_failed", "node_failed", "run.schema_validation"}
            else None
        )
        duration_ms = payload.get("duration_ms")
        timeline.append(
            {
                "id": f"event:{event_row.id}",
                "timestamp": event_row.created_at.isoformat(),
                "kind": "error"
                if event_row.event_type in {"run_failed", "node_failed", "run.schema_validation"}
                else "event",
                "event_type": event_row.event_type,
                "trace_id": event_row.trace_id or run.trace_id,
                "run_id": str(run.id),
                "node_id": node_id,
                "status": status_value,
                "duration_ms": duration_ms if isinstance(duration_ms, int) else None,
                "cost_usd": None,
                "decision_id": None,
                "message": _timeline_message_for_event(event_row.event_type, payload),
                "error_message": str(error_message) if error_message else None,
                "details": payload,
            }
        )

    approval_rows = ApprovalTask.objects.filter(run=run).order_by("created_at", "id")
    for approval in approval_rows:
        payload = redact_payload(approval.payload if isinstance(approval.payload, dict) else {})
        timeline.append(
            {
                "id": f"decision:{approval.id}:required",
                "timestamp": approval.created_at.isoformat(),
                "kind": "decision",
                "event_type": "decision_required",
                "trace_id": run.trace_id,
                "run_id": str(run.id),
                "node_id": approval.node_id,
                "status": "waiting",
                "duration_ms": None,
                "cost_usd": None,
                "decision_id": str(approval.id),
                "message": str(payload.get("prompt_message") or "Human decision required."),
                "error_message": None,
                "details": payload,
            }
        )
        if approval.status != "pending" and approval.resolved_at:
            resolution = redact_payload(
                approval.result if isinstance(approval.result, dict) else {}
            )
            timeline.append(
                {
                    "id": f"decision:{approval.id}:resolved",
                    "timestamp": approval.resolved_at.isoformat(),
                    "kind": "decision",
                    "event_type": "decision_resolved",
                    "trace_id": run.trace_id,
                    "run_id": str(run.id),
                    "node_id": approval.node_id,
                    "status": approval.status,
                    "duration_ms": None,
                    "cost_usd": None,
                    "decision_id": str(approval.id),
                    "message": f"Decision {approval.status}.",
                    "error_message": None,
                    "details": resolution,
                }
            )

    usage_rows = (
        LLMUsage.objects.filter(run=run)
        .order_by("created_at", "id")
        .only(
            "id",
            "node_id",
            "provider",
            "model",
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "cost_usd",
            "created_at",
        )
    )
    for usage in usage_rows:
        timeline.append(
            {
                "id": f"cost:{usage.id}",
                "timestamp": usage.created_at.isoformat(),
                "kind": "cost",
                "event_type": "cost_updated",
                "trace_id": run.trace_id,
                "run_id": str(run.id),
                "node_id": usage.node_id,
                "status": None,
                "duration_ms": None,
                "cost_usd": float(usage.cost_usd),
                "decision_id": None,
                "message": f"{usage.provider} {usage.model} usage recorded.",
                "error_message": None,
                "details": {
                    "provider": usage.provider,
                    "model": usage.model,
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                    "total_tokens": usage.total_tokens,
                },
            }
        )

    timeline.sort(key=lambda entry: (entry.get("timestamp") or "", str(entry.get("id") or "")))
    return timeline


def _extract_llm_usage_payload(*, node_type: str, output_json: Any) -> dict[str, Any] | None:
    if not isinstance(output_json, dict):
        return None

    candidate = output_json
    nested_output = output_json.get("output")
    if node_type == "agent" and isinstance(nested_output, dict):
        candidate = nested_output

    usage = candidate.get("usage")
    if not isinstance(usage, dict):
        return None

    return {
        "provider": str(candidate.get("provider") or "openai"),
        "model": str(candidate.get("model") or ""),
        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
        "completion_tokens": int(usage.get("completion_tokens") or 0),
        "total_tokens": int(usage.get("total_tokens") or 0),
    }


__all__ = [
    "Any",
    "APIView",
    "AllowAny",
    "ApprovalTask",
    "ArchiveService",
    "BackendMemoryIntentService",
    "Callable",
    "CanonicalEventValidationError",
    "Case",
    "ContextPackService",
    "Count",
    "DecisionRecord",
    "Decimal",
    "EngineAssignmentError",
    "EngineCallbackContext",
    "EngineConnectionError",
    "EngineExecutionError",
    "EngineExecutionEventSerializer",
    "EventSafetyViolation",
    "GraphVersion",
    "GrpcEngineClient",
    "IdempotencyConflict",
    "IdempotencyStatus",
    "IntegerField",
    "IntegrityError",
    "IsAuthenticated",
    "LLMAccessConfig",
    "LLMAccessValidationError",
    "LLMBudget",
    "LLMQuota",
    "LLMUsage",
    "LLM_MODE_MANAGED",
    "NodeRun",
    "NodeRunEventProjection",
    "OperationalError",
    "Organization",
    "Prefetch",
    "PreferenceEventService",
    "ProcessedAccountingEvent",
    "ProcessedCallbackEvent",
    "ProcessedDecisionSubmission",
    "PromptTemplateResolutionError",
    "Q",
    "ReplayCheckpointSeed",
    "Request",
    "Response",
    "Run",
    "RunCheckpoint",
    "RunDetailWithNodeRunsSerializer",
    "RunEngineDispatch",
    "RunEvent",
    "RunEventProjection",
    "RunEventSerializer",
    "RunInvokeRequestContext",
    "RunInvokeSerializer",
    "RunLifecycleMutation",
    "RunListSerializer",
    "RunReplayRequestContext",
    "RunReplaySerializer",
    "RunResumeRequestContext",
    "RunResumeSerializer",
    "RunSnapshot",
    "RunStartRequestContext",
    "RunStartSerializer",
    "RunTransitionConflict",
    "SchemaError",
    "StreamingHttpResponse",
    "SubgraphResolutionError",
    "Sum",
    "TenantSubscription",
    "ToolExecutionDispatchBlocked",
    "UTC",
    "UUID",
    "User",
    "When",
    "_DEADLOCK_RETRY_ATTEMPTS",
    "_UNSET",
    "acquire_run_transaction_lock",
    "add_event_level",
    "annotate_response",
    "annotated_response_from_body",
    "apply_run_status_transition",
    "assert_run_transition_allowed",
    "assert_runtime_state_mutation_allowed",
    "async_to_sync",
    "asyncio",
    "attach_llm_access_to_graph",
    "broadcast_cost_update",
    "broadcast_decision_required",
    "broadcast_decision_resolved",
    "broadcast_node_run_updated",
    "broadcast_node_stream_chunk",
    "broadcast_node_stream_summary",
    "broadcast_run_schema_validation",
    "broadcast_run_updated",
    "build_idempotency_context",
    "build_memory_config_json",
    "calculate_cost",
    "cast",
    "check_managed_llm_limits",
    "check_rate_limit",
    "consume_ws_ticket",
    "datetime",
    "defaultdict",
    "derive_node_memory_activity",
    "engine_input_with_llm_access",
    "engine_instance_label",
    "engine_llm_access_from_graph",
    "enqueue_run",
    "ensure_trace_context",
    "error_response",
    "event_levels_for_subscription",
    "extract_schema_metadata",
    "flush_all_stream_summaries",
    "flush_stream_summary",
    "get_channel_layer",
    "get_engine_target_by_id",
    "get_snapshot",
    "hash_request_payload",
    "hashlib",
    "has_min_role",
    "initialize_lifecycle_tasks_for_run",
    "is_access_jti_revoked",
    "log_event",
    "log_run_queue_worker_unavailable",
    "logger",
    "logging",
    "mark_run_tasks_terminal",
    "message_allowed_for_level",
    "models",
    "normalize_event_category",
    "normalize_idempotency_key",
    "normalize_requested_event_level",
    "parse_datetime",
    "parse_engine_event_payload",
    "prepare_graph_for_engine",
    "prepare_tool_executions_for_dispatch",
    "problem_response",
    "public_llm_access_from_graph",
    "pyjson",
    "rate_limit_response_payload",
    "reconcile_run_engine_instance",
    "record_audit_log",
    "record_callback_auth_failure",
    "record_event_dead_letter",
    "record_idempotency_observation",
    "record_processed_command",
    "record_retry_operation",
    "record_run_completed",
    "record_run_started",
    "record_stale_attempt_ignored",
    "recovery_state_for_status",
    "redact_payload",
    "replay_processed_command",
    "resolve_engine_callback_url",
    "resolve_llm_access_for_dispatch",
    "resolve_tenant_id_for_user",
    "response_body",
    "run_event_group_name",
    "s2s",
    "safe_delete_snapshot",
    "safe_set_snapshot",
    "select_engine_target",
    "set_snapshot",
    "settings",
    "start_backend_span",
    "status",
    "success_response",
    "summarize_run_memory_activity",
    "time",
    "timezone",
    "touch_run_liveness",
    "transaction",
    "transition_from_node_run",
    "transition_task_lifecycle",
    "update_stream_summary",
    "upsert_memory_session",
    "uuid4",
    "validate_access_token",
    "validate_json_schema",
    "validate_prompt_credentials",
    "_datetime_from_timestamp_ms",
    "_serialize_event_payload",
    "_persist_run_updated_event",
    "_parse_agent_stream_chunk",
    "_normalize_agent_stream_event",
    "_derive_agent_trace",
    "_merge_nested_payload",
    "_insert_dotted_payload_value",
    "_expand_dotted_payload",
    "_serialize_node_run_for_detail",
    "_timeline_status_from_payload",
    "_nested_timeline_status",
    "_timeline_node_id_from_payload",
    "_timeline_message_for_event",
    "_run_status_from_event",
    "_STATUS_HISTORY_EVENT_ORDER",
    "_STATUS_HISTORY_STATUS_ORDER",
    "_build_run_status_history",
    "_validate_run_event_transition",
    "_build_run_timeline",
    "_extract_llm_usage_payload",
]
