"""
Node type value objects.

Clean Architecture: Enterprise Business Rules layer.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any

from domain.value_objects.retry_policy import RetryPolicy


class NodeType(str, Enum):
    """Enumeration of supported node types."""

    PROMPT = "prompt"
    HTTP = "http"
    TRANSFORM = "transform"
    BRANCH = "branch"
    MERGE = "merge"
    HUMAN_GATE = "human_gate"
    OUTPUT = "output"

    @classmethod
    def is_valid(cls, value: str) -> bool:
        """Check if a value is a valid node type."""
        return value in cls._value2member_map_


@dataclass(frozen=True)
class NodeConfig:
    """Configuration for a node instance."""

    node_id: str
    node_type: NodeType
    name: str
    config: dict[str, Any]
    timeout_ms: int | None = None
    retry_policy: RetryPolicy | None = None

    def __post_init__(self):
        if not self.node_id:
            raise ValueError("node_id cannot be empty")
        if not self.name:
            raise ValueError("name cannot be empty")
