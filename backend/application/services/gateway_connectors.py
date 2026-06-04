"""Backend-owned Hermes-style gateway connector primitives."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import smtplib
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Any, Protocol
from urllib.parse import quote, urljoin
from uuid import UUID

import requests
from django.conf import settings
from django.utils import timezone

from application.services.domain_event_outbox import sanitize_outbox_payload
from application.services.redaction import redact_text
from infrastructure.crypto.encryption import decrypt_api_key
from infrastructure.orm.models import APIKey, GatewayConnection

GATEWAY_MODE_DRY_RUN = "dry_run"
GATEWAY_MODE_REAL_SEND = "real_send"
GATEWAY_EVIDENCE_SANDBOX = "sandbox"
GATEWAY_EVIDENCE_PROVIDER_SEND = "provider_send"
GATEWAY_EVIDENCE_SIDECAR_SEND = "sidecar_send"

HERMES_GATEWAY_PLATFORMS = (
    "api_server",
    "bluebubbles",
    "dingtalk",
    "email",
    "feishu",
    "feishu_comment",
    "homeassistant",
    "matrix",
    "msgraph_webhook",
    "qqbot",
    "signal",
    "slack",
    "sms",
    "telegram",
    "webhook",
    "wecom",
    "weixin",
    "whatsapp",
    "yuanbao",
)

GATEWAY_PLATFORM_ALIASES = {
    "gmail": "email",
    "generic_webhook": "webhook",
    "microsoft_graph": "msgraph_webhook",
    "msgraph": "msgraph_webhook",
}

GATEWAY_SEND_TOOL_IDS = {f"gateway.{platform}.send" for platform in HERMES_GATEWAY_PLATFORMS} | {
    "gateway.gmail.send",
    "gateway.generic_webhook.send",
    "gateway.microsoft_graph.send",
}

_MAX_ERROR_MESSAGE_LENGTH = 300
_MAX_PROVIDER_RESPONSE_BYTES = 8192
_SECRET_RE = re.compile(r"(?i)\b(?:bearer|token|secret|password|authorization)\b[^\s,;]*")


class GatewayConnectorError(RuntimeError):
    """Safe domain error for gateway connector validation/provider failures."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        platform: str = "",
        provider: str = "",
        mode: str = "",
        blocked_before_provider_call: bool = False,
        retryable: bool = False,
    ) -> None:
        self.code = _safe_key(code or "gateway_connector_error")
        self.message = _safe_error_message(message or "Gateway connector failed.")
        self.platform = normalize_platform(platform)
        self.provider = _safe_key(provider)
        self.mode = _safe_key(mode)
        self.blocked_before_provider_call = blocked_before_provider_call
        self.retryable = retryable
        super().__init__(self.message)

    def as_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "provider": self.provider,
            "mode": self.mode,
            "status": "failed",
            "error_code": self.code,
            "error_message": self.message,
            "blocked_before_provider_call": self.blocked_before_provider_call,
            "retryable": self.retryable,
            "sanitized": True,
        }


@dataclass(frozen=True, slots=True)
class GatewayInboundEvent:
    platform: str
    provider: str
    connection_id: UUID | str | None = None
    external_message_id: str = ""
    conversation_id: str = ""
    sender: str = ""
    text: str = ""
    attachments: list[dict[str, Any]] = field(default_factory=list)
    timestamp: str | None = None
    raw_metadata: dict[str, Any] = field(default_factory=dict)

    def as_input_json(self) -> dict[str, Any]:
        return sanitize_outbox_payload(
            {
                "channel": normalize_platform(self.platform),
                "message": self.text,
                "gateway": {
                    "platform": normalize_platform(self.platform),
                    "provider": _safe_key(self.provider),
                    "connection_id": str(self.connection_id or ""),
                    "event_id": self.external_message_id,
                    "conversation_id": self.conversation_id,
                    "sender": self.sender,
                    "attachments": self.attachments,
                    "timestamp": self.timestamp,
                    "metadata": self.raw_metadata,
                },
            }
        )


@dataclass(frozen=True, slots=True)
class GatewaySendRequest:
    platform: str
    provider: str
    mode: str
    organization_id: UUID | str | None = None
    credential_id: UUID | str | None = None
    connection_id: UUID | str | None = None
    schedule_id: UUID | str | None = None
    to: list[str] = field(default_factory=list)
    text: str = ""
    subject: str = ""
    html: str = ""
    attachments: list[dict[str, Any]] = field(default_factory=list)
    media_artifact_ids: list[str] = field(default_factory=list)
    thread: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    idempotency_key: str = ""
    approval_id: str | None = None
    operator_confirmed: bool = False

    def destinations(self) -> list[str]:
        return _normalized_destinations(self.to)


