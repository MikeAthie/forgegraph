"""
Run DTOs.

Clean Architecture: Application Business Rules layer.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from domain.value_objects import NodeRunStatus, RunStatus


@dataclass(frozen=True)
class StartRunInput:
    """Input for starting a run."""

    graph_version_id: UUID
    input_json: dict[str, Any] | None = None


@dataclass(frozen=True)
class ResumeRunInput:
    """Input for resuming a paused run."""

    node_id: str
    input_json: dict[str, Any] | None = None


@dataclass(frozen=True)
class RunOutput:
    """Output representing a run."""

    id: UUID
    owner_id: UUID
    graph_version_id: UUID
    status: RunStatus
    started_at: datetime | None
    ended_at: datetime | None
    input_json: dict[str, Any]
    output_json: dict[str, Any] | None
    error_message: str
    duration_ms: int | None


@dataclass(frozen=True)
class NodeRunOutput:
    """Output representing a node run."""

    id: UUID
    run_id: UUID
    node_id: str
    node_type: str
    status: NodeRunStatus
    attempt: int
    started_at: datetime | None
    ended_at: datetime | None
    duration_ms: int | None
    input_json: dict[str, Any]
    output_json: dict[str, Any] | None
    error_json: dict[str, Any] | None
