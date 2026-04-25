import json
from concurrent import futures
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

import grpc
import pytest

from adapters.grpc.memory_service import MemoryService
from application.services.vector_search_service import MemorySearchResult, VectorSearchService
from infrastructure.grpc import engine_pb2, engine_pb2_grpc


class FakeVectorSearchService(VectorSearchService):
    """
    Fake implementation of VectorSearchService to satisfy type checking.
    """

    def __init__(self, results: list[MemorySearchResult]):
        self._results = results
        self.last_kwargs: dict[str, Any] | None = None

    async def search(self, **kwargs: Any) -> list[MemorySearchResult]:
        self.last_kwargs = kwargs
        return self._results


def _start_server(service: MemoryService) -> tuple[grpc.Server, int]:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    # Removed the type: ignore as Mypy now recognizes this call
    engine_pb2_grpc.add_MemoryServiceServicer_to_server(service, server)
    port = server.add_insecure_port("localhost:0")
    server.start()
    return server, port


def test_memory_service_retrieve_memory_returns_chunks() -> None:
    now = datetime.now(UTC)
    results = [
        MemorySearchResult(
            content="Remember to call Sam",
            similarity=0.82,
            source_timestamp=now,
            metadata={"source": "chat"},
            recency_score=1.0,
            combined_score=0.82,
        )
    ]
    service = MemoryService(search_service=FakeVectorSearchService(results))
    server, port = _start_server(service)

    try:
        with grpc.insecure_channel(f"localhost:{port}") as channel:
            stub = engine_pb2_grpc.MemoryServiceStub(channel)

            engine_pb2_any = cast(Any, engine_pb2)
            RequestClass = engine_pb2_any.RetrieveMemoryRequest
            request = RequestClass(tenant_id="t1", query="call Sam")

            response = stub.RetrieveMemory(request)

        assert response.error == ""
        assert len(response.chunks) == 1
        chunk = response.chunks[0]
        assert chunk.content == "Remember to call Sam"
        assert chunk.score == 0.82
        assert json.loads(chunk.metadata_json) == {"source": "chat"}
    finally:
        server.stop(0)


def test_memory_service_requires_tenant_and_query() -> None:
    service = MemoryService(search_service=FakeVectorSearchService([]))
    server, port = _start_server(service)

    try:
        with grpc.insecure_channel(f"localhost:{port}") as channel:
            stub = engine_pb2_grpc.MemoryServiceStub(channel)

            engine_pb2_any = cast(Any, engine_pb2)
            RequestClass = engine_pb2_any.RetrieveMemoryRequest
            request = RequestClass(tenant_id="", query="")

            response = stub.RetrieveMemory(request)

        assert response.error != ""
    finally:
        server.stop(0)


def test_memory_service_retrieve_memory_forwards_scope_filters() -> None:
    now = datetime.now(UTC)
    fake_search = FakeVectorSearchService(
        [
            MemorySearchResult(
                content="Scoped memory",
                similarity=0.91,
                source_timestamp=now,
                metadata={"source": "chat"},
                recency_score=1.0,
                combined_score=0.91,
            )
        ]
    )
    service = MemoryService(search_service=fake_search)
    server, port = _start_server(service)

    try:
        with grpc.insecure_channel(f"localhost:{port}") as channel:
            stub = engine_pb2_grpc.MemoryServiceStub(channel)

            engine_pb2_any = cast(Any, engine_pb2)
            response = stub.RetrieveMemory(
                engine_pb2_any.RetrieveMemoryRequest(
                    tenant_id="tenant-1",
                    query="renewal risk",
                    agent_id="agent-1",
                    run_id="run-1",
                    session_id="session-1",
                    top_k=3,
                )
            )

        assert response.error == ""
        assert fake_search.last_kwargs is not None
        assert fake_search.last_kwargs["tenant_id"] == "tenant-1"
        assert fake_search.last_kwargs["agent_id"] == "agent-1"
        assert fake_search.last_kwargs["run_id"] == "run-1"
        assert fake_search.last_kwargs["session_id"] == "session-1"
        assert fake_search.last_kwargs["top_k"] == 3
    finally:
        server.stop(0)


