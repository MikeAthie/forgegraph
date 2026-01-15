"""
Run status value objects.

Clean Architecture: Enterprise Business Rules layer.
"""

from enum import Enum


class RunStatus(str, Enum):
    """Status of a workflow run."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"


class NodeRunStatus(str, Enum):
    """Status of a node execution within a run."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
