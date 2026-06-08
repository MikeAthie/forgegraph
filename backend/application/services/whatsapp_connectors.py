"""Provider-agnostic outbound messaging connector primitives for deployment orchestration."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urljoin

import requests
from django.conf import settings
from django.utils import timezone

from application.services.domain_event_outbox import sanitize_outbox_payload
from application.services.redaction import redact_text

WHATSAPP_SEND_DRY_RUN_TOOL_ID = "whatsapp.send_dry_run"
WHATSAPP_SEND_MANUAL_TOOL_ID = "whatsapp.send_manual"
WHATSAPP_WEB_AUTOMATION_SEND_TOOL_ID = "whatsapp.web_automation_send"
WHATSAPP_CONNECTOR_TOOL_IDS = {
    WHATSAPP_SEND_DRY_RUN_TOOL_ID,
    WHATSAPP_SEND_MANUAL_TOOL_ID,
    WHATSAPP_WEB_AUTOMATION_SEND_TOOL_ID,
}
WHATSAPP_CONNECTOR_IDS = {"whatsapp_connector", "whatsapp_web_automation_connector"}

WHATSAPP_PROVIDER_FAKE = "fake"
WHATSAPP_PROVIDER_OPEN_WA_WEB = "open_wa_web"
WHATSAPP_PROVIDER_HERMES_BRIDGE = "hermes_bridge"
WHATSAPP_PROVIDER_CLOUD_API = "whatsapp_cloud_api"

WHATSAPP_MODE_DRY_RUN = "dry_run"
WHATSAPP_MODE_MANUAL_OPS = "manual_ops"
WHATSAPP_MODE_REAL_SEND = "real_send"
WHATSAPP_EVIDENCE_SANDBOX = "sandbox"
WHATSAPP_EVIDENCE_WEB_AUTOMATION = "web_automation"
WHATSAPP_EVIDENCE_PROVIDER_SEND = "provider_send"

_MAX_ERROR_MESSAGE_LENGTH = 300
_MAX_PROVIDER_RESPONSE_BYTES = 8192
_PHONE_TOKEN_RE = re.compile(r"(?<!\w)\+?\d[\d\s().-]{6,}\d(?!\w)")
_SESSION_SECRET_RE = re.compile(
    r"(?i)\b(?:session|qr)[_-]?(?:secret|token|ref)[A-Za-z0-9._~+/=-]*\b"
)
_READY_SESSION_STATUSES = {"ready", "authenticated", "connected"}


class WhatsAppConnectorError(RuntimeError):
    """Safe domain error for outbound messaging validation or provider failures."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        provider: str = "",
        mode: str = "",
        blocked_before_provider_call: bool = False,
        retryable: bool = False,
    ) -> None:
        self.code = str(code or "whatsapp_connector_error")
        self.message = _safe_error_message(message or "Messaging connector failed.")
        self.provider = _safe_key(provider)
        self.mode = _safe_key(mode)
        self.blocked_before_provider_call = blocked_before_provider_call
        self.retryable = retryable
        super().__init__(self.message)

    def as_dict(self) -> dict[str, Any]:
        return {
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
class WhatsAppSendRequest:
    provider: str
    mode: str
    to: list[str] = field(default_factory=list)
    text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    idempotency_key: str = ""
    approval_id: str | None = None
    whiteboard_id: str | None = None
    deployment_channel_id: str | None = None
    asset_id: str | None = None
    publication_draft_id: str | None = None
    operator_confirmed: bool = False
    session_ref: str = ""

    def all_recipients(self) -> list[str]:
        return [*self.to]


@dataclass(frozen=True, slots=True)
class WhatsAppSendReceipt:
    provider: str
    mode: str
    evidence_mode: str
    status: str
    provider_message_id: str = ""
    accepted_recipients_count: int = 0
    rejected_recipients_count: int = 0
    recipient_count: int = 0
    recipient_hashes: list[str] = field(default_factory=list)
    recipient_domains: list[str] = field(default_factory=list)
    allowlist_matched: bool = False
    session_required: bool = False
    session_status: str = ""
    idempotency_key: str = ""
    sent_at: str | None = None
    completed_at: str | None = None
    sanitized: bool = True
    related: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return sanitize_outbox_payload(
            {
                "provider": self.provider,
                "mode": self.mode,
                "evidence_mode": self.evidence_mode,
                "status": self.status,
                "provider_message_id": self.provider_message_id,
                "message_id": self.provider_message_id,
                "accepted_recipients_count": self.accepted_recipients_count,
                "rejected_recipients_count": self.rejected_recipients_count,
                "recipient_count": self.recipient_count,
                "recipient_hashes": self.recipient_hashes,
                "recipient_domains": self.recipient_domains,
                "allowlist_matched": self.allowlist_matched,
                "session_required": self.session_required,
                "session_status": self.session_status,
                "idempotency_key": self.idempotency_key,
                "sent_at": self.sent_at,
                "completed_at": self.completed_at,
                "sanitized": self.sanitized,
                "related": sanitize_outbox_payload(self.related),
            }
        )


class WhatsAppProviderAdapter(Protocol):
    provider: str

    def credentials_configured(self) -> bool:
        """Return whether this adapter has enough private config to send."""

    def session_status(self) -> str:
        """Return a safe session status string."""

    def send(self, request: WhatsAppSendRequest) -> WhatsAppSendReceipt:
        """Send one outbound message request and return a sanitized receipt."""


class FakeWhatsAppAdapter:
    provider = WHATSAPP_PROVIDER_FAKE

    def __init__(self, *, fail: bool = False, failure_code: str = "fake_provider_failure") -> None:
        self.fail = fail
        self.failure_code = failure_code
        self.send_count = 0

    def credentials_configured(self) -> bool:
        return True

    def session_status(self) -> str:
        return "ready"

    def send(self, request: WhatsAppSendRequest) -> WhatsAppSendReceipt:
        self.send_count += 1
        if self.fail:
            raise WhatsAppConnectorError(
                self.failure_code,
                "Fake messaging provider failure.",
                provider=self.provider,
                mode=request.mode,
                retryable=False,
            )
        evidence = recipient_evidence(request.all_recipients(), allowlist_matched=True)
        completed_at = timezone.now().isoformat()
        message_id = _deterministic_message_id(
            prefix="fg-whatsapp-fake",
            idempotency_key=request.idempotency_key,
            recipient_hashes=evidence["recipient_hashes"],
        )
        return WhatsAppSendReceipt(
            provider=self.provider,
            mode=request.mode,
            evidence_mode=_evidence_mode_for_request(request),
            status="accepted",
            provider_message_id=message_id,
            accepted_recipients_count=evidence["recipient_count"],
            rejected_recipients_count=0,
            session_required=False,
            session_status="not_required",
            completed_at=completed_at,
            sent_at=completed_at if request.mode == WHATSAPP_MODE_REAL_SEND else None,
            idempotency_key=request.idempotency_key,
            **evidence,
            related=_related_payload(request),
        )


class OpenWaWebAutomationAdapter:
    """Optional sidecar adapter for open-wa/wa-automate-python style web automation."""

    provider = WHATSAPP_PROVIDER_OPEN_WA_WEB

    def __init__(
        self,
        *,
        sidecar_url: str | None = None,
        session_ref: str | None = None,
        timeout_seconds: float | None = None,
        session: Any = None,
    ) -> None:
        self.sidecar_url = (
            (
                sidecar_url
                if sidecar_url is not None
                else getattr(settings, "WHATSAPP_WEB_AUTOMATION_SIDECAR_URL", "")
                or getattr(settings, "SELENIUM_URL", "")
            )
            .strip()
            .rstrip("/")
        )
        self.session_ref = (
            session_ref
            if session_ref is not None
            else getattr(settings, "WHATSAPP_WEB_AUTOMATION_SESSION_REF", "")
        ).strip()
        self.timeout_seconds = float(
            timeout_seconds
            if timeout_seconds is not None
            else getattr(settings, "WHATSAPP_CONNECTOR_TIMEOUT_SECONDS", 10)
        )
        self.session = session or requests.Session()

    def credentials_configured(self) -> bool:
        return (
            bool(getattr(settings, "WHATSAPP_WEB_AUTOMATION_ENABLED", False))
            and bool(self.sidecar_url)
            and bool(self.session_ref)
        )

    def session_status(self) -> str:
        if not self.credentials_configured():
            return "missing"
        try:
            response = self.session.get(
                urljoin(f"{self.sidecar_url}/", "health"),
                params={"session_ref": self.session_ref},
                timeout=self.timeout_seconds,
            )
        except requests.RequestException:
            return "unreachable"
        if len(getattr(response, "content", b"") or b"") > _MAX_PROVIDER_RESPONSE_BYTES:
            return "unknown"
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        status_code = int(getattr(response, "status_code", 0) or 0)
        if status_code >= 400:
            return "unhealthy"
        if not isinstance(payload, dict):
            return "unknown"
        return _safe_session_status(
            payload.get("status") or payload.get("session_status") or "unknown"
        )

    def send(self, request: WhatsAppSendRequest) -> WhatsAppSendReceipt:
        if not self.credentials_configured():
            raise WhatsAppConnectorError(
                "whatsapp_session_missing",
                "Messaging web automation session is not configured.",
                provider=self.provider,
                mode=request.mode,
                blocked_before_provider_call=True,
            )
        status = self.session_status()
        if status not in _READY_SESSION_STATUSES:
            raise WhatsAppConnectorError(
                "whatsapp_session_unhealthy",
                "Messaging web automation session is not ready.",
                provider=self.provider,
                mode=request.mode,
                blocked_before_provider_call=True,
            )
        try:
            response = self.session.post(
                urljoin(f"{self.sidecar_url}/", "send-message"),
                json=_open_wa_body(request, session_ref=self.session_ref),
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "User-Agent": "forgegraph-whatsapp-web-automation/1.0",
                },
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise WhatsAppConnectorError(
                "provider_request_failed",
                "Messaging web automation request failed.",
                provider=self.provider,
                mode=request.mode,
                retryable=True,
            ) from exc
        payload = _provider_json_or_error(
            response, provider=self.provider, mode=request.mode
        )
        return sanitize_provider_response(
            payload, provider=self.provider, request=request, session_status=status
        )


class HermesBridgeWhatsAppAdapter:
    """HTTP adapter for Hermes-style WhatsApp bridge sidecars."""

    provider = WHATSAPP_PROVIDER_HERMES_BRIDGE

    def __init__(
        self,
        *,
        bridge_url: str | None = None,
        session_ref: str | None = None,
        enabled: bool | None = None,
        timeout_seconds: float | None = None,
        session: Any = None,
    ) -> None:
        self.bridge_url = (
            bridge_url
            if bridge_url is not None
            else getattr(settings, "WHATSAPP_HERMES_BRIDGE_URL", "")
        ).strip().rstrip("/")
        self.session_ref = (
            session_ref
            if session_ref is not None
            else getattr(settings, "WHATSAPP_HERMES_BRIDGE_SESSION_REF", "")
        ).strip()
        self.enabled = bool(
            enabled
            if enabled is not None
            else getattr(settings, "WHATSAPP_HERMES_BRIDGE_ENABLED", False)
        )
        self.timeout_seconds = float(
            timeout_seconds
            if timeout_seconds is not None
            else getattr(settings, "WHATSAPP_CONNECTOR_TIMEOUT_SECONDS", 10)
        )
        self.session = session or requests.Session()

    def credentials_configured(self) -> bool:
        return bool(self.enabled and self.bridge_url and self.session_ref)

    def session_status(self) -> str:
        if not self.credentials_configured():
            return "missing"
        headers = {
            "Accept": "application/json",
            "User-Agent": "forgegraph-whatsapp-hermes-bridge/1.0",
            "X-ForgeGraph-Session-Ref": self.session_ref,
        }
        for endpoint in ("health", "status"):
            try:
                response = self.session.get(
                    urljoin(f"{self.bridge_url}/", endpoint),
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
            except requests.RequestException:
                return "unreachable"
            status_code = int(getattr(response, "status_code", 0) or 0)
            if endpoint == "health" and status_code in {404, 405}:
                continue
            return _session_status_from_response(response)
        return "unknown"

    def send(self, request: WhatsAppSendRequest) -> WhatsAppSendReceipt:
        if not self.credentials_configured():
            raise WhatsAppConnectorError(
                "whatsapp_session_missing",
                "Messaging bridge session is not configured.",
                provider=self.provider,
                mode=request.mode,
                blocked_before_provider_call=True,
            )
        status = self.session_status()
        if status not in _READY_SESSION_STATUSES:
            raise WhatsAppConnectorError(
                "whatsapp_session_unhealthy",
                "Messaging bridge session is not ready.",
                provider=self.provider,
                mode=request.mode,
                blocked_before_provider_call=True,
            )
        body = _hermes_bridge_body(request, session_ref=self.session_ref)
        try:
            response = self.session.post(
                urljoin(f"{self.bridge_url}/", "send-message"),
                json=body,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "User-Agent": "forgegraph-whatsapp-hermes-bridge/1.0",
                },
                timeout=self.timeout_seconds,
            )
            if int(getattr(response, "status_code", 0) or 0) in {404, 405}:
                response = self.session.post(
                    urljoin(f"{self.bridge_url}/", "send"),
                    json=body,
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                        "User-Agent": "forgegraph-whatsapp-hermes-bridge/1.0",
                    },
                    timeout=self.timeout_seconds,
                )
        except requests.RequestException as exc:
            raise WhatsAppConnectorError(
                "provider_request_failed",
                "Messaging bridge request failed.",
                provider=self.provider,
                mode=request.mode,
                retryable=True,
            ) from exc
        payload = _provider_json_or_error(response, provider=self.provider, mode=request.mode)
        return sanitize_provider_response(
            payload, provider=self.provider, request=request, session_status=status
        )


