from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import urlencode
from uuid import UUID

import requests
from django.conf import settings

SUPPORTED_OAUTH_PROVIDERS = (
    "gmail",
    "google_calendar",
    "google_tasks",
    "notion",
    "slack",
    "jira",
    "linear",
    "hubspot",
    "google_drive",
    "microsoft_graph",
)

GOOGLE_OAUTH_PROVIDERS = ("gmail", "google_calendar", "google_tasks", "google_drive")

PROVIDER_DEFAULTS: dict[str, dict[str, Any]] = {
    "gmail": {
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scopes": [
            "https://www.googleapis.com/auth/gmail.send",
            "https://www.googleapis.com/auth/gmail.readonly",
        ],
        "authorize_extra_params": {
            "access_type": "offline",
            "prompt": "consent",
        },
        "token_extra_params": {},
    },
    "google_calendar": {
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scopes": [
            "https://www.googleapis.com/auth/calendar.events",
            "https://www.googleapis.com/auth/calendar.readonly",
        ],
        "authorize_extra_params": {
            "access_type": "offline",
            "prompt": "consent",
        },
        "token_extra_params": {},
    },
    "google_tasks": {
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scopes": [
            "https://www.googleapis.com/auth/tasks",
            "https://www.googleapis.com/auth/tasks.readonly",
        ],
        "authorize_extra_params": {
            "access_type": "offline",
            "prompt": "consent",
        },
        "token_extra_params": {},
    },
    "notion": {
        "authorize_url": "https://api.notion.com/v1/oauth/authorize",
        "token_url": "https://api.notion.com/v1/oauth/token",
        "scopes": [],
        "authorize_extra_params": {},
        "token_extra_params": {},
    },
    "slack": {
        "authorize_url": "https://slack.com/oauth/v2/authorize",
        "token_url": "https://slack.com/api/oauth.v2.access",
        "scopes": ["chat:write", "channels:read"],
        "authorize_extra_params": {},
        "token_extra_params": {},
    },
    "jira": {
        "authorize_url": "https://auth.atlassian.com/authorize",
        "token_url": "https://auth.atlassian.com/oauth/token",
        "scopes": ["read:jira-work", "write:jira-work", "offline_access"],
        "authorize_extra_params": {
            "audience": "api.atlassian.com",
            "prompt": "consent",
        },
        "token_extra_params": {},
    },
    "linear": {
        "authorize_url": "https://linear.app/oauth/authorize",
        "token_url": "https://api.linear.app/oauth/token",
        "scopes": ["read", "write"],
        "authorize_extra_params": {},
        "token_extra_params": {},
    },
    "hubspot": {
        "authorize_url": "https://app.hubspot.com/oauth/authorize",
        "token_url": "https://api.hubapi.com/oauth/v1/token",
        "scopes": [
            "crm.objects.contacts.read",
            "crm.objects.contacts.write",
        ],
        "authorize_extra_params": {},
        "token_extra_params": {},
    },
    "google_drive": {
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scopes": [
            "https://www.googleapis.com/auth/drive.file",
            "https://www.googleapis.com/auth/drive.metadata.readonly",
        ],
        "authorize_extra_params": {
            "access_type": "offline",
            "prompt": "consent",
        },
        "token_extra_params": {},
    },
    "microsoft_graph": {
        "authorize_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "scopes": [
            "offline_access",
            "Chat.ReadWrite",
            "ChannelMessage.Send",
            "User.Read",
        ],
        "authorize_extra_params": {},
        "token_extra_params": {},
    },
}


@dataclass(frozen=True)
class OAuthProviderConfig:
    provider: str
    client_id: str
    client_secret: str
    authorize_url: str
    token_url: str
    redirect_uri: str
    scopes: list[str]
    authorize_extra_params: dict[str, str | int | bool]
    token_extra_params: dict[str, str | int | bool]


def _frontend_url() -> str:
    return getattr(settings, "FRONTEND_URL", "http://localhost:3000").rstrip("/")


def _provider_env_candidates(provider: str, suffix: str) -> list[str]:
    normalized = provider.strip().lower()
    tokenized_provider = normalized.upper()
    keys = [f"OAUTH_{tokenized_provider}_{suffix}"]
    if normalized in GOOGLE_OAUTH_PROVIDERS:
        keys.append(f"GOOGLE_OAUTH_{suffix}")
    return keys


def _read_first_env_value(keys: list[str]) -> str | None:
    for key in keys:
        value = os.environ.get(key)
        if value is not None:
            return value
    return None


