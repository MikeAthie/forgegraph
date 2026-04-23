from __future__ import annotations

import json
from io import StringIO

from infrastructure.orm.management.commands import inspect_runtime_intent_dlq
from infrastructure.orm.management.commands.inspect_runtime_intent_dlq import Command


class FakeDeadLetterRedis:
    def __init__(self, records: list[tuple[str, dict[str, object]]]) -> None:
        self.records = records

    def xrevrange(
        self,
        stream: str,
        *,
        max: str = "+",
        min: str = "-",
        count: int | None = None,
    ) -> list[tuple[str, dict[str, object]]]:
        del stream, max, min
        return self.records[:count]


def test_runtime_intent_dlq_inspection_exposes_operational_tool_context(monkeypatch) -> None:
    redis = FakeDeadLetterRedis(
        [
            (
                "1700000000000-0",
                {
                    "run_id": "run-side-effect-001",
                    "intent_id": "intent-node-completed-001",
                    "attempt_id": "attempt-engine-001",
                    "intent_type": "node_completed",
                    "delivery_count": "6",
                    "reason": "max_delivery_attempts_exceeded",
                    "error_class": "PoisonToolResult",
                    "stream_message_id": "1699999999999-0",
                    "timestamp": "2026-04-22T19:30:00Z",
                },
            )
        ]
    )
    monkeypatch.setattr(
        inspect_runtime_intent_dlq,
        "build_runtime_intent_redis_client",
        lambda: redis,
    )

    stdout = StringIO()
    command = Command(stdout=stdout)
    command.handle(count=20, run_id="")

    record = json.loads(stdout.getvalue().strip())

    assert record == {
        "attempt_id": "attempt-engine-001",
        "delivery_count": 6,
        "dlq_message_id": "1700000000000-0",
        "error_class": "PoisonToolResult",
        "intent_id": "intent-node-completed-001",
        "intent_type": "node_completed",
        "reason": "max_delivery_attempts_exceeded",
        "run_id": "run-side-effect-001",
        "stream_message_id": "1699999999999-0",
        "timestamp": "2026-04-22T19:30:00Z",
    }
