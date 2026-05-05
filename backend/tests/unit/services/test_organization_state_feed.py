from __future__ import annotations

import pytest

from application.services.organization_state_feed import (
    record_organization_state_feed_event,
    replay_organization_state_feed_events,
)
from infrastructure.orm.models import OrganizationStateFeedEvent

pytestmark = pytest.mark.django_db


def test_record_organization_state_feed_event_is_versioned_and_idempotent(user) -> None:
    organization = user.default_organization

    first = record_organization_state_feed_event(
        organization=organization,
        event_type="overview.updated",
        event_id="evt-1",
        resource_type="overview",
        resource_id=str(organization.id),
    )
    duplicate = record_organization_state_feed_event(
        organization=organization,
        event_type="overview.updated",
        event_id="evt-1",
        resource_type="overview",
        resource_id=str(organization.id),
    )
    second = record_organization_state_feed_event(
        organization=organization,
        event_type="decision.created",
        event_id="evt-2",
        resource_type="decision",
        resource_id="decision-1",
    )

    assert first["state_version"] == 1
    assert duplicate["state_version"] == 1
    assert second["state_version"] == 2
    assert second["event_type"] == "decision.created"
    assert OrganizationStateFeedEvent.objects.filter(organization=organization).count() == 2


def test_replay_organization_state_feed_filters_by_event_type(user) -> None:
    organization = user.default_organization
    record_organization_state_feed_event(
        organization=organization,
        event_type="overview.updated",
        event_id="evt-1",
        resource_type="overview",
        resource_id=str(organization.id),
    )
    record_organization_state_feed_event(
        organization=organization,
        event_type="decision.updated",
        event_id="evt-2",
        resource_type="decision",
        resource_id="decision-1",
    )

    replay = replay_organization_state_feed_events(
        organization_id=organization.id,
        after_state_version=1,
        event_types={"decision.updated"},
    )

    assert replay.full_resync_required is False
    assert replay.latest_state_version == 2
    assert [event["event_id"] for event in replay.events] == ["evt-2"]


def test_replay_organization_state_feed_requires_full_resync_on_gap(user) -> None:
    organization = user.default_organization
    for index in range(1, 4):
        record_organization_state_feed_event(
            organization=organization,
            event_type="overview.updated",
            event_id=f"evt-{index}",
            resource_type="overview",
            resource_id=str(organization.id),
        )
    OrganizationStateFeedEvent.objects.filter(
        organization=organization,
        state_version=2,
    ).delete()

    replay = replay_organization_state_feed_events(
        organization_id=organization.id,
        after_state_version=1,
    )

    assert replay.full_resync_required is True
    assert replay.reason == "replay_window_expired"


def test_replay_organization_state_feed_requires_full_resync_on_limit_overflow(user) -> None:
    organization = user.default_organization
    for index in range(1, 4):
        record_organization_state_feed_event(
            organization=organization,
            event_type="overview.updated",
            event_id=f"evt-limit-{index}",
            resource_type="overview",
            resource_id=str(organization.id),
        )

    replay = replay_organization_state_feed_events(
        organization_id=organization.id,
        after_state_version=1,
        replay_limit=1,
    )

    assert replay.full_resync_required is True
    assert replay.reason == "replay_window_exceeded"
    assert replay.latest_state_version == 3
