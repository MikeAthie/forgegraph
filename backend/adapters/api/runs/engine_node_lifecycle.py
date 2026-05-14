"""Engine node lifecycle projection helpers for run event adapters."""

# ruff: noqa: F403,F405,I001

from adapters.api.runs.common import *  # noqa: F403


class EngineNodeLifecycleMixin:
    def _build_engine_node_payload(
        self, context: EngineCallbackContext
    ) -> tuple[Any, Any, int, dict[str, Any]]:
        run = context.run
        event = context.event
        event_type = context.event_type
        trace_context = context.trace_context
        callback_engine_instance_id = context.callback_engine_instance_id
        node_id = event.get("node_id") or ""
        node_type = event.get("node_type") or ""
        attempt = int(event.get("attempt") or 1)
        attempt_id = str(event.get("attempt_id") or "").strip() or None
        node_payload: dict[str, Any] = {
            "node_id": node_id,
            "node_type": node_type,
            "attempt": attempt,
            "trace_id": trace_context["trace_id"],
            "span_id": trace_context["span_id"],
        }
        if event_type in {"node_started", "node_completed"}:
            log_event(
                logger,
                logging.INFO,
                event_type,
                run_id=str(run.id),
                trace_id=trace_context["trace_id"],
                node_id=node_id,
                node_type=node_type,
                attempt=attempt,
                attempt_id=attempt_id,
                engine_instance_id=callback_engine_instance_id,
                message="Engine node lifecycle event received",
            )

        self._apply_engine_node_payload_event(
            context=context,
            node_payload=node_payload,
            node_id=node_id,
            node_type=node_type,
            attempt=attempt,
            attempt_id=attempt_id,
        )
        return node_id, node_type, attempt, node_payload

    def _apply_engine_node_payload_event(
        self,
        *,
        context: EngineCallbackContext,
        node_payload: dict[str, Any],
        node_id: Any,
        node_type: Any,
        attempt: int,
        attempt_id: str | None,
    ) -> None:
        event_type = context.event_type
        event_time = context.event_time
        if event_type == "node_started":
            self._apply_engine_node_started_payload(
                context, node_payload, node_id, node_type, attempt, attempt_id
            )
            return
        if event_type == "node_completed":
            self._apply_engine_node_completed_payload(
                context, node_payload, node_id, node_type, attempt, attempt_id
            )
            return
        if event_type == "node_failed":
            self._apply_engine_node_failed_payload(
                context, node_payload, node_id, node_type, attempt, attempt_id
            )
            return
        if event_type == "node_skipped":
            node_payload["status"] = "skipped"
            if event_time:
                node_payload["ended_at"] = event_time
            return
        if event_type == "node_retrying":
            node_payload["status"] = "running"

    def _apply_engine_node_started_payload(
        self,
        context: EngineCallbackContext,
        node_payload: dict[str, Any],
        node_id: Any,
        node_type: Any,
        attempt: int,
        attempt_id: str | None,
    ) -> None:
        node_payload["input_json"] = redact_payload(context.event.get("input") or {})
        self._log_engine_node_payload(
            context=context,
            event_name="node_input",
            node_payload=node_payload["input_json"],
            node_id=node_id,
            node_type=node_type,
            attempt=attempt,
            attempt_id=attempt_id,
            message="Engine node input received",
        )
        node_payload["status"] = "running"
        if context.event_time:
            node_payload["started_at"] = context.event_time

    def _apply_engine_node_completed_payload(
        self,
        context: EngineCallbackContext,
        node_payload: dict[str, Any],
        node_id: Any,
        node_type: Any,
        attempt: int,
        attempt_id: str | None,
    ) -> None:
        node_payload["status"] = "succeeded"
        if context.event_time:
            node_payload["ended_at"] = context.event_time
        node_payload["output_json"] = redact_payload(context.event.get("output"))
        self._log_engine_node_payload(
            context=context,
            event_name="node_output",
            node_payload=node_payload["output_json"],
            node_id=node_id,
            node_type=node_type,
            attempt=attempt,
            attempt_id=attempt_id,
            message="Engine node output received",
        )

    def _apply_engine_node_failed_payload(
        self,
        context: EngineCallbackContext,
        node_payload: dict[str, Any],
        node_id: Any,
        node_type: Any,
        attempt: int,
        attempt_id: str | None,
    ) -> None:
        node_payload["status"] = "failed"
        if context.event_time:
            node_payload["ended_at"] = context.event_time
        node_payload["error_json"] = self._engine_node_error_json(context.event)
        self._log_engine_node_payload(
            context=context,
            event_name="node_output",
            node_payload=node_payload["error_json"],
            node_id=node_id,
            node_type=node_type,
            attempt=attempt,
            attempt_id=attempt_id,
            message="Engine node failure output received",
        )

    def _engine_node_error_json(self, event: dict[str, Any]) -> dict[str, Any]:
        error_message = redact_payload(event.get("error") or "")
        output_payload = redact_payload(event.get("output") or {})
        error_json: dict[str, Any] = {}
        if isinstance(output_payload, dict) and isinstance(output_payload.get("error"), dict):
            error_json = dict(output_payload["error"])
        if not error_json:
            return {"error": error_message}
        if error_message:
            error_json.setdefault("error", error_message)
        return error_json

    def _log_engine_node_payload(
        self,
        *,
        context: EngineCallbackContext,
        event_name: str,
        node_payload: Any,
        node_id: Any,
        node_type: Any,
        attempt: int,
        attempt_id: str | None,
        message: str,
    ) -> None:
        log_event(
            logger,
            logging.INFO,
            event_name,
            run_id=str(context.run.id),
            trace_id=context.trace_context["trace_id"],
            node_id=node_id,
            node_type=node_type,
            attempt=attempt,
            attempt_id=attempt_id,
            engine_instance_id=context.callback_engine_instance_id,
            payload=_log_payload_summary(node_payload),
            message=message,
        )

    def _record_node_lifecycle_accounting(
        self,
        *,
        context: EngineCallbackContext,
        run: Run,
        node_id: Any,
        node_type: Any,
        attempt: int,
        node_payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        usage_payload = _extract_llm_usage_payload(
            node_type=node_type,
            output_json=node_payload.get("output_json"),
        )
        if node_type not in {"prompt", "agent"} or not usage_payload:
            return None
        prompt_tokens = usage_payload["prompt_tokens"]
        completion_tokens = usage_payload["completion_tokens"]
        total_tokens = usage_payload["total_tokens"]
        if not (prompt_tokens or completion_tokens or total_tokens):
            return None

        model = usage_payload["model"]
        provider = usage_payload["provider"]
        tenant_id = get_tenant_id_for_run(run)
        cost = calculate_cost(provider, model, prompt_tokens, completion_tokens)
        usage_key_material = (
            f"{context.event_id or run.id}:{run.id}:{node_id}:{attempt}:{provider}:{model}"
        )
        usage_external_key = f"llm:{hashlib.sha256(usage_key_material.encode('utf-8')).hexdigest()}"
        accounting_request_hash = hash_request_payload(
            {
                "event_id": context.event_id,
                "run_id": str(run.id),
                "node_id": node_id,
                "attempt": attempt,
                "provider": provider,
                "model": model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "cost_usd": str(cost),
            }
        )
        llm_usage, _ = LLMUsage.objects.update_or_create(
            tenant_id=tenant_id,
            external_key=usage_external_key,
            defaults={
                "run": run,
                "node_id": node_id,
                "provider": provider,
                "model": model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "cost_usd": cost,
            },
        )
        ProcessedAccountingEvent.objects.update_or_create(
            organization_id=tenant_id,
            event_key=usage_external_key,
            defaults={
                "event_type": "llm_usage",
                "request_hash": accounting_request_hash,
                "llm_usage": llm_usage,
                "status": "applied",
            },
        )
        record_idempotency_observation(
            boundary="accounting_write",
            status="applied",
            idempotency_key=usage_external_key,
            resource_type="llm_usage",
            organization_id=tenant_id,
            run_id=run.id,
        )
        return {
            "node_id": node_id,
            "node_type": node_type,
            "provider": provider,
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "cost_usd": float(cost),
        }

    def _upsert_node_run_from_payload(
        self,
        *,
        run: Run,
        node_id: Any,
        node_type: Any,
        attempt: int,
        node_payload: dict[str, Any],
        trace_context: dict[str, str],
    ) -> NodeRun:
        node_run, created = NodeRun.objects.get_or_create(
            run=run,
            node_id=node_id,
            attempt=attempt,
            defaults={
                "node_type": node_type,
                "status": node_payload["status"],
            },
        )
        node_update_fields: list[str] = []
        if not created and node_run.node_type != node_type:
            node_run.node_type = node_type
            node_update_fields.append("node_type")

        node_run.status = node_payload["status"]
        node_update_fields.append("status")
        for field in ["started_at", "ended_at", "input_json", "output_json", "error_json"]:
            if field in node_payload:
                setattr(node_run, field, node_payload[field])
                node_update_fields.append(field)
        node_run.trace_id = trace_context["trace_id"]
        node_run.span_id = trace_context["span_id"]
        node_update_fields.extend(["trace_id", "span_id"])
        node_run.save(update_fields=sorted(set(node_update_fields)))
        return node_run

    def _ephemeral_node_run_from_payload(
        self,
        *,
        run: Run,
        node_id: Any,
        node_type: Any,
        attempt: int,
        node_payload: dict[str, Any],
        trace_context: dict[str, str],
    ) -> NodeRun:
        node_run = NodeRun(
            run=run,
            node_id=node_id,
            node_type=node_type,
            attempt=attempt,
            status=str(node_payload["status"]),
            trace_id=trace_context["trace_id"],
            span_id=trace_context["span_id"],
        )
        for field in ["started_at", "ended_at", "input_json", "output_json", "error_json"]:
            if field in node_payload:
                setattr(node_run, field, node_payload[field])
        return node_run

    def _record_node_retry_lifecycle(
        self,
        *,
        run: Run,
        event: dict[str, Any],
        event_id: Any,
        event_time: datetime | None,
        node_run: NodeRun,
        node_id: Any,
        node_type: Any,
        attempt: int,
    ) -> None:
        retry_attempt = int(event.get("retry_attempt") or attempt)
        max_attempts = int(event.get("max_attempts") or event.get("max_retries") or retry_attempt)
        retry_delay_ms = int(event.get("retry_delay_ms") or event.get("retry_after_ms") or 0)
        retry_reason = str(event.get("reason") or event.get("error") or "node retry scheduled")
        transition_task_lifecycle(
            run=run,
            node_id=node_id,
            node_type=node_type,
            to_status="retry_scheduled",
            attempt_number=attempt,
            parent_attempt_number=attempt - 1 if attempt > 1 else None,
            source="engine_callback",
            idempotency_key=f"task:{event_id or run.id}:{node_id}:retry",
            reason=retry_reason,
            node_run=node_run,
            owner_component="engine",
            payload={
                "retry_attempt": retry_attempt,
                "max_attempts": max_attempts,
                "retry_delay_ms": retry_delay_ms,
            },
            occurred_at=event_time,
        )
        record_retry_operation(
            run=run,
            operation_type="node_execution",
            idempotency_key=f"retry:{event_id or run.id}:{node_id}:{attempt}",
            attempt_number=retry_attempt,
            max_attempts=max(max_attempts, retry_attempt),
            retry_delay_ms=retry_delay_ms,
            retry_reason=retry_reason,
            last_error=str(event.get("error") or retry_reason),
            owning_component="engine",
            retry_class=str(event.get("retry_class") or "llm_backpressure"),
            terminal_fallback="dead_letter",
            node_id=node_id,
            node_type=node_type,
            parent_attempt_number=attempt - 1 if attempt > 1 else None,
            payload=redact_payload(event),
        )

    def _record_node_lifecycle_transition(
        self,
        *,
        run: Run,
        event: dict[str, Any],
        event_type: str,
        event_id: Any,
        event_time: datetime | None,
        node_run: NodeRun,
        node_id: Any,
        node_type: Any,
        attempt: int,
        node_payload: dict[str, Any],
    ) -> None:
        try:
            if event_type == "node_retrying":
                self._record_node_retry_lifecycle(
                    run=run,
                    event=event,
                    event_id=event_id,
                    event_time=event_time,
                    node_run=node_run,
                    node_id=node_id,
                    node_type=node_type,
                    attempt=attempt,
                )
            else:
                transition_from_node_run(
                    run=run,
                    node_run=node_run,
                    source="engine_callback",
                    idempotency_key=(
                        f"task:{event_id or run.id}:{node_id}:{node_payload['status']}:{attempt}"
                    ),
                    reason=str(node_payload.get("error_json") or ""),
                    occurred_at=event_time,
                )
        except Exception as exc:
            log_event(
                logger,
                logging.WARNING,
                "task_lifecycle_projection_failed",
                run_id=str(run.id),
                node_id=node_id,
                attempt=attempt,
                event_type=event_type,
                error_message=str(exc),
            )

    def _touch_run_for_node_lifecycle(
        self,
        *,
        run: Run,
        event_time: datetime | None,
        trace_context: dict[str, str],
        callback_engine_instance_id: str,
    ) -> None:
        run_update_fields = touch_run_liveness(
            run,
            event_time=event_time,
            recovery_state=recovery_state_for_status(run.status),
            engine_instance_id=callback_engine_instance_id,
        )
        if run.trace_id != trace_context["trace_id"]:
            run.trace_id = trace_context["trace_id"]
            run_update_fields.append("trace_id")
        run.save(update_fields=sorted(set(run_update_fields)))

    def _handle_engine_node_lifecycle_event(self, context: EngineCallbackContext) -> Response:
        run = context.run
        event = context.event
        event_type = context.event_type
        event_id = context.event_id
        event_time = context.event_time
        trace_context = context.trace_context
        state_mutation_enabled = context.state_mutation_enabled
        callback_engine_instance_id = context.callback_engine_instance_id
        safety_response = self._runtime_safety_response(context)
        if safety_response is not None:
            return safety_response
        node_id, node_type, attempt, node_payload = self._build_engine_node_payload(context)
        cost_update_payload: dict[str, Any] | None = None
        node_run: NodeRun | None = None
        with transaction.atomic():
            run = _lock_run_for_update(run.id)
            context.run = run
            if state_mutation_enabled:
                node_run = self._upsert_node_run_from_payload(
                    run=run,
                    node_id=node_id,
                    node_type=node_type,
                    attempt=attempt,
                    node_payload=node_payload,
                    trace_context=trace_context,
                )
                self._record_node_lifecycle_transition(
                    run=run,
                    event=event,
                    event_type=event_type,
                    event_id=event_id,
                    event_time=event_time,
                    node_run=node_run,
                    node_id=node_id,
                    node_type=node_type,
                    attempt=attempt,
                    node_payload=node_payload,
                )
                self._touch_run_for_node_lifecycle(
                    run=run,
                    event_time=event_time,
                    trace_context=trace_context,
                    callback_engine_instance_id=callback_engine_instance_id,
                )
            else:
                node_run = self._ephemeral_node_run_from_payload(
                    run=run,
                    node_id=node_id,
                    node_type=node_type,
                    attempt=attempt,
                    node_payload=node_payload,
                    trace_context=trace_context,
                )

            if event_type == "node_failed" and _payload_contains_policy_denied(
                node_payload.get("error_json")
            ):
                record_audit_log(
                    actor=None,
                    tenant_id=get_tenant_id_for_run(run),
                    action="run.policy_denied",
                    resource_type="node_run",
                    resource_id=str(node_run.id or f"{run.id}:{node_id}:{attempt}"),
                    metadata={
                        "run_id": str(run.id),
                        "node_id": node_id,
                        "node_type": node_type,
                        "attempt": attempt,
                        "error_json": redact_payload(node_payload.get("error_json") or {}),
                    },
                )
            _project_node_event_state(
                run=run,
                node_id=node_id,
                node_type=node_type,
                attempt=attempt,
                projection_status=str(node_payload["status"]),
                trace_id=trace_context["trace_id"],
                span_id=trace_context["span_id"],
                event_type=event_type,
                event_id=event_id,
                event_time=event_time,
                started_at=node_payload.get("started_at", _UNSET),
                ended_at=node_payload.get("ended_at", _UNSET),
                output_json=node_payload.get("output_json", _UNSET),
                error_json=node_payload.get("error_json", _UNSET),
            )
            self._save_engine_callback_event(
                context, "node_run.updated", _serialize_event_payload(redact_payload(node_payload))
            )
            if (
                state_mutation_enabled
                and event_type == "node_completed"
                and getattr(node_run, "id", None)
            ):
                _schedule_deliverable_archive(run.id, node_run.id)

            cost_update_payload = self._record_node_lifecycle_accounting(
                context=context,
                run=run,
                node_id=node_id,
                node_type=node_type,
                attempt=attempt,
                node_payload=node_payload,
            )

        if event_type in {"node_completed", "node_failed", "node_skipped"}:
            summary_payload = flush_stream_summary(
                run_id=str(run.id),
                node_id=node_id,
                attempt=attempt,
                final_reason=event_type,
            )
            if summary_payload:
                broadcast_node_stream_summary(run=run, payload=summary_payload)

        if cost_update_payload:
            broadcast_cost_update(run=run, payload=cost_update_payload)

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

        message = broadcast_node_run_updated(run=run, node_run=node_run)
        return self._engine_callback_context_success(
            context,
            message,
            reason="node state event accepted",
            backend_event_id=str(event_id or ""),
        )
