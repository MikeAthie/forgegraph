"""
PromptTemplate entity.

Clean Architecture: Enterprise Business Rules layer.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from domain.value_objects.prompt_category import PromptCategory
from domain.value_objects.visibility import Visibility


@dataclass
class PromptTemplate:
    """PromptTemplate entity representing a reusable prompt template."""

    id: UUID
    owner_id: UUID | None  # None for built-in prompts
    title: str
    description: str
    category: PromptCategory
    content: str
    variables_schema: dict[str, Any]
    version: str
    license: str
    visibility: Visibility
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        title: str,
        content: str,
        category: PromptCategory,
        owner_id: UUID | None = None,
        description: str = "",
        variables_schema: dict[str, Any] | None = None,
        version: str = "1.0.0",
        license: str = "MIT",
        visibility: Visibility = Visibility.PRIVATE,
    ) -> "PromptTemplate":
        """Factory method to create a new prompt template."""
        now = datetime.utcnow()
        return cls(
            id=uuid4(),
            owner_id=owner_id,
            title=title.strip(),
            description=description.strip(),
            category=category,
            content=content,
            variables_schema=variables_schema or {},
            version=version,
            license=license,
            visibility=visibility,
            created_at=now,
            updated_at=now,
        )

    @classmethod
    def create_builtin(
        cls,
        title: str,
        content: str,
        category: PromptCategory,
        description: str = "",
        variables_schema: dict[str, Any] | None = None,
    ) -> "PromptTemplate":
        """Factory method to create a built-in prompt template."""
        return cls.create(
            title=title,
            content=content,
            category=category,
            owner_id=None,
            description=description,
            variables_schema=variables_schema,
            visibility=Visibility.PUBLIC,
        )

    @property
    def is_builtin(self) -> bool:
        """Check if this is a built-in prompt (no owner)."""
        return self.owner_id is None

    def update(
        self,
        title: str | None = None,
        description: str | None = None,
        content: str | None = None,
        variables_schema: dict[str, Any] | None = None,
    ) -> None:
        """Update prompt template fields."""
        if title is not None:
            self.title = title.strip()
        if description is not None:
            self.description = description.strip()
        if content is not None:
            self.content = content
        if variables_schema is not None:
            self.variables_schema = variables_schema
        self.updated_at = datetime.utcnow()

    def publish(self, license: str = "MIT") -> None:
        """Make the prompt public."""
        self.visibility = Visibility.PUBLIC
        self.license = license
        self.updated_at = datetime.utcnow()

    def unpublish(self) -> None:
        """Make the prompt private."""
        self.visibility = Visibility.PRIVATE
        self.updated_at = datetime.utcnow()

    def clone_for_user(self, user_id: UUID) -> "PromptTemplate":
        """Create a copy of this prompt for a user."""
        return PromptTemplate.create(
            title=f"{self.title} (Copy)",
            content=self.content,
            category=self.category,
            owner_id=user_id,
            description=self.description,
            variables_schema=self.variables_schema.copy(),
            visibility=Visibility.PRIVATE,
        )
