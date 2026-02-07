from __future__ import annotations

import re
from typing import Any

REDACTED_VALUE = "***REDACTED***"

_EXACT_SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "id_token",
    "token",
    "secret",
    "password",
    "authorization",
    "cookie",
    "client_secret",
    "webhook_secret",
    "bot_token",
    "auth_token",
    "encrypted_key",
    "encrypted_refresh_token",
}
_SENSITIVE_SUFFIXES = (
    "_token",
    "_secret",
    "_password",
    "_api_key",
    "_apikey",
)

_QUERY_SECRET_PATTERN = re.compile(
    r"(?i)(api[_-]?key|token|access_token|refresh_token|client_secret|password|secret)=([^&\s]+)"
)
_BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}\b")


def _is_sensitive_key(key: str) -> bool:
    normalized = key.strip().lower()
    if normalized in _EXACT_SENSITIVE_KEYS:
        return True
    return any(normalized.endswith(suffix) for suffix in _SENSITIVE_SUFFIXES)


def redact_text(value: str) -> str:
    redacted = _BEARER_PATTERN.sub("Bearer ***REDACTED***", value)
    redacted = _QUERY_SECRET_PATTERN.sub(lambda m: f"{m.group(1)}={REDACTED_VALUE}", redacted)
    return redacted


def redact_payload(value: Any, *, field_name: str | None = None) -> Any:
    if field_name and _is_sensitive_key(field_name):
        return REDACTED_VALUE

    if isinstance(value, dict):
        return {str(key): redact_payload(item, field_name=str(key)) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_payload(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_payload(item) for item in value)
    if isinstance(value, str):
        return redact_text(value)
    return value
