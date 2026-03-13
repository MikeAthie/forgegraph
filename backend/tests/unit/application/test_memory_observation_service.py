from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from django.utils import timezone

from application.services.memory_observation_service import MemoryObservationService

pytestmark = pytest.mark.django_db


def test_create_observation_normalizes_fields(user) -> None:
    service = MemoryObservationService()

    observation = service.create_observation(
        tenant_id=user.default_organization_id,
        graph_id=uuid4(),
        type=" User Preference ",
        title="  Favorite Snack  ",
        content="  Loves tacos.  ",
        scope="graph",
        topic_key=" Favorite Snack ",
        tool_name=" CRM Lookup ",
    )

    assert observation.type == "user_preference"
    assert observation.title == "Favorite Snack"
    assert observation.content == "Loves tacos."
    assert observation.topic_key == "favorite-snack"
    assert observation.tool_name == "crm_lookup"


def test_create_observation_dedupes_exact_matches(user) -> None:
    service = MemoryObservationService()
    graph_id = uuid4()

    first = service.create_observation(
        tenant_id=user.default_organization_id,
        graph_id=graph_id,
        type="fact",
        title="Preference",
        content="Jackie prefers tea.",
        scope="graph",
    )

    second = service.create_observation(
        tenant_id=user.default_organization_id,
        graph_id=graph_id,
        type="fact",
        title="Preference",
        content="Jackie prefers tea.",
        scope="graph",
    )

    first.refresh_from_db()
    assert second.id == first.id
    assert first.duplicate_count == 1


def test_create_observation_updates_existing_topic_when_requested(user) -> None:
    service = MemoryObservationService()
    graph_id = uuid4()

    original = service.create_observation(
        tenant_id=user.default_organization_id,
        graph_id=graph_id,
        type="fact",
        title="Coffee Order",
        content="Jackie wants a latte.",
        scope="graph",
        topic_key="jackie-drink",
    )

    updated = service.create_observation(
        tenant_id=user.default_organization_id,
        graph_id=graph_id,
        type="fact",
        title="Coffee Order",
        content="Jackie wants an oat milk latte.",
        scope="graph",
        topic_key="jackie-drink",
        update_topic=True,
    )

    original.refresh_from_db()
    assert updated.id == original.id
    assert original.content == "Jackie wants an oat milk latte."
    assert original.revision_count == 2


def test_delete_observation_soft_deletes_and_hides_from_search(user) -> None:
    service = MemoryObservationService()
    graph_id = uuid4()
    observation = service.create_observation(
        tenant_id=user.default_organization_id,
        graph_id=graph_id,
        type="fact",
        title="Delete Me",
        content="Temporary note.",
        scope="graph",
    )

    deleted = service.delete_observation(
        tenant_id=user.default_organization_id,
        observation_id=observation.id,
    )

    assert deleted.deleted_at is not None
    assert (
        service.search_observations(
            tenant_id=user.default_organization_id,
            graph_id=graph_id,
            query="Temporary",
        )
        == []
    )
    assert (
        service.get_observation(
            tenant_id=user.default_organization_id,
            observation_id=observation.id,
            include_deleted=True,
        ).id
        == observation.id
    )


def test_get_timeline_orders_by_last_seen_desc(user) -> None:
    service = MemoryObservationService()
    graph_id = uuid4()
    older = service.create_observation(
        tenant_id=user.default_organization_id,
        graph_id=graph_id,
        type="fact",
        title="Older",
        content="First note.",
        scope="graph",
    )
    newer = service.create_observation(
        tenant_id=user.default_organization_id,
        graph_id=graph_id,
        type="fact",
        title="Newer",
        content="Second note.",
        scope="graph",
    )

    now = timezone.now()
    older.__class__.objects.filter(id=older.id).update(last_seen_at=now - timedelta(hours=1))
    newer.__class__.objects.filter(id=newer.id).update(last_seen_at=now)

    timeline = service.get_timeline(
        tenant_id=user.default_organization_id,
        graph_id=graph_id,
    )

    assert [item.id for item in timeline[:2]] == [newer.id, older.id]


def test_search_observations_is_tenant_isolated(user) -> None:
    service = MemoryObservationService()
    other_tenant_id = uuid4()
    graph_id = uuid4()

    service.create_observation(
        tenant_id=other_tenant_id,
        graph_id=graph_id,
        type="fact",
        title="Other Tenant",
        content="Should stay isolated.",
        scope="graph",
    )

    results = service.search_observations(
        tenant_id=user.default_organization_id,
        graph_id=graph_id,
        query="isolated",
    )

    assert results == []
