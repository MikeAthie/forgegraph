"""
gRPC client implementation for the ForgeGraph execution engine.

Clean Architecture: Interface Adapters layer.
This adapter implements IEngineClient using gRPC to communicate with the Go engine.
"""

import json
import logging
from typing import Any
from uuid import UUID

import grpc

from application.ports.services import IEngineClient
from infrastructure.grpc import (
    CancelRunRequest,
    EngineServiceStub,
    GetRunStatusRequest,
    PingRequest,
    ResumeRunRequest,
    StartRunRequest,
)

logger = logging.getLogger(__name__)


class EngineConnectionError(Exception):
    """Raised when connection to engine fails."""

    pass


class EngineExecutionError(Exception):
    """Raised when engine reports an execution error."""

    pass


class GrpcEngineClient(IEngineClient):
    """
    gRPC implementation of IEngineClient.

    Communicates with the Go execution engine to manage workflow runs.
    """

    def __init__(self, host: str = "localhost", port: int = 50051, callback_url: str = ""):
        """
        Initialize the gRPC engine client.

        Args:
            host: Engine host address
            port: Engine gRPC port
            callback_url: URL for engine to POST execution events back to
        """
        self.host = host
        self.port = port
        self.callback_url = callback_url
        self._channel: grpc.Channel | None = None
        self._stub: EngineServiceStub | None = None

    def _get_stub(self) -> EngineServiceStub:
        """Get or create the gRPC stub."""
        if self._channel is None:
            target = f"{self.host}:{self.port}"
            logger.info(f"Connecting to engine at {target}")
            self._channel = grpc.insecure_channel(target)
            self._stub = EngineServiceStub(self._channel)  # type: ignore
        assert self._stub is not None
        return self._stub

    def close(self) -> None:
        """Close the gRPC channel."""
        if self._channel is not None:
            self._channel.close()
            self._channel = None
            self._stub = None

    def __enter__(self) -> "GrpcEngineClient":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def ping(self) -> bool:
        """
        Check if the engine is healthy.

        Returns:
            True if engine is healthy and responding
        """
        try:
            stub = self._get_stub()
            request = PingRequest(message="ping")
            response = stub.Ping(request, timeout=5.0)
            return str(response.message) == "pong"
        except grpc.RpcError as e:
            logger.warning(f"Engine ping failed: {e}")
            return False

    def start_run(
        self,
        run_id: UUID,
        graph_json: dict[str, Any],
        input_json: dict[str, Any],
        memory_config_json: str | None = None,
        tenant_id: str | None = None,
        session_id: str | None = None,
    ) -> None:
        """
        Start a workflow run on the engine.

        Args:
            run_id: Unique identifier for this run
            graph_json: The graph definition
            input_json: Initial input variables

        Raises:
            EngineConnectionError: If connection to engine fails
            EngineExecutionError: If engine rejects the run
        """
        try:
            stub = self._get_stub()
            request = StartRunRequest(
                run_id=str(run_id),
                graph_json=json.dumps(graph_json),
                input_json=json.dumps(input_json) if input_json else "{}",
                callback_url=self.callback_url,
                memory_config_json=memory_config_json or "",
                tenant_id=tenant_id or "",
                session_id=session_id or "",
            )

            logger.info(f"Starting run {run_id} on engine")
            response = stub.StartRun(request, timeout=30.0)

            if not response.accepted:
                logger.error(f"Engine rejected run {run_id}: {response.error}")
                raise EngineExecutionError(response.error)

            logger.info(f"Run {run_id} accepted by engine")

        except grpc.RpcError as e:
            logger.error(f"Failed to start run {run_id}: {e}")
            raise EngineConnectionError(f"Failed to connect to engine: {e}") from e

    def cancel_run(self, run_id: UUID) -> None:
        """
        Cancel a running workflow.

        Args:
            run_id: The run ID to cancel

        Raises:
            EngineConnectionError: If connection to engine fails
            EngineExecutionError: If cancellation fails
        """
        try:
            stub = self._get_stub()
            request = CancelRunRequest(run_id=str(run_id))

            logger.info(f"Cancelling run {run_id}")
            response = stub.CancelRun(request, timeout=10.0)

            if not response.success:
                logger.error(f"Failed to cancel run {run_id}: {response.error}")
                raise EngineExecutionError(response.error)

            logger.info(f"Run {run_id} cancelled")

        except grpc.RpcError as e:
            logger.error(f"Failed to cancel run {run_id}: {e}")
            raise EngineConnectionError(f"Failed to connect to engine: {e}") from e

    def resume_run(
        self,
        run_id: UUID,
        node_id: str,
        input_json: dict[str, Any],
    ) -> None:
        """
        Resume a paused workflow (e.g., after human gate approval).

        Args:
            run_id: The run ID to resume
            node_id: The human gate node ID to resume from
            input_json: Human-provided input

        Raises:
            EngineConnectionError: If connection to engine fails
            EngineExecutionError: If resumption fails
        """
        try:
            stub = self._get_stub()
            request = ResumeRunRequest(
                run_id=str(run_id),
                node_id=node_id,
                input_json=json.dumps(input_json) if input_json else "{}",
            )

            logger.info(f"Resuming run {run_id} from node {node_id}")
            response = stub.ResumeRun(request, timeout=30.0)

            if not response.accepted:
                logger.error(f"Failed to resume run {run_id}: {response.error}")
                raise EngineExecutionError(response.error)

            logger.info(f"Run {run_id} resumed")

        except grpc.RpcError as e:
            logger.error(f"Failed to resume run {run_id}: {e}")
            raise EngineConnectionError(f"Failed to connect to engine: {e}") from e

    def get_run_status(self, run_id: UUID) -> dict[str, Any]:
        """
        Get the current status of a run from the engine.

        Args:
            run_id: The run ID to query

        Returns:
            Dictionary with status, current_node_id, and error (if any)

        Raises:
            EngineConnectionError: If connection to engine fails
        """
        try:
            stub = self._get_stub()
            request = GetRunStatusRequest(run_id=str(run_id))

            response = stub.GetRunStatus(request, timeout=10.0)

            return {
                "run_id": response.run_id,
                "status": response.status,
                "current_node_id": response.current_node_id or None,
                "error": response.error or None,
            }

        except grpc.RpcError as e:
            logger.error(f"Failed to get status for run {run_id}: {e}")
            raise EngineConnectionError(f"Failed to connect to engine: {e}") from e