class WhatsAppCloudApiAdapter:
    provider = WHATSAPP_PROVIDER_CLOUD_API

    def __init__(
        self,
        *,
        api_token: str | None = None,
        phone_number_id: str | None = None,
        api_base_url: str | None = None,
        timeout_seconds: float | None = None,
        session: Any = None,
    ) -> None:
        self.api_token = (
            api_token if api_token is not None else getattr(settings, "WHATSAPP_CLOUD_API_TOKEN", "")
        ).strip()
        self.phone_number_id = (
            phone_number_id
            if phone_number_id is not None
            else getattr(settings, "WHATSAPP_CLOUD_PHONE_NUMBER_ID", "")
        ).strip()
        self.api_base_url = (
            api_base_url
            if api_base_url is not None
            else getattr(settings, "WHATSAPP_CLOUD_API_BASE_URL", "https://graph.facebook.com/v20.0")
        ).rstrip("/")
        self.timeout_seconds = float(
            timeout_seconds
            if timeout_seconds is not None
            else getattr(settings, "WHATSAPP_CONNECTOR_TIMEOUT_SECONDS", 10)
        )
        self.session = session or requests.Session()

    def credentials_configured(self) -> bool:
        return bool(self.api_token and self.phone_number_id)

    def session_status(self) -> str:
        return "not_applicable"

    def send(self, request: WhatsAppSendRequest) -> WhatsAppSendReceipt:
        if not self.credentials_configured():
            raise WhatsAppConnectorError(
                "whatsapp_credentials_missing",
                "Official messaging provider credentials are not configured.",
                provider=self.provider,
                mode=request.mode,
                blocked_before_provider_call=True,
            )
        recipients = _normalized_recipients(request.to)
        if len(recipients) != 1:
            raise WhatsAppConnectorError(
                "single_recipient_required",
                "Official messaging provider send requires exactly one recipient.",
                provider=self.provider,
                mode=request.mode,
                blocked_before_provider_call=True,
            )
        try:
            response = self.session.post(
                f"{self.api_base_url}/{self.phone_number_id}/messages",
                json={
                    "messaging_product": "whatsapp",
                    "to": recipients[0].removeprefix("+"),
                    "type": "text",
                    "text": {"body": request.text},
                },
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {self.api_token}",
                    "Content-Type": "application/json",
                    "User-Agent": "forgegraph-whatsapp-cloud-api/1.0",
                },
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise WhatsAppConnectorError(
                "provider_request_failed",
                "Official messaging provider request failed.",
                provider=self.provider,
                mode=request.mode,
                retryable=True,
            ) from exc
        payload = _provider_json_or_error(response, provider=self.provider, mode=request.mode)
        messages = payload.get("messages") if isinstance(payload.get("messages"), list) else []
        message = messages[0] if messages and isinstance(messages[0], dict) else {}
        provider_payload = {"id": str(message.get("id") or payload.get("id") or "")}
        return sanitize_provider_response(
            provider_payload,
            provider=self.provider,
            request=request,
            session_status="not_applicable",
        )


