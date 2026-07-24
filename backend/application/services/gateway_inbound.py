"""Backend-owned materialization for accepted gateway inbound events."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from application.services.domain_event_outbox import sanitize_outbox_payload
from application.services.gateway_media import (
    link_media_transcript,
    media_artifact_payload,
    normalize_gateway_attachments,
)
from application.services.memory_observation_service import MemoryObservationService
from infrastructure.orm.models import (
    CommunicationMessage,
    CommunicationThread,
    GatewayConnection,
    GatewayConversation,
    GatewayInboundReceipt,
    GraphVersion,
    MemoryObservation,
    Organization,
    Run,
    User,
)


def resolve_gateway_connection_for_event(
    *,
    organization: Organization,
    graph_version: GraphVersion,
    platform: str,
    provider: str,
) -> GatewayConnection | None:
    queryset = GatewayConnection.objects.filter(
        organization=organization,
        platform=platform,
        status__in=["enabled", "degraded"],
    )
    if provider:
        queryset = queryset.filter(provider=provider)
    return (
        queryset.filter(graph_version=graph_version).order_by("updated_at").first()
        or queryset.filter(graph_version__isnull=True).order_by("updated_at").first()
        or GatewayConnection.objects.create(
            organization=organization,
            graph_version=graph_version,
            platform=platform,
            provider=provider or platform,
            name=f"{platform}-webhook"[:120],
            status="enabled",
            config_json={"created_from": "gateway_webhook"},
            allowlist_json=[],
        )
    )


def materialize_gateway_inbound(
    *,
    receipt: GatewayInboundReceipt,
    graph_version: GraphVersion,
    owner: User,
    run: Run,
    input_json: dict[str, Any],
    thread_id: UUID | None,
) -> dict[str, Any]:
    raw_gateway = input_json.get("gateway")
    gateway: dict[str, Any] = raw_gateway if isinstance(raw_gateway, dict) else {}
    platform = str(gateway.get("platform") or receipt.platform)
    provider = str(gateway.get("provider") or receipt.provider)
    conversation_id = str(gateway.get("conversation_id") or receipt.external_conversation_id)
    message_text = str(input_json.get("message") or "")
    raw_attachments = gateway.get("attachments")
    attachments: list[Any] = raw_attachments if isinstance(raw_attachments, list) else []

    with transaction.atomic():
        if receipt.connection_id:
            GatewayConnection.objects.filter(id=receipt.connection_id).update(
                last_seen_at=timezone.now(),
                status="enabled",
            )
        conversation = _upsert_gateway_conversation(
            receipt=receipt,
            graph_version=graph_version,
            conversation_id=conversation_id,
            thread_id=thread_id,
        )
        communication_thread = _upsert_communication_thread(
            graph_version=graph_version,
            owner=owner,
            conversation=conversation,
            conversation_id=conversation_id,
            platform=platform,
        )
        message = _upsert_communication_message(
            thread=communication_thread,
            organization=receipt.organization,
            text=message_text,
            idempotency_key=receipt.idempotency_key,
            metadata={
                "gateway_receipt_id": str(receipt.id),
                "gateway_platform": platform,
                "gateway_provider": provider,
                "gateway_conversation_id": conversation_id,
                "gateway_event_id": receipt.external_event_id,
                "run_id": str(run.id),
            },
        )
        observation = _create_message_observation(
            receipt=receipt,
            graph_version=graph_version,
            run=run,
            thread_id=thread_id,
            message_text=message_text,
            platform=platform,
            conversation_id=conversation_id,
        )
        media_artifacts = normalize_gateway_attachments(
            organization=receipt.organization,
            platform=platform,
            provider=provider,
            direction="inbound",
            attachments=[item for item in attachments if isinstance(item, dict)],
            connection=receipt.connection,
            inbound_receipt=receipt,
        )
        for artifact, raw in zip(media_artifacts, attachments, strict=False):
            if not isinstance(raw, dict):
                continue
            transcript_text = str(raw.get("transcript") or raw.get("text_transcript") or "").strip()
            if transcript_text:
                transcript = _create_media_transcript_observation(
                    receipt=receipt,
                    graph_version=graph_version,
                    run=run,
                    thread_id=thread_id,
                    transcript_text=transcript_text,
                    platform=platform,
                    artifact_id=artifact.id,
                )
                link_media_transcript(artifact, transcript)

        event_json = dict(receipt.event_json or {})
        event_json["gateway_materialized"] = {
            "conversation_id": str(conversation.id),
            "communication_thread_id": str(communication_thread.id),
            "communication_message_id": str(message.id),
            "memory_observation_id": str(observation.id) if observation else "",
            "media_artifact_ids": [str(item.id) for item in media_artifacts],
        }
        receipt.event_json = sanitize_outbox_payload(event_json)
        receipt.save(update_fields=["event_json", "updated_at"])

    return {
        "gateway_conversation_id": str(conversation.id),
        "communication_thread_id": str(communication_thread.id),
        "communication_message_id": str(message.id),
        "memory_observation_id": str(observation.id) if observation else "",
        "media_artifacts": [media_artifact_payload(item) for item in media_artifacts],
    }


def _upsert_gateway_conversation(
    *,
    receipt: GatewayInboundReceipt,
    graph_version: GraphVersion,
    conversation_id: str,
    thread_id: UUID | None,
) -> GatewayConversation:
    effective_thread_id = thread_id or receipt.id
    conversation, _ = GatewayConversation.objects.update_or_create(
        organization=receipt.organization,
        platform=receipt.platform,
        external_conversation_id=conversation_id[:255],
        defaults={
            "connection": receipt.connection,
            "graph_version": graph_version,
            "thread_id": effective_thread_id,
            "metadata_json": {
                "provider": receipt.provider,
                "last_receipt_id": str(receipt.id),
            },
            "last_message_at": timezone.now(),
        },
    )
    return conversation


def _upsert_communication_thread(
    *,
    graph_version: GraphVersion,
    owner: User,
    conversation: GatewayConversation,
    conversation_id: str,
    platform: str,
) -> CommunicationThread:
    company = graph_version.graph
    source_key = f"gateway:{platform}:{conversation_id}"[:255]
    thread, _ = CommunicationThread.objects.update_or_create(
        company=company,
        source_key=source_key,
        defaults={
            "organization": conversation.organization,
            "operation": None,
            "title": f"{platform.title()} conversation {conversation_id}"[:255],
            "thread_type": "support",
            "visibility_mode": "mixed",
            "status": "open",
            "created_by_user": owner,
            "metadata_json": {
                "gateway_conversation_id": str(conversation.id),
                "gateway_thread_id": str(conversation.thread_id),
            },
        },
    )
    return thread


def _upsert_communication_message(
    *,
    thread: CommunicationThread,
    organization: Organization,
    text: str,
    idempotency_key: str,
    metadata: dict[str, Any],
) -> CommunicationMessage:
    message, _ = CommunicationMessage.objects.get_or_create(
        thread=thread,
        idempotency_key=idempotency_key[:255],
        defaults={
            "organization": organization,
            "company": thread.company,
            "sender_kind": "system",
            "sender_organization": organization,
            "message_kind": "request",
            "body": text[:8000],
            "body_format": "plain",
            "visibility": "customer",
            "metadata_json": sanitize_outbox_payload(metadata),
        },
    )
    return message


def _create_message_observation(
    *,
    receipt: GatewayInboundReceipt,
    graph_version: GraphVersion,
    run: Run,
    thread_id: UUID | None,
    message_text: str,
    platform: str,
    conversation_id: str,
) -> MemoryObservation | None:
    if not message_text.strip():
        return None
    service = MemoryObservationService()
    return service.create_observation(
        tenant_id=receipt.organization_id,
        type="gateway_message",
        title=f"{platform} inbound message",
        content=message_text,
        scope="session" if thread_id else "run",
        graph_id=graph_version.graph_id,
        run_id=None if thread_id else run.id,
        session_id=thread_id,
        topic_key=f"gateway:{platform}:{conversation_id}",
        source_event_id=receipt.external_event_id,
        source_event_type="gateway.inbound.accepted",
        provenance_json={
            "gateway_receipt_id": str(receipt.id),
            "run_id": str(run.id),
            "platform": platform,
            "conversation_id": conversation_id,
        },
        dedupe=True,
        update_topic=False,
    )


def _create_media_transcript_observation(
    *,
    receipt: GatewayInboundReceipt,
    graph_version: GraphVersion,
    run: Run,
    thread_id: UUID | None,
    transcript_text: str,
    platform: str,
    artifact_id: UUID,
) -> MemoryObservation:
    service = MemoryObservationService()
    return service.create_observation(
        tenant_id=receipt.organization_id,
        type="gateway_media_transcript",
        title=f"{platform} media transcript",
        content=transcript_text,
        scope="session" if thread_id else "run",
        graph_id=graph_version.graph_id,
        run_id=None if thread_id else run.id,
        session_id=thread_id,
        topic_key=f"gateway-media:{artifact_id}",
        source_event_id=receipt.external_event_id,
        source_event_type="gateway.media.transcript",
        provenance_json={
            "gateway_receipt_id": str(receipt.id),
            "run_id": str(run.id),
            "media_artifact_id": str(artifact_id),
        },
        dedupe=True,
        update_topic=False,
    )
