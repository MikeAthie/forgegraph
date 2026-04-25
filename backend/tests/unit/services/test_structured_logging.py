from __future__ import annotations

import json
import logging
from io import StringIO

from application.services.structured_logging import JsonLogFormatter, log_event


def _build_logger(name: str) -> tuple[logging.Logger, StringIO]:
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonLogFormatter())

    logger = logging.getLogger(name)
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger, stream


def test_log_event_serializes_attempt_correlation_fields():
    logger, stream = _build_logger("test.structured_logging.attempts")

    log_event(
        logger,
        logging.INFO,
        "runs_resume_dispatched",
        run_id="run-123",
        node_id="gate",
        resume_attempt_id="attempt-b",
        attempt_id="attempt-b",
    )

    payload = json.loads(stream.getvalue())
    assert payload["event_type"] == "runs_resume_dispatched"
    assert payload["run_id"] == "run-123"
    assert payload["node_id"] == "gate"
    assert payload["resume_attempt_id"] == "attempt-b"
    assert payload["attempt_id"] == "attempt-b"


def test_json_formatter_keeps_stale_intent_metadata():
    logger, stream = _build_logger("test.structured_logging.stale_intent")

    logger.warning(
        "intent_ignored_due_to_stale_attempt",
        extra={
            "run_id": "run-123",
            "intent_id": "intent-1",
            "intent_type": "pause_run",
            "intent_attempt_id": "attempt-a",
            "active_attempt_id": "attempt-b",
            "current_attempt_id": "attempt-b",
        },
    )

    payload = json.loads(stream.getvalue())
    assert payload["event_type"] == "intent_ignored_due_to_stale_attempt"
    assert payload["run_id"] == "run-123"
    assert payload["intent_id"] == "intent-1"
    assert payload["intent_type"] == "pause_run"
    assert payload["intent_attempt_id"] == "attempt-a"
    assert payload["active_attempt_id"] == "attempt-b"
    assert payload["current_attempt_id"] == "attempt-b"


def test_log_event_serializes_node_payload_fields():
    logger, stream = _build_logger("test.structured_logging.node_payload")

    log_event(
        logger,
        logging.INFO,
        "node_output",
        run_id="run-456",
        node_id="analytics_agent",
        payload={"iteration": 2, "ctr": 0.09},
        input_json={"goal": "launch"},
        output_json={"analytics": {"iteration": 2}},
    )

    payload = json.loads(stream.getvalue())
    assert payload["event_type"] == "node_output"
    assert payload["run_id"] == "run-456"
    assert payload["node_id"] == "analytics_agent"
    assert payload["payload"] == {"iteration": 2, "ctr": 0.09}
    assert payload["input_json"] == {"goal": "launch"}
    assert payload["output_json"] == {"analytics": {"iteration": 2}}