@dataclass(frozen=True, slots=True)
class GatewaySendReceipt:
    platform: str
    provider: str
    mode: str
    evidence_mode: str
    status: str
    provider_message_id: str = ""
    accepted_destinations_count: int = 0
    rejected_destinations_count: int = 0
    destination_count: int = 0
    destination_hashes: list[str] = field(default_factory=list)
    media_artifact_ids: list[str] = field(default_factory=list)
    capability: dict[str, Any] = field(default_factory=dict)
    retryable: bool = False
    allowlist_matched: bool = False
    idempotency_key: str = ""
    sent_at: str | None = None
    completed_at: str | None = None
    sanitized: bool = True
    related: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return sanitize_outbox_payload(
            {
                "platform": self.platform,
                "provider": self.provider,
                "mode": self.mode,
                "evidence_mode": self.evidence_mode,
                "status": self.status,
                "provider_message_id": self.provider_message_id,
                "message_id": self.provider_message_id,
                "accepted_destinations_count": self.accepted_destinations_count,
                "rejected_destinations_count": self.rejected_destinations_count,
                "destination_count": self.destination_count,
                "destination_hashes": self.destination_hashes,
                "media_artifact_ids": self.media_artifact_ids,
                "capability": sanitize_outbox_payload(self.capability),
                "retryable": self.retryable,
                "allowlist_matched": self.allowlist_matched,
                "idempotency_key": self.idempotency_key,
                "sent_at": self.sent_at,
                "completed_at": self.completed_at,
                "sanitized": self.sanitized,
                "related": sanitize_outbox_payload(self.related),
            }
        )


class GatewayConnectorAdapter(Protocol):
    platform: str
    provider: str

    def credentials_configured(self) -> bool:
        """Return whether this adapter has enough private config to send."""

    def health_check(self) -> str:
        """Return a safe health status."""

    def normalize_inbound(self, payload: dict[str, Any]) -> GatewayInboundEvent:
        """Normalize a provider payload into a backend-owned inbound event."""

    def poll(self) -> list[GatewayInboundEvent]:
        """Return newly polled inbound events, if the adapter supports polling."""

    def send(self, request: GatewaySendRequest) -> GatewaySendReceipt:
        """Send one gateway message and return a sanitized receipt."""


class BaseGatewayAdapter:
    platform = ""
    provider = ""

    def __init__(self, *, session: Any = None) -> None:
        self.session = session or requests.Session()
        self.timeout_seconds = float(getattr(settings, "GATEWAY_CONNECTOR_TIMEOUT_SECONDS", 10))

    def credentials_configured(self) -> bool:
        return bool(_credential_token(self._last_request) if hasattr(self, "_last_request") else True)

    def health_check(self) -> str:
        return "ready"

    def normalize_inbound(self, payload: dict[str, Any]) -> GatewayInboundEvent:
        return GatewayInboundEvent(
            platform=self.platform,
            provider=self.provider,
            external_message_id=str(payload.get("id") or payload.get("message_id") or ""),
            conversation_id=str(payload.get("conversation_id") or payload.get("thread_id") or ""),
            sender=str(payload.get("sender") or payload.get("from") or ""),
            text=str(payload.get("text") or payload.get("message") or payload.get("body") or ""),
            raw_metadata=payload,
        )

    def poll(self) -> list[GatewayInboundEvent]:
        return []

    def _record_connection_health(self, request: GatewaySendRequest, *, status: str) -> None:
        if not request.connection_id:
            return
        GatewayConnection.objects.filter(id=request.connection_id).update(
            last_health_check_at=timezone.now(),
            status="enabled" if status in {"ready", "accepted"} else "degraded",
        )


class FakeGatewayAdapter(BaseGatewayAdapter):
    provider = "fake"

    def __init__(self, *, platform: str, fail: bool = False) -> None:
        super().__init__()
        self.platform = normalize_platform(platform)
        self.fail = fail

    def credentials_configured(self) -> bool:
        return True

    def send(self, request: GatewaySendRequest) -> GatewaySendReceipt:
        if self.fail:
            raise GatewayConnectorError(
                "fake_provider_failure",
                "Fake gateway provider failure.",
                platform=request.platform,
                provider=self.provider,
                mode=request.mode,
            )
        return _accepted_receipt(
            request,
            provider=self.provider,
            evidence_mode=GATEWAY_EVIDENCE_PROVIDER_SEND,
            message_id=_deterministic_message_id("fg-gateway-fake", request),
        )


class TelegramGatewayAdapter(BaseGatewayAdapter):
    platform = "telegram"
    provider = "telegram"

    def credentials_configured(self) -> bool:
        return bool(_setting("TELEGRAM_BOT_TOKEN"))

    def send(self, request: GatewaySendRequest) -> GatewaySendReceipt:
        token = _credential_token(request) or _setting("TELEGRAM_BOT_TOKEN")
        if not token:
            raise _missing_credentials(request, provider=self.provider)
        chat_id = _first_destination(request)
        response = self.session.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": request.text, **_telegram_thread_payload(request)},
            timeout=self.timeout_seconds,
        )
        payload = _provider_json_or_error(response, request=request, provider=self.provider)
        message_id = str((payload.get("result") or {}).get("message_id") or "")[:255]
        return _accepted_receipt(
            request,
            provider=self.provider,
            evidence_mode=GATEWAY_EVIDENCE_PROVIDER_SEND,
            message_id=message_id,
        )


