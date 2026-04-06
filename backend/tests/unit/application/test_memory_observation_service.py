from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from django.utils import timezone

from application.services.memory_observation_service import MemoryObservationService
from application.services.vector_search_service import MemorySearchResult
from infrastructure.orm.models import MemoryChunk

pytestmark = pytest.mark.django_db


class FakeVectorSearchService:
    def __init__(self, results: list[MemorySearchResult]) -> None:
        self._results = results

    async def search(
        self,
        *,
        tenant_id: object,
        query: str,
        graph_id: object | None = None,
        agent_id: object | None = None,
        run_id: object | None = None,
        session_id: object | None = None,
        top_k: int = 5,
        threshold: float = 0.7,
        recency_weight: float = 0.2,
        model: str | None = None,
    ) -> list[MemorySearchResult]:
        return self._results


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


def test_create_observation_does_not_silently_overwrite_topic_without_update_flag(user) -> None:
    service = MemoryObservationService()
    graph_id = uuid4()

    original = service.create_observation(
        tenant_id=user.default_organization_id,
        graph_id=graph_id,
        type="fact",
        title="Customer Preference",
        content="Customer prefers email.",
        scope="graph",
        topic_key="contact-preference",
    )

    replacement = service.create_observation(
        tenant_id=user.default_organization_id,
        graph_id=graph_id,
        type="fact",
        title="Customer Preference",
        content="Customer now prefers SMS.",
        scope="graph",
        topic_key="contact-preference",
        update_topic=False,
    )

    original.refresh_from_db()
    assert replacement.id != original.id
    assert original.content == "Customer prefers email."
    assert replacement.content == "Customer now prefers SMS."
    assert original.revision_count == 1
    assert replacement.revision_count == 1


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


def test_get_context_uses_vector_hits_when_indexed_chunks_exist(user) -> None:
    service = MemoryObservationService()
    graph_id = uuid4()
    observation = service.create_observation(
        tenant_id=user.default_organization_id,
        graph_id=graph_id,
        session_id=uuid4(),
        type="fact",
        title="Support Preference",
        content="Jackie prefers concise summaries.",
        scope="graph",
    )
    chunk = MemoryChunk.objects.create(
        tenant_id=user.default_organization_id,
        session_id=observation.session_id,
        content=observation.content,
        chunk_type="observation",
        metadata={"observation_id": str(observation.id), "graph_id": str(graph_id)},
        embedding=[0.1] * 1536,
        embedding_model="text-embedding-ada-002",
        source_timestamp=timezone.now(),
    )
    observation.__class__.objects.filter(id=observation.id).update(memory_chunk_id=chunk.id)
    observation.refresh_from_db()

    vector_service = FakeVectorSearchService(
        [
            MemorySearchResult(
                content=observation.content,
                similarity=0.91,
                recency_score=1.0,
                combined_score=0.93,
                source_timestamp=timezone.now(),
                metadata={"observation_id": str(observation.id)},
            )
        ]
    )
    hybrid_service = MemoryObservationService(vector_search_service=vector_service)

    context = hybrid_service.get_context(
        tenant_id=user.default_organization_id,
        graph_id=graph_id,
        query="support summaries",
        limit=5,
    )

    assert context.degraded is False
    assert context.strategies == ["fts", "vector", "timeline"]
    assert [item.id for item in context.observations] == [observation.id]
