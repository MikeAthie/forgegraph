"""
Runtime environment validation helpers.
"""

from __future__ import annotations

import importlib.util
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


def _validate_frontend_url(errors: list[str]) -> None:
    frontend_url = str(getattr(settings, "FRONTEND_URL", "") or "").strip()
    parsed_frontend_url = urlparse(frontend_url)
    if not frontend_url or parsed_frontend_url.scheme not in {"http", "https"}:
        errors.append("FRONTEND_URL must be an absolute http(s) URL.")


def _validate_database_settings(errors: list[str]) -> None:
    if getattr(settings, "USE_SQLITE", False):
        return
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


def _validate_redis_settings(errors: list[str]) -> None:
    redis_location = str(settings.CACHES["default"].get("LOCATION", "") or "").strip()
    parsed_redis = urlparse(redis_location)
    if not redis_location or parsed_redis.scheme != "redis" or not parsed_redis.hostname:
        errors.append("Redis cache LOCATION must be configured with a redis:// URL.")


def _validate_runtime_secrets(errors: list[str]) -> None:
    callback_secret = str(getattr(settings, "ENGINE_CALLBACK_SECRET", "") or "").strip()
    if not callback_secret:
        errors.append("ENGINE_CALLBACK_SECRET must be configured for production runtime.")

    runtime_tool_secret = str(getattr(settings, "RUNTIME_TOOL_SECRET", "") or "").strip()
    if not runtime_tool_secret:
        errors.append("RUNTIME_TOOL_SECRET must be configured for runtime tool authentication.")
    if runtime_tool_secret and callback_secret and runtime_tool_secret == callback_secret:
        errors.append("RUNTIME_TOOL_SECRET must be distinct from ENGINE_CALLBACK_SECRET.")


def _validate_secure_transport(errors: list[str]) -> None:
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


def _validate_engine_tls_settings(errors: list[str]) -> None:
    if not getattr(settings, "ENGINE_GRPC_TLS_ENABLED", False):
        return
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


def _validate_engine_settings(errors: list[str]) -> None:
    engine_host = str(getattr(settings, "ENGINE_HOST", "") or "").strip()
    engine_port = str(getattr(settings, "ENGINE_PORT", "") or "").strip()
    if not engine_host or not engine_port:
        errors.append("ENGINE_HOST and ENGINE_PORT must be configured for production runtime.")
    _validate_engine_tls_settings(errors)


def _validate_run_stream_settings(errors: list[str]) -> None:
    if _is_enabled_setting("RUN_STREAM_ALLOW_QUERY_ACCESS_TOKEN"):
        errors.append(
            "RUN_STREAM_ALLOW_QUERY_ACCESS_TOKEN must be disabled for production runtime."
        )


def _validate_communication_kafka_settings(errors: list[str]) -> None:
    _validate_communication_kafka_routing_flags(errors)
    if not _is_enabled_setting("COMMUNICATION_KAFKA_ENABLED"):
        return
    if importlib.util.find_spec("confluent_kafka") is None:
        errors.append("confluent-kafka must be installed when COMMUNICATION_KAFKA_ENABLED=true.")
    bootstrap_servers = str(
        getattr(settings, "COMMUNICATION_KAFKA_BOOTSTRAP_SERVERS", "")
        or getattr(settings, "KAFKA_BROKERS", "")
        or ""
    ).strip()
    if not bootstrap_servers:
        errors.append(
            "COMMUNICATION_KAFKA_BOOTSTRAP_SERVERS or KAFKA_BROKERS must be configured "
            "when Kafka is enabled."
        )
    topic = str(getattr(settings, "COMMUNICATION_KAFKA_TOPIC", "") or "").strip()
    if not topic:
        errors.append("COMMUNICATION_KAFKA_TOPIC must be configured when Kafka is enabled.")

    _validate_communication_kafka_security(errors)


def _validate_communication_kafka_routing_flags(errors: list[str]) -> None:
    if _is_enabled_setting("COMMUNICATION_ROUTING_FROM_KAFKA_ENABLED"):
        errors.append(
            "COMMUNICATION_ROUTING_FROM_KAFKA_ENABLED must be disabled in production; "
            "Kafka is transport-only."
        )
    if _is_enabled_setting("REQUEST_ROUTER_FROM_KAFKA_ENABLED"):
        errors.append(
            "REQUEST_ROUTER_FROM_KAFKA_ENABLED must be disabled in production; "
            "Kafka is transport-only."
        )


def _validate_communication_kafka_security(errors: list[str]) -> None:
    security_protocol = str(
        getattr(settings, "COMMUNICATION_KAFKA_SECURITY_PROTOCOL", "") or ""
    ).strip()
    if security_protocol not in {"SSL", "SASL_SSL"}:
        errors.append(
            "COMMUNICATION_KAFKA_SECURITY_PROTOCOL must be SSL or SASL_SSL for production Kafka."
        )
    if security_protocol == "SASL_SSL":
        sasl_mechanism = str(getattr(settings, "COMMUNICATION_KAFKA_SASL_MECHANISM", "") or "")
        sasl_username = str(getattr(settings, "COMMUNICATION_KAFKA_SASL_USERNAME", "") or "")
        sasl_password = str(getattr(settings, "COMMUNICATION_KAFKA_SASL_PASSWORD", "") or "")
        if not sasl_mechanism.strip():
            errors.append(
                "COMMUNICATION_KAFKA_SASL_MECHANISM is required when "
                "COMMUNICATION_KAFKA_SECURITY_PROTOCOL=SASL_SSL."
            )
        if not sasl_username.strip():
            errors.append(
                "COMMUNICATION_KAFKA_SASL_USERNAME is required when "
                "COMMUNICATION_KAFKA_SECURITY_PROTOCOL=SASL_SSL."
            )
        if not sasl_password.strip():
            errors.append(
                "COMMUNICATION_KAFKA_SASL_PASSWORD is required when "
                "COMMUNICATION_KAFKA_SECURITY_PROTOCOL=SASL_SSL."
            )


def _validate_strict_runtime_settings(errors: list[str]) -> None:
    _validate_runtime_secrets(errors)
    _validate_secure_transport(errors)
    _validate_engine_settings(errors)
    _validate_run_stream_settings(errors)
    _validate_communication_kafka_settings(errors)


def collect_runtime_validation_errors(*, strict: bool | None = None) -> list[str]:
    strict = should_enforce_strict_runtime_validation() if strict is None else bool(strict)
    errors: list[str] = []

    _validate_frontend_url(errors)
    _validate_database_settings(errors)
    _validate_redis_settings(errors)
    if strict:
        _validate_strict_runtime_settings(errors)
    return errors