class SlackGatewayAdapter(BaseGatewayAdapter):
    platform = "slack"
    provider = "slack"

    def credentials_configured(self) -> bool:
        return bool(_setting("SLACK_BOT_TOKEN"))

    def send(self, request: GatewaySendRequest) -> GatewaySendReceipt:
        token = _credential_token(request) or _setting("SLACK_BOT_TOKEN")
        if not token:
            raise _missing_credentials(request, provider=self.provider)
        body = {
            "channel": _first_destination(request),
            "text": request.text,
        }
        thread_ts = str(request.thread.get("thread_ts") or request.metadata.get("thread_ts") or "")
        if thread_ts:
            body["thread_ts"] = thread_ts
        response = self.session.post(
            "https://slack.com/api/chat.postMessage",
            json=body,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=self.timeout_seconds,
        )
        payload = _provider_json_or_error(response, request=request, provider=self.provider)
        if payload.get("ok") is False:
            raise GatewayConnectorError(
                _safe_key(str(payload.get("error") or "slack_api_error")),
                "Slack API rejected the message.",
                platform=request.platform,
                provider=self.provider,
                mode=request.mode,
                retryable=False,
            )
        return _accepted_receipt(
            request,
            provider=self.provider,
            evidence_mode=GATEWAY_EVIDENCE_PROVIDER_SEND,
            message_id=str(payload.get("ts") or "")[:255],
        )


class WhatsAppCloudGatewayAdapter(BaseGatewayAdapter):
    platform = "whatsapp"
    provider = "whatsapp_cloud_api"

    def credentials_configured(self) -> bool:
        return bool(_setting("WHATSAPP_CLOUD_API_TOKEN") and _setting("WHATSAPP_CLOUD_PHONE_NUMBER_ID"))

    def send(self, request: GatewaySendRequest) -> GatewaySendReceipt:
        token = _credential_token(request) or _setting("WHATSAPP_CLOUD_API_TOKEN")
        phone_number_id = str(
            request.metadata.get("phone_number_id") or _setting("WHATSAPP_CLOUD_PHONE_NUMBER_ID")
        ).strip()
        if not token or not phone_number_id:
            raise _missing_credentials(request, provider=self.provider)
        response = self.session.post(
            f"https://graph.facebook.com/v20.0/{quote(phone_number_id)}/messages",
            json={
                "messaging_product": "whatsapp",
                "to": _first_destination(request).removeprefix("whatsapp:"),
                "type": "text",
                "text": {"body": request.text},
            },
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=self.timeout_seconds,
        )
        payload = _provider_json_or_error(response, request=request, provider=self.provider)
        messages = payload.get("messages") if isinstance(payload.get("messages"), list) else []
        message_id = str((messages[0] if messages else {}).get("id") or "")[:255]
        return _accepted_receipt(
            request,
            provider=self.provider,
            evidence_mode=GATEWAY_EVIDENCE_PROVIDER_SEND,
            message_id=message_id,
        )


class TwilioSmsGatewayAdapter(BaseGatewayAdapter):
    platform = "sms"
    provider = "twilio"

    def credentials_configured(self) -> bool:
        return bool(
            _setting("TWILIO_ACCOUNT_SID")
            and _setting("TWILIO_AUTH_TOKEN")
            and _setting("TWILIO_PHONE_NUMBER")
        )

    def send(self, request: GatewaySendRequest) -> GatewaySendReceipt:
        account_sid = str(request.metadata.get("account_sid") or _setting("TWILIO_ACCOUNT_SID"))
        auth_token = _credential_token(request) or _setting("TWILIO_AUTH_TOKEN")
        from_number = str(request.metadata.get("from") or _setting("TWILIO_PHONE_NUMBER"))
        if not account_sid or not auth_token or not from_number:
            raise _missing_credentials(request, provider=self.provider)
        response = self.session.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{quote(account_sid)}/Messages.json",
            data={"To": _first_destination(request), "From": from_number, "Body": request.text},
            auth=(account_sid, auth_token),
            timeout=self.timeout_seconds,
        )
        payload = _provider_json_or_error(response, request=request, provider=self.provider)
        return _accepted_receipt(
            request,
            provider=self.provider,
            evidence_mode=GATEWAY_EVIDENCE_PROVIDER_SEND,
            message_id=str(payload.get("sid") or "")[:255],
        )


class GmailApiGatewayAdapter(BaseGatewayAdapter):
    platform = "email"
    provider = "gmail"

    def credentials_configured(self) -> bool:
        return bool(_setting("GMAIL_ACCESS_TOKEN"))

    def send(self, request: GatewaySendRequest) -> GatewaySendReceipt:
        token = _credential_token(request) or _setting("GMAIL_ACCESS_TOKEN")
        if not token:
            raise _missing_credentials(request, provider=self.provider)
        message = EmailMessage()
        message["To"] = ", ".join(request.destinations())
        message["Subject"] = request.subject or "ForgeGraph message"
        from_email = str(request.metadata.get("from_email") or request.metadata.get("from") or "")
        if from_email:
            message["From"] = from_email
        if request.html:
            message.set_content(request.text or "")
            message.add_alternative(request.html, subtype="html")
        else:
            message.set_content(request.text)
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii").rstrip("=")
        response = self.session.post(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            json={"raw": raw},
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=self.timeout_seconds,
        )
        payload = _provider_json_or_error(response, request=request, provider=self.provider)
        return _accepted_receipt(
            request,
            provider=self.provider,
            evidence_mode=GATEWAY_EVIDENCE_PROVIDER_SEND,
            message_id=str(payload.get("id") or "")[:255],
        )


