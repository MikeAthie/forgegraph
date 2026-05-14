"""Authenticated run event adapters."""

# ruff: noqa: F403,F405,I001

from adapters.api.runs.common import *  # noqa: F403


class RunEventsView(APIView):
    """Persist + broadcast Run/NodeRun delta events.

    These authenticated events are write requests, not authoritative state by themselves.
    """

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
        serializer = RunEventSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                code="VALIDATION_ERROR",
                message="The request contains invalid fields",
                status=status.HTTP_400_BAD_REQUEST,
                details=[
                    {"field": field, "issue": ", ".join(errors)}
                    for field, errors in serializer.errors.items()
                ],
            )

        user = cast(User, request.user)
        try:
            run = run_queryset_for_user(user).get(id=run_id)
        except Run.DoesNotExist:
            return error_response(
                code="NOT_FOUND",
                message=f"Run with id '{run_id}' not found or you do not have access to it",
                status=status.HTTP_404_NOT_FOUND,
            )

        event_type = serializer.validated_data["event_type"]
        normalized_category = normalize_event_category(
            event_type,
            category=str(serializer.validated_data.get("category") or ""),
        )

        if event_type == "run.updated":
            safety_response = self._event_safety_response(
                event_type=event_type,
                normalized_category=normalized_category,
                payload=serializer.validated_data,
            )
            if safety_response is not None:
                return safety_response
            return self._handle_authenticated_run_updated(
                run=run,
                payload=serializer.validated_data["run"],
                event_type=event_type,
                normalized_category=normalized_category,
            )

        if event_type == "node_run.updated":
            safety_response = self._event_safety_response(
                event_type=event_type,
                normalized_category=normalized_category,
                payload=serializer.validated_data,
            )
            if safety_response is not None:
                return safety_response
            return self._handle_authenticated_node_run_updated(
                run=run,
                payload=serializer.validated_data["node_run"],
                event_type=event_type,
                normalized_category=normalized_category,
            )

        if event_type == "run.schema_validation":
            payload = redact_payload(serializer.validated_data.get("payload") or {})
            return self._handle_authenticated_schema_validation(
                run=run,
                payload=payload,
                event_type=event_type,
                normalized_category=normalized_category,
            )

        return error_response(
            code="VALIDATION_ERROR",
            message="Unknown event_type",
            status=status.HTTP_400_BAD_REQUEST,
        )
