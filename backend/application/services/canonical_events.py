from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from application.services.cloudevents import unwrap_engine_event as unwrap_legacy_engine_event

CANONICAL_EVENT_SCHEMA_VERSION = 2

CANONICAL_TO_ENGINE_EVENT_TYPE = {
    "run.started": "run_started",
    "run.completed": "run_completed",
    "run.failed": "run_failed",
    "run.paused": "run_paused",
    "run.resumed": "run_resumed",
    "run.canceled": "run_canceled",
    "run.schema_validation": "run.schema_validation",
    "node.started": "node_started",
    "node.completed": "node_completed",
    "node.failed": "node_failed",
    "node.skipped": "node_skipped",
    "node.retrying": "node_retrying",
    "node.stream_chunk": "node_stream_chunk",
    "memory.write_requested": "memory_write_requested",
    "memory.fact_extracted": "memory_fact_extracted",
    "summary.created": "summary_created",
}


class CanonicalEventValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedEngineEvent:
    event: dict[str, Any]
    canonical: bool


def parse_engine_event_payload(payload: Any, *, allow_legacy: bool = False) -> ParsedEngineEvent:
    if isinstance(payload, dict) and int(payload.get("schema_version") or 0) == 2:
        return ParsedEngineEvent(_canonical_to_engine_event(payload), True)
    if allow_legacy:
        return ParsedEngineEvent(unwrap_legacy_engine_event(payload), False)
    raise CanonicalEventValidationError("Engine callback must use canonical event envelope v2.")


def _canonical_to_engine_event(envelope: dict[str, Any]) -> dict[str, Any]:
    _validate_required(envelope)
    _validate_checksum(envelope)

    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        raise CanonicalEventValidationError("payload must be an object.")

    source = str(envelope.get("source") or "").strip()
    if source != "engine":
        raise CanonicalEventValidationError("source must be engine.")

    tenant_id = str(envelope.get("tenant_id") or "").strip()
    org_id = str(envelope.get("org_id") or "").strip()
    if tenant_id != org_id:
        raise CanonicalEventValidationError("org_id must match tenant_id for engine events.")

    event_type = str(envelope.get("type") or "").strip()
    mapped_type = CANONICAL_TO_ENGINE_EVENT_TYPE.get(event_type)
    if not mapped_type:
        raise CanonicalEventValidationError(
            f"Unsupported canonical engine event type: {event_type}."
        )

    occurred_at = _parse_occurred_at(envelope.get("occurred_at"))
    flattened = dict(payload)
    flattened.update(
        {
            "event_id": str(envelope["event_id"]).strip(),
            "idempotency_key": str(envelope["idempotency_key"]).strip(),
            "tenant_id": tenant_id,
            "org_id": org_id,
            "run_id": str(envelope["run_id"]).strip(),
            "agent_id": envelope.get("agent_id"),
            "task_id": envelope.get("task_id"),
            "source": source,
            "type": mapped_type,
            "canonical_type": event_type,
            "sequence": int(envelope["sequence"]),
            "causation_id": envelope.get("causation_id"),
            "correlation_id": str(envelope["correlation_id"]).strip(),
            "occurred_at": occurred_at.isoformat(),
            "timestamp": int(occurred_at.timestamp() * 1000),
            "schema_version": CANONICAL_EVENT_SCHEMA_VERSION,
            "checksum": str(envelope["checksum"]).strip(),
        }
    )
    if not flattened.get("node_id") and envelope.get("task_id"):
        flattened["node_id"] = str(envelope["task_id"]).strip()
    if "traceparent" not in flattened and payload.get("traceparent"):
        flattened["traceparent"] = str(payload["traceparent"])
    if "tracestate" not in flattened and payload.get("tracestate"):
        flattened["tracestate"] = str(payload["tracestate"])
    return flattened


def _validate_required(envelope: dict[str, Any]) -> None:
    required = {
        "event_id",
        "idempotency_key",
        "tenant_id",
        "org_id",
        "run_id",
        "source",
        "type",
        "sequence",
        "correlation_id",
        "occurred_at",
        "schema_version",
        "payload",
        "checksum",
    }
    missing = sorted(key for key in required if envelope.get(key) in (None, ""))
    if missing:
        raise CanonicalEventValidationError(
            f"Canonical engine event missing required field(s): {', '.join(missing)}."
        )
    if int(envelope.get("schema_version") or 0) != CANONICAL_EVENT_SCHEMA_VERSION:
        raise CanonicalEventValidationError("schema_version must be 2.")
    try:
        sequence = int(envelope.get("sequence"))
    except (TypeError, ValueError) as exc:
        raise CanonicalEventValidationError("sequence must be an integer.") from exc
    if sequence < 1:
        raise CanonicalEventValidationError("sequence must be positive.")


def _validate_checksum(envelope: dict[str, Any]) -> None:
    expected = str(envelope.get("checksum") or "").strip().lower()
    actual = canonical_event_checksum(envelope)
    if expected != actual:
        raise CanonicalEventValidationError("checksum mismatch.")


def canonical_event_checksum(envelope: dict[str, Any]) -> str:
    unsigned = {key: value for key, value in envelope.items() if key != "checksum"}
    body = json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _parse_occurred_at(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise CanonicalEventValidationError("occurred_at must be an ISO timestamp.")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise CanonicalEventValidationError("occurred_at must be an ISO timestamp.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
