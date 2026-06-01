"""Provider-agnostic social publishing connector primitives."""

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

SOCIAL_PUBLISH_DRY_RUN_TOOL_ID = "social.publish_dry_run"
SOCIAL_MANUAL_PUBLISH_RECORD_TOOL_ID = "social.manual_publish_record"
SOCIAL_PROVIDER_PUBLISH_TOOL_ID = "social.provider_publish"
SOCIAL_CONNECTOR_TOOL_IDS = {
    SOCIAL_PUBLISH_DRY_RUN_TOOL_ID,
    SOCIAL_MANUAL_PUBLISH_RECORD_TOOL_ID,
    SOCIAL_PROVIDER_PUBLISH_TOOL_ID,
}
SOCIAL_CONNECTOR_IDS = {"social_connector"}

SOCIAL_PROVIDER_FAKE = "fake"
SOCIAL_PROVIDER_MANUAL = "manual"
SOCIAL_PROVIDER_META_GRAPH = "meta_graph"

SOCIAL_MODE_DRY_RUN = "dry_run"
SOCIAL_MODE_MANUAL_PUBLISH_RECORD = "manual_publish_record"
SOCIAL_MODE_PROVIDER_PUBLISH = "provider_publish"
SOCIAL_EVIDENCE_SANDBOX = "sandbox"
SOCIAL_EVIDENCE_MANUAL_PUBLISH = "manual_publish"
SOCIAL_EVIDENCE_PROVIDER_PUBLISH = "provider_publish"

_MAX_ERROR_MESSAGE_LENGTH = 300
_MAX_PROVIDER_RESPONSE_BYTES = 8192
_URL_RE = re.compile(r"https?://[^\s'\"<>]+", re.IGNORECASE)
_TOKEN_RE = re.compile(
    r"(?i)\b(?:access[_-]?token|app[_-]?secret|bearer|secret|token)[A-Za-z0-9._~+/=:;-]*\b"
)


class SocialConnectorError(RuntimeError):
    """Safe domain error for social connector validation or provider failures."""

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
        self.code = str(code or "social_connector_error")
        self.message = _safe_error_message(message or "Social connector failed.")
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
class SocialPublishRequest:
    provider: str
    platform: str
    mode: str
    account_id: str = ""
    page_id: str = ""
    profile_id: str = ""
    asset_ids: list[str] = field(default_factory=list)
    publication_draft_id: str | None = None
    caption: str = ""
    link_url: str = ""
    media_url: str = ""
    external_post_url: str = ""
    external_post_id: str = ""
    scheduled_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    idempotency_key: str = ""
    approval_id: str | None = None
    whiteboard_id: str | None = None
    deployment_channel_id: str | None = None
    asset_approved: bool = False
    caption_approved: bool = False
    compliance_gate_passed: bool = False
    originality_check_passed: bool = False
    requires_compliance_gate: bool = False
    requires_originality_check: bool = False
    operator_confirmed: bool = False

    def target_account(self) -> str:
        return str(self.account_id or self.page_id or self.profile_id or "").strip()


@dataclass(frozen=True, slots=True)
class SocialPublishReceipt:
    provider: str
    platform: str
    mode: str
    evidence_mode: str
    status: str
    provider_post_id: str = ""
    provider_container_id: str = ""
    asset_count: int = 0
    media_asset_ids: list[str] = field(default_factory=list)
    caption_hash: str = ""
    account_id_hash: str = ""
    page_id_hash: str = ""
    profile_id_hash: str = ""
    external_post_url_hash: str = ""
    external_post_id_hash: str = ""
    idempotency_key: str = ""
    completed_at: str | None = None
    sanitized: bool = True
    related: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return sanitize_outbox_payload(
            {
                "provider": self.provider,
                "platform": self.platform,
                "mode": self.mode,
                "evidence_mode": self.evidence_mode,
                "status": self.status,
                "provider_post_id": self.provider_post_id,
                "provider_container_id": self.provider_container_id,
                "asset_count": self.asset_count,
                "media_asset_ids": self.media_asset_ids,
                "caption_hash": self.caption_hash,
                "account_id_hash": self.account_id_hash,
                "page_id_hash": self.page_id_hash,
                "profile_id_hash": self.profile_id_hash,
                "external_post_url_hash": self.external_post_url_hash,
                "external_post_id_hash": self.external_post_id_hash,
                "idempotency_key": self.idempotency_key,
                "completed_at": self.completed_at,
                "sanitized": self.sanitized,
                "related": sanitize_outbox_payload(self.related),
            }
        )


