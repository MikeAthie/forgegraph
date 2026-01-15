"""
Run and NodeRun entities.

Clean Architecture: Enterprise Business Rules layer.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from domain.value_objects.run_status import NodeRunStatus, RunStatus


@dataclass
class Run:
    """Run entity representing an execution of a graph."""

    id: UUID
    owner_id: UUID
    graph_version_id: UUID
    status: RunStatus
    started_at: datetime | None
    ended_at: datetime | None
    input_json: dict[str, Any]
    output_json: dict[str, Any] | None
    error_message: str

    @classmethod
    def create(
        cls,
        owner_id: UUID,
        graph_version_id: UUID,
        input_json: dict[str, Any] | None = None,
    ) -> "Run":
        """Factory method to create a new run."""
        return cls(
            id=uuid4(),
            owner_id=owner_id,
            graph_version_id=graph_version_id,
            status=RunStatus.PENDING,
            started_at=None,
            ended_at=None,
            input_json=input_json or {},
            output_json=None,
            error_message="",
        )

    def start(self) -> None:
        """Mark the run as started."""
        self.status = RunStatus.RUNNING
        self.started_at = datetime.utcnow()

    def pause(self) -> None:
        """Pause the run (e.g., for human gate)."""
        self.status = RunStatus.PAUSED

    def resume(self) -> None:
        """Resume a paused run."""
        self.status = RunStatus.RUNNING

    def succeed(self, output_json: dict[str, Any]) -> None:
        """Mark the run as succeeded."""
        self.status = RunStatus.SUCCEEDED
        self.output_json = output_json
        self.ended_at = datetime.utcnow()

    def fail(self, error_message: str) -> None:
        """Mark the run as failed."""
        self.status = RunStatus.FAILED
        self.error_message = error_message
        self.ended_at = datetime.utcnow()

    def cancel(self) -> None:
        """Cancel the run."""
        self.status = RunStatus.CANCELED
        self.ended_at = datetime.utcnow()

    @property
    def is_terminal(self) -> bool:
        """Check if the run is in a terminal state."""
        return self.status in (RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELED)

    @property
    def duration_ms(self) -> int | None:
        """Calculate the run duration in milliseconds."""
        if self.started_at is None or self.ended_at is None:
            return None
        delta = self.ended_at - self.started_at
        return int(delta.total_seconds() * 1000)


@dataclass
class NodeRun:
    """NodeRun entity representing the execution of a single node."""

    id: UUID
    run_id: UUID
    node_id: str
    node_type: str
    status: NodeRunStatus
    attempt: int
    started_at: datetime | None
    ended_at: datetime | None
    input_json: dict[str, Any]
    output_json: dict[str, Any] | None
    error_json: dict[str, Any] | None

    @classmethod
    def create(
        cls,
        run_id: UUID,
        node_id: str,
        node_type: str,
        input_json: dict[str, Any] | None = None,
        attempt: int = 1,
    ) -> "NodeRun":
        """Factory method to create a new node run."""
        return cls(
            id=uuid4(),
            run_id=run_id,
            node_id=node_id,
            node_type=node_type,
            status=NodeRunStatus.PENDING,
            attempt=attempt,
            started_at=None,
            ended_at=None,
            input_json=input_json or {},
            output_json=None,
            error_json=None,
        )

    def start(self) -> None:
        """Mark the node run as started."""
        self.status = NodeRunStatus.RUNNING
        self.started_at = datetime.utcnow()

    def succeed(self, output_json: dict[str, Any]) -> None:
        """Mark the node run as succeeded."""
        self.status = NodeRunStatus.SUCCEEDED
        self.output_json = output_json
        self.ended_at = datetime.utcnow()

    def fail(self, error_json: dict[str, Any]) -> None:
        """Mark the node run as failed."""
        self.status = NodeRunStatus.FAILED
        self.error_json = error_json
        self.ended_at = datetime.utcnow()

    def skip(self) -> None:
        """Mark the node run as skipped."""
        self.status = NodeRunStatus.SKIPPED
        self.ended_at = datetime.utcnow()

    @property
    def duration_ms(self) -> int | None:
        """Calculate the node run duration in milliseconds."""
        if self.started_at is None or self.ended_at is None:
            return None
        delta = self.ended_at - self.started_at
        return int(delta.total_seconds() * 1000)
