"""
Visibility value object.

Clean Architecture: Enterprise Business Rules layer.
"""

from enum import Enum


class Visibility(str, Enum):
    """Visibility settings for user-created resources."""

    PRIVATE = "private"
    PUBLIC = "public"
