"""Run API command adapter module."""

# ruff: noqa: F403,F405,I001

from adapters.api.runs.common import *  # noqa: F403
from adapters.api.runs.command_dispatch import *  # noqa: F403


class RunCancelView(APIView):
    """Cancel a run."""

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
            isinstance(output_schema, dict)
            and payload.get("status") == "succeeded"
            and "output_json" in payload
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

    def post(self, request: Request, run_id: UUID) -> Response:
        """Cancel a running run."""
        user = cast(User, request.user)
        if not has_min_role(user, "member"):
            return error_response(
                code="FORBIDDEN",
                message="You don't have permission to cancel runs in this organization.",
                status=status.HTTP_403_FORBIDDEN,
            )
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
                .select_related("graph_version__graph")
                .prefetch_related(Prefetch("node_runs", queryset=node_runs_queryset))
                .get(id=run_id)
            )
        except Run.DoesNotExist:
            return error_response(
                code="NOT_FOUND",
                message=f"Run with id '{run_id}' not found or you do not have access to it",
                status=status.HTTP_404_NOT_FOUND,
            )
        command_context = build_idempotency_context(
            request=request,
            organization=run.organization or user.default_organization,
            action=f"runs.cancel:{run.id}",
            request_payload=request.data,
        )
        replayed_response = _replayed_command_response(command_context)
        if replayed_response is not None:
            return replayed_response

        if run.status in {"succeeded", "failed", "canceled"}:
            return error_response(
                code="INVALID_STATE",
                message=f"Cannot cancel a run in status '{run.status}'.",
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Tell the engine to cancel the run
        try:
            _, engine_client = get_engine_client_for_run(run=run)
            with engine_client as engine:
                engine.cancel_run(run_id=run.id)

        except EngineConnectionError as e:
            log_event(
                logger,
                logging.WARNING,
                "engine_cancel_connection_failed",
                run_id=str(run.id),
                trace_id=run.trace_id,
                error_message=str(e),
            )
            # Still proceed to mark as canceled in the control plane

        except EngineExecutionError as e:
            log_event(
                logger,
                logging.WARNING,
                "engine_cancel_failed",
                run_id=str(run.id),
                trace_id=run.trace_id,
                error_message=str(e),
            )
            # Still proceed to mark as canceled in the control plane

        if not run.started_at:
            run.started_at = timezone.now()

        transition = apply_run_status_transition(run, "canceled")
        run.ended_at = timezone.now()
        if not run.error_message:
            run.error_message = "Canceled by user."

        run.save(
            update_fields=sorted(
                set(transition.update_fields + ["started_at", "ended_at", "error_message"])
            )
        )
        record_audit_log(
            actor=user,
            tenant_id=get_tenant_id_for_run(run),
            action="run.canceled",
            resource_type="run",
            resource_id=str(run.id),
            metadata={
                "status": run.status,
                "reason": run.error_message,
            },
        )
        mark_run_tasks_terminal(
            run=run,
            status_value="cancelled",
            source="run_cancel",
            reason=run.error_message or "Canceled by user.",
        )
        record_run_completed("canceled", run.duration_ms)
        broadcast_run_updated(run)

        graph_version = run.graph_version
        graph = graph_version.graph
        node_runs = list(run.node_runs.all())

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
            "started_at": run.started_at,
            "ended_at": run.ended_at,
            "input_json": redact_payload(run.input_json),
            "output_json": redact_payload(run.output_json),
            "error_message": redact_payload(run.error_message),
            "duration_ms": run.duration_ms,
            "memory_activity": summarize_run_memory_activity(node_runs, include_operations=True),
            "llm_access": _public_llm_access_payload(run),
            "node_runs": [
                _serialize_node_run_for_detail(node_run=node_run) for node_run in node_runs
            ],
        }

        serialized_data = RunDetailWithNodeRunsSerializer(run_data).data
        response = success_response(serialized_data)
        return record_processed_command(
            context=command_context,
            response=response,
            resource_type="run",
            resource_id=str(run.id),
        )
