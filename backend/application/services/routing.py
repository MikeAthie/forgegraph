"""Backend-owned department routing service."""

from __future__ import annotations

from datetime import timedelta
from typing import Any, cast
from uuid import UUID

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from application.services.communications import CommunicationError, create_message, create_thread
from application.services.company_access import accessible_company_queryset, has_company_access
from application.services.departments import (
    active_department_membership,
    can_mutate_department_work,
    has_department_role,
    is_department_admin,
)
from application.services.domain_event_outbox import sanitize_outbox_payload
from application.services.domain_events import record_domain_event
from application.services.task_lifecycle import assign_lifecycle_task_department
from infrastructure.orm.models import (
    ApprovalTask,
    CommunicationEventReceipt,
    CommunicationMessage,
    CommunicationThread,
    CompanySignal,
    DepartmentMembership,
    DepartmentRegistry,
    Graph,
    Organization,
    OrganizationMembership,
    RoutingPolicy,
    Run,
    ServiceEngagement,
    TaskLifecycleRecord,
    TaskRecord,
    TaskRoutingRecord,
    User,
)

ROUTING_EVENT_SCHEMA_VERSION = "routing_event_v1"
ROUTING_OUTBOX_TOPIC = "forgegraph.routing.events.v1"
DEFAULT_UNROUTED_DEPARTMENT_SLUG = "unrouted"
ROUTING_RECORD_STATUSES = {choice[0] for choice in TaskRoutingRecord.STATUS_CHOICES}
ROUTING_PRIORITIES = {choice[0] for choice in TaskRoutingRecord.PRIORITY_CHOICES}


class RoutingError(ValueError):
    """Domain error for department routing operations."""

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


def routing_policy_payload(policy: RoutingPolicy) -> dict[str, Any]:
    return {
        "id": str(policy.id),
        "organization_id": str(policy.organization_id),
        "company_id": str(policy.company_id) if policy.company_id else None,
        "department_id": str(policy.department_id),
        "trigger_type": policy.trigger_type,
        "event_type": policy.event_type,
        "service_type": policy.service_type,
        "channel": policy.channel,
        "signal_type": policy.signal_type,
        "entry_conditions": dict(policy.entry_conditions_json or {}),
        "priority_rules": dict(policy.priority_rules_json or {}),
        "sla": dict(policy.sla_json or {}),
        "required_approval_types": list(policy.required_approval_types_json or []),
        "fallback_department_id": (
            str(policy.fallback_department_id) if policy.fallback_department_id else None
        ),
        "active": policy.active,
        "metadata": dict(policy.metadata_json or {}),
        "created_by_id": str(policy.created_by_id) if policy.created_by_id else None,
        "created_at": policy.created_at.isoformat(),
        "updated_at": policy.updated_at.isoformat(),
    }


def routing_record_payload(record: TaskRoutingRecord) -> dict[str, Any]:
    task_lifecycle = record.task_lifecycle
    run_id = None
    if task_lifecycle is not None:
        run_id = str(task_lifecycle.run_id)
    elif record.operation_id:
        run_id = str(record.operation_id)
    return {
        "id": str(record.id),
        "organization_id": str(record.organization_id),
        "company_id": str(record.company_id),
        "task_lifecycle_id": str(record.task_lifecycle_id) if record.task_lifecycle_id else None,
        "task_record_id": _task_record_id_for_lifecycle(record.task_lifecycle_id),
        "run_id": run_id,
        "operation_id": str(record.operation_id) if record.operation_id else run_id,
        "communication_thread_id": (
            str(record.communication_thread_id) if record.communication_thread_id else None
        ),
        "communication_message_id": (
            str(record.communication_message_id) if record.communication_message_id else None
        ),
        "service_engagement_id": (
            str(record.service_engagement_id) if record.service_engagement_id else None
        ),
        "approval_task_id": str(record.approval_task_id) if record.approval_task_id else None,
        "company_signal_id": str(record.company_signal_id) if record.company_signal_id else None,
        "from_department_id": (
            str(record.from_department_id) if record.from_department_id else None
        ),
        "department_id": str(record.to_department_id),
        "department_name": record.to_department.name,
        "to_department_id": str(record.to_department_id),
        "to_department_name": record.to_department.name,
        "assigned_user_id": str(record.assigned_user_id) if record.assigned_user_id else None,
        "reason": record.reason,
        "status": record.status,
        "priority": record.priority,
        "due_at": record.due_at.isoformat() if record.due_at else None,
        "sla_breached_at": record.sla_breached_at.isoformat() if record.sla_breached_at else None,
        "resolution": dict(record.resolution_json or {}),
        "idempotency_key": record.idempotency_key,
        "metadata": dict(record.metadata_json or {}),
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
    }


