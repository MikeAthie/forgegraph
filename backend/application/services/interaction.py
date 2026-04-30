"""Backend-owned interaction layer services."""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from django.db import transaction
from django.utils import timezone

from domain.entities.interaction import (
    AssumptionItem,
    AutonomyMode,
    ClarificationItem,
    InteractionActor,
    InteractionEvent,
    InteractionEventType,
    OperatingBrief,
    PriorityFrame,
    ProjectManagerAction,
)
from infrastructure.orm.models import (
    Graph,
    GraphVersion,
    InteractionEventRecord,
    OperatingBriefRecord,
    Run,
    User,
)

SCALAR_FIELDS = {"objective", "deliverable", "autonomy_mode"}
LIST_FIELDS = {
    "constraints",
    "success_criteria",
    "stakeholders",
    "dependencies",
    "assumptions",
    "clarifications",
}
PRIORITY_FIELDS = {"speed", "cost", "quality", "risk"}
PLAN_REVISION_FIELDS = {
    "objective",
    "deliverable",
    "constraints",
    "success_criteria",
    "stakeholders",
    "dependencies",
    "priority_frame",
    "autonomy_mode",
}
ACTIVE_OPERATION_STATUSES = {"pending", "running", "paused", "resume_requested"}


@dataclass(slots=True)
class InteractionInterpretation:
    event_type: InteractionEventType
    delta: dict[str, Any]
    affected_fields: list[str]
    confidence: float
    rationale: str


@dataclass(slots=True)
class ProjectManagerDecision:
    action: ProjectManagerAction
    rationale: str


@dataclass(slots=True)
class InteractionResult:
    brief_record: OperatingBriefRecord
    event_record: InteractionEventRecord
    brief: OperatingBrief
    interpretation: InteractionInterpretation
    decision: ProjectManagerDecision
    plan_implications: dict[str, Any]


