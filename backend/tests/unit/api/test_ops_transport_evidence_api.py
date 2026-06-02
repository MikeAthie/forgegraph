from __future__ import annotations

from uuid import uuid4

import pytest
from rest_framework import status

from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import (
    CommunicationEventReceipt,
    DomainEventOutbox,
    EventDeadLetterRecord,
    Graph,
    User,
    WorkWhiteboard,
)

pytestmark = pytest.mark.django_db


def test_ops_transport_evidence_requires_supported_transport(authenticated_client) -> None:
    response = authenticated_client.get("/api/ops/transport-evidence?transport=redis")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["error"]["code"] == "UNSUPPORTED_TRANSPORT"


def test_ops_transport_evidence_reports_backend_owned_whiteboard_kafka_counts(
    authenticated_client,
    user,
    settings,
) -> None:
    settings.WHITEBOARD_BOARD_KAFKA_ENABLED = True
    ensure_default_organization(user)
    organization = user.default_organization
    assert organization is not None
    company = Graph.objects.create(
        owner=user,
        organization=organization,
        name=f"Atlas Ops Evidence {uuid4().hex[:8]}",
    )
    whiteboard = WorkWhiteboard.objects.create(
        organization=organization,
        company=company,
        status=WorkWhiteboard.STATUS_ONBOARDING,
        client_name=company.name,
        request_type="service_request",
        request_summary="P2 transport evidence",
        objective="Prove transport observability without authority.",
        created_by=user,
    )
    payload = {
        "event_id": "",
        "event_type": "whiteboard.card.created",
        "schema_version": "whiteboard_board_event_v1",
        "organization_id": str(organization.id),
        "company_id": str(company.id),
        "whiteboard_id": str(whiteboard.id),
        "created_at": "2026-06-01T00:00:00+00:00",
        "idempotency_key": f"ops-evidence:{whiteboard.id}",
    }
    outbox = DomainEventOutbox.objects.create(
        organization=organization,
        company=company,
        event_type="whiteboard.card.created",
        schema_version="whiteboard_board_event_v1",
        aggregate_type="work_whiteboard",
        aggregate_id=whiteboard.id,
        topic="forgegraph.whiteboard.board.events.v1",
        payload_json=payload,
        status="published",
        idempotency_key=f"ops-evidence:outbox:{whiteboard.id}",
    )
    payload["event_id"] = str(outbox.id)
    outbox.payload_json = payload
    outbox.save(update_fields=["payload_json"])
    CommunicationEventReceipt.objects.create(
        consumer_group="forgegraph-whiteboard-board-events",
        event_id=str(outbox.id),
        idempotency_key=payload["idempotency_key"],
        topic="forgegraph.whiteboard.board.events.v1",
        organization=organization,
        company=company,
        outbox_event=outbox,
        event_type="whiteboard.card.created",
        schema_version="whiteboard_board_event_v1",
        aggregate_type="work_whiteboard",
        aggregate_id=str(whiteboard.id),
        status="handled",
        payload_json=payload,
    )
    other_user = User.objects.create_user(
        email=f"atlas-ops-other-{uuid4().hex}@example.com",
        password="password123",
    )
    ensure_default_organization(other_user)
    other_organization = other_user.default_organization
    assert other_organization is not None
    other_company = Graph.objects.create(
        owner=other_user,
        organization=other_organization,
        name=f"Other Org Spoof {uuid4().hex[:8]}",
    )
    same_org_other_company = Graph.objects.create(
        owner=user,
        organization=organization,
        name=f"Same Org Spoof {uuid4().hex[:8]}",
    )
    CommunicationEventReceipt.objects.create(
        consumer_group="forgegraph-whiteboard-board-events",
        event_id=str(uuid4()),
        idempotency_key=f"ops-evidence:cross-org-spoof:{whiteboard.id}",
        topic="forgegraph.whiteboard.board.events.v1",
        organization=other_organization,
        company=other_company,
        event_type="whiteboard.card.created",
        schema_version="whiteboard_board_event_v1",
        aggregate_type="work_whiteboard",
        aggregate_id=str(whiteboard.id),
        status="handled",
        payload_json={**payload, "event_id": str(uuid4())},
    )
    CommunicationEventReceipt.objects.create(
        consumer_group="forgegraph-whiteboard-board-events",
        event_id=str(uuid4()),
        idempotency_key=f"ops-evidence:company-spoof:{whiteboard.id}",
        topic="forgegraph.whiteboard.board.events.v1",
        organization=organization,
        company=same_org_other_company,
        event_type="whiteboard.card.created",
        schema_version="whiteboard_board_event_v1",
        aggregate_type="work_whiteboard",
        aggregate_id=str(whiteboard.id),
        status="handled",
        payload_json={**payload, "event_id": str(uuid4())},
    )
    EventDeadLetterRecord.objects.create(
        organization=other_organization,
        source="whiteboard_board_kafka_consumer",
        reason="spoofed_payload_scope",
        event_id=str(uuid4()),
        event_type="whiteboard.card.created",
        payload=payload,
    )

    response = authenticated_client.get(
        f"/api/ops/transport-evidence?transport=whiteboard_board_kafka"
        f"&whiteboard_id={whiteboard.id}"
        f"&company_id={company.id}"
    )

    assert response.status_code == status.HTTP_200_OK
    evidence = response.data["data"]["transport_evidence"]
    assert evidence["authoritative_state_source"] == "backend_db"
    assert evidence["enabled"] is True
    assert evidence["outbox"]["published"] == 1
    assert evidence["receipts"]["handled"] == 1
    assert evidence["dead_letters"]["active_count"] == 0
