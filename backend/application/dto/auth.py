"""
Authentication DTOs.

Clean Architecture: Application Business Rules layer.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class RegisterInput:
    """Input for user registration."""

    email: str
    password: str


@dataclass(frozen=True)
class LoginInput:
    """Input for user login."""

    email: str
    password: str


@dataclass(frozen=True)
class UserOutput:
    """Output representing a user."""

    id: UUID
    email: str
    created_at: datetime
    is_active: bool


@dataclass(frozen=True)
class TokenOutput:
    """Output representing authentication tokens."""

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
