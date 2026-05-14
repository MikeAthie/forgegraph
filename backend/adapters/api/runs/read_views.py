"""Run API read adapters split from adapters.api.runs.views."""

# ruff: noqa: F403,F405,I001

from adapters.api.runs.common import *  # noqa: F403
from adapters.api.runs.command_views import RunStartView


class RunListView(APIView):
    """List runs (stub)."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        """Create and start a run using the same contract as /api/runs/start."""
        return RunStartView().post(request)

    def _base_runs_queryset(self, user: User) -> Any:
        return (
            run_queryset_for_user(user)
            .select_related("graph_version__graph", "queue_entry")
            .annotate(
                failed_node_count=Count(
                    "node_runs", filter=Q(node_runs__status="failed"), distinct=True
                )
            )
        )

    def _apply_run_uuid_filter(
        self,
        *,
        runs: Any,
        raw_value: str,
        filter_name: str,
        field_name: str,
    ) -> tuple[Any, Response | None]:
        if not raw_value:
            return runs, None
        try:
            parsed_uuid = UUID(raw_value)
        except ValueError:
            return runs, error_response(
                code="VALIDATION_ERROR",
                message=f"{filter_name} must be a valid UUID",
                status=status.HTTP_400_BAD_REQUEST,
            )
        return runs.filter(**{field_name: parsed_uuid}), None

    def _apply_run_datetime_filter(
        self,
        *,
        runs: Any,
        raw_value: str | None,
        filter_name: str,
        field_name: str,
    ) -> tuple[Any, Response | None]:
        if not raw_value:
            return runs, None
        parsed = parse_datetime(raw_value)
        if parsed is None:
            return runs, error_response(
                code="VALIDATION_ERROR",
                message=f"{filter_name} must be an ISO datetime.",
                status=status.HTTP_400_BAD_REQUEST,
            )
        return runs.filter(**{field_name: parsed}), None

    def _apply_run_list_filters(
        self, *, request: Request, runs: Any
    ) -> tuple[Any, Response | None]:
        status_filter = request.query_params.get("status")
        if status_filter:
            runs = runs.filter(status=status_filter)

        runs, error = self._apply_run_uuid_filter(
            runs=runs,
            raw_value=(request.query_params.get("graph_version_id") or "").strip(),
            filter_name="graph_version_id",
            field_name="graph_version_id",
        )
        if error is not None:
            return runs, error
        runs, error = self._apply_run_uuid_filter(
            runs=runs,
            raw_value=(request.query_params.get("graph_id") or "").strip(),
            filter_name="graph_id",
            field_name="graph_version__graph_id",
        )
        if error is not None:
            return runs, error
        runs, error = self._apply_run_datetime_filter(
            runs=runs,
            raw_value=request.query_params.get("started_after"),
            filter_name="started_after",
            field_name="started_at__gte",
        )
        if error is not None:
            return runs, error
        return self._apply_run_datetime_filter(
            runs=runs,
            raw_value=request.query_params.get("started_before"),
            filter_name="started_before",
            field_name="started_at__lte",
        )

    def _apply_failed_nodes_filter(self, *, request: Request, runs: Any) -> Any:
        has_failed_nodes_raw = (request.query_params.get("has_failed_nodes") or "").strip().lower()
        if has_failed_nodes_raw in {"1", "true", "yes"}:
            return runs.filter(failed_node_count__gt=0)
        if has_failed_nodes_raw in {"0", "false", "no"}:
            return runs.filter(failed_node_count=0)
        return runs

    def _apply_run_list_pagination(self, *, request: Request, runs: Any) -> Any:
        limit_param = request.query_params.get("limit")
        offset_param = request.query_params.get("offset")
        limit: int | None = None
        offset = 0

        if offset_param is not None:
            try:
                offset = max(int(offset_param), 0)
            except (TypeError, ValueError):
                offset = 0

        if limit_param is not None:
            try:
                parsed_limit = int(limit_param)
            except (TypeError, ValueError):
                parsed_limit = 0
            if parsed_limit > 0:
                limit = parsed_limit

        if offset or limit is not None:
            end = None if limit is None else offset + limit
            return runs[offset:end]
        return runs

    def _serialize_run_list(self, runs: Any) -> list[dict[str, Any]]:
        result = []
        for run in runs:
            graph_version = run.graph_version
            graph = graph_version.graph
            result.append(
                {
                    "id": run.id,
                    "thread_id": run.thread_id,
                    "graph_id": graph.id,
                    "graph_name": graph.name,
                    "graph_version_id": graph_version.id,
                    "graph_version": graph_version.version,
                    "status": run.status,
                    "has_failed_nodes": bool(getattr(run, "failed_node_count", 0)),
                    **_queue_payload(run),
                    "started_at": run.started_at,
                    "ended_at": run.ended_at,
                    "duration_ms": run.duration_ms,
                    "trace_id": run.trace_id,
                    "last_progress_at": run.last_progress_at,
                    "last_heartbeat_at": run.last_heartbeat_at,
                    "engine_instance_id": run.engine_instance_id,
                    "recovery_state": run.recovery_state,
                    "recovery_reason": run.recovery_reason,
                    "recovery_policy": run.recovery_policy,
                    "resume_requested_at": run.resume_requested_at,
                    "resume_attempt_id": run.resume_attempt_id,
                    "memory_activity": summarize_run_memory_activity(
                        list(run.node_runs.all()),
                        include_operations=False,
                    ),
                    "llm_access": _public_llm_access_payload(run),
                }
            )
        return result

    def get(self, request: Request) -> Response:
        """List user's runs."""
        user = cast(User, request.user)
        runs, filter_response = self._apply_run_list_filters(
            request=request,
            runs=self._base_runs_queryset(user),
        )
        if filter_response is not None:
            return filter_response
        runs = self._apply_failed_nodes_filter(request=request, runs=runs)

        runs = runs.order_by(
            Case(
                When(started_at__isnull=True, then=1),
                default=0,
                output_field=IntegerField(),
            ),
            "-started_at",
        )

        total_count = runs.count()
        runs = self._apply_run_list_pagination(request=request, runs=runs)

        runs = runs.prefetch_related(
            Prefetch(
                "node_runs",
                queryset=NodeRun.objects.only(
                    "id",
                    "run_id",
                    "node_id",
                    "node_type",
                    "status",
                    "attempt",
                    "started_at",
                    "ended_at",
                    "output_json",
                ).order_by("started_at", "attempt"),
            )
        )

        serialized_data = RunListSerializer(self._serialize_run_list(runs), many=True).data
        return success_response(serialized_data, meta={"total": total_count})


