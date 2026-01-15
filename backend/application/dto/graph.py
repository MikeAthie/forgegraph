"""
Graph DTOs.

Clean Architecture: Application Business Rules layer.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class CreateGraphInput:
    """Input for creating a graph."""

    name: str
    description: str = ""


@dataclass(frozen=True)
class UpdateGraphInput:
    """Input for updating a graph."""

    name: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class GraphOutput:
    """Output representing a graph."""

    id: UUID
    owner_id: UUID
    name: str
    description: str
    created_at: datetime
    updated_at: datetime
    version_count: int = 0
    latest_version: int | None = None


@dataclass(frozen=True)
class CreateGraphVersionInput:
    """Input for creating a graph version."""

    graph_json: dict[str, Any]


@dataclass(frozen=True)
class GraphVersionOutput:
    """Output representing a graph version."""

    id: UUID
    graph_id: UUID
    version: int
    graph_json: dict[str, Any]
    checksum: str
    created_at: datetime
