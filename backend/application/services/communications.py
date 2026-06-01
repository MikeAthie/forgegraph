"""Backend-owned communication thread, message, and attachment services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from application.services.audit_log import record_audit_log
from application.services.company_access import accessible_company_queryset, has_company_access
from application.services.domain_events import record_domain_event
from application.services.rbac import has_min_role
from application.services.redaction import redact_payload
from infrastructure.orm.models import (
    AgentRegistryEntry,
    ApprovalTask,
    Asset,
    AssetVersion,
    CommunicationAttachment,
    CommunicationMessage,
    CommunicationThread,
    CompanySignal,
    DecisionRecord,
    DepartmentRegistry,
    EvaluationRun,
    Graph,
    InteractionEventRecord,
    Organization,
    ReportRun,
    RequestClassificationRecord,
    Run,
    ServiceDeliverable,
    ServiceEngagement,
    ToolExecution,
    User,
    WorkWhiteboard,
)

COMMUNICATION_EVENT_SCHEMA_VERSION = "communication_event_v1"
COMMUNICATION_OUTBOX_TOPIC = "forgegraph.communication.events.v1"
INTERACTION_EVENT_RECORD_SUITABILITY_NOTE = (
    "InteractionEventRecord is operating-brief mutation history with raw_input, delta_json, "
    "brief sequence, and user/system actors. It is not a durable permissioned communication "
    "thread with message visibility, participants, attachments, or customer/operator filtering."
)

_DROPPED_METADATA_KEYS = {
    "secret",
    "secrets",
    "credential",
    "credentials",
    "provider_credentials",
    "private_config",
    "raw_private_config",
    "raw_prompt",
    "prompt",
    "prompts",
    "chain_of_thought",
    "cot",
    "reasoning_trace",
    "raw_evidence",
    "evidence_bundle",
    "evidence_bundles",
    "debug",
    "debug_trace",
    "debug_traces",
    "trace",
    "traces",
    "pack_manifest",
    "manifest",
    "namespace_claim",
    "namespace_claims",
    "smtp_config",
    "provider_config",
    "token",
    "tokens",
}

_PUBLIC_ATTACHMENT_TARGETS = {
    "artifact",
    "artifact_revision",
    "report_run",
    "service_engagement",
    "service_deliverable",
}


class CommunicationError(Exception):
    """Domain error for communication services."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or []


@dataclass(frozen=True)
class AttachmentRef:
    type: str
    id: UUID | str
    metadata: dict[str, Any] | None = None


def list_threads_for_user(
    *,
    user: User,
    company_id: UUID | str | None = None,
    status: str = "",
    service_engagement_id: UUID | str | None = None,
    operation_id: UUID | str | None = None,
) -> QuerySet[CommunicationThread]:
    companies = accessible_company_queryset(user, minimum_role="viewer")
    operator_companies = (
        accessible_company_queryset(user, minimum_role="member")
        if has_min_role(user, "member")
        else Graph.objects.none()
    )
    queryset = (
        _thread_queryset()
        .filter(company__in=companies)
        .filter(Q(visibility_mode__in=["customer", "mixed"]) | Q(company__in=operator_companies))
    )
    if company_id:
        queryset = queryset.filter(company_id=cast(UUID, company_id))
    if status:
        queryset = queryset.filter(status=status)
    if service_engagement_id:
        queryset = queryset.filter(service_engagement_id=cast(UUID, service_engagement_id))
    if operation_id:
        queryset = queryset.filter(operation_id=cast(UUID, operation_id))
    return queryset


def get_thread_for_user(
    *,
    user: User,
    thread_id: UUID | str,
) -> CommunicationThread | None:
    thread = _thread_queryset().filter(id=thread_id).first()
    if thread is None or not can_read_thread(user=user, thread=thread):
        return None
    return thread


