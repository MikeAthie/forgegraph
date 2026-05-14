"""Run API durable state projection helpers."""

# ruff: noqa: F401,F403,F405,I001

from adapters.api.runs.common_base import *  # noqa: F403


def _payload_contains_policy_denied(value: Any) -> bool:
    if isinstance(value, str):
        return "policy denied:" in value.lower()
    if isinstance(value, dict):
        return any(_payload_contains_policy_denied(item) for item in value.values())
    if isinstance(value, list):
        return any(_payload_contains_policy_denied(item) for item in value)
    return False


def _get_downstream_nodes(graph_json: dict[str, Any], start_node_id: str) -> set[str]:
    nodes_raw = graph_json.get("nodes")
    if not isinstance(nodes_raw, list):
        return set()

    node_ids: set[str] = {
        str(node.get("id"))
        for node in nodes_raw
        if isinstance(node, dict) and node.get("id") is not None
    }
    if start_node_id not in node_ids:
        return set()

    adjacency = _adjacency_for_nodes(node_ids, graph_json.get("edges"))
    visited: set[str] = set()
    stack = [start_node_id]
    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        for neighbor in adjacency.get(current, []):
            if neighbor not in visited:
                stack.append(neighbor)

    return visited


def _adjacency_for_nodes(node_ids: set[str], edges_raw: Any) -> dict[str, list[str]]:
    adjacency: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    if not isinstance(edges_raw, list):
        return adjacency
    for edge in edges_raw:
        if not isinstance(edge, dict):
            continue
        from_id = str(edge.get("from") or "")
        to_id = str(edge.get("to") or "")
        if from_id in adjacency and to_id:
            adjacency[from_id].append(to_id)
    return adjacency


def _prune_state_for_nodes(state_json: dict[str, Any], node_ids: set[str]) -> dict[str, Any]:
    if not node_ids:
        return state_json

    prefixes = tuple(f"node.{node_id}" for node_id in node_ids)
    pruned: dict[str, Any] = {}
    for key, value in state_json.items():
        if isinstance(key, str) and key.startswith(prefixes):
            continue
        pruned[key] = value
    return pruned


def _set_if_changed(instance: Any, field_name: str, value: Any, update_fields: list[str]) -> None:
    if value is _UNSET or getattr(instance, field_name) == value:
        return
    setattr(instance, field_name, value)
    update_fields.append(field_name)


def _run_audit_metadata(
    *,
    graph_version: GraphVersion,
    thread_id: UUID | None,
    trigger: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "graph_id": str(graph_version.graph_id),
        "graph_name": graph_version.graph.name,
        "graph_version_id": str(graph_version.id),
        "graph_version": graph_version.version,
        "trigger": trigger,
    }
    if thread_id is not None:
        metadata["thread_id"] = str(thread_id)
    if extra:
        metadata.update(extra)
    return metadata


def _tenant_active_run_count(tenant_uuid: UUID) -> int:
    return Run.objects.filter(
        Q(organization_id=tenant_uuid)
        | Q(organization__isnull=True, owner__default_organization_id=tenant_uuid),
        status__in=["pending", "running", "paused", "resume_requested"],
    ).count()


def _active_run_guardrail_response(*, tenant_uuid: UUID) -> Response | None:
    max_active = int(getattr(settings, "RUN_MAX_ACTIVE_PER_TENANT", 0))
    if max_active <= 0:
        return None
    active_runs = _tenant_active_run_count(tenant_uuid)
    if active_runs < max_active:
        return None
    return error_response(
        code="RATE_LIMITED",
        message="Too many active runs for this tenant. Wait for current runs to finish.",
        status=status.HTTP_429_TOO_MANY_REQUESTS,
        details=[
            {
                "field": "active_runs",
                "issue": f"limit={max_active}, current={active_runs}",
            }
        ],
    )


