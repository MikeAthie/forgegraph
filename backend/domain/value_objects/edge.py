"""
Edge value object.

Clean Architecture: Enterprise Business Rules layer.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class EdgeDefinition:
    """Definition of an edge connecting two nodes."""

    id: str
    from_node: str
    to_node: str
    condition: str | None = None
    label: str | None = None

    def __post_init__(self):
        if not self.id:
            raise ValueError("id cannot be empty")
        if not self.from_node:
            raise ValueError("from_node cannot be empty")
        if not self.to_node:
            raise ValueError("to_node cannot be empty")
        if self.from_node == self.to_node:
            raise ValueError("Edge cannot connect a node to itself")
