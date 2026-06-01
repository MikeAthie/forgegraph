"""Engine callback shared helpers for run API adapters."""

# ruff: noqa: F401,F403,F405,I001

from adapters.api.runs.common_base import *  # noqa: F403


def _is_deadlock(exc: OperationalError) -> bool:
    return "deadlock detected" in str(exc).lower()


def _lock_run_for_update(run_id: UUID) -> Run:
    acquire_run_transaction_lock(run_id)
    return Run.objects.select_for_update().select_related("owner").get(id=run_id)


def _engine_event_attempt_id(event_type: str, event: dict[str, Any]) -> str:
    attempt_id = str(event.get("attempt_id") or "").strip()
    if attempt_id:
        return attempt_id
    if event_type == "run_resumed":
        output = event.get("output")
        if isinstance(output, dict):
            return str(output.get("resume_attempt_id") or "").strip()
    return ""


def _engine_callback_payload(
    *,
    decision: str,
    reason: str,
    backend_event_id: str = "",
    safe_to_discard: bool = False,
    retry_after_ms: int | None = None,
    conflict_code: str = "",
    **extra: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "decision": decision,
        "reason": reason,
        "backend_event_id": backend_event_id,
        "safe_to_discard": safe_to_discard,
    }
    if retry_after_ms is not None:
        payload["retry_after_ms"] = retry_after_ms
    if conflict_code:
        payload["conflict_code"] = conflict_code
    payload.update(extra)
    return payload


def _engine_callback_success(
    data: dict[str, Any] | None = None,
    *,
    decision: str = "accepted",
    reason: str = "accepted",
    backend_event_id: str = "",
    safe_to_discard: bool = True,
    conflict_code: str = "",
) -> Response:
    payload = _engine_callback_payload(
        decision=decision,
        reason=reason,
        backend_event_id=backend_event_id,
        safe_to_discard=safe_to_discard,
        conflict_code=conflict_code,
    )
    if data:
        payload.update(data)
    return success_response(payload)


def _engine_callback_problem(
    *,
    type_uri: str,
    title: str,
    status_code: int,
    detail: str,
    decision: str,
    reason: str,
    backend_event_id: str = "",
    safe_to_discard: bool = False,
    conflict_code: str = "",
    extensions: dict[str, Any] | None = None,
) -> Response:
    payload = _engine_callback_payload(
        decision=decision,
        reason=reason,
        backend_event_id=backend_event_id,
        safe_to_discard=safe_to_discard,
        conflict_code=conflict_code,
        type=type_uri,
        title=title,
        status=status_code,
        detail=detail,
    )
    if extensions:
        payload.update(extensions)
    return Response(payload, status=status_code)


def _record_engine_callback_dead_letter(
    *,
    event: dict[str, Any] | None,
    run: Run | None = None,
    reason: str,
    error_class: str = "",
    event_type: str = "",
    event_id: str = "",
    idempotency_key: str = "",
) -> None:
    payload = event if isinstance(event, dict) else {}
    try:
        organization = run.organization if run is not None and run.organization_id else None
        if organization is None:
            organization = _organization_from_event_payload(payload)
        record_event_dead_letter(
            source="engine_callback",
            reason=reason,
            payload=payload,
            organization=organization,
            run=run,
            event_id=event_id or str(payload.get("event_id") or ""),
            idempotency_key=idempotency_key or str(payload.get("idempotency_key") or ""),
            event_type=event_type or str(payload.get("type") or payload.get("event_type") or ""),
            error_class=error_class,
        )
    except Exception:
        logger.exception(
            "engine_callback_dead_letter_record_failed",
            extra={
                "run_id": str(run.id) if run is not None else "",
                "event_id": event_id or str(payload.get("event_id") or ""),
                "event_type": event_type or str(payload.get("type") or ""),
                "reason": reason,
            },
        )


def _organization_from_event_payload(event: dict[str, Any]) -> Organization | None:
    raw_org_id = str(event.get("tenant_id") or event.get("organization_id") or "").strip()
    if not raw_org_id:
        return None
    try:
        org_id = UUID(raw_org_id)
    except ValueError:
        return None
    return Organization.objects.filter(id=org_id).first()


def _ignore_stale_engine_attempt(
    *,
    run: Run,
    event_type: str,
    event: dict[str, Any],
    event_id: str,
    trace_id: str,
    normalized_category: str,
) -> Response | None:
    if normalized_category != "state":
        return None

    current_attempt_id = run.authoritative_attempt_id
    event_attempt_id = _engine_event_attempt_id(event_type, event)
    if not current_attempt_id or not event_attempt_id or event_attempt_id == current_attempt_id:
        return None

    record_stale_attempt_ignored("engine_callback")
    log_event(
        logger,
        logging.WARNING,
        "stale_attempt_ignored",
        run_id=str(run.id),
        trace_id=trace_id,
        event_id=event_id,
        attempt_id=event_attempt_id,
        active_attempt_id=current_attempt_id,
        current_attempt_id=current_attempt_id,
        message="Ignored stale engine callback for superseded attempt",
        category=normalized_category,
    )
    if event_type == "run_resumed":
        return _engine_callback_problem(
            type_uri="https://forgegraph.dev/problems/stale-resume-acknowledgement",
            title="Stale resume acknowledgement",
            status_code=status.HTTP_409_CONFLICT,
            detail="run_resumed acknowledgement does not match the active resume_attempt_id.",
            decision="stale_superseded",
            reason="resume_attempt_id does not match the active backend resume attempt",
            backend_event_id=event_id,
            safe_to_discard=True,
            conflict_code="409_STALE_SUPERSEDED",
        )
    return _engine_callback_success(
        {
            "received": True,
            "stale": True,
            "authoritative_state_updated": False,
        },
        decision="stale_superseded",
        reason="event attempt does not match the active backend attempt",
        backend_event_id=event_id,
        safe_to_discard=True,
        conflict_code="409_STALE_SUPERSEDED",
    )


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
    "_is_deadlock",
    "_lock_run_for_update",
    "_engine_event_attempt_id",
    "_engine_callback_payload",
    "_engine_callback_success",
    "_engine_callback_problem",
    "_record_engine_callback_dead_letter",
    "_organization_from_event_payload",
    "_ignore_stale_engine_attempt",
]