class SmtpGatewayAdapter(BaseGatewayAdapter):
    platform = "email"
    provider = "smtp"

    def credentials_configured(self) -> bool:
        return bool(_setting("EMAIL_SMTP_HOST") and _setting("EMAIL_ADDRESS"))

    def send(self, request: GatewaySendRequest) -> GatewaySendReceipt:
        host = str(request.metadata.get("smtp_host") or _setting("EMAIL_SMTP_HOST"))
        port = int(request.metadata.get("smtp_port") or _setting("EMAIL_SMTP_PORT") or 587)
        username = str(request.metadata.get("smtp_username") or _setting("EMAIL_ADDRESS"))
        password = _credential_token(request) or _setting("EMAIL_PASSWORD")
        if not host or not username or not password:
            raise _missing_credentials(request, provider=self.provider)
        message = EmailMessage()
        message["From"] = str(request.metadata.get("from_email") or username)
        message["To"] = ", ".join(request.destinations())
        message["Subject"] = request.subject or "ForgeGraph message"
        message.set_content(request.text or "")
        with smtplib.SMTP(host, port, timeout=self.timeout_seconds) as smtp:
            smtp.starttls()
            smtp.login(username, password)
            smtp.send_message(message)
        return _accepted_receipt(
            request,
            provider=self.provider,
            evidence_mode=GATEWAY_EVIDENCE_PROVIDER_SEND,
            message_id=_deterministic_message_id("fg-gateway-smtp", request),
        )


class MicrosoftGraphGatewayAdapter(BaseGatewayAdapter):
    platform = "msgraph_webhook"
    provider = "microsoft_graph"

    def credentials_configured(self) -> bool:
        return bool(_setting("MSGRAPH_ACCESS_TOKEN"))

    def send(self, request: GatewaySendRequest) -> GatewaySendReceipt:
        token = _credential_token(request) or _setting("MSGRAPH_ACCESS_TOKEN")
        if not token:
            raise _missing_credentials(request, provider=self.provider)
        endpoint = str(request.metadata.get("endpoint_url") or "").strip()
        if not endpoint:
            chat_id = _first_destination(request)
            endpoint = f"https://graph.microsoft.com/v1.0/chats/{quote(chat_id)}/messages"
        response = self.session.post(
            endpoint,
            json={"body": {"contentType": "text", "content": request.text}},
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=self.timeout_seconds,
        )
        payload = _provider_json_or_error(response, request=request, provider=self.provider)
        return _accepted_receipt(
            request,
            provider=self.provider,
            evidence_mode=GATEWAY_EVIDENCE_PROVIDER_SEND,
            message_id=str(payload.get("id") or "")[:255],
        )


class MatrixGatewayAdapter(BaseGatewayAdapter):
    platform = "matrix"
    provider = "matrix"

    def credentials_configured(self) -> bool:
        return bool(_setting("MATRIX_HOMESERVER") and _setting("MATRIX_ACCESS_TOKEN"))

    def send(self, request: GatewaySendRequest) -> GatewaySendReceipt:
        homeserver = str(request.metadata.get("homeserver") or _setting("MATRIX_HOMESERVER")).rstrip("/")
        token = _credential_token(request) or _setting("MATRIX_ACCESS_TOKEN")
        room_id = _first_destination(request)
        txn_id = quote(request.idempotency_key or _deterministic_message_id("fg-matrix", request))
        if not homeserver or not token:
            raise _missing_credentials(request, provider=self.provider)
        response = self.session.put(
            f"{homeserver}/_matrix/client/v3/rooms/{quote(room_id, safe='')}/send/m.room.message/{txn_id}",
            json={"msgtype": "m.text", "body": request.text},
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=self.timeout_seconds,
        )
        payload = _provider_json_or_error(response, request=request, provider=self.provider)
        return _accepted_receipt(
            request,
            provider=self.provider,
            evidence_mode=GATEWAY_EVIDENCE_PROVIDER_SEND,
            message_id=str(payload.get("event_id") or "")[:255],
        )


class HomeAssistantGatewayAdapter(BaseGatewayAdapter):
    platform = "homeassistant"
    provider = "homeassistant"

    def credentials_configured(self) -> bool:
        return bool(_setting("HASS_URL") and _setting("HASS_TOKEN"))

    def send(self, request: GatewaySendRequest) -> GatewaySendReceipt:
        base_url = str(request.metadata.get("base_url") or _setting("HASS_URL")).rstrip("/")
        token = _credential_token(request) or _setting("HASS_TOKEN")
        domain = str(request.metadata.get("domain") or "persistent_notification")
        service = str(request.metadata.get("service") or "create")
        if not base_url or not token:
            raise _missing_credentials(request, provider=self.provider)
        response = self.session.post(
            f"{base_url}/api/services/{quote(domain)}/{quote(service)}",
            json=request.metadata.get("service_data")
            or {"message": request.text, "title": request.subject or "ForgeGraph"},
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=self.timeout_seconds,
        )
        _provider_json_or_error(response, request=request, provider=self.provider)
        return _accepted_receipt(
            request,
            provider=self.provider,
            evidence_mode=GATEWAY_EVIDENCE_PROVIDER_SEND,
            message_id=_deterministic_message_id("fg-homeassistant", request),
        )