def get_whatsapp_provider_adapter(
    provider: str | None = None,
    *,
    session: Any = None,
) -> WhatsAppProviderAdapter:
    selected = _safe_key(
        provider or getattr(settings, "WHATSAPP_CONNECTOR_PROVIDER", "fake") or "fake"
    )
    if selected == WHATSAPP_PROVIDER_OPEN_WA_WEB:
        return OpenWaWebAutomationAdapter(session=session)
    if selected == WHATSAPP_PROVIDER_HERMES_BRIDGE:
        return HermesBridgeWhatsAppAdapter(session=session)
    if selected == WHATSAPP_PROVIDER_CLOUD_API:
        return WhatsAppCloudApiAdapter(session=session)
    if selected == WHATSAPP_PROVIDER_FAKE:
        return FakeWhatsAppAdapter()
    raise WhatsAppConnectorError(
        "whatsapp_provider_unsupported",
        "Messaging provider is not supported.",
        provider=selected,
        blocked_before_provider_call=True,
    )


def dry_run_whatsapp(request: WhatsAppSendRequest) -> WhatsAppSendReceipt:
    validate_whatsapp_request(request, dry_run=True)
    evidence = recipient_evidence(request.all_recipients(), allowlist_matched=False)
    completed_at = timezone.now().isoformat()
    provider = _safe_key(
        request.provider or getattr(settings, "WHATSAPP_CONNECTOR_PROVIDER", "fake") or "fake"
    )
    message_id = _deterministic_message_id(
        prefix="fg-whatsapp-dry-run",
        idempotency_key=request.idempotency_key,
        recipient_hashes=evidence["recipient_hashes"],
    )
    return WhatsAppSendReceipt(
        provider=provider,
        mode=WHATSAPP_MODE_DRY_RUN,
        evidence_mode=WHATSAPP_EVIDENCE_SANDBOX,
        status="accepted",
        provider_message_id=message_id,
        accepted_recipients_count=evidence["recipient_count"],
        rejected_recipients_count=0,
        session_required=False,
        session_status="not_required",
        completed_at=completed_at,
        idempotency_key=request.idempotency_key,
        **evidence,
        related=_related_payload(request),
    )


