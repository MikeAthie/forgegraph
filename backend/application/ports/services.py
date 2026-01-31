"""
Service interfaces (ports).

Clean Architecture: Application Business Rules layer.
These interfaces define external services the application depends on.
"""

from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID


class IPasswordHasher(ABC):
    """Interface for password hashing service."""

    @abstractmethod
    def hash(self, password: str) -> str:
        """Hash a password."""
        ...

    @abstractmethod
    def verify(self, password: str, hashed: str) -> bool:
        """Verify a password against a hash."""
        ...


class IEngineClient(ABC):
    """Interface for communication with the Go execution engine."""

    @abstractmethod
    def ping(self) -> bool:
        """Check if the engine is healthy."""
        ...

    @abstractmethod
    def start_run(
        self,
        run_id: UUID,
        graph_json: dict[str, Any],
        input_json: dict[str, Any],
        memory_config_json: str | None = None,
        tenant_id: str | None = None,
        session_id: str | None = None,
    ) -> None:
        """Start a workflow run on the engine."""
        ...

    @abstractmethod
    def cancel_run(self, run_id: UUID) -> None:
        """Cancel a running workflow."""
        ...

    @abstractmethod
    def resume_run(
        self,
        run_id: UUID,
        node_id: str,
        input_json: dict[str, Any],
    ) -> None:
        """Resume a paused workflow (e.g., after human gate approval)."""
        ...

    @abstractmethod
    def get_run_status(self, run_id: UUID) -> dict[str, Any]:
        """Get the current status of a run from the engine."""
        ...
