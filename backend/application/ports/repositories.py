"""
Repository interfaces (ports).

Clean Architecture: Application Business Rules layer.
These interfaces define how the application interacts with data persistence.
"""

from abc import ABC, abstractmethod
from uuid import UUID

from domain.entities import Graph, GraphVersion, NodeRun, PromptTemplate, Run, User
from domain.value_objects import PromptCategory, Visibility


class IUserRepository(ABC):
    """Interface for user data access."""

    @abstractmethod
    def get_by_id(self, user_id: UUID) -> User | None:
        """Get a user by ID."""
        ...

    @abstractmethod
    def get_by_email(self, email: str) -> User | None:
        """Get a user by email."""
        ...

    @abstractmethod
    def save(self, user: User) -> User:
        """Save a user (create or update)."""
        ...

    @abstractmethod
    def delete(self, user_id: UUID) -> None:
        """Delete a user."""
        ...


class IGraphRepository(ABC):
    """Interface for graph data access."""

    @abstractmethod
    def get_by_id(self, graph_id: UUID) -> Graph | None:
        """Get a graph by ID."""
        ...

    @abstractmethod
    def get_by_id_for_user(self, graph_id: UUID, user_id: UUID) -> Graph | None:
        """Get a graph by ID, ensuring it belongs to the user."""
        ...

    @abstractmethod
    def list_for_user(self, user_id: UUID, limit: int = 20, offset: int = 0) -> list[Graph]:
        """List graphs owned by a user."""
        ...

    @abstractmethod
    def count_for_user(self, user_id: UUID) -> int:
        """Count graphs owned by a user."""
        ...

    @abstractmethod
    def save(self, graph: Graph) -> Graph:
        """Save a graph (create or update)."""
        ...

    @abstractmethod
    def delete(self, graph_id: UUID) -> None:
        """Delete a graph and all its versions."""
        ...

    # GraphVersion methods
    @abstractmethod
    def get_version_by_id(self, version_id: UUID) -> GraphVersion | None:
        """Get a graph version by ID."""
        ...

    @abstractmethod
    def get_latest_version(self, graph_id: UUID) -> GraphVersion | None:
        """Get the latest version of a graph."""
        ...

    @abstractmethod
    def list_versions(self, graph_id: UUID) -> list[GraphVersion]:
        """List all versions of a graph."""
        ...

    @abstractmethod
    def get_next_version_number(self, graph_id: UUID) -> int:
        """Get the next version number for a graph."""
        ...

    @abstractmethod
    def save_version(self, version: GraphVersion) -> GraphVersion:
        """Save a graph version."""
        ...


class IPromptRepository(ABC):
    """Interface for prompt template data access."""

    @abstractmethod
    def get_by_id(self, prompt_id: UUID) -> PromptTemplate | None:
        """Get a prompt by ID."""
        ...

    @abstractmethod
    def list_for_user(
        self,
        user_id: UUID,
        category: PromptCategory | None = None,
        visibility: Visibility | None = None,
        include_builtin: bool = True,
        search: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[PromptTemplate]:
        """List prompts accessible to a user."""
        ...

    @abstractmethod
    def count_for_user(
        self,
        user_id: UUID,
        category: PromptCategory | None = None,
        visibility: Visibility | None = None,
        include_builtin: bool = True,
        search: str | None = None,
    ) -> int:
        """Count prompts accessible to a user."""
        ...

    @abstractmethod
    def list_builtin(
        self,
        category: PromptCategory | None = None,
    ) -> list[PromptTemplate]:
        """List built-in prompts."""
        ...

    @abstractmethod
    def save(self, prompt: PromptTemplate) -> PromptTemplate:
        """Save a prompt (create or update)."""
        ...

    @abstractmethod
    def delete(self, prompt_id: UUID) -> None:
        """Delete a prompt."""
        ...


class IRunRepository(ABC):
    """Interface for run data access."""

    @abstractmethod
    def get_by_id(self, run_id: UUID) -> Run | None:
        """Get a run by ID."""
        ...

    @abstractmethod
    def get_by_id_for_user(self, run_id: UUID, user_id: UUID) -> Run | None:
        """Get a run by ID, ensuring it belongs to the user."""
        ...

    @abstractmethod
    def list_for_user(
        self,
        user_id: UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Run]:
        """List runs owned by a user."""
        ...

    @abstractmethod
    def count_for_user(self, user_id: UUID) -> int:
        """Count runs owned by a user."""
        ...

    @abstractmethod
    def save(self, run: Run) -> Run:
        """Save a run (create or update)."""
        ...

    # NodeRun methods
    @abstractmethod
    def get_node_runs(self, run_id: UUID) -> list[NodeRun]:
        """Get all node runs for a run."""
        ...

    @abstractmethod
    def save_node_run(self, node_run: NodeRun) -> NodeRun:
        """Save a node run."""
        ...