def manual_ops_whatsapp(request: WhatsAppSendRequest) -> WhatsAppSendReceipt:
    validate_whatsapp_request(request, dry_run=True)
    evidence = recipient_evidence(request.all_recipients(), allowlist_matched=False)
    completed_at = timezone.now().isoformat()
    provider = _safe_key(
        request.provider or getattr(settings, "WHATSAPP_CONNECTOR_PROVIDER", "fake") or "fake"
    )
    message_id = _deterministic_message_id(
        prefix="fg-whatsapp-manual",
        idempotency_key=request.idempotency_key,
        recipient_hashes=evidence["recipient_hashes"],
    )
    return WhatsAppSendReceipt(
        provider=provider,
        mode=WHATSAPP_MODE_MANUAL_OPS,
        evidence_mode=WHATSAPP_EVIDENCE_WEB_AUTOMATION,
        status="accepted",
        provider_message_id=message_id,
        accepted_recipients_count=evidence["recipient_count"],
        rejected_recipients_count=0,
        session_required=False,
        session_status="manual_ops",
        completed_at=completed_at,
        idempotency_key=request.idempotency_key,
        **evidence,
        related=_related_payload(request),
    )


def send_whatsapp(
    request: WhatsAppSendRequest,
    *,
    approved: bool,
    policy_allows_live: bool,
    adapter: WhatsAppProviderAdapter | None = None,
) -> WhatsAppSendReceipt:
    validate_whatsapp_request(request, dry_run=False)
    selected_adapter = adapter or get_whatsapp_provider_adapter(request.provider)
    validate_real_send_allowed(
        request,
        approved=approved,
        policy_allows_live=policy_allows_live,
        adapter=selected_adapter,
    )
    return selected_adapter.send(request)