def _read_first_non_empty_env_value(keys: list[str]) -> str:
    raw = _read_first_env_value(keys)
    return "" if raw is None else raw.strip()


def _parse_bool(raw: str | None, *, default: bool) -> bool:
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default


def _parse_scopes(raw: str, *, fallback: list[str]) -> list[str]:
    if not raw.strip():
        return fallback
    values = [item.strip() for item in re.split(r"[\s,]+", raw.strip()) if item.strip()]
    return values or fallback


def _parse_json_object(raw: str, *, fallback: dict[str, Any]) -> dict[str, str | int | bool]:
    if not raw.strip():
        return {str(key): value for key, value in fallback.items()}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {str(key): value for key, value in fallback.items()}
    if not isinstance(parsed, dict):
        return {str(key): value for key, value in fallback.items()}
    return {str(key): value for key, value in parsed.items()}


def _resolve_provider_settings(provider: str) -> dict[str, Any]:
    defaults = PROVIDER_DEFAULTS[provider]

    client_id = _read_first_non_empty_env_value(_provider_env_candidates(provider, "CLIENT_ID"))
    client_secret = _read_first_non_empty_env_value(
        _provider_env_candidates(provider, "CLIENT_SECRET")
    )
    authorize_url = _read_first_non_empty_env_value(
        _provider_env_candidates(provider, "AUTHORIZE_URL")
    ) or str(defaults["authorize_url"])
    token_url = _read_first_non_empty_env_value(
        _provider_env_candidates(provider, "TOKEN_URL")
    ) or str(defaults["token_url"])
    redirect_uri = _read_first_non_empty_env_value(
        _provider_env_candidates(provider, "REDIRECT_URI")
    ) or (f"{_frontend_url()}/oauth/callback")
    scopes = _parse_scopes(
        _read_first_non_empty_env_value(_provider_env_candidates(provider, "SCOPES")),
        fallback=[str(item) for item in defaults["scopes"]],
    )
    authorize_extra_params = _parse_json_object(
        _read_first_non_empty_env_value(
            _provider_env_candidates(provider, "AUTHORIZE_EXTRA_PARAMS_JSON")
        ),
        fallback=cast(dict[str, Any], defaults["authorize_extra_params"]),
    )
    token_extra_params = _parse_json_object(
        _read_first_non_empty_env_value(
            _provider_env_candidates(provider, "TOKEN_EXTRA_PARAMS_JSON")
        ),
        fallback=cast(dict[str, Any], defaults["token_extra_params"]),
    )
    enabled = _parse_bool(
        _read_first_env_value(_provider_env_candidates(provider, "ENABLED")),
        default=True,
    )

    missing: list[str] = []
    if not enabled:
        missing.append("provider_disabled")
    elif not client_id and not client_secret:
        missing.append("provider_configuration")
    else:
        if not client_id:
            missing.append("client_id")
        if not client_secret:
            missing.append("client_secret")
        if not authorize_url:
            missing.append("authorize_url")
        if not token_url:
            missing.append("token_url")

    return {
        "provider": provider,
        "client_id": client_id,
        "client_secret": client_secret,
        "authorize_url": authorize_url,
        "token_url": token_url,
        "redirect_uri": redirect_uri,
        "scopes": scopes,
        "authorize_extra_params": authorize_extra_params,
        "token_extra_params": token_extra_params,
        "enabled": enabled,
        "missing": missing,
        "has_provider_config": bool(client_id and client_secret),
    }


def get_oauth_provider_config(
    tenant_id: str | UUID, provider: str
) -> tuple[OAuthProviderConfig | None, list[str]]:
    normalized = provider.strip().lower()
    if normalized not in SUPPORTED_OAUTH_PROVIDERS:
        raise ValueError(f"Unsupported OAuth provider '{provider}'.")

    _ = tenant_id
    resolved = _resolve_provider_settings(normalized)
    missing = cast(list[str], resolved["missing"])
    if missing:
        return None, missing

    config = OAuthProviderConfig(
        provider=normalized,
        client_id=cast(str, resolved["client_id"]),
        client_secret=cast(str, resolved["client_secret"]),
        authorize_url=cast(str, resolved["authorize_url"]),
        token_url=cast(str, resolved["token_url"]),
        redirect_uri=cast(str, resolved["redirect_uri"]),
        scopes=cast(list[str], resolved["scopes"]),
        authorize_extra_params=cast(
            dict[str, str | int | bool], resolved["authorize_extra_params"]
        ),
        token_extra_params=cast(dict[str, str | int | bool], resolved["token_extra_params"]),
    )
    return config, []


