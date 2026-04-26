from application.services import runtime_transport_observability as observability
from application.services.runtime_write_intents import (
    RUNTIME_INTENT_CONSUMER_GROUP,
    RUNTIME_INTENT_DEAD_LETTER_STREAM,
    RUNTIME_INTENT_STREAM,
)


class FakeRedis:
    def xlen(self, stream: str) -> int:
        if stream == RUNTIME_INTENT_STREAM:
            return 42
        if stream == RUNTIME_INTENT_DEAD_LETTER_STREAM:
            return 7
        return 0

    def xinfo_groups(self, stream: str):
        assert stream == RUNTIME_INTENT_STREAM
        return [
            {
                "name": RUNTIME_INTENT_CONSUMER_GROUP,
                "pending": 2,
                "lag": 3,
            }
        ]

    def xinfo_consumers(self, stream: str, group: str):
        assert stream == RUNTIME_INTENT_STREAM
        assert group == RUNTIME_INTENT_CONSUMER_GROUP
        return [{"name": "consumer-a", "idle": 1500}]

    def xpending_range(self, stream: str, group: str, start: str, end: str, count: int):
        assert stream == RUNTIME_INTENT_STREAM
        assert group == RUNTIME_INTENT_CONSUMER_GROUP
        return [{"message_id": "1-0", "idle": 900}]


def test_runtime_transport_observability_reads_live_redis_metrics(monkeypatch):
    monkeypatch.setattr(
        observability,
        "build_runtime_intent_redis_client",
        lambda: FakeRedis(),
    )

    snapshot = observability.get_runtime_transport_observability_snapshot()

    assert snapshot.source == "redis"
    assert snapshot.stream_length == 42
    assert snapshot.pending == 2
    assert snapshot.lag == 3
    assert snapshot.backlog == 5
    assert snapshot.consumer_idle_ms == 1500
    assert snapshot.oldest_pending_idle_ms == 900
    assert snapshot.dead_letter_count == 7