class ProjectManager:
    """Deterministic project manager for mutating and stabilizing operating intent."""

    def interpret(
        self,
        *,
        brief: OperatingBrief,
        user_input: str,
        now: datetime,
    ) -> InteractionInterpretation:
        text = _normalize_text(user_input)
        event_type = _classify_input(brief=brief, text=text)
        delta: dict[str, Any] = {"set": {}, "append": {}, "remove": {}, "priority_frame": {}}
        affected_fields: list[str] = []

        if event_type == InteractionEventType.CONSTRAINT:
            _append_delta(delta, "constraints", [_constraint_from_text(text)])
        elif event_type == InteractionEventType.PRIORITY_SHIFT:
            delta["priority_frame"] = _priority_delta_from_text(text)
        elif event_type == InteractionEventType.APPROVE:
            _append_delta(
                delta,
                "assumptions",
                [
                    _assumption_payload(
                        "approval",
                        "User approved the current operating brief.",
                        0.95,
                        now,
                    )
                ],
            )
        elif event_type == InteractionEventType.OVERRIDE:
            _append_delta(delta, "constraints", [_override_from_text(text)])
        else:
            self._interpret_general_mutation(
                brief=brief,
                text=text,
                now=now,
                event_type=event_type,
                delta=delta,
            )

        self._add_stabilizing_assumptions(brief=brief, delta=delta, now=now)
        affected_fields = _affected_fields(delta)
        if not affected_fields and text:
            _append_delta(
                delta,
                "assumptions",
                [_assumption_payload("context", text, 0.45, now)],
            )
            affected_fields = _affected_fields(delta)

        return InteractionInterpretation(
            event_type=event_type,
            delta=_compact_delta(delta),
            affected_fields=affected_fields,
            confidence=_interpretation_confidence(event_type, affected_fields),
            rationale=_interpretation_rationale(event_type, affected_fields),
        )

    def _interpret_general_mutation(
        self,
        *,
        brief: OperatingBrief,
        text: str,
        now: datetime,
        event_type: InteractionEventType,
        delta: dict[str, Any],
    ) -> None:
        if event_type == InteractionEventType.CLARIFY and not brief.objective:
            _append_delta(
                delta,
                "clarifications",
                [
                    {
                        "question": "What outcome should the company pursue first?",
                        "blocking": True,
                        "related_field": "objective",
                    }
                ],
            )
            return

        stakeholder = _stakeholder_from_text(text)
        if stakeholder:
            _append_delta(delta, "stakeholders", [stakeholder])

        success_criterion = _success_criterion_from_text(text)
        if success_criterion:
            _append_delta(delta, "success_criteria", [success_criterion])

        dependency = _dependency_from_text(text)
        if dependency:
            _append_delta(delta, "dependencies", [dependency])

        autonomy_mode = _autonomy_mode_from_text(text)
        if autonomy_mode is not None:
            delta["set"]["autonomy_mode"] = autonomy_mode.value

        if event_type == InteractionEventType.CREATE or not brief.objective:
            delta["set"]["objective"] = _sentence_case(text)
            inferred_deliverable = _deliverable_from_objective(text)
            if inferred_deliverable:
                delta["set"]["deliverable"] = inferred_deliverable
                _append_delta(
                    delta,
                    "assumptions",
                    [
                        _assumption_payload(
                            "deliverable",
                            inferred_deliverable,
                            0.72,
                            now,
                        )
                    ],
                )
        elif (
            _looks_like_objective_rewrite(text)
            and not stakeholder
            and not success_criterion
            and not dependency
            and autonomy_mode is None
        ):
            delta["set"]["objective"] = _sentence_case(_strip_rewrite_prefix(text))

    def _add_stabilizing_assumptions(
        self,
        *,
        brief: OperatingBrief,
        delta: dict[str, Any],
        now: datetime,
    ) -> None:
        set_delta = _dict_value(delta, "set")
        append_delta = _dict_value(delta, "append")
        next_objective = str(set_delta.get("objective") or brief.objective or "").strip()
        next_deliverable = str(set_delta.get("deliverable") or brief.deliverable or "").strip()
        has_success_criteria = bool(
            brief.success_criteria or _list_value(append_delta.get("success_criteria"))
        )

        if next_objective and not next_deliverable:
            assumed = f"Concrete deliverable for: {next_objective}"
            delta["set"]["deliverable"] = assumed
            _append_delta(
                delta,
                "assumptions",
                [_assumption_payload("deliverable", assumed, 0.55, now)],
            )

        if next_objective and not has_success_criteria:
            _append_delta(
                delta,
                "assumptions",
                [
                    _assumption_payload(
                        "success_criteria",
                        "The output is useful, reviewable, and aligned with the stated objective.",
                        0.58,
                        now,
                    )
                ],
            )

    def apply_event(self, *, brief: OperatingBrief, event: InteractionEvent) -> OperatingBrief:
        return apply_event(brief, event)

    def decide_next_action(
        self,
        *,
        brief: OperatingBrief,
        event: InteractionEvent,
        affected_fields: list[str],
        raw_input: str,
    ) -> ProjectManagerDecision:
        blocking_clarifications = [
            item
            for item in brief.clarifications
            if item.blocking and item.related_field in affected_fields
        ]
        if not brief.objective:
            return ProjectManagerDecision(
                action=ProjectManagerAction.ASK_CLARIFICATION,
                rationale="The objective is still missing, so execution cannot be stabilized.",
            )
        if blocking_clarifications:
            return ProjectManagerDecision(
                action=ProjectManagerAction.ASK_CLARIFICATION,
                rationale="A blocking clarification affects the current mutation.",
            )
        if _is_stop_or_cancel(raw_input):
            return ProjectManagerDecision(
                action=ProjectManagerAction.BLOCK,
                rationale="The user asked to stop or block forward execution.",
            )
        if event.type == InteractionEventType.APPROVE and brief.objective and brief.deliverable:
            return ProjectManagerDecision(
                action=ProjectManagerAction.EXECUTE,
                rationale="The current brief has enough stable intent and the user approved it.",
            )
        if _requires_high_impact_clarification(raw_input, affected_fields):
            return ProjectManagerDecision(
                action=ProjectManagerAction.ASK_CLARIFICATION,
                rationale="The mutation affects feasibility, cost/risk, success criteria, or ownership.",
            )
        return ProjectManagerDecision(
            action=ProjectManagerAction.ASSUME_AND_CONTINUE,
            rationale="The mutation can be carried forward with recorded assumptions.",
        )


