from __future__ import annotations

import pytest

from application.services.organization_state_feed import (
    record_organization_state_feed_event,
    replay_organization_state_feed_events,
)

pytestmark = pytest.mark.django_db


def test_org_state_feed_replay_uses_backend_owned_state_versions(user) -> None:
    organization = user.default_organization
    first = record_organization_state_feed_event(
        organization=organization,
        event_type="overview.updated",
        event_id="evt-org-feed-1",
        resource_type="overview",
        resource_id=str(organization.id),
    )
    second = record_organization_state_feed_event(
        organization=organization,
        event_type="task.updated",
        event_id="evt-org-feed-2",
        resource_type="task",
        resource_id="task-1",
    )

    replay = replay_organization_state_feed_events(
        organization_id=organization.id,
        after_state_version=first["state_version"],
    )

    assert second["state_version"] == first["state_version"] + 1
    assert replay.full_resync_required is False
    assert replay.latest_state_version == second["state_version"]
    assert [event["event_id"] for event in replay.events] == ["evt-org-feed-2"]
