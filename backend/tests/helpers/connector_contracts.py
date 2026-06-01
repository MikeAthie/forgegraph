from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

from infrastructure.orm.models import CompanySignal, Graph, TaskRoutingRecord, ToolExecution

FORBIDDEN_CONNECTOR_PAYLOAD_FRAGMENTS = (
    "secret-api-key",
    "resend-secret-token",
    "meta-secret-token",
    "session-secret",
    "qr-secret",
    "Bearer ",
    "Authorization",
    "access_token",
    "app_secret",
    "raw_provider_response",
    "raw_provider_config",
    "private_config_ref",
    "pack_manifest",
    "raw_prompt",
    "debug_trace",
    "evidence_bundle",
    "owner@example.com",
    "allowed@example.com",
    "+15550101234",
    "5550101234",
    "<p>Private",
    "Private caption",
    "Private message body",
    "https://cdn.example/private",
    "https://social.example/posts/private",
)

SAFE_RECEIPT_KEYS = {
    "accepted_recipients_count",
    "account_id_hash",
    "allowlist_matched",
    "asset_count",
    "asset_ids",
    "caption_hash",
    "completed_at",
    "evidence_mode",
    "external_post_id_hash",
    "external_post_url_hash",
    "idempotency_key",
    "media_asset_ids",
    "message_id",
    "mode",
    "page_id_hash",
    "phone_hash",
    "platform",
    "profile_id_hash",
    "provider",
    "provider_container_id",
    "provider_message_id",
    "provider_post_id",
    "recipient_count",
    "recipient_domains",
    "recipient_hashes",
    "rejected_recipients_count",
    "related",
    "sanitized",
    "sent_at",
    "session_required",
    "session_status",
    "status",
}


def assert_success_receipt_contract(
    receipt: Mapping[str, Any],
    *,
    expected_evidence_mode: str,
    allowed_statuses: Iterable[str] = ("accepted", "dry_run", "recorded"),
) -> None:
    assert receipt["provider"]
    assert receipt["mode"]
    assert receipt["evidence_mode"] == expected_evidence_mode
    assert receipt["status"] in set(allowed_statuses)
    assert receipt["sanitized"] is True
    assert_no_forbidden_connector_material(receipt)


def assert_failure_receipt_contract(
    receipt: Mapping[str, Any],
    *,
    expected_statuses: Iterable[str] = ("failed", "blocked"),
    max_message_length: int = 300,
) -> None:
    assert receipt["provider"]
    assert receipt["mode"]
    assert receipt["status"] in set(expected_statuses)
    assert receipt["sanitized"] is True
    assert receipt["error_code"]
    assert len(str(receipt["error_message"])) <= max_message_length
    assert_no_forbidden_connector_material(receipt)


def assert_tool_execution_receipt_sanitized(
    execution: ToolExecution,
    *,
    extra_forbidden: Iterable[str] = (),
) -> None:
    assert_no_forbidden_connector_material(
        {
            "result_json": execution.result_json,
            "error_json": execution.error_json,
        },
        extra_forbidden=extra_forbidden,
    )
    if execution.result_json:
        assert execution.result_json.get("sanitized") is True
    if execution.error_json:
        assert execution.error_json.get("sanitized") is True


def assert_no_forbidden_connector_material(
    payload: Any,
    *,
    extra_forbidden: Iterable[str] = (),
) -> None:
    rendered = json.dumps(payload, sort_keys=True, default=str)
    for fragment in (*FORBIDDEN_CONNECTOR_PAYLOAD_FRAGMENTS, *tuple(extra_forbidden)):
        assert fragment not in rendered, (
            f"Forbidden connector payload fragment persisted: {fragment!r}"
        )


def assert_pii_minimized_receipt(receipt: Mapping[str, Any]) -> None:
    unsafe_keys = {
        "to",
        "cc",
        "bcc",
        "recipients",
        "recipient_emails",
        "phone_numbers",
        "caption",
        "html",
        "text",
        "media_url",
        "external_post_url",
        "external_post_id",
        "provider_request",
        "provider_response",
        "auth_header",
        "access_token",
    }
    assert unsafe_keys.isdisjoint(set(receipt.keys()))
    assert set(receipt.keys()).issubset(SAFE_RECEIPT_KEYS | {"metadata"})
    assert_no_forbidden_connector_material(receipt)


def assert_tool_execution_company_scope(
    execution: ToolExecution,
    *,
    company: Graph,
) -> None:
    assert execution.run.graph_version.graph_id == company.id
    assert execution.run.organization_id == company.organization_id


def assert_blocked_before_provider_call_routed(
    *,
    company: Graph,
    reason_code: str,
) -> None:
    assert CompanySignal.objects.filter(
        company=company, metadata_json__reason_code=reason_code
    ).exists()
    assert TaskRoutingRecord.objects.filter(
        company=company,
        metadata_json__blocked_reason_code=reason_code,
    ).exists()
