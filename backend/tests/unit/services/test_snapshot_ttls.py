from __future__ import annotations

from typing import cast
from uuid import uuid4

from django.utils import timezone
from redis import Redis

from application.services.run_snapshots import (
    RUN_SNAPSHOT_DEFAULT_TTL_SECONDS,
    RunSnapshot,
    run_snapshot_ttl_seconds,
    set_snapshot,
)
from application.services.work_whiteboards import (
    WHITEBOARD_SNAPSHOT_DEFAULT_TTL_SECONDS,
    whiteboard_snapshot_ttl_seconds,
)


class _RecordingRedis:
    def __init__(self) -> None:
        self.setex_calls: list[tuple[str, int, str]] = []

    def setex(self, key: str, ttl_seconds: int, value: str) -> bool:
        self.setex_calls.append((key, ttl_seconds, value))
        return True


def test_run_snapshot_ttl_rejects_unbounded_configuration(monkeypatch):
    monkeypatch.setenv("FORGEGRAPH_RUN_SNAPSHOT_TTL_SECONDS", "0")

    assert run_snapshot_ttl_seconds() == RUN_SNAPSHOT_DEFAULT_TTL_SECONDS


def test_set_snapshot_writes_with_explicit_ttl(monkeypatch):
    monkeypatch.setenv("FORGEGRAPH_RUN_SNAPSHOT_TTL_SECONDS", "42")
    redis_client = _RecordingRedis()
    snapshot = RunSnapshot(
        run_id=uuid4(),
        last_completed_node="approved",
        next_node="publish",
        attempt_id="attempt-1",
        updated_at=timezone.now(),
    )

    set_snapshot(snapshot, redis_client=cast(Redis, redis_client))

    assert len(redis_client.setex_calls) == 1
    assert redis_client.setex_calls[0][1] == 42


def test_whiteboard_snapshot_ttl_rejects_unbounded_configuration(monkeypatch):
    monkeypatch.setenv("WHITEBOARD_SNAPSHOT_TTL_SECONDS", "0")

    assert whiteboard_snapshot_ttl_seconds() == WHITEBOARD_SNAPSHOT_DEFAULT_TTL_SECONDS


def test_whiteboard_snapshot_ttl_uses_explicit_positive_configuration(monkeypatch):
    monkeypatch.setenv("WHITEBOARD_SNAPSHOT_TTL_SECONDS", "73")

    assert whiteboard_snapshot_ttl_seconds() == 73
