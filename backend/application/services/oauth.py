from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode
from uuid import UUID

import requests
from django.conf import settings

from infrastructure.orm.models import IntegrationOAuthProviderConfig

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
)

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


def get_oauth_provider_config(
    tenant_id: str | UUID, provider: str
) -> tuple[OAuthProviderConfig | None, list[str]]:
    normalized = provider.strip().lower()
    if normalized not in SUPPORTED_OAUTH_PROVIDERS:
        raise ValueError(f"Unsupported OAuth provider '{provider}'.")

    tenant_id_str = str(tenant_id)
    stored = IntegrationOAuthProviderConfig.objects.filter(
        tenant_id=tenant_id_str,
        provider=normalized,
    ).first()
    if stored is None:
        return None, ["provider_configuration"]
    if not stored.enabled:
        return None, ["provider_disabled"]

    defaults = PROVIDER_DEFAULTS[normalized]
    client_id = stored.client_id.strip()
    client_secret = stored.client_secret.strip()
    authorize_url = stored.authorize_url.strip() or str(defaults["authorize_url"])
    token_url = stored.token_url.strip() or str(defaults["token_url"])
    redirect_uri = stored.redirect_uri.strip() or f"{_frontend_url()}/oauth/callback"
    scopes = [str(item).strip() for item in (stored.scopes or []) if str(item).strip()]
    if not scopes:
        scopes = [str(item) for item in defaults["scopes"]]
    authorize_extra_params = (
        stored.authorize_extra_params
        if isinstance(stored.authorize_extra_params, dict)
        else defaults["authorize_extra_params"]
    )
    token_extra_params = (
        stored.token_extra_params
        if isinstance(stored.token_extra_params, dict)
        else defaults["token_extra_params"]
    )

    missing: list[str] = []
    if not client_id:
        missing.append("client_id")
    if not client_secret:
        missing.append("client_secret")
    if not authorize_url:
        missing.append("authorize_url")
    if not token_url:
        missing.append("token_url")

    if missing:
        return None, missing

    config = OAuthProviderConfig(
        provider=normalized,
        client_id=client_id,
        client_secret=client_secret,
        authorize_url=authorize_url,
        token_url=token_url,
        redirect_uri=redirect_uri,
        scopes=scopes,
        authorize_extra_params={str(key): value for key, value in authorize_extra_params.items()},
        token_extra_params={str(key): value for key, value in token_extra_params.items()},
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


def get_oauth_provider_status(tenant_id: str | UUID) -> list[dict[str, Any]]:
    tenant_id_str = str(tenant_id)
    status_items: list[dict[str, Any]] = []
    for provider in SUPPORTED_OAUTH_PROVIDERS:
        config, missing = get_oauth_provider_config(tenant_id_str, provider)
        defaults = PROVIDER_DEFAULTS[provider]
        stored = IntegrationOAuthProviderConfig.objects.filter(
            tenant_id=tenant_id_str,
            provider=provider,
        ).first()
        status_items.append(
            {
                "provider": provider,
                "configured": not missing,
                "missing_config_fields": missing,
                "enabled": False if stored is None else stored.enabled,
                "has_provider_config": stored is not None,
                "client_id": "" if stored is None else stored.client_id,
                "authorize_url": (
                    str(defaults["authorize_url"])
                    if stored is None
                    else (stored.authorize_url or str(defaults["authorize_url"]))
                ),
                "token_url": (
                    str(defaults["token_url"])
                    if stored is None
                    else (stored.token_url or str(defaults["token_url"]))
                ),
                "redirect_uri": None if config is None else config.redirect_uri,
                "scopes": (
                    [str(item) for item in defaults["scopes"]] if config is None else config.scopes
                ),
                "authorize_extra_params": (
                    defaults["authorize_extra_params"]
                    if stored is None
                    else stored.authorize_extra_params
                ),
                "token_extra_params": (
                    defaults["token_extra_params"] if stored is None else stored.token_extra_params
                ),
            }
        )
    return status_items
