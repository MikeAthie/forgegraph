from __future__ import annotations

import time

from infrastructure.security import s2s


def test_verify_request_once_retries_transient_replay_cache_failure(settings, monkeypatch) -> None:
    settings.ENGINE_CALLBACK_SECRET = "test-secret"
    timestamp_ms = str(int(time.time() * 1000))
    body = b'{"event":"ok"}'
    signature = s2s.build_signature("test-secret", timestamp_ms, body)
    attempts = {"count": 0}

    def flaky_add(key: str, value: str, timeout: int) -> bool:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("temporary redis connection reset")
        assert key.startswith("forgegraph:s2s-replay:")
        assert value == "1"
        assert timeout > 0
        return True

    monkeypatch.setattr("infrastructure.security.s2s.cache.add", flaky_add)
    monkeypatch.setattr("infrastructure.security.s2s.time.sleep", lambda _seconds: None)

    ok, reason = s2s.verify_request_once(
        timestamp_ms=timestamp_ms,
        signature=signature,
        body=body,
        method="GET",
        path="/api/engine/runtime-intents/00000000-0000-0000-0000-000000000000",
    )

    assert ok is True
    assert reason == "ok"
    assert attempts["count"] == 2


def test_verify_request_once_fails_closed_when_replay_cache_stays_unavailable(
    settings, monkeypatch
) -> None:
    settings.ENGINE_CALLBACK_SECRET = "test-secret"
    timestamp_ms = str(int(time.time() * 1000))
    body = b'{"event":"ok"}'
    signature = s2s.build_signature("test-secret", timestamp_ms, body)

    def unavailable_add(key: str, value: str, timeout: int) -> bool:
        raise RuntimeError("redis unavailable")

    monkeypatch.setattr("infrastructure.security.s2s.cache.add", unavailable_add)
    monkeypatch.setattr("infrastructure.security.s2s.time.sleep", lambda _seconds: None)

    ok, reason = s2s.verify_request_once(
        timestamp_ms=timestamp_ms,
        signature=signature,
        body=body,
        method="GET",
        path="/api/engine/runtime-intents/00000000-0000-0000-0000-000000000000",
    )

    assert ok is False
    assert reason == "replay_cache_unavailable"