def validate_whatsapp_request(request: WhatsAppSendRequest, *, dry_run: bool) -> None:
    mode = WHATSAPP_MODE_DRY_RUN if dry_run else request.mode or WHATSAPP_MODE_REAL_SEND
    recipients = _normalized_recipients(request.all_recipients())
    max_recipients = int(getattr(settings, "WHATSAPP_WEB_AUTOMATION_MAX_RECIPIENTS", 5))
    if len(recipients) > max_recipients:
        raise WhatsAppConnectorError(
            "recipient_cap_exceeded",
            "Messaging recipient count exceeds the configured limit.",
            provider=request.provider,
            mode=mode,
            blocked_before_provider_call=True,
        )
    if not dry_run and not recipients:
        raise WhatsAppConnectorError(
            "recipient_required",
            "Real messaging send requires at least one recipient.",
            provider=request.provider,
            mode=mode,
            blocked_before_provider_call=True,
        )
    for value in recipients:
        _validate_recipient(value, provider=request.provider, mode=mode)
    if not dry_run and not str(request.text or "").strip():
        raise WhatsAppConnectorError(
            "message_required",
            "Real messaging send requires message text.",
            provider=request.provider,
            mode=mode,
            blocked_before_provider_call=True,
        )


def validate_real_send_allowed(
    request: WhatsAppSendRequest,
    *,
    approved: bool,
    policy_allows_live: bool,
    adapter: WhatsAppProviderAdapter | None = None,
) -> None:
    if not approved:
        raise WhatsAppConnectorError(
            "approval_required",
            "Approved human gate is required before real messaging send.",
            provider=request.provider,
            mode=WHATSAPP_MODE_REAL_SEND,
            blocked_before_provider_call=True,
        )
    if not policy_allows_live:
        raise WhatsAppConnectorError(
            "live_execution_not_allowed",
            "Policy does not allow real messaging send.",
            provider=request.provider,
            mode=WHATSAPP_MODE_REAL_SEND,
            blocked_before_provider_call=True,
        )
    if not (
        bool(getattr(settings, "WHATSAPP_CONNECTOR_ALLOW_REAL_SEND", False))
        or bool(getattr(settings, "WHATSAPP_WEB_AUTOMATION_ALLOW_REAL_SEND", False))
    ):
        raise WhatsAppConnectorError(
            "real_send_disabled",
            "Real messaging send is disabled by environment configuration.",
            provider=request.provider,
            mode=WHATSAPP_MODE_REAL_SEND,
            blocked_before_provider_call=True,
        )
    if not request.operator_confirmed:
        raise WhatsAppConnectorError(
            "operator_confirmation_required",
            "Operator confirmation is required before real messaging send.",
            provider=request.provider,
            mode=WHATSAPP_MODE_REAL_SEND,
            blocked_before_provider_call=True,
        )
    selected_adapter = adapter or get_whatsapp_provider_adapter(request.provider)
    if request.provider == WHATSAPP_PROVIDER_OPEN_WA_WEB and not bool(
        getattr(settings, "WHATSAPP_WEB_AUTOMATION_ENABLED", False)
    ):
        raise WhatsAppConnectorError(
            "whatsapp_web_automation_disabled",
            "Messaging web automation provider is disabled by environment configuration.",
            provider=request.provider,
            mode=WHATSAPP_MODE_REAL_SEND,
            blocked_before_provider_call=True,
        )
    if not selected_adapter.credentials_configured():
        raise WhatsAppConnectorError(
            "whatsapp_session_missing",
            "Messaging web automation session is not configured.",
            provider=request.provider,
            mode=WHATSAPP_MODE_REAL_SEND,
            blocked_before_provider_call=True,
        )
    validate_recipient_allowlist(request.all_recipients(), provider=request.provider)
    session_status = selected_adapter.session_status()
    if (
        request.provider in {WHATSAPP_PROVIDER_OPEN_WA_WEB, WHATSAPP_PROVIDER_HERMES_BRIDGE}
        and session_status not in _READY_SESSION_STATUSES
    ):
        raise WhatsAppConnectorError(
            "whatsapp_session_unhealthy",
            "Messaging web automation session is not ready.",
            provider=request.provider,
            mode=WHATSAPP_MODE_REAL_SEND,
            blocked_before_provider_call=True,
        )