def apply_event(brief: OperatingBrief, event: InteractionEvent) -> OperatingBrief:
    """Apply a structured event to a brief without mutating the input object."""

    updated = copy.deepcopy(brief)
    delta = event.delta
    set_delta = _dict_value(delta, "set")
    append_delta = _dict_value(delta, "append")
    remove_delta = _dict_value(delta, "remove")
    priority_delta = _dict_value(delta, "priority_frame")

    for field_name, value in set_delta.items():
        if field_name == "objective":
            updated.objective = _nullable_string(value)
        elif field_name == "deliverable":
            updated.deliverable = _nullable_string(value)
        elif field_name == "autonomy_mode":
            updated.autonomy_mode = _autonomy_mode_value(value)

    for field_name, values in append_delta.items():
        if field_name in {"constraints", "success_criteria", "stakeholders", "dependencies"}:
            current = cast(list[str], getattr(updated, field_name))
            setattr(updated, field_name, _append_unique_strings(current, _string_list(values)))
        elif field_name == "assumptions":
            updated.assumptions = _append_unique_assumptions(
                updated.assumptions,
                [_assumption_from_payload(item, event.timestamp) for item in _dict_list(values)],
            )
        elif field_name == "clarifications":
            updated.clarifications = _append_unique_clarifications(
                updated.clarifications,
                [_clarification_from_payload(item) for item in _dict_list(values)],
            )

    for field_name, values in remove_delta.items():
        if field_name in {"constraints", "success_criteria", "stakeholders", "dependencies"}:
            current = cast(list[str], getattr(updated, field_name))
            setattr(updated, field_name, _remove_strings(current, _string_list(values)))

    if priority_delta:
        current_priority = updated.priority_frame
        updated.priority_frame = PriorityFrame(
            speed=float(priority_delta.get("speed", current_priority.speed)),
            cost=float(priority_delta.get("cost", current_priority.cost)),
            quality=float(priority_delta.get("quality", current_priority.quality)),
            risk=float(priority_delta.get("risk", current_priority.risk)),
        ).normalized()

    return updated


def get_current_brief_record(
    *,
    company: Graph,
    operation: Run | None = None,
) -> OperatingBriefRecord | None:
    return (
        OperatingBriefRecord.objects.select_related("company", "operation")
        .filter(
            organization=company.organization,
            company=company,
            operation=operation,
        )
        .first()
    )


def current_brief_payload(*, company: Graph, operation: Run | None = None) -> dict[str, Any]:
    record = get_current_brief_record(company=company, operation=operation)
    if record is not None:
        return brief_payload(brief_from_record(record), record=record)
    initial = initial_brief_for_scope(company=company, operation=operation)
    return brief_payload(initial, record=None, company=company, operation=operation)


@transaction.atomic
def process_user_interaction(
    *,
    user: User,
    company: Graph,
    operation: Run | None,
    user_input: str,
) -> InteractionResult:
    now = timezone.now()
    pm = ProjectManager()
    record = _get_or_create_locked_brief(
        user=user,
        company=company,
        operation=operation,
    )
    current_brief = brief_from_record(record)
    interpretation = pm.interpret(brief=current_brief, user_input=user_input, now=now)
    event = InteractionEvent(
        type=interpretation.event_type,
        delta=interpretation.delta,
        actor=InteractionActor.USER,
        timestamp=now,
    )
    updated_brief = pm.apply_event(brief=current_brief, event=event)
    decision = pm.decide_next_action(
        brief=updated_brief,
        event=event,
        affected_fields=interpretation.affected_fields,
        raw_input=user_input,
    )
    plan_implications = build_plan_implications(
        brief=updated_brief,
        action=decision.action,
        affected_fields=interpretation.affected_fields,
        operation=operation,
    )

    _update_record_from_brief(record=record, brief=updated_brief, user=user)
    sequence = _next_event_sequence(record)
    event_record = InteractionEventRecord.objects.create(
        organization=record.organization,
        company=record.company,
        operation=record.operation,
        brief=record,
        sequence=sequence,
        event_type=event.type.value,
        actor=event.actor.value,
        actor_user=user,
        timestamp=event.timestamp,
        raw_input=user_input,
        delta_json=interpretation.delta,
        affected_fields_json=interpretation.affected_fields,
        interpretation_json=interpretation_payload(interpretation),
        pm_action=decision.action.value,
        plan_implications_json=plan_implications,
    )

    return InteractionResult(
        brief_record=record,
        event_record=event_record,
        brief=updated_brief,
        interpretation=interpretation,
        decision=decision,
        plan_implications=plan_implications,
    )