def resolve_routing_policy(
    *,
    company: Graph,
    trigger_type: str = "",
    event_type: str = "",
    service_type: str = "",
    channel: str = "",
    signal_type: str = "",
) -> RoutingPolicy | None:
    """Resolve the active routing policy, preferring company scope over organization scope."""

    for company_filter in (Q(company=company), Q(company__isnull=True)):
        candidates = _policy_candidates(
            company=company,
            company_filter=company_filter,
            trigger_type=trigger_type,
            event_type=event_type,
            service_type=service_type,
            channel=channel,
            signal_type=signal_type,
        )
        if candidates:
            return candidates[0]
    return None


def resolve_department_for_work(
    *,
    company: Graph,
    trigger_type: str = "",
    event_type: str = "",
    service_type: str = "",
    channel: str = "",
    signal_type: str = "",
) -> DepartmentRegistry | None:
    policy = resolve_routing_policy(
        company=company,
        trigger_type=trigger_type,
        event_type=event_type,
        service_type=service_type,
        channel=channel,
        signal_type=signal_type,
    )
    if policy is not None:
        return policy.department
    return _default_traffic_department(company)


def register_department(
    *,
    organization: Organization,
    slug: str,
    name: str,
    department_type: str = "",
    lead_user: User | None = None,
    service_tags: list[str] | None = None,
    active: bool = True,
    metadata: dict[str, Any] | None = None,
) -> DepartmentRegistry:
    """Create or update an organization-scoped department registry row."""

    slug = str(slug or "").strip()
    name = str(name or "").strip()
    if not slug or not name:
        raise RoutingError(
            "department_required",
            "Department slug and name are required.",
        )
    if (
        lead_user is not None
        and not OrganizationMembership.objects.filter(
            organization=organization,
            user=lead_user,
        ).exists()
    ):
        raise RoutingError(
            "lead_user_not_in_organization",
            "Department lead must belong to the department organization.",
        )
    department, _created = DepartmentRegistry.objects.update_or_create(
        organization=organization,
        slug=slug,
        defaults={
            "name": name,
            "department_type": str(department_type or "")[:64],
            "lead_user": lead_user,
            "service_tags_json": list(service_tags or []),
            "active": bool(active),
            "metadata_json": sanitize_outbox_payload(metadata or {}),
        },
    )
    department.full_clean()
    department.save()
    return department


def create_or_update_routing_policy(
    *,
    organization: Organization,
    department: DepartmentRegistry,
    company: Graph | None = None,
    trigger_type: str = "",
    event_type: str = "",
    service_type: str = "",
    channel: str = "",
    signal_type: str = "",
    entry_conditions: dict[str, Any] | None = None,
    priority_rules: dict[str, Any] | None = None,
    sla: dict[str, Any] | None = None,
    required_approval_types: list[str] | None = None,
    fallback_department: DepartmentRegistry | None = None,
    active: bool = True,
    metadata: dict[str, Any] | None = None,
    created_by: User | None = None,
) -> RoutingPolicy:
    """Create or update a backend-owned routing policy for generic events/work."""

    if company is not None and company.organization_id != organization.id:
        raise RoutingError(
            "company_organization_mismatch",
            "Routing policy company must belong to the policy organization.",
        )
    if department.organization_id != organization.id:
        raise RoutingError(
            "department_organization_mismatch",
            "Routing policy department must belong to the policy organization.",
        )
    if fallback_department is not None and fallback_department.organization_id != organization.id:
        raise RoutingError(
            "fallback_department_organization_mismatch",
            "Routing policy fallback department must belong to the policy organization.",
        )
    lookup = {
        "organization": organization,
        "company": company,
        "trigger_type": str(trigger_type or "")[:128],
        "event_type": str(event_type or "")[:128],
        "service_type": str(service_type or "")[:80],
        "channel": str(channel or "")[:64],
        "signal_type": str(signal_type or "")[:64],
    }
    policy = RoutingPolicy.objects.filter(**lookup).order_by("-updated_at").first()
    if policy is None:
        policy = RoutingPolicy(**lookup, created_by=created_by)
    policy.department = department
    policy.fallback_department = fallback_department
    policy.entry_conditions_json = sanitize_outbox_payload(entry_conditions or {})
    policy.priority_rules_json = sanitize_outbox_payload(priority_rules or {})
    policy.sla_json = sanitize_outbox_payload(sla or {})
    policy.required_approval_types_json = list(required_approval_types or [])
    policy.active = bool(active)
    policy.metadata_json = sanitize_outbox_payload(metadata or {})
    if policy.created_by_id is None:
        policy.created_by = created_by
    policy.full_clean()
    policy.save()
    return policy


