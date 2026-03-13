from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from application.services.embedding_service import EmbeddingService
from application.services.memory_observation_indexing import (
    MemoryObservationIndexingService,
)
from infrastructure.orm.models import MemoryChunk, MemoryObservation

pytestmark = pytest.mark.django_db


class FakeEmbedder(EmbeddingService):
    async def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        return [[0.25] * 1536 for _ in texts]

    def dimension(self) -> int:
        return 1536


def test_upsert_observation_creates_chunk_and_links_metadata(user) -> None:
    observation = MemoryObservation.objects.create(
        tenant_id=user.default_organization_id,
        graph_id=uuid4(),
        session_id=uuid4(),
        type="fact",
        title="Preference",
        content="Jackie prefers concise summaries.",
        scope="graph",
        topic_key="jackie-preference",
        last_seen_at=datetime.now(UTC),
    )

    service = MemoryObservationIndexingService(FakeEmbedder())
    chunk = service.upsert_observation(observation_id=observation.id)

    observation.refresh_from_db()
    assert chunk is not None
    assert observation.memory_chunk_id == chunk.id
    assert chunk.chunk_type == "observation"
    assert chunk.metadata["observation_id"] == str(observation.id)
    assert chunk.metadata["topic_key"] == "jackie-preference"
    assert chunk.metadata["graph_id"] == str(observation.graph_id)
    assert chunk.content == "Preference\n\nJackie prefers concise summaries."


def test_upsert_observation_updates_existing_chunk(user) -> None:
    observation = MemoryObservation.objects.create(
        tenant_id=user.default_organization_id,
        graph_id=uuid4(),
        session_id=uuid4(),
        type="fact",
        title="Preference",
        content="Jackie prefers tea.",
        scope="graph",
        topic_key="jackie-preference",
        last_seen_at=datetime.now(UTC),
    )
    original_chunk = MemoryChunk.objects.create(
        tenant_id=user.default_organization_id,
        session_id=observation.session_id,
        content="stale",
        chunk_type="observation",
        metadata={"observation_id": str(observation.id)},
        embedding=[0.1] * 1536,
        embedding_model="text-embedding-ada-002",
        source_timestamp=datetime.now(UTC),
    )
    observation.memory_chunk = original_chunk
    observation.save(update_fields=["memory_chunk", "updated_at"])

    observation.content = "Jackie prefers oat milk tea."
    observation.save(update_fields=["content", "updated_at"])

    service = MemoryObservationIndexingService(FakeEmbedder())
    updated_chunk = service.upsert_observation(observation_id=observation.id)

    assert updated_chunk is not None
    assert updated_chunk.id == original_chunk.id
    assert updated_chunk.content == "Preference\n\nJackie prefers oat milk tea."
    assert updated_chunk.metadata["title"] == "Preference"


def test_delete_observation_index_removes_chunk_and_unlinks(user) -> None:
    observation = MemoryObservation.objects.create(
        tenant_id=user.default_organization_id,
        graph_id=uuid4(),
        session_id=uuid4(),
        type="fact",
        title="Preference",
        content="Jackie prefers tea.",
        scope="graph",
        topic_key="jackie-preference",
    )
    chunk = MemoryChunk.objects.create(
        tenant_id=user.default_organization_id,
        session_id=observation.session_id,
        content="Preference\n\nJackie prefers tea.",
        chunk_type="observation",
        metadata={"observation_id": str(observation.id)},
        embedding=[0.1] * 1536,
        embedding_model="text-embedding-ada-002",
        source_timestamp=datetime.now(UTC),
    )
    observation.memory_chunk = chunk
    observation.save(update_fields=["memory_chunk", "updated_at"])

    service = MemoryObservationIndexingService(FakeEmbedder())
    deleted = service.delete_observation_index(observation_id=observation.id)

    observation.refresh_from_db()
    assert deleted is True
    assert observation.memory_chunk_id is None
    assert not MemoryChunk.objects.filter(id=chunk.id).exists()