def create_thread(
    *,
    company: Graph,
    user: User,
    data: dict[str, Any],
) -> CommunicationThread:
    visibility_mode = str(data.get("visibility_mode") or "mixed")
    if visibility_mode in {"operator", "internal"} and not is_operator_for_company(
        user=user, company=company
    ):
        raise CommunicationError(
            "permission_denied",
            "You do not have permission to create operator/internal communication threads.",
        )
    if not has_company_access(user, company, "viewer"):
        raise CommunicationError(
            "company_not_found",
            "Company was not found or you do not have access.",
        )

    source_key = str(data.get("source_key") or "").strip()
    if source_key:
        existing = _thread_queryset().filter(company=company, source_key=source_key).first()
        if existing is not None:
            return existing

    linked = _resolve_thread_links(company=company, data=data)
    with transaction.atomic():
        thread = CommunicationThread(
            organization=company.organization,
            company=company,
            service_engagement=linked.get("service_engagement"),
            operation=linked.get("operation"),
            approval_task=linked.get("approval_task"),
            artifact=linked.get("artifact"),
            report_run=linked.get("report_run"),
            department=linked.get("department"),
            title=str(data.get("title") or "").strip()[:255],
            thread_type=str(data.get("thread_type") or "support"),
            visibility_mode=visibility_mode,
            status=str(data.get("status") or "open"),
            source_key=source_key,
            created_by_user=user,
            metadata_json=sanitize_metadata(data.get("metadata") or {}),
        )
        thread.full_clean()
        thread.save()
        record_audit_log(
            actor=user,
            tenant_id=str(thread.organization_id),
            action="communication.thread.created",
            resource_type="communication_thread",
            resource_id=str(thread.id),
            metadata={
                "company_id": str(thread.company_id) if thread.company_id else "",
                "thread_type": thread.thread_type,
                "visibility_mode": thread.visibility_mode,
            },
        )
        record_communication_event(
            event_type="communication.thread.created",
            aggregate_type="communication_thread",
            aggregate_id=thread.id,
            organization=thread.organization,
            company=thread.company,
            payload=_thread_event_payload(thread),
            idempotency_key=f"communication-thread:{thread.id}:created",
        )
        return thread


def list_messages_for_user(
    *,
    user: User,
    thread: CommunicationThread,
) -> QuerySet[CommunicationMessage]:
    if not can_read_thread(user=user, thread=thread):
        return _message_queryset().none()
    queryset = _message_queryset().filter(thread=thread)
    if not is_operator_for_company(user=user, company=thread.company):
        queryset = queryset.filter(visibility="customer")
    return queryset


def create_message(
    *,
    thread: CommunicationThread,
    message_kind: str,
    body: str,
    body_format: str = "plain",
    visibility: str = "customer",
    idempotency_key: str = "",
    metadata: dict[str, Any] | None = None,
    sender_user: User | None = None,
    sender_agent: AgentRegistryEntry | None = None,
    sender_company: Graph | None = None,
    sender_organization: Organization | None = None,
    sender_kind: str = "user",
    attachments: list[AttachmentRef | dict[str, Any]] | None = None,
) -> CommunicationMessage:
    idempotency_key = str(idempotency_key or "").strip()[:255]
    if sender_kind in {"agent", "system"} and not idempotency_key:
        raise CommunicationError(
            "idempotency_key_required",
            "Agent and system messages require an idempotency key.",
        )
    _validate_service_sender_context(
        thread=thread,
        sender_kind=sender_kind,
        sender_agent=sender_agent,
        sender_organization=sender_organization,
    )
    if sender_user is not None and not can_create_message(
        user=sender_user,
        thread=thread,
        visibility=visibility,
    ):
        raise CommunicationError(
            "permission_denied",
            "You do not have permission to create this communication message.",
        )
    if idempotency_key:
        existing = (
            _message_queryset()
            .filter(thread=thread, idempotency_key=idempotency_key)
            .order_by("created_at")
            .first()
        )
        if existing is not None:
            return existing

    with transaction.atomic():
        message = CommunicationMessage(
            thread=thread,
            organization=thread.organization,
            company=thread.company,
            sender_kind=sender_kind,
            sender_user=sender_user,
            sender_agent=sender_agent,
            sender_company=sender_company,
            sender_organization=sender_organization,
            message_kind=message_kind,
            body=str(body or ""),
            body_format=body_format,
            visibility=visibility,
            idempotency_key=idempotency_key,
            metadata_json=sanitize_metadata(metadata or {}),
        )
        message.full_clean()
        message.save()
        thread.save(update_fields=["updated_at"])
        record_audit_log(
            actor=sender_user,
            tenant_id=str(message.organization_id),
            action="communication.message.created",
            resource_type="communication_message",
            resource_id=str(message.id),
            metadata={
                "thread_id": str(thread.id),
                "company_id": str(message.company_id) if message.company_id else "",
                "visibility": message.visibility,
                "sender_kind": message.sender_kind,
                "message_kind": message.message_kind,
            },
        )
        record_communication_event(
            event_type="communication.message.created",
            aggregate_type="communication_message",
            aggregate_id=message.id,
            organization=message.organization,
            company=message.company,
            payload=_message_event_payload(message),
            idempotency_key=f"communication-message:{message.id}:created",
        )
        if attachments:
            _create_attachments(
                message=message,
                refs=[_coerce_attachment_ref(ref) for ref in attachments],
                actor=sender_user,
            )
        return message


