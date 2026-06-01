"""
Django ORM models.

Clean Architecture: Frameworks & Drivers layer.
These models map to database tables and implement Django's ORM.
"""

# ruff: noqa: F401

from __future__ import annotations

import copy
import hashlib
import inspect
import json
import uuid
from datetime import timedelta
from typing import TYPE_CHECKING, Any, ClassVar

from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from pgvector.django import IvfflatIndex, VectorField

__all__ = [
    "TYPE_CHECKING",
    "AbstractUser",
    "Any",
    "BaseUserManager",
    "ClassVar",
    "IvfflatIndex",
    "MaxValueValidator",
    "MinValueValidator",
    "ValidationError",
    "VectorField",
    "_make_check_constraint",
    "copy",
    "hashlib",
    "inspect",
    "json",
    "models",
    "post_save",
    "receiver",
    "settings",
    "timedelta",
    "timezone",
    "uuid",
]

if TYPE_CHECKING:
    pass


def _make_check_constraint(expr: models.Q, *, name: str) -> models.CheckConstraint:
    params = inspect.signature(models.CheckConstraint).parameters
    if "condition" in params:
        return models.CheckConstraint(condition=expr, name=name)
    return models.CheckConstraint(check=expr, name=name)
