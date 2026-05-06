from __future__ import annotations

from collections import Counter
from datetime import datetime
from threading import RLock
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

WS_SUBSCRIBERS_CACHE_KEY = "forgegraph:ws:run_subscribers"
WS_SUBSCRIBERS_TTL_SECONDS = 60 * 60 * 24
DEFAULT_MAX_CONNECTIONS_PER_ORG = 250
DEFAULT_MAX_CONNECTIONS_PER_USER = 20
DEFAULT_STALE_SUBSCRIBER_SECONDS = 45
_SUBSCRIBERS_LOCK = RLock()


def _stale_subscriber_seconds() -> int:
    configured = getattr(settings, "WS_SUBSCRIBER_STALE_AFTER_SECONDS", None)
    if configured is not None:
        try:
            return max(int(configured), 1)
        except (TypeError, ValueError):
            return DEFAULT_STALE_SUBSCRIBER_SECONDS
    heartbeat = max(
        _setting_int("RUN_WS_HEARTBEAT_INTERVAL_SECONDS", 12),
        _setting_int("ORG_WS_HEARTBEAT_INTERVAL_SECONDS", 12),
    )
    return max(heartbeat * 3 + 10, DEFAULT_STALE_SUBSCRIBER_SECONDS)


def _parse_timestamp(raw_value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(raw_value or ""))
    except ValueError:
        return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _prune_stale_subscribers(
    subscribers: dict[str, dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], bool]:
    cutoff = timezone.now().timestamp() - _stale_subscriber_seconds()
    pruned: dict[str, dict[str, Any]] = {}
    changed = False
    for connection_id, subscriber in subscribers.items():
        timestamp = _parse_timestamp(
            subscriber.get("last_seen_at") or subscriber.get("connected_at")
        )
        if timestamp is None or timestamp.timestamp() < cutoff:
            changed = True
            continue
        pruned[connection_id] = subscriber
    return pruned, changed


def _subscriber_map() -> dict[str, dict[str, Any]]:
    payload = cache.get(WS_SUBSCRIBERS_CACHE_KEY)
    subscribers = payload if isinstance(payload, dict) else {}
    pruned, changed = _prune_stale_subscribers(subscribers)
    if changed:
        _store_subscriber_map(pruned)
    return pruned


def _store_subscriber_map(subscribers: dict[str, dict[str, Any]]) -> None:
    cache.set(WS_SUBSCRIBERS_CACHE_KEY, subscribers, timeout=WS_SUBSCRIBERS_TTL_SECONDS)


def _setting_int(name: str, default: int) -> int:
    raw = getattr(settings, name, default)
    try:
        return max(int(raw), 0)
    except (TypeError, ValueError):
        return default


def websocket_connection_limits() -> dict[str, int]:
    return {
        "per_org": _setting_int(
            "RUN_WS_MAX_CONNECTIONS_PER_ORG",
            DEFAULT_MAX_CONNECTIONS_PER_ORG,
        ),
        "per_user": _setting_int(
            "RUN_WS_MAX_CONNECTIONS_PER_USER",
            DEFAULT_MAX_CONNECTIONS_PER_USER,
        ),
    }


def _counts_for(
    subscribers: dict[str, dict[str, Any]],
    *,
    organization_id: str,
    user_id: str,
) -> dict[str, int]:
    return {
        "organization": sum(
            1
            for item in subscribers.values()
            if str(item.get("organization_id") or "") == str(organization_id)
        ),
        "user": sum(
            1 for item in subscribers.values() if str(item.get("user_id") or "") == str(user_id)
        ),
    }


def can_accept_run_websocket_subscriber(
    *,
    organization_id: str,
    user_id: str,
) -> tuple[bool, dict[str, Any]]:
    with _SUBSCRIBERS_LOCK:
        subscribers = _subscriber_map()
        counts = _counts_for(subscribers, organization_id=organization_id, user_id=user_id)
        limits = websocket_connection_limits()
    if counts["organization"] >= limits["per_org"]:
        return (
            False,
            {
                "code": "org_connection_limit",
                "message": "Organization WebSocket connection limit exceeded.",
                "counts": counts,
                "limits": limits,
            },
        )
    if counts["user"] >= limits["per_user"]:
        return (
            False,
            {
                "code": "user_connection_limit",
                "message": "User WebSocket connection limit exceeded.",
                "counts": counts,
                "limits": limits,
            },
        )
    return True, {"counts": counts, "limits": limits}


def _normalize_event_types(event_types: list[str] | tuple[str, ...] | None) -> list[str]:
    if not event_types:
        return []
    normalized = {
        str(event_type).strip() for event_type in event_types if str(event_type or "").strip()
    }
    return sorted(normalized)


def register_run_websocket_subscriber(
    *,
    connection_id: str,
    run_id: str,
    organization_id: str,
    user_id: str,
    event_level: str,
    event_types: list[str] | tuple[str, ...] | None = None,
    last_seen_event_id: str = "",
    last_seen_state_version: int = 0,
) -> None:
    now = timezone.now().isoformat()
    with _SUBSCRIBERS_LOCK:
        subscribers = _subscriber_map()
        subscribers[connection_id] = {
            "connection_id": connection_id,
            "run_id": run_id,
            "organization_id": organization_id,
            "user_id": user_id,
            "event_level": event_level,
            "event_types": _normalize_event_types(event_types),
            "last_seen_event_id": str(last_seen_event_id or ""),
            "last_seen_state_version": max(int(last_seen_state_version or 0), 0),
            "connected_at": now,
            "last_seen_at": now,
            "heartbeat_count": 0,
            "messages_sent": 0,
            "messages_dropped": 0,
            "messages_filtered": 0,
            "slow_disconnect": False,
        }
        _store_subscriber_map(subscribers)


