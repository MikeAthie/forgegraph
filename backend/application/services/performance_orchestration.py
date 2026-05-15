"""Generic whiteboard-scoped performance measurement and optimization orchestration."""

from __future__ import annotations

import hashlib
from datetime import date, timedelta
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone

from application.services.company_access import has_company_access
from application.services.company_ops import create_company_signal
from application.services.domain_event_outbox import sanitize_outbox_payload
from application.services.operating_model_packs import OperatingModelPackError, load_pack_definition
from application.services.pack_tool_executions import PackToolExecutionError, execute_pack_tool
from application.services.rbac import has_min_role
from application.services.routing import register_department, route_event_to_department
from infrastructure.orm.models import (
    CompanyOperatingModelInstallation,
    CompanyProgram,
    DepartmentRegistry,
    EvaluationRun,
    EvaluationScorecard,
    Graph,
    GraphVersion,
    MetricSnapshot,
    ReportRun,
    Run,
    StateProjection,
    User,
    WorkWhiteboard,
)

PERFORMANCE_SCHEMA_VERSION = "whiteboard_performance_v1"
PERFORMANCE_CONFIG_KEYS = ("performance_policies", "measurement_policies")
PERFORMANCE_PROJECTION_PREFIX = "whiteboard_performance"
SUPPORTED_OPERATORS = {">=", ">", "<=", "<", "==", "!=", "in"}
DEPLOYMENT_READY_STATUSES = {"prepared", "partial", "executed"}


class PerformanceOrchestrationError(ValueError):
    """Domain error for generic performance orchestration."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.details = details or []
        super().__init__(message)


def load_performance_policy(
    *,
    whiteboard: WorkWhiteboard,
    policy_id: str = "",
    definition: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve a performance policy for one whiteboard from explicit data or installed packs."""

    requested = str(policy_id or "").strip()
    if definition is not None:
        normalized = _normalize_policy(
            sanitize_outbox_payload(definition),
            source_policy_id=str(definition.get("source_policy_id") or "explicit_fixture"),
            pack_id=str(definition.get("pack_id") or "explicit_fixture"),
        )
        if requested and normalized["policy_id"] != requested:
            raise PerformanceOrchestrationError(
                "performance_policy_not_found",
                "The requested performance policy was not found for this whiteboard.",
                details=[{"policy_id": requested}],
            )
        return normalized

    candidates = list_available_performance_policies(whiteboard=whiteboard)
    for candidate in candidates:
        if requested and str(candidate.get("policy_id") or "") != requested:
            continue
        return _normalize_policy(
            sanitize_outbox_payload(candidate),
            source_policy_id=str(candidate.get("source_policy_id") or candidate.get("pack_id") or ""),
            pack_id=str(candidate.get("pack_id") or ""),
        )
    if not requested and candidates:
        return _normalize_policy(
            sanitize_outbox_payload(candidates[0]),
            source_policy_id=str(candidates[0].get("source_policy_id") or candidates[0].get("pack_id") or ""),
            pack_id=str(candidates[0].get("pack_id") or ""),
        )
    raise PerformanceOrchestrationError(
        "performance_policy_not_found",
        "No active performance policy was found for this whiteboard.",
        details=[{"policy_id": requested}],
    )


def list_available_performance_policies(*, whiteboard: WorkWhiteboard) -> list[dict[str, Any]]:
    policies: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in _policy_candidates(whiteboard):
        policy_id = str(candidate.get("policy_id") or "")
        if not policy_id or policy_id in seen:
            continue
        policies.append(candidate)
        seen.add(policy_id)
    projection = _performance_projection(whiteboard)
    if projection is not None and isinstance(projection.json_state, dict):
        definition = projection.json_state.get("policy") if isinstance(projection.json_state.get("policy"), dict) else {}
        policy_id = str(definition.get("policy_id") or "")
        if policy_id and policy_id not in seen:
            policies.append(definition)
    return policies


def performance_contract_for_whiteboard(
    *,
    whiteboard: WorkWhiteboard,
    user: User | None = None,
    include_internal: bool = False,
) -> dict[str, Any] | None:
    """Return the sanitized performance contract for the whiteboard, if a policy exists."""

    try:
        policy = load_performance_policy(whiteboard=whiteboard)
    except PerformanceOrchestrationError:
        projection = _performance_projection(whiteboard)
        if projection is None or not isinstance(projection.json_state, dict):
            return None
        policy = projection.json_state.get("policy") if isinstance(projection.json_state.get("policy"), dict) else {}
        if not policy:
            return None
    internal = include_internal or _can_manage_performance(user=user, whiteboard=whiteboard)
    return _performance_contract(whiteboard=whiteboard, policy=policy, user=user, include_internal=internal)


