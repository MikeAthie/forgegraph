from concurrent import futures

import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc


def test_memory_grpc_health_probe_serving():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    health_servicer = health.HealthServicer()
    health_servicer.set("memory", health_pb2.HealthCheckResponse.SERVING)
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)

    port = server.add_insecure_port("localhost:0")
    server.start()

    try:
        with grpc.insecure_channel(f"localhost:{port}") as channel:
            stub = health_pb2_grpc.HealthStub(channel)
            response = stub.Check(health_pb2.HealthCheckRequest(service="memory"), timeout=0.2)

        assert response.status == health_pb2.HealthCheckResponse.SERVING
    finally:
        server.stop(0)
