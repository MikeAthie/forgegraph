from __future__ import annotations

from uuid import uuid4

import pytest

from application.services.domain_events import record_domain_event
from application.workers.process_os_projection_events import process_pending_projection_events
from infrastructure.orm.models import EventDeadLetterRecord, ProjectionCursor

pytestmark = pytest.mark.django_db


def test_projection_worker_dead_letters_malformed_event(user) -> None:
    organization = user.default_organization
    assert organization is not None
    event = record_domain_event(
        organization=organization,
        aggregate_type="llm_usage",
        aggregate_id=uuid4(),
        event_type="accounting.llm_usage_recorded",
        idempotency_key="malformed-accounting-event",
        payload={"llm_usage_id": "not-a-uuid"},
    ).event

    result = process_pending_projection_events(
        organization_id=organization.id,
        projection_names=("accounting",),
    )

    assert result.deadlettered == 1
    assert EventDeadLetterRecord.objects.filter(
        organization=organization,
        source="os_projection_worker",
        event_id=str(event.id),
    ).exists()
    cursor = ProjectionCursor.objects.get(organization=organization, projection_name="accounting")
    assert cursor.status == "degraded"
    assert cursor.last_sequence == event.sequence
