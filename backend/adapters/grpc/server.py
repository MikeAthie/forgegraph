from __future__ import annotations

import os
from concurrent import futures
from typing import Any, cast

import django
import grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc

from adapters.grpc.memory_service import MemoryService
from infrastructure.grpc import engine_pb2_grpc as engine_pb2_grpc_module

engine_pb2_grpc = cast(Any, engine_pb2_grpc_module)


def serve() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()

    host = os.getenv("MEMORY_GRPC_HOST", "0.0.0.0")
    port = os.getenv("MEMORY_GRPC_PORT", "50052")

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    engine_pb2_grpc.add_MemoryServiceServicer_to_server(MemoryService(), server)
    health_servicer = health.HealthServicer()
    health_servicer.set("memory", health_pb2.HealthCheckResponse.SERVING)
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
    server.add_insecure_port(f"{host}:{port}")
    server.start()
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