def validate_recipient_allowlist(recipients: list[str], *, provider: str = "") -> None:
    values = _normalized_recipients(recipients)
    allowlist = _allowlist_values()
    if not allowlist:
        raise WhatsAppConnectorError(
            "recipient_allowlist_required",
            "Messaging recipient allowlist is not configured.",
            provider=provider,
            mode=WHATSAPP_MODE_REAL_SEND,
            blocked_before_provider_call=True,
        )
    rejected = [value for value in values if not _recipient_allowed(value, allowlist)]
    if rejected:
        raise WhatsAppConnectorError(
            "recipient_not_allowlisted",
            "One or more messaging recipients are not allowlisted.",
            provider=provider,
            mode=WHATSAPP_MODE_REAL_SEND,
            blocked_before_provider_call=True,
        )


def recipient_evidence(
    recipients: list[str],
    *,
    allowlist_matched: bool,
) -> dict[str, Any]:
    normalized = _normalized_recipients(recipients)
    domains = sorted({value.rsplit("@", 1)[1] for value in normalized if "@" in value})
    hashes = [f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}" for value in normalized]
    return {
        "recipient_count": len(normalized),
        "recipient_hashes": hashes,
        "recipient_domains": domains,
        "allowlist_matched": allowlist_matched,
    }


def sanitize_provider_response(
    response_json: dict[str, Any],
    *,
    provider: str,
    request: WhatsAppSendRequest,
    session_status: str = "ready",
) -> WhatsAppSendReceipt:
    message_id = _provider_message_id(response_json)
    evidence = recipient_evidence(request.all_recipients(), allowlist_matched=True)
    completed_at = timezone.now().isoformat()
    evidence_mode = (
        WHATSAPP_EVIDENCE_PROVIDER_SEND
        if provider == WHATSAPP_PROVIDER_CLOUD_API
        else WHATSAPP_EVIDENCE_WEB_AUTOMATION
    )
    return WhatsAppSendReceipt(
        provider=_safe_key(provider),
        mode=WHATSAPP_MODE_REAL_SEND,
        evidence_mode=evidence_mode,
        status="accepted",
        provider_message_id=message_id,
        accepted_recipients_count=evidence["recipient_count"],
        rejected_recipients_count=0,
        session_required=provider in {WHATSAPP_PROVIDER_OPEN_WA_WEB, WHATSAPP_PROVIDER_HERMES_BRIDGE},
        session_status=_safe_session_status(session_status),
        completed_at=completed_at,
        sent_at=completed_at,
        idempotency_key=request.idempotency_key,
        **evidence,
        related=_related_payload(request),
    )


