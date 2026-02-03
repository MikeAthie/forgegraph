"""
Graph and GraphVersion entities.

Clean Architecture: Enterprise Business Rules layer.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4


@dataclass
class Graph:
    """Graph entity representing a workflow graph owned by a user."""

    id: UUID
    owner_id: UUID
    name: str
    description: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(cls, owner_id: UUID, name: str, description: str = "") -> "Graph":
        """Factory method to create a new graph."""
        now = datetime.utcnow()
        return cls(
            id=uuid4(),
            owner_id=owner_id,
            name=name.strip(),
            description=description.strip(),
            created_at=now,
            updated_at=now,
        )

    def update(self, name: str | None = None, description: str | None = None) -> None:
        """Update graph metadata."""
        if name is not None:
            self.name = name.strip()
        if description is not None:
            self.description = description.strip()
        self.updated_at = datetime.utcnow()


@dataclass
class GraphVersion:
    """GraphVersion entity representing a specific version of a graph."""

    id: UUID
    graph_id: UUID
    version: int
    graph_json: dict[str, Any]
    checksum: str
    created_at: datetime

    @classmethod
    def create(
        cls,
        graph_id: UUID,
        version: int,
        graph_json: dict[str, Any],
    ) -> "GraphVersion":
        """Factory method to create a new graph version."""
        checksum = cls._compute_checksum(graph_json)
        return cls(
            id=uuid4(),
            graph_id=graph_id,
            version=version,
            graph_json=graph_json,
            checksum=checksum,
            created_at=datetime.utcnow(),
        )

    @staticmethod
    def _compute_checksum(graph_json: dict[str, Any]) -> str:
        """Compute SHA256 checksum of the graph JSON."""
        json_str = json.dumps(graph_json, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(json_str.encode()).hexdigest()

    @property
    def nodes(self) -> list[dict[str, Any]]:
        """Get the list of nodes from the graph JSON."""
        nodes = self.graph_json.get("nodes", [])
        return list(nodes) if nodes else []

    @property
    def edges(self) -> list[dict[str, Any]]:
        """Get the list of edges from the graph JSON."""
        edges = self.graph_json.get("edges", [])
        return list(edges) if edges else []

    @property
    def metadata(self) -> dict[str, Any]:
        """Get the metadata from the graph JSON."""
        metadata = self.graph_json.get("metadata", {})
        return dict(metadata) if metadata else {}
