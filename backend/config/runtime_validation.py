"""
Runtime environment validation helpers.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings


def _is_enabled_setting(name: str) -> bool:
    return bool(getattr(settings, name, False))


def should_enforce_strict_runtime_validation() -> bool:
    return bool(getattr(settings, "FORGEGRAPH_STRICT_RUNTIME_ENV", False)) or (
        not bool(getattr(settings, "DEBUG", False))
        and not bool(getattr(settings, "TESTING", False))
    )


def collect_runtime_validation_errors(*, strict: bool | None = None) -> list[str]:
    strict = should_enforce_strict_runtime_validation() if strict is None else bool(strict)
    errors: list[str] = []

    frontend_url = str(getattr(settings, "FRONTEND_URL", "") or "").strip()
    parsed_frontend_url = urlparse(frontend_url)
    if not frontend_url or parsed_frontend_url.scheme not in {"http", "https"}:
        errors.append("FRONTEND_URL must be an absolute http(s) URL.")

    if not getattr(settings, "USE_SQLITE", False):
        required_db_settings = {
            "DB host": settings.DATABASES["default"].get("HOST", ""),
            "DB port": settings.DATABASES["default"].get("PORT", ""),
            "DB name": settings.DATABASES["default"].get("NAME", ""),
            "DB user": settings.DATABASES["default"].get("USER", ""),
            "DB password": settings.DATABASES["default"].get("PASSWORD", ""),
        }
        for label, value in required_db_settings.items():
            if not str(value or "").strip():
                errors.append(f"{label} must be configured.")

    redis_location = str(settings.CACHES["default"].get("LOCATION", "") or "").strip()
    parsed_redis = urlparse(redis_location)
    if not redis_location or parsed_redis.scheme != "redis" or not parsed_redis.hostname:
        errors.append("Redis cache LOCATION must be configured with a redis:// URL.")

    if strict:
        callback_secret = str(getattr(settings, "ENGINE_CALLBACK_SECRET", "") or "").strip()
        if not callback_secret:
            errors.append("ENGINE_CALLBACK_SECRET must be configured for production runtime.")

        runtime_tool_secret = str(getattr(settings, "RUNTIME_TOOL_SECRET", "") or "").strip()
        if not runtime_tool_secret:
            errors.append("RUNTIME_TOOL_SECRET must be configured for runtime tool authentication.")
        if runtime_tool_secret and callback_secret and runtime_tool_secret == callback_secret:
            errors.append("RUNTIME_TOOL_SECRET must be distinct from ENGINE_CALLBACK_SECRET.")

        allow_insecure_transport = _is_enabled_setting("FORGEGRAPH_ALLOW_INSECURE_TRANSPORT")
        insecure_flags = []
        if not _is_enabled_setting("SESSION_COOKIE_SECURE"):
            insecure_flags.append("SESSION_COOKIE_SECURE")
        if not _is_enabled_setting("CSRF_COOKIE_SECURE"):
            insecure_flags.append("CSRF_COOKIE_SECURE")
        if not _is_enabled_setting("AUTH_REFRESH_COOKIE_SECURE"):
            insecure_flags.append("AUTH_REFRESH_COOKIE_SECURE")
        if not _is_enabled_setting("SECURE_SSL_REDIRECT"):
            insecure_flags.append("SECURE_SSL_REDIRECT")
        if insecure_flags and not allow_insecure_transport:
            joined = ", ".join(insecure_flags)
            errors.append(
                f"{joined} must be enabled, or FORGEGRAPH_ALLOW_INSECURE_TRANSPORT=true "
                "must be set for local smoke tests behind non-public HTTP."
            )

        engine_host = str(getattr(settings, "ENGINE_HOST", "") or "").strip()
        engine_port = str(getattr(settings, "ENGINE_PORT", "") or "").strip()
        if not engine_host or not engine_port:
            errors.append("ENGINE_HOST and ENGINE_PORT must be configured for production runtime.")

        if getattr(settings, "ENGINE_GRPC_TLS_ENABLED", False):
            ca_file = str(getattr(settings, "ENGINE_GRPC_TLS_CA_FILE", "") or "").strip()
            if not ca_file:
                errors.append("ENGINE_GRPC_TLS_CA_FILE must be configured when TLS is enabled.")
            elif not Path(ca_file).exists():
                errors.append("ENGINE_GRPC_TLS_CA_FILE does not exist.")
            server_name = str(getattr(settings, "ENGINE_GRPC_TLS_SERVER_NAME", "") or "").strip()
            if not server_name:
                errors.append(
                    "ENGINE_GRPC_TLS_SERVER_NAME must be configured when engine gRPC TLS is enabled."
                )

        if _is_enabled_setting("RUN_STREAM_ALLOW_QUERY_ACCESS_TOKEN"):
            errors.append(
                "RUN_STREAM_ALLOW_QUERY_ACCESS_TOKEN must be disabled for production runtime."
            )

    return errors
