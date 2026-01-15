"""
Prompt category value object.

Clean Architecture: Enterprise Business Rules layer.
"""

from enum import Enum


class PromptCategory(str, Enum):
    """Categories for prompt templates."""

    RESEARCH = "research"
    SUMMARIZATION = "summarization"
    EMAIL = "email"
    EXTRACTION = "extraction"
    REASONING = "reasoning"
    OTHER = "other"
