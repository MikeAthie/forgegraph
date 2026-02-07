from __future__ import annotations

from application.services.redaction import REDACTED_VALUE, redact_payload, redact_text


def test_redact_payload_redacts_sensitive_keys() -> None:
    payload = {
        "api_key": "secret-value",
        "nested": {"Authorization": "Bearer abcdef123456"},
        "safe": "hello",
    }

    redacted = redact_payload(payload)

    assert redacted["api_key"] == REDACTED_VALUE
    assert redacted["nested"]["Authorization"] == REDACTED_VALUE
    assert redacted["safe"] == "hello"


def test_redact_text_redacts_query_tokens_and_bearer() -> None:
    text = "https://example.com?token=abc123&safe=1 Authorization: Bearer sk-verysecretvalue"
    redacted = redact_text(text)
    assert "token=***REDACTED***" in redacted
    assert "Bearer ***REDACTED***" in redacted
