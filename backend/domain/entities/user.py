"""
User entity.

Clean Architecture: Enterprise Business Rules layer.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4


@dataclass
class User:
    """User entity representing a registered user."""

    id: UUID
    email: str
    created_at: datetime
    is_active: bool = True

    @classmethod
    def create(cls, email: str) -> "User":
        """Factory method to create a new user."""
        return cls(
            id=uuid4(),
            email=email.lower().strip(),
            created_at=datetime.utcnow(),
            is_active=True,
        )

    def deactivate(self) -> None:
        """Deactivate the user account."""
        self.is_active = False

    def activate(self) -> None:
        """Activate the user account."""
        self.is_active = True
