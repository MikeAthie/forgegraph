"""Request classification and WorkWhiteboard routing services."""

from __future__ import annotations

from django.conf import settings
from django.db import IntegrityError, transaction

from application.services.domain_event_outbox import sanitize_outbox_payload
from application.services.work_whiteboards import (
    ACTIVE_WHITEBOARD_STATUSES,
    create_onboarding_routing_tasks,
    initialize_whiteboard_from_message,
    route_account_intake_clarification,
)
from infrastructure.orm.models import (
    CommunicationEventReceipt,
    CommunicationMessage,
    RequestClassificationRecord,
    TaskRoutingRecord,
    WorkWhiteboard,
)


class RequestRouterError(ValueError):
    """Domain error for request routing operations."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def classify_request(
    *,
    message: CommunicationMessage,
    idempotency_key: str = "",
) -> RequestClassificationRecord:
    """Classify a committed communication message into the next backend-owned path."""

    if message.company is None:
        raise RequestRouterError("company_required", "Request classification requires a company-scoped message.")
    key = str(idempotency_key or f"request-classification:message:{message.id}").strip()
    existing = RequestClassificationRecord.objects.filter(
        organization=message.organization,
        idempotency_key=key,
    ).first()
    if existing is not None:
        return existing

    matched_whiteboard = _matched_whiteboard_for_message(message)
    matched_service_engagement = message.thread.service_engagement
    classification = RequestClassificationRecord.CLASS_AMBIGUOUS
    confidence = 0.45
    rationale = "Request needs account-intake clarification before a whiteboard can be created."
    if matched_whiteboard is not None or matched_service_engagement is not None or _references_existing_work(message):
        classification = RequestClassificationRecord.CLASS_EXISTING
        confidence = 0.9
        rationale = "Request references active work, a service engagement, or an existing work thread."
    elif _looks_like_new_request(message.body, message.message_kind):
        classification = RequestClassificationRecord.CLASS_NEW
        confidence = 0.82
        rationale = "Request asks for new service work and no active matching whiteboard was found."

    record = RequestClassificationRecord(
        organization=message.organization,
        company=message.company,
        communication_thread=message.thread,
        communication_message=message,
        service_engagement=message.thread.service_engagement,
        classification=classification,
        confidence=confidence,
        rationale=rationale,
        matched_whiteboard=matched_whiteboard,
        matched_service_engagement=matched_service_engagement,
        idempotency_key=key,
        metadata_json=sanitize_outbox_payload(
            {
                "thread_type": message.thread.thread_type,
                "message_kind": message.message_kind,
                "visibility": message.visibility,
            }
        ),
    )
    try:
        record.full_clean()
        record.save()
    except IntegrityError:
        existing = RequestClassificationRecord.objects.filter(
            organization=message.organization,
            idempotency_key=key,
        ).first()
        if existing is not None:
            return existing
        raise
    return record


def create_or_resume_whiteboard(
    *,
    message: CommunicationMessage,
    classification: RequestClassificationRecord | None = None,
) -> tuple[WorkWhiteboard | None, list[TaskRoutingRecord]]:
    """Apply a classification by creating/resuming whiteboard state or routing clarification."""

    classification = classification or classify_request(message=message)
    records: list[TaskRoutingRecord] = []
    if classification.classification == RequestClassificationRecord.CLASS_AMBIGUOUS:
        records.append(route_account_intake_clarification(message=message, classification=classification))
        return None, records
    if classification.classification == RequestClassificationRecord.CLASS_EXISTING:
        whiteboard = classification.matched_whiteboard or _matched_whiteboard_for_message(message)
        if whiteboard is not None:
            if classification.matched_whiteboard_id != whiteboard.id:
                classification.matched_whiteboard = whiteboard
                classification.save(update_fields=["matched_whiteboard", "updated_at"])
            return whiteboard, records
    whiteboard = initialize_whiteboard_from_message(
        message=message,
        classification=classification,
        idempotency_key=f"whiteboard:message:{message.id}",
    )
    records.extend(create_onboarding_routing_tasks(whiteboard=whiteboard, classification=classification))
    return whiteboard, records


def classify_and_route_request(
    *,
    message: CommunicationMessage,
    idempotency_key: str = "",
) -> tuple[RequestClassificationRecord, WorkWhiteboard | None, list[TaskRoutingRecord]]:
    """Classify a message and apply the durable whiteboard/onboarding routing path."""

    with transaction.atomic():
        classification = classify_request(message=message, idempotency_key=idempotency_key)
        whiteboard, records = create_or_resume_whiteboard(message=message, classification=classification)
    return classification, whiteboard, records


def handle_communication_request_receipt(*, receipt: CommunicationEventReceipt) -> WorkWhiteboard | None:
    """Feature-flagged bridge from consumed Kafka receipt to backend request routing."""

    if not bool(getattr(settings, "REQUEST_ROUTER_FROM_KAFKA_ENABLED", False)):
        return None
    if receipt.status != "handled" or receipt.event_type != "communication.message.created":
        return None
    message_id = str((receipt.payload_json or {}).get("message_id") or "").strip()
    if not message_id:
        return None
    message = (
        CommunicationMessage.objects.select_related(
            "thread__service_engagement",
            "thread",
            "company",
            "organization",
            "sender_user",
        )
        .filter(id=message_id, company_id=receipt.company_id)
        .first()
    )
    if message is None:
        return None
    _classification, whiteboard, _records = classify_and_route_request(
        message=message,
        idempotency_key=f"request-router:communication-receipt:{receipt.id}",
    )
    return whiteboard


def _matched_whiteboard_for_message(message: CommunicationMessage) -> WorkWhiteboard | None:
    metadata = message.metadata_json if isinstance(message.metadata_json, dict) else {}
    whiteboard_id = str(metadata.get("whiteboard_id") or "").strip()
    queryset = WorkWhiteboard.objects.filter(
        organization=message.organization,
        company=message.company,
        status__in=ACTIVE_WHITEBOARD_STATUSES,
    )
    if whiteboard_id:
        by_id = queryset.filter(id=whiteboard_id).first()
        if by_id is not None:
            return by_id
    by_thread = queryset.filter(communication_thread=message.thread).order_by("-updated_at").first()
    if by_thread is not None:
        return by_thread
    if message.thread.service_engagement_id:
        return queryset.filter(service_engagement=message.thread.service_engagement).order_by("-updated_at").first()
    return None


def _references_existing_work(message: CommunicationMessage) -> bool:
    thread = message.thread
    metadata = message.metadata_json if isinstance(message.metadata_json, dict) else {}
    if any(
        [
            thread.service_engagement_id,
            thread.operation_id,
            thread.approval_task_id,
            thread.artifact_id,
            thread.report_run_id,
        ]
    ):
        return True
    return any(
        bool(metadata.get(key))
        for key in (
            "whiteboard_id",
            "service_engagement_id",
            "operation_id",
            "approval_task_id",
            "artifact_id",
            "report_run_id",
        )
    )


def _looks_like_new_request(body: str, message_kind: str) -> bool:
    text = str(body or "").lower()
    if message_kind not in {"request", "missing_info_request", "note"} or len(text.strip()) <= 12:
        return False
    return any(
        phrase in text
        for phrase in (
            "new campaign",
            "launch",
            "audit",
            "campaign",
            "promote",
            "build",
            "create",
            "service",
            "request",
            "strategy",
        )
    )