def attach_objects_to_message(
    *,
    user: User,
    message: CommunicationMessage,
    attachments: list[AttachmentRef | dict[str, Any]],
) -> list[CommunicationAttachment]:
    if not can_create_message(user=user, thread=message.thread, visibility=message.visibility):
        raise CommunicationError(
            "permission_denied",
            "You do not have permission to attach objects to this message.",
        )
    with transaction.atomic():
        return _create_attachments(
            message=message,
            refs=[_coerce_attachment_ref(ref) for ref in attachments],
            actor=user,
        )


def redact_message(
    *,
    user: User,
    message: CommunicationMessage,
    reason: str,
) -> CommunicationMessage:
    if not is_operator_for_company(user=user, company=message.company):
        raise CommunicationError(
            "permission_denied",
            "You do not have permission to redact this communication message.",
        )
    with transaction.atomic():
        message.body = ""
        message.redacted_at = timezone.now()
        message.redaction_reason = str(reason or "")[:2000]
        message.save(update_fields=["body", "redacted_at", "redaction_reason", "updated_at"])
        record_audit_log(
            actor=user,
            tenant_id=str(message.organization_id),
            action="communication.message.redacted",
            resource_type="communication_message",
            resource_id=str(message.id),
            metadata={
                "thread_id": str(message.thread_id),
                "visibility": message.visibility,
            },
        )
        record_communication_event(
            event_type="communication.message.redacted",
            aggregate_type="communication_message",
            aggregate_id=message.id,
            organization=message.organization,
            company=message.company,
            payload=_message_event_payload(message),
            idempotency_key=f"communication-message:{message.id}:redacted:{message.updated_at.isoformat()}",
        )
    return message


def thread_payload(thread: CommunicationThread, *, user: User) -> dict[str, Any]:
    return {
        "id": str(thread.id),
        "organization_id": str(thread.organization_id),
        "company_id": str(thread.company_id) if thread.company_id else None,
        "service_engagement_id": (
            str(thread.service_engagement_id) if thread.service_engagement_id else None
        ),
        "operation_id": str(thread.operation_id) if thread.operation_id else None,
        "approval_task_id": str(thread.approval_task_id) if thread.approval_task_id else None,
        "artifact_id": str(thread.artifact_id) if thread.artifact_id else None,
        "report_run_id": str(thread.report_run_id) if thread.report_run_id else None,
        "department_id": str(thread.department_id) if thread.department_id else None,
        "title": thread.title,
        "thread_type": thread.thread_type,
        "visibility_mode": thread.visibility_mode,
        "status": thread.status,
        "source_key": thread.source_key,
        "metadata": sanitize_metadata(thread.metadata_json or {}),
        "can_send_internal": is_operator_for_company(user=user, company=thread.company),
        "created_by_user_id": str(thread.created_by_user_id) if thread.created_by_user_id else None,
        "created_by_agent_id": str(thread.created_by_agent_id)
        if thread.created_by_agent_id
        else None,
        "created_at": thread.created_at.isoformat(),
        "updated_at": thread.updated_at.isoformat(),
    }


