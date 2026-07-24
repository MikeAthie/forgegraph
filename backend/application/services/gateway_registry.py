"""Gateway capability registry, diagnostics, and connection services."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from application.services.credential_state import (
    is_credential_revoked,
    normalize_token_metadata,
)
from application.services.domain_event_outbox import sanitize_outbox_payload
from application.services.gateway_connectors import (
    GATEWAY_SEND_TOOL_IDS,
    get_gateway_adapter,
    normalize_platform,
    platform_for_tool_id,
)
from infrastructure.orm.models import (
    APIKey,
    GatewayConnection,
    GatewayConnectorCapability,
    GatewayInboundReceipt,
    GraphVersion,
    Organization,
)

DEFAULT_GATEWAY_CAPABILITIES: tuple[dict[str, Any], ...] = (
    {
        "platform": "api_server",
        "provider": "api_server",
        "display_name": "API Server",
        "credential_provider": "api_server",
        "capabilities": {"send": True, "inbound_webhook": True, "health_check": True},
        "setup": ["API_SERVER_KEY"],
    },
    {
        "platform": "bluebubbles",
        "provider": "bluebubbles",
        "display_name": "BlueBubbles",
        "credential_provider": "bluebubbles",
        "capabilities": {
            "send": True,
            "inbound_webhook": True,
            "sidecar_required": True,
            "health_check": True,
        },
        "setup": ["BLUEBUBBLES_SERVER_URL", "BLUEBUBBLES_PASSWORD"],
        "sidecar_required": True,
        "sidecar_health_path": "/health",
    },
    {
        "platform": "dingtalk",
        "provider": "dingtalk",
        "display_name": "DingTalk",
        "credential_provider": "dingtalk",
        "capabilities": {"send": True, "inbound_webhook": True, "health_check": True},
        "setup": ["DINGTALK_ACCESS_TOKEN", "DINGTALK_SECRET"],
    },
    {
        "platform": "email",
        "provider": "gmail",
        "display_name": "Gmail",
        "credential_provider": "gmail",
        "capabilities": {"send": True, "poll": True, "media": True, "health_check": True},
        "setup": ["GMAIL_ACCESS_TOKEN"],
    },
    {
        "platform": "email",
        "provider": "smtp",
        "display_name": "SMTP Email",
        "credential_provider": "gmail",
        "capabilities": {"send": True, "health_check": True},
        "setup": ["EMAIL_SMTP_HOST", "EMAIL_ADDRESS", "EMAIL_PASSWORD"],
    },
    {
        "platform": "feishu",
        "provider": "feishu",
        "display_name": "Feishu",
        "credential_provider": "feishu",
        "capabilities": {
            "send": True,
            "inbound_webhook": True,
            "media": True,
            "health_check": True,
        },
        "setup": ["FEISHU_APP_ID", "FEISHU_APP_SECRET", "FEISHU_VERIFICATION_TOKEN"],
    },
    {
        "platform": "feishu_comment",
        "provider": "feishu",
        "display_name": "Feishu Comments",
        "credential_provider": "feishu",
        "capabilities": {"send": True, "poll": True, "health_check": True},
        "setup": ["FEISHU_APP_ID", "FEISHU_APP_SECRET"],
    },
    {
        "platform": "homeassistant",
        "provider": "homeassistant",
        "display_name": "Home Assistant",
        "credential_provider": "homeassistant",
        "capabilities": {"send": True, "health_check": True},
        "setup": ["HOME_ASSISTANT_URL", "HOME_ASSISTANT_TOKEN"],
    },
    {
        "platform": "matrix",
        "provider": "matrix",
        "display_name": "Matrix",
        "credential_provider": "matrix",
        "capabilities": {"send": True, "poll": True, "media": True, "health_check": True},
        "setup": ["MATRIX_HOMESERVER", "MATRIX_ACCESS_TOKEN", "MATRIX_USER_ID"],
    },
    {
        "platform": "msgraph_webhook",
        "provider": "microsoft_graph",
        "display_name": "Microsoft Graph",
        "credential_provider": "microsoft_graph",
        "capabilities": {"send": True, "inbound_webhook": True, "health_check": True},
        "setup": ["MSGRAPH_ACCESS_TOKEN", "MSGRAPH_CLIENT_STATE"],
    },
    {
        "platform": "qqbot",
        "provider": "qqbot",
        "display_name": "QQ Bot",
        "credential_provider": "qqbot",
        "capabilities": {"send": True, "inbound_webhook": True, "health_check": True},
        "setup": ["QQBOT_APP_ID", "QQBOT_TOKEN", "QQBOT_APP_SECRET"],
    },
    {
        "platform": "signal",
        "provider": "signal",
        "display_name": "Signal",
        "credential_provider": "signal",
        "capabilities": {
            "send": True,
            "poll": True,
            "sidecar_required": True,
            "health_check": True,
        },
        "setup": ["SIGNAL_HTTP_URL", "SIGNAL_ACCOUNT"],
        "sidecar_required": True,
        "sidecar_health_path": "/health",
    },
    {
        "platform": "slack",
        "provider": "slack",
        "display_name": "Slack",
        "credential_provider": "slack",
        "capabilities": {
            "send": True,
            "inbound_webhook": True,
            "media": True,
            "typing": True,
            "health_check": True,
        },
        "setup": ["SLACK_BOT_TOKEN", "SLACK_SIGNING_SECRET"],
    },
    {
        "platform": "sms",
        "provider": "twilio",
        "display_name": "SMS",
        "credential_provider": "twilio",
        "capabilities": {"send": True, "inbound_webhook": True, "health_check": True},
        "setup": ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_PHONE_NUMBER"],
    },
    {
        "platform": "telegram",
        "provider": "telegram",
        "display_name": "Telegram",
        "credential_provider": "telegram",
        "capabilities": {
            "send": True,
            "inbound_webhook": True,
            "media": True,
            "health_check": True,
        },
        "setup": ["TELEGRAM_BOT_TOKEN"],
    },
    {
        "platform": "webhook",
        "provider": "generic_webhook",
        "display_name": "Generic Webhook",
        "credential_provider": "generic_webhook",
        "capabilities": {"send": True, "inbound_webhook": True, "health_check": True},
        "setup": ["GENERIC_WEBHOOK_SECRET"],
    },
    {
        "platform": "wecom",
        "provider": "wecom",
        "display_name": "WeCom",
        "credential_provider": "wecom",
        "capabilities": {"send": True, "inbound_webhook": True, "health_check": True},
        "setup": ["WECOM_CORP_ID", "WECOM_AGENT_ID", "WECOM_SECRET"],
    },
    {
        "platform": "weixin",
        "provider": "weixin",
        "display_name": "Weixin",
        "credential_provider": "weixin",
        "capabilities": {"send": True, "inbound_webhook": True, "health_check": True},
        "setup": ["WEIXIN_APP_ID", "WEIXIN_APP_SECRET", "WEIXIN_TOKEN"],
    },
    {
        "platform": "whatsapp",
        "provider": "whatsapp_cloud_api",
        "display_name": "WhatsApp Cloud API",
        "credential_provider": "whatsapp",
        "capabilities": {
            "send": True,
            "inbound_webhook": True,
            "media": True,
            "health_check": True,
        },
        "setup": [
            "WHATSAPP_CLOUD_API_TOKEN",
            "WHATSAPP_CLOUD_PHONE_NUMBER_ID",
            "WHATSAPP_VERIFY_TOKEN",
        ],
    },
    {
        "platform": "whatsapp",
        "provider": "twilio",
        "display_name": "Twilio WhatsApp",
        "credential_provider": "twilio",
        "capabilities": {
            "send": True,
            "inbound_webhook": True,
            "media": True,
            "health_check": True,
        },
        "setup": ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_PHONE_NUMBER"],
    },
    {
        "platform": "yuanbao",
        "provider": "yuanbao",
        "display_name": "Yuanbao",
        "credential_provider": "yuanbao",
        "capabilities": {"send": True, "poll": True, "media": True, "health_check": True},
        "setup": ["YUANBAO_COOKIE", "YUANBAO_DEVICE_ID"],
    },
)


@dataclass(frozen=True, slots=True)
class GatewayConnectionDiagnostics:
    connection_id: str
    status: str
    checks: list[dict[str, Any]]
    capability: dict[str, Any] | None
    generated_at: str

    @property
    def ready(self) -> bool:
        return all(check.get("status") == "ok" for check in self.checks)

    def as_dict(self) -> dict[str, Any]:
        return {
            "connection_id": self.connection_id,
            "status": self.status,
            "ready": self.ready,
            "checks": self.checks,
            "capability": self.capability,
            "generated_at": self.generated_at,
        }


def default_provider_for_platform(platform: str) -> str:
    selected = normalize_platform(platform)
    if selected == "email":
        return "gmail"
    if selected == "sms":
        return "twilio"
    if selected == "whatsapp":
        return "whatsapp_cloud_api"
    if selected == "msgraph_webhook":
        return "microsoft_graph"
    if selected == "webhook":
        return "generic_webhook"
    return selected


def list_capabilities(*, enabled_only: bool = True) -> list[GatewayConnectorCapability]:
    queryset = GatewayConnectorCapability.objects.all()
    if enabled_only:
        queryset = queryset.filter(enabled=True)
    capabilities = list(queryset.order_by("platform", "provider"))
    if capabilities:
        return capabilities
    return _fallback_capabilities(enabled_only=enabled_only)


def get_capability(
    *,
    platform: str,
    provider: str = "",
    enabled_only: bool = True,
) -> GatewayConnectorCapability | None:
    selected_platform = normalize_platform(platform)
    selected_provider = _safe_provider(provider or default_provider_for_platform(selected_platform))
    queryset = GatewayConnectorCapability.objects.filter(
        platform=selected_platform,
        provider=selected_provider,
    )
    if enabled_only:
        queryset = queryset.filter(enabled=True)
    capability = queryset.first()
    if capability is not None:
        return capability
    for item in _fallback_capabilities(enabled_only=enabled_only):
        if item.platform == selected_platform and item.provider == selected_provider:
            return item
    return None


def capability_for_tool_id(tool_id: str, provider: str = "") -> GatewayConnectorCapability | None:
    platform = platform_for_tool_id(tool_id)
    if not platform:
        return None
    return get_capability(platform=platform, provider=provider)


def capability_payload(capability: GatewayConnectorCapability | None) -> dict[str, Any] | None:
    if capability is None:
        return None
    return {
        "id": str(capability.id),
        "platform": capability.platform,
        "provider": capability.provider,
        "display_name": capability.display_name,
        "credential_provider": capability.credential_provider,
        "runtime_tool_id": capability.runtime_tool_id,
        "capabilities": sanitize_outbox_payload(capability.capabilities_json or {}),
        "setup_requirements": list(capability.setup_requirements_json or []),
        "inbound_modes": list(capability.inbound_modes_json or []),
        "outbound_modes": list(capability.outbound_modes_json or []),
        "sidecar_required": capability.sidecar_required,
        "sidecar_health_path": capability.sidecar_health_path,
        "docs_url": capability.docs_url,
        "enabled": capability.enabled,
    }


def connection_payload(connection: GatewayConnection) -> dict[str, Any]:
    capability = get_capability(platform=connection.platform, provider=connection.provider)
    return {
        "id": str(connection.id),
        "organization_id": str(connection.organization_id),
        "graph_version_id": str(connection.graph_version_id)
        if connection.graph_version_id
        else None,
        "credential_id": str(connection.credential_id) if connection.credential_id else None,
        "platform": connection.platform,
        "provider": connection.provider,
        "name": connection.name,
        "status": connection.status,
        "config": _public_connection_config(connection.config_json or {}),
        "allowlist": list(connection.allowlist_json or []),
        "capability": capability_payload(capability),
        "last_seen_at": connection.last_seen_at.isoformat() if connection.last_seen_at else None,
        "last_health_check_at": (
            connection.last_health_check_at.isoformat() if connection.last_health_check_at else None
        ),
        "last_error_at": connection.last_error_at.isoformat() if connection.last_error_at else None,
        "last_error_code": connection.last_error_code,
        "created_at": connection.created_at.isoformat(),
        "updated_at": connection.updated_at.isoformat(),
    }


def create_connection(
    *,
    organization: Organization,
    platform: str,
    provider: str = "",
    name: str = "",
    graph_version: GraphVersion | None = None,
    credential: APIKey | None = None,
    config: dict[str, Any] | None = None,
    allowlist: list[Any] | None = None,
) -> GatewayConnection:
    selected_platform = normalize_platform(platform)
    selected_provider = _safe_provider(provider or default_provider_for_platform(selected_platform))
    capability = get_capability(platform=selected_platform, provider=selected_provider)
    if capability is None:
        raise ValueError("Unsupported gateway capability.")
    clean_name = str(name or capability.display_name or selected_platform).strip()[:120]
    with transaction.atomic():
        connection, _ = GatewayConnection.objects.update_or_create(
            organization=organization,
            platform=selected_platform,
            provider=selected_provider,
            name=clean_name,
            defaults={
                "graph_version": graph_version,
                "credential": credential,
                "config_json": _safe_config(config or {}),
                "allowlist_json": _safe_allowlist(allowlist or []),
                "status": "enabled",
            },
        )
    return connection


def update_connection(
    connection: GatewayConnection,
    *,
    status: str | None = None,
    graph_version: GraphVersion | None = None,
    credential: APIKey | None = None,
    config: dict[str, Any] | None = None,
    allowlist: list[Any] | None = None,
) -> GatewayConnection:
    update_fields: list[str] = []
    if status is not None:
        connection.status = (
            status if status in {"enabled", "disabled", "degraded", "error"} else "error"
        )
        update_fields.append("status")
    if graph_version is not None:
        connection.graph_version = graph_version
        update_fields.append("graph_version")
    if credential is not None:
        connection.credential = credential
        update_fields.append("credential")
    if config is not None:
        connection.config_json = _safe_config(config)
        update_fields.append("config_json")
    if allowlist is not None:
        connection.allowlist_json = _safe_allowlist(allowlist)
        update_fields.append("allowlist_json")
    if update_fields:
        connection.save(update_fields=[*update_fields, "updated_at"])
    return connection


def connection_diagnostics(connection: GatewayConnection) -> GatewayConnectionDiagnostics:
    capability = get_capability(platform=connection.platform, provider=connection.provider)
    checks = [
        _capability_check(capability),
        _connection_status_check(connection),
        _credential_check(connection, capability),
        *_setup_checks(connection, capability),
        _webhook_check(connection, capability),
        _last_seen_check(connection, capability),
        _adapter_health_check(connection),
    ]
    if capability is not None and capability.sidecar_required:
        checks.append(_sidecar_check(connection, capability))
    overall = "enabled" if all(check["status"] == "ok" for check in checks) else "degraded"
    if connection.status == "disabled":
        overall = "disabled"
    return GatewayConnectionDiagnostics(
        connection_id=str(connection.id),
        status=overall,
        checks=checks,
        capability=capability_payload(capability),
        generated_at=timezone.now().isoformat(),
    )


def record_connection_health(connection: GatewayConnection) -> GatewayConnectionDiagnostics:
    diagnostics = connection_diagnostics(connection)
    status_value = (
        diagnostics.status if diagnostics.status in {"enabled", "disabled"} else "degraded"
    )
    error_checks = [check for check in diagnostics.checks if check["status"] != "ok"]
    GatewayConnection.objects.filter(id=connection.id).update(
        last_health_check_at=timezone.now(),
        status=status_value,
        last_error_at=timezone.now() if error_checks else None,
        last_error_code=str(error_checks[0]["code"])[:96] if error_checks else "",
    )
    connection.refresh_from_db()
    return diagnostics


def installed_runtime_tool_ids() -> set[str]:
    return set(GATEWAY_SEND_TOOL_IDS)


def _fallback_capabilities(*, enabled_only: bool) -> list[GatewayConnectorCapability]:
    capabilities: list[GatewayConnectorCapability] = []
    for item in DEFAULT_GATEWAY_CAPABILITIES:
        capability = GatewayConnectorCapability(
            platform=str(item["platform"]),
            provider=str(item["provider"]),
            display_name=str(item["display_name"]),
            credential_provider=str(item["credential_provider"]),
            runtime_tool_id=f"gateway.{item['platform']}.send",
            capabilities_json=dict(item["capabilities"]),
            setup_requirements_json=list(item["setup"]),
            inbound_modes_json=_modes(item["capabilities"], inbound=True),
            outbound_modes_json=_modes(item["capabilities"], inbound=False),
            sidecar_required=bool(item.get("sidecar_required", False)),
            sidecar_health_path=str(item.get("sidecar_health_path") or ""),
            docs_url="https://github.com/NousResearch/hermes-agent/tree/main/gateway/platforms",
            enabled=True,
        )
        if not enabled_only or capability.enabled:
            capabilities.append(capability)
    return capabilities


def _modes(capabilities: dict[str, Any], *, inbound: bool) -> list[str]:
    if inbound:
        modes: list[str] = []
        if capabilities.get("inbound_webhook"):
            modes.append("webhook")
        if capabilities.get("poll"):
            modes.append("poll")
        return modes
    return ["send"] if capabilities.get("send") else []


def _capability_check(capability: GatewayConnectorCapability | None) -> dict[str, Any]:
    if capability is None:
        return {
            "code": "capability_missing",
            "status": "error",
            "message": "Capability is not registered.",
        }
    if not capability.enabled:
        return {
            "code": "capability_disabled",
            "status": "error",
            "message": "Capability is disabled.",
        }
    return {"code": "capability_registered", "status": "ok", "message": "Capability is registered."}


def _connection_status_check(connection: GatewayConnection) -> dict[str, Any]:
    if connection.status == "disabled":
        return {
            "code": "connection_disabled",
            "status": "warning",
            "message": "Connection is disabled.",
        }
    if connection.status == "error":
        return {
            "code": "connection_error",
            "status": "error",
            "message": "Connection is in error state.",
        }
    return {"code": "connection_enabled", "status": "ok", "message": "Connection can be evaluated."}


def _credential_check(
    connection: GatewayConnection,
    capability: GatewayConnectorCapability | None,
) -> dict[str, Any]:
    if capability is None:
        return {"code": "credential_skipped", "status": "warning", "message": "Capability missing."}
    if not capability.credential_provider:
        return {
            "code": "credential_not_required",
            "status": "ok",
            "message": "No credential required.",
        }
    credential = connection.credential
    if credential is None:
        return {
            "code": "credential_missing",
            "status": "error",
            "message": "Credential is not attached.",
        }
    metadata = normalize_token_metadata(credential.token_metadata)
    if is_credential_revoked(metadata):
        return {
            "code": "credential_revoked",
            "status": "error",
            "message": "Credential is revoked.",
        }
    if credential.provider != capability.credential_provider:
        return {
            "code": "credential_provider_mismatch",
            "status": "warning",
            "message": "Credential provider differs from capability provider.",
        }
    return {"code": "credential_ready", "status": "ok", "message": "Credential is attached."}


def _setup_checks(
    connection: GatewayConnection,
    capability: GatewayConnectorCapability | None,
) -> list[dict[str, Any]]:
    if capability is None:
        return []
    checks: list[dict[str, Any]] = []
    config = connection.config_json if isinstance(connection.config_json, dict) else {}
    for key in list(capability.setup_requirements_json or []):
        configured = bool(str(config.get(key) or config.get(key.lower()) or _setting(key)).strip())
        checks.append(
            {
                "code": f"setup:{key}",
                "status": "ok" if configured else "warning",
                "message": f"{key} is configured." if configured else f"{key} is not configured.",
            }
        )
    return checks


def _webhook_check(
    connection: GatewayConnection,
    capability: GatewayConnectorCapability | None,
) -> dict[str, Any]:
    if capability is None or not (capability.capabilities_json or {}).get("inbound_webhook"):
        return {
            "code": "webhook_not_required",
            "status": "ok",
            "message": "Webhook is not required.",
        }
    configured = bool(connection.webhook_secret_hash or connection.verify_token_hash)
    if not configured:
        config = connection.config_json if isinstance(connection.config_json, dict) else {}
        configured = bool(
            config.get("webhook_secret_configured") or config.get("verify_token_configured")
        )
    return {
        "code": "webhook_verification",
        "status": "ok" if configured else "warning",
        "message": "Webhook verification is configured."
        if configured
        else "Webhook verification is not configured.",
    }


def _last_seen_check(
    connection: GatewayConnection,
    capability: GatewayConnectorCapability | None,
) -> dict[str, Any]:
    if capability is None or not _modes(capability.capabilities_json or {}, inbound=True):
        return {
            "code": "last_seen_not_required",
            "status": "ok",
            "message": "Inbound liveness is not required.",
        }
    latest = (
        GatewayInboundReceipt.objects.filter(connection=connection).order_by("-received_at").first()
    )
    if latest is None:
        return {
            "code": "no_inbound_seen",
            "status": "warning",
            "message": "No inbound event has been seen.",
        }
    return {
        "code": "last_inbound_seen",
        "status": "ok",
        "message": "Inbound event has been seen.",
        "received_at": latest.received_at.isoformat(),
    }


def _adapter_health_check(connection: GatewayConnection) -> dict[str, Any]:
    try:
        adapter = get_gateway_adapter(connection.platform, connection.provider)
        status_value = adapter.health_check()
    except Exception:
        return {
            "code": "adapter_health",
            "status": "warning",
            "message": "Adapter health could not be evaluated.",
        }
    return {
        "code": "adapter_health",
        "status": "ok" if status_value in {"ready", "ok", "healthy"} else "warning",
        "message": f"Adapter health: {status_value}.",
    }


def _sidecar_check(
    connection: GatewayConnection,
    capability: GatewayConnectorCapability,
) -> dict[str, Any]:
    config = connection.config_json if isinstance(connection.config_json, dict) else {}
    base_url = str(
        config.get("sidecar_url")
        or _setting(f"GATEWAY_{connection.platform.upper()}_SIDECAR_URL")
        or _setting(f"{connection.platform.upper()}_SIDECAR_URL")
    ).rstrip("/")
    if not base_url:
        return {
            "code": "sidecar_url_missing",
            "status": "error",
            "message": "Sidecar URL is missing.",
        }
    health_path = capability.sidecar_health_path or "/health"
    url = f"{base_url}{health_path if health_path.startswith('/') else '/' + health_path}"
    try:
        response = requests.get(
            url,
            timeout=float(getattr(settings, "GATEWAY_CONNECTOR_TIMEOUT_SECONDS", 10)),
        )
    except requests.RequestException:
        return {
            "code": "sidecar_unreachable",
            "status": "error",
            "message": "Sidecar is unreachable.",
        }
    return {
        "code": "sidecar_health",
        "status": "ok" if response.status_code < 500 else "error",
        "message": f"Sidecar returned HTTP {response.status_code}.",
    }


def _public_connection_config(config: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in config.items():
        key_text = str(key)
        if _sensitive_key(key_text):
            result[key_text] = "[configured]" if value else ""
        else:
            result[key_text] = value
    return sanitize_outbox_payload(result)


def _safe_config(config: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in config.items():
        key_text = str(key)[:80]
        if _sensitive_key(key_text):
            result[f"{key_text}_hash"] = _hash_value(value)
            result[f"{key_text}_configured"] = bool(value)
            continue
        result[key_text] = value
    return sanitize_outbox_payload(result)


def _safe_allowlist(values: list[Any]) -> list[str]:
    return [str(value or "").strip()[:255] for value in values if str(value or "").strip()]


def _sensitive_key(value: str) -> bool:
    lowered = value.lower()
    return any(
        token in lowered for token in ("secret", "token", "password", "authorization", "api_key")
    )


def _hash_value(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def _setting(name: str) -> str:
    return str(getattr(settings, name, "") or "").strip()


def _safe_provider(value: str) -> str:
    return str(value or "").strip().lower().replace("-", "_")[:64]
