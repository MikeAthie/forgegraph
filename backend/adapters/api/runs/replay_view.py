"""Run API command adapter module."""

# ruff: noqa: F403,F405,I001

from adapters.api.runs.common import *  # noqa: F403
from adapters.api.runs.command_dispatch import *  # noqa: F403


class RunReplayView(APIView):
    """Replay a completed run from its latest checkpoint."""

    permission_classes = [IsAuthenticated]

    def _event_safety_response(
        self,
        *,
        event_type: str,
        normalized_category: str,
        payload: dict[str, Any],
    ) -> Response | None:
        try:
            assert_runtime_state_mutation_allowed(
                event_type,
                category=normalized_category,
                payload=payload,
            )
        except EventSafetyViolation as exc:
            return problem_response(
                type_uri="https://forgegraph.dev/problems/event-safety-violation",
                title="Event safety violation",
                status=status.HTTP_409_CONFLICT,
                detail=str(exc),
            )
        return None

    def _run_output_schema_errors(
        self,
        *,
        run: Run,
        payload: dict[str, Any],
    ) -> tuple[str, list[dict[str, Any]] | None]:
        output_schema = None
        schema_mode = "warn"
        try:
            _, output_schema, _, schema_mode = extract_schema_metadata(run.graph_version.graph_json)
        except Exception:
            output_schema = None

        if not (
            output_schema and payload.get("status") == "succeeded" and "output_json" in payload
        ):
            return schema_mode, None
        try:
            return schema_mode, validate_json_schema(payload.get("output_json"), output_schema)
        except SchemaError as exc:
            log_event(
                logger,
                logging.WARNING,
                "run_output_schema_invalid",
                run_id=str(run.id),
                trace_id=run.trace_id,
                error_message=str(exc),
            )
            return schema_mode, None

    def _apply_authenticated_run_payload(
        self,
        *,
        run: Run,
        payload: dict[str, Any],
    ) -> None:
        update_fields: list[str] = []
        for field in ["status", "started_at", "ended_at", "output_json", "error_message"]:
            if field not in payload:
                continue
            value = payload[field]
            if field in {"output_json", "error_message"}:
                value = redact_payload(value)
            setattr(run, field, value)
            payload[field] = value
            update_fields.append(field)

        if "paused_node_id" in payload:
            run.paused_node_id = payload["paused_node_id"]
            update_fields.append("paused_node_id")
        if "pause_state_json" in payload:
            run.pause_state_json = redact_payload(payload["pause_state_json"])
            payload["pause_state_json"] = run.pause_state_json
            update_fields.append("pause_state_json")

        if update_fields:
            update_fields.extend(
                touch_run_liveness(
                    run,
                    recovery_state=recovery_state_for_status(run.status),
                    engine_instance_id=run.engine_instance_id or engine_instance_label(),
                )
            )
            run.save(update_fields=sorted(set(update_fields)))

    def _ensure_pause_approval_task(self, *, run: Run, payload: dict[str, Any]) -> None:
        if payload.get("status") != "paused":
            return
        pause_output = payload.get("pause_payload", {})
        node_id = run.paused_node_id or pause_output.get("node_id", "")
        if not node_id:
            return
        ApprovalTask.objects.get_or_create(
            run=run,
            node_id=node_id,
            status="pending",
            defaults={
                "assignee": run.owner,
                "payload": {
                    "prompt_message": pause_output.get("prompt_message", ""),
                    "required_fields": pause_output.get("required_fields", []),
                },
            },
        )

    def _persist_authenticated_schema_errors(
        self,
        *,
        run: Run,
        schema_mode: str,
        schema_errors: list[dict[str, Any]] | None,
    ) -> None:
        if not schema_errors:
            return
        try:
            RunEvent.objects.create(
                run=run,
                event_type="run.schema_validation",
                payload=redact_payload(
                    {
                        "errors": schema_errors,
                        "mode": schema_mode,
                        "category": normalize_event_category("run.schema_validation"),
                    }
                ),
            )
        except Exception as exc:  # pragma: no cover - log and continue
            log_event(
                logger,
                logging.WARNING,
                "schema_validation_event_persist_failed",
                run_id=str(run.id),
                trace_id=run.trace_id,
                error_message=str(exc),
            )

    def _persist_authenticated_run_event(
        self,
        *,
        run: Run,
        event_type: str,
        payload: dict[str, Any],
        normalized_category: str,
    ) -> None:
        try:
            RunEvent.objects.create(
                run=run,
                event_type=event_type,
                payload=_serialize_event_payload(
                    redact_payload(
                        {
                            **payload,
                            "category": normalized_category,
                        }
                    )
                ),
            )
        except Exception as exc:  # pragma: no cover - log and continue
            log_event(
                logger,
                logging.WARNING,
                "run_event_persist_failed",
                run_id=str(run.id),
                trace_id=run.trace_id,
                error_message=str(exc),
            )

    def _handle_authenticated_run_updated(
        self,
        *,
        run: Run,
        payload: dict[str, Any],
        event_type: str,
        normalized_category: str,
    ) -> Response:
        schema_mode, schema_errors = self._run_output_schema_errors(run=run, payload=payload)
        if schema_errors and schema_mode == "strict":
            payload["status"] = "failed"
            payload["error_message"] = (
                f"Output schema validation failed: {schema_errors[0]['message']}"
            )
        self._apply_authenticated_run_payload(run=run, payload=payload)
        self._ensure_pause_approval_task(run=run, payload=payload)
        self._persist_authenticated_schema_errors(
            run=run,
            schema_mode=schema_mode,
            schema_errors=schema_errors,
        )
        self._persist_authenticated_run_event(
            run=run,
            event_type=event_type,
            payload=payload,
            normalized_category=normalized_category,
        )
        return success_response(broadcast_run_updated(run))

    def _apply_authenticated_node_payload(
        self,
        *,
        node_run: NodeRun,
        created: bool,
        node_type: Any,
        payload: dict[str, Any],
    ) -> list[str]:
        node_update_fields: list[str] = []
        if not created and node_run.node_type != node_type:
            node_run.node_type = node_type
            node_update_fields.append("node_type")
        node_run.status = payload["status"]
        node_update_fields.append("status")
        for field in ["started_at", "ended_at", "input_json", "output_json", "error_json"]:
            if field not in payload:
                continue
            value = redact_payload(payload[field]) if field.endswith("_json") else payload[field]
            setattr(node_run, field, value)
            payload[field] = value
            node_update_fields.append(field)
        return node_update_fields

    def _handle_authenticated_node_run_updated(
        self,
        *,
        run: Run,
        payload: dict[str, Any],
        event_type: str,
        normalized_category: str,
    ) -> Response:
        node_id = payload["node_id"]
        node_type = payload["node_type"]
        attempt = payload["attempt"]
        with transaction.atomic():
            node_run, created = NodeRun.objects.get_or_create(
                run=run,
                node_id=node_id,
                attempt=attempt,
                defaults={
                    "node_type": node_type,
                    "status": payload["status"],
                },
            )
            node_update_fields = self._apply_authenticated_node_payload(
                node_run=node_run,
                created=created,
                node_type=node_type,
                payload=payload,
            )
            node_run.save(update_fields=sorted(set(node_update_fields)))
            run_update_fields = touch_run_liveness(
                run,
                recovery_state=recovery_state_for_status(run.status),
                engine_instance_id=run.engine_instance_id or engine_instance_label(),
            )
            run.save(update_fields=sorted(set(run_update_fields)))
            RunEvent.objects.create(
                run=run,
                event_type=event_type,
                payload=_serialize_event_payload(
                    redact_payload(
                        {
                            **payload,
                            "category": normalized_category,
                        }
                    )
                ),
            )

        return success_response(broadcast_node_run_updated(run=run, node_run=node_run))

    def _handle_authenticated_schema_validation(
        self,
        *,
        run: Run,
        payload: dict[str, Any],
        event_type: str,
        normalized_category: str,
    ) -> Response:
        try:
            RunEvent.objects.create(
                run=run,
                event_type=event_type,
                payload={
                    **payload,
                    "category": normalized_category,
                },
            )
        except Exception as exc:  # pragma: no cover - log and continue
            log_event(
                logger,
                logging.WARNING,
                "schema_validation_event_persist_failed",
                run_id=str(run.id),
                trace_id=run.trace_id,
                error_message=str(exc),
            )
        return success_response(broadcast_run_schema_validation(run=run, payload=payload))

    def _validated_replay_serializer(self, request: Request) -> tuple[Any | None, Response | None]:
        serializer = RunReplaySerializer(data=request.data)
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

    def _replay_source_run(
        self,
        *,
        user: User,
        run_id: UUID,
    ) -> tuple[Run | None, Response | None]:
        try:
            run = run_queryset_for_user(user).select_related("graph_version__graph").get(id=run_id)
        except Run.DoesNotExist:
            return None, error_response(
                code="NOT_FOUND",
                message=f"Run with id '{run_id}' not found or you do not have access to it",
                status=status.HTTP_404_NOT_FOUND,
            )
        if run.status not in {"pending", "running", "paused", "resume_requested"}:
            return run, None
        return None, error_response(
            code="INVALID_STATE",
            message=f"Cannot replay a run in status '{run.status}'. Run must be completed.",
            status=status.HTTP_400_BAD_REQUEST,
        )

    def _replay_llm_access(
        self,
        *,
        request: Request,
        serializer: Any,
        run: Run,
        user: User,
    ) -> tuple[LLMAccessConfig | None, Response | None]:
        request_overrides_llm_access = any(
            key in request.data for key in ("llm_mode", "provider", "credential_id", "api_key")
        )
        try:
            if request_overrides_llm_access:
                return resolve_llm_access_for_dispatch(
                    serializer.validated_data["llm_access"],
                    user,
                ), None
            return engine_llm_access_from_graph(
                run.dispatch_graph_json if isinstance(run.dispatch_graph_json, dict) else {},
                user,
            ), None
        except LLMAccessValidationError as exc:
            return None, _llm_access_error_response(exc)

    def _replay_checkpoint(self, run: Run) -> tuple[RunCheckpoint | None, Response | None]:
        try:
            return run.checkpoint, None
        except RunCheckpoint.DoesNotExist:
            return None, error_response(
                code="NO_CHECKPOINT",
                message="No checkpoint available for this run.",
                status=status.HTTP_409_CONFLICT,
            )

    def _active_replay_thread_response(self, *, user: User, run: Run) -> Response | None:
        if not run.thread_id:
            return None
        active_run = (
            run_queryset_for_user(user)
            .filter(
                thread_id=run.thread_id,
                status__in=["pending", "running", "paused", "resume_requested"],
            )
            .order_by("-started_at")
            .first()
        )
        if not active_run:
            return None
        return error_response(
            code="INVALID_STATE",
            message=f"Thread '{run.thread_id}' has an active run ({active_run.id}).",
            status=status.HTTP_400_BAD_REQUEST,
        )

    def _build_replay_request_context(
        self,
        request: Request,
        run_id: UUID,
    ) -> tuple[RunReplayRequestContext | None, Response | None]:
        serializer, serializer_response = self._validated_replay_serializer(request)
        if serializer_response is not None:
            return None, serializer_response
        assert serializer is not None

        user = cast(User, request.user)
        if not has_min_role(user, "member"):
            return None, error_response(
                code="FORBIDDEN",
                message="You don't have permission to replay runs in this organization.",
                status=status.HTTP_403_FORBIDDEN,
            )
        tenant_id = get_tenant_id_for_user(user)
        node_id = str(serializer.validated_data.get("node_id") or "").strip()

        run, run_response = self._replay_source_run(user=user, run_id=run_id)
        if run_response is not None:
            return None, run_response
        assert run is not None

        command_context = build_idempotency_context(
            request=request,
            organization=run.organization or user.default_organization,
            action=f"runs.replay:{run.id}",
            request_payload=serializer.validated_data,
        )
        replayed_response = _replayed_command_response(command_context)
        if replayed_response is not None:
            return None, replayed_response

        llm_access, llm_response = self._replay_llm_access(
            request=request,
            serializer=serializer,
            run=run,
            user=user,
        )
        if llm_response is not None:
            return None, llm_response
        assert llm_access is not None

        checkpoint, checkpoint_response = self._replay_checkpoint(run)
        if checkpoint_response is not None:
            return None, checkpoint_response
        assert checkpoint is not None

        thread_response = self._active_replay_thread_response(user=user, run=run)
        if thread_response is not None:
            return None, thread_response

        budget_response = check_llm_budget(user)
        if budget_response is not None:
            return None, budget_response
        tenant_uuid = UUID(tenant_id)
        active_guardrail_response = _active_run_guardrail_response(tenant_uuid=tenant_uuid)
        if active_guardrail_response is not None:
            return None, active_guardrail_response

        return RunReplayRequestContext(
            user=user,
            tenant_id=tenant_id,
            tenant_uuid=tenant_uuid,
            command_context=command_context,
            run=run,
            node_id=node_id,
            llm_access=llm_access,
            checkpoint=checkpoint,
            input_json=run.input_json if isinstance(run.input_json, dict) else {},
            session_id=str(run.thread_id) if run.thread_id else None,
        ), None

    def _prepare_replay_dispatch_graph(
        self,
        *,
        request: Request,
        replay_context: RunReplayRequestContext,
    ) -> tuple[dict[str, Any] | None, dict[str, str] | None, Response | None]:
        run = replay_context.run
        graph_version = run.graph_version
        try:
            traceparent, tracestate = _request_trace_headers(request)
            prepared_graph = prepare_graph_for_engine(
                graph_version.graph_json,
                replay_context.user,
                company_id=graph_version.graph_id,
                traceparent=traceparent,
                tracestate=tracestate,
            )
            prepared_graph = attach_llm_access_to_graph(
                prepared_graph,
                replay_context.llm_access,
            )
        except LLMAccessValidationError as exc:
            return None, None, _llm_access_error_response(exc)
        except (PromptTemplateResolutionError, SubgraphResolutionError, ValueError) as exc:
            return None, None, _run_preparation_error_response(exc)

        managed_limit_response = _managed_llm_limit_response(
            user=replay_context.user,
            graph_json=prepared_graph,
            llm_access=replay_context.llm_access,
        )
        if managed_limit_response is not None:
            return None, None, managed_limit_response

        credential_errors = validate_prompt_credentials(
            prepared_graph,
            replay_context.user,
            llm_access=replay_context.llm_access,
        )
        if credential_errors:
            return (
                None,
                None,
                error_response(
                    code="INVALID_CREDENTIALS",
                    message="Prompt node credentials are missing or invalid.",
                    status=status.HTTP_400_BAD_REQUEST,
                    details=credential_errors,
                ),
            )

        return prepared_graph, _trace_metadata_from_graph(prepared_graph), None

    def _replay_checkpoint_seed(
        self,
        *,
        checkpoint: RunCheckpoint,
        prepared_graph: dict[str, Any],
        node_id: str,
    ) -> tuple[ReplayCheckpointSeed | None, Response | None]:
        replay_nodes: set[str] = set()
        if node_id:
            replay_nodes = _get_downstream_nodes(prepared_graph, node_id)
            if not replay_nodes:
                return None, error_response(
                    code="INVALID_NODE",
                    message=f"Node '{node_id}' was not found in the graph.",
                    status=status.HTTP_400_BAD_REQUEST,
                )

        state_json = checkpoint.state_json if isinstance(checkpoint.state_json, dict) else {}
        state_json = dict(state_json)
        completed_nodes = list(checkpoint.completed_nodes or [])
        skipped_nodes = list(checkpoint.skipped_nodes or [])
        if replay_nodes:
            state_json = _prune_state_for_nodes(state_json, replay_nodes)
            completed_nodes = [node for node in completed_nodes if node not in replay_nodes]
            skipped_nodes = [node for node in skipped_nodes if node not in replay_nodes]

        return ReplayCheckpointSeed(
            state_json=state_json,
            completed_nodes=completed_nodes,
            skipped_nodes=skipped_nodes,
        ), None

    def _create_replay_run(
        self,
        *,
        replay_context: RunReplayRequestContext,
        prepared_graph: dict[str, Any],
        trace_metadata: dict[str, str],
        seed: ReplayCheckpointSeed,
    ) -> tuple[Run | None, dict[str, Any] | None, Response | None]:
        source_run = replay_context.run
        graph_version = source_run.graph_version
        replay_context_pack_id = ""
        try:
            with transaction.atomic():
                replay_run = Run.objects.create(
                    owner=replay_context.user,
                    organization=graph_version.graph.organization
                    or replay_context.user.default_organization,
                    graph_version=graph_version,
                    thread_id=source_run.thread_id,
                    status="pending",
                    started_at=timezone.now(),
                    ended_at=None,
                    input_json=replay_context.input_json,
                    dispatch_graph_json=prepared_graph,
                    output_json=None,
                    error_message="",
                    trace_id=trace_metadata["trace_id"],
                )
                outbound_graph = prepare_tool_executions_for_dispatch(
                    run=replay_run,
                    graph_json=prepared_graph,
                )
                outbound_graph = _attach_operation_context_pack(
                    replay_run,
                    outbound_graph,
                    context_pack_mode="fresh_at_replay",
                )
                outbound_metadata = (
                    outbound_graph.get("metadata") if isinstance(outbound_graph, dict) else {}
                )
                replay_context_pack_id = (
                    str(outbound_metadata.get("context_pack_id") or "")
                    if isinstance(outbound_metadata, dict)
                    else ""
                )

                RunCheckpoint.objects.create(
                    run=replay_run,
                    node_id=replay_context.checkpoint.node_id,
                    step_index=replay_context.checkpoint.step_index,
                    state_json=seed.state_json,
                    completed_nodes=seed.completed_nodes,
                    skipped_nodes=seed.skipped_nodes,
                    graph_json=pyjson.dumps(outbound_graph),
                )
                RunEvent.objects.create(
                    run=replay_run,
                    event_type="run.replay",
                    payload={
                        "source_run_id": str(source_run.id),
                        "from_node_id": replay_context.node_id or None,
                        "checkpoint_step": replay_context.checkpoint.step_index,
                        "context_pack_id": replay_context_pack_id or None,
                        "context_pack_mode": "fresh_at_replay",
                    },
                    trace_id=trace_metadata["trace_id"],
                    span_id=trace_metadata["span_id"],
                )
        except ToolExecutionDispatchBlocked as exc:
            return None, None, _tool_execution_dispatch_error_response(exc)
        return replay_run, outbound_graph, None

    def _record_replay_created(
        self,
        *,
        replay_context: RunReplayRequestContext,
        replay_run: Run,
    ) -> None:
        source_run = replay_context.run
        graph_version = source_run.graph_version
        broadcast_run_updated(replay_run)
        record_audit_log(
            actor=replay_context.user,
            tenant_id=get_tenant_id_for_user(replay_context.user),
            action="run.replayed",
            resource_type="run",
            resource_id=str(replay_run.id),
            metadata=_run_audit_metadata(
                graph_version=graph_version,
                thread_id=replay_run.thread_id,
                trigger="replay",
                extra={
                    "source_run_id": str(source_run.id),
                    "from_node_id": replay_context.node_id or None,
                },
            ),
        )
        upsert_memory_session(replay_context.user, replay_context.session_id)

    def _queued_replay_response(
        self,
        *,
        replay_context: RunReplayRequestContext,
        replay_run: Run,
    ) -> Response:
        graph_version = replay_context.run.graph_version
        queue_entry = enqueue_run(replay_run, tenant_id=replay_context.tenant_id)
        run_data = {
            "id": replay_run.id,
            "owner_id": replay_run.owner_id,
            "owner_email": replay_run.owner.email,
            "thread_id": replay_run.thread_id,
            "graph_id": graph_version.graph_id,
            "graph_name": graph_version.graph.name,
            "graph_version_id": graph_version.id,
            "graph_version": graph_version.version,
            "status": replay_run.status,
            "queue_status": queue_entry.status,
            "queue_attempts": queue_entry.attempts,
            "queue_available_at": queue_entry.available_at,
            "started_at": replay_run.started_at,
            "ended_at": replay_run.ended_at,
            "input_json": redact_payload(replay_run.input_json),
            "output_json": redact_payload(replay_run.output_json),
            "error_message": redact_payload(replay_run.error_message),
            "duration_ms": replay_run.duration_ms,
            "trace_id": replay_run.trace_id,
            "llm_access": _public_llm_access_payload(replay_run),
            "node_runs": [],
        }
        serialized_data = RunDetailWithNodeRunsSerializer(run_data).data
        response = success_response(
            serialized_data,
            status=status.HTTP_201_CREATED,
            meta=_queue_response_meta(
                run=replay_run,
                tenant_id=replay_context.tenant_id,
            ),
        )
        return record_processed_command(
            context=replay_context.command_context,
            response=response,
            resource_type="run",
            resource_id=str(replay_run.id),
        )

    def _dispatch_replay_run(
        self,
        *,
        request: Request,
        replay_context: RunReplayRequestContext,
        replay_run: Run,
        outbound_graph: dict[str, Any],
        trace_metadata: dict[str, str],
    ) -> Response | None:
        return _dispatch_run_to_engine(
            RunEngineDispatch(
                run=replay_run,
                graph_version=replay_context.run.graph_version,
                outbound_graph=outbound_graph,
                input_json=replay_context.input_json,
                llm_access=replay_context.llm_access,
                session_id=replay_context.session_id,
                tenant_id=get_tenant_id(request),
                trace_metadata=trace_metadata,
                span_name="runs.replay",
                trigger="replay",
                engine_rejected_event="engine_rejected_replay",
            )
        )

    def _replay_run_response(
        self,
        *,
        replay_context: RunReplayRequestContext,
        replay_run: Run,
    ) -> Response:
        graph_version = replay_context.run.graph_version
        run_data = {
            "id": replay_run.id,
            "owner_id": replay_run.owner_id,
            "owner_email": replay_run.owner.email,
            "thread_id": replay_run.thread_id,
            "graph_id": graph_version.graph_id,
            "graph_name": graph_version.graph.name,
            "graph_version_id": graph_version.id,
            "graph_version": graph_version.version,
            "status": replay_run.status,
            **_queue_payload(replay_run),
            "started_at": replay_run.started_at,
            "ended_at": replay_run.ended_at,
            "input_json": redact_payload(replay_run.input_json),
            "output_json": redact_payload(replay_run.output_json),
            "error_message": redact_payload(replay_run.error_message),
            "duration_ms": replay_run.duration_ms,
            "llm_access": _public_llm_access_payload(replay_run),
            "node_runs": [],
        }
        serialized_data = RunDetailWithNodeRunsSerializer(run_data).data
        response = success_response(serialized_data, status=status.HTTP_201_CREATED)
        return record_processed_command(
            context=replay_context.command_context,
            response=response,
            resource_type="run",
            resource_id=str(replay_run.id),
        )

    def post(self, request: Request, run_id: UUID) -> Response:
        replay_context, context_response = self._build_replay_request_context(request, run_id)
        if context_response is not None:
            return context_response
        assert replay_context is not None
        checkpoint = replay_context.checkpoint

        prepared_graph, trace_metadata, prepare_response = self._prepare_replay_dispatch_graph(
            request=request,
            replay_context=replay_context,
        )
        if prepare_response is not None:
            return prepare_response
        assert prepared_graph is not None
        assert trace_metadata is not None

        seed, seed_response = self._replay_checkpoint_seed(
            checkpoint=checkpoint,
            prepared_graph=prepared_graph,
            node_id=replay_context.node_id,
        )
        if seed_response is not None:
            return seed_response
        assert seed is not None

        replay_run, outbound_graph, create_response = self._create_replay_run(
            replay_context=replay_context,
            prepared_graph=prepared_graph,
            trace_metadata=trace_metadata,
            seed=seed,
        )
        if create_response is not None:
            return create_response
        assert replay_run is not None
        assert outbound_graph is not None

        self._record_replay_created(replay_context=replay_context, replay_run=replay_run)
        if getattr(settings, "RUN_QUEUE_ENABLED", False):
            return self._queued_replay_response(
                replay_context=replay_context,
                replay_run=replay_run,
            )

        dispatch_response = self._dispatch_replay_run(
            request=request,
            replay_context=replay_context,
            replay_run=replay_run,
            outbound_graph=outbound_graph,
            trace_metadata=trace_metadata,
        )
        if dispatch_response is not None:
            return dispatch_response

        return self._replay_run_response(
            replay_context=replay_context,
            replay_run=replay_run,
        )