def _input_size_guardrail_response(input_json: dict[str, Any]) -> Response | None:
    max_bytes = int(getattr(settings, "RUN_INPUT_MAX_BYTES", 0))
    if max_bytes <= 0:
        return None
    serialized = pyjson.dumps(input_json, ensure_ascii=False, separators=(",", ":"))
    payload_bytes = len(serialized.encode("utf-8"))
    if payload_bytes <= max_bytes:
        return None
    return error_response(
        code="VALIDATION_ERROR",
        message="input_json is too large for a single run.",
        status=status.HTTP_400_BAD_REQUEST,
        details=[
            {
                "field": "input_json",
                "issue": f"max_bytes={max_bytes}, actual_bytes={payload_bytes}",
            }
        ],
    )


def _input_schema_validation_response(
    graph_json: dict[str, Any],
    input_json: dict[str, Any],
) -> Response | None:
    input_schema, _, _, _ = extract_schema_metadata(graph_json)
    if not input_schema:
        return None
    try:
        schema_errors = validate_json_schema(input_json, input_schema)
    except SchemaError as exc:
        return error_response(
            code="INVALID_SCHEMA",
            message="Input schema is invalid.",
            status=status.HTTP_400_BAD_REQUEST,
            details=[{"message": str(exc)}],
        )
    if not schema_errors:
        return None
    return error_response(
        code="INVALID_INPUT_SCHEMA",
        message="Input does not match the required schema.",
        status=status.HTTP_400_BAD_REQUEST,
        details=schema_errors,
    )


def _project_pause_state(
    *,
    run: Run,
    node_id: str,
    node_type: str,
    attempt: int,
    pause_payload: dict[str, Any],
    trace_id: str,
    span_id: str,
    event_time: datetime | None,
) -> None:
    if not node_id:
        return

    normalized_node_type = node_type or "human_gate"
    node_defaults: dict[str, Any] = {
        "node_type": normalized_node_type,
        "status": "waiting",
    }
    if event_time:
        node_defaults["started_at"] = event_time
    if pause_payload:
        node_defaults["output_json"] = {"pause_payload": pause_payload}

    with transaction.atomic():
        node_run, created = NodeRun.objects.get_or_create(
            run=run,
            node_id=node_id,
            attempt=attempt,
            defaults=node_defaults,
        )
        node_update_fields: list[str] = []
        if not created:
            _set_if_changed(node_run, "node_type", normalized_node_type, node_update_fields)
        _set_if_changed(node_run, "status", "waiting", node_update_fields)
        if event_time:
            _set_if_changed(node_run, "started_at", event_time, node_update_fields)
        if pause_payload:
            output_json = (
                dict(node_run.output_json) if isinstance(node_run.output_json, dict) else {}
            )
            output_json["pause_payload"] = pause_payload
            _set_if_changed(node_run, "output_json", output_json, node_update_fields)
        _set_if_changed(node_run, "trace_id", trace_id, node_update_fields)
        _set_if_changed(node_run, "span_id", span_id, node_update_fields)
        if node_update_fields:
            node_run.save(update_fields=sorted(set(node_update_fields)))
        lifecycle_result = transition_from_node_run(
            run=run,
            node_run=node_run,
            source="engine_callback",
            idempotency_key=f"task:{run.id}:{node_id}:pause:{attempt}:{event_time.isoformat() if event_time else 'unknown'}",
            reason="human decision gate paused execution",
            occurred_at=event_time,
        )

        approval_payload = {
            "prompt_message": str(pause_payload.get("prompt_message") or ""),
            "required_fields": list(pause_payload.get("required_fields") or []),
        }
        approval_task, created = ApprovalTask.objects.get_or_create(
            run=run,
            node_id=node_id,
            status="pending",
            defaults={
                "assignee": run.owner,
                "payload": approval_payload,
                "task_lifecycle": lifecycle_result.lifecycle_task,
            },
        )
        update_fields: list[str] = []
        if not created:
            _set_if_changed(approval_task, "payload", approval_payload, update_fields)
        _set_if_changed(
            approval_task,
            "task_lifecycle",
            lifecycle_result.lifecycle_task,
            update_fields,
        )
        if update_fields:
            approval_task.save(update_fields=sorted(set(update_fields)))


