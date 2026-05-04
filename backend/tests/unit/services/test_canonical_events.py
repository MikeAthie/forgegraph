from __future__ import annotations

from datetime import UTC, datetime

import pytest

from application.services.canonical_events import (
    CanonicalEventValidationError,
    canonical_event_checksum,
    parse_engine_event_payload,
)


def _envelope(**overrides):
    payload = {
        "category": "state",
        "node_id": "node-1",
        "node_type": "prompt",
        "attempt": 1,
        "output": {"ok": True},
    }
    envelope = {
        "event_id": "evt-1",
        "idempotency_key": "tenant/run/engine/1/hash",
        "tenant_id": "11111111-1111-1111-1111-111111111111",
        "org_id": "11111111-1111-1111-1111-111111111111",
        "run_id": "22222222-2222-2222-2222-222222222222",
        "agent_id": None,
        "task_id": "node-1",
        "source": "engine",
        "type": "node.completed",
        "sequence": 1,
        "causation_id": None,
        "correlation_id": "22222222-2222-2222-2222-222222222222",
        "occurred_at": datetime(2026, 5, 3, 12, 0, tzinfo=UTC).isoformat(),
        "schema_version": 2,
        "payload": payload,
    }
    envelope.update(overrides)
    envelope["checksum"] = canonical_event_checksum(envelope)
    return envelope


def test_parse_canonical_event_maps_to_engine_event_shape():
    parsed = parse_engine_event_payload(_envelope())

    assert parsed.canonical is True
    assert parsed.event["type"] == "node_completed"
    assert parsed.event["canonical_type"] == "node.completed"
    assert parsed.event["event_id"] == "evt-1"
    assert parsed.event["idempotency_key"] == "tenant/run/engine/1/hash"
    assert parsed.event["tenant_id"] == "11111111-1111-1111-1111-111111111111"
    assert parsed.event["org_id"] == "11111111-1111-1111-1111-111111111111"
    assert parsed.event["run_id"] == "22222222-2222-2222-2222-222222222222"
    assert parsed.event["node_id"] == "node-1"
    assert parsed.event["timestamp"] == 1777809600000


def test_parse_canonical_event_rejects_checksum_mismatch():
    envelope = _envelope()
    envelope["payload"]["output"] = {"ok": False}

    with pytest.raises(CanonicalEventValidationError, match="checksum mismatch"):
        parse_engine_event_payload(envelope)


def test_parse_engine_event_rejects_legacy_payload_by_default():
    with pytest.raises(CanonicalEventValidationError, match="canonical event envelope v2"):
        parse_engine_event_payload(
            {
                "event_id": "legacy-1",
                "type": "run_started",
                "run_id": "22222222-2222-2222-2222-222222222222",
                "tenant_id": "11111111-1111-1111-1111-111111111111",
            }
        )
