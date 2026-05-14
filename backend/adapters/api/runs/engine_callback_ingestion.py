"""Engine callback ingestion helpers for run event adapters."""

# ruff: noqa: F403,F405,I001

from adapters.api.runs.common import *  # noqa: F403


class EngineCallbackIngestionMixin:
    def _save_engine_callback_event(
        self,
        context: EngineCallbackContext,
        event_type_name: str,
        payload: dict[str, Any],
        *,
        derived: bool = False,
    ) -> bool:
        normalized_payload = dict(payload)
        normalized_payload["category"] = normalize_event_category(
            event_type_name,
            category=str(normalized_payload.get("category") or ""),
            payload=normalized_payload,
        )
        try:
            RunEvent.objects.create(
                run=context.run,
                event_type=event_type_name,
                payload=normalized_payload,
                external_id=None if derived else context.event_id,
                trace_id=context.trace_context["trace_id"],
                span_id=context.trace_context["span_id"],
            )
            if not derived and context.event_id and context.callback_organization_id:
                ProcessedCallbackEvent.objects.update_or_create(
                    run=context.run,
                    event_id=str(context.event_id),
                    defaults={
                        "organization_id": context.callback_organization_id,
                        "idempotency_key": context.callback_idempotency_key,
                        "event_type": event_type_name,
                        "request_hash": context.callback_request_hash,
                        "resource_type": "run",
                        "resource_id": str(context.run.id),
                        "status": "applied",
                    },
                )
                record_idempotency_observation(
                    boundary="engine_callback",
                    status="applied",
                    idempotency_key=str(context.event_id),
                    resource_type="run",
                    organization_id=context.callback_organization_id,
                    run_id=context.run.id,
                )
            return True
        except IntegrityError:
            log_event(
                logger,
                logging.INFO,
                "duplicate_run_event_ignored",
                run_id=str(context.run.id),
                trace_id=context.trace_context["trace_id"],
                event_id=context.event_id,
                message="Duplicate run event ignored",
            )
            return False

    def _engine_callback_context_success(
        self,
        context: EngineCallbackContext,
        data: dict[str, Any] | None = None,
        *,
        decision: str = "accepted",
        reason: str = "accepted",
        backend_event_id: str = "",
        safe_to_discard: bool = True,
        conflict_code: str = "",
        idempotency_status: IdempotencyStatus = "applied",
    ) -> Response:
        response = _engine_callback_success(
            data,
            decision=decision,
            reason=reason,
            backend_event_id=backend_event_id,
            safe_to_discard=safe_to_discard,
            conflict_code=conflict_code,
        )
        if not context.event_id:
            return response

        annotate_response(
            response,
            status=idempotency_status,
            idempotency_key=str(context.event_id),
            resource_type="run",
            resource_id=str(context.run.id),
        )
        if context.callback_organization_id:
            ProcessedCallbackEvent.objects.update_or_create(
                run=context.run,
                event_id=str(context.event_id),
                defaults={
                    "organization_id": context.callback_organization_id,
                    "idempotency_key": context.callback_idempotency_key,
                    "event_type": str(context.event_type or ""),
                    "request_hash": context.callback_request_hash,
                    "response_status": response.status_code,
                    "response_body": response_body(response),
                    "resource_type": "run",
                    "resource_id": str(context.run.id),
                    "status": "applied",
                },
            )
        return response

    def _verify_engine_callback_signature(
        self,
        request: Request,
        *,
        verify_signature: bool,
    ) -> Response | None:
        if not verify_signature:
            return None
        ok, reason = s2s.verify_request_once(
            timestamp_ms=request.headers.get("X-Forgegraph-Timestamp", ""),
            signature=request.headers.get("X-Forgegraph-Signature", ""),
            body=request.body or b"",
            method=request.method or "",
            path=request.path,
        )
        if ok:
            cast(Any, request)._forgegraph_s2s_verified = True
            return None
        record_callback_auth_failure(reason)
        _record_engine_callback_dead_letter(
            event={"path": request.path, "body_size": len(request.body or b"")},
            reason="engine callback authentication failed",
            error_class="engine_callback_auth_failed",
        )
        return _engine_callback_problem(
            type_uri="https://forgegraph.dev/problems/engine-callback-unauthorized",
            title="Unauthorized",
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Engine callback verification failed: {reason}",
            decision="reject_invalid",
            reason="engine callback authentication failed",
            safe_to_discard=False,
        )

    def _parse_engine_callback_event(
        self,
        request: Request,
    ) -> tuple[dict[str, Any] | None, Response | None]:
        try:
            parsed_event = parse_engine_event_payload(
                request.data,
                allow_legacy=bool(
                    getattr(settings, "ENGINE_LEGACY_EVENT_CALLBACKS_ENABLED", False)
                ),
            )
        except CanonicalEventValidationError as exc:
            payload = request.data if isinstance(request.data, dict) else {}
            _record_engine_callback_dead_letter(
                event=payload,
                reason="invalid canonical engine event envelope",
                error_class="canonical_event_validation",
                event_id=str(payload.get("event_id") or ""),
                idempotency_key=str(payload.get("idempotency_key") or ""),
                event_type=str(payload.get("type") or ""),
            )
            return None, _engine_callback_problem(
                type_uri="https://forgegraph.dev/problems/canonical-engine-event-validation",
                title="Invalid canonical engine event envelope",
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
                decision="reject_invalid",
                reason="invalid canonical engine event envelope",
                backend_event_id=str(payload.get("event_id") or ""),
                safe_to_discard=True,
            )

        incoming_payload = parsed_event.event
        serializer = EngineExecutionEventSerializer(data=incoming_payload)
        if serializer.is_valid():
            return serializer.validated_data, None
        _record_engine_callback_dead_letter(
            event=incoming_payload if isinstance(incoming_payload, dict) else {},
            reason="invalid engine callback schema",
            error_class="engine_callback_validation",
        )
        return None, _engine_callback_problem(
            type_uri="https://forgegraph.dev/problems/engine-callback-validation",
            title="Invalid engine callback payload",
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The request contains invalid fields.",
            decision="reject_invalid",
            reason="invalid engine callback schema",
            safe_to_discard=True,
            extensions={
                "errors": [
                    {"field": field, "issue": ", ".join(errors)}
                    for field, errors in serializer.errors.items()
                ]
            },
        )

    def _load_engine_callback_run(
        self,
        event: dict[str, Any],
    ) -> tuple[Run | None, Response | None]:
        run_id = event.get("run_id")
        try:
            return Run.objects.get(id=cast(UUID | str, run_id)), None
        except Run.DoesNotExist:
            _record_engine_callback_dead_letter(
                event=event,
                reason="backend cannot prove the run is tombstoned",
                error_class="run_not_found",
            )
            return None, _engine_callback_problem(
                type_uri="https://forgegraph.dev/problems/run-not-found",
                title="Run not found",
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Run with id '{run_id}' not found.",
                decision="retry_required",
                reason="backend cannot prove the run is tombstoned",
                safe_to_discard=False,
                conflict_code="404_UNKNOWN_ENTITY",
            )

    def _engine_callback_trace_context(
        self,
        *,
        request: Request,
        event: dict[str, Any],
        run: Run,
    ) -> dict[str, str]:
        traceparent = str(
            event.get("traceparent")
            or request.headers.get("traceparent")
            or request.headers.get("Traceparent")
            or ""
        ).strip()
        tracestate = str(
            event.get("tracestate")
            or request.headers.get("tracestate")
            or request.headers.get("Tracestate")
            or ""
        ).strip()
        return ensure_trace_context(
            traceparent=traceparent or None,
            tracestate=tracestate or None,
            trace_id=run.trace_id or None,
        )

    def _engine_callback_tenant_response(
        self,
        *,
        event: dict[str, Any],
        run: Run,
    ) -> Response | None:
        tenant_id = str(event.get("tenant_id"))
        if tenant_id == get_tenant_id_for_run(run):
            return None
        _record_engine_callback_dead_letter(
            event=event,
            run=run,
            reason="tenant mismatch for run event",
            error_class="tenant_mismatch",
            event_id=str(event.get("event_id") or ""),
        )
        return _engine_callback_problem(
            type_uri="https://forgegraph.dev/problems/tenant-mismatch",
            title="Tenant mismatch",
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant mismatch for run event.",
            decision="reject_invalid",
            reason="tenant mismatch for run event",
            backend_event_id=str(event.get("event_id") or ""),
            safe_to_discard=False,
        )

    def _engine_callback_duplicate_response(
        self,
        *,
        run: Run,
        event_id: Any,
        callback_request_hash: str,
    ) -> Response | None:
        if not event_id or not RunEvent.objects.filter(run=run, external_id=event_id).exists():
            return None
        processed_callback = ProcessedCallbackEvent.objects.filter(
            run=run,
            event_id=str(event_id),
        ).first()
        if (
            processed_callback is not None
            and processed_callback.request_hash == callback_request_hash
            and processed_callback.response_body
        ):
            record_idempotency_observation(
                boundary="engine_callback",
                status="already_applied",
                idempotency_key=str(event_id),
                resource_type=processed_callback.resource_type or "run",
                organization_id=processed_callback.organization_id,
                run_id=run.id,
            )
            duplicate_response = annotated_response_from_body(
                processed_callback.response_body,
                response_status=processed_callback.response_status,
                status="already_applied",
                idempotency_key=str(event_id),
                resource_type=processed_callback.resource_type or "run",
                resource_id=processed_callback.resource_id or str(run.id),
            )
            body = duplicate_response.data
            if isinstance(body, dict):
                data = body.get("data")
                if isinstance(data, dict):
                    data["duplicate"] = True
                    data["decision"] = "duplicate"
                    data["reason"] = "event already applied"
                    data["safe_to_discard"] = True
            return duplicate_response

        response = _engine_callback_success(
            {"received": True, "duplicate": True},
            decision="duplicate",
            reason="event already applied",
            backend_event_id=str(event_id),
            safe_to_discard=True,
        )
        annotate_response(
            response,
            status="already_applied",
            idempotency_key=str(event_id),
            resource_type="run",
            resource_id=str(run.id),
        )
        return response

    def _engine_callback_idempotency_conflict_response(
        self,
        *,
        run: Run,
        event_id: Any,
        callback_request_hash: str,
        callback_organization_id: UUID | None,
    ) -> Response | None:
        if not event_id:
            return None
        processed_callback = ProcessedCallbackEvent.objects.filter(
            run=run,
            event_id=str(event_id),
        ).first()
        if processed_callback is None or processed_callback.request_hash == callback_request_hash:
            return None
        record_idempotency_observation(
            boundary="engine_callback",
            status="rejected",
            idempotency_key=str(event_id),
            resource_type="run",
            organization_id=callback_organization_id,
            run_id=run.id,
        )
        return _engine_callback_problem(
            type_uri="https://forgegraph.dev/problems/engine-callback-idempotency-conflict",
            title="Engine callback idempotency conflict",
            status_code=status.HTTP_409_CONFLICT,
            detail="Engine callback event_id was already used with a different payload.",
            decision="reject_invalid",
            reason="event idempotency key conflict",
            backend_event_id=str(event_id),
            safe_to_discard=False,
            conflict_code="409_IDEMPOTENCY_CONFLICT",
        )

    def _reconcile_engine_callback_assignment(
        self,
        *,
        run: Run,
        event: dict[str, Any],
        event_type: Any,
        event_id: Any,
        trace_context: dict[str, str],
        normalized_category: str,
    ) -> tuple[str, bool, Response | None]:
        try:
            callback_engine_instance_id, assigned_engine = reconcile_run_engine_instance(
                assigned_engine_id=run.engine_instance_id,
                callback_engine_id=str(event.get("engine_instance_id") or ""),
            )
        except EngineAssignmentError as exc:
            log_event(
                logger,
                logging.WARNING,
                "engine_callback_assignment_conflict",
                run_id=str(run.id),
                trace_id=trace_context["trace_id"],
                event_id=event_id,
                message="Rejected engine callback due to engine ownership mismatch",
                assigned_engine_instance_id=run.engine_instance_id or None,
                callback_engine_instance_id=str(event.get("engine_instance_id") or "").strip()
                or None,
                error_detail=str(exc),
                category=normalized_category,
            )
            _record_engine_callback_dead_letter(
                event=event,
                run=run,
                reason="engine callback ownership conflict",
                error_class="engine_instance_mismatch",
                event_id=str(event_id or ""),
                event_type=str(event_type or ""),
            )
            return (
                "",
                False,
                _engine_callback_problem(
                    type_uri="https://forgegraph.dev/problems/engine-instance-mismatch",
                    title="Engine instance mismatch",
                    status_code=status.HTTP_409_CONFLICT,
                    detail=str(exc),
                    decision="retry_required",
                    reason="engine callback ownership conflict",
                    backend_event_id=str(event_id or ""),
                    safe_to_discard=False,
                    conflict_code="409_ORDERING_CONFLICT",
                ),
            )
        return callback_engine_instance_id, assigned_engine, None

    def _adopt_engine_callback_assignment(
        self,
        *,
        run: Run,
        event: dict[str, Any],
        event_type: Any,
        event_id: Any,
        callback_engine_instance_id: str,
        assigned_engine: bool,
        normalized_category: str,
    ) -> Response | None:
        raw_callback_engine_instance_id = str(event.get("engine_instance_id") or "").strip()
        if not (assigned_engine and callback_engine_instance_id != run.engine_instance_id):
            return None
        if not raw_callback_engine_instance_id:
            return None
        try:
            assert_runtime_state_mutation_allowed(
                event_type,
                category=normalized_category,
                payload=event,
            )
        except EventSafetyViolation as exc:
            _record_engine_callback_dead_letter(
                event=event,
                run=run,
                reason="event safety violation",
                error_class="event_safety_violation",
                event_id=str(event_id or ""),
                event_type=str(event_type or ""),
            )
            return _engine_callback_problem(
                type_uri="https://forgegraph.dev/problems/event-safety-violation",
                title="Event safety violation",
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
                decision="reject_invalid",
                reason="event safety violation",
                backend_event_id=str(event_id or ""),
                safe_to_discard=True,
                conflict_code="409_EVENT_SAFETY_VIOLATION",
            )
        run.engine_instance_id = callback_engine_instance_id
        run.save(update_fields=["engine_instance_id"])
        return None

    def _dispatch_engine_callback_event(self, context: EngineCallbackContext) -> Response:
        event_type = context.event_type
        if event_type == "run.schema_validation":
            return self._handle_engine_schema_validation_event(context)
        if event_type == "node_stream_chunk":
            return self._handle_engine_stream_chunk_event(context)
        if event_type in {
            "memory_write_requested",
            "memory_fact_extracted",
            "summary_created",
            "memory.write_requested",
            "memory.fact_extracted",
            "summary.created",
        }:
            return self._handle_engine_memory_intent_event(context)
        if event_type in {
            "run_started",
            "run_completed",
            "run_failed",
            "run_paused",
            "run_resumed",
            "run_canceled",
        }:
            return self._handle_engine_run_lifecycle_event(context)
        if event_type in {
            "node_started",
            "node_completed",
            "node_failed",
            "node_skipped",
            "node_retrying",
        }:
            return self._handle_engine_node_lifecycle_event(context)

        _record_engine_callback_dead_letter(
            event=context.event,
            run=context.run,
            reason="unknown engine event type",
            error_class="unknown_engine_event",
            event_id=str(context.event_id or ""),
            event_type=str(event_type or ""),
        )
        return _engine_callback_problem(
            type_uri="https://forgegraph.dev/problems/unknown-engine-event",
            title="Unknown engine event",
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unknown event type.",
            decision="reject_invalid",
            reason="unknown engine event type",
            backend_event_id=str(context.event_id or ""),
            safe_to_discard=True,
        )

    def _post_once(self, request: Request, *, verify_signature: bool) -> Response:
        signature_response = self._verify_engine_callback_signature(
            request,
            verify_signature=verify_signature,
        )
        if signature_response is not None:
            return signature_response

        event, parse_response = self._parse_engine_callback_event(request)
        if parse_response is not None:
            return parse_response
        assert event is not None

        run, load_response = self._load_engine_callback_run(event)
        if load_response is not None:
            return load_response
        assert run is not None

        trace_context = self._engine_callback_trace_context(
            request=request,
            event=event,
            run=run,
        )
        tenant_response = self._engine_callback_tenant_response(event=event, run=run)
        if tenant_response is not None:
            return tenant_response

        event_id = event.get("event_id")
        callback_organization_id = run.organization_id or run.owner.default_organization_id
        callback_idempotency_key = normalize_idempotency_key(
            event.get("idempotency_key") or event_id,
        )
        callback_request_hash = hash_request_payload(event)
        duplicate_response = self._engine_callback_duplicate_response(
            run=run,
            event_id=event_id,
            callback_request_hash=callback_request_hash,
        )
        if duplicate_response is not None:
            return duplicate_response
        conflict_response = self._engine_callback_idempotency_conflict_response(
            run=run,
            event_id=event_id,
            callback_request_hash=callback_request_hash,
            callback_organization_id=callback_organization_id,
        )
        if conflict_response is not None:
            return conflict_response
        event_type = event.get("type", "")
        timestamp_ms = event.get("timestamp")
        event_time = _datetime_from_timestamp_ms(timestamp_ms)
        normalized_category = normalize_event_category(
            str(event_type),
            category=str(event.get("category") or ""),
        )
        state_mutation_enabled = bool(
            getattr(settings, "ENGINE_EVENT_STATE_MUTATION_ENABLED", False)
        )
        stale_attempt_response = _ignore_stale_engine_attempt(
            run=run,
            event_type=event_type,
            event=event,
            event_id=str(event_id or ""),
            trace_id=trace_context["trace_id"],
            normalized_category=normalized_category,
        )
        if stale_attempt_response is not None:
            return stale_attempt_response

        callback_engine_instance_id, assigned_engine, assignment_response = (
            self._reconcile_engine_callback_assignment(
                run=run,
                event=event,
                event_type=event_type,
                event_id=event_id,
                trace_context=trace_context,
                normalized_category=normalized_category,
            )
        )
        if assignment_response is not None:
            return assignment_response
        adoption_response = self._adopt_engine_callback_assignment(
            run=run,
            event=event,
            event_type=event_type,
            event_id=event_id,
            callback_engine_instance_id=callback_engine_instance_id,
            assigned_engine=assigned_engine,
            normalized_category=normalized_category,
        )
        if adoption_response is not None:
            return adoption_response

        context = EngineCallbackContext(
            run=run,
            event=event,
            event_type=str(event_type),
            event_id=event_id,
            event_time=event_time,
            trace_context=trace_context,
            normalized_category=normalized_category,
            state_mutation_enabled=state_mutation_enabled,
            callback_engine_instance_id=callback_engine_instance_id,
            callback_organization_id=callback_organization_id,
            callback_idempotency_key=callback_idempotency_key,
            callback_request_hash=callback_request_hash,
        )

        return self._dispatch_engine_callback_event(context)
