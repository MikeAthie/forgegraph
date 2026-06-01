"""Run API response, dispatch, quota, and guardrail helpers."""

# ruff: noqa: F401,F403,F405,I001

from adapters.api.runs.common_base import *  # noqa: F403


def get_engine_client(
    callback_url: str = "",
    *,
    host: str | None = None,
    port: int | None = None,
) -> GrpcEngineClient:
    """Get an engine client instance. Can be mocked in tests."""
    return GrpcEngineClient(
        host=host or settings.ENGINE_HOST,
        port=port or settings.ENGINE_PORT,
        callback_url=callback_url,
        tls_enabled=settings.ENGINE_GRPC_TLS_ENABLED,
        tls_ca_file=settings.ENGINE_GRPC_TLS_CA_FILE,
        tls_server_name=settings.ENGINE_GRPC_TLS_SERVER_NAME,
    )


def get_engine_assignment(*, run_id: str, callback_url: str = "") -> tuple[str, GrpcEngineClient]:
    target = select_engine_target(run_id=run_id)
    return (
        target.engine_id,
        get_engine_client(callback_url, host=target.host, port=target.port),
    )


def get_engine_client_for_run(*, run: Run, callback_url: str = "") -> tuple[str, GrpcEngineClient]:
    target = (
        get_engine_target_by_id(run.engine_instance_id)
        if str(run.engine_instance_id or "").strip()
        else None
    )
    if target is None:
        target = select_engine_target(run_id=str(run.id))
    return (
        target.engine_id,
        get_engine_client(callback_url, host=target.host, port=target.port),
    )


def get_tenant_id(request: Request) -> str:
    """Get tenant ID from the authenticated user."""
    user = cast(User, request.user)
    return get_tenant_id_for_user(user)


def get_tenant_id_for_user(user: User) -> str:
    return resolve_tenant_id_for_user(user)


def get_tenant_id_for_run(run: Run) -> str:
    if run.organization_id:
        return str(run.organization_id)
    return get_tenant_id_for_user(run.owner)


def _request_trace_headers(request: Request) -> tuple[str | None, str | None]:
    return request.headers.get("traceparent"), request.headers.get("tracestate")


def _idempotency_conflict_response(exc: IdempotencyConflict) -> Response:
    return error_response(
        code="IDEMPOTENCY_CONFLICT",
        message=str(exc),
        status=status.HTTP_409_CONFLICT,
        details=[
            {
                "action": exc.action,
                "idempotency_key": exc.idempotency_key,
            }
        ],
    )


def _replayed_command_response(command_context: Any) -> Response | None:
    try:
        return replay_processed_command(command_context)
    except IdempotencyConflict as exc:
        return _idempotency_conflict_response(exc)


def _deterministic_submit_id(*, run_id: UUID, node_id: str, input_json: Any) -> str:
    digest = hash_request_payload(
        {
            "run_id": str(run_id),
            "node_id": node_id,
            "input_json": input_json if isinstance(input_json, dict) else {},
        }
    )
    return f"decision:{run_id}:{node_id}:{digest}"


def _resume_submit_id(*, request: Request, run_id: UUID, node_id: str, input_json: Any) -> str:
    explicit = normalize_idempotency_key(
        request.data.get("submit_id") if isinstance(request.data, dict) else "",
    )
    if explicit:
        return explicit
    header = normalize_idempotency_key(request.headers.get("Idempotency-Key"))
    if header:
        return header
    return _deterministic_submit_id(run_id=run_id, node_id=node_id, input_json=input_json)


def _processed_decision_replay_response(
    submission: ProcessedDecisionSubmission,
    *,
    submit_id: str,
) -> Response | None:
    if not submission.response_body:
        return None
    record_idempotency_observation(
        boundary="human_decision",
        status="already_applied",
        idempotency_key=submit_id,
        resource_type="run",
        organization_id=submission.organization_id,
        run_id=submission.run_id,
    )
    return annotated_response_from_body(
        submission.response_body,
        response_status=submission.response_status,
        status="already_applied",
        idempotency_key=submit_id,
        resource_type="run",
        resource_id=str(submission.run_id),
    )