def message_payload(message: CommunicationMessage, *, user: User) -> dict[str, Any]:
    attachments = [
        payload
        for attachment in message.attachments.all()
        if (payload := attachment_payload(attachment, user=user)) is not None
    ]
    redacted = message.redacted_at is not None
    routed_whiteboard_id: str | None = None
    routed_classification: str | None = None
    if message.company_id and is_operator_for_company(user=user, company=message.company):
        routed_whiteboard = (
            WorkWhiteboard.objects.filter(source_message=message, company=message.company)
            .order_by("-updated_at")
            .only("id")
            .first()
        )
        if routed_whiteboard is not None:
            routed_whiteboard_id = str(routed_whiteboard.id)
            classification = (
                RequestClassificationRecord.objects.filter(
                    communication_message=message,
                    company=message.company,
                )
                .order_by("-created_at")
                .only("classification")
                .first()
            )
            routed_classification = (
                classification.classification if classification is not None else None
            )
    return {
        "id": str(message.id),
        "thread_id": str(message.thread_id),
        "organization_id": str(message.organization_id),
        "company_id": str(message.company_id) if message.company_id else None,
        "sender_kind": message.sender_kind,
        "sender_user_id": str(message.sender_user_id) if message.sender_user_id else None,
        "sender_agent_id": str(message.sender_agent_id) if message.sender_agent_id else None,
        "sender_company_id": str(message.sender_company_id) if message.sender_company_id else None,
        "sender_organization_id": (
            str(message.sender_organization_id) if message.sender_organization_id else None
        ),
        "message_kind": message.message_kind,
        "body": "" if redacted else message.body,
        "body_format": message.body_format,
        "visibility": message.visibility,
        "redacted": redacted,
        "redacted_at": message.redacted_at.isoformat() if message.redacted_at else None,
        "metadata": sanitize_metadata(message.metadata_json or {}),
        "attachments": attachments,
        "routed_whiteboard_id": routed_whiteboard_id,
        "routed_classification": routed_classification,
        "created_at": message.created_at.isoformat(),
        "updated_at": message.updated_at.isoformat(),
    }


def attachment_payload(
    attachment: CommunicationAttachment,
    *,
    user: User,
) -> dict[str, Any] | None:
    target_type = attachment_target_type(attachment)
    target_id = attachment_target_id(attachment)
    if not target_type or not target_id:
        return None
    if not can_read_attachment_target(user=user, attachment=attachment, target_type=target_type):
        return None
    return {
        "id": str(attachment.id),
        "message_id": str(attachment.message_id),
        "type": target_type,
        "target_id": str(target_id),
        "metadata": sanitize_metadata(attachment.metadata_json or {}),
        "created_at": attachment.created_at.isoformat(),
    }


def can_read_thread(*, user: User, thread: CommunicationThread) -> bool:
    if thread.company is None:
        return has_min_role(user, "viewer", str(thread.organization_id))
    if thread.visibility_mode in {"operator", "internal"}:
        return is_operator_for_company(user=user, company=thread.company)
    return has_company_access(user, thread.company, "viewer")


def can_create_message(*, user: User, thread: CommunicationThread, visibility: str) -> bool:
    if thread.company is None:
        return has_min_role(user, "member", str(thread.organization_id))
    if visibility == "customer":
        return has_company_access(user, thread.company, "viewer")
    return is_operator_for_company(user=user, company=thread.company)


def is_operator_for_company(*, user: User, company: Graph | None) -> bool:
    if company is None:
        return has_min_role(user, "member")
    return has_company_access(user, company, "member") and has_min_role(
        user,
        "member",
        str(company.organization_id),
    )


def _validate_service_sender_context(
    *,
    thread: CommunicationThread,
    sender_kind: str,
    sender_agent: AgentRegistryEntry | None,
    sender_organization: Organization | None,
) -> None:
    if sender_kind not in {"agent", "system"}:
        return
    if thread.company_id is None:
        raise CommunicationError(
            "service_sender_context_required",
            "Agent and system messages require a company-scoped communication thread.",
        )
    if sender_kind == "system":
        if sender_organization is None or sender_organization.id != thread.organization_id:
            raise CommunicationError(
                "service_sender_context_required",
                "System messages require sender_organization matching the thread organization.",
            )
        return
    if sender_agent is None:
        raise CommunicationError(
            "service_sender_context_required",
            "Agent messages require sender_agent.",
        )
    if sender_agent.organization_id != thread.organization_id:
        raise CommunicationError(
            "service_sender_context_required",
            "Agent sender must belong to the thread organization.",
        )
    if sender_agent.source_workflow_id != thread.company_id:
        raise CommunicationError(
            "service_sender_context_required",
            "Agent sender must be registered to the thread company.",
        )


def sanitize_metadata(value: Any) -> dict[str, Any]:
    redacted = redact_payload(value or {})
    if not isinstance(redacted, dict):
        return {}
    cleaned = _drop_sensitive_metadata(redacted)
    return cleaned if isinstance(cleaned, dict) else {}


def assert_interaction_event_record_not_suitable() -> str:
    _ = InteractionEventRecord
    return INTERACTION_EVENT_RECORD_SUITABILITY_NOTE