class RunDetailView(APIView):
    """Get run details (stub)."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, run_id: UUID) -> Response:
        """Get run details with node runs."""
        user = cast(User, request.user)
        node_runs_queryset = NodeRun.objects.order_by(
            Case(
                When(started_at__isnull=True, then=1),
                default=0,
                output_field=IntegerField(),
            ),
            "started_at",
            "attempt",
        )

        try:
            run = (
                run_queryset_for_user(user)
                .select_related("graph_version__graph", "queue_entry")
                .prefetch_related(Prefetch("node_runs", queryset=node_runs_queryset))
                .get(id=run_id)
            )
        except Run.DoesNotExist:
            return error_response(
                code="NOT_FOUND",
                message=f"Run with id '{run_id}' not found or you do not have access to it",
                status=status.HTTP_404_NOT_FOUND,
            )

        graph_version = run.graph_version
        graph = graph_version.graph

        # Get pause_payload from the waiting node run if available
        pause_payload = None
        if run.paused_node_id:
            waiting_node_run = run.node_runs.filter(
                node_id=run.paused_node_id, status="waiting"
            ).first()
            if waiting_node_run and waiting_node_run.output_json:
                pause_payload = waiting_node_run.output_json.get("pause_payload")
        node_runs = list(run.node_runs.all())
        agent_event_rows = list(
            RunEvent.objects.filter(run=run, event_type__startswith="agent.")
            .order_by("created_at", "id")
            .only("id", "event_type", "payload", "created_at")
        )
        agent_events: list[dict[str, Any]] = []
        agent_events_by_node: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
        for event_row in agent_event_rows:
            payload = redact_payload(event_row.payload or {})
            event_payload = {
                "id": str(event_row.id),
                "type": event_row.event_type,
                "created_at": event_row.created_at.isoformat(),
                **payload,
            }
            agent_events.append(event_payload)
            node_id = str(payload.get("node_id") or "")
            attempt = int(payload.get("attempt") or 1)
            if node_id:
                agent_events_by_node[(node_id, attempt)].append(event_payload)
        node_outcomes = {
            "pending": 0,
            "running": 0,
            "waiting": 0,
            "succeeded": 0,
            "failed": 0,
            "skipped": 0,
        }
        for node_run in node_runs:
            status_key = str(node_run.status)
            if status_key in node_outcomes:
                node_outcomes[status_key] += 1

        run_data = {
            "id": run.id,
            "owner_id": run.owner_id,
            "owner_email": run.owner.email,
            "thread_id": run.thread_id,
            "graph_id": graph.id,
            "graph_name": graph.name,
            "graph_version_id": graph_version.id,
            "graph_version": graph_version.version,
            "status": run.status,
            **_queue_payload(run),
            "started_at": run.started_at,
            "ended_at": run.ended_at,
            "input_json": redact_payload(run.input_json),
            "output_json": redact_payload(run.output_json),
            "error_message": redact_payload(run.error_message),
            "duration_ms": run.duration_ms,
            "backend_attempt_id": run.active_attempt_id,
            "status_history": _build_run_status_history(run=run),
            "trace_id": run.trace_id,
            "last_progress_at": run.last_progress_at,
            "last_heartbeat_at": run.last_heartbeat_at,
            "engine_instance_id": run.engine_instance_id,
            "recovery_state": run.recovery_state,
            "recovery_reason": run.recovery_reason,
            "recovery_policy": run.recovery_policy,
            "resume_requested_at": run.resume_requested_at,
            "resume_attempt_id": run.resume_attempt_id,
            "paused_node_id": run.paused_node_id,
            "pause_payload": redact_payload(pause_payload),
            "node_outcomes": node_outcomes,
            "agent_events": agent_events,
            "timeline": _build_run_timeline(run=run),
            "memory_activity": summarize_run_memory_activity(node_runs, include_operations=True),
            "llm_access": _public_llm_access_payload(run),
            "node_runs": [
                _serialize_node_run_for_detail(
                    node_run=node_run,
                    agent_events_by_node=agent_events_by_node,
                )
                for node_run in node_runs
            ],
        }

        serialized_data = RunDetailWithNodeRunsSerializer(run_data).data
        return success_response(serialized_data)
