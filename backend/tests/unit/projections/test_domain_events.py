from __future__ import annotations

from uuid import uuid4

import pytest

from application.services.domain_events import record_domain_event
from infrastructure.orm.models import DomainEvent

pytestmark = pytest.mark.django_db


def test_domain_event_recording_is_idempotent_and_org_sequenced(user) -> None:
    organization = user.default_organization
    assert organization is not None
    aggregate_id = uuid4()

    first = record_domain_event(
        organization=organization,
        aggregate_type="test",
        aggregate_id=aggregate_id,
        event_type="test.created",
        idempotency_key="test:event:1",
        payload={"value": 1},
    )
    duplicate = record_domain_event(
        organization=organization,
        aggregate_type="test",
        aggregate_id=aggregate_id,
        event_type="test.created",
        idempotency_key="test:event:1",
        payload={"value": 1},
    )
    second = record_domain_event(
        organization=organization,
        aggregate_type="test",
        aggregate_id=uuid4(),
        event_type="test.updated",
        idempotency_key="test:event:2",
        payload={"value": 2},
    )

    assert first.created is True
    assert duplicate.created is False
    assert duplicate.event.id == first.event.id
    assert second.event.sequence == first.event.sequence + 1
    assert DomainEvent.objects.filter(organization=organization).count() == 2