def record_communication_event(
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: UUID | str,
    organization: Organization,
    company: Graph | None,
    payload: dict[str, Any],
    idempotency_key: str,
) -> None:
    safe_payload = sanitize_metadata(payload)
    safe_payload["event_type"] = event_type
    safe_payload["schema_version"] = COMMUNICATION_EVENT_SCHEMA_VERSION
    record_domain_event(
        organization=organization,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        event_version=1,
        idempotency_key=idempotency_key,
        payload=safe_payload,
        outbox_topic=_communication_outbox_topic(),
        outbox_schema_version=COMMUNICATION_EVENT_SCHEMA_VERSION,
        outbox_payload=safe_payload,
        outbox_visibility=str(safe_payload.get("visibility") or ""),
        outbox_company=company,
    )


def _communication_outbox_topic() -> str:
    return str(
        getattr(settings, "COMMUNICATION_KAFKA_TOPIC", "")
        or getattr(settings, "KAFKA_COMMUNICATION_TOPIC", "")
        or COMMUNICATION_OUTBOX_TOPIC
    )


def _thread_queryset() -> QuerySet[CommunicationThread]:
    return CommunicationThread.objects.select_related(
        "organization",
        "company",
        "service_engagement",
        "operation__graph_version__graph",
        "approval_task__run__graph_version__graph",
        "artifact",
        "report_run",
        "department",
        "created_by_user",
        "created_by_agent",
    )


def _message_queryset() -> QuerySet[CommunicationMessage]:
    return CommunicationMessage.objects.select_related(
        "thread__company",
        "thread__organization",
        "organization",
        "company",
        "sender_user",
        "sender_agent",
        "sender_company",
        "sender_organization",
    ).prefetch_related("attachments")


def _resolve_thread_links(company: Graph, data: dict[str, Any]) -> dict[str, Any]:
    links: dict[str, Any] = {}
    resolvers = {
        "service_engagement": (ServiceEngagement, "service_engagement_id"),
        "operation": (Run, "operation_id"),
        "approval_task": (ApprovalTask, "approval_task_id"),
        "artifact": (Asset, "artifact_id"),
        "report_run": (ReportRun, "report_run_id"),
        "department": (DepartmentRegistry, "department_id"),
    }
    for key, (model, input_key) in resolvers.items():
        object_id = data.get(input_key)
        if not object_id:
            continue
        obj = _lookup_target(model, object_id)
        if obj is None:
            raise CommunicationError(
                "linked_object_not_found",
                f"{input_key} was not found.",
            )
        _validate_scope(obj, company=company, field_name=input_key)
        links[key] = obj
    return links


def _create_attachments(
    *,
    message: CommunicationMessage,
    refs: list[AttachmentRef],
    actor: User | None,
) -> list[CommunicationAttachment]:
    created: list[CommunicationAttachment] = []
    for ref in refs:
        target = resolve_attachment_target(ref)
        if target is None:
            raise CommunicationError(
                "attachment_target_not_found",
                "Attachment target was not found.",
                details=[{"type": ref.type, "id": str(ref.id)}],
            )
        if message.company is None:
            raise CommunicationError(
                "company_required",
                "Attachments require a company-scoped message.",
            )
        _validate_scope(target, company=message.company, field_name=ref.type)
        attachment = CommunicationAttachment(
            message=message,
            metadata_json=sanitize_metadata(ref.metadata or {}),
        )
        setattr(attachment, _attachment_model_field(ref.type), target)
        attachment.full_clean()
        try:
            attachment.save()
        except IntegrityError as exc:
            raise CommunicationError(
                "attachment_create_failed",
                "Attachment could not be created.",
            ) from exc
        created.append(attachment)
        record_audit_log(
            actor=actor,
            tenant_id=str(message.organization_id),
            action="communication.attachment.created",
            resource_type="communication_attachment",
            resource_id=str(attachment.id),
            metadata={
                "message_id": str(message.id),
                "thread_id": str(message.thread_id),
                "target_type": ref.type,
                "target_id": str(ref.id),
            },
        )
        record_communication_event(
            event_type="communication.attachment.created",
            aggregate_type="communication_attachment",
            aggregate_id=attachment.id,
            organization=message.organization,
            company=message.company,
            payload=_attachment_event_payload(attachment),
            idempotency_key=f"communication-attachment:{attachment.id}:created",
        )
    return created


