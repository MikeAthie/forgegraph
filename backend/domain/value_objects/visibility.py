"""
Visibility value object.

Clean Architecture: Enterprise Business Rules layer.
"""

from enum import StrEnum


class Visibility(StrEnum):
    """Visibility settings for user-created resources."""

    PRIVATE = "private"
    PUBLIC = "public"
