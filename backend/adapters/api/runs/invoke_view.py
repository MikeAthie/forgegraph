"""Run API command adapter module."""

# ruff: noqa: F403,F405,I001

from adapters.api.runs.common import *  # noqa: F403
from adapters.api.runs.command_dispatch import *  # noqa: F403


class RunInvokeView(APIView):
    """Invoke a threaded run using persisted state."""

    permission_classes = [IsAuthenticated]

    def _validated_invoke_serializer(self, request: Request) -> tuple[Any | None, Response | None]:
        serializer = RunInvokeSerializer(data=request.data)
        if serializer.is_valid():
            return serializer, None
        return None, error_response(
            code="VALIDATION_ERROR",
            message="The request contains invalid fields",
            status=status.HTTP_400_BAD_REQUEST,
            details=[
                {"field": field, "issue": ", ".join(errors)}
                for field, errors in serializer.errors.items()
            ],
        )

    def _invoke_policy_response(self, user: User) -> Response | None:
        quota_response = check_llm_quota(user)
        if quota_response is not None:
            return quota_response
        return check_llm_budget(user)

    def _active_thread_response(self, user: User, thread_id: UUID) -> Response | None:
        active_run = (
            run_queryset_for_user(user)
            .filter(
                thread_id=thread_id,
                status__in=["pending", "running", "paused", "resume_requested"],
            )
            .order_by("-started_at")
            .first()
        )
        if not active_run:
            return None
        return error_response(
            code="INVALID_STATE",
            message=f"Thread '{thread_id}' has an active run ({active_run.id}).",
            status=status.HTTP_400_BAD_REQUEST,
        )

    def _latest_thread_run(
        self,
        user: User,
        thread_id: UUID,
    ) -> tuple[Run | None, Response | None]:
        latest_run = (
            run_queryset_for_user(user)
            .filter(thread_id=thread_id)
            .select_related("graph_version__graph")
            .order_by(
                Case(
                    When(started_at__isnull=True, then=1),
                    default=0,
                    output_field=IntegerField(),
                ),
                "-started_at",
            )
            .first()
        )
        if latest_run is not None:
            return latest_run, None
        return None, error_response(
            code="NOT_FOUND",
            message=f"Thread with id '{thread_id}' not found",
            status=status.HTTP_404_NOT_FOUND,
        )

    def _run_checkpoint(self, run: Run) -> tuple[RunCheckpoint | None, Response | None]:
        try:
            return run.checkpoint, None
        except RunCheckpoint.DoesNotExist:
            return None, error_response(
                code="NO_CHECKPOINT",
                message="No persisted state found for this thread.",
                status=status.HTTP_409_CONFLICT,
            )

    def _prepare_invoke_dispatch_graph(
        self,
        *,
        request: Request,
        graph_version: GraphVersion,
        user: User,
        llm_access: LLMAccessConfig,
        input_json: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, dict[str, str] | None, Response | None]:
        try:
            traceparent, tracestate = _request_trace_headers(request)
            graph_json = prepare_graph_for_engine(
                graph_version.graph_json,
                user,
                company_id=graph_version.graph_id,
                traceparent=traceparent,
                tracestate=tracestate,
            )
            graph_json = attach_llm_access_to_graph(graph_json, llm_access)
        except LLMAccessValidationError as exc:
            return None, None, _llm_access_error_response(exc)
        except (PromptTemplateResolutionError, SubgraphResolutionError, ValueError) as exc:
            return None, None, _run_preparation_error_response(exc)

        response = self._invoke_dispatch_graph_response(
            user=user,
            graph_version=graph_version,
            graph_json=graph_json,
            input_json=input_json,
            llm_access=llm_access,
        )
        if response is not None:
            return None, None, response
        return graph_json, _trace_metadata_from_graph(graph_json), None

    def _invoke_input_json(
        self,
        validated_data: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, Response | None]:
        input_json = validated_data.get("input_json") or {}
        input_size_response = _input_size_guardrail_response(input_json)
        if input_size_response is not None:
            return None, input_size_response
        if isinstance(input_json, dict):
            return input_json, None
        return None, error_response(
            code="VALIDATION_ERROR",
            message="input_json must be a JSON object",
            status=status.HTTP_400_BAD_REQUEST,
        )

    def _invoke_llm_access(
        self,
        validated_data: dict[str, Any],
        user: User,
    ) -> tuple[LLMAccessConfig | None, Response | None]:
        try:
            return resolve_llm_access_for_dispatch(validated_data["llm_access"], user), None
        except LLMAccessValidationError as exc:
            return None, _llm_access_error_response(exc)

    def _invoke_thread_checkpoint(
        self,
        *,
        user: User,
        thread_id: UUID,
    ) -> tuple[Run | None, RunCheckpoint | None, Response | None]:
        active_response = self._active_thread_response(user, thread_id)
        if active_response is not None:
            return None, None, active_response

        latest_run, latest_response = self._latest_thread_run(user, thread_id)
        if latest_response is not None:
            return None, None, latest_response
        assert latest_run is not None

        checkpoint, checkpoint_response = self._run_checkpoint(latest_run)
        if checkpoint_response is not None:
            return None, None, checkpoint_response
        assert checkpoint is not None
        return latest_run, checkpoint, None

    def _invoke_dispatch_graph_response(
        self,
        *,
        user: User,
        graph_version: GraphVersion,
        graph_json: dict[str, Any],
        input_json: dict[str, Any],
        llm_access: LLMAccessConfig,
    ) -> Response | None:
        managed_limit_response = _managed_llm_limit_response(
            user=user,
            graph_json=graph_json,
            llm_access=llm_access,
        )
        if managed_limit_response is not None:
            return managed_limit_response

        credential_errors = validate_prompt_credentials(graph_json, user, llm_access=llm_access)
        if credential_errors:
            return error_response(
                code="INVALID_CREDENTIALS",
                message="Prompt node credentials are missing or invalid.",
                status=status.HTTP_400_BAD_REQUEST,
                details=credential_errors,
            )
        return _input_schema_validation_response(graph_version.graph_json, input_json)

    def _build_invoke_request_context(
        self,
        request: Request,
    ) -> tuple[RunInvokeRequestContext | None, Response | None]:
        serializer, serializer_response = self._validated_invoke_serializer(request)
        if serializer_response is not None:
            return None, serializer_response
        assert serializer is not None

        user = cast(User, request.user)
        if not has_min_role(user, "member"):
            return None, error_response(
                code="FORBIDDEN",
                message="You don't have permission to invoke runs in this organization.",
                status=status.HTTP_403_FORBIDDEN,
            )
        tenant_id = get_tenant_id_for_user(user)
        command_context = build_idempotency_context(
            request=request,
            organization=user.default_organization,
            action="runs.invoke",
            request_payload=serializer.validated_data,
        )
        replayed_response = _replayed_command_response(command_context)
        if replayed_response is not None:
            return None, replayed_response

        rate_limit_response = _apply_rate_limit(
            scope="run_invoke",
            tenant_id=tenant_id,
            limit=getattr(settings, "RUN_INVOKE_RATE_LIMIT_PER_MIN", 0),
            window_seconds=getattr(settings, "RUN_RATE_LIMIT_WINDOW_SECONDS", 60),
        )
        if rate_limit_response is not None:
            return None, rate_limit_response

        input_json, input_response = self._invoke_input_json(serializer.validated_data)
        if input_response is not None:
            return None, input_response
        assert input_json is not None

        llm_access, llm_response = self._invoke_llm_access(serializer.validated_data, user)
        if llm_response is not None:
            return None, llm_response
        assert llm_access is not None

        policy_response = self._invoke_policy_response(user)
        if policy_response is not None:
            return None, policy_response

        thread_id = serializer.validated_data["thread_id"]
        latest_run, checkpoint, thread_response = self._invoke_thread_checkpoint(
            user=user,
            thread_id=thread_id,
        )
        if thread_response is not None:
            return None, thread_response
        assert checkpoint is not None
        assert latest_run is not None

        tenant_uuid = UUID(tenant_id)
        active_guardrail_response = _active_run_guardrail_response(tenant_uuid=tenant_uuid)
        if active_guardrail_response is not None:
            return None, active_guardrail_response

        return RunInvokeRequestContext(
            user=user,
            tenant_id=tenant_id,
            tenant_uuid=tenant_uuid,
            command_context=command_context,
            thread_id=thread_id,
            session_id=str(thread_id),
            input_json=input_json,
            llm_access=llm_access,
            latest_run=latest_run,
            checkpoint=checkpoint,
        ), None

    def post(self, request: Request) -> Response:
        invoke_context, context_response = self._build_invoke_request_context(request)
        if context_response is not None:
            return context_response
        assert invoke_context is not None
        user = invoke_context.user
        tenant_id = invoke_context.tenant_id
        command_context = invoke_context.command_context
        thread_id = invoke_context.thread_id
        session_id = invoke_context.session_id
        input_json = invoke_context.input_json
        llm_access = invoke_context.llm_access
        latest_run = invoke_context.latest_run
        checkpoint = invoke_context.checkpoint

        graph_version = latest_run.graph_version
        graph_json, trace_metadata, prepare_response = self._prepare_invoke_dispatch_graph(
            request=request,
            graph_version=graph_version,
            user=user,
            llm_access=llm_access,
            input_json=input_json,
        )
        if prepare_response is not None:
            return prepare_response
        assert graph_json is not None and trace_metadata is not None
        checkpoint_graph_json = pyjson.dumps(graph_json)

        seed_state = checkpoint.state_json if isinstance(checkpoint.state_json, dict) else {}
        seed_state = dict(seed_state)
        for key, value in input_json.items():
            seed_state[f"input.{key}"] = value

        try:
            with transaction.atomic():
                run = Run.objects.create(
                    owner=user,
                    organization=graph_version.graph.organization or user.default_organization,
                    graph_version=graph_version,
                    thread_id=thread_id,
                    status="pending",
                    started_at=timezone.now(),
                    ended_at=None,
                    input_json=input_json,
                    dispatch_graph_json=graph_json,
                    output_json=None,
                    error_message="",
                    trace_id=trace_metadata["trace_id"],
                )
                outbound_graph = prepare_tool_executions_for_dispatch(
                    run=run,
                    graph_json=graph_json,
                )
                outbound_graph = _attach_operation_context_pack(run, outbound_graph)
                checkpoint_graph_json = pyjson.dumps(outbound_graph)

                RunCheckpoint.objects.create(
                    run=run,
                    node_id="seed",
                    step_index=0,
                    state_json=seed_state,
                    completed_nodes=[],
                    skipped_nodes=[],
                    graph_json=checkpoint_graph_json,
                )
        except ToolExecutionDispatchBlocked as exc:
            return _tool_execution_dispatch_error_response(exc)

        broadcast_run_updated(run)
        record_audit_log(
            actor=user,
            tenant_id=get_tenant_id_for_user(user),
            action="run.started",
            resource_type="run",
            resource_id=str(run.id),
            metadata=_run_audit_metadata(
                graph_version=graph_version,
                thread_id=thread_id,
                trigger="invoke",
                extra={"source_run_id": str(latest_run.id)},
            ),
        )

        upsert_memory_session(user, session_id)

        if getattr(settings, "RUN_QUEUE_ENABLED", False):
            queue_entry = enqueue_run(run, tenant_id=tenant_id)
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
            response = success_response(
                serialized_data,
                status=status.HTTP_201_CREATED,
                meta=_queue_response_meta(run=run, tenant_id=tenant_id),
            )
            return record_processed_command(
                context=command_context,
                response=response,
                resource_type="run",
                resource_id=str(run.id),
            )

        dispatch_response = _dispatch_run_to_engine(
            RunEngineDispatch(
                run=run,
                graph_version=graph_version,
                outbound_graph=outbound_graph,
                input_json=input_json,
                llm_access=llm_access,
                session_id=session_id,
                tenant_id=get_tenant_id(request),
                trace_metadata=trace_metadata,
                span_name="runs.invoke",
                trigger="invoke",
            )
        )
        if dispatch_response is not None:
            return dispatch_response

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
            context=command_context,
            response=response,
            resource_type="run",
            resource_id=str(run.id),
        )