def route_event(
    *,
    company: Graph,
    event_type: str,
    user: User | None = None,
    trigger_type: str = "",
    service_type: str = "",
    channel: str = "",
    signal_type: str = "",
    communication_thread: CommunicationThread | None = None,
    communication_message: CommunicationMessage | None = None,
    service_engagement: ServiceEngagement | None = None,
    operation: Run | None = None,
    approval_task: ApprovalTask | None = None,
    company_signal: CompanySignal | None = None,
    from_department: DepartmentRegistry | None = None,
    assigned_user: User | None = None,
    reason: str = "",
    status: str = "",
    priority: str = "",
    due_at: Any | None = None,
    idempotency_key: str = "",
    metadata: dict[str, Any] | None = None,
) -> TaskRoutingRecord:
    """Route a committed backend event to an internal department inbox."""

    if user is not None and not has_company_access(user, company, "member"):
        raise RoutingError(
            "permission_denied",
            "You do not have company access to route this work.",
        )
    policy = resolve_routing_policy(
        company=company,
        trigger_type=trigger_type or event_type,
        event_type=event_type,
        service_type=service_type,
        channel=channel,
        signal_type=signal_type,
    )
    department = policy.department if policy is not None else _default_traffic_department(company)
    route_status = _normalize_status(status or "queued")
    route_reason = str(reason or "Routed from committed backend event.")
    organization = _company_organization(company)
    if department is None:
        department = _ensure_unrouted_department(organization)
        route_status = "blocked"
        missing_policy_reason = (
            "No active routing policy or fallback department matched this event."
        )
        route_reason = (
            f"{route_reason} {missing_policy_reason}" if reason else missing_policy_reason
        )
    route_priority = _normalize_priority(priority or _priority_for_policy(policy, metadata or {}))
    key = str(idempotency_key or "").strip()
    if not key:
        key = _default_routing_idempotency_key(
            event_type=event_type,
            communication_message=communication_message,
            communication_thread=communication_thread,
            service_engagement=service_engagement,
            operation=operation,
            approval_task=approval_task,
            company_signal=company_signal,
        )
    if not key:
        raise RoutingError(
            "idempotency_key_required",
            "Routing generic events requires an idempotency key or linked durable target.",
        )
    record = _create_routing_record(
        organization=organization,
        company=company,
        department=department,
        from_department=from_department,
        assigned_user=assigned_user,
        communication_thread=communication_thread,
        communication_message=communication_message,
        service_engagement=service_engagement,
        operation=operation,
        approval_task=approval_task,
        company_signal=company_signal,
        reason=route_reason,
        status=route_status,
        priority=route_priority,
        due_at=due_at
        if due_at is not None
        else _due_at_for_policy(
            company=company,
            department=department,
            metadata={
                **(metadata or {}),
                "trigger_type": trigger_type or event_type,
                "event_type": event_type,
                "service_type": service_type,
                "channel": channel,
                "signal_type": signal_type,
            },
        ),
        idempotency_key=key,
        metadata={
            **sanitize_outbox_payload(metadata or {}),
            "event_type": event_type,
            "trigger_type": trigger_type or event_type,
        },
    )
    if getattr(record, "_routing_record_was_created", False):
        record_routing_event(record)
    return record


def route_event_to_department(
    *,
    company: Graph,
    department: DepartmentRegistry,
    event_type: str,
    user: User | None = None,
    trigger_type: str = "",
    communication_thread: CommunicationThread | None = None,
    communication_message: CommunicationMessage | None = None,
    service_engagement: ServiceEngagement | None = None,
    operation: Run | None = None,
    approval_task: ApprovalTask | None = None,
    company_signal: CompanySignal | None = None,
    from_department: DepartmentRegistry | None = None,
    assigned_user: User | None = None,
    task_lifecycle: TaskLifecycleRecord | None = None,
    reason: str = "",
    status: str = "",
    priority: str = "",
    due_at: Any | None = None,
    idempotency_key: str = "",
    metadata: dict[str, Any] | None = None,
) -> TaskRoutingRecord:
    """Route a committed backend event to an explicit organization department."""

    if department.organization_id != company.organization_id:
        raise RoutingError(
            "department_company_mismatch",
            "Target department belongs to a different organization than the company.",
        )
    if user is not None and not has_company_access(user, company, "member"):
        raise RoutingError(
            "permission_denied",
            "You do not have company access to route this work.",
        )
    if assigned_user is not None:
        _validate_assigned_user(
            assigned_user=assigned_user,
            department=department,
            company=company,
        )
    key = str(idempotency_key or "").strip()
    if not key:
        key = _default_routing_idempotency_key(
            event_type=event_type,
            communication_message=communication_message,
            communication_thread=communication_thread,
            service_engagement=service_engagement,
            operation=operation,
            approval_task=approval_task,
            company_signal=company_signal,
        )
    if not key:
        raise RoutingError(
            "idempotency_key_required",
            "Explicit event routing requires an idempotency key or linked durable target.",
        )
    sanitized_metadata = sanitize_outbox_payload(metadata or {})
    record = _create_routing_record(
        organization=_company_organization(company),
        company=company,
        department=department,
        from_department=from_department,
        assigned_user=assigned_user,
        task_lifecycle=task_lifecycle,
        communication_thread=communication_thread,
        communication_message=communication_message,
        service_engagement=service_engagement,
        operation=operation,
        approval_task=approval_task,
        company_signal=company_signal,
        reason=str(reason or "Routed from committed backend event."),
        status=_normalize_status(status or "queued"),
        priority=_normalize_priority(priority or str(sanitized_metadata.get("priority") or "")),
        due_at=due_at
        if due_at is not None
        else _due_at_for_policy(
            company=company,
            department=department,
            metadata={
                **sanitized_metadata,
                "trigger_type": trigger_type or event_type,
                "event_type": event_type,
            },
        ),
        idempotency_key=key,
        metadata={
            **sanitized_metadata,
            "event_type": event_type,
            "trigger_type": trigger_type or event_type,
        },
    )
    if getattr(record, "_routing_record_was_created", False):
        record_routing_event(record)
    return record


