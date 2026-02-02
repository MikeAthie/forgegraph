import json
from concurrent import futures
from datetime import UTC, datetime

import grpc

from adapters.grpc.memory_service import MemoryService
from application.services.vector_search_service import MemorySearchResult
from infrastructure.grpc import engine_pb2, engine_pb2_grpc


class FakeVectorSearchService:
    def __init__(self, results):
        self._results = results

    async def search(self, **_kwargs):
        return self._results


def _start_server(service):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    engine_pb2_grpc.add_MemoryServiceServicer_to_server(service, server)
    port = server.add_insecure_port("localhost:0")
    server.start()
    return server, port


def test_memory_service_retrieve_memory_returns_chunks():
    now = datetime.now(UTC)
    results = [
        MemorySearchResult(
            content="Remember to call Sam",
            similarity=0.82,
            source_timestamp=now,
            metadata={"source": "chat"},
        )
    ]
    service = MemoryService(search_service=FakeVectorSearchService(results))
    server, port = _start_server(service)

    try:
        with grpc.insecure_channel(f"localhost:{port}") as channel:
            stub = engine_pb2_grpc.MemoryServiceStub(channel)
            response = stub.RetrieveMemory(
                engine_pb2.RetrieveMemoryRequest(tenant_id="t1", query="call Sam")
            )

        assert response.error == ""
        assert len(response.chunks) == 1
        chunk = response.chunks[0]
        assert chunk.content == "Remember to call Sam"
        assert chunk.score == 0.82
        assert json.loads(chunk.metadata_json) == {"source": "chat"}
    finally:
        server.stop(0)


def test_memory_service_requires_tenant_and_query():
    service = MemoryService(search_service=FakeVectorSearchService([]))
    server, port = _start_server(service)

    try:
        with grpc.insecure_channel(f"localhost:{port}") as channel:
            stub = engine_pb2_grpc.MemoryServiceStub(channel)
            response = stub.RetrieveMemory(engine_pb2.RetrieveMemoryRequest(tenant_id="", query=""))

        assert response.error
    finally:
        server.stop(0)
