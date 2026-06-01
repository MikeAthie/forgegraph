"""
Integration tests for Run APIs.

Tests run history and run detail endpoints for Phase 4 observability MVP.
"""

# ruff: noqa: F401

import json
import logging
import time
from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework_simplejwt.tokens import AccessToken

from application.services.auth_state import issue_ws_ticket
from application.services.llm_access import LLMAccessConfig, resolve_llm_access_for_dispatch
from application.services.run_liveness import reconcile_stale_runs
from application.services.run_snapshots import RunSnapshot, get_snapshot, set_snapshot
from infrastructure.crypto.encryption import encrypt_api_key
from infrastructure.orm.models import (
    APIKey,
    ApprovalTask,
    ContextPack,
    Graph,
    GraphVersion,
    LLMBudget,
    LLMQuota,
    LLMUsage,
    MemoryConfiguration,
    NodePackageInstallation,
    NodeRegistryPackage,
    NodeRegistryRelease,
    NodeRun,
    NodeRunEventProjection,
    PromptTemplate,
    Run,
    RunCheckpoint,
    RunEvent,
    RunEventProjection,
    RunQueueEntry,
    User,
)
from infrastructure.security import s2s

pytestmark = pytest.mark.django_db


def _create_openai_credential(user: User) -> APIKey:
    organization = user.default_organization
    assert organization is not None
    return APIKey.objects.create(
        organization=organization,
        user=user,
        provider="openai",
        name=f"OpenAI {uuid4()}",
        encrypted_key=b"test-key",
    )


__all__ = [
    "json",
    "logging",
    "time",
    "timedelta",
    "Decimal",
    "Any",
    "uuid4",
    "pytest",
    "TestCase",
    "override_settings",
    "timezone",
    "status",
    "AccessToken",
    "issue_ws_ticket",
    "LLMAccessConfig",
    "resolve_llm_access_for_dispatch",
    "reconcile_stale_runs",
    "RunSnapshot",
    "get_snapshot",
    "set_snapshot",
    "encrypt_api_key",
    "APIKey",
    "ApprovalTask",
    "ContextPack",
    "Graph",
    "GraphVersion",
    "LLMBudget",
    "LLMQuota",
    "LLMUsage",
    "MemoryConfiguration",
    "NodePackageInstallation",
    "NodeRegistryPackage",
    "NodeRegistryRelease",
    "NodeRun",
    "NodeRunEventProjection",
    "PromptTemplate",
    "Run",
    "RunCheckpoint",
    "RunEvent",
    "RunEventProjection",
    "RunQueueEntry",
    "User",
    "s2s",
    "pytestmark",
    "_create_openai_credential",
]
