from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any


class JsonLogFormatter(logging.Formatter):
    """JSON formatter with a stable ForgeGraph observability schema."""

    default_service = "backend"
    default_id_fields = ("trace_id", "run_id", "agent_id", "task_id")
    optional_fields = (
        "status",
        "duration_ms",
        "cost",
        "error_message",
        "error_detail",
        "retry_count",
        "decision_id",
        "event_id",
        "intent_id",
        "intent_type",
        "node_id",
        "node_type",
        "attempt",
        "attempt_id",
        "resume_attempt_id",
        "intent_attempt_id",
        "current_attempt_id",
        "tenant_id",
        "category",
        "engine_instance_id",
        "assigned_engine_instance_id",
        "callback_engine_instance_id",
        "recovery_policy",
        "checkpoint_available",
        "checkpoint_step_index",
        "checkpoint_updated_at",
        "user_id",
        "organization_id",
        "connection_id",
        "event_level",
    )

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "service": getattr(record, "service", self.default_service),
            "level": record.levelname.lower(),
            "event_type": getattr(record, "event_type", record.getMessage()),
        }

        for field in self.default_id_fields:
            payload[field] = getattr(record, field, None)

        for field in self.optional_fields:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = self._serialize(value)

        message = record.getMessage()
        if message and message != payload["event_type"]:
            payload["message"] = message

        if record.exc_info:
            payload["stack"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=self._json_default)

    def _json_default(self, value: Any) -> Any:
        return self._serialize(value)

    def _serialize(self, value: Any) -> Any:
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=UTC)
            return value.isoformat()
        if isinstance(value, Exception):
            return str(value)
        return value


def log_event(
    logger: logging.Logger,
    level: int,
    event_type: str,
    /,
    *,
    message: str | None = None,
    **fields: Any,
) -> None:
    extra: dict[str, Any] = {
        "service": "backend",
        "event_type": event_type,
        "trace_id": fields.pop("trace_id", None),
        "run_id": fields.pop("run_id", None),
        "agent_id": fields.pop("agent_id", None),
        "task_id": fields.pop("task_id", None),
    }
    extra.update(fields)
    logger.log(level, message or event_type, extra=extra)