def initial_brief_for_scope(*, company: Graph, operation: Run | None = None) -> OperatingBrief:
    company_profile = _company_profile(company)
    objective = _profile_string(company_profile, "objective") or company.description or None
    autonomy_mode = _autonomy_mode_value(_profile_string(company_profile, "autonomyMode"))
    if operation is not None:
        operation_brief = operation.input_json.get("operation_brief")
        if isinstance(operation_brief, str) and operation_brief.strip():
            objective = operation_brief.strip()
    return OperatingBrief(
        objective=objective,
        deliverable=None,
        priority_frame=PriorityFrame(),
        autonomy_mode=autonomy_mode,
    )


def brief_from_record(record: OperatingBriefRecord) -> OperatingBrief:
    return OperatingBrief(
        objective=_nullable_string(record.objective),
        deliverable=_nullable_string(record.deliverable),
        constraints=_string_list(record.constraints_json),
        success_criteria=_string_list(record.success_criteria_json),
        stakeholders=_string_list(record.stakeholders_json),
        dependencies=_string_list(record.dependencies_json),
        assumptions=[
            _assumption_from_payload(item, record.created_at)
            for item in _dict_list(record.assumptions_json)
        ],
        clarifications=[
            _clarification_from_payload(item) for item in _dict_list(record.clarifications_json)
        ],
        priority_frame=_priority_frame_from_payload(record.priority_frame_json),
        autonomy_mode=_autonomy_mode_value(record.autonomy_mode),
    )


def brief_payload(
    brief: OperatingBrief,
    *,
    record: OperatingBriefRecord | None,
    company: Graph | None = None,
    operation: Run | None = None,
) -> dict[str, Any]:
    company_id = record.company_id if record is not None else getattr(company, "id", None)
    operation_id = record.operation_id if record is not None else getattr(operation, "id", None)
    return {
        "id": str(record.id) if record is not None else None,
        "organization_id": str(record.organization_id) if record is not None else None,
        "company_id": str(company_id) if company_id is not None else None,
        "operation_id": str(operation_id) if operation_id is not None else None,
        "objective": brief.objective,
        "deliverable": brief.deliverable,
        "constraints": brief.constraints,
        "success_criteria": brief.success_criteria,
        "stakeholders": brief.stakeholders,
        "dependencies": brief.dependencies,
        "assumptions": [_assumption_to_payload(item) for item in brief.assumptions],
        "clarifications": [_clarification_to_payload(item) for item in brief.clarifications],
        "priority_frame": _priority_frame_to_payload(brief.priority_frame),
        "autonomy_mode": brief.autonomy_mode.value,
        "created_at": record.created_at.isoformat() if record is not None else None,
        "updated_at": record.updated_at.isoformat() if record is not None else None,
    }


def event_payload(record: InteractionEventRecord) -> dict[str, Any]:
    return {
        "id": str(record.id),
        "brief_id": str(record.brief_id),
        "company_id": str(record.company_id),
        "operation_id": str(record.operation_id) if record.operation_id else None,
        "sequence": record.sequence,
        "type": record.event_type,
        "actor": record.actor,
        "timestamp": record.timestamp.isoformat(),
        "raw_input": record.raw_input,
        "delta": record.delta_json,
        "affected_fields": record.affected_fields_json,
        "interpretation": record.interpretation_json,
        "pm_action": record.pm_action,
        "plan_implications": record.plan_implications_json,
        "created_at": record.created_at.isoformat(),
    }


def interpretation_payload(interpretation: InteractionInterpretation) -> dict[str, Any]:
    return {
        "intent_classification": interpretation.event_type.value,
        "affected_fields": interpretation.affected_fields,
        "confidence": interpretation.confidence,
        "rationale": interpretation.rationale,
    }


def decision_payload(decision: ProjectManagerDecision) -> dict[str, Any]:
    return {
        "action": decision.action.value,
        "rationale": decision.rationale,
    }


