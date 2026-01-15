"""
Run-related domain events.

Clean Architecture: Enterprise Business Rules layer.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass
class RunEvent:
    """Base class for run-related events."""

    run_id: UUID
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class RunStarted(RunEvent):
    """Event emitted when a run starts."""

    graph_version_id: UUID = field(default=None)  # type: ignore


@dataclass
class RunCompleted(RunEvent):
    """Event emitted when a run completes successfully."""

    output: dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0


@dataclass
class RunFailed(RunEvent):
    """Event emitted when a run fails."""

    error_message: str = ""
    failed_node_id: str | None = None


@dataclass
class RunCanceled(RunEvent):
    """Event emitted when a run is canceled."""

    canceled_by: UUID | None = None


@dataclass
class RunPaused(RunEvent):
    """Event emitted when a run is paused (e.g., at human gate)."""

    paused_at_node: str = ""
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunResumed(RunEvent):
    """Event emitted when a paused run is resumed."""

    resumed_by: UUID | None = None
    input_provided: dict[str, Any] = field(default_factory=dict)


@dataclass
class NodeStarted(RunEvent):
    """Event emitted when a node starts executing."""

    node_id: str = ""
    node_type: str = ""
    attempt: int = 1


@dataclass
class NodeCompleted(RunEvent):
    """Event emitted when a node completes successfully."""

    node_id: str = ""
    node_type: str = ""
    output: dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0


@dataclass
class NodeFailed(RunEvent):
    """Event emitted when a node fails."""

    node_id: str = ""
    node_type: str = ""
    error: dict[str, Any] = field(default_factory=dict)
    attempt: int = 1
    will_retry: bool = False
