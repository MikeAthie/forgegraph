from __future__ import annotations

from application.services import rate_limit


class _FallbackCache:
    def __init__(self) -> None:
        self.values: dict[str, int] = {}

    def add(self, key: str, value: int, timeout: int) -> bool:
        if key in self.values:
            return False
        self.values[key] = value
        return True

    def incr(self, key: str) -> int:
        raise ValueError(key)

    def get(self, key: str) -> int | None:
        return self.values.get(key)

    def set(self, key: str, value: int, timeout: int) -> None:
        self.values[key] = value


def test_check_rate_limit_incr_fallback_preserves_existing_count(monkeypatch) -> None:
    fake_cache = _FallbackCache()
    monkeypatch.setattr(rate_limit, "cache", fake_cache)

    first = rate_limit.check_rate_limit(
        scope="run_start",
        tenant_id="tenant-1",
        limit=1,
        window_seconds=60,
    )
    second = rate_limit.check_rate_limit(
        scope="run_start",
        tenant_id="tenant-1",
        limit=1,
        window_seconds=60,
    )

    assert first.allowed is True
    assert second.allowed is False
    assert second.remaining == 0