def _coerce_attachment_ref(value: AttachmentRef | dict[str, Any]) -> AttachmentRef:
    if isinstance(value, AttachmentRef):
        return value
    return AttachmentRef(
        type=str(value.get("type") or ""),
        id=value.get("id") or "",
        metadata=value.get("metadata") if isinstance(value.get("metadata"), dict) else None,
    )


def resolve_attachment_target(ref: AttachmentRef) -> object | None:
    model = _attachment_model(ref.type)
    return _lookup_target(model, ref.id) if model is not None else None


def attachment_target_type(attachment: CommunicationAttachment) -> str:
    for target_type, field_name in _ATTACHMENT_TYPE_TO_FIELD.items():
        if getattr(attachment, f"{field_name}_id"):
            return target_type
    return ""


def attachment_target_id(attachment: CommunicationAttachment) -> UUID | None:
    target_type = attachment_target_type(attachment)
    if not target_type:
        return None
    return cast(UUID | None, getattr(attachment, f"{_attachment_model_field(target_type)}_id"))


def can_read_attachment_target(
    *,
    user: User,
    attachment: CommunicationAttachment,
    target_type: str,
) -> bool:
    if is_operator_for_company(user=user, company=attachment.message.company):
        return True
    if attachment.message.visibility != "customer":
        return False
    if target_type not in _PUBLIC_ATTACHMENT_TARGETS:
        return False
    if target_type == "service_deliverable":
        deliverable = attachment.service_deliverable
        return deliverable is not None and deliverable.visibility != "internal"
    return (
        has_company_access(user, attachment.message.company, "viewer")
        if attachment.message.company
        else False
    )


def _lookup_target(model: type[Any], object_id: UUID | str) -> Any | None:
    queryset = model.objects
    if model is AssetVersion:
        queryset = queryset.select_related("asset")
    elif model is ApprovalTask:
        queryset = queryset.select_related("run__graph_version__graph")
    elif model is DecisionRecord:
        queryset = queryset.select_related(
            "execution__graph_version__graph",
            "source_approval_task__run__graph_version__graph",
            "task__execution__graph_version__graph",
        )
    elif model is Run:
        queryset = queryset.select_related("graph_version__graph")
    elif model is ToolExecution:
        queryset = queryset.select_related("run__graph_version__graph")
    return queryset.filter(id=object_id).first()


def _validate_scope(obj: object, *, company: Graph, field_name: str) -> None:
    organization_id, company_id = _scope_for_object(obj)
    if organization_id and organization_id != company.organization_id:
        raise CommunicationError(
            "linked_object_scope_mismatch",
            "Linked object belongs to a different organization.",
            details=[{"field": field_name}],
        )
    if company_id and company_id != company.id:
        raise CommunicationError(
            "linked_object_scope_mismatch",
            "Linked object belongs to a different company.",
            details=[{"field": field_name}],
        )


def _scope_for_object(value: object) -> tuple[UUID | None, UUID | None]:
    organization_id = cast(UUID | None, getattr(value, "organization_id", None))
    company_id = cast(UUID | None, getattr(value, "company_id", None))
    if isinstance(value, AssetVersion):
        return value.asset.organization_id, value.asset.company_id
    if isinstance(value, ApprovalTask):
        return _scope_for_approval_task(value)
    if isinstance(value, DecisionRecord):
        return _scope_for_decision_record(value)
    if isinstance(value, ToolExecution):
        return _scope_for_run(value.run)
    if isinstance(value, Run):
        return _scope_for_run(value)
    return organization_id, company_id


def _scope_for_approval_task(
    approval_task: ApprovalTask,
) -> tuple[UUID | None, UUID | None]:
    if approval_task.run is None:
        return approval_task.organization_id, None
    return _scope_for_run(approval_task.run)


def _scope_for_decision_record(
    decision: DecisionRecord,
) -> tuple[UUID | None, UUID | None]:
    if decision.execution_id and decision.execution is not None:
        return _scope_for_run(decision.execution)
    if (
        decision.source_approval_task_id
        and decision.source_approval_task is not None
        and decision.source_approval_task.run is not None
    ):
        return _scope_for_run(decision.source_approval_task.run)
    if (
        decision.task_id
        and decision.task is not None
        and decision.task.execution_id
        and decision.task.execution is not None
    ):
        return _scope_for_run(decision.task.execution)
    return decision.organization_id, None


