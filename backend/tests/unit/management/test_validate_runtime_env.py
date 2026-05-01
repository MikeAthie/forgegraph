from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[3]


def _runtime_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("SECRET_KEYS", None)
    env.pop("ENGINE_CALLBACK_SECRETS", None)
    env["DJANGO_SETTINGS_MODULE"] = "config.settings"
    env["FORGEGRAPH_ENV_FILE"] = ".env.example"
    if extra:
        env.update(extra)
    return env


def _run_validate_runtime_env(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "manage.py", "validate_runtime_env", "--strict"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_env_example_passes_strict_runtime_validation() -> None:
    result = _run_validate_runtime_env(_runtime_env())

    assert result.returncode == 0, result.stderr + result.stdout
    assert "Runtime environment validation passed." in result.stdout


def test_legacy_secret_keys_env_var_is_rejected() -> None:
    result = _run_validate_runtime_env(_runtime_env({"SECRET_KEYS": "legacy"}))

    assert result.returncode != 0
    assert "SECRET_KEYS is no longer supported; use SECRET_KEY." in result.stderr


def test_legacy_engine_callback_secrets_env_var_is_rejected() -> None:
    result = _run_validate_runtime_env(_runtime_env({"ENGINE_CALLBACK_SECRETS": "legacy"}))

    assert result.returncode != 0
    assert (
        "ENGINE_CALLBACK_SECRETS is no longer supported; use ENGINE_CALLBACK_SECRET."
        in result.stderr
    )
