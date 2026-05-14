"""Run API command adapter module."""

# ruff: noqa: F403,F405,I001

from adapters.api.runs.common import *  # noqa: F403
from adapters.api.runs.command_dispatch import *  # noqa: F403


class RunStartView(APIView):
    """Start a run."""

    permission_classes = [IsAuthenticated]

    def _build_start_request_context(
        self,
        request: Request,
    ) -> tuple[RunStartRequestContext | None, Response | None]:
        serializer = RunStartSerializer(data=request.data)
        if not serializer.is_valid():
            return None, error_response(
                code="VALIDATION_ERROR",
                message="The request contains invalid fields",
                status=status.HTTP_400_BAD_REQUEST,
                details=[
                    {"field": field, "issue": ", ".join(errors)}
                    for field, errors in serializer.errors.items()
                ],
            )

        user = cast(User, request.user)
        if not has_min_role(user, "member"):
            return None, error_response(
                code="FORBIDDEN",
                message="You don't have permission to start runs in this organization.",
                status=status.HTTP_403_FORBIDDEN,
            )
        tenant_id = get_tenant_id_for_user(user)
        command_context = build_idempotency_context(
            request=request,
            organization=user.default_organization,
            action="runs.start",
            request_payload=serializer.validated_data,
        )
        replayed_response = _replayed_command_response(command_context)
        if replayed_response is not None:
            return None, replayed_response

        rate_limit_response = _apply_rate_limit(
            scope="run_start",
            tenant_id=tenant_id,
            limit=getattr(settings, "RUN_START_RATE_LIMIT_PER_MIN", 0),
            window_seconds=getattr(settings, "RUN_RATE_LIMIT_WINDOW_SECONDS", 60),
        )
        if rate_limit_response is not None:
            return None, rate_limit_response

        input_json = serializer.validated_data.get("input_json") or {}
        input_size_response = _input_size_guardrail_response(input_json)
        if input_size_response is not None:
            return None, input_size_response
        tenant_uuid = UUID(tenant_id)
        active_guardrail_response = _active_run_guardrail_response(tenant_uuid=tenant_uuid)
        if active_guardrail_response is not None:
            return None, active_guardrail_response

        thread_id = serializer.validated_data.get("thread_id")
        return RunStartRequestContext(
            user=user,
            tenant_id=tenant_id,
            tenant_uuid=tenant_uuid,
            command_context=command_context,
            graph_version_id=serializer.validated_data["graph_version_id"],
            input_json=input_json,
            llm_access=serializer.validated_data["llm_access"],
            thread_id=thread_id,
            session_id=str(thread_id) if thread_id else None,
        ), None

    def _start_policy_response(self, user: User) -> Response | None:
        entitlement_response = check_entitlements(user)
        if entitlement_response is not None:
            return entitlement_response
        quota_response = check_llm_quota(user)
        if quota_response is not None:
            return quota_response
        return check_llm_budget(user)

    def _start_input_schema_response(
        self,
        *,
        graph_version: GraphVersion,
        input_json: dict[str, Any],
    ) -> Response | None:
        input_schema, _, _, _ = extract_schema_metadata(graph_version.graph_json)
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

    def _start_credentials_response(
        self,
        *,
        user: User,
        prepared_graph: dict[str, Any],
        llm_access: LLMAccessConfig,
    ) -> Response | None:
        managed_limit_response = _managed_llm_limit_response(
            user=user,
            graph_json=prepared_graph,
            llm_access=llm_access,
        )
        if managed_limit_response is not None:
            return managed_limit_response

        credential_errors = validate_prompt_credentials(
            prepared_graph,
            user,
            llm_access=llm_access,
        )
        if not credential_errors:
            return None
        return error_response(
            code="INVALID_CREDENTIALS",
            message="Prompt node credentials are missing or invalid.",
            status=status.HTTP_400_BAD_REQUEST,
            details=credential_errors,
        )

    def _start_graph_version(
        self,
        *,
        tenant_uuid: UUID,
        graph_version_id: UUID,
    ) -> tuple[GraphVersion | None, Response | None]:
        try:
            return (
                GraphVersion.objects.select_related("graph")
                .filter(
                    Q(graph__organization_id=tenant_uuid)
                    | Q(
                        graph__organization__isnull=True,
                        graph__owner__default_organization_id=tenant_uuid,
                    ),
                    id=graph_version_id,
                )
                .get()
            ), None
        except GraphVersion.DoesNotExist:
            return None, error_response(
                code="NOT_FOUND",
                message=(
                    f"GraphVersion with id '{graph_version_id}' not found "
                    "or you do not have access to it"
                ),
                status=status.HTTP_404_NOT_FOUND,
            )

    def _prepare_start_dispatch_graph(
        self,
        *,
        request: Request,
        context: RunStartRequestContext,
        mark: Callable[[str], None],
    ) -> tuple[
        GraphVersion | None,
        dict[str, Any] | None,
        dict[str, str] | None,
        LLMAccessConfig | None,
        Response | None,
    ]:
        graph_version, graph_response = self._start_graph_version(
            tenant_uuid=context.tenant_uuid,
            graph_version_id=context.graph_version_id,
        )
        if graph_response is not None:
            return None, None, None, None, graph_response
        assert graph_version is not None
        mark("graph_loaded")

        try:
            llm_access = resolve_llm_access_for_dispatch(context.llm_access, context.user)
        except LLMAccessValidationError as exc:
            return None, None, None, None, _llm_access_error_response(exc)

        policy_response = self._start_policy_response(context.user)
        if policy_response is not None:
            return None, None, None, None, policy_response
        mark("policy_checked")

        schema_response = self._start_input_schema_response(
            graph_version=graph_version,
            input_json=context.input_json,
        )
        if schema_response is not None:
            return None, None, None, None, schema_response

        try:
            traceparent, tracestate = _request_trace_headers(request)
            prepared_graph = prepare_graph_for_engine(
                graph_version.graph_json,
                context.user,
                company_id=graph_version.graph_id,
                traceparent=traceparent,
                tracestate=tracestate,
            )
            prepared_graph = attach_llm_access_to_graph(prepared_graph, llm_access)
        except LLMAccessValidationError as exc:
            return None, None, None, None, _llm_access_error_response(exc)
        except (PromptTemplateResolutionError, SubgraphResolutionError, ValueError) as exc:
            return None, None, None, None, _run_preparation_error_response(exc)

        trace_metadata = _trace_metadata_from_graph(prepared_graph)
        mark("graph_prepared")
        credentials_response = self._start_credentials_response(
            user=context.user,
            prepared_graph=prepared_graph,
            llm_access=llm_access,
        )
        if credentials_response is not None:
            return None, None, None, None, credentials_response
        mark("credentials_checked")
        return graph_version, prepared_graph, trace_metadata, llm_access, None

    def _create_start_run(
        self,
        *,
        context: RunStartRequestContext,
        graph_version: GraphVersion,
        prepared_graph: dict[str, Any],
        trace_metadata: dict[str, str],
    ) -> Run:
        return Run.objects.create(
            owner=context.user,
            organization=graph_version.graph.organization or context.user.default_organization,
            graph_version=graph_version,
            thread_id=context.thread_id,
            status="pending",
            started_at=timezone.now(),
            ended_at=None,
            input_json=context.input_json,
            dispatch_graph_json=prepared_graph,
            output_json=None,
            error_message="",
            trace_id=trace_metadata["trace_id"],
        )

    def _initialize_start_run(
        self,
        *,
        context: RunStartRequestContext,
        graph_version: GraphVersion,
        run: Run,
        queue_enabled: bool,
        mark: Callable[[str], None],
    ) -> None:
        initialize_lifecycle_tasks_for_run(
            run,
            source="run_start",
            initial_status="queued" if queue_enabled else "created",
            reason=(
                "run queued for backend-owned dispatch"
                if queue_enabled
                else "task initialized from graph"
            ),
        )
        mark("lifecycle_initialized")
        if not queue_enabled:
            broadcast_run_updated(run)
            mark("run_broadcast")
        record_audit_log(
            actor=context.user,
            tenant_id=get_tenant_id_for_user(context.user),
            action="run.started",
            resource_type="run",
            resource_id=str(run.id),
            metadata=_run_audit_metadata(
                graph_version=graph_version,
                thread_id=context.thread_id,
                trigger="start",
            ),
        )
        mark("audit_recorded")
        upsert_memory_session(context.user, context.session_id)
        mark("memory_session")

    def _queued_start_response(
        self,
        *,
        context: RunStartRequestContext,
        graph_version: GraphVersion,
        run: Run,
        timing_started_at: float,
        timing_marks: list[tuple[str, float]],
        mark: Callable[[str], None],
    ) -> Response:
        queue_entry = enqueue_run(run, tenant_id=context.tenant_id)
        mark("run_enqueued")
        run_data = {
            "id": run.id,
            "owner_id": run.owner_id,
            "owner_email": run.owner.email,
            "thread_id": run.thread_id,
            "graph_id": graph_version.graph_id,
            "graph_name": graph_version.graph.name,
            "graph_version_id": graph_version.id,
            "graph_version": graph_version.version,
            "status": run.status,
            "queue_status": queue_entry.status,
            "queue_attempts": queue_entry.attempts,
            "queue_available_at": queue_entry.available_at,
            "started_at": run.started_at,
            "ended_at": run.ended_at,
            "input_json": redact_payload(run.input_json),
            "output_json": redact_payload(run.output_json),
            "error_message": redact_payload(run.error_message),
            "duration_ms": run.duration_ms,
            "trace_id": run.trace_id,
            "llm_access": _public_llm_access_payload(run),
            "node_runs": [],
        }
        serialized_data = RunDetailWithNodeRunsSerializer(run_data).data
        mark("serialized")
        response = success_response(
            serialized_data,
            status=status.HTTP_201_CREATED,
            meta=_queue_response_meta(run=run, tenant_id=context.tenant_id),
        )
        mark("response_built")
        response = record_processed_command(
            context=context.command_context,
            response=response,
            resource_type="run",
            resource_id=str(run.id),
        )
        mark("processed_command_recorded")
        _log_run_start_timing(
            run=run,
            tenant_id=context.tenant_id,
            queued=True,
            started_at=timing_started_at,
            marks=timing_marks,
        )
        return response

    def _dispatch_start_run(
        self,
        *,
        request: Request,
        context: RunStartRequestContext,
        graph_version: GraphVersion,
        run: Run,
        prepared_graph: dict[str, Any],
        trace_metadata: dict[str, str],
        llm_access: LLMAccessConfig,
    ) -> Response | None:
        try:
            outbound_graph = prepare_tool_executions_for_dispatch(
                run=run,
                graph_json=prepared_graph,
            )
            outbound_graph = _attach_operation_context_pack(run, outbound_graph)
        except ToolExecutionDispatchBlocked as exc:
            transition = apply_run_status_transition(run, "failed")
            run.ended_at = timezone.now()
            run.error_message = str(exc)
            run.save(
                update_fields=sorted(set(transition.update_fields + ["ended_at", "error_message"]))
            )
            mark_run_tasks_terminal(
                run=run,
                status_value="failed",
                source="run_start",
                reason=str(exc),
            )
            return _tool_execution_dispatch_error_response(exc)

        return _dispatch_run_to_engine(
            RunEngineDispatch(
                run=run,
                graph_version=graph_version,
                outbound_graph=outbound_graph,
                input_json=context.input_json,
                llm_access=llm_access,
                session_id=context.session_id,
                tenant_id=get_tenant_id(request),
                trace_metadata=trace_metadata,
                span_name="runs.start",
                trigger="start",
                failure_task_source="run_start",
            )
        )

    def _started_run_response(
        self,
        *,
        context: RunStartRequestContext,
        graph_version: GraphVersion,
        run: Run,
    ) -> Response:
        run_data = {
            "id": run.id,
            "owner_id": run.owner_id,
            "owner_email": run.owner.email,
            "thread_id": run.thread_id,
            "graph_id": graph_version.graph_id,
            "graph_name": graph_version.graph.name,
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
            "llm_access": _public_llm_access_payload(run),
            "node_runs": [],
        }
        serialized_data = RunDetailWithNodeRunsSerializer(run_data).data
        response = success_response(serialized_data, status=status.HTTP_201_CREATED)
        return record_processed_command(
            context=context.command_context,
            response=response,
            resource_type="run",
            resource_id=str(run.id),
        )

    def post(self, request: Request) -> Response:
        """Start a new run."""
        timing_started_at = time.perf_counter()
        timing_marks: list[tuple[str, float]] = []

        def mark(stage: str) -> None:
            timing_marks.append((stage, time.perf_counter()))

        start_context, context_response = self._build_start_request_context(request)
        if context_response is not None:
            return context_response
        assert start_context is not None
        mark("validated")

        (
            graph_version,
            prepared_graph,
            trace_metadata,
            llm_access,
            prepare_response,
        ) = self._prepare_start_dispatch_graph(
            request=request,
            context=start_context,
            mark=mark,
        )
        if prepare_response is not None:
            return prepare_response
        assert graph_version is not None
        assert prepared_graph is not None
        assert trace_metadata is not None
        assert llm_access is not None

        run = self._create_start_run(
            context=start_context,
            graph_version=graph_version,
            prepared_graph=prepared_graph,
            trace_metadata=trace_metadata,
        )
        mark("run_created")
        queue_enabled = bool(getattr(settings, "RUN_QUEUE_ENABLED", False))
        self._initialize_start_run(
            context=start_context,
            graph_version=graph_version,
            run=run,
            queue_enabled=queue_enabled,
            mark=mark,
        )

        if queue_enabled:
            return self._queued_start_response(
                context=start_context,
                graph_version=graph_version,
                run=run,
                timing_started_at=timing_started_at,
                timing_marks=timing_marks,
                mark=mark,
            )

        dispatch_response = self._dispatch_start_run(
            request=request,
            context=start_context,
            graph_version=graph_version,
            run=run,
            prepared_graph=prepared_graph,
            trace_metadata=trace_metadata,
            llm_access=llm_access,
        )
        if dispatch_response is not None:
            return dispatch_response

        return self._started_run_response(
            context=start_context,
            graph_version=graph_version,
            run=run,
        )