def _memory_intent_payload_from_event(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("output")
    if not isinstance(payload, dict):
        payload = event.get("payload")
    if not isinstance(payload, dict):
        payload = {
            key: event[key]
            for key in (
                "fact",
                "facts",
                "content",
                "value",
                "key",
                "title",
                "source_span",
                "confidence",
                "summary_id",
                "ttl_seconds",
                "cost_usd",
                "total_tokens",
                "prompt_tokens",
                "completion_tokens",
                "model",
                "provider",
            )
            if key in event
        }
    payload = dict(payload)
    for key in ("tenant_id", "organization_id", "org_id", "run_id", "agent_id", "idempotency_key"):
        if key in event and key not in payload:
            payload[key] = str(event[key]) if event[key] is not None else None
    return payload


def _log_payload_summary(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        keys = [str(key) for key in value.keys()]
        return {
            "type": "object",
            "key_count": len(keys),
            "keys": keys[:12],
            "truncated": len(keys) > 12,
        }
    if isinstance(value, list):
        return {"type": "array", "length": len(value)}
    if isinstance(value, str):
        return {"type": "string", "length": len(value)}
    if value is None:
        return {"type": "null"}
    return {"type": type(value).__name__}


def _trace_metadata_from_graph(graph_json: dict[str, Any]) -> dict[str, str]:
    metadata = graph_json.get("metadata")
    if not isinstance(metadata, dict):
        return ensure_trace_context()
    trace = metadata.get("trace")
    if not isinstance(trace, dict):
        return ensure_trace_context()
    return ensure_trace_context(
        traceparent=str(trace.get("traceparent") or "").strip() or None,
        tracestate=str(trace.get("tracestate") or "").strip() or None,
        trace_id=str(trace.get("trace_id") or "").strip() or None,
    )


def run_queryset_for_user(user: User) -> models.QuerySet[Run]:
    tenant_id = get_tenant_id_for_user(user)
    if not has_min_role(user, "viewer", tenant_id):
        return Run.objects.none()
    tenant_uuid = UUID(tenant_id)
    return Run.objects.filter(
        Q(organization_id=tenant_uuid)
        | Q(organization__isnull=True, owner__default_organization_id=tenant_uuid)
    )


def _queue_payload(run: Run) -> dict[str, Any]:
    entry = getattr(run, "queue_entry", None)
    if not entry:
        return {
            "queue_status": None,
            "queue_attempts": None,
            "queue_available_at": None,
        }
    return {
        "queue_status": entry.status,
        "queue_attempts": entry.attempts,
        "queue_available_at": entry.available_at,
    }


def _queue_response_meta(*, run: Run, tenant_id: str) -> dict[str, Any]:
    health = log_run_queue_worker_unavailable(run_id=run.id, tenant_id=tenant_id)
    return {
        "queued": True,
        "queue_worker_active": health.active,
        "queue_worker_id": health.worker_id or None,
        "queue_worker_last_seen_at": (
            health.last_seen_at.isoformat() if health.last_seen_at else None
        ),
        "queue_worker_age_seconds": health.age_seconds,
        "queue_warning": None if health.active else "run_queue_worker_unavailable",
    }


def _run_start_slow_log_threshold_ms() -> float:
    return float(getattr(settings, "RUN_START_SLOW_LOG_MS", 250))


def _log_run_start_timing(
    *,
    run: Run,
    tenant_id: str,
    queued: bool,
    started_at: float,
    marks: list[tuple[str, float]],
) -> None:
    elapsed_ms = (time.perf_counter() - started_at) * 1000
    if elapsed_ms < _run_start_slow_log_threshold_ms():
        return
    previous = started_at
    phases: list[dict[str, Any]] = []
    for stage, mark in marks:
        phases.append(
            {
                "stage": stage,
                "elapsed_ms": round((mark - started_at) * 1000, 2),
                "delta_ms": round((mark - previous) * 1000, 2),
            }
        )
        previous = mark
    log_event(
        logger,
        logging.INFO,
        "run_start_timing",
        run_id=str(run.id),
        tenant_id=tenant_id,
        duration_ms=round(elapsed_ms, 2),
        status=run.status,
        payload={
            "queued": queued,
            "phase_count": len(phases),
            "phases": phases,
        },
        message="Slow run start timing",
    )


def _public_llm_access_payload(run: Run) -> dict[str, Any]:
    return public_llm_access_from_graph(
        run.dispatch_graph_json if isinstance(run.dispatch_graph_json, dict) else {}
    )


def _engine_input_for_llm_access(
    input_json: dict[str, Any],
    llm_access: LLMAccessConfig,
) -> dict[str, Any]:
    return engine_input_with_llm_access(input_json, llm_access)


def _attach_operation_context_pack(
    run: Run,
    outbound_graph: dict[str, Any],
    *,
    context_pack_mode: str = "fresh_at_dispatch",
) -> dict[str, Any]:
    _, outbound_with_context = ContextPackService().attach_context_pack_to_run(
        run=run,
        outbound_graph=outbound_graph,
        context_pack_mode=context_pack_mode,
    )
    run.save(update_fields=["dispatch_graph_json"])
    return outbound_with_context or outbound_graph


def _schedule_deliverable_archive(run_id: UUID, node_run_id: UUID | None = None) -> None:
    def archive_deliverables() -> None:
        try:
            run = Run.objects.select_related(
                "organization",
                "graph_version__graph__organization",
            ).get(id=run_id)
            node_run = None
            if node_run_id is not None:
                node_run = NodeRun.objects.filter(id=node_run_id, run=run).first()
            ArchiveService().archive_deliverable_as_asset(run=run, node_run=node_run)
        except Exception:
            logger.exception(
                "deliverable_archive_failed",
                extra={"run_id": str(run_id), "node_run_id": str(node_run_id or "")},
            )

    transaction.on_commit(archive_deliverables)


def _llm_access_error_response(exc: LLMAccessValidationError) -> Response:
    return error_response(
        code="INVALID_LLM_ACCESS",
        message="LLM access configuration is invalid.",
        status=status.HTTP_400_BAD_REQUEST,
        details=exc.details,
    )


def _managed_llm_limit_response(
    *,
    user: User,
    graph_json: dict[str, Any],
    llm_access: LLMAccessConfig,
) -> Response | None:
    if llm_access.llm_mode != LLM_MODE_MANAGED:
        return None
    result = check_managed_llm_limits(graph_json=graph_json, user=user)
    if result.allowed:
        return None
    response = error_response(
        code="MANAGED_LIMIT_EXCEEDED",
        message="Managed LLM limit exceeded.",
        status=status.HTTP_429_TOO_MANY_REQUESTS,
        details=result.details,
    )
    if result.rate_limit is not None:
        response["Retry-After"] = str(result.rate_limit.retry_after_seconds)
        response["X-RateLimit-Limit"] = str(result.rate_limit.limit)
        response["X-RateLimit-Remaining"] = str(result.rate_limit.remaining)
        response["X-RateLimit-Reset"] = result.rate_limit.reset_at.isoformat()
    return response


def _run_preparation_error_response(exc: Exception) -> Response:
    if isinstance(exc, PromptTemplateResolutionError):
        return error_response(
            code="INVALID_PROMPT_CONFIG",
            message=str(exc),
            status=status.HTTP_400_BAD_REQUEST,
        )
    if isinstance(exc, SubgraphResolutionError):
        return error_response(
            code="INVALID_SUBGRAPH",
            message=str(exc),
            status=status.HTTP_400_BAD_REQUEST,
        )
    return error_response(
        code="INVALID_SUBGRAPH",
        message=str(exc),
        status=status.HTTP_400_BAD_REQUEST,
    )


def _tool_execution_dispatch_error_response(exc: Exception) -> Response:
    return error_response(
        code="TOOL_EXECUTION_DISPATCH_BLOCKED",
        message=str(exc),
        status=status.HTTP_409_CONFLICT,
    )


def check_llm_budget(user: User) -> Response | None:
    tenant_id = get_tenant_id_for_user(user)
    budget = LLMBudget.objects.filter(tenant_id=tenant_id).first()
    if not budget:
        return None

    month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    total_cost = LLMUsage.objects.filter(
        tenant_id=tenant_id, created_at__gte=month_start
    ).aggregate(total=Sum("cost_usd")).get("total") or Decimal("0")

    if total_cost >= budget.monthly_limit_usd:
        return error_response(
            code="BUDGET_EXCEEDED",
            message="Monthly LLM budget exceeded. Increase your limit or wait for next month.",
            status=status.HTTP_402_PAYMENT_REQUIRED,
            details=[
                {
                    "reason": "budget",
                    "scope": "tenant_monthly_spend",
                    "current_cost_usd": float(total_cost),
                    "limit_cost_usd": float(budget.monthly_limit_usd),
                }
            ],
        )

    return None


def check_llm_quota(user: User) -> Response | None:
    tenant_id = get_tenant_id_for_user(user)
    quota = LLMQuota.objects.filter(tenant_id=tenant_id).first()
    if not quota:
        return None

    month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    totals = LLMUsage.objects.filter(tenant_id=tenant_id, created_at__gte=month_start).aggregate(
        total_tokens=Sum("total_tokens"),
        total_cost=Sum("cost_usd"),
    )
    total_tokens = int(totals.get("total_tokens") or 0)
    total_cost = totals.get("total_cost") or Decimal("0")

    if quota.monthly_token_limit and total_tokens >= quota.monthly_token_limit:
        return error_response(
            code="QUOTA_EXCEEDED",
            message="Monthly LLM token quota exceeded. Increase your quota or wait for next month.",
            status=status.HTTP_402_PAYMENT_REQUIRED,
            details=[
                {
                    "reason": "quota",
                    "scope": "tenant_monthly_tokens",
                    "current_total_tokens": total_tokens,
                    "limit_total_tokens": quota.monthly_token_limit,
                }
            ],
        )

    if quota.monthly_cost_limit_usd and total_cost >= quota.monthly_cost_limit_usd:
        return error_response(
            code="QUOTA_EXCEEDED",
            message="Monthly LLM cost quota exceeded. Increase your quota or wait for next month.",
            status=status.HTTP_402_PAYMENT_REQUIRED,
            details=[
                {
                    "reason": "quota",
                    "scope": "tenant_monthly_cost",
                    "current_cost_usd": float(total_cost),
                    "limit_cost_usd": float(quota.monthly_cost_limit_usd),
                }
            ],
        )

    return None


def check_entitlements(user: User) -> Response | None:
    tenant_id = get_tenant_id_for_user(user)
    tenant_uuid = UUID(tenant_id)
    subscription = (
        TenantSubscription.objects.select_related("plan").filter(tenant_id=tenant_id).first()
    )

    if not subscription or not subscription.plan:
        return None

    if subscription.status not in {"active", "trialing"}:
        return error_response(
            code="SUBSCRIPTION_INACTIVE",
            message="Your subscription is not active. Update billing to continue.",
            status=status.HTTP_402_PAYMENT_REQUIRED,
            details=[
                {
                    "reason": "plan_entitlement",
                    "scope": "subscription_status",
                    "subscription_status": subscription.status,
                    "plan_name": subscription.plan.name if subscription.plan else None,
                }
            ],
        )

    entitlements = subscription.plan.entitlements or {}
    month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    max_tokens = entitlements.get("max_monthly_tokens")
    if max_tokens is not None:
        total_tokens = (
            LLMUsage.objects.filter(tenant_id=tenant_id, created_at__gte=month_start)
            .aggregate(total=Sum("total_tokens"))
            .get("total")
            or 0
        )
        if int(total_tokens) >= int(max_tokens):
            return error_response(
                code="ENTITLEMENT_LIMIT",
                message="Monthly token entitlement exceeded for your plan.",
                status=status.HTTP_402_PAYMENT_REQUIRED,
                details=[
                    {
                        "reason": "plan_entitlement",
                        "scope": "plan_monthly_tokens",
                        "current_total_tokens": int(total_tokens),
                        "limit_total_tokens": int(max_tokens),
                        "plan_name": subscription.plan.name,
                    }
                ],
            )

    max_cost = entitlements.get("max_monthly_cost_usd")
    if max_cost is not None:
        total_cost = LLMUsage.objects.filter(
            tenant_id=tenant_id, created_at__gte=month_start
        ).aggregate(total=Sum("cost_usd")).get("total") or Decimal("0")
        if total_cost >= Decimal(str(max_cost)):
            return error_response(
                code="ENTITLEMENT_LIMIT",
                message="Monthly cost entitlement exceeded for your plan.",
                status=status.HTTP_402_PAYMENT_REQUIRED,
                details=[
                    {
                        "reason": "plan_entitlement",
                        "scope": "plan_monthly_cost",
                        "current_cost_usd": float(total_cost),
                        "limit_cost_usd": float(Decimal(str(max_cost))),
                        "plan_name": subscription.plan.name,
                    }
                ],
            )

    max_runs = entitlements.get("max_runs_per_month")
    if max_runs is not None:
        run_count = Run.objects.filter(
            Q(organization_id=tenant_uuid)
            | Q(organization__isnull=True, owner__default_organization_id=tenant_uuid),
            started_at__gte=month_start,
        ).count()
        if run_count >= int(max_runs):
            return error_response(
                code="ENTITLEMENT_LIMIT",
                message="Monthly run entitlement exceeded for your plan.",
                status=status.HTTP_402_PAYMENT_REQUIRED,
                details=[
                    {
                        "reason": "plan_entitlement",
                        "scope": "plan_monthly_runs",
                        "current_run_count": run_count,
                        "limit_run_count": int(max_runs),
                        "plan_name": subscription.plan.name,
                    }
                ],
            )

    return None


def _apply_rate_limit(
    *, scope: str, tenant_id: str, limit: int, window_seconds: int
) -> Response | None:
    if limit <= 0:
        return None
    result = check_rate_limit(
        scope=scope,
        tenant_id=tenant_id,
        limit=limit,
        window_seconds=window_seconds,
    )
    if result.allowed:
        return None
    response = error_response(
        code="RATE_LIMITED",
        message="Rate limit exceeded. Try again shortly.",
        status=status.HTTP_429_TOO_MANY_REQUESTS,
        details=[rate_limit_response_payload(result)],
    )
    response["Retry-After"] = str(result.retry_after_seconds)
    response["X-RateLimit-Limit"] = str(result.limit)
    response["X-RateLimit-Remaining"] = str(result.remaining)
    response["X-RateLimit-Reset"] = result.reset_at.isoformat()
    return response


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
    "get_engine_client",
    "get_engine_assignment",
    "get_engine_client_for_run",
    "get_tenant_id",
    "get_tenant_id_for_user",
    "get_tenant_id_for_run",
    "_request_trace_headers",
    "_idempotency_conflict_response",
    "_replayed_command_response",
    "_deterministic_submit_id",
    "_resume_submit_id",
    "_processed_decision_replay_response",
    "_memory_intent_payload_from_event",
    "_log_payload_summary",
    "_trace_metadata_from_graph",
    "run_queryset_for_user",
    "_queue_payload",
    "_queue_response_meta",
    "_run_start_slow_log_threshold_ms",
    "_log_run_start_timing",
    "_public_llm_access_payload",
    "_engine_input_for_llm_access",
    "_attach_operation_context_pack",
    "_schedule_deliverable_archive",
    "_llm_access_error_response",
    "_managed_llm_limit_response",
    "_run_preparation_error_response",
    "_tool_execution_dispatch_error_response",
    "check_llm_budget",
    "check_llm_quota",
    "check_entitlements",
    "_apply_rate_limit",
]