def build_plan_implications(
    *,
    brief: OperatingBrief,
    action: ProjectManagerAction,
    affected_fields: list[str],
    operation: Run | None,
) -> dict[str, Any]:
    active_operation = operation is not None and operation.status in ACTIVE_OPERATION_STATUSES
    requires_plan_revision = active_operation and bool(set(affected_fields) & PLAN_REVISION_FIELDS)
    blocking_clarifications = [
        _clarification_to_payload(item) for item in brief.clarifications if item.blocking
    ]
    return {
        "execution_ready": action == ProjectManagerAction.EXECUTE,
        "requires_plan_revision": requires_plan_revision,
        "active_operation_id": str(operation.id) if operation is not None else None,
        "should_interrupt_active_operation": False,
        "affected_fields": affected_fields,
        "blocking_clarifications": blocking_clarifications,
        "summary": _implication_summary(action, requires_plan_revision),
    }


def _get_or_create_locked_brief(
    *,
    user: User,
    company: Graph,
    operation: Run | None,
) -> OperatingBriefRecord:
    organization = company.organization
    if organization is None:
        raise ValueError("Operating briefs require an organization-scoped company.")

    record = (
        OperatingBriefRecord.objects.select_for_update()
        .filter(
            organization=organization,
            company=company,
            operation=operation,
        )
        .first()
    )
    if record is not None:
        return record

    initial = initial_brief_for_scope(company=company, operation=operation)
    company_brief = None
    if operation is not None:
        company_brief = get_current_brief_record(company=company, operation=None)
    if company_brief is not None and operation is not None:
        initial = brief_from_record(company_brief)
        operation_brief = operation.input_json.get("operation_brief")
        if isinstance(operation_brief, str) and operation_brief.strip():
            initial.objective = operation_brief.strip()

    return OperatingBriefRecord.objects.create(
        organization=organization,
        company=company,
        operation=operation,
        objective=initial.objective,
        deliverable=initial.deliverable,
        constraints_json=initial.constraints,
        success_criteria_json=initial.success_criteria,
        stakeholders_json=initial.stakeholders,
        dependencies_json=initial.dependencies,
        assumptions_json=[_assumption_to_payload(item) for item in initial.assumptions],
        clarifications_json=[_clarification_to_payload(item) for item in initial.clarifications],
        priority_frame_json=_priority_frame_to_payload(initial.priority_frame),
        autonomy_mode=initial.autonomy_mode.value,
        created_by=user,
        updated_by=user,
    )


def _update_record_from_brief(
    *,
    record: OperatingBriefRecord,
    brief: OperatingBrief,
    user: User,
) -> None:
    record.objective = brief.objective
    record.deliverable = brief.deliverable
    record.constraints_json = brief.constraints
    record.success_criteria_json = brief.success_criteria
    record.stakeholders_json = brief.stakeholders
    record.dependencies_json = brief.dependencies
    record.assumptions_json = [_assumption_to_payload(item) for item in brief.assumptions]
    record.clarifications_json = [_clarification_to_payload(item) for item in brief.clarifications]
    record.priority_frame_json = _priority_frame_to_payload(brief.priority_frame)
    record.autonomy_mode = brief.autonomy_mode.value
    record.updated_by = user
    record.save(
        update_fields=[
            "objective",
            "deliverable",
            "constraints_json",
            "success_criteria_json",
            "stakeholders_json",
            "dependencies_json",
            "assumptions_json",
            "clarifications_json",
            "priority_frame_json",
            "autonomy_mode",
            "updated_by",
            "updated_at",
        ]
    )


def _next_event_sequence(record: OperatingBriefRecord) -> int:
    last_event = InteractionEventRecord.objects.filter(brief=record).order_by("-sequence").first()
    if last_event is None:
        return 1
    return int(last_event.sequence) + 1


def _company_profile(company: Graph) -> dict[str, Any]:
    latest_version = (
        GraphVersion.objects.filter(graph=company).order_by("-version", "-created_at").first()
    )
    if latest_version is None:
        return {}
    metadata = latest_version.graph_json.get("metadata")
    if not isinstance(metadata, dict):
        return {}
    profile = metadata.get("company_profile")
    return profile if isinstance(profile, dict) else {}