def route_communication_message(
    *,
    message: CommunicationMessage,
    user: User | None = None,
    idempotency_key: str = "",
    reason: str = "",
    metadata: dict[str, Any] | None = None,
) -> TaskRoutingRecord:
    """Route a committed communication message without mutating the message/thread."""

    if message.company is None:
        raise RoutingError(
            "company_required",
            "Communication message routing requires a company-scoped message.",
        )
    thread = message.thread
    source_metadata = _communication_routing_metadata(message=message, extra=metadata or {})
    return route_event(
        company=message.company,
        user=user,
        event_type="communication.message.created",
        trigger_type="communication.message.created",
        service_type=str(source_metadata.get("service_type") or thread.thread_type or ""),
        channel=str(source_metadata.get("channel") or ""),
        signal_type=str(source_metadata.get("signal_type") or ""),
        communication_thread=thread,
        communication_message=message,
        service_engagement=thread.service_engagement,
        operation=thread.operation,
        approval_task=thread.approval_task,
        reason=reason or "Routed communication message.",
        idempotency_key=idempotency_key or f"routing:communication-message:{message.id}",
        metadata=source_metadata,
    )


def route_communication_receipt(
    *,
    receipt: CommunicationEventReceipt,
    user: User | None = None,
) -> TaskRoutingRecord | None:
    """Feature-flagged bridge from a consumed receipt to backend-owned routing state."""

    if not bool(getattr(settings, "COMMUNICATION_ROUTING_FROM_KAFKA_ENABLED", False)):
        return None
    if receipt.status != "handled" or receipt.event_type != "communication.message.created":
        return None
    message_id = str((receipt.payload_json or {}).get("message_id") or "").strip()
    if not message_id:
        return None
    message = (
        CommunicationMessage.objects.select_related(
            "thread__service_engagement",
            "thread__operation",
            "thread__approval_task",
            "company",
            "organization",
        )
        .filter(id=message_id, company_id=receipt.company_id)
        .first()
    )
    if message is None:
        return None
    return route_communication_message(
        message=message,
        user=user,
        idempotency_key=f"routing:communication-receipt:{receipt.id}",
        metadata={"receipt_id": str(receipt.id), "consumer_group": receipt.consumer_group},
    )


def list_department_inbox(
    *,
    user: User,
    department_id: UUID | str | None = None,
    company_id: UUID | str | None = None,
    status: str = "",
) -> QuerySet[TaskRoutingRecord]:
    return list_inbox_for_user(
        user=user,
        department_id=department_id,
        company_id=company_id,
        status=status,
    )


def mark_routing_record_status(
    *,
    user: User,
    record: TaskRoutingRecord,
    status: str,
    resolution: dict[str, Any] | None = None,
    assigned_user: User | None = None,
) -> TaskRoutingRecord:
    """Update a routing inbox item without granting department-only company access."""

    if not can_mutate_department_work(
        user=user,
        company=record.company,
        department=record.to_department,
    ):
        raise RoutingError(
            "permission_denied",
            "You do not have permission to update this routing record.",
        )
    if assigned_user is not None:
        _validate_assigned_user(
            assigned_user=assigned_user,
            department=record.to_department,
            company=record.company,
        )
    record.status = _normalize_status(status)
    if resolution is not None:
        record.resolution_json = sanitize_outbox_payload(resolution)
    if assigned_user is not None:
        record.assigned_user = assigned_user
    record.full_clean()
    record.save(update_fields=["status", "resolution_json", "assigned_user", "updated_at"])
    return record


