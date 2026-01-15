"""
Prompt DTOs.

Clean Architecture: Application Business Rules layer.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from domain.value_objects import PromptCategory, Visibility


@dataclass(frozen=True)
class CreatePromptInput:
    """Input for creating a prompt."""

    title: str
    content: str
    category: PromptCategory
    description: str = ""
    variables_schema: dict[str, Any] | None = None


@dataclass(frozen=True)
class UpdatePromptInput:
    """Input for updating a prompt."""

    title: str | None = None
    description: str | None = None
    content: str | None = None
    variables_schema: dict[str, Any] | None = None


@dataclass(frozen=True)
class PublishPromptInput:
    """Input for publishing a prompt."""

    license: str = "MIT"


@dataclass(frozen=True)
class PromptOutput:
    """Output representing a prompt."""

    id: UUID
    owner_id: UUID | None
    title: str
    description: str
    category: PromptCategory
    content: str
    variables_schema: dict[str, Any]
    version: str
    license: str
    visibility: Visibility
    is_builtin: bool
    created_at: datetime
    updated_at: datetime