def sanitize_provider_error(
    exc: Exception,
    *,
    provider: str = "",
    mode: str = "",
) -> dict[str, Any]:
    if isinstance(exc, WhatsAppConnectorError):
        return exc.as_dict()
    return WhatsAppConnectorError(
        "provider_request_failed",
        str(exc.__class__.__name__),
        provider=provider,
        mode=mode,
        retryable=True,
    ).as_dict()


def _provider_json_or_error(response: Any, *, provider: str, mode: str) -> dict[str, Any]:
    content = getattr(response, "content", b"") or b""
    if len(content) > _MAX_PROVIDER_RESPONSE_BYTES:
        raise WhatsAppConnectorError(
            "provider_response_too_large",
            "Messaging provider response exceeded the safe size limit.",
            provider=provider,
            mode=mode,
            retryable=True,
        )
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    status_code = int(getattr(response, "status_code", 0) or 0)
    if status_code >= 400:
        code, message = _provider_error_details(payload, response=response, status_code=status_code)
        raise WhatsAppConnectorError(
            code,
            message,
            provider=provider,
            mode=mode,
            retryable=status_code == 429 or status_code >= 500,
        )
    if not isinstance(payload, dict):
        raise WhatsAppConnectorError(
            "invalid_provider_response",
            "Messaging provider response was not a JSON object.",
            provider=provider,
            mode=mode,
            retryable=True,
        )
    return payload


def _provider_message_id(response_json: dict[str, Any]) -> str:
    direct = response_json.get("id") or response_json.get("message_id") or response_json.get("messageId")
    if direct:
        return _safe_provider_message_id(direct)
    for container_key in ("message", "result"):
        container = response_json.get(container_key)
        if isinstance(container, dict):
            nested = container.get("id") or container.get("message_id") or container.get("messageId")
            if nested:
                return _safe_provider_message_id(nested)
    messages = response_json.get("messages")
    if isinstance(messages, list):
        for message in messages:
            if isinstance(message, dict):
                nested = message.get("id") or message.get("message_id") or message.get("messageId")
                if nested:
                    return _safe_provider_message_id(nested)
    return ""


def _safe_provider_message_id(value: Any) -> str:
    return _safe_error_message(str(value or ""))[:255]


def _provider_error_details(payload: Any, *, response: Any, status_code: int) -> tuple[str, str]:
    code = "provider_http_error"
    message = f"Messaging provider request failed with HTTP {status_code}."
    if isinstance(payload, dict):
        raw_error = payload.get("error")
        error = raw_error if isinstance(raw_error, dict) else payload
        code = _safe_error_code(error.get("name") or error.get("code") or code)
    elif getattr(response, "reason", ""):
        code = _safe_error_code(response.reason)
    return code, message


def _open_wa_body(request: WhatsAppSendRequest, *, session_ref: str) -> dict[str, Any]:
    return {
        "session_ref": session_ref,
        "to": _normalized_recipients(request.to),
        "message": str(request.text or ""),
        "idempotency_key": request.idempotency_key[:256],
    }


def _hermes_bridge_body(request: WhatsAppSendRequest, *, session_ref: str) -> dict[str, Any]:
    recipients = _normalized_recipients(request.to)
    return {
        "session_ref": session_ref,
        "to": recipients[0] if len(recipients) == 1 else recipients,
        "recipients": recipients,
        "message": str(request.text or ""),
        "text": str(request.text or ""),
        "idempotency_key": request.idempotency_key[:256],
    }


def _session_status_from_response(response: Any) -> str:
    if len(getattr(response, "content", b"") or b"") > _MAX_PROVIDER_RESPONSE_BYTES:
        return "unknown"
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    status_code = int(getattr(response, "status_code", 0) or 0)
    if status_code >= 400:
        return "unhealthy"
    if not isinstance(payload, dict):
        return "unknown"
    session_payload = payload.get("session") if isinstance(payload.get("session"), dict) else {}
    connected = payload.get("connected") is True or payload.get("isConnected") is True
    return _safe_session_status(
        payload.get("status")
        or payload.get("session_status")
        or payload.get("state")
        or payload.get("connection_status")
        or session_payload.get("status")
        or session_payload.get("state")
        or ("connected" if connected else "unknown")
    )


