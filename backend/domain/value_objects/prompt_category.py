"""
Prompt category value object.

Clean Architecture: Enterprise Business Rules layer.
"""

from enum import StrEnum


class PromptCategory(StrEnum):
    """Categories for prompt templates."""

    RESEARCH = "research"
    SUMMARIZATION = "summarization"
    EMAIL = "email"
    EXTRACTION = "extraction"
    REASONING = "reasoning"
    OTHER = "other"