class SocialProviderAdapter(Protocol):
    provider: str

    def credentials_configured(self) -> bool:
        """Return whether this adapter has enough private config to publish."""

    def publish(self, request: SocialPublishRequest) -> SocialPublishReceipt:
        """Publish one social request and return a sanitized provider receipt."""


class FakeSocialProviderAdapter:
    provider = SOCIAL_PROVIDER_FAKE

    def __init__(self, *, fail: bool = False, failure_code: str = "fake_provider_failure") -> None:
        self.fail = fail
        self.failure_code = failure_code
        self.publish_count = 0

    def credentials_configured(self) -> bool:
        return True

    def publish(self, request: SocialPublishRequest) -> SocialPublishReceipt:
        self.publish_count += 1
        if self.fail:
            raise SocialConnectorError(
                self.failure_code,
                "Fake social provider failure.",
                provider=self.provider,
                mode=request.mode,
                retryable=False,
            )
        completed_at = timezone.now().isoformat()
        return SocialPublishReceipt(
            provider=self.provider,
            platform=_safe_key(request.platform),
            mode=SOCIAL_MODE_PROVIDER_PUBLISH,
            evidence_mode=SOCIAL_EVIDENCE_PROVIDER_PUBLISH,
            status="accepted",
            provider_post_id=_deterministic_id(prefix="fg-social-fake-post", request=request),
            provider_container_id=_deterministic_id(
                prefix="fg-social-fake-container", request=request
            ),
            completed_at=completed_at,
            idempotency_key=request.idempotency_key,
            **_receipt_evidence(request),
            related=_related_payload(request),
        )