def _validate_recipient(value: str, *, provider: str, mode: str) -> None:
    if not _recipient_digits(value):
        raise WhatsAppConnectorError(
            "invalid_recipient",
            "Messaging recipient is invalid.",
            provider=provider,
            mode=mode,
            blocked_before_provider_call=True,
        )


def _normalized_recipients(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = _normalize_recipient(raw)
        if not value or value in seen:
            continue
        result.append(value)
        seen.add(value)
    return result


def _normalize_recipient(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    if text.startswith("whatsapp:"):
        text = text.split(":", 1)[1].strip()
    if "wa.me/" in text:
        text = text.rsplit("wa.me/", 1)[1].strip("/")
    if "@" in text:
        local, domain = text.split("@", 1)
        digits = _recipient_digits(local)
        return f"+{digits}@{domain}" if digits else ""
    digits = _recipient_digits(text)
    return f"+{digits}" if digits else ""


def _recipient_digits(value: Any) -> str:
    digits = re.sub(r"\D+", "", str(value or ""))
    if len(digits) < 8 or len(digits) > 15:
        return ""
    return digits


def _allowlist_values() -> set[str]:
    raw = getattr(settings, "WHATSAPP_RECIPIENT_ALLOWLIST", [])
    if isinstance(raw, str):
        values = raw.split(",")
    else:
        values = list(raw or [])
    result: set[str] = set()
    for value in values:
        text = str(value or "").strip().lower()
        if not text:
            continue
        if text.startswith("sha256:"):
            result.add(text)
            continue
        normalized = _normalize_recipient(text)
        if normalized:
            result.add(normalized)
    return result


def _recipient_allowed(recipient: str, allowlist: set[str]) -> bool:
    if recipient in allowlist:
        return True
    digest = f"sha256:{hashlib.sha256(recipient.encode('utf-8')).hexdigest()}"
    return digest in allowlist


def _evidence_mode_for_request(request: WhatsAppSendRequest) -> str:
    if request.mode == WHATSAPP_MODE_REAL_SEND and request.provider == WHATSAPP_PROVIDER_CLOUD_API:
        return WHATSAPP_EVIDENCE_PROVIDER_SEND
    if request.mode in {WHATSAPP_MODE_REAL_SEND, WHATSAPP_MODE_MANUAL_OPS}:
        return WHATSAPP_EVIDENCE_WEB_AUTOMATION
    return WHATSAPP_EVIDENCE_SANDBOX


def _related_payload(request: WhatsAppSendRequest) -> dict[str, Any]:
    return {
        "whiteboard_id": request.whiteboard_id or "",
        "deployment_channel_id": request.deployment_channel_id or "",
        "asset_id": request.asset_id or "",
        "publication_draft_id": request.publication_draft_id or "",
        "approval_id": request.approval_id or "",
        "metadata": sanitize_outbox_payload(request.metadata),
    }


def _deterministic_message_id(
    *, prefix: str, idempotency_key: str, recipient_hashes: list[str]
) -> str:
    digest = hashlib.sha256(
        json.dumps(
            {
                "idempotency_key": idempotency_key,
                "recipient_hashes": recipient_hashes,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:24]
    return f"{prefix}-{digest}"


def _safe_error_message(value: str) -> str:
    redacted = redact_text(str(value or ""))
    redacted = redacted.replace("Bearer ***REDACTED***", "[redacted-token]")
    redacted = _PHONE_TOKEN_RE.sub("[redacted-phone]", redacted)
    redacted = _SESSION_SECRET_RE.sub("[redacted-session]", redacted)
    return redacted[:_MAX_ERROR_MESSAGE_LENGTH] or "Messaging connector failed."


def _safe_key(value: str) -> str:
    return re.sub(r"[^a-z0-9_.-]+", "_", str(value or "").strip().lower())[:80]


def _safe_error_code(value: Any) -> str:
    sanitized = _safe_error_message(str(value or ""))
    sanitized = _PHONE_TOKEN_RE.sub("", sanitized)
    key = _safe_key(sanitized)
    if not key or key in {"redacted-phone", "redacted-session", "redacted-token"}:
        return "provider_http_error"
    return key


def _safe_session_status(value: Any) -> str:
    status = _safe_key(str(value or "unknown"))
    return (
        status
        if status
        in {
            "ready",
            "authenticated",
            "connected",
            "missing",
            "unreachable",
            "unhealthy",
            "unknown",
            "manual_ops",
            "not_required",
            "not_applicable",
        }
        else "unknown"
    )