@pytest.mark.django_db
def test_memory_service_save_get_search_context_and_timeline(user) -> None:
    service = MemoryService(search_service=FakeVectorSearchService([]))
    server, port = _start_server(service)
    graph_id = uuid4()
    run_id = uuid4()
    session_id = uuid4()

    try:
        with grpc.insecure_channel(f"localhost:{port}") as channel:
            stub = engine_pb2_grpc.MemoryServiceStub(channel)
            engine_pb2_any = cast(Any, engine_pb2)

            save_request = engine_pb2_any.SaveObservationRequest(
                tenant_id=str(user.default_organization_id),
                graph_id=str(graph_id),
                run_id=str(run_id),
                session_id=str(session_id),
                type="fact",
                title="Sam preference",
                content="Sam prefers SMS reminders",
                scope="session",
                topic_key="sam-preference",
            )
            save_response = stub.SaveObservation(save_request)

            assert save_response.error == ""
            assert save_response.observation.title == "Sam preference"
            observation_id = save_response.observation.id

            get_response = stub.GetObservation(
                engine_pb2_any.GetObservationRequest(
                    tenant_id=str(user.default_organization_id),
                    observation_id=observation_id,
                )
            )

            assert get_response.error == ""
            assert get_response.observation.content == "Sam prefers SMS reminders"

            search_response = stub.SearchObservations(
                engine_pb2_any.SearchObservationsRequest(
                    tenant_id=str(user.default_organization_id),
                    query="SMS reminders",
                    session_id=str(session_id),
                )
            )

            assert search_response.error == ""
            assert [item.id for item in search_response.observations] == [observation_id]

            context_response = stub.GetContext(
                engine_pb2_any.GetContextRequest(
                    tenant_id=str(user.default_organization_id),
                    session_id=str(session_id),
                    query="SMS",
                )
            )

            assert context_response.error == ""
            assert context_response.degraded is True
            assert list(context_response.strategies) == ["fts", "timeline"]
            assert [item.id for item in context_response.observations] == [observation_id]

            timeline_response = stub.GetTimeline(
                engine_pb2_any.GetTimelineRequest(
                    tenant_id=str(user.default_organization_id),
                    session_id=str(session_id),
                )
            )

            assert timeline_response.error == ""
            assert [item.id for item in timeline_response.observations] == [observation_id]
    finally:
        server.stop(0)


@pytest.mark.django_db
def test_memory_service_save_observation_updates_existing_record(user) -> None:
    service = MemoryService(search_service=FakeVectorSearchService([]))
    server, port = _start_server(service)
    session_id = uuid4()

    try:
        with grpc.insecure_channel(f"localhost:{port}") as channel:
            stub = engine_pb2_grpc.MemoryServiceStub(channel)
            engine_pb2_any = cast(Any, engine_pb2)

            create_response = stub.SaveObservation(
                engine_pb2_any.SaveObservationRequest(
                    tenant_id=str(user.default_organization_id),
                    session_id=str(session_id),
                    type="fact",
                    title="Name",
                    content="Sam",
                    scope="session",
                )
            )
            assert create_response.error == ""

            update_response = stub.SaveObservation(
                engine_pb2_any.SaveObservationRequest(
                    tenant_id=str(user.default_organization_id),
                    observation_id=create_response.observation.id,
                    title="Preferred contact",
                    content="Sam prefers SMS reminders",
                    topic_key="sam-contact",
                )
            )

            assert update_response.error == ""
            assert update_response.observation.id == create_response.observation.id
            assert update_response.observation.title == "Preferred contact"
            assert update_response.observation.content == "Sam prefers SMS reminders"
            assert update_response.observation.topic_key == "sam-contact"
            assert update_response.observation.revision_count == 2
    finally:
        server.stop(0)


@pytest.mark.django_db
def test_memory_service_save_observation_dedupes_exact_retries(user) -> None:
    service = MemoryService(search_service=FakeVectorSearchService([]))
    server, port = _start_server(service)
    graph_id = uuid4()
    run_id = uuid4()
    session_id = uuid4()

    try:
        with grpc.insecure_channel(f"localhost:{port}") as channel:
            stub = engine_pb2_grpc.MemoryServiceStub(channel)
            engine_pb2_any = cast(Any, engine_pb2)

            request = engine_pb2_any.SaveObservationRequest(
                tenant_id=str(user.default_organization_id),
                graph_id=str(graph_id),
                run_id=str(run_id),
                session_id=str(session_id),
                type="fact",
                title="Renewal note",
                content="Customer asked for a concise renewal summary.",
                scope="session",
            )

            first = stub.SaveObservation(request)
            second = stub.SaveObservation(request)

        assert first.error == ""
        assert second.error == ""
        assert second.observation.id == first.observation.id
        assert second.observation.duplicate_count == 1
    finally:
        server.stop(0)


@pytest.mark.django_db
def test_memory_service_observation_methods_require_tenant(user) -> None:
    service = MemoryService(search_service=FakeVectorSearchService([]))
    server, port = _start_server(service)

    try:
        with grpc.insecure_channel(f"localhost:{port}") as channel:
            stub = engine_pb2_grpc.MemoryServiceStub(channel)
            engine_pb2_any = cast(Any, engine_pb2)

            save_response = stub.SaveObservation(
                engine_pb2_any.SaveObservationRequest(
                    tenant_id="",
                    session_id=str(uuid4()),
                    type="fact",
                    content="Missing tenant",
                    scope="session",
                )
            )
            search_response = stub.SearchObservations(
                engine_pb2_any.SearchObservationsRequest(tenant_id="")
            )
            get_response = stub.GetObservation(
                engine_pb2_any.GetObservationRequest(tenant_id="", observation_id=str(uuid4()))
            )
            context_response = stub.GetContext(engine_pb2_any.GetContextRequest(tenant_id=""))
            timeline_response = stub.GetTimeline(engine_pb2_any.GetTimelineRequest(tenant_id=""))

        assert save_response.error == "tenant_id is required"
        assert search_response.error == "tenant_id is required"
        assert get_response.error == "tenant_id is required"
        assert context_response.error == "tenant_id is required"
        assert timeline_response.error == "tenant_id is required"
    finally:
        server.stop(0)