def _profile_string(profile: dict[str, Any], key: str) -> str:
    value = profile.get(key)
    return value.strip() if isinstance(value, str) else ""


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _classify_input(*, brief: OperatingBrief, text: str) -> InteractionEventType:
    normalized = text.lower()
    if _is_constraint(normalized):
        return InteractionEventType.CONSTRAINT
    if _is_priority_shift(normalized):
        return InteractionEventType.PRIORITY_SHIFT
    if _is_approval(normalized):
        return InteractionEventType.APPROVE
    if _is_override(normalized):
        return InteractionEventType.OVERRIDE
    if text.endswith("?") or re.match(r"^(what|who|when|where|why|how)\b", normalized):
        return InteractionEventType.CLARIFY
    if not brief.objective or re.match(
        r"^(build|create|launch|start|make|plan|design|produce)\b", normalized
    ):
        return InteractionEventType.CREATE
    return InteractionEventType.MODIFY


def _is_priority_shift(text: str) -> bool:
    if any(word in text for word in ("speed", "fast", "faster", "quick", "urgent", "asap")):
        return True
    if (
        any(word in text for word in ("cost", "budget", "cheap", "expensive"))
        and "constraint" not in text
    ):
        return True
    if any(word in text for word in ("quality", "polish", "premium", "accuracy")):
        return True
    return any(word in text for word in ("risk", "safe", "compliance", "legal"))


def _is_constraint(text: str) -> bool:
    return bool(
        re.search(
            r"\b(can't|cannot|can not|must not|don't|do not|without|no)\b",
            text,
        )
    )


def _is_approval(text: str) -> bool:
    return bool(re.search(r"\b(approve|approved|go ahead|execute|ship it|looks good)\b", text))


def _is_override(text: str) -> bool:
    return bool(re.search(r"\b(override|ignore previous|replace previous|instead of)\b", text))


def _is_stop_or_cancel(text: str) -> bool:
    return bool(re.search(r"\b(stop|cancel|block|do not continue|don't continue)\b", text.lower()))


def _requires_high_impact_clarification(raw_input: str, affected_fields: list[str]) -> bool:
    text = raw_input.lower()
    high_impact = {"success_criteria", "constraints", "dependencies", "autonomy_mode"}
    vague = bool(
        re.search(r"\b(stricter|looser|better|different|someone else|another team)\b", text)
    )
    risk_or_feasibility = bool(
        re.search(r"\b(legal|compliance|risk|budget|deadline|feasible)\b", text)
    )
    return bool(set(affected_fields) & high_impact and vague and risk_or_feasibility)


def _constraint_from_text(text: str) -> str:
    normalized = text.strip().rstrip(".")
    replacements = [
        (r"^we can'?t use\s+", "Cannot use "),
        (r"^we cannot use\s+", "Cannot use "),
        (r"^we can not use\s+", "Cannot use "),
        (r"^can't use\s+", "Cannot use "),
        (r"^cannot use\s+", "Cannot use "),
        (r"^no\s+", "No "),
        (r"^without\s+", "Without "),
        (r"^do not use\s+", "Do not use "),
        (r"^don't use\s+", "Do not use "),
        (r"^must not\s+", "Must not "),
    ]
    result = normalized
    for pattern, replacement in replacements:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return _sentence_case(result)


def _override_from_text(text: str) -> str:
    return f"Operator override: {_sentence_case(text)}"


def _priority_delta_from_text(text: str) -> dict[str, float]:
    normalized = text.lower()
    priorities = {"speed": 0.5, "cost": 0.5, "quality": 0.5, "risk": 0.5}
    aliases = {
        "speed": ("speed", "fast", "faster", "quick", "urgent", "asap"),
        "cost": ("cost", "budget", "cheap", "less expensive", "lower cost"),
        "quality": ("quality", "polish", "premium", "accuracy"),
        "risk": ("risk", "safe", "safety", "compliance", "legal"),
    }
    for field_name, terms in aliases.items():
        if any(term in normalized for term in terms):
            priorities[field_name] = 0.8

    match = re.search(
        r"(speed|cost|quality|risk)\s+matters\s+more\s+than\s+(speed|cost|quality|risk)", normalized
    )
    if match:
        priorities[match.group(1)] = 0.9
        priorities[match.group(2)] = 0.3
    match = re.search(r"(speed|cost|quality|risk)\s+over\s+(speed|cost|quality|risk)", normalized)
    if match:
        priorities[match.group(1)] = 0.9
        priorities[match.group(2)] = 0.35

    return {key: value for key, value in priorities.items() if value != 0.5}