def list_inbox_for_user(
    *,
    user: User,
    department_id: UUID | str | None = None,
    company_id: UUID | str | None = None,
    status: str = "",
) -> QuerySet[TaskRoutingRecord]:
    companies = accessible_company_queryset(user, minimum_role="viewer")
    if company_id:
        companies = companies.filter(id=company_id)
    queryset = _routing_record_queryset().filter(company__in=companies)
    organization = user.default_organization
    if organization is None:
        return queryset.none()
    queryset = queryset.filter(organization=organization)
    if department_id:
        department = DepartmentRegistry.objects.filter(
            organization=organization,
            id=department_id,
        ).first()
        if department is None or not _can_view_inbox_department(user, department):
            return queryset.none()
        queryset = queryset.filter(to_department=department)
    elif not is_department_admin(user, organization):
        queryset = queryset.filter(
            to_department__memberships__in=_active_memberships_for_user(user)
        ).distinct()
    if status:
        queryset = queryset.filter(status=status)
    return queryset


def route_task(
    *,
    user: User,
    task: TaskRecord,
    to_department: DepartmentRegistry,
    from_department: DepartmentRegistry | None = None,
    assigned_user: User | None = None,
    reason: str = "",
    status: str = "queued",
    priority: str = "",
    idempotency_key: str = "",
    metadata: dict[str, Any] | None = None,
    resolution: dict[str, Any] | None = None,
    missing_capability: dict[str, Any] | None = None,
) -> TaskRoutingRecord:
    company = company_for_task(task)
    if to_department.organization_id != company.organization_id:
        raise RoutingError(
            "department_company_mismatch",
            "Target department belongs to a different organization than the task company.",
        )
    if not has_company_access(user, company, "member"):
        raise RoutingError(
            "permission_denied",
            "You do not have company access to route this task.",
        )
    source_department = from_department or task.department or _lifecycle_department(task)
    if (
        source_department is not None
        and source_department.organization_id != company.organization_id
    ):
        raise RoutingError(
            "department_company_mismatch",
            "Source department belongs to a different organization than the task company.",
        )
    if not _can_route_between(
        user=user,
        company=company,
        source_department=source_department,
        target_department=to_department,
    ):
        raise RoutingError(
            "permission_denied",
            "You must lead the source or target department to route this task.",
        )
    if assigned_user is not None:
        _validate_assigned_user(
            assigned_user=assigned_user,
            department=to_department,
            company=company,
        )

    if task.lifecycle_task_id is None:
        raise RoutingError(
            "lifecycle_task_required",
            "Department routing requires a backend-owned task lifecycle record.",
        )

    with transaction.atomic():
        lifecycle_task = TaskLifecycleRecord.objects.select_for_update().get(
            id=task.lifecycle_task_id
        )
        key = str(idempotency_key or "").strip()
        if not key:
            key = f"routing:task:{task.id}:{to_department.id}"
        record = _create_routing_record(
            organization=lifecycle_task.organization,
            company=company,
            department=to_department,
            from_department=source_department,
            assigned_user=assigned_user,
            task_lifecycle=lifecycle_task,
            operation=task.execution,
            reason=str(reason or "")[:4000],
            status=_normalize_status(status),
            priority=_normalize_priority(priority or str((metadata or {}).get("priority") or "")),
            due_at=_due_at_for_policy(
                company=company,
                department=to_department,
                metadata=metadata or {},
            ),
            resolution=resolution or {},
            idempotency_key=key,
            metadata=metadata or {},
        )
        assign_lifecycle_task_department(
            lifecycle_task=lifecycle_task,
            department=to_department,
        )
        TaskRecord.objects.filter(id=task.id).update(
            department=to_department,
            updated_at=timezone.now(),
        )
        signal = None
        was_created = getattr(record, "_routing_record_was_created", False)
        if missing_capability and was_created:
            signal = _create_missing_capability_signal(
                user=user,
                company=company,
                task=task,
                routing_record=record,
                missing_capability=missing_capability,
            )
            _record_missing_capability_note(
                user=user,
                company=company,
                task=task,
                routing_record=record,
                signal=signal,
                missing_capability=missing_capability,
            )
        if was_created:
            record_routing_event(record, missing_capability_signal=signal)
        return record


def company_for_task(task: TaskRecord) -> Graph:
    return task.execution.graph_version.graph