def _project_run_event_state(
    *,
    run: Run,
    projection_status: str,
    trace_id: str,
    event_type: str,
    event_id: str | None,
    event_time: datetime | None,
    started_at: datetime | object = _UNSET,
    ended_at: datetime | object = _UNSET,
    output_json: Any = _UNSET,
    error_message: str | object = _UNSET,
    pause_state_json: Any = _UNSET,
    paused_node_id: str | None | object = _UNSET,
) -> None:
    projection, _ = RunEventProjection.objects.get_or_create(
        run=run,
        defaults={
            "status": projection_status,
            "trace_id": trace_id,
            "last_event_type": event_type,
            "last_event_id": event_id or "",
            "last_event_at": event_time or timezone.now(),
        },
    )

    update_fields: list[str] = []
    _set_if_changed(projection, "status", projection_status, update_fields)
    _set_if_changed(projection, "started_at", started_at, update_fields)
    _set_if_changed(projection, "ended_at", ended_at, update_fields)
    _set_if_changed(projection, "output_json", output_json, update_fields)
    if error_message is not _UNSET:
        _set_if_changed(projection, "error_message", cast(str, error_message), update_fields)
    _set_if_changed(projection, "pause_state_json", pause_state_json, update_fields)
    _set_if_changed(projection, "paused_node_id", paused_node_id, update_fields)
    _set_if_changed(projection, "trace_id", trace_id, update_fields)
    _set_if_changed(projection, "last_event_type", event_type, update_fields)
    next_event_id = event_id or ""
    _set_if_changed(projection, "last_event_id", next_event_id, update_fields)
    effective_event_time = event_time or timezone.now()
    _set_if_changed(projection, "last_event_at", effective_event_time, update_fields)
    if update_fields:
        projection.save(update_fields=sorted(set(update_fields)))


def _project_node_event_state(
    *,
    run: Run,
    node_id: str,
    node_type: str,
    attempt: int,
    projection_status: str,
    trace_id: str,
    span_id: str,
    event_type: str,
    event_id: str | None,
    event_time: datetime | None,
    started_at: datetime | object = _UNSET,
    ended_at: datetime | object = _UNSET,
    output_json: Any = _UNSET,
    error_json: Any = _UNSET,
) -> None:
    if not node_id:
        return

    projection, _ = NodeRunEventProjection.objects.get_or_create(
        run=run,
        node_id=node_id,
        attempt=attempt,
        defaults={
            "node_type": node_type,
            "status": projection_status,
            "trace_id": trace_id,
            "span_id": span_id,
            "last_event_type": event_type,
            "last_event_id": event_id or "",
            "last_event_at": event_time or timezone.now(),
        },
    )

    update_fields: list[str] = []
    _set_if_changed(projection, "node_type", node_type, update_fields)
    _set_if_changed(projection, "status", projection_status, update_fields)
    _set_if_changed(projection, "started_at", started_at, update_fields)
    _set_if_changed(projection, "ended_at", ended_at, update_fields)
    _set_if_changed(projection, "output_json", output_json, update_fields)
    _set_if_changed(projection, "error_json", error_json, update_fields)
    _set_if_changed(projection, "trace_id", trace_id, update_fields)
    _set_if_changed(projection, "span_id", span_id, update_fields)
    _set_if_changed(projection, "last_event_type", event_type, update_fields)
    next_event_id = event_id or ""
    _set_if_changed(projection, "last_event_id", next_event_id, update_fields)
    effective_event_time = event_time or timezone.now()
    _set_if_changed(projection, "last_event_at", effective_event_time, update_fields)
    if update_fields:
        projection.save(update_fields=sorted(set(update_fields)))


__all__ = [name for name in globals() if not name.startswith("__")]
