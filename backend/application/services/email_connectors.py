"""Provider-agnostic email connector primitives for deployment orchestration."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urljoin

import requests
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils import timezone

from application.services.domain_event_outbox import sanitize_outbox_payload
from application.services.redaction import redact_text

EMAIL_SEND_DRY_RUN_TOOL_ID = "email.send_dry_run"
EMAIL_SEND_TOOL_ID = "email.send"
EMAIL_CONNECTOR_TOOL_IDS = {
    EMAIL_SEND_DRY_RUN_TOOL_ID,
    EMAIL_SEND_TOOL_ID,
}
EMAIL_CONNECTOR_IDS = {"email_connector"}

EMAIL_MODE_DRY_RUN = "dry_run"
EMAIL_MODE_REAL_SEND = "real_send"
EMAIL_EVIDENCE_SANDBOX = "sandbox"
EMAIL_EVIDENCE_PROVIDER_SEND = "provider_send"

_MAX_ERROR_MESSAGE_LENGTH = 300
_MAX_PROVIDER_RESPONSE_BYTES = 8192
_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_HTML_FRAGMENT_RE = re.compile(r"<[^>]+>.*?</[^>]+>|<[^>]+>", re.IGNORECASE | re.DOTALL)


class EmailConnectorError(RuntimeError):
    """Safe domain error for email connector validation or provider failures."""

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
        self.code = str(code or "email_connector_error")
        self.message = _safe_error_message(message or "Email connector failed.")
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
class EmailSendRequest:
    provider: str
    mode: str
    from_email: str = ""
    from_name: str = ""
    to: list[str] = field(default_factory=list)
    cc: list[str] = field(default_factory=list)
    bcc: list[str] = field(default_factory=list)
    subject: str = ""
    html: str = ""
    text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    idempotency_key: str = ""
    approval_id: str | None = None
    whiteboard_id: str | None = None
    deployment_channel_id: str | None = None
    asset_id: str | None = None
    publication_draft_id: str | None = None
    allow_cc: bool = False
    allow_bcc: bool = False
    requires_unsubscribe_footer: bool = False

    def all_recipients(self) -> list[str]:
        return [*self.to, *self.cc, *self.bcc]


@dataclass(frozen=True, slots=True)
class EmailSendReceipt:
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
    idempotency_key: str = ""
    sent_at: str | None = None
    completed_at: str | None = None
    sanitized: bool = True
    related: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        payload = {
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
            "idempotency_key": self.idempotency_key,
            "sent_at": self.sent_at,
            "completed_at": self.completed_at,
            "sanitized": self.sanitized,
            "related": sanitize_outbox_payload(self.related),
        }
        return sanitize_outbox_payload(payload)


class EmailProviderAdapter(Protocol):
    provider: str

    def credentials_configured(self) -> bool:
        """Return whether this adapter has enough private config to send."""

    def send(self, request: EmailSendRequest) -> EmailSendReceipt:
        """Send one email request and return a sanitized provider receipt."""


class FakeEmailProviderAdapter:
    provider = "fake"

    def __init__(self, *, fail: bool = False, failure_code: str = "fake_provider_failure") -> None:
        self.fail = fail
        self.failure_code = failure_code
        self.send_count = 0

    def credentials_configured(self) -> bool:
        return True

    def send(self, request: EmailSendRequest) -> EmailSendReceipt:
        self.send_count += 1
        if self.fail:
            raise EmailConnectorError(
                self.failure_code,
                "Fake email provider failure.",
                provider=self.provider,
                mode=request.mode,
                retryable=False,
            )
        evidence = recipient_evidence(request.all_recipients(), allowlist_matched=True)
        completed_at = timezone.now().isoformat()
        message_id = _deterministic_message_id(
            prefix="fg-email-fake",
            idempotency_key=request.idempotency_key,
            subject=request.subject,
            recipient_hashes=evidence["recipient_hashes"],
        )
        return EmailSendReceipt(
            provider=self.provider,
            mode=EMAIL_MODE_REAL_SEND,
            evidence_mode=EMAIL_EVIDENCE_PROVIDER_SEND,
            status="accepted",
            provider_message_id=message_id,
            accepted_recipients_count=evidence["recipient_count"],
            rejected_recipients_count=0,
            completed_at=completed_at,
            sent_at=completed_at,
            idempotency_key=request.idempotency_key,
            **evidence,
            related=_related_payload(request),
        )


class ResendEmailProviderAdapter:
    provider = "resend"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        api_base_url: str | None = None,
        timeout_seconds: float | None = None,
        session: Any = None,
    ) -> None:
        self.api_key = (
            api_key if api_key is not None else getattr(settings, "RESEND_API_KEY", "")
        ).strip()
        self.api_base_url = (
            api_base_url
            if api_base_url is not None
            else getattr(settings, "RESEND_API_BASE_URL", "https://api.resend.com")
        ).rstrip("/")
        self.timeout_seconds = float(
            timeout_seconds
            if timeout_seconds is not None
            else getattr(settings, "EMAIL_CONNECTOR_TIMEOUT_SECONDS", 10)
        )
        self.session = session or requests.Session()

    def credentials_configured(self) -> bool:
        return bool(self.api_key)

    def send(self, request: EmailSendRequest) -> EmailSendReceipt:
        if not self.credentials_configured():
            raise EmailConnectorError(
                "email_credentials_missing",
                "Email provider credentials are not configured.",
                provider=self.provider,
                mode=request.mode,
                blocked_before_provider_call=True,
            )
        body = _resend_body(request)
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "forgegraph-email-connector/1.0",
        }
        if request.idempotency_key:
            headers["Idempotency-Key"] = request.idempotency_key[:256]
        try:
            response = self.session.post(
                urljoin(f"{self.api_base_url}/", "emails"),
                json=body,
                headers=headers,
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise EmailConnectorError(
                "provider_request_failed",
                "Email provider request failed.",
                provider=self.provider,
                mode=request.mode,
                retryable=True,
            ) from exc
        payload = _provider_json_or_error(response, provider=self.provider, mode=request.mode)
        return sanitize_provider_response(
            payload,
            provider=self.provider,
            request=request,
        )


def get_email_provider_adapter(
    provider: str | None = None,
    *,
    session: Any = None,
) -> EmailProviderAdapter:
    selected = _safe_key(
        provider or getattr(settings, "EMAIL_CONNECTOR_PROVIDER", "fake") or "fake"
    )
    if selected == "resend":
        return ResendEmailProviderAdapter(session=session)
    if selected == "fake":
        return FakeEmailProviderAdapter()
    raise EmailConnectorError(
        "email_provider_unsupported",
        "Email provider is not supported.",
        provider=selected,
        blocked_before_provider_call=True,
    )


def dry_run_email(request: EmailSendRequest) -> EmailSendReceipt:
    validate_email_request(request, dry_run=True)
    evidence = recipient_evidence(request.all_recipients(), allowlist_matched=False)
    completed_at = timezone.now().isoformat()
    provider = _safe_key(
        request.provider or getattr(settings, "EMAIL_CONNECTOR_PROVIDER", "fake") or "fake"
    )
    message_id = _deterministic_message_id(
        prefix="fg-email-dry-run",
        idempotency_key=request.idempotency_key,
        subject=request.subject,
        recipient_hashes=evidence["recipient_hashes"],
    )
    return EmailSendReceipt(
        provider=provider,
        mode=EMAIL_MODE_DRY_RUN,
        evidence_mode=EMAIL_EVIDENCE_SANDBOX,
        status="dry_run",
        provider_message_id=message_id,
        accepted_recipients_count=evidence["recipient_count"],
        rejected_recipients_count=0,
        completed_at=completed_at,
        idempotency_key=request.idempotency_key,
        **evidence,
        related=_related_payload(request),
    )


def send_email(
    request: EmailSendRequest,
    *,
    approved: bool,
    policy_allows_live: bool,
    adapter: EmailProviderAdapter | None = None,
) -> EmailSendReceipt:
    validate_email_request(request, dry_run=False)
    selected_adapter = adapter or get_email_provider_adapter(request.provider)
    validate_real_send_allowed(
        request,
        approved=approved,
        policy_allows_live=policy_allows_live,
        adapter=selected_adapter,
    )
    return selected_adapter.send(request)


def validate_email_request(request: EmailSendRequest, *, dry_run: bool) -> None:
    mode = EMAIL_MODE_DRY_RUN if dry_run else EMAIL_MODE_REAL_SEND
    recipients = _normalized_recipients(request.all_recipients())
    max_recipients = int(getattr(settings, "EMAIL_CONNECTOR_MAX_RECIPIENTS", 50))
    if len(recipients) > max_recipients:
        raise EmailConnectorError(
            "recipient_cap_exceeded",
            "Email recipient count exceeds the configured limit.",
            provider=request.provider,
            mode=mode,
            blocked_before_provider_call=True,
        )
    if not dry_run and not recipients:
        raise EmailConnectorError(
            "recipient_required",
            "Real email send requires at least one recipient.",
            provider=request.provider,
            mode=mode,
            blocked_before_provider_call=True,
        )
    for value in recipients:
        _validate_address(value, provider=request.provider, mode=mode)
    if request.cc and not request.allow_cc:
        raise EmailConnectorError(
            "cc_not_allowed",
            "Email cc recipients are not allowed by this request.",
            provider=request.provider,
            mode=mode,
            blocked_before_provider_call=True,
        )
    if request.bcc and not request.allow_bcc:
        raise EmailConnectorError(
            "bcc_not_allowed",
            "Email bcc recipients are not allowed by this request.",
            provider=request.provider,
            mode=mode,
            blocked_before_provider_call=True,
        )
    if not str(request.subject or "").strip():
        raise EmailConnectorError(
            "subject_required",
            "Email subject is required.",
            provider=request.provider,
            mode=mode,
            blocked_before_provider_call=True,
        )
    if not dry_run and not str(request.html or request.text or "").strip():
        raise EmailConnectorError(
            "content_required",
            "Real email send requires text or HTML content.",
            provider=request.provider,
            mode=mode,
            blocked_before_provider_call=True,
        )


def validate_real_send_allowed(
    request: EmailSendRequest,
    *,
    approved: bool,
    policy_allows_live: bool,
    adapter: EmailProviderAdapter | None = None,
) -> None:
    if not approved:
        raise EmailConnectorError(
            "approval_required",
            "Approved human gate is required before real email send.",
            provider=request.provider,
            mode=EMAIL_MODE_REAL_SEND,
            blocked_before_provider_call=True,
        )
    if not policy_allows_live:
        raise EmailConnectorError(
            "live_execution_not_allowed",
            "Policy does not allow real email send.",
            provider=request.provider,
            mode=EMAIL_MODE_REAL_SEND,
            blocked_before_provider_call=True,
        )
    if not bool(getattr(settings, "EMAIL_CONNECTOR_ALLOW_REAL_SEND", False)):
        raise EmailConnectorError(
            "real_send_disabled",
            "Real email send is disabled by environment configuration.",
            provider=request.provider,
            mode=EMAIL_MODE_REAL_SEND,
            blocked_before_provider_call=True,
        )
    if not str(request.from_email or "").strip():
        raise EmailConnectorError(
            "sender_required",
            "Email sender is not configured.",
            provider=request.provider,
            mode=EMAIL_MODE_REAL_SEND,
            blocked_before_provider_call=True,
        )
    _validate_address(request.from_email, provider=request.provider, mode=EMAIL_MODE_REAL_SEND)
    selected_adapter = adapter or get_email_provider_adapter(request.provider)
    if not selected_adapter.credentials_configured():
        raise EmailConnectorError(
            "email_credentials_missing",
            "Email provider credentials are not configured.",
            provider=request.provider,
            mode=EMAIL_MODE_REAL_SEND,
            blocked_before_provider_call=True,
        )
    validate_recipient_allowlist(request.all_recipients(), provider=request.provider)
    if request.requires_unsubscribe_footer and not _has_unsubscribe_marker(request):
        raise EmailConnectorError(
            "unsubscribe_footer_required",
            "Email policy requires an unsubscribe marker before real send.",
            provider=request.provider,
            mode=EMAIL_MODE_REAL_SEND,
            blocked_before_provider_call=True,
        )


def validate_recipient_allowlist(recipients: list[str], *, provider: str = "") -> None:
    values = _normalized_recipients(recipients)
    allowlist = _allowlist_values()
    if not allowlist:
        raise EmailConnectorError(
            "recipient_allowlist_required",
            "Email recipient allowlist is not configured.",
            provider=provider,
            mode=EMAIL_MODE_REAL_SEND,
            blocked_before_provider_call=True,
        )
    rejected = [value for value in values if not _recipient_allowed(value, allowlist)]
    if rejected:
        raise EmailConnectorError(
            "recipient_not_allowlisted",
            "One or more email recipients are not allowlisted.",
            provider=provider,
            mode=EMAIL_MODE_REAL_SEND,
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
    request: EmailSendRequest,
) -> EmailSendReceipt:
    message_id = str(response_json.get("id") or response_json.get("message_id") or "")[:255]
    evidence = recipient_evidence(request.all_recipients(), allowlist_matched=True)
    completed_at = timezone.now().isoformat()
    return EmailSendReceipt(
        provider=_safe_key(provider),
        mode=EMAIL_MODE_REAL_SEND,
        evidence_mode=EMAIL_EVIDENCE_PROVIDER_SEND,
        status="accepted",
        provider_message_id=message_id,
        accepted_recipients_count=evidence["recipient_count"],
        rejected_recipients_count=0,
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
    if isinstance(exc, EmailConnectorError):
        return exc.as_dict()
    return EmailConnectorError(
        "provider_request_failed",
        str(exc.__class__.__name__),
        provider=provider,
        mode=mode,
        retryable=True,
    ).as_dict()


def _provider_json_or_error(response: Any, *, provider: str, mode: str) -> dict[str, Any]:
    content = getattr(response, "content", b"") or b""
    if len(content) > _MAX_PROVIDER_RESPONSE_BYTES:
        raise EmailConnectorError(
            "provider_response_too_large",
            "Email provider response exceeded the safe size limit.",
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
        raise EmailConnectorError(
            code,
            message,
            provider=provider,
            mode=mode,
            retryable=status_code == 429 or status_code >= 500,
        )
    if not isinstance(payload, dict):
        raise EmailConnectorError(
            "invalid_provider_response",
            "Email provider response was not a JSON object.",
            provider=provider,
            mode=mode,
            retryable=True,
        )
    return payload


def _provider_error_details(
    payload: Any,
    *,
    response: Any,
    status_code: int,
) -> tuple[str, str]:
    code = "provider_http_error"
    message = f"Email provider request failed with HTTP {status_code}."
    if isinstance(payload, dict):
        raw_error = payload.get("error")
        error = raw_error if isinstance(raw_error, dict) else payload
        code = str(error.get("name") or error.get("code") or code)
        message = str(error.get("message") or message)
    elif getattr(response, "reason", ""):
        message = str(response.reason)
    return _safe_key(code), _safe_error_message(message)


def _resend_body(request: EmailSendRequest) -> dict[str, Any]:
    body: dict[str, Any] = {
        "from": _format_from_address(request.from_email, request.from_name),
        "to": _normalized_recipients(request.to),
        "subject": str(request.subject or "").strip(),
    }
    if request.html:
        body["html"] = str(request.html)
    if request.text:
        body["text"] = str(request.text)
    if request.cc:
        body["cc"] = _normalized_recipients(request.cc)
    if request.bcc:
        body["bcc"] = _normalized_recipients(request.bcc)
    return body


def _format_from_address(email: str, name: str) -> str:
    address = str(email or "").strip()
    display_name = str(name or "").strip()
    if not display_name:
        return address
    safe_name = display_name.replace("<", "").replace(">", "").replace('"', "").strip()
    return f"{safe_name} <{address}>"


def _validate_address(value: str, *, provider: str, mode: str) -> None:
    try:
        validate_email(value)
    except ValidationError as exc:
        raise EmailConnectorError(
            "invalid_email_address",
            "Email address is invalid.",
            provider=provider,
            mode=mode,
            blocked_before_provider_call=True,
        ) from exc


def _normalized_recipients(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = str(raw or "").strip().lower()
        if not value or value in seen:
            continue
        result.append(value)
        seen.add(value)
    return result


def _allowlist_values() -> set[str]:
    raw = getattr(settings, "EMAIL_CONNECTOR_RECIPIENT_ALLOWLIST", [])
    if isinstance(raw, str):
        values = raw.split(",")
    else:
        values = list(raw or [])
    return {str(value).strip().lower() for value in values if str(value).strip()}


def _recipient_allowed(address: str, allowlist: set[str]) -> bool:
    if address in allowlist:
        return True
    domain = address.rsplit("@", 1)[1] if "@" in address else ""
    return f"@{domain}" in allowlist


def _has_unsubscribe_marker(request: EmailSendRequest) -> bool:
    content = f"{request.html}\n{request.text}".lower()
    return "unsubscribe" in content


def _related_payload(request: EmailSendRequest) -> dict[str, Any]:
    return {
        "whiteboard_id": request.whiteboard_id or "",
        "deployment_channel_id": request.deployment_channel_id or "",
        "asset_id": request.asset_id or "",
        "publication_draft_id": request.publication_draft_id or "",
        "approval_id": request.approval_id or "",
        "metadata": sanitize_outbox_payload(request.metadata),
    }


def _deterministic_message_id(
    *,
    prefix: str,
    idempotency_key: str,
    subject: str,
    recipient_hashes: list[str],
) -> str:
    digest = hashlib.sha256(
        json.dumps(
            {
                "idempotency_key": idempotency_key,
                "subject": subject,
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
    redacted = _HTML_FRAGMENT_RE.sub("[redacted-html]", redacted)
    redacted = _EMAIL_RE.sub("[redacted-email]", redacted)
    return redacted[:_MAX_ERROR_MESSAGE_LENGTH] or "Email connector failed."


def _safe_key(value: str) -> str:
    return re.sub(r"[^a-z0-9_.-]+", "_", str(value or "").strip().lower())[:80]