class GenericHttpGatewayAdapter(BaseGatewayAdapter):
    """Configured HTTP/sidecar adapter for vendor-specific Hermes gateway platforms."""

    def __init__(self, *, platform: str, provider: str, session: Any = None) -> None:
        super().__init__(session=session)
        self.platform = normalize_platform(platform)
        self.provider = _safe_key(provider or platform)

    def credentials_configured(self) -> bool:
        return True

    def send(self, request: GatewaySendRequest) -> GatewaySendReceipt:
        spec = _generic_http_spec(request)
        response = self.session.request(
            spec["method"],
            spec["url"],
            json=spec.get("json"),
            data=spec.get("data"),
            headers=spec.get("headers"),
            timeout=self.timeout_seconds,
        )
        payload = _provider_json_or_error(response, request=request, provider=self.provider)
        message_id = str(
            payload.get("id")
            or payload.get("message_id")
            or payload.get("messageId")
            or payload.get("event_id")
            or ""
        )[:255]
        return _accepted_receipt(
            request,
            provider=self.provider,
            evidence_mode=GATEWAY_EVIDENCE_SIDECAR_SEND
            if spec.get("sidecar")
            else GATEWAY_EVIDENCE_PROVIDER_SEND,
            message_id=message_id or _deterministic_message_id("fg-gateway-http", request),
        )


def normalize_platform(value: str) -> str:
    platform = _safe_key(value).replace("-", "_")
    return GATEWAY_PLATFORM_ALIASES.get(platform, platform)


def platform_for_tool_id(tool_id: str) -> str:
    normalized = str(tool_id or "").strip().lower()
    if not normalized.startswith("gateway.") or not normalized.endswith(".send"):
        return ""
    return normalize_platform(normalized.removeprefix("gateway.").removesuffix(".send"))


def is_gateway_tool(tool_id: str) -> bool:
    return platform_for_tool_id(tool_id) in HERMES_GATEWAY_PLATFORMS


def get_gateway_adapter(  # noqa: C901
    platform: str,
    provider: str | None = None,
    *,
    session: Any = None,
) -> GatewayConnectorAdapter:
    selected_platform = normalize_platform(platform)
    selected_provider = _safe_key(provider or selected_platform)
    if selected_provider == "fake":
        return FakeGatewayAdapter(platform=selected_platform)
    if selected_platform == "telegram":
        return TelegramGatewayAdapter(session=session)
    if selected_platform == "slack":
        return SlackGatewayAdapter(session=session)
    if selected_platform == "whatsapp":
        return WhatsAppCloudGatewayAdapter(session=session)
    if selected_platform == "sms":
        return TwilioSmsGatewayAdapter(session=session)
    if selected_platform == "email" and selected_provider == "gmail":
        return GmailApiGatewayAdapter(session=session)
    if selected_platform == "email" and selected_provider in {"smtp", "email"}:
        return SmtpGatewayAdapter(session=session)
    if selected_platform == "msgraph_webhook":
        return MicrosoftGraphGatewayAdapter(session=session)
    if selected_platform == "matrix":
        return MatrixGatewayAdapter(session=session)
    if selected_platform == "homeassistant":
        return HomeAssistantGatewayAdapter(session=session)
    return GenericHttpGatewayAdapter(
        platform=selected_platform,
        provider=selected_provider,
        session=session,
    )


def dry_run_gateway(request: GatewaySendRequest) -> GatewaySendReceipt:
    validate_gateway_request(request, dry_run=True)
    return GatewaySendReceipt(
        platform=normalize_platform(request.platform),
        provider=_safe_key(request.provider or "fake"),
        mode=GATEWAY_MODE_DRY_RUN,
        evidence_mode=GATEWAY_EVIDENCE_SANDBOX,
        status="dry_run",
        provider_message_id=_deterministic_message_id("fg-gateway-dry-run", request),
        accepted_destinations_count=len(request.destinations()),
        rejected_destinations_count=0,
        completed_at=timezone.now().isoformat(),
        idempotency_key=request.idempotency_key,
        media_artifact_ids=list(request.media_artifact_ids),
        capability=_capability_for_request(request),
        **destination_evidence(request.destinations(), allowlist_matched=False),
        related=_related_payload(request),
    )


def send_gateway(
    request: GatewaySendRequest,
    *,
    approved: bool,
    policy_allows_live: bool,
    adapter: GatewayConnectorAdapter | None = None,
) -> GatewaySendReceipt:
    validate_gateway_request(request, dry_run=False)
    selected_adapter = adapter or get_gateway_adapter(request.platform, request.provider)
    validate_real_send_allowed(
        request,
        approved=approved,
        policy_allows_live=policy_allows_live,
        adapter=selected_adapter,
    )
    return selected_adapter.send(request)


def validate_gateway_request(request: GatewaySendRequest, *, dry_run: bool) -> None:
    platform = normalize_platform(request.platform)
    mode = GATEWAY_MODE_DRY_RUN if dry_run else request.mode or GATEWAY_MODE_REAL_SEND
    if platform not in HERMES_GATEWAY_PLATFORMS and not _capability_exists(request):
        raise GatewayConnectorError(
            "gateway_platform_unsupported",
            "Gateway platform is not supported.",
            platform=platform,
            provider=request.provider,
            mode=mode,
            blocked_before_provider_call=True,
        )
    destinations = request.destinations()
    max_destinations = int(getattr(settings, "GATEWAY_CONNECTOR_MAX_RECIPIENTS", 10))
    if len(destinations) > max_destinations:
        raise GatewayConnectorError(
            "destination_cap_exceeded",
            "Gateway destination count exceeds the configured limit.",
            platform=platform,
            provider=request.provider,
            mode=mode,
            blocked_before_provider_call=True,
        )
    if not dry_run and not destinations and platform not in {"webhook", "api_server", "homeassistant"}:
        raise GatewayConnectorError(
            "destination_required",
            "Real gateway send requires at least one destination.",
            platform=platform,
            provider=request.provider,
            mode=mode,
            blocked_before_provider_call=True,
        )
    if not dry_run and not str(request.text or request.html or "").strip():
        raise GatewayConnectorError(
            "message_required",
            "Real gateway send requires message text or HTML content.",
            platform=platform,
            provider=request.provider,
            mode=mode,
            blocked_before_provider_call=True,
        )