def _stakeholder_from_text(text: str) -> str:
    patterns = [
        r"\btarget\s+(.+)$",
        r"\bfocus on\s+(.+)$",
        r"\bfor\s+(.+? clients?)$",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            value = _strip_trailing_punctuation(match.group(1))
            return _sentence_case(_strip_leading_filler(value))
    return ""


def _success_criterion_from_text(text: str) -> str:
    patterns = [
        r"\bsuccess means\s+(.+)$",
        r"\bsuccess is\s+(.+)$",
        r"\bmeasure\s+(.+)$",
        r"\bmetric is\s+(.+)$",
        r"\bmust achieve\s+(.+)$",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return _sentence_case(_strip_trailing_punctuation(match.group(1)))
    return ""


def _dependency_from_text(text: str) -> str:
    patterns = [
        r"\bdepends on\s+(.+)$",
        r"\bneed access to\s+(.+)$",
        r"\brequires\s+(.+)$",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return _sentence_case(_strip_trailing_punctuation(match.group(1)))
    return ""


def _autonomy_mode_from_text(text: str) -> AutonomyMode | None:
    normalized = text.lower()
    if "manual" in normalized:
        return AutonomyMode.MANUAL
    if "autonomous" in normalized:
        return AutonomyMode.AUTONOMOUS
    if "assisted" in normalized:
        return AutonomyMode.ASSISTED
    return None


def _looks_like_objective_rewrite(text: str) -> bool:
    return bool(re.match(r"^(actually|change|update|switch|make it|now)\b", text.lower()))


def _strip_rewrite_prefix(text: str) -> str:
    return (
        re.sub(
            r"^(actually|change|update|switch|make it|now)\s+(to\s+)?",
            "",
            text,
            flags=re.IGNORECASE,
        ).strip()
        or text
    )


def _deliverable_from_objective(text: str) -> str:
    value = re.sub(
        r"^(build|create|launch|start|make|plan|design|produce)\s+(a|an|the)?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()
    return _sentence_case(_strip_trailing_punctuation(value)) if value else ""


def _strip_leading_filler(value: str) -> str:
    return re.sub(r"^(the|a|an)\s+", "", value.strip(), flags=re.IGNORECASE)


def _strip_trailing_punctuation(value: str) -> str:
    return value.strip().rstrip(".,;: ")


def _sentence_case(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        return ""
    return stripped[0].upper() + stripped[1:]


def _append_delta(delta: dict[str, Any], field_name: str, values: list[Any]) -> None:
    append_delta = _dict_value(delta, "append")
    existing = append_delta.get(field_name)
    if isinstance(existing, list):
        existing.extend(values)
    else:
        append_delta[field_name] = values


def _affected_fields(delta: dict[str, Any]) -> list[str]:
    fields: set[str] = set()
    for key in ("set", "append", "remove"):
        value = delta.get(key)
        if isinstance(value, dict):
            fields.update(str(item) for item in value.keys())
    if _dict_value(delta, "priority_frame"):
        fields.add("priority_frame")
    return sorted(fields)


def _compact_delta(delta: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key, value in delta.items():
        if value:
            compact[key] = value
    return compact


def _interpretation_confidence(
    event_type: InteractionEventType, affected_fields: list[str]
) -> float:
    if event_type in {InteractionEventType.CONSTRAINT, InteractionEventType.PRIORITY_SHIFT}:
        return 0.86
    if affected_fields:
        return 0.74
    return 0.42


def _interpretation_rationale(event_type: InteractionEventType, affected_fields: list[str]) -> str:
    fields = ", ".join(affected_fields) if affected_fields else "context"
    return f"Classified as {event_type.value} affecting {fields}."


def _append_unique_strings(existing: list[str], incoming: list[str]) -> list[str]:
    result = list(existing)
    seen = {_dedupe_key(item) for item in result}
    for item in incoming:
        normalized = item.strip()
        if not normalized:
            continue
        key = _dedupe_key(normalized)
        if key not in seen:
            result.append(normalized)
            seen.add(key)
    return result


def _remove_strings(existing: list[str], incoming: list[str]) -> list[str]:
    removals = {_dedupe_key(item) for item in incoming}
    return [item for item in existing if _dedupe_key(item) not in removals]


def _append_unique_assumptions(
    existing: list[AssumptionItem], incoming: list[AssumptionItem]
) -> list[AssumptionItem]:
    result = list(existing)
    seen = {
        _dedupe_key(f"{item.field}:{json.dumps(item.value, sort_keys=True, default=str)}")
        for item in result
    }
    for item in incoming:
        key = _dedupe_key(f"{item.field}:{json.dumps(item.value, sort_keys=True, default=str)}")
        if key not in seen:
            result.append(item)
            seen.add(key)
    return result


def _append_unique_clarifications(
    existing: list[ClarificationItem], incoming: list[ClarificationItem]
) -> list[ClarificationItem]:
    result = list(existing)
    seen = {_dedupe_key(f"{item.related_field}:{item.question}") for item in result}
    for item in incoming:
        key = _dedupe_key(f"{item.related_field}:{item.question}")
        if key not in seen:
            result.append(item)
            seen.add(key)
    return result


def _dedupe_key(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _assumption_payload(
    field: str, value: Any, confidence: float, created_at: datetime
) -> dict[str, Any]:
    return {
        "field": field,
        "value": value,
        "confidence": round(max(0.0, min(float(confidence), 1.0)), 2),
        "created_at": created_at.isoformat(),
    }


def _assumption_from_payload(
    payload: dict[str, Any], fallback_created_at: datetime
) -> AssumptionItem:
    return AssumptionItem(
        field=str(payload.get("field") or "context"),
        value=payload.get("value"),
        confidence=float(payload.get("confidence") or 0.5),
        created_at=_datetime_from_payload(payload.get("created_at"), fallback_created_at),
    )


def _assumption_to_payload(item: AssumptionItem) -> dict[str, Any]:
    return _assumption_payload(item.field, item.value, item.confidence, item.created_at)


def _clarification_from_payload(payload: dict[str, Any]) -> ClarificationItem:
    return ClarificationItem(
        question=str(payload.get("question") or "Clarification needed."),
        blocking=bool(payload.get("blocking")),
        related_field=str(payload.get("related_field") or "objective"),
    )


def _clarification_to_payload(item: ClarificationItem) -> dict[str, Any]:
    return {
        "question": item.question,
        "blocking": item.blocking,
        "related_field": item.related_field,
    }


def _priority_frame_from_payload(value: Any) -> PriorityFrame:
    payload = value if isinstance(value, dict) else {}
    return PriorityFrame(
        speed=float(payload.get("speed", 0.5)),
        cost=float(payload.get("cost", 0.5)),
        quality=float(payload.get("quality", 0.5)),
        risk=float(payload.get("risk", 0.5)),
    ).normalized()


def _priority_frame_to_payload(priority_frame: PriorityFrame) -> dict[str, float]:
    normalized = priority_frame.normalized()
    return {
        "speed": normalized.speed,
        "cost": normalized.cost,
        "quality": normalized.quality,
        "risk": normalized.risk,
    }


def _autonomy_mode_value(value: Any) -> AutonomyMode:
    try:
        return AutonomyMode(str(value or AutonomyMode.ASSISTED.value))
    except ValueError:
        return AutonomyMode.ASSISTED


def _nullable_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [cast(dict[str, Any], item) for item in value if isinstance(item, dict)]


def _dict_value(value: dict[str, Any], key: str) -> dict[str, Any]:
    candidate = value.get(key)
    return candidate if isinstance(candidate, dict) else {}


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _datetime_from_payload(value: Any, fallback: datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=UTC)
            return parsed
        except ValueError:
            return fallback
    return fallback


def _implication_summary(action: ProjectManagerAction, requires_plan_revision: bool) -> str:
    if requires_plan_revision:
        return "Brief updated; active operation may need a plan revision after the current backend-owned step."
    if action == ProjectManagerAction.EXECUTE:
        return "Brief is ready for execution through the existing operation controls."
    if action == ProjectManagerAction.ASK_CLARIFICATION:
        return "Brief updated, but a blocking clarification is needed before execution."
    if action == ProjectManagerAction.BLOCK:
        return "Brief updated and forward execution is blocked by operator direction."
    return "Brief updated; assumptions were recorded so work can continue without restarting."