def record_routing_event(
    record: TaskRoutingRecord,
    *,
    missing_capability_signal: CompanySignal | None = None,
) -> None:
    payload = routing_record_payload(record)
    if missing_capability_signal is not None:
        payload["missing_capability_signal_id"] = str(missing_capability_signal.id)
    payload["schema_version"] = ROUTING_EVENT_SCHEMA_VERSION
    record_domain_event(
        organization=record.organization,
        aggregate_type="task_routing_record",
        aggregate_id=record.id,
        event_type="task.routing_created",
        event_version=1,
        idempotency_key=f"task-routing:{record.id}:created",
        payload=payload,
        outbox_topic=ROUTING_OUTBOX_TOPIC,
        outbox_schema_version=ROUTING_EVENT_SCHEMA_VERSION,
        outbox_payload=payload,
        outbox_visibility="operator",
        outbox_company=record.company,
    )


def _create_routing_record(
    *,
    organization: Organization,
    company: Graph,
    department: DepartmentRegistry,
    from_department: DepartmentRegistry | None = None,
    assigned_user: User | None = None,
    task_lifecycle: TaskLifecycleRecord | None = None,
    communication_thread: CommunicationThread | None = None,
    communication_message: CommunicationMessage | None = None,
    service_engagement: ServiceEngagement | None = None,
    operation: Run | None = None,
    approval_task: ApprovalTask | None = None,
    company_signal: CompanySignal | None = None,
    reason: str = "",
    status: str = "queued",
    priority: str = "normal",
    due_at: Any | None = None,
    resolution: dict[str, Any] | None = None,
    idempotency_key: str = "",
    metadata: dict[str, Any] | None = None,
) -> TaskRoutingRecord:
    key = str(idempotency_key or "").strip()
    if key:
        existing = (
            _routing_record_queryset()
            .filter(organization=organization, idempotency_key=key)
            .first()
        )
        if existing is not None:
            cast(Any, existing)._routing_record_was_created = False
            return existing
    record = TaskRoutingRecord(
        organization=organization,
        company=company,
        task_lifecycle=task_lifecycle,
        communication_thread=communication_thread,
        communication_message=communication_message,
        service_engagement=service_engagement,
        operation=operation,
        approval_task=approval_task,
        company_signal=company_signal,
        from_department=from_department,
        to_department=department,
        assigned_user=assigned_user,
        reason=str(reason or "")[:4000],
        status=_normalize_status(status),
        priority=_normalize_priority(priority),
        due_at=due_at,
        resolution_json=sanitize_outbox_payload(resolution or {}),
        idempotency_key=key,
        metadata_json=sanitize_outbox_payload(metadata or {}),
    )
    record.full_clean()
    try:
        record.save()
    except IntegrityError:
        if key:
            existing = (
                _routing_record_queryset()
                .filter(organization=organization, idempotency_key=key)
                .first()
            )
            if existing is not None:
                cast(Any, existing)._routing_record_was_created = False
                return existing
        raise
    cast(Any, record)._routing_record_was_created = True
    return record


def _policy_candidates(
    *,
    company: Graph,
    company_filter: Q,
    trigger_type: str,
    event_type: str,
    service_type: str,
    channel: str,
    signal_type: str,
) -> list[RoutingPolicy]:
    queryset = (
        RoutingPolicy.objects.filter(organization=_company_organization(company), active=True)
        .filter(company_filter)
        .filter(Q(trigger_type=trigger_type) | Q(trigger_type=""))
        .filter(Q(event_type=event_type) | Q(event_type=""))
        .filter(Q(service_type=service_type) | Q(service_type=""))
        .filter(Q(channel=channel) | Q(channel=""))
        .filter(Q(signal_type=signal_type) | Q(signal_type=""))
        .select_related("department", "fallback_department", "company", "organization")
    )
    return sorted(
        queryset,
        key=lambda policy: (
            bool(policy.trigger_type),
            bool(policy.event_type),
            bool(policy.service_type),
            bool(policy.channel),
            bool(policy.signal_type),
            policy.updated_at,
        ),
        reverse=True,
    )


def _default_traffic_department(company: Graph) -> DepartmentRegistry | None:
    return (
        DepartmentRegistry.objects.filter(
            organization=_company_organization(company),
            active=True,
        )
        .filter(Q(slug="traffic") | Q(department_type="traffic"))
        .order_by("slug")
        .first()
    )


def _routing_record_queryset() -> QuerySet[TaskRoutingRecord]:
    return TaskRoutingRecord.objects.select_related(
        "organization",
        "company",
        "task_lifecycle",
        "task_lifecycle__run",
        "communication_thread",
        "communication_message",
        "service_engagement",
        "operation",
        "approval_task",
        "company_signal",
        "from_department",
        "to_department",
        "assigned_user",
    )


