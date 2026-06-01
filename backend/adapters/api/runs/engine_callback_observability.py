"""Engine callback observability handlers for run event adapters."""

# ruff: noqa: F403,F405,I001

from adapters.api.runs.common import *  # noqa: F403


class EngineCallbackObservabilityMixin(EngineCallbackComposableMixin):
    def _handle_engine_schema_validation_event(self, context: EngineCallbackContext) -> Response:
        run = context.run
        event = context.event
        event_id = context.event_id
        payload = redact_payload(event.get("output") or {})
        self._save_engine_callback_event(context, "run.schema_validation", payload)
        message = broadcast_run_schema_validation(run=run, payload=payload)
        return self._engine_callback_context_success(
            context,
            message,
            reason="schema validation event accepted",
            backend_event_id=str(event_id or ""),
        )

    def _handle_engine_stream_chunk_event(self, context: EngineCallbackContext) -> Response:
        run = context.run
        event = context.event
        event_id = context.event_id
        event_time = context.event_time
        output = event.get("output")
        payload = output if isinstance(output, dict) else {}
        chunk = str(redact_payload(payload.get("chunk") or ""))
        chunk_index = int(payload.get("chunk_index") or 0)
        stream_node_id = str(event.get("node_id") or "")
        stream_node_type = str(event.get("node_type") or "")
        stream_attempt = int(cast(int | str, event.get("attempt") or 1))
        stream_payload = {
            "node_id": stream_node_id,
            "node_type": stream_node_type,
            "attempt": stream_attempt,
            "chunk": chunk,
            "chunk_index": chunk_index,
        }
        agent_chunk = _parse_agent_stream_chunk(chunk)
        if agent_chunk:
            normalized_agent_event = _normalize_agent_stream_event(
                node_id=stream_node_id,
                node_type=stream_node_type,
                attempt=stream_attempt,
                chunk_index=chunk_index,
                payload=agent_chunk,
            )
            stream_payload["agent_event"] = normalized_agent_event
        self._save_engine_callback_event(context, "node_stream.chunk", stream_payload)
        if agent_chunk:
            self._save_engine_callback_event(
                context,
                str(agent_chunk.get("event") or "agent.unknown"),
                cast(dict[str, Any], stream_payload["agent_event"]),
                derived=True,
            )
        summary_payload = update_stream_summary(
            run_id=str(run.id),
            payload=stream_payload,
            event_time=event_time,
        )
        if summary_payload:
            broadcast_node_stream_summary(run=run, payload=summary_payload)
        message = broadcast_node_stream_chunk(run=run, payload=stream_payload)
        return self._engine_callback_context_success(
            context,
            message,
            reason="stream chunk event accepted",
            backend_event_id=str(event_id or ""),
        )

    def _handle_engine_memory_intent_event(self, context: EngineCallbackContext) -> Response:
        run = context.run
        event = context.event
        event_type = context.event_type
        event_id = context.event_id
        memory_payload = _memory_intent_payload_from_event(event)
        try:
            memory_result = BackendMemoryIntentService().apply_engine_memory_intent(
                run=run,
                event_type=str(event_type),
                payload=memory_payload,
                event_id=str(event_id or ""),
            )
        except ValueError as exc:
            _record_engine_callback_dead_letter(
                event=event,
                run=run,
                reason="invalid backend memory intent",
                error_class="memory_intent_validation",
                event_id=str(event_id or ""),
                event_type=str(event_type or ""),
            )
            return _engine_callback_problem(
                type_uri="https://forgegraph.dev/problems/memory-intent-validation",
                title="Invalid memory intent",
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
                decision="reject_invalid",
                reason="invalid backend memory intent",
                backend_event_id=str(event_id or ""),
                safe_to_discard=True,
            )
        if not self._save_engine_callback_event(
            context, event_type, _serialize_event_payload(redact_payload(memory_payload))
        ):
            return self._engine_callback_context_success(
                context,
                {"received": True, "duplicate": True},
                decision="duplicate",
                reason="event already applied",
                backend_event_id=str(event_id or ""),
                safe_to_discard=True,
                idempotency_status="already_applied",
            )
        record_audit_log(
            actor=None,
            tenant_id=get_tenant_id_for_run(run),
            action=f"memory.{event_type}",
            resource_type="run",
            resource_id=str(run.id),
            metadata={
                "event_id": event_id,
                "event_type": event_type,
                "source": "engine_callback",
                "backend_owner": "memory_service",
                "observation_count": memory_result.observation_count,
            },
        )
        return self._engine_callback_context_success(
            context,
            {
                "received": True,
                "event_type": event_type,
                "authoritative_state_updated": True,
                "memory_owner": "backend",
                "memory_observation_count": memory_result.observation_count,
            },
            reason="backend memory intent event accepted",
            backend_event_id=str(event_id or ""),
        )
