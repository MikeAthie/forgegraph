"""Engine run lifecycle projection helpers for run event adapters."""

# ruff: noqa: F403,F405,I001

from adapters.api.runs.common import *  # noqa: F403


class EngineRunLifecycleMixin(EngineCallbackComposableMixin):
    def _run_started_duplicate_response(
        self, context: EngineCallbackContext, current_status: str
    ) -> Response | None:
        if context.event_type != "run_started" or current_status == "pending":
            return None
        return self._engine_callback_context_success(
            context,
            {
                "received": True,
                "duplicate": True,
                "current_status": current_status,
            },
            decision="duplicate",
            reason="run_started was already superseded by backend state",
            backend_event_id=str(context.event_id or ""),
            safe_to_discard=True,
            idempotency_status="already_applied",
        )

    def _runtime_safety_response(
        self, context: EngineCallbackContext, *, reason: str = "event safety violation"
    ) -> Response | None:
        try:
            assert_runtime_state_mutation_allowed(
                context.event_type,
                category=context.normalized_category,
                payload=context.event,
            )
        except EventSafetyViolation as exc:
            _record_engine_callback_dead_letter(
                event=context.event,
                run=context.run,
                reason=reason,
                error_class="event_safety_violation",
                event_id=str(context.event_id or ""),
                event_type=str(context.event_type or ""),
            )
            return _engine_callback_problem(
                type_uri="https://forgegraph.dev/problems/event-safety-violation",
                title="Event safety violation",
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
                decision="reject_invalid",
                reason=reason,
                backend_event_id=str(context.event_id or ""),
                safe_to_discard=True,
                conflict_code="409_EVENT_SAFETY_VIOLATION",
            )
        return None

    def _run_transition_conflict_response(
        self,
        context: EngineCallbackContext,
        *,
        current_status: str,
    ) -> Response | None:
        try:
            _validate_run_event_transition(
                current_status=current_status,
                event_type=context.event_type,
            )
        except ValueError as exc:
            _record_engine_callback_dead_letter(
                event=context.event,
                run=context.run,
                reason="run state ordering conflict",
                error_class="run_state_ordering_conflict",
                event_id=str(context.event_id or ""),
                event_type=str(context.event_type or ""),
            )
            return _engine_callback_problem(
                type_uri="https://forgegraph.dev/problems/invalid-run-transition",
                title="Invalid run transition",
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
                decision="retry_required",
                reason="run state ordering conflict",
                backend_event_id=str(context.event_id or ""),
                safe_to_discard=False,
                conflict_code="409_ORDERING_CONFLICT",
            )
        return None

    def _run_lifecycle_preflight_response(
        self,
        context: EngineCallbackContext,
        *,
        current_status: str,
        check_safety: bool,
    ) -> Response | None:
        duplicate_response = self._run_started_duplicate_response(context, current_status)
        if duplicate_response is not None:
            return duplicate_response
        if check_safety:
            safety_response = self._runtime_safety_response(context)
            if safety_response is not None:
                return safety_response
        return self._run_transition_conflict_response(context, current_status=current_status)

    def _record_run_lifecycle_metrics(
        self,
        *,
        context: EngineCallbackContext,
        run: Run,
        previous_status: str,
    ) -> None:
        if context.event_type == "run_started" and previous_status != "running":
            record_run_started()
        if context.event_type in {
            "run_completed",
            "run_failed",
            "run_canceled",
        } and previous_status not in {
            "succeeded",
            "failed",
            "canceled",
        }:
            record_run_completed(run.status, run.duration_ms)
        if context.state_mutation_enabled and context.event_type == "run_completed":
            _schedule_deliverable_archive(run.id)

    def _empty_run_lifecycle_mutation(self) -> RunLifecycleMutation:
        return RunLifecycleMutation(
            run_payload={},
            update_fields=[],
            pause_payload={},
            node_id="",
            projection_kwargs={},
        )

    def _run_started_lifecycle_mutation(
        self,
        *,
        run: Run,
        event_time: datetime | None,
    ) -> RunLifecycleMutation:
        run_payload: dict[str, Any] = {"status": "running"}
        update_fields = apply_run_status_transition(run, "running").update_fields
        if event_time:
            run_payload["started_at"] = event_time
            run.started_at = event_time
            update_fields.append("started_at")
        return RunLifecycleMutation(
            run_payload=run_payload,
            update_fields=update_fields,
            pause_payload={},
            node_id="",
            projection_kwargs={"started_at": event_time},
        )

    def _run_completed_lifecycle_mutation(
        self,
        *,
        run: Run,
        event: dict[str, Any],
        event_time: datetime | None,
    ) -> RunLifecycleMutation:
        run_payload: dict[str, Any] = {"status": "succeeded"}
        update_fields = apply_run_status_transition(run, "succeeded").update_fields
        if event_time:
            run_payload["ended_at"] = event_time
            run.ended_at = event_time
            update_fields.append("ended_at")
        if "output" in event:
            redacted_output = redact_payload(event.get("output"))
            run_payload["output_json"] = redacted_output
            run.output_json = redacted_output
            update_fields.append("output_json")
        return RunLifecycleMutation(
            run_payload=run_payload,
            update_fields=update_fields,
            pause_payload={},
            node_id="",
            projection_kwargs={
                "ended_at": event_time,
                "output_json": run_payload.get("output_json", _UNSET),
            },
        )

    def _run_failed_lifecycle_mutation(
        self,
        *,
        run: Run,
        event: dict[str, Any],
        event_time: datetime | None,
    ) -> RunLifecycleMutation:
        error_message = redact_payload(event.get("error") or "")
        run_payload: dict[str, Any] = {
            "status": "failed",
            "error_message": error_message,
        }
        update_fields = apply_run_status_transition(run, "failed").update_fields
        if event_time:
            run_payload["ended_at"] = event_time
            run.ended_at = event_time
            update_fields.append("ended_at")
        run.error_message = error_message
        update_fields.append("error_message")
        return RunLifecycleMutation(
            run_payload=run_payload,
            update_fields=update_fields,
            pause_payload={},
            node_id="",
            projection_kwargs={"ended_at": event_time, "error_message": error_message},
        )

    def _run_canceled_lifecycle_mutation(
        self,
        *,
        run: Run,
        event_time: datetime | None,
    ) -> RunLifecycleMutation:
        run_payload: dict[str, Any] = {"status": "canceled"}
        update_fields = apply_run_status_transition(run, "canceled").update_fields
        if event_time:
            run_payload["ended_at"] = event_time
            run.ended_at = event_time
            update_fields.append("ended_at")
        return RunLifecycleMutation(
            run_payload=run_payload,
            update_fields=update_fields,
            pause_payload={},
            node_id="",
            projection_kwargs={"ended_at": event_time},
        )

    def _run_paused_lifecycle_mutation(
        self,
        *,
        run: Run,
        event: dict[str, Any],
    ) -> RunLifecycleMutation:
        node_id = str(event.get("node_id") or "")
        run_payload: dict[str, Any] = {"status": "paused"}
        update_fields = apply_run_status_transition(run, "paused").update_fields
        if node_id:
            run_payload["paused_node_id"] = node_id
            run.paused_node_id = node_id
            update_fields.append("paused_node_id")
        raw_pause_payload = redact_payload(event.get("output") or {})
        pause_payload = raw_pause_payload if isinstance(raw_pause_payload, dict) else {}
        run_payload["pause_payload"] = pause_payload
        persisted_pause_state = redact_payload(run.pause_state_json)
        if persisted_pause_state is not None:
            run_payload["pause_state_json"] = persisted_pause_state
        return RunLifecycleMutation(
            run_payload=run_payload,
            update_fields=update_fields,
            pause_payload=pause_payload,
            node_id=node_id,
            projection_kwargs={
                "paused_node_id": node_id or None,
                "pause_state_json": (
                    persisted_pause_state if persisted_pause_state is not None else _UNSET
                ),
            },
        )

    def _run_resumed_lifecycle_mutation(
        self,
        *,
        context: EngineCallbackContext,
        run: Run,
    ) -> RunLifecycleMutation:
        event = context.event
        event_output = event.get("output")
        resume_output = event_output if isinstance(event_output, dict) else {}
        resume_attempt_id = str(
            resume_output.get("resume_attempt_id") or event.get("attempt_id") or ""
        ).strip()
        expected_resume_attempt_id = str(
            run.resume_attempt_id or run.authoritative_attempt_id or ""
        ).strip()
        if not resume_attempt_id or (
            expected_resume_attempt_id and resume_attempt_id != expected_resume_attempt_id
        ):
            return RunLifecycleMutation(
                run_payload={},
                update_fields=[],
                pause_payload={},
                node_id="",
                projection_kwargs={},
                error_response=_engine_callback_problem(
                    type_uri="https://forgegraph.dev/problems/stale-resume-acknowledgement",
                    title="Stale resume acknowledgement",
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "run_resumed acknowledgement does not match the active resume_attempt_id."
                    ),
                    decision="stale_superseded",
                    reason="resume_attempt_id does not match the active backend resume attempt",
                    backend_event_id=str(context.event_id or ""),
                    safe_to_discard=True,
                    conflict_code="409_STALE_SUPERSEDED",
                ),
            )
        run_payload: dict[str, Any] = {
            "status": "running",
            "paused_node_id": None,
            "pause_state_json": None,
        }
        update_fields = apply_run_status_transition(run, "running").update_fields
        run.paused_node_id = None
        run.pause_state_json = None
        update_fields.extend(["paused_node_id", "pause_state_json"])
        return RunLifecycleMutation(
            run_payload=run_payload,
            update_fields=update_fields,
            pause_payload={},
            node_id="",
            projection_kwargs={
                "paused_node_id": None,
                "pause_state_json": None,
            },
        )

    def _run_lifecycle_mutation(
        self,
        *,
        context: EngineCallbackContext,
        run: Run,
    ) -> RunLifecycleMutation:
        if context.event_type == "run_started":
            return self._run_started_lifecycle_mutation(run=run, event_time=context.event_time)
        if context.event_type == "run_completed":
            return self._run_completed_lifecycle_mutation(
                run=run,
                event=context.event,
                event_time=context.event_time,
            )
        if context.event_type == "run_failed":
            return self._run_failed_lifecycle_mutation(
                run=run,
                event=context.event,
                event_time=context.event_time,
            )
        if context.event_type == "run_canceled":
            return self._run_canceled_lifecycle_mutation(run=run, event_time=context.event_time)
        if context.event_type == "run_paused":
            return self._run_paused_lifecycle_mutation(run=run, event=context.event)
        if context.event_type == "run_resumed":
            return self._run_resumed_lifecycle_mutation(context=context, run=run)
        return self._empty_run_lifecycle_mutation()

    def _clear_resume_request_fields(
        self,
        *,
        run: Run,
        run_payload: dict[str, Any],
        update_fields: list[str],
    ) -> None:
        if run.resume_requested_at is not None:
            run_payload["resume_requested_at"] = None
            run.resume_requested_at = None
            update_fields.append("resume_requested_at")
        if run.resume_attempt_id is not None:
            run_payload["resume_attempt_id"] = None
            run.resume_attempt_id = None
            update_fields.append("resume_attempt_id")

    def _handle_engine_run_lifecycle_event(self, context: EngineCallbackContext) -> Response:
        run = context.run
        event_type = context.event_type
        event_id = context.event_id
        event_time = context.event_time
        trace_context = context.trace_context
        state_mutation_enabled = context.state_mutation_enabled
        callback_engine_instance_id = context.callback_engine_instance_id
        preflight_response = self._run_lifecycle_preflight_response(
            context,
            current_status=run.status,
            check_safety=True,
        )
        if preflight_response is not None:
            return preflight_response
        with transaction.atomic():
            run = _lock_run_for_update(run.id)
            context.run = run
            previous_status = run.status
            locked_response = self._run_lifecycle_preflight_response(
                context,
                current_status=previous_status,
                check_safety=False,
            )
            if locked_response is not None:
                return locked_response
            previous_paused_node_id = run.paused_node_id
            previous_pause_state = (
                dict(run.pause_state_json) if isinstance(run.pause_state_json, dict) else {}
            )
            mutation = self._run_lifecycle_mutation(context=context, run=run)
            if mutation.error_response is not None:
                return cast(Response, mutation.error_response)
            run_payload = mutation.run_payload
            update_fields = mutation.update_fields
            pause_payload = mutation.pause_payload
            node_id = mutation.node_id
            projection_kwargs = mutation.projection_kwargs
            self._clear_resume_request_fields(
                run=run,
                run_payload=run_payload,
                update_fields=update_fields,
            )

            if state_mutation_enabled and update_fields:
                update_fields.extend(
                    touch_run_liveness(
                        run,
                        event_time=event_time,
                        recovery_state=recovery_state_for_status(run.status),
                        engine_instance_id=callback_engine_instance_id,
                    )
                )
                run.trace_id = trace_context["trace_id"]
                update_fields.append("trace_id")
                run.save(update_fields=sorted(set(update_fields)))

            final_run_stream_summaries = self._final_run_stream_summaries(run, event_type)

            _project_run_event_state(
                run=run,
                projection_status=run.status,
                trace_id=trace_context["trace_id"],
                event_type=event_type,
                event_id=event_id,
                event_time=event_time,
                **projection_kwargs,
            )

            self._project_run_pause_event_state(
                context=context,
                node_id=node_id,
                pause_payload=pause_payload,
            )

            self._record_run_lifecycle_metrics(
                context=context,
                run=run,
                previous_status=previous_status,
            )

            lifecycle_event_saved = self._save_engine_callback_event(
                context, "run.updated", _serialize_event_payload(redact_payload(run_payload))
            )
            if lifecycle_event_saved:
                self._save_engine_callback_event(
                    context,
                    event_type,
                    _serialize_event_payload(redact_payload(run_payload)),
                    derived=True,
                )
            for summary_payload in final_run_stream_summaries:
                broadcast_node_stream_summary(run=run, payload=summary_payload)
            self._broadcast_run_lifecycle_decision_event(
                context=context,
                node_id=node_id,
                pause_payload=pause_payload,
                previous_paused_node_id=previous_paused_node_id,
                previous_pause_state=previous_pause_state,
            )

            for summary_payload in final_run_stream_summaries:
                broadcast_node_stream_summary(run=run, payload=summary_payload)

            if not state_mutation_enabled:
                return self._engine_callback_context_success(
                    context,
                    {
                        "received": True,
                        "event_type": event_type,
                        "authoritative_state_updated": False,
                    },
                    reason="event accepted without authoritative state mutation",
                    backend_event_id=str(event_id or ""),
                )

            message = broadcast_run_updated(run)
            return self._engine_callback_context_success(
                context,
                message,
                reason="run state event accepted",
                backend_event_id=str(event_id or ""),
            )

    def _final_run_stream_summaries(
        self,
        run: Run,
        event_type: str,
    ) -> list[dict[str, Any]]:
        if event_type not in {"run_completed", "run_failed", "run_canceled", "run_paused"}:
            return []
        return flush_all_stream_summaries(run_id=str(run.id), final_reason=event_type)

    def _project_run_pause_event_state(
        self,
        *,
        context: EngineCallbackContext,
        node_id: Any,
        pause_payload: Any,
    ) -> None:
        if context.event_type != "run_paused" or not node_id:
            return
        event = context.event
        trace_context = context.trace_context
        pause_payload_dict = pause_payload if isinstance(pause_payload, dict) else {}
        _project_pause_state(
            run=context.run,
            node_id=node_id,
            node_type=str(event.get("node_type") or ""),
            attempt=int(event.get("attempt") or 1),
            pause_payload=pause_payload_dict,
            trace_id=trace_context["trace_id"],
            span_id=trace_context["span_id"],
            event_time=context.event_time,
        )
        _project_node_event_state(
            run=context.run,
            node_id=node_id,
            node_type=str(event.get("node_type") or "human_gate"),
            attempt=int(event.get("attempt") or 1),
            projection_status="waiting",
            trace_id=trace_context["trace_id"],
            span_id=trace_context["span_id"],
            event_type=context.event_type,
            event_id=context.event_id,
            event_time=context.event_time,
            started_at=context.event_time,
            output_json={"pause_payload": pause_payload} if pause_payload else _UNSET,
        )

    def _broadcast_run_lifecycle_decision_event(
        self,
        *,
        context: EngineCallbackContext,
        node_id: Any,
        pause_payload: Any,
        previous_paused_node_id: str | None,
        previous_pause_state: dict[str, Any],
    ) -> None:
        if not context.state_mutation_enabled:
            return
        if context.event_type == "run_paused" and node_id:
            pause_payload_dict = pause_payload if isinstance(pause_payload, dict) else {}
            broadcast_decision_required(
                run=context.run,
                payload={
                    "node_id": node_id,
                    "node_type": str(context.event.get("node_type") or "human_gate"),
                    "attempt": int(context.event.get("attempt") or 1),
                    "status": "waiting",
                    "prompt_message": str(pause_payload_dict.get("prompt_message") or ""),
                    "required_fields": list(pause_payload_dict.get("required_fields") or []),
                    "node_name": str(pause_payload_dict.get("node_name") or ""),
                },
            )
            return
        if context.event_type == "run_resumed" and previous_paused_node_id:
            broadcast_decision_resolved(
                run=context.run,
                payload={
                    "node_id": previous_paused_node_id,
                    "status": "resolved",
                    "prompt_message": str(previous_pause_state.get("prompt_message") or ""),
                    "required_fields": list(previous_pause_state.get("required_fields") or []),
                    "resolution": redact_payload(context.event.get("output") or {}),
                },
            )
