"""Run API command adapter module."""

# ruff: noqa: F403,F405,I001

from adapters.api.runs.common import *  # noqa: F403
from adapters.api.runs.command_dispatch import *  # noqa: F403


class RunResumeView(APIView):
    """Resume a paused run (human gate approval/rejection)."""

    permission_classes = [IsAuthenticated]

    def _load_resume_request_context(
        self,
        *,
        request: Request,
        run_id: UUID,
    ) -> tuple[RunResumeRequestContext | None, Response | None]:
        user = cast(User, request.user)
        if not has_min_role(user, "member"):
            return None, error_response(
                code="FORBIDDEN",
                message="You don't have permission to resume runs in this organization.",
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = RunResumeSerializer(data=request.data)
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

        try:
            run = run_queryset_for_user(user).select_related("graph_version__graph").get(id=run_id)
        except Run.DoesNotExist:
            return None, error_response(
                code="NOT_FOUND",
                message=f"Run with id '{run_id}' not found or you do not have access to it",
                status=status.HTTP_404_NOT_FOUND,
            )
        organization = run.organization or user.default_organization
        command_context = build_idempotency_context(
            request=request,
            organization=organization,
            action=f"runs.resume:{run.id}",
            request_payload=serializer.validated_data,
        )
        replayed_response = _replayed_command_response(command_context)
        if replayed_response is not None:
            return None, replayed_response

        node_id = serializer.validated_data["node_id"]
        input_json = serializer.validated_data.get("input_json", {})
        submit_id = _resume_submit_id(
            request=request,
            run_id=run.id,
            node_id=node_id,
            input_json=input_json,
        )
        decision_request_hash = hash_request_payload(
            {
                "run_id": str(run.id),
                "node_id": node_id,
                "input_json": input_json,
            }
        )
        decision_submission, decision_response = self._load_resume_decision_submission(
            run=run,
            organization=organization,
            submit_id=submit_id,
            decision_request_hash=decision_request_hash,
        )
        if decision_response is not None:
            return None, decision_response
        if run.status not in {"paused", "resume_requested"}:
            return None, error_response(
                code="INVALID_STATE",
                message=(
                    f"Cannot resume a run in status '{run.status}'. "
                    "Run must be paused or already resuming."
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        resume_attempt_id = uuid4()
        if decision_submission is not None and decision_submission.resume_attempt_id:
            resume_attempt_id = decision_submission.resume_attempt_id
        return RunResumeRequestContext(
            user=user,
            run=run,
            organization=organization,
            command_context=command_context,
            node_id=node_id,
            input_json=input_json,
            submit_id=submit_id,
            decision_request_hash=decision_request_hash,
            decision_submission=decision_submission,
            resume_attempt_id=resume_attempt_id,
        ), None

    def _resume_preflight_response(
        self,
        *,
        context: RunResumeRequestContext,
        pending_approval_task: ApprovalTask | None,
    ) -> Response | None:
        run = context.run
        if pending_approval_task is None:
            resolved_response = self._resolved_approval_response(
                run=run,
                node_id=context.node_id,
                input_json=context.input_json,
                submit_id=context.submit_id,
                decision_submission=context.decision_submission,
                command_context=context.command_context,
            )
            if resolved_response is not None:
                return resolved_response
        if run.status == "resume_requested":
            return error_response(
                code="INVALID_STATE",
                message="Resume already requested for this run.",
                status=status.HTTP_409_CONFLICT,
            )
        if run.paused_node_id and run.paused_node_id != context.node_id:
            return error_response(
                code="INVALID_NODE",
                message=f"Node '{context.node_id}' does not match paused node '{run.paused_node_id}'",
                status=status.HTTP_400_BAD_REQUEST,
            )

        entitlement_response = check_entitlements(context.user)
        if entitlement_response is not None:
            return entitlement_response
        quota_response = check_llm_quota(context.user)
        if quota_response is not None:
            return quota_response
        return check_llm_budget(context.user)

    def _resume_trace_context(self, *, request: Request, run: Run) -> dict[str, str]:
        traceparent, tracestate = _request_trace_headers(request)
        trace_context = ensure_trace_context(
            traceparent=traceparent,
            tracestate=tracestate,
            trace_id=run.trace_id or None,
        )
        if not run.trace_id:
            run.trace_id = trace_context["trace_id"]
            run.save(update_fields=["trace_id"])
        return trace_context

    def _resume_engine_input(
        self,
        *,
        run: Run,
        user: User,
        input_json: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, Response | None]:
        try:
            resume_llm_access = engine_llm_access_from_graph(
                run.dispatch_graph_json if isinstance(run.dispatch_graph_json, dict) else {},
                user,
            )
            return _engine_input_for_llm_access(input_json, resume_llm_access), None
        except LLMAccessValidationError as exc:
            return None, _llm_access_error_response(exc)

    def _updated_resume_snapshot(
        self,
        *,
        existing_snapshot: RunSnapshot | None,
        resume_attempt_id: UUID,
        resume_requested_at: datetime,
    ) -> RunSnapshot | None:
        if existing_snapshot is None:
            return None
        return RunSnapshot(
            run_id=existing_snapshot.run_id,
            last_completed_node=existing_snapshot.last_completed_node,
            next_node=existing_snapshot.next_node,
            attempt_id=str(resume_attempt_id),
            updated_at=resume_requested_at,
        )

    def _activate_resume_attempt(
        self,
        *,
        run: Run,
        resume_requested_at: datetime,
        resume_attempt_id: UUID,
        trace_context: dict[str, str],
    ) -> Response | None:
        existing_snapshot = get_snapshot(run.id)
        updated_snapshot = self._updated_resume_snapshot(
            existing_snapshot=existing_snapshot,
            resume_attempt_id=resume_attempt_id,
            resume_requested_at=resume_requested_at,
        )
        self._mark_resume_requested(
            run=run,
            resume_requested_at=resume_requested_at,
            resume_attempt_id=resume_attempt_id,
        )
        if updated_snapshot is None:
            return None
        try:
            set_snapshot(updated_snapshot)
        except Exception as exc:
            self._revert_resume_request(
                run=run,
                resume_attempt_id=resume_attempt_id,
                existing_snapshot=existing_snapshot,
                updated_snapshot=updated_snapshot,
            )
            log_event(
                logger,
                logging.ERROR,
                "resume_snapshot_update_failed",
                run_id=str(run.id),
                trace_id=run.trace_id or trace_context["trace_id"],
                resume_attempt_id=str(resume_attempt_id),
                error_message=str(exc),
            )
            return error_response(
                code="SNAPSHOT_UNAVAILABLE",
                message="Unable to activate the resume attempt. Please try again later.",
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return None

    def _touch_resume_liveness(
        self,
        *,
        run: Run,
        resume_requested_at: datetime,
        selected_engine_id: str,
    ) -> Run:
        with transaction.atomic():
            run = Run.objects.select_for_update().get(id=run.id)
            update_fields = touch_run_liveness(
                run,
                event_time=resume_requested_at,
                recovery_state=recovery_state_for_status("resume_requested"),
                engine_instance_id=selected_engine_id,
            )
            if update_fields:
                run.save(update_fields=sorted(set(update_fields)))
            return run

    def _resume_completed_response(
        self,
        *,
        context: RunResumeRequestContext,
        run: Run,
        decision_status: str,
    ) -> Response:
        response = success_response(
            {
                "resumed": True,
                "run_id": str(run.id),
                "resume_attempt_id": str(context.resume_attempt_id),
                "decision_status": decision_status,
            }
        )
        annotate_response(
            response,
            status="applied",
            idempotency_key=context.submit_id,
            resource_type="run",
            resource_id=str(run.id),
        )
        if context.organization is not None:
            ProcessedDecisionSubmission.objects.filter(
                organization=context.organization,
                submit_id=context.submit_id,
            ).update(
                dispatched_at=timezone.now(),
                response_status=response.status_code,
                response_body=response_body(response),
                status="applied",
            )
        return record_processed_command(
            context=context.command_context,
            response=response,
            resource_type="run",
            resource_id=str(run.id),
        )

    def post(self, request: Request, run_id: UUID) -> Response:
        """Resume a paused run with human decision."""
        resume_context, context_response = self._load_resume_request_context(
            request=request,
            run_id=run_id,
        )
        if context_response is not None:
            return context_response
        assert resume_context is not None
        user = resume_context.user
        run = resume_context.run
        organization = resume_context.organization
        node_id = resume_context.node_id
        input_json = resume_context.input_json
        submit_id = resume_context.submit_id
        decision_request_hash = resume_context.decision_request_hash
        resume_attempt_id = resume_context.resume_attempt_id
        log_event(
            logger,
            logging.INFO,
            "runs_resume_requested",
            run_id=str(run.id),
            trace_id=run.trace_id or None,
            node_id=node_id,
            resume_attempt_id=str(resume_attempt_id),
            message="Received run resume request",
        )

        pending_approval_task = run.approval_tasks.filter(node_id=node_id, status="pending").first()
        preflight_response = self._resume_preflight_response(
            context=resume_context,
            pending_approval_task=pending_approval_task,
        )
        if preflight_response is not None:
            return preflight_response

        resume_requested_at = timezone.now()
        trace_context = self._resume_trace_context(request=request, run=run)
        engine_input_json, engine_input_response = self._resume_engine_input(
            run=run,
            user=user,
            input_json=input_json,
        )
        if engine_input_response is not None:
            return engine_input_response
        assert engine_input_json is not None

        activation_response = self._activate_resume_attempt(
            run=run,
            resume_requested_at=resume_requested_at,
            resume_attempt_id=resume_attempt_id,
            trace_context=trace_context,
        )
        if activation_response is not None:
            return activation_response

        decision_status = "accepted" if bool(input_json.get("approved", True)) else "rejected"
        run, decision_resolved_payload = self._record_resume_decision(
            run=run,
            user=user,
            organization=organization,
            pending_approval_task=pending_approval_task,
            node_id=node_id,
            input_json=input_json,
            submit_id=submit_id,
            decision_request_hash=decision_request_hash,
            resume_requested_at=resume_requested_at,
            resume_attempt_id=resume_attempt_id,
            decision_status=decision_status,
            trace_id=trace_context["trace_id"],
        )

        broadcast_run_updated(run)
        if decision_resolved_payload is not None:
            broadcast_decision_resolved(run=run, payload=decision_resolved_payload)

        run, selected_engine_id, dispatch_error = self._dispatch_resume_to_engine(
            run=run,
            node_id=node_id,
            engine_input_json=engine_input_json,
            resume_attempt_id=resume_attempt_id,
            trace_context=trace_context,
        )
        if dispatch_error is not None:
            return dispatch_error

        run = self._touch_resume_liveness(
            run=run,
            resume_requested_at=resume_requested_at,
            selected_engine_id=selected_engine_id,
        )
        broadcast_run_updated(run)

        log_event(
            logger,
            logging.INFO,
            "runs_resume_completed",
            run_id=str(run.id),
            trace_id=run.trace_id or trace_context["trace_id"],
            node_id=node_id,
            resume_attempt_id=str(resume_attempt_id),
            message="Run resume request completed",
        )
        return self._resume_completed_response(
            context=resume_context,
            run=run,
            decision_status=decision_status,
        )

    def _load_resume_decision_submission(
        self,
        *,
        run: Run,
        organization: Organization | None,
        submit_id: str,
        decision_request_hash: str,
    ) -> tuple[ProcessedDecisionSubmission | None, Response | None]:
        if organization is None:
            return None, None

        decision_submission = ProcessedDecisionSubmission.objects.filter(
            organization=organization,
            submit_id=submit_id,
        ).first()
        if decision_submission is None:
            return None, None
        if decision_submission.request_hash != decision_request_hash:
            record_idempotency_observation(
                boundary="human_decision",
                status="rejected",
                idempotency_key=submit_id,
                resource_type="run",
                organization_id=organization.id,
                run_id=run.id,
            )
            return decision_submission, error_response(
                code="IDEMPOTENCY_CONFLICT",
                message="Decision submit id was already used with a different payload.",
                status=status.HTTP_409_CONFLICT,
                details=[{"submit_id": submit_id}],
            )
        replayed_decision = _processed_decision_replay_response(
            decision_submission,
            submit_id=submit_id,
        )
        return decision_submission, replayed_decision

    def _resolved_approval_response(
        self,
        *,
        run: Run,
        node_id: str,
        input_json: dict[str, Any],
        submit_id: str,
        decision_submission: ProcessedDecisionSubmission | None,
        command_context: Any,
    ) -> Response | None:
        resolved_task = (
            run.approval_tasks.filter(node_id=node_id)
            .exclude(status="pending")
            .order_by("-resolved_at", "-created_at")
            .first()
        )
        if resolved_task is None:
            return None
        if resolved_task.result != input_json:
            return error_response(
                code="DECISION_CONFLICT",
                message="Approval task for this node has already been resolved differently.",
                status=status.HTTP_409_CONFLICT,
                details=[
                    {
                        "field": "input_json",
                        "issue": "Conflicting decision does not match the recorded result.",
                    }
                ],
            )

        response = success_response(
            {
                "resumed": True,
                "run_id": str(run.id),
                "duplicate": True,
                "decision_status": resolved_task.status,
            }
        )
        annotate_response(
            response,
            status="already_applied",
            idempotency_key=submit_id,
            resource_type="run",
            resource_id=str(run.id),
        )
        if decision_submission is not None and not decision_submission.response_body:
            decision_submission.response_status = response.status_code
            decision_submission.response_body = response_body(response)
            decision_submission.status = "applied"
            decision_submission.save(
                update_fields=["response_status", "response_body", "status", "updated_at"]
            )
        return record_processed_command(
            context=command_context,
            response=response,
            resource_type="run",
            resource_id=str(run.id),
        )

    def _mark_resume_requested(
        self,
        *,
        run: Run,
        resume_requested_at: datetime,
        resume_attempt_id: UUID,
    ) -> None:
        with transaction.atomic():
            transition = apply_run_status_transition(run, "resume_requested")
            run.resume_requested_at = resume_requested_at
            run.resume_attempt_id = resume_attempt_id
            update_fields = transition.update_fields + [
                "resume_requested_at",
                "resume_attempt_id",
            ]
            update_fields.extend(
                touch_run_liveness(
                    run,
                    event_time=resume_requested_at,
                    recovery_state=recovery_state_for_status("resume_requested"),
                )
            )
            run.save(update_fields=sorted(set(update_fields)))

    def _revert_resume_request(
        self,
        *,
        run: Run,
        resume_attempt_id: UUID,
        existing_snapshot: RunSnapshot | None,
        updated_snapshot: RunSnapshot | None,
    ) -> None:
        with transaction.atomic():
            refreshed_run = Run.objects.select_for_update().get(id=run.id)
            if (
                refreshed_run.status == "resume_requested"
                and refreshed_run.resume_attempt_id == resume_attempt_id
            ):
                transition = apply_run_status_transition(refreshed_run, "paused")
                refreshed_run.resume_requested_at = None
                refreshed_run.resume_attempt_id = None
                revert_fields = transition.update_fields + [
                    "resume_requested_at",
                    "resume_attempt_id",
                ]
                revert_fields.extend(
                    touch_run_liveness(
                        refreshed_run,
                        event_time=timezone.now(),
                        recovery_state=recovery_state_for_status("paused"),
                    )
                )
                refreshed_run.save(update_fields=sorted(set(revert_fields)))
        if existing_snapshot is not None:
            safe_set_snapshot(existing_snapshot)
        elif updated_snapshot is not None:
            safe_delete_snapshot(run.id)

    def _record_resume_decision(
        self,
        *,
        run: Run,
        user: User,
        organization: Organization | None,
        pending_approval_task: ApprovalTask | None,
        node_id: str,
        input_json: dict[str, Any],
        submit_id: str,
        decision_request_hash: str,
        resume_requested_at: datetime,
        resume_attempt_id: UUID,
        decision_status: str,
        trace_id: str,
    ) -> tuple[Run, dict[str, Any] | None]:
        with transaction.atomic():
            run = Run.objects.select_for_update().get(id=run.id)
            update_fields = touch_run_liveness(
                run,
                event_time=resume_requested_at,
                recovery_state=recovery_state_for_status("resume_requested"),
            )
            if update_fields:
                run.save(update_fields=sorted(set(update_fields)))
            self._record_resume_requested_event(
                run=run,
                user=user,
                node_id=node_id,
                resume_requested_at=resume_requested_at,
                resume_attempt_id=resume_attempt_id,
                decision_status=decision_status,
                trace_id=trace_id,
            )
            decision_resolved_payload = self._resolve_pending_approval(
                run=run,
                user=user,
                approval_task=pending_approval_task,
                node_id=node_id,
                input_json=input_json,
                resume_requested_at=resume_requested_at,
                resume_attempt_id=resume_attempt_id,
            )
            self._record_processed_resume_decision(
                run=run,
                organization=organization,
                approval_task=pending_approval_task,
                submit_id=submit_id,
                decision_request_hash=decision_request_hash,
                resume_attempt_id=resume_attempt_id,
            )
            return run, decision_resolved_payload

    def _record_resume_requested_event(
        self,
        *,
        run: Run,
        user: User,
        node_id: str,
        resume_requested_at: datetime,
        resume_attempt_id: UUID,
        decision_status: str,
        trace_id: str,
    ) -> None:
        RunEvent.objects.create(
            run=run,
            event_type="run.resume_requested",
            payload={
                "status": "resume_requested",
                "node_id": node_id,
                "resume_requested_at": resume_requested_at.isoformat(),
                "resume_attempt_id": str(resume_attempt_id),
                "decision_status": decision_status,
                "category": "state",
            },
            trace_id=run.trace_id or trace_id,
        )
        record_audit_log(
            actor=user,
            tenant_id=get_tenant_id_for_run(run),
            action="run.resume_requested",
            resource_type="run",
            resource_id=str(run.id),
            metadata={
                "node_id": node_id,
                "resume_attempt_id": str(resume_attempt_id),
                "decision_status": decision_status,
            },
        )
        _project_run_event_state(
            run=run,
            projection_status="resume_requested",
            trace_id=run.trace_id or trace_id,
            event_type="run.resume_requested",
            event_id=None,
            event_time=resume_requested_at,
            pause_state_json=run.pause_state_json,
            paused_node_id=run.paused_node_id,
        )

    def _resolve_pending_approval(
        self,
        *,
        run: Run,
        user: User,
        approval_task: ApprovalTask | None,
        node_id: str,
        input_json: dict[str, Any],
        resume_requested_at: datetime,
        resume_attempt_id: UUID,
    ) -> dict[str, Any] | None:
        if approval_task is None:
            return None
        approved = bool(input_json.get("approved", True))
        lifecycle_task = approval_task.task_lifecycle
        if lifecycle_task is None:
            lifecycle_task = transition_task_lifecycle(
                run=run,
                node_id=node_id,
                node_type="human_gate",
                to_status="waiting_for_decision",
                attempt_number=1,
                source="hitl_resume",
                idempotency_key=f"task:{run.id}:{node_id}:decision_link:{approval_task.id}",
                reason="approval task linked to lifecycle task",
            ).lifecycle_task
        approval_task.status = "approved" if approved else "rejected"
        approval_task.result = input_json
        approval_task.resolved_at = resume_requested_at
        approval_task.task_lifecycle = lifecycle_task
        approval_task.save(update_fields=["status", "result", "resolved_at", "task_lifecycle"])
        self._record_approval_decision(
            run=run,
            user=user,
            approval_task=approval_task,
            lifecycle_task=lifecycle_task,
            input_json=input_json,
            node_id=node_id,
            resume_requested_at=resume_requested_at,
            resume_attempt_id=resume_attempt_id,
        )
        return {
            "node_id": node_id,
            "status": approval_task.status,
            "resolution": redact_payload(input_json),
            "resume_attempt_id": str(resume_attempt_id),
        }

    def _record_approval_decision(
        self,
        *,
        run: Run,
        user: User,
        approval_task: ApprovalTask,
        lifecycle_task: Any,
        input_json: dict[str, Any],
        node_id: str,
        resume_requested_at: datetime,
        resume_attempt_id: UUID,
    ) -> None:
        organization = run.organization if run.organization_id else user.default_organization
        if organization is not None:
            decision_record, _ = DecisionRecord.objects.update_or_create(
                organization=organization,
                external_key=f"approval:{approval_task.id}",
                defaults={
                    "execution": run,
                    "task": None,
                    "task_lifecycle": lifecycle_task,
                    "agent": None,
                    "decision_type": "human_approval",
                    "status": approval_task.status,
                    "source_approval_task": approval_task,
                    "context_json": approval_task.payload
                    if isinstance(approval_task.payload, dict)
                    else {},
                    "resolution_json": input_json,
                    "requested_at": approval_task.created_at,
                    "resolved_at": resume_requested_at,
                },
            )
            lifecycle_task.current_decision = decision_record
            lifecycle_task.save(update_fields=["current_decision", "updated_at"])
        PreferenceEventService().record_hitl_feedback(
            approval_task=approval_task,
            actor=user,
            final_value=input_json,
        )
        record_audit_log(
            actor=user,
            tenant_id=get_tenant_id_for_user(user),
            action="approval.resolved",
            resource_type="approval",
            resource_id=str(approval_task.id),
            metadata={
                "run_id": str(run.id),
                "node_id": node_id,
                "status": approval_task.status,
                "resume_attempt_id": str(resume_attempt_id),
            },
        )

    def _record_processed_resume_decision(
        self,
        *,
        run: Run,
        organization: Organization | None,
        approval_task: ApprovalTask | None,
        submit_id: str,
        decision_request_hash: str,
        resume_attempt_id: UUID,
    ) -> None:
        if organization is None:
            return
        ProcessedDecisionSubmission.objects.update_or_create(
            organization=organization,
            submit_id=submit_id,
            defaults={
                "run": run,
                "approval_task": approval_task,
                "request_hash": decision_request_hash,
                "resume_attempt_id": resume_attempt_id,
                "status": "applied",
            },
        )
        record_idempotency_observation(
            boundary="human_decision",
            status="applied",
            idempotency_key=submit_id,
            resource_type="run",
            organization_id=organization.id,
            run_id=run.id,
        )

    def _mark_resume_dispatch_failed(
        self,
        *,
        run: Run,
        node_id: str,
        resume_attempt_id: UUID,
        trace_id: str,
        reason: str,
        error_message: str,
    ) -> Run:
        failure_time = timezone.now()
        with transaction.atomic():
            failed_run = Run.objects.select_for_update().get(id=run.id)
            if (
                failed_run.status == "resume_requested"
                and failed_run.resume_attempt_id == resume_attempt_id
            ):
                failed_run.recovery_state = "resume_dispatch_failed"
                failed_run.recovery_reason = reason[:64]
                update_fields = ["recovery_state", "recovery_reason"]
                update_fields.extend(
                    touch_run_liveness(
                        failed_run,
                        event_time=failure_time,
                        recovery_state="resume_dispatch_failed",
                    )
                )
                failed_run.save(update_fields=sorted(set(update_fields)))
                RunEvent.objects.create(
                    run=failed_run,
                    event_type="run.resume_dispatch_failed",
                    payload={
                        "status": "resume_requested",
                        "recovery_state": "resume_dispatch_failed",
                        "recovery_reason": reason,
                        "error_message": redact_payload(error_message),
                        "resume_attempt_id": str(resume_attempt_id),
                        "node_id": node_id,
                        "category": "state",
                    },
                    trace_id=failed_run.trace_id or trace_id,
                )
                _project_run_event_state(
                    run=failed_run,
                    projection_status="resume_requested",
                    trace_id=failed_run.trace_id or trace_id,
                    event_type="run.resume_dispatch_failed",
                    event_id=None,
                    event_time=failure_time,
                    pause_state_json=failed_run.pause_state_json,
                    paused_node_id=failed_run.paused_node_id,
                )
            return failed_run

    def _dispatch_resume_to_engine(
        self,
        *,
        run: Run,
        node_id: str,
        engine_input_json: dict[str, Any],
        resume_attempt_id: UUID,
        trace_context: dict[str, str],
    ) -> tuple[Run, str, Response | None]:
        try:
            selected_engine_id = self._send_resume_to_engine(
                run=run,
                node_id=node_id,
                engine_input_json=engine_input_json,
                resume_attempt_id=resume_attempt_id,
                trace_context=trace_context,
            )
        except EngineConnectionError as exc:
            failed_run = self._mark_resume_dispatch_failed(
                run=run,
                node_id=node_id,
                resume_attempt_id=resume_attempt_id,
                trace_id=trace_context["trace_id"],
                reason="engine_unavailable",
                error_message=str(exc),
            )
            broadcast_run_updated(failed_run)
            log_event(
                logger,
                logging.ERROR,
                "engine_resume_connection_failed",
                run_id=str(failed_run.id),
                trace_id=failed_run.trace_id or trace_context["trace_id"],
                resume_attempt_id=str(resume_attempt_id),
                error_message=str(exc),
            )
            return (
                failed_run,
                "",
                error_response(
                    code="ENGINE_UNAVAILABLE",
                    message="The execution engine is not available. Please try again later.",
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                ),
            )
        except EngineExecutionError as exc:
            failed_run = self._mark_resume_dispatch_failed(
                run=run,
                node_id=node_id,
                resume_attempt_id=resume_attempt_id,
                trace_id=trace_context["trace_id"],
                reason="engine_rejected_resume",
                error_message=str(exc),
            )
            broadcast_run_updated(failed_run)
            log_event(
                logger,
                logging.ERROR,
                "engine_resume_failed",
                run_id=str(failed_run.id),
                trace_id=failed_run.trace_id or trace_context["trace_id"],
                resume_attempt_id=str(resume_attempt_id),
                error_message=str(exc),
            )
            return (
                failed_run,
                "",
                error_response(
                    code="ENGINE_ERROR",
                    message=str(exc),
                    status=status.HTTP_400_BAD_REQUEST,
                ),
            )
        return run, selected_engine_id, None

    def _send_resume_to_engine(
        self,
        *,
        run: Run,
        node_id: str,
        engine_input_json: dict[str, Any],
        resume_attempt_id: UUID,
        trace_context: dict[str, str],
    ) -> str:
        with start_backend_span(
            "runs.resume",
            traceparent=trace_context["traceparent"],
            tracestate=trace_context["tracestate"],
            attributes={
                "forgegraph.run_id": str(run.id),
                "forgegraph.node_id": node_id,
                "forgegraph.trigger": "resume",
            },
        ):
            selected_engine_id, engine_client = get_engine_client_for_run(run=run)
            with engine_client as engine:
                engine.resume_run(
                    run_id=run.id,
                    node_id=node_id,
                    input_json=engine_input_json,
                    resume_attempt_id=str(resume_attempt_id),
                    traceparent=trace_context["traceparent"],
                    tracestate=trace_context["tracestate"],
                )
        log_event(
            logger,
            logging.INFO,
            "runs_resume_dispatched",
            run_id=str(run.id),
            trace_id=run.trace_id or trace_context["trace_id"],
            node_id=node_id,
            resume_attempt_id=str(resume_attempt_id),
            engine_instance_id=selected_engine_id,
            message="Dispatched run resume to engine",
        )
        return selected_engine_id