def validate_real_send_allowed(
    request: GatewaySendRequest,
    *,
    approved: bool,
    policy_allows_live: bool,
    adapter: GatewayConnectorAdapter | None = None,
) -> None:
    if not approved:
        raise GatewayConnectorError(
            "approval_required",
            "Approved human gate is required before real gateway send.",
            platform=request.platform,
            provider=request.provider,
            mode=GATEWAY_MODE_REAL_SEND,
            blocked_before_provider_call=True,
        )
    if not policy_allows_live:
        raise GatewayConnectorError(
            "live_execution_not_allowed",
            "Policy does not allow real gateway send.",
            platform=request.platform,
            provider=request.provider,
            mode=GATEWAY_MODE_REAL_SEND,
            blocked_before_provider_call=True,
        )
    if not bool(getattr(settings, "GATEWAY_CONNECTOR_ALLOW_REAL_SEND", False)):
        raise GatewayConnectorError(
            "real_send_disabled",
            "Real gateway send is disabled by environment configuration.",
            platform=request.platform,
            provider=request.provider,
            mode=GATEWAY_MODE_REAL_SEND,
            blocked_before_provider_call=True,
        )
    if not request.operator_confirmed:
        raise GatewayConnectorError(
            "operator_confirmation_required",
            "Operator confirmation is required before real gateway send.",
            platform=request.platform,
            provider=request.provider,
            mode=GATEWAY_MODE_REAL_SEND,
            blocked_before_provider_call=True,
        )
    selected_adapter = adapter or get_gateway_adapter(request.platform, request.provider)
    if not selected_adapter.credentials_configured() and not _credential_token(request):
        raise _missing_credentials(request, provider=selected_adapter.provider)
    validate_destination_allowlist(request.destinations(), platform=request.platform, provider=request.provider)


def validate_destination_allowlist(
    destinations: list[str],
    *,
    platform: str = "",
    provider: str = "",
) -> None:
    values = _normalized_destinations(destinations)
    allowlist = _allowlist_values()
    if "*" in allowlist:
        return
    if not allowlist:
        raise GatewayConnectorError(
            "destination_allowlist_required",
            "Gateway destination allowlist is not configured.",
            platform=platform,
            provider=provider,
            mode=GATEWAY_MODE_REAL_SEND,
            blocked_before_provider_call=True,
        )
    rejected = [value for value in values if not _destination_allowed(value, allowlist)]
    if rejected:
        raise GatewayConnectorError(
            "destination_not_allowlisted",
            "One or more gateway destinations are not allowlisted.",
            platform=platform,
            provider=provider,
            mode=GATEWAY_MODE_REAL_SEND,
            blocked_before_provider_call=True,
        )


def destination_evidence(destinations: list[str], *, allowlist_matched: bool) -> dict[str, Any]:
    normalized = _normalized_destinations(destinations)
    hashes = [f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}" for value in normalized]
    return {
        "destination_count": len(normalized),
        "destination_hashes": hashes,
        "allowlist_matched": allowlist_matched,
    }


def sanitize_provider_error(
    exc: Exception,
    *,
    platform: str = "",
    provider: str = "",
    mode: str = "",
) -> dict[str, Any]:
    if isinstance(exc, GatewayConnectorError):
        return exc.as_dict()
    return GatewayConnectorError(
        "provider_request_failed",
        str(exc.__class__.__name__),
        platform=platform,
        provider=provider,
        mode=mode,
        retryable=True,
    ).as_dict()


def verify_hmac_signature(*, secret: str, body: bytes, signature: str, algorithm: str = "sha256") -> bool:
    if not secret or not signature:
        return False
    digestmod = hashlib.sha1 if algorithm == "sha1" else hashlib.sha256
    expected = hmac.new(secret.encode("utf-8"), body, digestmod).hexdigest()
    candidates = {expected, f"{algorithm}={expected}"}
    return any(hmac.compare_digest(signature, candidate) for candidate in candidates)


def _accepted_receipt(
    request: GatewaySendRequest,
    *,
    provider: str,
    evidence_mode: str,
    message_id: str,
) -> GatewaySendReceipt:
    evidence = destination_evidence(request.destinations(), allowlist_matched=True)
    completed_at = timezone.now().isoformat()
    return GatewaySendReceipt(
        platform=normalize_platform(request.platform),
        provider=_safe_key(provider),
        mode=GATEWAY_MODE_REAL_SEND if request.mode == GATEWAY_MODE_REAL_SEND else request.mode,
        evidence_mode=evidence_mode,
        status="accepted",
        provider_message_id=message_id[:255],
        accepted_destinations_count=evidence["destination_count"],
        rejected_destinations_count=0,
        sent_at=completed_at,
        completed_at=completed_at,
        idempotency_key=request.idempotency_key,
        media_artifact_ids=list(request.media_artifact_ids),
        capability=_capability_for_request(request),
        **evidence,
        related=_related_payload(request),
    )