def _can_view_inbox_department(user: User, department: DepartmentRegistry) -> bool:
    if is_department_admin(user, department.organization):
        return True
    return has_department_role(user, department, "viewer")


def _can_route_between(
    *,
    user: User,
    company: Graph,
    source_department: DepartmentRegistry | None,
    target_department: DepartmentRegistry,
) -> bool:
    if is_department_admin(user, _company_organization(company)):
        return True
    if can_mutate_department_work(user=user, company=company, department=target_department):
        return True
    return source_department is not None and can_mutate_department_work(
        user=user,
        company=company,
        department=source_department,
    )


def _validate_assigned_user(
    *,
    assigned_user: User,
    department: DepartmentRegistry,
    company: Graph,
) -> None:
    if not has_company_access(assigned_user, company, "viewer"):
        raise RoutingError(
            "assigned_user_company_access_required",
            "Assigned user must have access to the task company.",
        )
    if active_department_membership(user=assigned_user, department=department) is None:
        raise RoutingError(
            "assigned_user_department_member_required",
            "Assigned user must belong to the target department.",
        )


def _due_at_for_policy(
    *,
    company: Graph,
    department: DepartmentRegistry,
    metadata: dict[str, Any],
) -> Any:
    target_minutes = metadata.get("sla_minutes")
    if target_minutes is None:
        policy = resolve_routing_policy(
            company=company,
            trigger_type=str(metadata.get("trigger_type") or ""),
            event_type=str(metadata.get("event_type") or ""),
            service_type=str(metadata.get("service_type") or ""),
            channel=str(metadata.get("channel") or ""),
            signal_type=str(metadata.get("signal_type") or ""),
        )
        if policy is not None and policy.department_id == department.id:
            sla_json = policy.sla_json if isinstance(policy.sla_json, dict) else {}
            target_minutes = sla_json.get("target_minutes")
    if target_minutes is None:
        return None
    try:
        minutes = int(target_minutes)
    except (TypeError, ValueError):
        return None
    if minutes <= 0:
        return None
    return timezone.now() + timedelta(minutes=minutes)


def _lifecycle_department(task: TaskRecord) -> DepartmentRegistry | None:
    if task.lifecycle_task_id is None:
        return None
    if task.lifecycle_task is None:
        return None
    return task.lifecycle_task.current_department


def _active_memberships_for_user(user: User) -> QuerySet[DepartmentMembership]:
    now = timezone.now()
    return (
        DepartmentMembership.objects.filter(user=user, status="active")
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
        .select_related("department")
    )


def _task_record_id_for_lifecycle(lifecycle_id: UUID | str | None) -> str | None:
    if not lifecycle_id:
        return None
    try:
        lifecycle_uuid = lifecycle_id if isinstance(lifecycle_id, UUID) else UUID(str(lifecycle_id))
    except ValueError:
        return None
    task_id = (
        TaskRecord.objects.filter(lifecycle_task_id=lifecycle_uuid)
        .order_by("-updated_at")
        .values_list("id", flat=True)
        .first()
    )
    return str(task_id) if task_id else None


def _ensure_unrouted_department(organization: Organization) -> DepartmentRegistry:
    department, _created = DepartmentRegistry.objects.get_or_create(
        organization=organization,
        slug=DEFAULT_UNROUTED_DEPARTMENT_SLUG,
        defaults={
            "name": "Unrouted",
            "department_type": "routing_fallback",
            "service_tags_json": ["routing"],
            "active": True,
            "metadata_json": {"system_managed": True},
        },
    )
    return department


def _company_organization(company: Graph) -> Organization:
    organization = company.organization
    if organization is None:
        raise RoutingError(
            "company_organization_required",
            "Routing requires the company to belong to an organization.",
        )
    return organization


def _normalize_status(value: str) -> str:
    status = str(value or "queued").strip()
    return status if status in ROUTING_RECORD_STATUSES else "queued"


def _normalize_priority(value: str) -> str:
    priority = str(value or "normal").strip()
    return priority if priority in ROUTING_PRIORITIES else "normal"


def _priority_for_policy(policy: RoutingPolicy | None, metadata: dict[str, Any]) -> str:
    explicit_priority = str(metadata.get("priority") or "").strip()
    if explicit_priority:
        return explicit_priority
    if policy is None or not isinstance(policy.priority_rules_json, dict):
        return "normal"
    default_priority = str(policy.priority_rules_json.get("default") or "").strip()
    return default_priority or "normal"


