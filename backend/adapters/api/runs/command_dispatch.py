"""Run API command adapter module."""

# ruff: noqa: F403,F405,I001

from adapters.api.runs.common import *  # noqa: F403


def _mark_engine_dispatch_failure(
    dispatch: RunEngineDispatch,
    *,
    log_name: str,
    error_prefix: str,
    exc: Exception,
    response_code: str,
    response_message: str,
    response_status: int,
) -> Response:
    run = dispatch.run
    log_event(
        logger,
        logging.ERROR,
        log_name,
        run_id=str(run.id),
        trace_id=run.trace_id or dispatch.trace_metadata["trace_id"],
        error_message=str(exc),
    )
    transition = apply_run_status_transition(run, "failed")
    run.ended_at = timezone.now()
    run.error_message = f"{error_prefix}: {exc}"
    run.save(update_fields=sorted(set(transition.update_fields + ["ended_at", "error_message"])))
    if dispatch.failure_task_source:
        mark_run_tasks_terminal(
            run=run,
            status_value="failed",
            source=dispatch.failure_task_source,
            reason=run.error_message,
        )
    record_run_completed("failed", run.duration_ms)
    broadcast_run_updated(run)
    return error_response(
        code=response_code,
        message=response_message,
        status=response_status,
    )


def _dispatch_run_to_engine(dispatch: RunEngineDispatch) -> Response | None:
    callback_url = resolve_engine_callback_url(run_id=str(dispatch.run.id))
    memory_config_json = build_memory_config_json(
        dispatch.graph_version.graph,
        dispatch.run.owner,
        session_id=dispatch.session_id,
    )
    engine_input_json = _engine_input_for_llm_access(
        dispatch.run.input_json
        if isinstance(dispatch.run.input_json, dict)
        else dispatch.input_json,
        dispatch.llm_access,
    )
    try:
        with start_backend_span(
            dispatch.span_name,
            traceparent=dispatch.trace_metadata["traceparent"],
            tracestate=dispatch.trace_metadata["tracestate"],
            attributes={
                "forgegraph.run_id": str(dispatch.run.id),
                "forgegraph.graph_version_id": str(dispatch.graph_version.id),
                "forgegraph.trigger": dispatch.trigger,
            },
        ):
            selected_engine_id, engine_client = get_engine_assignment(
                run_id=str(dispatch.run.id),
                callback_url=callback_url,
            )
            with engine_client as engine:
                engine.start_run(
                    run_id=dispatch.run.id,
                    graph_json=dispatch.outbound_graph,
                    input_json=engine_input_json,
                    memory_config_json=memory_config_json,
                    tenant_id=dispatch.tenant_id,
                    session_id=dispatch.session_id,
                    traceparent=dispatch.trace_metadata["traceparent"],
                    tracestate=dispatch.trace_metadata["tracestate"],
                )
                transition = apply_run_status_transition(dispatch.run, "running")
                update_fields = transition.update_fields
                update_fields.extend(
                    touch_run_liveness(
                        dispatch.run,
                        recovery_state=recovery_state_for_status("running"),
                        engine_instance_id=selected_engine_id,
                    )
                )
                dispatch.run.save(update_fields=sorted(set(update_fields)))
                _persist_run_updated_event(dispatch.run)
                record_run_started()
                broadcast_run_updated(dispatch.run)
    except EngineConnectionError as exc:
        return _mark_engine_dispatch_failure(
            dispatch,
            log_name="engine_connection_failed",
            error_prefix="Engine connection failed",
            exc=exc,
            response_code="ENGINE_UNAVAILABLE",
            response_message="The execution engine is not available. Please try again later.",
            response_status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    except EngineExecutionError as exc:
        return _mark_engine_dispatch_failure(
            dispatch,
            log_name=dispatch.engine_rejected_event,
            error_prefix="Engine rejected run",
            exc=exc,
            response_code="ENGINE_ERROR",
            response_message=str(exc),
            response_status=status.HTTP_400_BAD_REQUEST,
        )
    return None


__all__ = [name for name in globals() if not name.startswith("__")]
