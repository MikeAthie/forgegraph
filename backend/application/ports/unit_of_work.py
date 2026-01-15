"""
Unit of Work interface (port).

Clean Architecture: Application Business Rules layer.
This interface defines transaction management.
"""

from abc import ABC, abstractmethod
from types import TracebackType

from application.ports.repositories import (
    IGraphRepository,
    IPromptRepository,
    IRunRepository,
    IUserRepository,
)


class IUnitOfWork(ABC):
    """
    Interface for Unit of Work pattern.

    Manages transactions and provides access to repositories.
    """

    users: IUserRepository
    graphs: IGraphRepository
    prompts: IPromptRepository
    runs: IRunRepository

    @abstractmethod
    def __enter__(self) -> "IUnitOfWork":
        """Enter the context manager."""
        ...

    @abstractmethod
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit the context manager."""
        ...

    @abstractmethod
    def commit(self) -> None:
        """Commit the transaction."""
        ...

    @abstractmethod
    def rollback(self) -> None:
        """Rollback the transaction."""
        ...