def _scope_for_run(run: Run) -> tuple[UUID | None, UUID | None]:
    organization_id = run.organization_id or run.graph_version.graph.organization_id
    return organization_id, run.graph_version.graph_id


def _thread_event_payload(thread: CommunicationThread) -> dict[str, Any]:
    return {
        "thread_id": str(thread.id),
        "organization_id": str(thread.organization_id),
        "company_id": str(thread.company_id) if thread.company_id else None,
        "operation_id": str(thread.operation_id) if thread.operation_id else None,
        "service_engagement_id": (
            str(thread.service_engagement_id) if thread.service_engagement_id else None
        ),
        "approval_task_id": str(thread.approval_task_id) if thread.approval_task_id else None,
        "artifact_id": str(thread.artifact_id) if thread.artifact_id else None,
        "report_run_id": str(thread.report_run_id) if thread.report_run_id else None,
        "department_id": str(thread.department_id) if thread.department_id else None,
        "visibility": thread.visibility_mode,
        "thread_type": thread.thread_type,
        "status": thread.status,
        "created_at": thread.created_at.isoformat(),
    }


def _message_event_payload(message: CommunicationMessage) -> dict[str, Any]:
    thread = message.thread
    return {
        "thread_id": str(thread.id),
        "message_id": str(message.id),
        "organization_id": str(message.organization_id),
        "company_id": str(message.company_id) if message.company_id else None,
        "operation_id": str(thread.operation_id) if thread.operation_id else None,
        "service_engagement_id": (
            str(thread.service_engagement_id) if thread.service_engagement_id else None
        ),
        "visibility": message.visibility,
        "sender_kind": message.sender_kind,
        "message_kind": message.message_kind,
        "created_at": message.created_at.isoformat(),
        "idempotency_key": message.idempotency_key,
    }


def _attachment_event_payload(attachment: CommunicationAttachment) -> dict[str, Any]:
    message = attachment.message
    target_type = attachment_target_type(attachment)
    return {
        "thread_id": str(message.thread_id),
        "message_id": str(message.id),
        "attachment_id": str(attachment.id),
        "organization_id": str(message.organization_id),
        "company_id": str(message.company_id) if message.company_id else None,
        "visibility": message.visibility,
        "target_type": target_type,
        "target_id": str(attachment_target_id(attachment)) if target_type else None,
        "created_at": attachment.created_at.isoformat(),
    }


def _drop_sensitive_metadata(value: Any, *, field_name: str = "") -> Any:
    if field_name.strip().lower() in _DROPPED_METADATA_KEYS:
        return None
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            normalized = str(key)
            cleaned = _drop_sensitive_metadata(item, field_name=normalized)
            if cleaned is not None:
                result[normalized] = cleaned
        return result
    if isinstance(value, list):
        return [
            cleaned
            for item in value
            if (cleaned := _drop_sensitive_metadata(item, field_name=field_name)) is not None
        ]
    return value


_ATTACHMENT_TYPE_TO_FIELD = {
    "artifact": "artifact",
    "artifact_revision": "artifact_revision",
    "report_run": "report_run",
    "approval_task": "approval_task",
    "decision": "decision",
    "company_signal": "signal",
    "signal": "signal",
    "service_engagement": "service_engagement",
    "operation": "operation",
    "tool_execution": "tool_execution",
    "evaluation_run": "evaluation_run",
    "service_deliverable": "service_deliverable",
}

_ATTACHMENT_FIELD_TO_MODEL = {
    "artifact": Asset,
    "artifact_revision": AssetVersion,
    "report_run": ReportRun,
    "approval_task": ApprovalTask,
    "decision": DecisionRecord,
    "signal": CompanySignal,
    "service_engagement": ServiceEngagement,
    "operation": Run,
    "tool_execution": ToolExecution,
    "evaluation_run": EvaluationRun,
    "service_deliverable": ServiceDeliverable,
}


def _attachment_model_field(target_type: str) -> str:
    field_name = _ATTACHMENT_TYPE_TO_FIELD.get(target_type)
    if not field_name:
        raise CommunicationError(
            "attachment_type_invalid",
            "Attachment type is not supported.",
            details=[{"type": target_type}],
        )
    return field_name


def _attachment_model(target_type: str) -> type[Any] | None:
    field_name = _ATTACHMENT_TYPE_TO_FIELD.get(target_type)
    if not field_name:
        return None
    return _ATTACHMENT_FIELD_TO_MODEL[field_name]