def _generic_http_spec(request: GatewaySendRequest) -> dict[str, Any]:
    platform = normalize_platform(request.platform)
    metadata = request.metadata
    token = _credential_token(request)
    sidecar_url = str(
        metadata.get("sidecar_url")
        or _setting(f"GATEWAY_{platform.upper()}_SIDECAR_URL")
        or _setting(f"{platform.upper()}_SIDECAR_URL")
    ).rstrip("/")
    endpoint_url = str(
        metadata.get("endpoint_url")
        or metadata.get("url")
        or _setting(f"GATEWAY_{platform.upper()}_ENDPOINT_URL")
    ).strip()
    if sidecar_url and not endpoint_url:
        endpoint_url = urljoin(f"{sidecar_url}/", "send")
    if not endpoint_url:
        endpoint_url = _official_endpoint_for_platform(request, token=token)
    if not endpoint_url:
        raise GatewayConnectorError(
            "gateway_endpoint_missing",
            "Gateway endpoint or sidecar URL is not configured.",
            platform=platform,
            provider=request.provider,
            mode=request.mode,
            blocked_before_provider_call=True,
        )
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        **({} if not token else {"Authorization": f"Bearer {token}"}),
    }
    headers.update({str(k): str(v) for k, v in (metadata.get("headers") or {}).items()} if isinstance(metadata.get("headers"), dict) else {})
    return {
        "method": str(metadata.get("method") or "POST").upper(),
        "url": endpoint_url,
        "headers": headers,
        "json": _generic_body(request),
        "sidecar": bool(sidecar_url),
    }


def _official_endpoint_for_platform(request: GatewaySendRequest, *, token: str) -> str:
    platform = normalize_platform(request.platform)
    metadata = request.metadata
    if platform == "dingtalk":
        access_token = token or str(metadata.get("access_token") or _setting("DINGTALK_ACCESS_TOKEN"))
        return f"https://oapi.dingtalk.com/robot/send?access_token={quote(access_token)}" if access_token else ""
    if platform == "feishu":
        receive_id_type = str(metadata.get("receive_id_type") or "chat_id")
        return f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type={quote(receive_id_type)}"
    if platform == "feishu_comment":
        file_token = str(metadata.get("file_token") or "")
        return f"https://open.feishu.cn/open-apis/drive/v1/files/{quote(file_token)}/comments" if file_token else ""
    if platform == "qqbot":
        channel_id = _first_destination(request)
        return f"https://api.sgroup.qq.com/channels/{quote(channel_id)}/messages" if channel_id else ""
    if platform == "wecom":
        access_token = token or str(metadata.get("access_token") or _setting("WECOM_ACCESS_TOKEN"))
        return f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={quote(access_token)}" if access_token else ""
    if platform == "weixin":
        access_token = token or str(metadata.get("access_token") or _setting("WEIXIN_ACCESS_TOKEN"))
        return f"https://api.weixin.qq.com/cgi-bin/message/custom/send?access_token={quote(access_token)}" if access_token else ""
    if platform == "bluebubbles":
        server_url = str(metadata.get("server_url") or _setting("BLUEBUBBLES_SERVER_URL")).rstrip("/")
        return f"{server_url}/api/v1/message/text" if server_url else ""
    if platform == "signal":
        base_url = str(metadata.get("signal_cli_rest_url") or _setting("SIGNAL_HTTP_URL")).rstrip("/")
        account = str(metadata.get("account") or _setting("SIGNAL_ACCOUNT"))
        return f"{base_url}/v2/send/{quote(account)}" if base_url and account else ""
    if platform in {"api_server", "webhook", "yuanbao"}:
        return str(metadata.get("endpoint_url") or metadata.get("webhook_url") or "").strip()
    return ""


def _generic_body(request: GatewaySendRequest) -> dict[str, Any]:
    platform = normalize_platform(request.platform)
    destination = _first_destination(request, required=False)
    if platform == "dingtalk":
        return {"msgtype": "text", "text": {"content": request.text}}
    if platform == "feishu":
        return {"receive_id": destination, "msg_type": "text", "content": json.dumps({"text": request.text})}
    if platform == "qqbot":
        return {"content": request.text}
    if platform == "wecom":
        return {
            "touser": destination,
            "msgtype": "text",
            "agentid": str(request.metadata.get("agent_id") or ""),
            "text": {"content": request.text},
        }
    if platform == "weixin":
        return {"touser": destination, "msgtype": "text", "text": {"content": request.text}}
    if platform == "bluebubbles":
        return {
            "chatGuid": destination or request.metadata.get("chat_guid"),
            "message": request.text,
            "password": request.metadata.get("password") or _setting("BLUEBUBBLES_PASSWORD"),
        }
    if platform == "signal":
        return {"message": request.text, "recipients": request.destinations()}
    return {
        "platform": platform,
        "provider": request.provider,
        "to": request.destinations(),
        "text": request.text,
        "subject": request.subject,
        "thread": sanitize_outbox_payload(request.thread),
        "metadata": sanitize_outbox_payload(request.metadata),
        "idempotency_key": request.idempotency_key,
    }


