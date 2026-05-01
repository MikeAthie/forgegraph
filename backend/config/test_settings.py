"""
Pytest/backend test settings.

This module forces the repo-owned test environment so local and CI backend
test runs use the same DB/Redis contract instead of inheriting developer
machine .env drift.
"""

from __future__ import annotations

import os
from typing import Any, cast

os.environ.setdefault("FORGEGRAPH_ENV_FILE", ".env.test")

from .settings import *  # noqa: F401,F403

# Legacy engine-event mutation stays enabled in the broad test environment while
# the suite is migrated to the runtime-intent path. Production defaults remain
# backend-intent-only unless explicitly overridden.
ENGINE_EVENT_STATE_MUTATION_ENABLED = True

_REST_FRAMEWORK = cast(dict[str, Any], globals().get("REST_FRAMEWORK", {}))
_DEFAULT_THROTTLE_RATES = cast(
    dict[str, str],
    _REST_FRAMEWORK.get("DEFAULT_THROTTLE_RATES", {}),
)

REST_FRAMEWORK = {
    **_REST_FRAMEWORK,
    "DEFAULT_THROTTLE_RATES": {
        **_DEFAULT_THROTTLE_RATES,
        "auth_register": "10000/min",
        "auth_login": "10000/min",
        "auth_refresh": "10000/min",
        "auth_ws_ticket": "10000/min",
    },
}