class MetaGraphSocialAdapter:
    provider = SOCIAL_PROVIDER_META_GRAPH

    def __init__(
        self,
        *,
        access_token: str | None = None,
        api_base_url: str | None = None,
        api_version: str | None = None,
        timeout_seconds: float | None = None,
        session: Any = None,
    ) -> None:
        self.access_token = (
            access_token
            if access_token is not None
            else getattr(settings, "META_GRAPH_ACCESS_TOKEN", "")
        ).strip()
        self.api_base_url = (
            (
                api_base_url
                if api_base_url is not None
                else getattr(settings, "META_GRAPH_API_BASE_URL", "https://graph.facebook.com")
            )
            .strip()
            .rstrip("/")
        )
        self.api_version = (
            (
                api_version
                if api_version is not None
                else getattr(settings, "META_GRAPH_API_VERSION", "v24.0")
            )
            .strip()
            .strip("/")
        )
        self.timeout_seconds = float(
            timeout_seconds
            if timeout_seconds is not None
            else getattr(settings, "SOCIAL_CONNECTOR_TIMEOUT_SECONDS", 10)
        )
        self.session = session or requests.Session()

    def credentials_configured(self) -> bool:
        return bool(self.access_token)

    def publish(self, request: SocialPublishRequest) -> SocialPublishReceipt:
        if not self.credentials_configured():
            raise SocialConnectorError(
                "social_credentials_missing",
                "Social provider credentials are not configured.",
                provider=self.provider,
                mode=request.mode,
                blocked_before_provider_call=True,
            )
        if _safe_key(request.platform) in {"instagram", "ig"}:
            return self._publish_instagram(request)
        if _safe_key(request.platform) in {"facebook", "fb"}:
            return self._publish_facebook_page(request)
        raise SocialConnectorError(
            "platform_not_supported",
            "Social provider platform is not supported by this adapter.",
            provider=self.provider,
            mode=request.mode,
            blocked_before_provider_call=True,
        )

    def _publish_instagram(self, request: SocialPublishRequest) -> SocialPublishReceipt:
        account_id = request.target_account()
        if not account_id:
            raise SocialConnectorError(
                "target_account_required",
                "Social provider publish requires a target account.",
                provider=self.provider,
                mode=request.mode,
                blocked_before_provider_call=True,
            )
        if not request.media_url:
            raise SocialConnectorError(
                "media_url_required",
                "Social provider publish requires approved hosted media for this platform.",
                provider=self.provider,
                mode=request.mode,
                blocked_before_provider_call=True,
            )
        container_payload = {
            "image_url": request.media_url,
            "caption": request.caption,
        }
        container = self._post(
            f"{account_id}/media",
            json=container_payload,
            idempotency_key=f"{request.idempotency_key}:container"
            if request.idempotency_key
            else "",
            mode=request.mode,
        )
        container_id = str(container.get("id") or "")[:255]
        if not container_id:
            raise SocialConnectorError(
                "invalid_provider_response",
                "Social provider response did not include a container id.",
                provider=self.provider,
                mode=request.mode,
                retryable=True,
            )
        publish = self._post(
            f"{account_id}/media_publish",
            json={"creation_id": container_id},
            idempotency_key=request.idempotency_key,
            mode=request.mode,
        )
        return sanitize_provider_response(
            publish,
            provider=self.provider,
            request=request,
            provider_container_id=container_id,
        )

    def _publish_facebook_page(self, request: SocialPublishRequest) -> SocialPublishReceipt:
        account_id = request.target_account()
        if not account_id:
            raise SocialConnectorError(
                "target_account_required",
                "Social provider publish requires a target account.",
                provider=self.provider,
                mode=request.mode,
                blocked_before_provider_call=True,
            )
        if request.media_url:
            raise SocialConnectorError(
                "unsupported_media_shape",
                "Social provider publish for this slice supports text or link posts only.",
                provider=self.provider,
                mode=request.mode,
                blocked_before_provider_call=True,
            )
        payload: dict[str, Any] = {}
        if request.caption:
            payload["message"] = request.caption
        if request.link_url:
            payload["link"] = request.link_url
        if not payload:
            raise SocialConnectorError(
                "content_required",
                "Social provider publish requires approved text or link content.",
                provider=self.provider,
                mode=request.mode,
                blocked_before_provider_call=True,
            )
        response = self._post(
            f"{account_id}/feed",
            json=payload,
            idempotency_key=request.idempotency_key,
            mode=request.mode,
        )
        return sanitize_provider_response(response, provider=self.provider, request=request)

    def _post(
        self,
        path: str,
        *,
        json: dict[str, Any],
        idempotency_key: str,
        mode: str,
    ) -> dict[str, Any]:
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "User-Agent": "forgegraph-social-connector/1.0",
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key[:256]
        try:
            response = self.session.post(
                urljoin(f"{self.api_base_url}/{self.api_version}/", path),
                json=json,
                headers=headers,
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise SocialConnectorError(
                "provider_request_failed",
                "Social provider request failed.",
                provider=self.provider,
                mode=mode,
                retryable=True,
            ) from exc
        return _provider_json_or_error(response, provider=self.provider, mode=mode)


def get_social_provider_adapter(
    provider: str | None = None,
    *,
    session: Any = None,
) -> SocialProviderAdapter:
    selected = _safe_key(
        provider or getattr(settings, "SOCIAL_CONNECTOR_PROVIDER", "fake") or "fake"
    )
    if selected == SOCIAL_PROVIDER_META_GRAPH:
        return MetaGraphSocialAdapter(session=session)
    if selected == SOCIAL_PROVIDER_FAKE:
        return FakeSocialProviderAdapter()
    if selected == SOCIAL_PROVIDER_MANUAL:
        return FakeSocialProviderAdapter()
    raise SocialConnectorError(
        "social_provider_unsupported",
        "Social provider is not supported.",
        provider=selected,
        blocked_before_provider_call=True,
    )


def dry_run_social_publish(request: SocialPublishRequest) -> SocialPublishReceipt:
    validate_social_request(request, dry_run=True)
    completed_at = timezone.now().isoformat()
    provider = _safe_key(
        request.provider or getattr(settings, "SOCIAL_CONNECTOR_PROVIDER", "fake") or "fake"
    )
    return SocialPublishReceipt(
        provider=provider,
        platform=_safe_key(request.platform),
        mode=SOCIAL_MODE_DRY_RUN,
        evidence_mode=SOCIAL_EVIDENCE_SANDBOX,
        status="accepted",
        provider_post_id=_deterministic_id(prefix="fg-social-dry-run", request=request),
        completed_at=completed_at,
        idempotency_key=request.idempotency_key,
        **_receipt_evidence(request),
        related=_related_payload(request),
    )


def record_manual_publish_evidence(request: SocialPublishRequest) -> SocialPublishReceipt:
    validate_social_request(request, dry_run=True)
    if not bool(getattr(settings, "SOCIAL_CONNECTOR_ALLOW_MANUAL_EVIDENCE", True)):
        raise SocialConnectorError(
            "manual_evidence_disabled",
            "Manual social publish evidence is disabled by environment configuration.",
            provider=request.provider,
            mode=SOCIAL_MODE_MANUAL_PUBLISH_RECORD,
            blocked_before_provider_call=True,
        )
    if not request.operator_confirmed:
        raise SocialConnectorError(
            "operator_confirmation_required",
            "Operator confirmation is required before recording manual social evidence.",
            provider=request.provider,
            mode=SOCIAL_MODE_MANUAL_PUBLISH_RECORD,
            blocked_before_provider_call=True,
        )
    _validate_content_approval(request, mode=SOCIAL_MODE_MANUAL_PUBLISH_RECORD)
    if not str(request.external_post_url or request.external_post_id or "").strip():
        raise SocialConnectorError(
            "manual_evidence_required",
            "Manual social publish evidence requires an external post reference.",
            provider=request.provider,
            mode=SOCIAL_MODE_MANUAL_PUBLISH_RECORD,
            blocked_before_provider_call=True,
        )
    completed_at = timezone.now().isoformat()
    return SocialPublishReceipt(
        provider=SOCIAL_PROVIDER_MANUAL,
        platform=_safe_key(request.platform),
        mode=SOCIAL_MODE_MANUAL_PUBLISH_RECORD,
        evidence_mode=SOCIAL_EVIDENCE_MANUAL_PUBLISH,
        status="recorded",
        completed_at=completed_at,
        idempotency_key=request.idempotency_key,
        **_receipt_evidence(request),
        related=_related_payload(request),
    )


def provider_publish_social(
    request: SocialPublishRequest,
    *,
    approved: bool,
    policy_allows_provider_publish: bool,
    adapter: SocialProviderAdapter | None = None,
) -> SocialPublishReceipt:
    validate_social_request(request, dry_run=False)
    selected_adapter = adapter or get_social_provider_adapter(request.provider)
    validate_real_publish_allowed(
        request,
        approved=approved,
        policy_allows_provider_publish=policy_allows_provider_publish,
        adapter=selected_adapter,
    )
    return selected_adapter.publish(request)


def validate_social_request(request: SocialPublishRequest, *, dry_run: bool) -> None:
    mode = SOCIAL_MODE_DRY_RUN if dry_run else request.mode or SOCIAL_MODE_PROVIDER_PUBLISH
    if not _safe_key(request.platform):
        raise SocialConnectorError(
            "platform_required",
            "Social publish requires a platform.",
            provider=request.provider,
            mode=mode,
            blocked_before_provider_call=True,
        )
    max_assets = int(getattr(settings, "SOCIAL_CONNECTOR_MAX_ASSETS_PER_POST", 1))
    if len(_normalized_asset_ids(request.asset_ids)) > max_assets:
        raise SocialConnectorError(
            "asset_cap_exceeded",
            "Social publish asset count exceeds the configured limit.",
            provider=request.provider,
            mode=mode,
            blocked_before_provider_call=True,
        )
    max_caption_chars = int(getattr(settings, "SOCIAL_CONNECTOR_MAX_CAPTION_CHARS", 2200))
    if len(str(request.caption or "")) > max_caption_chars:
        raise SocialConnectorError(
            "caption_too_long",
            "Social publish caption exceeds the configured limit.",
            provider=request.provider,
            mode=mode,
            blocked_before_provider_call=True,
        )
    if not dry_run and not request.target_account():
        raise SocialConnectorError(
            "target_account_required",
            "Social provider publish requires a target account.",
            provider=request.provider,
            mode=mode,
            blocked_before_provider_call=True,
        )


def validate_real_publish_allowed(
    request: SocialPublishRequest,
    *,
    approved: bool,
    policy_allows_provider_publish: bool,
    adapter: SocialProviderAdapter | None = None,
) -> None:
    if not approved:
        raise SocialConnectorError(
            "approval_required",
            "Approved human gate is required before provider social publish.",
            provider=request.provider,
            mode=SOCIAL_MODE_PROVIDER_PUBLISH,
            blocked_before_provider_call=True,
        )
    if not policy_allows_provider_publish:
        raise SocialConnectorError(
            "provider_publish_not_allowed",
            "Policy does not allow provider social publish.",
            provider=request.provider,
            mode=SOCIAL_MODE_PROVIDER_PUBLISH,
            blocked_before_provider_call=True,
        )
    if not bool(getattr(settings, "SOCIAL_CONNECTOR_ALLOW_PROVIDER_PUBLISH", False)):
        raise SocialConnectorError(
            "provider_publish_disabled",
            "Provider social publish is disabled by environment configuration.",
            provider=request.provider,
            mode=SOCIAL_MODE_PROVIDER_PUBLISH,
            blocked_before_provider_call=True,
        )
    selected_adapter = adapter or get_social_provider_adapter(request.provider)
    if not selected_adapter.credentials_configured():
        raise SocialConnectorError(
            "social_credentials_missing",
            "Social provider credentials are not configured.",
            provider=request.provider,
            mode=SOCIAL_MODE_PROVIDER_PUBLISH,
            blocked_before_provider_call=True,
        )
    validate_platform_account_allowlist(request, provider=request.provider)
    _validate_content_approval(request, mode=SOCIAL_MODE_PROVIDER_PUBLISH)
    if request.requires_compliance_gate and not request.compliance_gate_passed:
        raise SocialConnectorError(
            "compliance_gate_required",
            "Social publish requires a passed compliance gate.",
            provider=request.provider,
            mode=SOCIAL_MODE_PROVIDER_PUBLISH,
            blocked_before_provider_call=True,
        )
    if request.requires_originality_check and not request.originality_check_passed:
        raise SocialConnectorError(
            "originality_check_required",
            "Social publish requires a passed originality check.",
            provider=request.provider,
            mode=SOCIAL_MODE_PROVIDER_PUBLISH,
            blocked_before_provider_call=True,
        )


def validate_platform_account_allowlist(
    request: SocialPublishRequest, *, provider: str = ""
) -> None:
    account = _normalized_account_id(request.target_account())
    if not account:
        raise SocialConnectorError(
            "target_account_required",
            "Social publish requires a target account.",
            provider=provider,
            mode=SOCIAL_MODE_PROVIDER_PUBLISH,
            blocked_before_provider_call=True,
        )
    allowlist = _allowlist_values()
    if not allowlist:
        raise SocialConnectorError(
            "account_allowlist_required",
            "Social account allowlist is not configured.",
            provider=provider,
            mode=SOCIAL_MODE_PROVIDER_PUBLISH,
            blocked_before_provider_call=True,
        )
    if not _account_allowed(account, allowlist):
        raise SocialConnectorError(
            "account_not_allowlisted",
            "Social target account is not allowlisted.",
            provider=provider,
            mode=SOCIAL_MODE_PROVIDER_PUBLISH,
            blocked_before_provider_call=True,
        )


def validate_social_assets(request: SocialPublishRequest) -> None:
    _validate_content_approval(request, mode=request.mode)


def sanitize_provider_response(
    response_json: dict[str, Any],
    *,
    provider: str,
    request: SocialPublishRequest,
    provider_container_id: str = "",
) -> SocialPublishReceipt:
    completed_at = timezone.now().isoformat()
    return SocialPublishReceipt(
        provider=_safe_key(provider),
        platform=_safe_key(request.platform),
        mode=SOCIAL_MODE_PROVIDER_PUBLISH,
        evidence_mode=SOCIAL_EVIDENCE_PROVIDER_PUBLISH,
        status="accepted",
        provider_post_id=str(response_json.get("id") or response_json.get("post_id") or "")[:255],
        provider_container_id=str(provider_container_id or response_json.get("container_id") or "")[
            :255
        ],
        completed_at=completed_at,
        idempotency_key=request.idempotency_key,
        **_receipt_evidence(request),
        related=_related_payload(request),
    )


def sanitize_provider_error(
    exc: Exception,
    *,
    provider: str = "",
    mode: str = "",
) -> dict[str, Any]:
    if isinstance(exc, SocialConnectorError):
        return exc.as_dict()
    return SocialConnectorError(
        "provider_request_failed",
        str(exc.__class__.__name__),
        provider=provider,
        mode=mode,
        retryable=True,
    ).as_dict()


def _provider_json_or_error(response: Any, *, provider: str, mode: str) -> dict[str, Any]:
    content = getattr(response, "content", b"") or b""
    if len(content) > _MAX_PROVIDER_RESPONSE_BYTES:
        raise SocialConnectorError(
            "provider_response_too_large",
            "Social provider response exceeded the safe size limit.",
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
        raise SocialConnectorError(
            code,
            message,
            provider=provider,
            mode=mode,
            retryable=status_code == 429 or status_code >= 500,
        )
    if not isinstance(payload, dict):
        raise SocialConnectorError(
            "invalid_provider_response",
            "Social provider response was not a JSON object.",
            provider=provider,
            mode=mode,
            retryable=True,
        )
    return payload


def _provider_error_details(payload: Any, *, response: Any, status_code: int) -> tuple[str, str]:
    code = "provider_http_error"
    message = f"Social provider request failed with HTTP {status_code}."
    if isinstance(payload, dict):
        raw_error = payload.get("error")
        error = raw_error if isinstance(raw_error, dict) else payload
        code = str(error.get("type") or error.get("code") or code)
        message = str(error.get("message") or message)
    elif getattr(response, "reason", ""):
        message = str(response.reason)
    return _safe_key(code), _safe_error_message(message)


def _validate_content_approval(request: SocialPublishRequest, *, mode: str) -> None:
    if not _normalized_asset_ids(request.asset_ids):
        raise SocialConnectorError(
            "asset_required",
            "Social publish requires an approved asset.",
            provider=request.provider,
            mode=mode,
            blocked_before_provider_call=True,
        )
    if not request.asset_approved:
        raise SocialConnectorError(
            "asset_approval_required",
            "Social publish requires approved asset content.",
            provider=request.provider,
            mode=mode,
            blocked_before_provider_call=True,
        )
    if not str(request.caption or "").strip():
        raise SocialConnectorError(
            "caption_required",
            "Social publish requires approved caption content.",
            provider=request.provider,
            mode=mode,
            blocked_before_provider_call=True,
        )
    if not request.caption_approved:
        raise SocialConnectorError(
            "caption_approval_required",
            "Social publish requires approved caption content.",
            provider=request.provider,
            mode=mode,
            blocked_before_provider_call=True,
        )


def _receipt_evidence(request: SocialPublishRequest) -> dict[str, Any]:
    account = _normalized_account_id(request.account_id)
    page = _normalized_account_id(request.page_id)
    profile = _normalized_account_id(request.profile_id)
    target = _normalized_account_id(request.target_account())
    return {
        "asset_count": len(_normalized_asset_ids(request.asset_ids)),
        "media_asset_ids": _normalized_asset_ids(request.asset_ids),
        "caption_hash": _hash_value(request.caption),
        "account_id_hash": _hash_value(account or target),
        "page_id_hash": _hash_value(page),
        "profile_id_hash": _hash_value(profile),
        "external_post_url_hash": _hash_value(request.external_post_url),
        "external_post_id_hash": _hash_value(request.external_post_id),
    }


def _related_payload(request: SocialPublishRequest) -> dict[str, Any]:
    return {
        "whiteboard_id": request.whiteboard_id or "",
        "deployment_channel_id": request.deployment_channel_id or "",
        "publication_draft_id": request.publication_draft_id or "",
        "approval_id": request.approval_id or "",
        "metadata": _safe_metadata(request.metadata),
    }


def _safe_metadata(raw: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in raw.items():
        safe_key = _safe_key(str(key))
        if any(
            token in safe_key
            for token in ("token", "secret", "url", "caption", "body", "media", "payload")
        ):
            continue
        if isinstance(value, str):
            result[safe_key] = redact_text(value)[:300]
        elif isinstance(value, bool | int | float) or value is None:
            result[safe_key] = value
        elif isinstance(value, list):
            result[safe_key] = [redact_text(str(item))[:120] for item in value[:20]]
        elif isinstance(value, dict):
            result[safe_key] = _safe_metadata(value)
    return sanitize_outbox_payload(result)


def _allowlist_values() -> set[str]:
    raw_values: list[Any] = []
    for setting_name in (
        "SOCIAL_CONNECTOR_ACCOUNT_ALLOWLIST",
        "META_GRAPH_PAGE_ID_ALLOWLIST",
        "META_GRAPH_IG_USER_ID_ALLOWLIST",
    ):
        raw = getattr(settings, setting_name, [])
        if isinstance(raw, str):
            raw_values.extend(raw.split(","))
        else:
            raw_values.extend(list(raw or []))
    result: set[str] = set()
    for value in raw_values:
        text = str(value or "").strip().lower()
        if not text:
            continue
        if text.startswith("sha256:"):
            result.add(text)
        else:
            result.add(_normalized_account_id(text))
    return {value for value in result if value}


def _account_allowed(account: str, allowlist: set[str]) -> bool:
    if account in allowlist:
        return True
    return _hash_value(account) in allowlist


def _normalized_asset_ids(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = str(raw or "").strip()
        if not value or value in seen:
            continue
        result.append(value[:128])
        seen.add(value)
    return result


def _normalized_account_id(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").strip().lower())[:200]


def _hash_value(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return f"sha256:{hashlib.sha256(text.lower().encode('utf-8')).hexdigest()}"


def _deterministic_id(*, prefix: str, request: SocialPublishRequest) -> str:
    digest = hashlib.sha256(
        json.dumps(
            {
                "idempotency_key": request.idempotency_key,
                "platform": _safe_key(request.platform),
                "asset_ids": _normalized_asset_ids(request.asset_ids),
                "caption_hash": _hash_value(request.caption),
                "account_hash": _hash_value(request.target_account()),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:24]
    return f"{prefix}-{digest}"


def _safe_error_message(value: str) -> str:
    redacted = redact_text(str(value or ""))
    redacted = _URL_RE.sub("[redacted-url]", redacted)
    redacted = _TOKEN_RE.sub("[redacted-token]", redacted)
    return redacted[:_MAX_ERROR_MESSAGE_LENGTH] or "Social connector failed."


def _safe_key(value: str) -> str:
    return re.sub(r"[^a-z0-9_.-]+", "_", str(value or "").strip().lower())[:80]