def _provider_json_or_error(response: Any, *, request: GatewaySendRequest, provider: str) -> dict[str, Any]:
    content = getattr(response, "content", b"") or b""
    if len(content) > _MAX_PROVIDER_RESPONSE_BYTES:
        raise GatewayConnectorError(
            "provider_response_too_large",
            "Gateway provider response exceeded the safe size limit.",
            platform=request.platform,
            provider=provider,
            mode=request.mode,
            retryable=True,
        )
    status_code = int(getattr(response, "status_code", 0) or 0)
    try:
        payload = response.json() if content else {}
    except ValueError:
        payload = {}
    if status_code >= 400:
        code = "provider_http_error"
        message = f"Gateway provider request failed with HTTP {status_code}."
        if isinstance(payload, dict):
            raw_error = payload.get("error")
            error = raw_error if isinstance(raw_error, dict) else payload
            code = str(error.get("name") or error.get("code") or code)
            message = str(error.get("message") or message)
        raise GatewayConnectorError(
            code,
            message,
            platform=request.platform,
            provider=provider,
            mode=request.mode,
            retryable=status_code == 429 or status_code >= 500,
        )
    return payload if isinstance(payload, dict) else {}


def _credential_token(request: GatewaySendRequest) -> str:
    if not request.credential_id:
        return ""
    queryset = APIKey.objects.all()
    if request.organization_id:
        queryset = queryset.filter(organization_id=request.organization_id)
    credential = queryset.filter(id=request.credential_id).first()
    if credential is None:
        return ""
    try:
        return decrypt_api_key(bytes(credential.encrypted_key))
    except Exception:
        return ""


def _missing_credentials(request: GatewaySendRequest, *, provider: str) -> GatewayConnectorError:
    return GatewayConnectorError(
        "gateway_credentials_missing",
        "Gateway provider credentials are not configured.",
        platform=request.platform,
        provider=provider,
        mode=request.mode,
        blocked_before_provider_call=True,
    )


def _first_destination(request: GatewaySendRequest, *, required: bool = True) -> str:
    destinations = request.destinations()
    if destinations:
        return destinations[0]
    if required:
        raise GatewayConnectorError(
            "destination_required",
            "Gateway destination is required.",
            platform=request.platform,
            provider=request.provider,
            mode=request.mode,
            blocked_before_provider_call=True,
        )
    return ""


def _telegram_thread_payload(request: GatewaySendRequest) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for source_key, target_key in (
        ("message_thread_id", "message_thread_id"),
        ("reply_to_message_id", "reply_to_message_id"),
    ):
        value = request.thread.get(source_key) or request.metadata.get(source_key)
        if value:
            payload[target_key] = value
    return payload


def _related_payload(request: GatewaySendRequest) -> dict[str, Any]:
    return {
        "connection_id": str(request.connection_id or ""),
        "credential_id": str(request.credential_id or ""),
        "schedule_id": str(request.schedule_id or ""),
        "approval_id": request.approval_id or "",
        "thread": sanitize_outbox_payload(request.thread),
        "metadata": sanitize_outbox_payload(request.metadata),
    }


def _capability_for_request(request: GatewaySendRequest) -> dict[str, Any]:
    try:
        from application.services.gateway_registry import capability_payload, get_capability

        return capability_payload(
            get_capability(platform=request.platform, provider=request.provider)
        ) or {}
    except Exception:
        return {}


def _capability_exists(request: GatewaySendRequest) -> bool:
    try:
        from application.services.gateway_registry import get_capability

        return get_capability(platform=request.platform, provider=request.provider) is not None
    except Exception:
        return False


def _normalized_destinations(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = str(raw or "").strip()
        if not value or value in seen:
            continue
        result.append(value[:255])
        seen.add(value)
    return result


def _allowlist_values() -> set[str]:
    raw = getattr(settings, "GATEWAY_RECIPIENT_ALLOWLIST", [])
    if isinstance(raw, str):
        values = raw.split(",")
    else:
        values = list(raw or [])
    return {str(value or "").strip() for value in values if str(value or "").strip()}


def _destination_allowed(destination: str, allowlist: set[str]) -> bool:
    if destination in allowlist:
        return True
    digest = f"sha256:{hashlib.sha256(destination.encode('utf-8')).hexdigest()}"
    return digest in allowlist


def _deterministic_message_id(prefix: str, request: GatewaySendRequest) -> str:
    digest = hashlib.sha256(
        json.dumps(
            {
                "platform": normalize_platform(request.platform),
                "idempotency_key": request.idempotency_key,
                "destinations": request.destinations(),
                "text_hash": hashlib.sha256(str(request.text or "").encode("utf-8")).hexdigest(),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:24]
    return f"{prefix}-{digest}"


def _setting(name: str) -> str:
    return str(getattr(settings, name, "") or "").strip()


def _safe_error_message(value: str) -> str:
    redacted = redact_text(str(value or ""))
    redacted = _SECRET_RE.sub("[redacted-secret]", redacted)
    return redacted[:_MAX_ERROR_MESSAGE_LENGTH] or "Gateway connector failed."


def _safe_key(value: str) -> str:
    return re.sub(r"[^a-z0-9_.-]+", "_", str(value or "").strip().lower())[:80]