def list_performance_state(
    *,
    user: User,
    whiteboard: WorkWhiteboard,
    policy_id: str = "",
    definition: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not has_company_access(user, whiteboard.company, "viewer"):
        raise PerformanceOrchestrationError(
            "permission_denied",
            "You do not have access to this whiteboard performance state.",
        )
    policy = load_performance_policy(whiteboard=whiteboard, policy_id=policy_id, definition=definition)
    return _performance_contract(
        whiteboard=whiteboard,
        policy=policy,
        user=user,
        include_internal=_can_manage_performance(user=user, whiteboard=whiteboard),
    )


def start_performance_review_for_whiteboard(
    *,
    user: User,
    whiteboard: WorkWhiteboard,
    policy_id: str = "",
    definition: dict[str, Any] | None = None,
    period_start: date | None = None,
    period_end: date | None = None,
) -> dict[str, Any]:
    """Start or replay a generic performance review loop for one whiteboard."""

    _ensure_can_manage_performance(user=user, whiteboard=whiteboard)
    policy = load_performance_policy(whiteboard=whiteboard, policy_id=policy_id, definition=definition)
    _ensure_review_start_allowed(whiteboard=whiteboard, policy=policy)
    period = _review_period(policy=policy, period_start=period_start, period_end=period_end)
    existing = _performance_state(whiteboard)
    if (
        existing.get("policy_id") == policy["policy_id"]
        and existing.get("period_start") == period["period_start"]
        and existing.get("period_end") == period["period_end"]
        and existing.get("sources")
    ):
        return _performance_contract(whiteboard=whiteboard, policy=policy, user=user, include_internal=True)

    with transaction.atomic():
        sources = create_metric_collection_tasks(
            user=user,
            whiteboard=whiteboard,
            policy=policy,
            period_start=period["period_start"],
            period_end=period["period_end"],
        )
        snapshot = create_metric_snapshot(
            user=user,
            whiteboard=whiteboard,
            policy=policy,
            sources=sources,
            period_start=period["period_start"],
            period_end=period["period_end"],
        )
        _upsert_performance_projection(
            whiteboard=whiteboard,
            policy=policy,
            state={
                "status": _overall_status(sources),
                "sources": sources,
                "metric_snapshot_id": str(snapshot.id) if snapshot is not None else "",
                "tool_execution_ids": _ids_from_sources(sources, "tool_execution_id"),
                "company_signal_ids": _ids_from_sources(sources, "company_signal_id"),
                "routing_record_ids": _ids_from_sources(sources, "routing_record_id"),
                "period_start": period["period_start"],
                "period_end": period["period_end"],
                "started_at": timezone.now().isoformat(),
            },
        )
    _refresh_whiteboard_snapshot(whiteboard)
    return _performance_contract(whiteboard=whiteboard, policy=policy, user=user, include_internal=True)


def create_metric_collection_tasks(
    *,
    user: User,
    whiteboard: WorkWhiteboard,
    policy: dict[str, Any],
    period_start: str,
    period_end: str,
) -> list[dict[str, Any]]:
    """Evaluate policy-defined metric sources and create durable generic receipts or blockers."""

    _ensure_can_manage_performance(user=user, whiteboard=whiteboard)
    existing = _performance_state(whiteboard)
    existing_sources = {
        str(item.get("id") or ""): item
        for item in list(existing.get("sources") or [])
        if isinstance(item, dict)
    }
    result: list[dict[str, Any]] = []
    for source in _metric_sources(policy):
        source_id = str(source["id"])
        previous = existing_sources.get(source_id, {})
        readiness = _readiness_for_source(whiteboard=whiteboard, source=source)
        if readiness["status"] == "blocked":
            blocked = _mark_source_blocked(
                user=user,
                whiteboard=whiteboard,
                policy=policy,
                source=source,
                reason_code=str(readiness.get("reason_code") or "blocked"),
                reason=str(readiness.get("reason") or "Metric source is blocked."),
            )
            result.append({**previous, **blocked, "status": "blocked"})
            continue
        collected = collect_metric_source(
            user=user,
            whiteboard=whiteboard,
            policy=policy,
            source=source,
            period_start=period_start,
            period_end=period_end,
        )
        result.append({**previous, **collected})
    return result


def collect_metric_source(
    *,
    user: User,
    whiteboard: WorkWhiteboard,
    policy: dict[str, Any],
    source: dict[str, Any],
    period_start: str,
    period_end: str,
) -> dict[str, Any]:
    """Collect one policy-defined metric source through a declared pack tool."""

    tool_id = str(source.get("tool_id") or "").strip()
    source_id = str(source["id"])
    operation = _performance_run(user=user, whiteboard=whiteboard, policy=policy, source=source)
    receipt: dict[str, Any] | None = None
    tool_execution_id = ""
    if tool_id:
        try:
            receipt = execute_pack_tool(
                company=whiteboard.company,
                user=user,
                operation=operation,
                tool_id=tool_id,
                inputs=_tool_inputs(
                    whiteboard=whiteboard,
                    policy=policy,
                    source=source,
                    period_start=period_start,
                    period_end=period_end,
                ),
                dry_run=True,
                idempotency_key=_performance_key(
                    whiteboard=whiteboard,
                    policy=policy,
                    suffix=f"tool:{source_id}",
                ),
            )
            tool_execution_id = str(receipt.get("tool_execution_id") or "")
        except PackToolExecutionError as exc:
            return _mark_source_blocked(
                user=user,
                whiteboard=whiteboard,
                policy=policy,
                source=source,
                reason_code=exc.code,
                reason=exc.message,
                operation=operation,
            )
    return _source_payload(
        source=source,
        status="collected",
        operation_id=str(operation.id),
        tool_execution_id=tool_execution_id,
        metrics=_source_metric_values(source),
        receipt=receipt,
        include_internal=True,
    )


def create_metric_snapshot(
    *,
    user: User,
    whiteboard: WorkWhiteboard,
    policy: dict[str, Any],
    sources: list[dict[str, Any]],
    period_start: str,
    period_end: str,
) -> MetricSnapshot | None:
    """Create or return the performance metric snapshot for this whiteboard period."""

    key = _performance_key(whiteboard=whiteboard, policy=policy, suffix=f"snapshot:{period_start}:{period_end}")
    existing = MetricSnapshot.objects.filter(
        organization=whiteboard.organization,
        company=whiteboard.company,
        metric_sources_json__whiteboard_id=str(whiteboard.id),
        metric_sources_json__idempotency_key=key,
    ).first()
    if existing is not None:
        return existing
    values = _collected_metric_values(sources)
    source_refs = {
        "schema_version": PERFORMANCE_SCHEMA_VERSION,
        "whiteboard_id": str(whiteboard.id),
        "policy_id": policy["policy_id"],
        "source_policy_id": policy.get("source_policy_id"),
        "pack_id": policy.get("pack_id"),
        "idempotency_key": key,
        "sources": _source_refs(sources),
        "blocked_sources": [
            _source_ref(item)
            for item in sources
            if str(item.get("status") or "") == "blocked"
        ],
    }
    return MetricSnapshot.objects.create(
        organization=whiteboard.organization,
        company=whiteboard.company,
        program=_program_for_whiteboard(whiteboard),
        period_start=_parse_date(period_start),
        period_end=_parse_date(period_end),
        metric_values_json=sanitize_outbox_payload(values),
        metric_sources_json=sanitize_outbox_payload(source_refs),
        source_type="computed",
        notes="Whiteboard performance metric snapshot from configured policy.",
        created_by=user,
    )


def create_performance_report(
    *,
    user: User,
    whiteboard: WorkWhiteboard,
    policy_id: str = "",
    definition: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _ensure_can_manage_performance(user=user, whiteboard=whiteboard)
    policy = load_performance_policy(whiteboard=whiteboard, policy_id=policy_id, definition=definition)
    state = _performance_state(whiteboard)
    snapshot = _metric_snapshot_from_state(whiteboard=whiteboard, state=state)
    if snapshot is None:
        raise PerformanceOrchestrationError(
            "metric_snapshot_required",
            "Performance report requires a started review with a metric snapshot.",
        )
    existing_id = str(state.get("report_run_id") or "")
    existing = ReportRun.objects.filter(id=existing_id, company=whiteboard.company).first() if existing_id else None
    if existing is not None:
        return _performance_contract(whiteboard=whiteboard, policy=policy, user=user, include_internal=True)
    report = _assemble_performance_report(user=user, whiteboard=whiteboard, policy=policy, snapshot=snapshot, state=state)
    _upsert_performance_projection(
        whiteboard=whiteboard,
        policy=policy,
        state={
            **state,
            "status": "reported",
            "report_run_id": str(report.id),
            "reported_at": timezone.now().isoformat(),
        },
    )
    _refresh_whiteboard_snapshot(whiteboard)
    return _performance_contract(whiteboard=whiteboard, policy=policy, user=user, include_internal=True)


def evaluate_performance(
    *,
    user: User,
    whiteboard: WorkWhiteboard,
    policy_id: str = "",
    definition: dict[str, Any] | None = None,
    scorecard: dict[str, Any] | None = None,
) -> EvaluationRun:
    """Evaluate performance using policy-defined generic criteria."""

    _ensure_can_manage_performance(user=user, whiteboard=whiteboard)
    policy = load_performance_policy(whiteboard=whiteboard, policy_id=policy_id, definition=definition)
    state = _performance_state(whiteboard)
    snapshot = _metric_snapshot_from_state(whiteboard=whiteboard, state=state)
    if snapshot is None:
        raise PerformanceOrchestrationError(
            "metric_snapshot_required",
            "Performance evaluation requires a started review with a metric snapshot.",
        )
    submitted = _evaluation_inputs(snapshot=snapshot, state=state, scorecard=scorecard or {})
    criteria_results = [_criterion_result(criterion, submitted) for criterion in _evaluation_criteria(policy)]
    result = _evaluation_result(criteria_results)
    composite = _composite_score(criteria_results)
    with transaction.atomic():
        evaluation = EvaluationRun.objects.create(
            organization=whiteboard.organization,
            company=whiteboard.company,
            program=snapshot.program,
            operation=_evaluation_run(user=user, whiteboard=whiteboard, policy=policy),
            profile_key=str(policy.get("evaluation_profile_id") or policy["policy_id"])[:160],
            status="PASS" if result == "pass" else "BLOCK" if result == "fail" else "WARN",
            score=composite,
            grade=_grade(composite),
            input_refs_json=[
                {"whiteboard_id": str(whiteboard.id), "policy_id": policy["policy_id"]},
                {"metric_snapshot_id": str(snapshot.id)},
                {"report_run_id": str(state.get("report_run_id") or "")},
            ],
            result_json=sanitize_outbox_payload(
                {
                    "schema_version": PERFORMANCE_SCHEMA_VERSION,
                    "whiteboard_id": str(whiteboard.id),
                    "policy_id": policy["policy_id"],
                    "source_policy_id": policy.get("source_policy_id"),
                    "pack_id": policy.get("pack_id"),
                    "performance_result": result,
                    "criteria_results": criteria_results,
                    "submitted_scorecard": sanitize_outbox_payload(scorecard or {}),
                    "conditions": _matched_conditions(state=state, criteria_results=criteria_results, submitted=submitted),
                }
            ),
            created_by=user,
            evaluated_at=timezone.now(),
        )
        EvaluationScorecard.objects.create(
            evaluation=evaluation,
            organization=whiteboard.organization,
            company=whiteboard.company,
            dimensions_json=sanitize_outbox_payload({"criteria": criteria_results, "submitted_scorecard": scorecard or {}}),
            composite_score=composite,
            grade=_grade(composite),
        )
        routing_records = route_optimization_work(
            user=user,
            whiteboard=whiteboard,
            policy=policy,
            evaluation=evaluation,
        )
        _upsert_performance_projection(
            whiteboard=whiteboard,
            policy=policy,
            state={
                **state,
                "status": "evaluated",
                "evaluation_id": str(evaluation.id),
                "routing_record_ids": sorted(
                    {
                        *list(state.get("routing_record_ids") or []),
                        *[str(record.id) for record in routing_records],
                    }
                ),
                "evaluated_at": timezone.now().isoformat(),
            },
        )
    _refresh_whiteboard_snapshot(whiteboard)
    return evaluation


def route_optimization_work(
    *,
    user: User,
    whiteboard: WorkWhiteboard,
    policy: dict[str, Any],
    evaluation: EvaluationRun,
) -> list[Any]:
    """Create idempotent optimization routing records from policy-defined conditions."""

    conditions = set(_result_json(evaluation).get("conditions") or [])
    records = []
    for rule in _routing_rules(policy):
        condition = str(rule.get("condition") or "").strip()
        if condition and condition not in conditions:
            continue
        department_slug = str(rule.get("route_to_department") or rule.get("route_to") or "").strip()
        if not department_slug:
            continue
        if bool(rule.get("create_signal", False)):
            signal = _optimization_signal(
                user=user,
                whiteboard=whiteboard,
                policy=policy,
                evaluation=evaluation,
                rule=rule,
                condition=condition,
            )
        else:
            signal = None
        department = register_department(
            organization=whiteboard.organization,
            slug=department_slug,
            name=str(rule.get("department_name") or _label(department_slug)),
            department_type=str(rule.get("department_type") or department_slug)[:64],
            service_tags=["performance", "optimization"],
            metadata={"system_managed": True, "source": "performance_orchestration"},
        )
        records.append(
            route_event_to_department(
                company=whiteboard.company,
                department=department,
                user=user,
                event_type="whiteboard.performance.optimization",
                trigger_type="whiteboard.performance.optimization",
                communication_thread=whiteboard.communication_thread,
                communication_message=whiteboard.source_message,
                service_engagement=whiteboard.service_engagement,
                operation=evaluation.operation,
                company_signal=signal,
                reason=str(rule.get("reason") or f"Route optimization for condition: {condition or 'policy_match'}."),
                status=str(rule.get("status") or "queued"),
                priority=str(rule.get("priority") or "normal"),
                idempotency_key=_performance_key(
                    whiteboard=whiteboard,
                    policy=policy,
                    suffix=f"route:{evaluation.id}:{condition}:{department_slug}",
                ),
                metadata={
                    "whiteboard_id": str(whiteboard.id),
                    "policy_id": policy.get("policy_id"),
                    "source_policy_id": policy.get("source_policy_id"),
                    "pack_id": policy.get("pack_id"),
                    "evaluation_id": str(evaluation.id),
                    "condition": condition,
                },
            )
        )
    return records


def _performance_contract(
    *,
    whiteboard: WorkWhiteboard,
    policy: dict[str, Any],
    user: User | None,
    include_internal: bool,
) -> dict[str, Any]:
    manage = _can_manage_performance(user=user, whiteboard=whiteboard)
    state = _performance_state(whiteboard)
    state_sources = {
        str(item.get("id") or ""): item
        for item in list(state.get("sources") or [])
        if isinstance(item, dict)
    }
    sources = []
    for source in _metric_sources(policy):
        source_id = str(source["id"])
        previous = state_sources.get(source_id, {})
        sources.append(
            _source_payload(
                source=source,
                status=str(previous.get("status") or "not_started"),
                blocked_reason=str(previous.get("blocked_reason") or ""),
                blocked_reason_code=str(previous.get("blocked_reason_code") or ""),
                operation_id=str(previous.get("operation_id") or ""),
                tool_execution_id=str(previous.get("tool_execution_id") or ""),
                company_signal_id=str(previous.get("company_signal_id") or ""),
                routing_record_id=str(previous.get("routing_record_id") or ""),
                metrics=previous.get("metrics") if isinstance(previous.get("metrics"), dict) else {},
                receipt=previous.get("receipt") if isinstance(previous.get("receipt"), dict) else None,
                include_internal=include_internal,
            )
        )
    contract = {
        "whiteboard_id": str(whiteboard.id),
        "policy_id": str(policy["policy_id"]),
        "source_policy_id": str(policy.get("source_policy_id") or ""),
        "pack_id": str(policy.get("pack_id") or ""),
        "status": str(state.get("status") or _overall_status(sources)),
        "cadence": str(policy.get("cadence") or ""),
        "sources": sources,
        "current_state": _current_state_payload(state=state, include_internal=include_internal),
        "allowed_actions": _allowed_actions(whiteboard=whiteboard, state=state, policy=policy) if manage else [],
    }
    if include_internal:
        contract["evaluation_criteria"] = list(policy.get("evaluation_criteria") or [])
        contract["routing_rules"] = list(policy.get("routing_rules") or [])
    return sanitize_outbox_payload(contract)


def _normalize_policy(policy: dict[str, Any], *, source_policy_id: str, pack_id: str) -> dict[str, Any]:
    policy_id = str(policy.get("policy_id") or policy.get("id") or "").strip()
    if not policy_id:
        raise PerformanceOrchestrationError("performance_policy_id_required", "Performance policy requires an id.")
    sources = [_normalize_source(item) for item in list(policy.get("metric_sources") or []) if isinstance(item, dict)]
    if not sources:
        raise PerformanceOrchestrationError(
            "performance_metric_sources_required",
            "Performance policy must include at least one metric source.",
        )
    return {
        "policy_id": policy_id[:160],
        "source_policy_id": str(policy.get("source_policy_id") or source_policy_id or policy_id)[:200],
        "pack_id": str(policy.get("pack_id") or pack_id or "")[:160],
        "required_whiteboard_status": policy.get("required_whiteboard_status") or "",
        "cadence": str(policy.get("cadence") or policy.get("review_cadence") or "weekly")[:32],
        "metric_sources": sources,
        "evaluation_criteria": [_normalize_criterion(item) for item in list(policy.get("evaluation_criteria") or []) if isinstance(item, dict)],
        "routing_rules": [sanitize_outbox_payload(item) for item in list(policy.get("routing_rules") or []) if isinstance(item, dict)],
        "on_complete": sanitize_outbox_payload(policy.get("on_complete") or {}),
        "on_blocked": sanitize_outbox_payload(policy.get("on_blocked") or {}),
        "metadata": sanitize_outbox_payload(policy.get("metadata") or {}),
    }


def _normalize_source(item: dict[str, Any]) -> dict[str, Any]:
    source_id = str(item.get("id") or "").strip()
    if not source_id:
        raise PerformanceOrchestrationError("performance_source_id_required", "Metric source requires an id.")
    return {
        "id": source_id[:120],
        "display_name": str(item.get("display_name") or item.get("name") or _label(source_id))[:160],
        "department": str(item.get("department") or item.get("department_slug") or "analytics")[:160],
        "department_name": str(item.get("department_name") or _label(str(item.get("department") or "analytics")))[:255],
        "department_type": str(item.get("department_type") or item.get("department") or "analytics")[:64],
        "required_connector": str(item.get("required_connector") or "")[:160],
        "tool_id": str(item.get("tool_id") or "")[:160],
        "metrics": [str(value)[:160] for value in list(item.get("metrics") or [])],
        "required": bool(item.get("required", True)),
        "priority": str(item.get("priority") or "normal")[:16],
        "sample_metrics": sanitize_outbox_payload(item.get("sample_metrics") or item.get("metric_values") or {}),
        "metadata": sanitize_outbox_payload(item.get("metadata") or {}),
    }


def _normalize_criterion(item: dict[str, Any]) -> dict[str, Any]:
    key = str(item.get("key") or "").strip()
    operator = str(item.get("operator") or "==").strip()
    if not key or operator not in SUPPORTED_OPERATORS:
        return {}
    return {
        "key": key[:160],
        "label": str(item.get("label") or _label(key))[:160],
        "value_type": str(item.get("value_type") or "number")[:24],
        "operator": operator,
        "threshold": item.get("threshold"),
        "expected": item.get("expected"),
        "required": bool(item.get("required", True)),
        "hard_fail": bool(item.get("hard_fail", False)),
    }


def _policy_candidates(whiteboard: WorkWhiteboard) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    program = _program_for_whiteboard(whiteboard)
    if program is not None and program.installation_id:
        candidates.extend(_policies_from_installation(program.installation))
    installations = CompanyOperatingModelInstallation.objects.filter(
        organization=whiteboard.organization,
        company=whiteboard.company,
        status="active",
    ).select_related("pack_release")
    for installation in installations:
        candidates.extend(_policies_from_installation(installation))
    return candidates


def _program_for_whiteboard(whiteboard: WorkWhiteboard) -> CompanyProgram | None:
    metadata = whiteboard.metadata_json if isinstance(whiteboard.metadata_json, dict) else {}
    candidates = [metadata.get("company_program_id"), metadata.get("program_id")]
    if whiteboard.service_engagement is not None:
        svc_metadata = (
            whiteboard.service_engagement.metadata_json
            if isinstance(whiteboard.service_engagement.metadata_json, dict)
            else {}
        )
        candidates.extend([svc_metadata.get("company_program_id"), svc_metadata.get("program_id")])
    for program_id in candidates:
        if not program_id:
            continue
        program = CompanyProgram.objects.filter(
            organization=whiteboard.organization,
            company=whiteboard.company,
            id=program_id,
        ).select_related("installation", "installation__pack_release").first()
        if program is not None:
            return program
    return None


def _policies_from_installation(installation: CompanyOperatingModelInstallation | None) -> list[dict[str, Any]]:
    if installation is None:
        return []
    sources = [
        installation.public_config_json or {},
        installation.config_json or {},
        installation.pack_release.manifest_json if installation.pack_release_id else {},
        installation.pack_release.files_json if installation.pack_release_id else {},
    ]
    policies: list[dict[str, Any]] = []
    for source in sources:
        policies.extend(_extract_policies(source, pack_id=installation.pack_id))
    return policies


def _extract_policies(source: Any, *, pack_id: str) -> list[dict[str, Any]]:
    if not isinstance(source, dict):
        return []
    raw = None
    for key in PERFORMANCE_CONFIG_KEYS:
        raw = source.get(key)
        if raw is not None:
            break
    if isinstance(raw, dict):
        raw = list(raw.values())
    if not isinstance(raw, list):
        return []
    policies: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        policy_id = str(item.get("policy_id") or item.get("id") or "")
        policies.append(
            {
                **item,
                "pack_id": str(item.get("pack_id") or pack_id),
                "source_policy_id": str(item.get("source_policy_id") or f"{pack_id}:{policy_id}"),
            }
        )
    return policies


def _ensure_review_start_allowed(*, whiteboard: WorkWhiteboard, policy: dict[str, Any]) -> None:
    required_status = policy.get("required_whiteboard_status")
    if not required_status:
        return
    statuses = set(required_status if isinstance(required_status, list) else [required_status])
    if whiteboard.status in statuses:
        return
    deployment_status = _deployment_status(whiteboard)
    if deployment_status in DEPLOYMENT_READY_STATUSES:
        return
    raise PerformanceOrchestrationError(
        "whiteboard_status_mismatch",
        "Whiteboard status or deployment evidence does not satisfy this performance policy.",
        details=[{"required_status": list(statuses), "deployment_status": deployment_status}],
    )


def _deployment_status(whiteboard: WorkWhiteboard) -> str:
    projection = StateProjection.objects.filter(
        organization=whiteboard.organization,
        company=whiteboard.company,
        program=None,
        projection_type=f"whiteboard_deployment:{whiteboard.id}",
    ).first()
    if projection is None or not isinstance(projection.json_state, dict):
        return ""
    return str(projection.json_state.get("status") or "")


def _readiness_for_source(*, whiteboard: WorkWhiteboard, source: dict[str, Any]) -> dict[str, Any]:
    connector = str(source.get("required_connector") or "").strip()
    if connector and connector not in _available_connectors(whiteboard):
        return {
            "status": "blocked",
            "reason_code": "missing_metric_connector",
            "reason": "Required metric connector is not available for this company.",
        }
    tool_id = str(source.get("tool_id") or "").strip()
    if tool_id and not _tool_available(company=whiteboard.company, tool_id=tool_id):
        return {
            "status": "blocked",
            "reason_code": "metric_tool_missing",
            "reason": "Required metric collection tool is not declared by an active installed pack.",
        }
    return {"status": "ready", "reason_code": "", "reason": ""}


def _available_connectors(whiteboard: WorkWhiteboard) -> set[str]:
    values: set[str] = set()
    for installation in CompanyOperatingModelInstallation.objects.filter(
        organization=whiteboard.organization,
        company=whiteboard.company,
        status="active",
    ).select_related("pack_release"):
        sources = [
            installation.public_config_json or {},
            installation.config_json or {},
            installation.pack_release.manifest_json if installation.pack_release_id else {},
            installation.pack_release.files_json if installation.pack_release_id else {},
        ]
        for source in sources:
            values.update(_connector_values(source))
    return values


def _connector_values(source: Any) -> set[str]:
    if not isinstance(source, dict):
        return set()
    raw = source.get("available_connectors") or source.get("connector_inventory") or {}
    if isinstance(raw, dict):
        return _connector_values_from_dict(raw)
    if isinstance(raw, list):
        return _connector_values_from_list(raw)
    return set()


def _connector_values_from_dict(raw: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    for key, item in raw.items():
        if item is False:
            continue
        if isinstance(item, dict) and not _connector_status_available(item):
            continue
        values.add(str(key))
    return values


def _connector_values_from_list(raw: list[Any]) -> set[str]:
    values: set[str] = set()
    for item in raw:
        if isinstance(item, str):
            values.add(item)
            continue
        if not isinstance(item, dict):
            continue
        connector_id = str(item.get("id") or item.get("connector") or "").strip()
        if connector_id and bool(item.get("active", True)) and _connector_status_available(item):
            values.add(connector_id)
    return values


def _connector_status_available(item: dict[str, Any]) -> bool:
    return str(item.get("status") or "available").lower() in {
        "available",
        "active",
        "configured",
        "ready",
        "true",
    }


def _tool_available(*, company: Graph, tool_id: str) -> bool:
    if not tool_id:
        return False
    for installation in CompanyOperatingModelInstallation.objects.filter(company=company, status="active"):
        try:
            definition = load_pack_definition(installation.pack_id)
        except OperatingModelPackError:
            continue
        tools_file = definition.files.get("tools") if isinstance(definition.files, dict) else {}
        for key in ("tool_packages", "department_tools"):
            values = tools_file.get(key) if isinstance(tools_file, dict) else []
            if not isinstance(values, list):
                continue
            for tool in values:
                if isinstance(tool, dict) and str(tool.get("id") or "") == tool_id:
                    return True
    return False


def _mark_source_blocked(
    *,
    user: User,
    whiteboard: WorkWhiteboard,
    policy: dict[str, Any],
    source: dict[str, Any],
    reason_code: str,
    reason: str,
    operation: Run | None = None,
) -> dict[str, Any]:
    source_id = str(source["id"])
    signal = create_company_signal(
        company=whiteboard.company,
        actor=user,
        signal_type="manual",
        source="performance_orchestration",
        external_key=_performance_key(
            whiteboard=whiteboard,
            policy=policy,
            suffix=f"signal:{source_id}:{reason_code}",
        ),
        title=f"{source['display_name']} performance source blocked",
        summary=reason,
        channel=source_id[:64],
        metadata={
            "whiteboard_id": str(whiteboard.id),
            "policy_id": policy.get("policy_id"),
            "source_policy_id": policy.get("source_policy_id"),
            "pack_id": policy.get("pack_id"),
            "source_id": source_id,
            "reason_code": reason_code,
            "condition": reason_code,
        },
    )
    department = _blocked_department(whiteboard=whiteboard, policy=policy, source=source)
    record = route_event_to_department(
        company=whiteboard.company,
        department=department,
        user=user,
        event_type="whiteboard.performance.blocked",
        trigger_type="whiteboard.performance.blocked",
        communication_thread=whiteboard.communication_thread,
        communication_message=whiteboard.source_message,
        service_engagement=whiteboard.service_engagement,
        operation=operation,
        company_signal=signal,
        reason=reason,
        status="blocked",
        priority=str(source.get("priority") or "normal"),
        idempotency_key=_performance_key(
            whiteboard=whiteboard,
            policy=policy,
            suffix=f"route:{source_id}:{reason_code}",
        ),
        metadata={
            "whiteboard_id": str(whiteboard.id),
            "policy_id": policy.get("policy_id"),
            "source_policy_id": policy.get("source_policy_id"),
            "pack_id": policy.get("pack_id"),
            "source_id": source_id,
            "blocked_reason_code": reason_code,
            "condition": reason_code,
        },
    )
    return _source_payload(
        source=source,
        status="blocked",
        blocked_reason=reason,
        blocked_reason_code=reason_code,
        operation_id=str(operation.id) if operation is not None else "",
        company_signal_id=str(signal.id),
        routing_record_id=str(record.id),
        include_internal=True,
    )


def _blocked_department(
    *,
    whiteboard: WorkWhiteboard,
    policy: dict[str, Any],
    source: dict[str, Any],
) -> DepartmentRegistry:
    blocked = policy.get("on_blocked") if isinstance(policy.get("on_blocked"), dict) else {}
    slug = str(blocked.get("route_to_department") or blocked.get("route_to") or source.get("department") or "analytics")
    name = str(source.get("department_name") or _label(slug))
    return register_department(
        organization=whiteboard.organization,
        slug=slug,
        name=name,
        department_type=str(source.get("department_type") or slug),
        service_tags=["performance"],
        metadata={"system_managed": True, "source": "performance_orchestration"},
    )


def _optimization_signal(
    *,
    user: User,
    whiteboard: WorkWhiteboard,
    policy: dict[str, Any],
    evaluation: EvaluationRun,
    rule: dict[str, Any],
    condition: str,
) -> Any:
    return create_company_signal(
        company=whiteboard.company,
        actor=user,
        signal_type="manual",
        source="performance_orchestration",
        external_key=_performance_key(
            whiteboard=whiteboard,
            policy=policy,
            suffix=f"optimization-signal:{evaluation.id}:{condition}",
        ),
        title=str(rule.get("signal_title") or "Performance optimization signal")[:255],
        summary=str(rule.get("signal_summary") or f"Performance condition matched: {condition}")[:2000],
        metadata={
            "whiteboard_id": str(whiteboard.id),
            "policy_id": policy.get("policy_id"),
            "evaluation_id": str(evaluation.id),
            "condition": condition,
        },
    )


def _performance_graph_version(*, company: Graph, policy_id: str) -> GraphVersion:
    key = f"performance:{policy_id}"[:255]
    existing = GraphVersion.objects.filter(graph=company, external_idempotency_key=key).first()
    if existing is not None:
        return existing
    version = (GraphVersion.objects.filter(graph=company).aggregate(max_version=Max("version"))["max_version"] or 0) + 1
    try:
        return GraphVersion.objects.create(
            graph=company,
            version=version,
            external_idempotency_key=key,
            graph_json={"nodes": [], "edges": [], "source": "performance_orchestration", "policy_id": policy_id},
        )
    except IntegrityError:
        existing = GraphVersion.objects.filter(graph=company, external_idempotency_key=key).first()
        if existing is not None:
            return existing
        raise


def _performance_run(
    *,
    user: User,
    whiteboard: WorkWhiteboard,
    policy: dict[str, Any],
    source: dict[str, Any],
) -> Run:
    policy_id = str(policy["policy_id"])
    source_id = str(source["id"])
    graph_version = _performance_graph_version(company=whiteboard.company, policy_id=policy_id)
    key = _performance_key(whiteboard=whiteboard, policy=policy, suffix=f"run:{source_id}")
    run = Run.objects.filter(
        organization=whiteboard.organization,
        graph_version__graph=whiteboard.company,
        input_json__idempotency_key=key,
    ).first()
    if run is not None:
        return run
    return Run.objects.create(
        owner=user,
        organization=whiteboard.organization,
        thread_id=whiteboard.communication_thread_id,
        graph_version=graph_version,
        status="succeeded",
        started_at=timezone.now(),
        ended_at=timezone.now(),
        input_json={
            "idempotency_key": key,
            "whiteboard_id": str(whiteboard.id),
            "policy_id": policy_id,
            "source_policy_id": policy.get("source_policy_id"),
            "pack_id": policy.get("pack_id"),
            "metric_source_id": source_id,
        },
        output_json={"whiteboard_id": str(whiteboard.id), "policy_id": policy_id, "metric_source_id": source_id},
        dispatch_graph_json=graph_version.graph_json,
    )


def _evaluation_run(*, user: User, whiteboard: WorkWhiteboard, policy: dict[str, Any]) -> Run:
    source = {
        "id": "evaluation",
        "display_name": "Performance Evaluation",
        "department": "analytics",
        "department_name": "Analytics",
        "department_type": "analytics",
        "tool_id": "",
    }
    return _performance_run(user=user, whiteboard=whiteboard, policy=policy, source=source)


def _tool_inputs(
    *,
    whiteboard: WorkWhiteboard,
    policy: dict[str, Any],
    source: dict[str, Any],
    period_start: str,
    period_end: str,
) -> dict[str, Any]:
    return sanitize_outbox_payload(
        {
            "whiteboard_id": str(whiteboard.id),
            "policy_id": policy.get("policy_id"),
            "metric_source_id": source.get("id"),
            "period_start": period_start,
            "period_end": period_end,
            "metrics": list(source.get("metrics") or []),
            "sample_metrics": source.get("sample_metrics") or {},
        }
    )


def _assemble_performance_report(
    *,
    user: User,
    whiteboard: WorkWhiteboard,
    policy: dict[str, Any],
    snapshot: MetricSnapshot,
    state: dict[str, Any],
) -> ReportRun:
    template_id = str(policy.get("report_template_id") or policy["policy_id"])[:160]
    existing = ReportRun.objects.filter(
        company=whiteboard.company,
        metric_snapshot=snapshot,
        report_template_id=template_id,
    ).first()
    if existing is not None:
        return existing
    sections = sanitize_outbox_payload(
        {
            "schema_version": PERFORMANCE_SCHEMA_VERSION,
            "whiteboard_id": str(whiteboard.id),
            "policy_id": policy["policy_id"],
            "summary": {
                "status": state.get("status"),
                "source_count": len(list(state.get("sources") or [])),
                "blocked_source_count": len([item for item in list(state.get("sources") or []) if item.get("status") == "blocked"]),
            },
            "metric_snapshot": {
                "id": str(snapshot.id),
                "period_start": snapshot.period_start.isoformat(),
                "period_end": snapshot.period_end.isoformat(),
            },
            "sources": list(state.get("sources") or []),
        }
    )
    return ReportRun.objects.create(
        organization=whiteboard.organization,
        company=whiteboard.company,
        program=snapshot.program,
        metric_snapshot=snapshot,
        report_template_id=template_id,
        period_start=snapshot.period_start,
        period_end=snapshot.period_end,
        generated_sections_json=sections,
        source_refs_json=[
            {"type": "whiteboard", "id": str(whiteboard.id)},
            {"type": "metric_snapshot", "id": str(snapshot.id)},
        ],
        created_by=user,
    )


def _metric_snapshot_from_state(*, whiteboard: WorkWhiteboard, state: dict[str, Any]) -> MetricSnapshot | None:
    snapshot_id = str(state.get("metric_snapshot_id") or "")
    if not snapshot_id:
        return None
    return MetricSnapshot.objects.filter(
        organization=whiteboard.organization,
        company=whiteboard.company,
        id=snapshot_id,
    ).first()


def _source_payload(
    *,
    source: dict[str, Any],
    status: str,
    blocked_reason: str = "",
    blocked_reason_code: str = "",
    operation_id: str = "",
    tool_execution_id: str = "",
    company_signal_id: str = "",
    routing_record_id: str = "",
    metrics: dict[str, Any] | None = None,
    receipt: dict[str, Any] | None = None,
    include_internal: bool = True,
) -> dict[str, Any]:
    item = {
        "id": str(source["id"]),
        "display_name": str(source.get("display_name") or _label(str(source["id"]))),
        "status": status,
        "blocked_reason": blocked_reason,
        "blocked_reason_code": blocked_reason_code,
        "tool_execution_id": tool_execution_id,
        "company_signal_id": company_signal_id,
        "routing_record_id": routing_record_id,
        "metrics": sanitize_outbox_payload(metrics or {}),
    }
    if operation_id:
        item["operation_id"] = operation_id
    if receipt:
        item["receipt"] = _receipt_payload(receipt)
    if include_internal:
        item.update(
            {
                "department": str(source.get("department") or ""),
                "department_name": str(source.get("department_name") or ""),
                "required_connector": str(source.get("required_connector") or ""),
                "tool_id": str(source.get("tool_id") or ""),
                "metric_keys": list(source.get("metrics") or []),
                "metadata": sanitize_outbox_payload(source.get("metadata") or {}),
            }
        )
    return sanitize_outbox_payload(item)


def _receipt_payload(receipt: dict[str, Any]) -> dict[str, Any]:
    result = receipt.get("result") if isinstance(receipt.get("result"), dict) else {}
    return sanitize_outbox_payload(
        {
            "tool_execution_id": receipt.get("tool_execution_id"),
            "tool_id": receipt.get("tool_id"),
            "dry_run": receipt.get("dry_run"),
            "status": receipt.get("status"),
            "completed_at": receipt.get("completed_at"),
            "result": {
                "provider": result.get("provider"),
                "mode": result.get("mode"),
                "status": result.get("status"),
            },
        }
    )


def _review_period(
    *,
    policy: dict[str, Any],
    period_start: date | None,
    period_end: date | None,
) -> dict[str, str]:
    if (period_start is None) != (period_end is None):
        raise PerformanceOrchestrationError(
            "invalid_period",
            "Both period_start and period_end are required together.",
        )
    if period_start is not None and period_end is not None:
        if period_end < period_start:
            raise PerformanceOrchestrationError("invalid_period", "Period end cannot precede start.")
        return {"period_start": period_start.isoformat(), "period_end": period_end.isoformat()}
    today = timezone.localdate()
    cadence = str(policy.get("cadence") or "weekly")
    if cadence == "monthly":
        current_start = date(today.year, today.month, 1)
        previous_end = current_start - timedelta(days=1)
        previous_start = date(previous_end.year, previous_end.month, 1)
        return {"period_start": previous_start.isoformat(), "period_end": previous_end.isoformat()}
    start = today - timedelta(days=7)
    end = today - timedelta(days=1)
    return {"period_start": start.isoformat(), "period_end": end.isoformat()}


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _source_metric_values(source: dict[str, Any]) -> dict[str, Any]:
    values = source.get("sample_metrics") if isinstance(source.get("sample_metrics"), dict) else {}
    allowed = {str(item) for item in list(source.get("metrics") or [])}
    if not allowed:
        return sanitize_outbox_payload(values)
    return sanitize_outbox_payload({key: value for key, value in values.items() if key in allowed})


def _collected_metric_values(sources: list[dict[str, Any]]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for source in sources:
        if str(source.get("status") or "") != "collected":
            continue
        for key, value in dict(source.get("metrics") or {}).items():
            values[str(key)] = value
    return sanitize_outbox_payload(values)


def _source_refs(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_source_ref(item) for item in sources]


def _source_ref(source: dict[str, Any]) -> dict[str, Any]:
    return sanitize_outbox_payload(
        {
            "id": source.get("id"),
            "status": source.get("status"),
            "tool_execution_id": source.get("tool_execution_id"),
            "company_signal_id": source.get("company_signal_id"),
            "routing_record_id": source.get("routing_record_id"),
            "blocked_reason_code": source.get("blocked_reason_code"),
        }
    )


def _ids_from_sources(sources: list[dict[str, Any]], field: str) -> list[str]:
    return sorted({str(item.get(field) or "") for item in sources if item.get(field)})


def _evaluation_inputs(
    *,
    snapshot: MetricSnapshot,
    state: dict[str, Any],
    scorecard: dict[str, Any],
) -> dict[str, Any]:
    values = dict(snapshot.metric_values_json or {})
    values.update(sanitize_outbox_payload(scorecard))
    conditions = set(values.get("conditions") or [])
    for item in list(state.get("sources") or []):
        if str(item.get("status") or "") == "blocked":
            conditions.add(str(item.get("blocked_reason_code") or "blocked"))
    values["conditions"] = sorted(condition for condition in conditions if condition)
    return sanitize_outbox_payload(values)


def _criterion_result(criterion: dict[str, Any], submitted: dict[str, Any]) -> dict[str, Any]:
    key = str(criterion.get("key") or "")
    value_present = key in submitted
    value = submitted.get(key)
    expected = criterion.get("expected")
    threshold = criterion.get("threshold")
    comparator = expected if expected is not None else threshold
    passed = False
    if value_present:
        passed = _compare_values(
            value=value,
            comparator=comparator,
            operator=str(criterion.get("operator") or "=="),
            value_type=str(criterion.get("value_type") or "number"),
        )
    elif not bool(criterion.get("required", True)):
        passed = True
    return {
        "key": key,
        "label": criterion.get("label") or _label(key),
        "operator": criterion.get("operator"),
        "value_type": criterion.get("value_type"),
        "expected": comparator,
        "actual": sanitize_outbox_payload(value),
        "required": bool(criterion.get("required", True)),
        "hard_fail": bool(criterion.get("hard_fail", False)),
        "passed": passed,
        "missing": not value_present,
    }


def _compare_values(*, value: Any, comparator: Any, operator: str, value_type: str) -> bool:
    if operator == "in":
        return value in (comparator if isinstance(comparator, list) else [comparator])
    resolved = _comparison_pair(value=value, comparator=comparator, value_type=value_type)
    if resolved is None:
        return False
    actual, expected = resolved
    return _apply_operator(actual=actual, expected=expected, operator=operator)


def _comparison_pair(*, value: Any, comparator: Any, value_type: str) -> tuple[Any, Any] | None:
    if value_type == "number":
        try:
            return float(value), float(comparator)
        except (TypeError, ValueError):
            return None
    if value_type == "boolean":
        return _bool_value(value), _bool_value(comparator)
    if value_type == "enum":
        return str(value).lower(), str(comparator).lower()
    return str(value), str(comparator)


def _apply_operator(*, actual: Any, expected: Any, operator: str) -> bool:
    if operator == ">=":
        return bool(actual >= expected)
    if operator == ">":
        return bool(actual > expected)
    if operator == "<=":
        return bool(actual <= expected)
    if operator == "<":
        return bool(actual < expected)
    if operator == "==":
        return bool(actual == expected)
    if operator == "!=":
        return bool(actual != expected)
    return False


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "pass", "passed"}


def _evaluation_result(criteria_results: list[dict[str, Any]]) -> str:
    failed = [item for item in criteria_results if not bool(item.get("passed"))]
    if not failed:
        return "pass"
    if any(bool(item.get("hard_fail")) for item in failed):
        return "fail"
    return "revision_required"


def _composite_score(criteria_results: list[dict[str, Any]]) -> float:
    if not criteria_results:
        return 0.0
    passed = sum(1 for item in criteria_results if bool(item.get("passed")))
    return round((passed / len(criteria_results)) * 100, 2)


def _matched_conditions(
    *,
    state: dict[str, Any],
    criteria_results: list[dict[str, Any]],
    submitted: dict[str, Any],
) -> list[str]:
    conditions = {str(item) for item in list(submitted.get("conditions") or []) if item}
    for item in list(state.get("sources") or []):
        if str(item.get("status") or "") == "blocked":
            conditions.add(str(item.get("blocked_reason_code") or "blocked"))
    for criterion in criteria_results:
        if not bool(criterion.get("passed")):
            conditions.add(str(criterion.get("key") or "criterion_failed"))
    return sorted(conditions)


def _metric_sources(policy: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in list(policy.get("metric_sources") or []) if isinstance(item, dict)]


def _evaluation_criteria(policy: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in list(policy.get("evaluation_criteria") or []) if isinstance(item, dict) and item.get("key")]


def _routing_rules(policy: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in list(policy.get("routing_rules") or []) if isinstance(item, dict)]


def _upsert_performance_projection(
    *,
    whiteboard: WorkWhiteboard,
    policy: dict[str, Any],
    state: dict[str, Any],
) -> StateProjection:
    existing = _performance_projection(whiteboard)
    merged = {
        **((existing.json_state if existing is not None and isinstance(existing.json_state, dict) else {}) or {}),
        **sanitize_outbox_payload(state),
        "schema_version": PERFORMANCE_SCHEMA_VERSION,
        "whiteboard_id": str(whiteboard.id),
        "policy_id": str(policy["policy_id"]),
        "policy": _policy_snapshot(policy),
        "updated_at": timezone.now().isoformat(),
    }
    projection, _created = StateProjection.objects.update_or_create(
        organization=whiteboard.organization,
        company=whiteboard.company,
        program=None,
        projection_type=_performance_projection_type(whiteboard),
        defaults={
            "display_label": "Whiteboard performance",
            "source_refs_json": [{"whiteboard_id": str(whiteboard.id), "policy_id": str(policy["policy_id"])}],
            "json_state": merged,
            "markdown_summary": "Whiteboard performance state from configured policy.",
            "generated_by": "system",
        },
    )
    return projection


def _performance_projection(whiteboard: WorkWhiteboard) -> StateProjection | None:
    return StateProjection.objects.filter(
        organization=whiteboard.organization,
        company=whiteboard.company,
        program=None,
        projection_type=_performance_projection_type(whiteboard),
    ).first()


def _performance_state(whiteboard: WorkWhiteboard) -> dict[str, Any]:
    projection = _performance_projection(whiteboard)
    if projection is None or not isinstance(projection.json_state, dict):
        return {}
    return dict(projection.json_state)


def _performance_projection_type(whiteboard: WorkWhiteboard) -> str:
    return f"{PERFORMANCE_PROJECTION_PREFIX}:{whiteboard.id}"


def _policy_snapshot(policy: dict[str, Any]) -> dict[str, Any]:
    return sanitize_outbox_payload(
        {
            "policy_id": policy.get("policy_id"),
            "source_policy_id": policy.get("source_policy_id"),
            "pack_id": policy.get("pack_id"),
            "required_whiteboard_status": policy.get("required_whiteboard_status"),
            "cadence": policy.get("cadence"),
            "metric_sources": list(policy.get("metric_sources") or []),
            "evaluation_criteria": list(policy.get("evaluation_criteria") or []),
            "routing_rules": list(policy.get("routing_rules") or []),
        }
    )


def _current_state_payload(*, state: dict[str, Any], include_internal: bool) -> dict[str, Any]:
    payload = {
        "status": str(state.get("status") or "not_started"),
        "metric_snapshot_id": str(state.get("metric_snapshot_id") or ""),
        "report_run_id": str(state.get("report_run_id") or ""),
        "evaluation_id": str(state.get("evaluation_id") or ""),
        "period_start": str(state.get("period_start") or ""),
        "period_end": str(state.get("period_end") or ""),
        "updated_at": state.get("updated_at"),
    }
    if include_internal:
        payload.update(
            {
                "schema_version": state.get("schema_version"),
                "tool_execution_ids": list(state.get("tool_execution_ids") or []),
                "company_signal_ids": list(state.get("company_signal_ids") or []),
                "routing_record_ids": list(state.get("routing_record_ids") or []),
            }
        )
    return sanitize_outbox_payload(payload)


def _allowed_actions(*, whiteboard: WorkWhiteboard, state: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    if not state.get("sources"):
        actions.append("start")
    if state.get("metric_snapshot_id") and not state.get("report_run_id"):
        actions.append("report")
    if state.get("metric_snapshot_id") and not state.get("evaluation_id"):
        actions.append("evaluate")
    if not actions and _deployment_status(whiteboard) in DEPLOYMENT_READY_STATUSES:
        actions.append("start")
    if not actions and not policy.get("required_whiteboard_status"):
        actions.append("start")
    return sorted(set(actions))


def _overall_status(sources: list[dict[str, Any]]) -> str:
    if not sources:
        return "not_started"
    statuses = {str(item.get("status") or "") for item in sources}
    if statuses == {"not_started"}:
        return "not_started"
    if "blocked" in statuses and len(statuses) == 1:
        return "blocked"
    if "blocked" in statuses:
        return "partial"
    if statuses <= {"collected"}:
        return "collected"
    return "partial"


def _ensure_can_manage_performance(*, user: User, whiteboard: WorkWhiteboard) -> None:
    if not _can_manage_performance(user=user, whiteboard=whiteboard):
        raise PerformanceOrchestrationError(
            "permission_denied",
            "Managing this whiteboard performance state requires company member access and organization member role.",
        )


def _can_manage_performance(*, user: User | None, whiteboard: WorkWhiteboard) -> bool:
    if user is None:
        return False
    return has_company_access(user, whiteboard.company, "member") and has_min_role(
        user,
        "member",
        str(whiteboard.organization_id),
    )


def _performance_key(*, whiteboard: WorkWhiteboard, policy: dict[str, Any], suffix: str) -> str:
    raw = f"whiteboard:{whiteboard.id}:performance:{policy['policy_id']}:{suffix}"
    if len(raw) <= 255:
        return raw
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
    return f"whiteboard:{whiteboard.id}:performance:{digest}"


def _grade(score: float) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def _result_json(evaluation: EvaluationRun) -> dict[str, Any]:
    return evaluation.result_json if isinstance(evaluation.result_json, dict) else {}


def _label(value: str) -> str:
    return str(value or "").replace("_", " ").replace("-", " ").title()


def _refresh_whiteboard_snapshot(whiteboard: WorkWhiteboard) -> None:
    from application.services.work_whiteboards import refresh_whiteboard_redis_snapshot

    refresh_whiteboard_redis_snapshot(whiteboard)
