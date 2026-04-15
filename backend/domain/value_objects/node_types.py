"""
Node type value objects.

Clean Architecture: Enterprise Business Rules layer.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from domain.value_objects.retry_policy import RetryPolicy


class NodeType(StrEnum):
    """Enumeration of supported node types."""

    AGENT = "agent"
    PROMPT = "prompt"
    HTTP = "http"
    TRANSFORM = "transform"
    BRANCH = "branch"
    MERGE = "merge"
    HUMAN_GATE = "human_gate"
    MEMORY = "memory"
    OBSERVATION_SAVE = "observation_save"
    OBSERVATION_SEARCH = "observation_search"
    OBSERVATION_CONTEXT = "observation_context"
    OBSERVATION_TIMELINE = "observation_timeline"
    TOOL = "tool"
    SUBGRAPH = "subgraph"
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

    def __post_init__(self) -> None:
        if not self.node_id:
            raise ValueError("node_id cannot be empty")
        if not self.name:
            raise ValueError("name cannot be empty")
