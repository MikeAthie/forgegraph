"""Backend-owned WorkWhiteboard services and cache snapshots."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any
from uuid import UUID

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import Q, QuerySet

from application.services.company_access import accessible_company_queryset, has_company_access
from application.services.domain_event_outbox import sanitize_outbox_payload
from application.services.rbac import has_min_role
from application.services.redis_connections import build_redis_client
from application.services.routing import register_department, route_event_to_department
from infrastructure.orm.models import (
    CommunicationMessage,
    DepartmentRegistry,
    Graph,
    RequestClassificationRecord,
    ServiceEngagement,
    TaskRoutingRecord,
    User,
    WorkWhiteboard,
)

ACTIVE_WHITEBOARD_STATUSES = {
    WorkWhiteboard.STATUS_DRAFT,
    WorkWhiteboard.STATUS_ONBOARDING,
    WorkWhiteboard.STATUS_READY_FOR_STRATEGY,
    WorkWhiteboard.STATUS_IN_STRATEGY,
    WorkWhiteboard.STATUS_IN_CONTENT,
    WorkWhiteboard.STATUS_IN_APPROVAL,
    WorkWhiteboard.STATUS_IN_DEPLOYMENT,
    WorkWhiteboard.STATUS_IN_OPTIMIZATION,
}
ACTIVE_WORKBOARD_STATUSES = {
    WorkWhiteboard.WORK_STATUS_DRAFT,
    WorkWhiteboard.WORK_STATUS_INTAKE,
    WorkWhiteboard.WORK_STATUS_READY_FOR_PLANNING,
    WorkWhiteboard.WORK_STATUS_PLANNING,
    WorkWhiteboard.WORK_STATUS_IN_PROGRESS,
    WorkWhiteboard.WORK_STATUS_REVIEW,
    WorkWhiteboard.WORK_STATUS_DELIVERY,
    WorkWhiteboard.WORK_STATUS_MEASUREMENT,
}
LEGACY_STATUS_TO_WORK_STATUS = {
    WorkWhiteboard.STATUS_DRAFT: WorkWhiteboard.WORK_STATUS_DRAFT,
    WorkWhiteboard.STATUS_ONBOARDING: WorkWhiteboard.WORK_STATUS_INTAKE,
    WorkWhiteboard.STATUS_READY_FOR_STRATEGY: WorkWhiteboard.WORK_STATUS_READY_FOR_PLANNING,
    WorkWhiteboard.STATUS_IN_STRATEGY: WorkWhiteboard.WORK_STATUS_PLANNING,
    WorkWhiteboard.STATUS_IN_CONTENT: WorkWhiteboard.WORK_STATUS_IN_PROGRESS,
    WorkWhiteboard.STATUS_IN_APPROVAL: WorkWhiteboard.WORK_STATUS_REVIEW,
    WorkWhiteboard.STATUS_IN_DEPLOYMENT: WorkWhiteboard.WORK_STATUS_DELIVERY,
    WorkWhiteboard.STATUS_IN_OPTIMIZATION: WorkWhiteboard.WORK_STATUS_MEASUREMENT,
    WorkWhiteboard.STATUS_CLOSED: WorkWhiteboard.WORK_STATUS_CLOSED,
}
WORK_STATUS_TO_LEGACY_STATUS = {
    WorkWhiteboard.WORK_STATUS_DRAFT: WorkWhiteboard.STATUS_DRAFT,
    WorkWhiteboard.WORK_STATUS_INTAKE: WorkWhiteboard.STATUS_ONBOARDING,
    WorkWhiteboard.WORK_STATUS_READY_FOR_PLANNING: WorkWhiteboard.STATUS_READY_FOR_STRATEGY,
    WorkWhiteboard.WORK_STATUS_PLANNING: WorkWhiteboard.STATUS_IN_STRATEGY,
    WorkWhiteboard.WORK_STATUS_IN_PROGRESS: WorkWhiteboard.STATUS_IN_CONTENT,
    WorkWhiteboard.WORK_STATUS_REVIEW: WorkWhiteboard.STATUS_IN_APPROVAL,
    WorkWhiteboard.WORK_STATUS_DELIVERY: WorkWhiteboard.STATUS_IN_DEPLOYMENT,
    WorkWhiteboard.WORK_STATUS_MEASUREMENT: WorkWhiteboard.STATUS_IN_OPTIMIZATION,
    WorkWhiteboard.WORK_STATUS_CLOSED: WorkWhiteboard.STATUS_CLOSED,
}
WHITEBOARD_SNAPSHOT_DEFAULT_TTL_SECONDS = 24 * 60 * 60
WHITEBOARD_REQUIRED_FIELDS = [
    "objective",
    "offer",
    "timeline",
    "target_audience",
    "brand_voice",
    "visual_constraints",
    "legal_compliance_constraints",
    "approval_owner",
    "success_metrics",
    "inventory_price_margin_constraints",
    "connector_readiness",
]
WORKBOARD_REQUIRED_FIELDS = [
    "objective",
    "scope",
    "timeline",
    "stakeholders",
    "resources",
    "constraints",
    "approval_owner",
    "success_metrics",
    "delivery_readiness",
]
WORK_STATUS_VALUES = {choice[0] for choice in WorkWhiteboard.WORK_STATUS_CHOICES}
LEGACY_MISSING_FIELD_TO_WORK_FIELD = {
    "objective": "objective",
    "offer": "scope",
    "timeline": "timeline",
    "target_audience": "stakeholders",
    "brand_voice": "resources",
    "visual_constraints": "constraints",
    "legal_compliance_constraints": "constraints",
    "approval_owner": "approval_owner",
    "success_metrics": "success_metrics",
    "inventory_price_margin_constraints": "resources",
    "connector_readiness": "delivery_readiness",
}
logger = logging.getLogger(__name__)
ONBOARDING_DEPARTMENTS = {
    "account-intake": {
        "name": "Account Intake",
        "department_type": "account_intake",
        "fields": {
            "objective",
            "offer",
            "timeline",
            "approval_owner",
            "inventory_price_margin_constraints",
        },
    },
    "strategy": {
        "name": "Strategy",
        "department_type": "strategy",
        "fields": {"target_audience", "success_metrics", "objective"},
    },
    "analytics": {
        "name": "Analytics",
        "department_type": "analytics",
        "fields": {"success_metrics"},
    },
    "brand-creative": {
        "name": "Brand/Creative",
        "department_type": "brand_creative",
        "fields": {"brand_voice", "visual_constraints"},
    },
    "deployment-ops": {
        "name": "Deployment Ops",
        "department_type": "deployment_ops",
        "fields": {"connector_readiness"},
    },
    "legal-compliance": {
        "name": "Legal/Compliance",
        "department_type": "legal_compliance",
        "fields": {"legal_compliance_constraints"},
    },
}


class WorkWhiteboardError(ValueError):
    """Domain error for WorkWhiteboard operations."""

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


def list_whiteboards_for_user(
    *,
    user: User,
    company_id: UUID | str | None = None,
    status: str = "",
) -> QuerySet[WorkWhiteboard]:
    companies = accessible_company_queryset(user, minimum_role="viewer")
    if company_id:
        companies = companies.filter(id=company_id)
    queryset = _whiteboard_queryset().filter(company__in=companies)
    organization = user.default_organization
    if organization is None:
        return queryset.none()
    queryset = queryset.filter(organization=organization)
    if status:
        if status in WORK_STATUS_VALUES:
            queryset = queryset.filter(work_status=status)
        else:
            queryset = queryset.filter(status=status)
    return queryset


def get_whiteboard_for_user(*, user: User, whiteboard_id: UUID | str) -> WorkWhiteboard | None:
    return list_whiteboards_for_user(user=user).filter(id=whiteboard_id).first()


def create_or_resume_whiteboard(  # noqa: C901
    *,
    company: Graph,
    source_message: CommunicationMessage | None = None,
    service_engagement: ServiceEngagement | None = None,
    classification: RequestClassificationRecord | None = None,
    known_fields: dict[str, Any] | None = None,
    idempotency_key: str = "",
    created_by: User | None = None,
) -> WorkWhiteboard:
    """Create an active durable whiteboard, or return the canonical existing one."""

    if source_message is not None and source_message.company_id != company.id:
        raise WorkWhiteboardError(
            "company_mismatch", "Source message belongs to a different company."
        )
    if service_engagement is not None and service_engagement.company_id != company.id:
        raise WorkWhiteboardError(
            "company_mismatch", "Service engagement belongs to a different company."
        )
    existing = _active_whiteboard_for(
        company=company,
        source_message=source_message,
        service_engagement=service_engagement,
    )
    if existing is not None:
        if classification is not None and classification.matched_whiteboard_id != existing.id:
            classification.matched_whiteboard = existing
            classification.save(update_fields=["matched_whiteboard", "updated_at"])
        return existing
    key = str(idempotency_key or "").strip()
    if key:
        existing = (
            _whiteboard_queryset()
            .filter(organization=company.organization, idempotency_key=key)
            .first()
        )
        if existing is not None:
            return existing
    data = sanitize_outbox_payload(known_fields or {})
    context = _workboard_context_from_data(
        data=data,
        company=company,
        default_status=WorkWhiteboard.STATUS_ONBOARDING,
        default_work_status=WorkWhiteboard.WORK_STATUS_INTAKE,
    )
    whiteboard = WorkWhiteboard(
        organization=company.organization,
        company=company,
        service_engagement=service_engagement,
        communication_thread=source_message.thread if source_message is not None else None,
        source_message=source_message,
        status=context["status"],
        work_status=context["work_status"],
        request_type=str(data.get("request_type") or "service_request")[:80],
        project_name=context["project_name"],
        client_name=context["client_name"],
        request_summary=str(data.get("request_summary") or "")[:4000],
        objective=str(data.get("objective") or ""),
        budget_limit=str(data.get("budget_limit") or "")[:120],
        timeline=str(data.get("timeline") or "")[:255],
        constraints_json=context["constraints"],
        target_audience_json=context["target_audience"],
        brand_context_json=context["brand_context"],
        product_context_json=context["product_context"],
        channel_context_json=context["channel_context"],
        stakeholder_context_json=context["stakeholder_context"],
        resource_context_json=context["resource_context"],
        delivery_context_json=context["delivery_context"],
        known_facts_json=_dict(data.get("known_facts")),
        assumptions_json=_list(data.get("assumptions")),
        metadata_json=_dict(data.get("metadata")),
        idempotency_key=key,
        created_by=created_by,
    )
    whiteboard.missing_fields_json = compute_whiteboard_missing_fields(whiteboard)
    whiteboard.work_missing_fields_json = compute_workboard_missing_fields(whiteboard)
    whiteboard.completion_score = compute_workboard_completion_score(
        whiteboard.work_missing_fields_json
    )
    whiteboard.redis_snapshot_key = whiteboard_snapshot_key(whiteboard)
    try:
        with transaction.atomic():
            whiteboard.full_clean()
            whiteboard.save()
            if classification is not None:
                classification.matched_whiteboard = whiteboard
                classification.save(update_fields=["matched_whiteboard", "updated_at"])
    except IntegrityError:
        if key:
            existing = (
                _whiteboard_queryset()
                .filter(organization=company.organization, idempotency_key=key)
                .first()
            )
            if existing is not None:
                return existing
        raise
    refresh_whiteboard_redis_snapshot(whiteboard)
    return whiteboard


def initialize_whiteboard_from_message(
    *,
    message: CommunicationMessage,
    classification: RequestClassificationRecord | None = None,
    idempotency_key: str = "",
    created_by: User | None = None,
) -> WorkWhiteboard:
    if message.company is None:
        raise WorkWhiteboardError(
            "company_required", "Whiteboards require a company-scoped message."
        )
    known_fields = extract_known_fields_from_message(message)
    key = idempotency_key or f"whiteboard:message:{message.id}"
    return create_or_resume_whiteboard(
        company=message.company,
        source_message=message,
        service_engagement=message.thread.service_engagement,
        classification=classification,
        known_fields=known_fields,
        idempotency_key=key,
        created_by=created_by or message.sender_user,
    )


def create_onboarding_routing_tasks(
    *,
    whiteboard: WorkWhiteboard,
    classification: RequestClassificationRecord | None = None,
) -> list[TaskRoutingRecord]:
    missing = set(whiteboard.missing_fields_json or [])
    if not missing:
        return []
    records: list[TaskRoutingRecord] = []
    for slug, config in ONBOARDING_DEPARTMENTS.items():
        department_missing = sorted(missing.intersection(set(config["fields"])))
        if not department_missing:
            continue
        department = _ensure_onboarding_department(
            company=whiteboard.company,
            slug=slug,
            name=str(config["name"]),
            department_type=str(config["department_type"]),
        )
        record = route_event_to_department(
            company=whiteboard.company,
            department=department,
            event_type="whiteboard.onboarding.missing_context",
            trigger_type="whiteboard.onboarding.missing_context",
            communication_thread=whiteboard.communication_thread,
            communication_message=whiteboard.source_message,
            service_engagement=whiteboard.service_engagement,
            reason=f"Fill missing whiteboard context: {', '.join(department_missing)}.",
            status="queued",
            priority="normal",
            idempotency_key=f"whiteboard:{whiteboard.id}:onboarding:{slug}",
            metadata={
                "whiteboard_id": str(whiteboard.id),
                "classification_id": str(classification.id) if classification else None,
                "missing_fields": department_missing,
            },
        )
        records.append(record)
    return records


def route_account_intake_clarification(
    *,
    message: CommunicationMessage,
    classification: RequestClassificationRecord,
) -> TaskRoutingRecord:
    if message.company is None:
        raise WorkWhiteboardError(
            "company_required", "Clarification routing requires a company-scoped message."
        )
    department = _ensure_onboarding_department(
        company=message.company,
        slug="account-intake",
        name="Account Intake",
        department_type="account_intake",
    )
    return route_event_to_department(
        company=message.company,
        department=department,
        event_type="request.ambiguous",
        trigger_type="request.ambiguous",
        communication_thread=message.thread,
        communication_message=message,
        service_engagement=message.thread.service_engagement,
        reason="Clarify whether this is a new request or existing work.",
        status="queued",
        priority="normal",
        idempotency_key=f"request-classification:{classification.id}:clarification",
        metadata={
            "classification_id": str(classification.id),
            "classification": classification.classification,
            "confidence": classification.confidence,
        },
    )


def update_whiteboard_field(  # noqa: C901
    *,
    user: User,
    whiteboard: WorkWhiteboard,
    fields: dict[str, Any],
) -> WorkWhiteboard:
    if not _can_mutate_whiteboard(user=user, whiteboard=whiteboard):
        raise WorkWhiteboardError(
            "permission_denied", "You do not have permission to update this whiteboard."
        )
    data = sanitize_outbox_payload(fields)
    update_fields: set[str] = {"updated_at"}

    if "work_status" in data:
        whiteboard.work_status = normalize_work_status(str(data.get("work_status") or ""))
        whiteboard.status = legacy_status_for_work_status(whiteboard.work_status)
        update_fields.update({"work_status", "status"})
    elif "status" in data:
        whiteboard.status = str(data.get("status") or "")
        whiteboard.work_status = work_status_for_legacy_status(whiteboard.status)
        update_fields.update({"status", "work_status"})

    for key, attr in {
        "request_type": "request_type",
        "request_summary": "request_summary",
        "objective": "objective",
        "budget_limit": "budget_limit",
        "timeline": "timeline",
    }.items():
        if key in data:
            setattr(whiteboard, attr, str(data.get(key) or ""))
            update_fields.add(attr)

    if "project_name" in data:
        project_name = str(data.get("project_name") or "")[:255]
        whiteboard.project_name = project_name
        whiteboard.client_name = project_name
        update_fields.update({"project_name", "client_name"})
    elif "client_name" in data:
        client_name = str(data.get("client_name") or "")[:255]
        whiteboard.client_name = client_name
        whiteboard.project_name = client_name
        update_fields.update({"client_name", "project_name"})

    for key, attr in {
        "constraints": "constraints_json",
        "known_facts": "known_facts_json",
        "metadata": "metadata_json",
    }.items():
        if key in data:
            setattr(whiteboard, attr, _dict(data.get(key)))
            update_fields.add(attr)

    if "stakeholder_context" in data:
        stakeholder_context = _dict(data.get("stakeholder_context"))
        whiteboard.stakeholder_context_json = stakeholder_context
        whiteboard.target_audience_json = stakeholder_context
        update_fields.update({"stakeholder_context_json", "target_audience_json"})
    elif "target_audience" in data:
        target_audience = _dict(data.get("target_audience"))
        whiteboard.target_audience_json = target_audience
        whiteboard.stakeholder_context_json = target_audience
        update_fields.update({"target_audience_json", "stakeholder_context_json"})

    if "resource_context" in data:
        resource_context = _dict(data.get("resource_context"))
        whiteboard.resource_context_json = resource_context
        whiteboard.product_context_json = _legacy_product_context_from_resource(resource_context)
        whiteboard.brand_context_json = _legacy_brand_context_from_resource(resource_context)
        update_fields.update(
            {"resource_context_json", "product_context_json", "brand_context_json"}
        )
    elif "product_context" in data or "brand_context" in data:
        if "product_context" in data:
            whiteboard.product_context_json = _dict(data.get("product_context"))
            update_fields.add("product_context_json")
        if "brand_context" in data:
            whiteboard.brand_context_json = _dict(data.get("brand_context"))
            update_fields.add("brand_context_json")
        whiteboard.resource_context_json = _resource_context_from_legacy(
            product_context=whiteboard.product_context_json,
            brand_context=whiteboard.brand_context_json,
        )
        update_fields.add("resource_context_json")

    if "delivery_context" in data:
        delivery_context = _dict(data.get("delivery_context"))
        whiteboard.delivery_context_json = delivery_context
        whiteboard.channel_context_json = delivery_context
        update_fields.update({"delivery_context_json", "channel_context_json"})
    elif "channel_context" in data:
        channel_context = _dict(data.get("channel_context"))
        whiteboard.channel_context_json = channel_context
        whiteboard.delivery_context_json = channel_context
        update_fields.update({"channel_context_json", "delivery_context_json"})

    if "assumptions" in data:
        whiteboard.assumptions_json = _list(data.get("assumptions"))
        update_fields.add("assumptions_json")
    whiteboard.missing_fields_json = compute_whiteboard_missing_fields(whiteboard)
    whiteboard.work_missing_fields_json = compute_workboard_missing_fields(whiteboard)
    whiteboard.completion_score = compute_workboard_completion_score(
        whiteboard.work_missing_fields_json
    )
    update_fields.update(["missing_fields_json", "work_missing_fields_json", "completion_score"])
    whiteboard.full_clean()
    whiteboard.save(update_fields=sorted(set(update_fields)))
    refresh_whiteboard_redis_snapshot(whiteboard)
    return whiteboard


def mark_whiteboard_ready_for_planning(
    *, user: User, whiteboard: WorkWhiteboard
) -> TaskRoutingRecord:
    if not _can_mutate_whiteboard(user=user, whiteboard=whiteboard):
        raise WorkWhiteboardError(
            "permission_denied", "You do not have permission to update this whiteboard."
        )
    with transaction.atomic():
        whiteboard.status = WorkWhiteboard.STATUS_READY_FOR_STRATEGY
        whiteboard.work_status = WorkWhiteboard.WORK_STATUS_READY_FOR_PLANNING
        whiteboard.missing_fields_json = compute_whiteboard_missing_fields(whiteboard)
        whiteboard.work_missing_fields_json = compute_workboard_missing_fields(whiteboard)
        whiteboard.completion_score = compute_workboard_completion_score(
            whiteboard.work_missing_fields_json
        )
        whiteboard.full_clean()
        whiteboard.save(
            update_fields=[
                "status",
                "work_status",
                "missing_fields_json",
                "work_missing_fields_json",
                "completion_score",
                "updated_at",
            ]
        )
        department = _ensure_onboarding_department(
            company=whiteboard.company,
            slug="strategy",
            name="Strategy",
            department_type="strategy",
        )
        record = route_event_to_department(
            company=whiteboard.company,
            department=department,
            user=user,
            event_type="whiteboard.ready_for_planning",
            trigger_type="whiteboard.ready_for_planning",
            communication_thread=whiteboard.communication_thread,
            communication_message=whiteboard.source_message,
            service_engagement=whiteboard.service_engagement,
            reason="Workboard is ready for planning intake.",
            status="queued",
            priority="normal",
            idempotency_key=f"whiteboard:{whiteboard.id}:ready-for-planning",
            metadata={
                "whiteboard_id": str(whiteboard.id),
                "completion_score": whiteboard.completion_score,
                "work_status": whiteboard.work_status,
            },
        )
    refresh_whiteboard_redis_snapshot(whiteboard)
    return record


def mark_whiteboard_ready_for_strategy(
    *, user: User, whiteboard: WorkWhiteboard
) -> TaskRoutingRecord:
    return mark_whiteboard_ready_for_planning(user=user, whiteboard=whiteboard)


def work_status_for_legacy_status(status: str) -> str:
    return LEGACY_STATUS_TO_WORK_STATUS.get(str(status or ""), WorkWhiteboard.WORK_STATUS_DRAFT)


def legacy_status_for_work_status(work_status: str) -> str:
    return WORK_STATUS_TO_LEGACY_STATUS.get(str(work_status or ""), WorkWhiteboard.STATUS_DRAFT)


def normalize_work_status(work_status: str) -> str:
    status = str(work_status or "").strip()
    return status or WorkWhiteboard.WORK_STATUS_DRAFT


def effective_work_status_for_whiteboard(whiteboard: WorkWhiteboard) -> str:
    if whiteboard.work_status and whiteboard.work_status != WorkWhiteboard.WORK_STATUS_DRAFT:
        return whiteboard.work_status
    if whiteboard.status and whiteboard.status != WorkWhiteboard.STATUS_DRAFT:
        return work_status_for_legacy_status(whiteboard.status)
    return whiteboard.work_status or work_status_for_legacy_status(whiteboard.status)


def compute_whiteboard_missing_fields(whiteboard: WorkWhiteboard) -> list[str]:  # noqa: C901
    missing: list[str] = []
    if not str(whiteboard.objective or "").strip():
        missing.append("objective")
    product_context = _dict(whiteboard.product_context_json)
    known_facts = _dict(whiteboard.known_facts_json)
    constraints = _dict(whiteboard.constraints_json)
    target_audience = _dict(whiteboard.target_audience_json)
    brand_context = _dict(whiteboard.brand_context_json)
    channel_context = _dict(whiteboard.channel_context_json)
    if not _has_any(product_context, ["offer", "product", "service"]):
        missing.append("offer")
    if not str(whiteboard.timeline or "").strip():
        missing.append("timeline")
    if not target_audience:
        missing.append("target_audience")
    if not _has_any(brand_context, ["brand_voice", "voice", "tone"]):
        missing.append("brand_voice")
    if not _has_any(constraints, ["visual_constraints", "visual"]):
        missing.append("visual_constraints")
    if not _has_any(constraints, ["legal_compliance_constraints", "legal", "compliance"]):
        missing.append("legal_compliance_constraints")
    if not _has_any(known_facts, ["approval_owner", "approver"]):
        missing.append("approval_owner")
    if not _has_any(known_facts, ["success_metrics", "kpi", "metrics"]):
        missing.append("success_metrics")
    if not _has_any(
        known_facts, ["inventory_price_margin_constraints", "inventory", "price", "margin"]
    ):
        missing.append("inventory_price_margin_constraints")
    if not _has_any(channel_context, ["connector_readiness", "connectors"]):
        missing.append("connector_readiness")
    return [field for field in WHITEBOARD_REQUIRED_FIELDS if field in set(missing)]


def compute_workboard_missing_fields(whiteboard: WorkWhiteboard) -> list[str]:
    missing: list[str] = []
    if not str(whiteboard.objective or "").strip():
        missing.append("objective")
    constraints = _dict(whiteboard.constraints_json)
    known_facts = _dict(whiteboard.known_facts_json)
    stakeholder_context = _dict(whiteboard.stakeholder_context_json) or _dict(
        whiteboard.target_audience_json
    )
    resource_context = _dict(whiteboard.resource_context_json) or _resource_context_from_legacy(
        product_context=whiteboard.product_context_json,
        brand_context=whiteboard.brand_context_json,
    )
    delivery_context = _dict(whiteboard.delivery_context_json) or _dict(
        whiteboard.channel_context_json
    )
    if not _has_any(
        resource_context,
        ["scope", "offer", "product", "service", "deliverable", "output", "resources"],
    ):
        missing.append("scope")
    if not str(whiteboard.timeline or "").strip():
        missing.append("timeline")
    if not stakeholder_context:
        missing.append("stakeholders")
    if not resource_context:
        missing.append("resources")
    if not constraints:
        missing.append("constraints")
    if not (
        _has_any(known_facts, ["approval_owner", "approver"])
        or _has_any(stakeholder_context, ["approval_owner", "approver"])
    ):
        missing.append("approval_owner")
    if not (
        _has_any(known_facts, ["success_metrics", "kpi", "metrics"])
        or _has_any(resource_context, ["success_metrics", "kpi", "metrics"])
    ):
        missing.append("success_metrics")
    if not _has_any(
        delivery_context,
        [
            "delivery_readiness",
            "connector_readiness",
            "connectors",
            "requested_channels",
            "channels",
        ],
    ):
        missing.append("delivery_readiness")
    return [field for field in WORKBOARD_REQUIRED_FIELDS if field in set(missing)]


def compute_whiteboard_completion_score(missing_fields: list[str]) -> float:
    missing = len(set(missing_fields))
    complete = max(len(WHITEBOARD_REQUIRED_FIELDS) - missing, 0)
    return round((complete / len(WHITEBOARD_REQUIRED_FIELDS)) * 100, 2)


def compute_workboard_completion_score(missing_fields: list[str]) -> float:
    missing = len(set(missing_fields))
    complete = max(len(WORKBOARD_REQUIRED_FIELDS) - missing, 0)
    return round((complete / len(WORKBOARD_REQUIRED_FIELDS)) * 100, 2)


def extract_known_fields_from_message(message: CommunicationMessage) -> dict[str, Any]:
    body = str(message.body or "")
    lower = body.lower()
    channels = [
        channel
        for channel in [
            "whatsapp",
            "twilio",
            "brevo",
            "email",
            "instagram",
            "facebook",
            "social",
            "landing page",
        ]
        if channel in lower
    ]
    budget = _extract_budget(body)
    timeline = _extract_timeline(body)
    product_context: dict[str, Any] = {"raw_request_hint": _truncate(body, 280)}
    offer = _extract_offer(body)
    if offer:
        product_context["offer"] = offer
    known_facts: dict[str, Any] = {
        "source_message_id": str(message.id),
        "source_thread_id": str(message.thread_id),
    }
    if "approve" in lower or "approval" in lower:
        known_facts["approval_owner"] = "client"
    channel_context: dict[str, Any] = {}
    if channels:
        channel_context["requested_channels"] = channels
    request_type = "service_request"
    if "campaign" in lower:
        request_type = "campaign"
    elif "launch" in lower:
        request_type = "launch"
    elif "audit" in lower:
        request_type = "audit"
    return {
        "request_type": request_type,
        "client_name": message.company.name if message.company is not None else "",
        "request_summary": _truncate(body, 800),
        "budget_limit": budget,
        "timeline": timeline,
        "product_context": product_context,
        "channel_context": channel_context,
        "known_facts": known_facts,
        "metadata": {"source": "communication_message"},
    }


def whiteboard_payload(
    whiteboard: WorkWhiteboard,
    *,
    user: User | None = None,
    include_internal: bool | None = None,
) -> dict[str, Any]:
    operator = (
        _can_view_internal(user=user, whiteboard=whiteboard)
        if include_internal is None
        else include_internal
    )
    work_status = effective_work_status_for_whiteboard(whiteboard)
    project_name = whiteboard.project_name or whiteboard.client_name
    stakeholder_context = _dict(whiteboard.stakeholder_context_json) or _dict(
        whiteboard.target_audience_json
    )
    resource_context = _dict(whiteboard.resource_context_json) or _resource_context_from_legacy(
        product_context=whiteboard.product_context_json,
        brand_context=whiteboard.brand_context_json,
    )
    delivery_context = _dict(whiteboard.delivery_context_json) or _dict(
        whiteboard.channel_context_json
    )
    work_missing_fields = list(
        whiteboard.work_missing_fields_json
        if isinstance(whiteboard.work_missing_fields_json, list)
        else []
    )
    payload = {
        "id": str(whiteboard.id),
        "organization_id": str(whiteboard.organization_id),
        "company_id": str(whiteboard.company_id),
        "service_engagement_id": str(whiteboard.service_engagement_id)
        if whiteboard.service_engagement_id
        else None,
        "communication_thread_id": str(whiteboard.communication_thread_id)
        if whiteboard.communication_thread_id
        else None,
        "source_message_id": str(whiteboard.source_message_id)
        if whiteboard.source_message_id
        else None,
        "work_status": work_status,
        "status": whiteboard.status,
        "request_type": whiteboard.request_type,
        "project_name": project_name,
        "client_name": whiteboard.client_name,
        "request_summary": whiteboard.request_summary,
        "objective": whiteboard.objective,
        "budget_limit": whiteboard.budget_limit,
        "timeline": whiteboard.timeline,
        "constraints": dict(whiteboard.constraints_json or {}),
        "stakeholder_context": stakeholder_context,
        "resource_context": resource_context,
        "delivery_context": delivery_context,
        "target_audience": dict(whiteboard.target_audience_json or {}),
        "brand_context": dict(whiteboard.brand_context_json or {}),
        "product_context": dict(whiteboard.product_context_json or {}),
        "channel_context": dict(whiteboard.channel_context_json or {}),
        "known_facts": dict(whiteboard.known_facts_json or {}),
        "work_missing_fields": work_missing_fields,
        "missing_fields": list(whiteboard.missing_fields_json or []),
        "semantic_aliases": whiteboard_semantic_aliases(whiteboard),
        "completion_score": whiteboard.completion_score,
        "redis_snapshot_key": whiteboard.redis_snapshot_key if operator else "",
        "created_at": whiteboard.created_at.isoformat(),
        "updated_at": whiteboard.updated_at.isoformat(),
        "can_update": _can_mutate_whiteboard(user=user, whiteboard=whiteboard) if user else False,
    }
    from application.services.workstream_gates import list_whiteboard_phase_contracts

    payload["phase_contracts"] = list_whiteboard_phase_contracts(
        whiteboard=whiteboard,
        user=user,
        include_internal=operator,
    )
    from application.services.deployment_orchestration import deployment_contract_for_whiteboard

    payload["deployment_contract"] = deployment_contract_for_whiteboard(
        whiteboard=whiteboard,
        user=user,
        include_internal=operator,
    )
    from application.services.performance_orchestration import performance_contract_for_whiteboard

    payload["performance_contract"] = performance_contract_for_whiteboard(
        whiteboard=whiteboard,
        user=user,
        include_internal=operator,
    )
    if operator:
        payload["assumptions"] = list(whiteboard.assumptions_json or [])
        payload["metadata"] = dict(whiteboard.metadata_json or {})
        payload["routing_records"] = [
            {
                "id": str(record.id),
                "department_id": str(record.to_department_id),
                "department_name": record.to_department.name,
                "status": record.status,
                "priority": record.priority,
                "reason": record.reason,
                "created_at": record.created_at.isoformat(),
            }
            for record in _routing_records_for_whiteboard(whiteboard)
        ]
    return payload


def whiteboard_snapshot_key(whiteboard: WorkWhiteboard) -> str:
    return whiteboard.redis_snapshot_key or f"forgegraph:whiteboard:{whiteboard.id}"


def whiteboard_snapshot_ttl_seconds() -> int:
    configured_value: object = os.environ.get("WHITEBOARD_SNAPSHOT_TTL_SECONDS")
    if configured_value is None or configured_value == "":
        configured_value = getattr(
            settings,
            "WHITEBOARD_SNAPSHOT_TTL_SECONDS",
            WHITEBOARD_SNAPSHOT_DEFAULT_TTL_SECONDS,
        )
    try:
        ttl_seconds = int(str(configured_value))
    except (TypeError, ValueError):
        logger.warning(
            "invalid_whiteboard_snapshot_ttl",
            extra={"configured_value": str(configured_value)},
        )
        return WHITEBOARD_SNAPSHOT_DEFAULT_TTL_SECONDS
    if ttl_seconds <= 0:
        logger.warning(
            "invalid_whiteboard_snapshot_ttl",
            extra={"configured_value": str(configured_value)},
        )
        return WHITEBOARD_SNAPSHOT_DEFAULT_TTL_SECONDS
    return ttl_seconds


def refresh_whiteboard_redis_snapshot(whiteboard: WorkWhiteboard) -> None:
    key = whiteboard_snapshot_key(whiteboard)
    payload = whiteboard_payload(whiteboard, include_internal=True)
    payload["snapshot_source"] = "db"
    payload["snapshot_version"] = "work_whiteboard_v1"
    serialized = json.dumps(sanitize_outbox_payload(payload), sort_keys=True)
    ttl_seconds = whiteboard_snapshot_ttl_seconds()
    if key != whiteboard.redis_snapshot_key:
        WorkWhiteboard.objects.filter(id=whiteboard.id).update(redis_snapshot_key=key)
        whiteboard.redis_snapshot_key = key
    if not _use_cache_snapshot_store():
        try:
            redis_client = build_redis_client(
                db=int(
                    os.environ.get("WHITEBOARD_SNAPSHOT_REDIS_DB", os.environ.get("REDIS_DB", "0"))
                ),
                decode_responses=True,
            )
            redis_client.setex(key, ttl_seconds, serialized)
            return
        except Exception:
            pass
    cache.set(key, serialized, timeout=ttl_seconds)


def rebuild_whiteboard_snapshot_from_db(whiteboard_id: UUID | str) -> dict[str, Any] | None:
    whiteboard = _whiteboard_queryset().filter(id=whiteboard_id).first()
    if whiteboard is None:
        return None
    refresh_whiteboard_redis_snapshot(whiteboard)
    return whiteboard_payload(whiteboard, include_internal=True)


def _active_whiteboard_for(
    *,
    company: Graph,
    source_message: CommunicationMessage | None,
    service_engagement: ServiceEngagement | None,
) -> WorkWhiteboard | None:
    queryset = (
        _whiteboard_queryset()
        .filter(company=company)
        .filter(
            Q(status__in=ACTIVE_WHITEBOARD_STATUSES) | Q(work_status__in=ACTIVE_WORKBOARD_STATUSES)
        )
    )
    if source_message is not None:
        by_message = queryset.filter(source_message=source_message).first()
        if by_message is not None:
            return by_message
        by_thread = queryset.filter(communication_thread=source_message.thread).first()
        if by_thread is not None:
            return by_thread
    if service_engagement is not None:
        by_service = queryset.filter(service_engagement=service_engagement).first()
        if by_service is not None:
            return by_service
    return None


def _ensure_onboarding_department(
    *,
    company: Graph,
    slug: str,
    name: str,
    department_type: str,
) -> DepartmentRegistry:
    organization = company.organization
    if organization is None:
        raise WorkWhiteboardError(
            "company_organization_required",
            "Whiteboard onboarding requires the company to belong to an organization.",
        )
    return register_department(
        organization=organization,
        slug=slug,
        name=name,
        department_type=department_type,
        service_tags=["onboarding", "whiteboard"],
        metadata={"system_managed": True, "source": "request_router"},
    )


def _whiteboard_queryset() -> QuerySet[WorkWhiteboard]:
    return WorkWhiteboard.objects.select_related(
        "organization",
        "company",
        "service_engagement",
        "communication_thread",
        "source_message",
    )


def _use_cache_snapshot_store() -> bool:
    default_cache = settings.CACHES.get("default", {})
    backend = str(default_cache.get("BACKEND", "")).lower()
    return "locmem" in backend


def _routing_records_for_whiteboard(whiteboard: WorkWhiteboard) -> QuerySet[TaskRoutingRecord]:
    return TaskRoutingRecord.objects.filter(
        company=whiteboard.company,
        metadata_json__whiteboard_id=str(whiteboard.id),
    ).select_related("to_department")


def _can_mutate_whiteboard(*, user: User, whiteboard: WorkWhiteboard) -> bool:
    return has_company_access(user, whiteboard.company, "member") and has_min_role(
        user,
        "member",
        str(whiteboard.organization_id),
    )


def _can_view_internal(*, user: User | None, whiteboard: WorkWhiteboard) -> bool:
    if user is None:
        return False
    return has_company_access(user, whiteboard.company, "member") and has_min_role(
        user,
        "member",
        str(whiteboard.organization_id),
    )


def whiteboard_semantic_aliases(whiteboard: WorkWhiteboard) -> dict[str, Any]:
    return {
        "work_status": {
            "legacy_field": "status",
            "legacy_value": whiteboard.status,
            "value": effective_work_status_for_whiteboard(whiteboard),
        },
        "project_name": {
            "legacy_field": "client_name",
            "legacy_value": whiteboard.client_name,
            "value": whiteboard.project_name or whiteboard.client_name,
        },
        "stakeholder_context": {
            "legacy_field": "target_audience",
            "legacy_value": _dict(whiteboard.target_audience_json),
        },
        "resource_context": {
            "legacy_fields": ["product_context", "brand_context"],
            "legacy_value": {
                "product_context": _dict(whiteboard.product_context_json),
                "brand_context": _dict(whiteboard.brand_context_json),
            },
        },
        "delivery_context": {
            "legacy_field": "channel_context",
            "legacy_value": _dict(whiteboard.channel_context_json),
        },
        "work_missing_fields": {
            "legacy_field": "missing_fields",
            "legacy_value": list(whiteboard.missing_fields_json or []),
            "mapped_from_legacy": _work_missing_fields_from_legacy(whiteboard.missing_fields_json),
        },
    }


def _workboard_context_from_data(
    *,
    data: dict[str, Any],
    company: Graph,
    default_status: str,
    default_work_status: str,
) -> dict[str, Any]:
    if "work_status" in data:
        work_status = normalize_work_status(str(data.get("work_status") or ""))
        status = legacy_status_for_work_status(work_status)
    else:
        status = str(data.get("status") or default_status)
        work_status = work_status_for_legacy_status(status) or default_work_status
    if not work_status:
        work_status = default_work_status
    project_name = str(data.get("project_name") or data.get("client_name") or company.name or "")[
        :255
    ]
    stakeholder_context = (
        _dict(data.get("stakeholder_context"))
        if "stakeholder_context" in data
        else _dict(data.get("target_audience"))
    )
    target_audience = (
        stakeholder_context if "stakeholder_context" in data else _dict(data.get("target_audience"))
    )
    if "resource_context" in data:
        resource_context = _dict(data.get("resource_context"))
        product_context = _legacy_product_context_from_resource(resource_context)
        brand_context = _legacy_brand_context_from_resource(resource_context)
    else:
        product_context = _dict(data.get("product_context"))
        brand_context = _dict(data.get("brand_context"))
        resource_context = _resource_context_from_legacy(
            product_context=product_context,
            brand_context=brand_context,
        )
    delivery_context = (
        _dict(data.get("delivery_context"))
        if "delivery_context" in data
        else _dict(data.get("channel_context"))
    )
    channel_context = (
        delivery_context if "delivery_context" in data else _dict(data.get("channel_context"))
    )
    return {
        "status": status,
        "work_status": work_status,
        "project_name": project_name,
        "client_name": project_name,
        "constraints": _dict(data.get("constraints")),
        "stakeholder_context": stakeholder_context,
        "target_audience": target_audience,
        "resource_context": resource_context,
        "product_context": product_context,
        "brand_context": brand_context,
        "delivery_context": delivery_context,
        "channel_context": channel_context,
    }


def _resource_context_from_legacy(
    *,
    product_context: Any,
    brand_context: Any,
) -> dict[str, Any]:
    resource_context = _dict(product_context)
    brand = _dict(brand_context)
    if brand:
        resource_context["brand_context"] = brand
    return resource_context


def _legacy_product_context_from_resource(resource_context: Any) -> dict[str, Any]:
    resource = _dict(resource_context)
    nested = _dict(resource.get("product_context"))
    if nested:
        return nested
    product_context = dict(resource)
    product_context.pop("brand_context", None)
    return product_context


def _legacy_brand_context_from_resource(resource_context: Any) -> dict[str, Any]:
    resource = _dict(resource_context)
    return _dict(resource.get("brand_context"))


def _work_missing_fields_from_legacy(value: Any) -> list[str]:
    mapped = {
        LEGACY_MISSING_FIELD_TO_WORK_FIELD.get(str(field), str(field)) for field in _list(value)
    }
    return [field for field in WORKBOARD_REQUIRED_FIELDS if field in mapped]


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _has_any(value: dict[str, Any], keys: list[str]) -> bool:
    return any(bool(value.get(key)) for key in keys)


def _truncate(value: str, limit: int) -> str:
    return value.strip().replace("\x00", "")[:limit]


def _extract_budget(body: str) -> str:
    match = re.search(r"(?i)(?:budget\s*(?:is|of|:)?\s*)?(\$[\d,]+(?:\.\d{2})?)", body)
    return match.group(1)[:120] if match else ""


def _extract_timeline(body: str) -> str:
    patterns = [
        r"(?i)\bby\s+([A-Za-z]+\s+\d{1,2}(?:,\s*\d{4})?)",
        r"(?i)\b(next\s+(?:week|month|quarter))\b",
        r"(?i)\b(in\s+\d+\s+(?:days|weeks|months))\b",
        r"(?i)\b(tomorrow|today)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, body)
        if match:
            return match.group(1)[:255]
    return ""


def _extract_offer(body: str) -> str:
    match = re.search(r"(?i)\b(?:for|promote|launch)\s+([^.\n]{4,120})", body)
    return match.group(1).strip()[:255] if match else ""