def _default_routing_idempotency_key(
    *,
    event_type: str,
    communication_message: CommunicationMessage | None,
    communication_thread: CommunicationThread | None,
    service_engagement: ServiceEngagement | None,
    operation: Run | None,
    approval_task: ApprovalTask | None,
    company_signal: CompanySignal | None,
) -> str:
    if communication_message is not None:
        return f"routing:{event_type}:message:{communication_message.id}"
    if communication_thread is not None:
        return f"routing:{event_type}:thread:{communication_thread.id}"
    if service_engagement is not None:
        return f"routing:{event_type}:service-engagement:{service_engagement.id}"
    if operation is not None:
        return f"routing:{event_type}:operation:{operation.id}"
    if approval_task is not None:
        return f"routing:{event_type}:approval:{approval_task.id}"
    if company_signal is not None:
        return f"routing:{event_type}:signal:{company_signal.id}"
    return ""


def _communication_routing_metadata(
    *,
    message: CommunicationMessage,
    extra: dict[str, Any],
) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    thread_metadata = (
        message.thread.metadata_json if isinstance(message.thread.metadata_json, dict) else {}
    )
    message_metadata = message.metadata_json if isinstance(message.metadata_json, dict) else {}
    metadata.update(thread_metadata)
    metadata.update(message_metadata)
    metadata.update(extra)
    metadata.setdefault("visibility", message.visibility)
    metadata.setdefault("message_kind", message.message_kind)
    metadata.setdefault("thread_type", message.thread.thread_type)
    if message.thread.service_engagement_id:
        metadata.setdefault("service_engagement_id", str(message.thread.service_engagement_id))
        catalog_item = getattr(message.thread.service_engagement, "catalog_item", None)
        if catalog_item is not None:
            metadata.setdefault("service_type", catalog_item.slug)
    return sanitize_outbox_payload(metadata)


def _create_missing_capability_signal(
    *,
    user: User,
    company: Graph,
    task: TaskRecord,
    routing_record: TaskRoutingRecord,
    missing_capability: dict[str, Any],
) -> CompanySignal:
    channel = str(missing_capability.get("channel") or "").strip()[:64]
    capability = str(missing_capability.get("capability") or channel or "connector").strip()
    external_key = str(missing_capability.get("external_key") or "").strip()
    if not external_key:
        external_key = f"routing:{task.id}:{routing_record.id}:missing-capability"
    signal, created = CompanySignal.objects.get_or_create(
        company=company,
        source="department_routing",
        external_key=external_key,
        defaults={
            "organization": _company_organization(company),
            "created_by": user,
            "signal_type": "manual",
            "signal_kind": "capability_gap",
            "domain_context": "routing",
            "status": "new",
            "title": str(
                missing_capability.get("title") or f"Missing execution capability: {capability}"
            )[:255],
            "summary": str(
                missing_capability.get("summary")
                or "Execution is blocked until the required connector is configured."
            ),
            "channel": channel,
            "operation": task.execution,
            "metadata_json": {
                "task_record_id": str(task.id),
                "task_lifecycle_id": str(task.lifecycle_task_id),
                "routing_record_id": str(routing_record.id),
                "execution_status": "blocked_until_missing_capabilities_resolved",
                "missing_capability": capability,
            },
        },
    )
    if not created and (
        signal.signal_kind != "capability_gap" or signal.domain_context != "routing"
    ):
        signal.signal_kind = "capability_gap"
        signal.domain_context = "routing"
        signal.save(update_fields=["signal_kind", "domain_context", "updated_at"])
    return signal


def _record_missing_capability_note(
    *,
    user: User,
    company: Graph,
    task: TaskRecord,
    routing_record: TaskRoutingRecord,
    signal: CompanySignal,
    missing_capability: dict[str, Any],
) -> None:
    thread = create_thread(
        company=company,
        user=user,
        data={
            "title": str(missing_capability.get("thread_title") or "Missing execution capability"),
            "thread_type": "capability_gap",
            "visibility_mode": "operator",
            "operation_id": task.execution_id,
            "source_key": f"routing:{routing_record.id}:capability-gap",
            "metadata": {
                "routing_record_id": str(routing_record.id),
                "task_record_id": str(task.id),
            },
        },
    )
    thread.department = routing_record.to_department
    thread.save(update_fields=["department", "updated_at"])
    try:
        create_message(
            thread=thread,
            sender_kind="system",
            sender_organization=_company_organization(company),
            message_kind="capability_gap",
            body=str(
                missing_capability.get("internal_note")
                or "Execution remains blocked until the required connector is configured."
            ),
            body_format="plain",
            visibility="internal",
            idempotency_key=f"routing:{routing_record.id}:missing-capability-note",
            metadata={
                "routing_record_id": str(routing_record.id),
                "signal_id": str(signal.id),
            },
            attachments=[{"type": "company_signal", "id": str(signal.id)}],
        )
    except CommunicationError as exc:
        raise RoutingError(exc.code, exc.message, details=exc.details) from exc
