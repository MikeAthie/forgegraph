from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[3]


def _read_env_example() -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in (BACKEND_DIR.parent / ".env.example").read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _runtime_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("SECRET_KEYS", None)
    env.pop("ENGINE_CALLBACK_SECRETS", None)
    env.update(_read_env_example())
    env["DJANGO_SETTINGS_MODULE"] = "config.settings"
    env["FORGEGRAPH_ENV_FILE"] = ""
    env["OPERATING_MODEL_PACKS_DIR"] = str(BACKEND_DIR.parent / "operating_model_packs")
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


def test_runtime_tool_secret_is_required() -> None:
    result = _run_validate_runtime_env(_runtime_env({"RUNTIME_TOOL_SECRET": ""}))

    assert result.returncode != 0
    assert "RUNTIME_TOOL_SECRET must be configured" in result.stderr


def test_runtime_tool_secret_must_not_match_engine_callback_secret() -> None:
    result = _run_validate_runtime_env(
        _runtime_env(
            {
                "ENGINE_CALLBACK_SECRET": "shared-secret",
                "RUNTIME_TOOL_SECRET": "shared-secret",
            }
        )
    )

    assert result.returncode != 0
    assert "RUNTIME_TOOL_SECRET must be distinct from ENGINE_CALLBACK_SECRET." in result.stderr


def test_insecure_transport_flags_are_rejected_without_explicit_exception() -> None:
    result = _run_validate_runtime_env(
        _runtime_env(
            {
                "SECURE_SSL_REDIRECT": "false",
                "SESSION_COOKIE_SECURE": "false",
                "CSRF_COOKIE_SECURE": "false",
                "AUTH_REFRESH_COOKIE_SECURE": "false",
                "FORGEGRAPH_ALLOW_INSECURE_TRANSPORT": "false",
            }
        )
    )

    assert result.returncode != 0
    assert "FORGEGRAPH_ALLOW_INSECURE_TRANSPORT=true" in result.stderr


def test_query_access_tokens_are_rejected_in_strict_runtime() -> None:
    result = _run_validate_runtime_env(
        _runtime_env({"RUN_STREAM_ALLOW_QUERY_ACCESS_TOKEN": "true"})
    )

    assert result.returncode != 0
    assert "RUN_STREAM_ALLOW_QUERY_ACCESS_TOKEN must be disabled" in result.stderr


def test_kafka_routing_flags_are_rejected_in_strict_runtime() -> None:
    result = _run_validate_runtime_env(
        _runtime_env(
            {
                "COMMUNICATION_ROUTING_FROM_KAFKA_ENABLED": "true",
                "REQUEST_ROUTER_FROM_KAFKA_ENABLED": "true",
            }
        )
    )

    assert result.returncode != 0
    assert "COMMUNICATION_ROUTING_FROM_KAFKA_ENABLED must be disabled" in result.stderr
    assert "REQUEST_ROUTER_FROM_KAFKA_ENABLED must be disabled" in result.stderr


def test_enabled_kafka_requires_managed_broker_security_settings() -> None:
    result = _run_validate_runtime_env(
        _runtime_env(
            {
                "COMMUNICATION_KAFKA_ENABLED": "true",
                "COMMUNICATION_KAFKA_BOOTSTRAP_SERVERS": "managed.kafka:9092",
                "COMMUNICATION_KAFKA_TOPIC": "forgegraph.communication.events.v1",
                "COMMUNICATION_KAFKA_SECURITY_PROTOCOL": "PLAINTEXT",
            }
        )
    )

    assert result.returncode != 0
    assert "COMMUNICATION_KAFKA_SECURITY_PROTOCOL must be SSL or SASL_SSL" in result.stderr


def test_enabled_whiteboard_board_kafka_requires_managed_broker_security_settings() -> None:
    result = _run_validate_runtime_env(
        _runtime_env(
            {
                "WHITEBOARD_BOARD_KAFKA_ENABLED": "true",
                "WHITEBOARD_BOARD_KAFKA_BOOTSTRAP_SERVERS": "managed.kafka:9092",
                "WHITEBOARD_BOARD_KAFKA_TOPIC": "forgegraph.whiteboard.board.events.v1",
                "WHITEBOARD_BOARD_KAFKA_SECURITY_PROTOCOL": "PLAINTEXT",
            }
        )
    )

    assert result.returncode != 0
    assert "WHITEBOARD_BOARD_KAFKA_SECURITY_PROTOCOL must be SSL or SASL_SSL" in result.stderr
