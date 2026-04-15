"""
Run status value objects.

Clean Architecture: Enterprise Business Rules layer.
"""

from enum import StrEnum


class RunStatus(StrEnum):
    """Status of a workflow run."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"


class NodeRunStatus(StrEnum):
    """Status of a node execution within a run."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