def build_oauth_authorize_url(config: OAuthProviderConfig, *, state: str) -> str:
    params: dict[str, str | int | bool] = {
        "response_type": "code",
        "client_id": config.client_id,
        "redirect_uri": config.redirect_uri,
        "state": state,
    }
    if config.scopes:
        params["scope"] = " ".join(config.scopes)
    params.update(config.authorize_extra_params)
    return f"{config.authorize_url}?{urlencode(params)}"


def exchange_code_for_tokens(config: OAuthProviderConfig, *, code: str) -> dict[str, Any]:
    payload: dict[str, str | int | bool] = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": config.client_id,
        "client_secret": config.client_secret,
        "redirect_uri": config.redirect_uri,
    }
    payload.update(config.token_extra_params)

    try:
        headers: dict[str, str] = {"Accept": "application/json"}
        request_kwargs: dict[str, Any] = {"timeout": 15}

        if config.provider in {"jira", "linear"}:
            headers["Content-Type"] = "application/json"
            request_kwargs["json"] = payload
        elif config.provider == "notion":
            # Notion expects Basic auth with JSON payload.
            headers["Content-Type"] = "application/json"
            request_kwargs["json"] = {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": config.redirect_uri,
            }
            request_kwargs["auth"] = (config.client_id, config.client_secret)
        else:
            request_kwargs["data"] = payload

        request_kwargs["headers"] = headers
        response = requests.post(config.token_url, **request_kwargs)
        response.raise_for_status()
    except requests.RequestException as exc:
        detail = ""
        response_obj = exc.response
        if response_obj is not None:
            detail = f" Response: {response_obj.text[:300]}"
        raise ValueError(f"OAuth token exchange failed.{detail}") from exc

    token_data = response.json()
    if not isinstance(token_data, dict):
        raise ValueError("OAuth token exchange returned an invalid response payload.")
    return token_data


def exchange_refresh_token_for_access_token(
    config: OAuthProviderConfig, *, refresh_token: str
) -> dict[str, Any]:
    payload: dict[str, str | int | bool] = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": config.client_id,
        "client_secret": config.client_secret,
    }
    payload.update(config.token_extra_params)

    try:
        headers: dict[str, str] = {"Accept": "application/json"}
        request_kwargs: dict[str, Any] = {"timeout": 15}

        if config.provider in {"jira", "linear"}:
            headers["Content-Type"] = "application/json"
            request_kwargs["json"] = payload
        elif config.provider == "notion":
            headers["Content-Type"] = "application/json"
            request_kwargs["json"] = {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            }
            request_kwargs["auth"] = (config.client_id, config.client_secret)
        else:
            request_kwargs["data"] = payload

        request_kwargs["headers"] = headers
        response = requests.post(config.token_url, **request_kwargs)
        response.raise_for_status()
    except requests.RequestException as exc:
        detail = ""
        response_obj = exc.response
        if response_obj is not None:
            detail = f" Response: {response_obj.text[:300]}"
        raise ValueError(f"OAuth token refresh failed.{detail}") from exc

    token_data = response.json()
    if not isinstance(token_data, dict):
        raise ValueError("OAuth token refresh returned an invalid response payload.")
    return token_data


def get_oauth_provider_status(tenant_id: str | UUID) -> list[dict[str, Any]]:
    _ = tenant_id
    status_items: list[dict[str, Any]] = []
    for provider in SUPPORTED_OAUTH_PROVIDERS:
        resolved = _resolve_provider_settings(provider)
        missing = cast(list[str], resolved["missing"])
        status_items.append(
            {
                "provider": provider,
                "configured": not missing,
                "missing_config_fields": missing,
                "enabled": bool(resolved["enabled"]),
                "has_provider_config": bool(resolved["has_provider_config"]),
                "client_id": str(resolved["client_id"]),
                "authorize_url": str(resolved["authorize_url"]),
                "token_url": str(resolved["token_url"]),
                "redirect_uri": str(resolved["redirect_uri"]),
                "scopes": list(cast(list[str], resolved["scopes"])),
                "authorize_extra_params": cast(
                    dict[str, str | int | bool], resolved["authorize_extra_params"]
                ),
                "token_extra_params": cast(
                    dict[str, str | int | bool], resolved["token_extra_params"]
                ),
                "configuration_mode": "environment",
            }
        )
    return status_items