class MockEngineClient(IEngineClient):
    """
    Mock implementation of IEngineClient for testing.

    Records all calls and allows configuring responses.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.ping_response: bool = True
        self.start_run_error: str | None = None
        self.cancel_run_error: str | None = None
        self.resume_run_error: str | None = None
        self.run_statuses: dict[str, dict[str, Any]] = {}

    def __enter__(self) -> "MockEngineClient":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass

    def ping(self) -> bool:
        self.calls.append(("ping", {}))
        return self.ping_response

    def start_run(
        self,
        run_id: UUID,
        graph_json: dict[str, Any],
        input_json: dict[str, Any],
        memory_config_json: str | None = None,
        tenant_id: str | None = None,
        session_id: str | None = None,
    ) -> None:
        self.calls.append(
            (
                "start_run",
                {
                    "run_id": run_id,
                    "graph_json": graph_json,
                    "input_json": input_json,
                    "memory_config_json": memory_config_json,
                    "tenant_id": tenant_id,
                    "session_id": session_id,
                },
            )
        )
        if self.start_run_error:
            raise EngineExecutionError(self.start_run_error)

    def cancel_run(self, run_id: UUID) -> None:
        self.calls.append(("cancel_run", {"run_id": run_id}))
        if self.cancel_run_error:
            raise EngineExecutionError(self.cancel_run_error)

    def resume_run(
        self,
        run_id: UUID,
        node_id: str,
        input_json: dict[str, Any],
    ) -> None:
        self.calls.append(
            (
                "resume_run",
                {"run_id": run_id, "node_id": node_id, "input_json": input_json},
            )
        )
        if self.resume_run_error:
            raise EngineExecutionError(self.resume_run_error)

    def get_run_status(self, run_id: UUID) -> dict[str, Any]:
        self.calls.append(("get_run_status", {"run_id": run_id}))
        return self.run_statuses.get(
            str(run_id),
            {"run_id": str(run_id), "status": "running", "current_node_id": None, "error": None},
        )

    def reset(self) -> None:
        """Reset all recorded calls and configured responses."""
        self.calls.clear()
        self.start_run_error = None
        self.cancel_run_error = None
        self.resume_run_error = None
        self.run_statuses.clear()
