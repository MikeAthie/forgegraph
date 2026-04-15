"""
Pytest/backend test settings.

This module forces the repo-owned test environment so local and CI backend
test runs use the same DB/Redis contract instead of inheriting developer
machine .env drift.
"""

from __future__ import annotations

import os

os.environ.setdefault("FORGEGRAPH_ENV_FILE", ".env.test")

from .settings import *  # noqa: F401,F403

# Legacy engine-event mutation stays enabled in the broad test environment while
# the suite is migrated to the runtime-intent path. Production defaults remain
# backend-intent-only unless explicitly overridden.
ENGINE_EVENT_STATE_MUTATION_ENABLED = True