def unregister_run_websocket_subscriber(*, connection_id: str) -> None:
    with _SUBSCRIBERS_LOCK:
        subscribers = _subscriber_map()
        subscribers.pop(connection_id, None)
        _store_subscriber_map(subscribers)


def update_run_websocket_subscriber_activity(
    *,
    connection_id: str,
    event_id: str | None = None,
    state_version: int | None = None,
    event_type: str | None = None,
    sent: bool = False,
    dropped: bool = False,
    filtered: bool = False,
    heartbeat: bool = False,
    slow_disconnect: bool = False,
    slow_disconnect_reason: str = "",
    sent_count: int = 0,
    dropped_count: int = 0,
    filtered_count: int = 0,
    heartbeat_count: int = 0,
) -> None:
    with _SUBSCRIBERS_LOCK:
        subscribers = _subscriber_map()
        subscriber = subscribers.get(connection_id)
        if not isinstance(subscriber, dict):
            return
        subscriber["last_seen_at"] = timezone.now().isoformat()
        if event_id:
            subscriber["last_seen_event_id"] = str(event_id)
        if state_version is not None and state_version > 0:
            subscriber["last_seen_state_version"] = max(
                int(subscriber.get("last_seen_state_version") or 0),
                int(state_version),
            )
        if event_type:
            subscriber["last_event_type"] = str(event_type)
        sent_increment = max(int(sent_count or 0), 0) + (1 if sent else 0)
        dropped_increment = max(int(dropped_count or 0), 0) + (1 if dropped else 0)
        filtered_increment = max(int(filtered_count or 0), 0) + (1 if filtered else 0)
        heartbeat_increment = max(int(heartbeat_count or 0), 0) + (1 if heartbeat else 0)
        if sent_increment:
            subscriber["messages_sent"] = int(subscriber.get("messages_sent") or 0) + sent_increment
        if dropped_increment:
            subscriber["messages_dropped"] = (
                int(subscriber.get("messages_dropped") or 0) + dropped_increment
            )
        if filtered_increment:
            subscriber["messages_filtered"] = (
                int(subscriber.get("messages_filtered") or 0) + filtered_increment
            )
        if heartbeat_increment:
            subscriber["heartbeat_count"] = (
                int(subscriber.get("heartbeat_count") or 0) + heartbeat_increment
            )
        if slow_disconnect:
            subscriber["slow_disconnect"] = True
            subscriber["slow_disconnect_reason"] = str(slow_disconnect_reason or "send_timeout")
        subscribers[connection_id] = subscriber
        _store_subscriber_map(subscribers)


def get_websocket_subscriber_snapshot() -> dict[str, Any]:
    with _SUBSCRIBERS_LOCK:
        subscribers = list(_subscriber_map().values())
    by_org = Counter(str(item.get("organization_id") or "") for item in subscribers)
    by_run = Counter(str(item.get("run_id") or "") for item in subscribers)
    by_user = Counter(str(item.get("user_id") or "") for item in subscribers)
    sent_by_org: Counter[str] = Counter()
    dropped_by_org: Counter[str] = Counter()
    filtered_by_org: Counter[str] = Counter()
    slow_by_org: Counter[str] = Counter()
    for item in subscribers:
        organization_id = str(item.get("organization_id") or "")
        if not organization_id:
            continue
        sent_by_org[organization_id] += int(item.get("messages_sent") or 0)
        dropped_by_org[organization_id] += int(item.get("messages_dropped") or 0)
        filtered_by_org[organization_id] += int(item.get("messages_filtered") or 0)
        if bool(item.get("slow_disconnect")):
            slow_by_org[organization_id] += 1

    limits = websocket_connection_limits()
    return {
        "active_connections": len(subscribers),
        "by_org": [
            {
                "organization_id": key,
                "connections": value,
                "limit": limits["per_org"],
                "remaining": max(limits["per_org"] - value, 0),
                "messages_sent": sent_by_org[key],
                "messages_dropped": dropped_by_org[key],
                "messages_filtered": filtered_by_org[key],
                "slow_disconnects": slow_by_org[key],
            }
            for key, value in sorted(by_org.items())
            if key
        ],
        "by_run": [
            {"run_id": key, "connections": value} for key, value in sorted(by_run.items()) if key
        ],
        "by_user": [
            {"user_id": key, "connections": value} for key, value in sorted(by_user.items()) if key
        ],
        "limits": limits,
        "fanout": {
            "messages_sent": sum(int(item.get("messages_sent") or 0) for item in subscribers),
            "messages_dropped": sum(int(item.get("messages_dropped") or 0) for item in subscribers),
            "messages_filtered": sum(
                int(item.get("messages_filtered") or 0) for item in subscribers
            ),
            "slow_disconnects": sum(1 for item in subscribers if bool(item.get("slow_disconnect"))),
        },
        "connections": subscribers,
        "generated_at": timezone.now().isoformat(),
    }
