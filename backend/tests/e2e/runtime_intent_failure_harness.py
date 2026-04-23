from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from io import StringIO
from typing import Any

from application.services.structured_logging import JsonLogFormatter


@dataclass
class _PendingEntry:
    consumer: str
    delivery_count: int
    last_delivered_at: float


@dataclass
class _ConsumerState:
    idle_ms: int = 0


@dataclass
class _GroupState:
    delivered_index: int = 0
    pending: dict[str, _PendingEntry] = field(default_factory=dict)
    consumers: dict[str, _ConsumerState] = field(default_factory=dict)


class FakeRuntimeIntentRedis:
    """Small Redis Streams harness for intent-consumer failure tests."""

    def __init__(self) -> None:
        self._streams: dict[str, list[tuple[str, dict[str, Any]]]] = {}
        self._groups: dict[str, dict[str, _GroupState]] = {}
        self._next_ids: dict[str, int] = {}

    def xgroup_create(
        self,
        name: str,
        groupname: str,
        id: str = "0",
        mkstream: bool = True,
    ) -> bool:
        _ = id
        if mkstream:
            self._streams.setdefault(name, [])
        groups = self._groups.setdefault(name, {})
        if groupname in groups:
            raise RuntimeError("BUSYGROUP Consumer Group name already exists")
        groups[groupname] = _GroupState()
        return True

    def xadd(self, stream: str, fields: dict[str, Any]) -> str:
        messages = self._streams.setdefault(stream, [])
        next_id = self._next_ids.get(stream, 0) + 1
        self._next_ids[stream] = next_id
        message_id = f"{next_id}-0"
        messages.append((message_id, dict(fields)))
        return message_id

    def xlen(self, stream: str) -> int:
        return len(self._streams.get(stream, []))

    def xreadgroup(
        self,
        *,
        groupname: str,
        consumername: str,
        streams: dict[str, str],
        count: int,
        block: int,
    ) -> list[tuple[str, list[tuple[str, dict[str, Any]]]]]:
        _ = block
        stream_name, stream_position = next(iter(streams.items()))
        if stream_position != ">":
            raise RuntimeError("FakeRuntimeIntentRedis only supports xreadgroup with '>'")

        group = self._groups[stream_name][groupname]
        messages = self._streams.get(stream_name, [])
        batch = messages[group.delivered_index : group.delivered_index + count]
        if not batch:
            return []

        now = time.monotonic()
        group.consumers.setdefault(consumername, _ConsumerState()).idle_ms = 0
        for message_id, _ in batch:
            group.pending[message_id] = _PendingEntry(
                consumer=consumername,
                delivery_count=1,
                last_delivered_at=now,
            )
        group.delivered_index += len(batch)
        return [(stream_name, [(message_id, dict(fields)) for message_id, fields in batch])]

    def xpending_range(
        self,
        stream: str,
        groupname: str,
        start: str,
        end: str,
        count: int,
        consumername: str | None = None,
    ) -> list[dict[str, Any]]:
        _ = end
        _ = count
        pending = self._groups.get(stream, {}).get(groupname, _GroupState()).pending.get(start)
        group = self._groups.get(stream, {}).get(groupname, _GroupState())
        if start == "-" and end == "+":
            entries = sorted(group.pending.items(), key=lambda item: item[0])[:count]
        elif pending is None:
            entries = []
        else:
            entries = [(start, pending)]

        now = time.monotonic()
        results: list[dict[str, Any]] = []
        for message_id, entry in entries:
            if consumername is not None and entry.consumer != consumername:
                continue
            results.append(
                {
                    "message_id": message_id,
                    "consumer": entry.consumer,
                    "times_delivered": entry.delivery_count,
                    "idle": int(max((now - entry.last_delivered_at) * 1000, 0)),
                    "time_since_delivered": int(max((now - entry.last_delivered_at) * 1000, 0)),
                }
            )
        return results

    def xack(self, stream: str, groupname: str, message_id: str) -> int:
        group = self._groups[stream][groupname]
        return 1 if group.pending.pop(message_id, None) is not None else 0

    def xautoclaim(
        self,
        stream: str,
        groupname: str,
        consumername: str,
        min_idle_time: int,
        start_id: str,
        count: int,
    ) -> tuple[str, list[tuple[str, dict[str, Any]]], list[str]]:
        _ = start_id
        group = self._groups[stream][groupname]
        messages_by_id = dict(self._streams.get(stream, []))
        now = time.monotonic()
        consumer_state = group.consumers.setdefault(consumername, _ConsumerState())
        consumer_state.idle_ms = 0
        claimed: list[tuple[str, dict[str, Any]]] = []
        for message_id, pending in list(group.pending.items()):
            idle_ms = (now - pending.last_delivered_at) * 1000
            if idle_ms < min_idle_time:
                continue
            pending.consumer = consumername
            pending.delivery_count += 1
            pending.last_delivered_at = now
            claimed.append((message_id, dict(messages_by_id[message_id])))
            if len(claimed) >= count:
                break
        return ("0-0", claimed, [])

    def xinfo_groups(self, stream: str) -> list[dict[str, Any]]:
        groups = []
        for group_name, group in self._groups.get(stream, {}).items():
            groups.append(
                {
                    "name": group_name,
                    "pending": len(group.pending),
                    "lag": max(len(self._streams.get(stream, [])) - group.delivered_index, 0),
                    "last-delivered-id": self._streams.get(stream, [("0-0", {})])[
                        max(min(group.delivered_index, len(self._streams.get(stream, []))) - 1, 0)
                    ][0]
                    if group.delivered_index > 0 and self._streams.get(stream)
                    else "0-0",
                }
            )
        return groups

    def xinfo_consumers(self, stream: str, groupname: str) -> list[dict[str, Any]]:
        group = self._groups.get(stream, {}).get(groupname)
        if group is None:
            return []
        now = time.monotonic()
        consumers: list[dict[str, Any]] = []
        for consumer_name, consumer_state in group.consumers.items():
            latest_delivery = max(
                (
                    pending.last_delivered_at
                    for pending in group.pending.values()
                    if pending.consumer == consumer_name
                ),
                default=now,
            )
            idle_ms = int(max((now - latest_delivery) * 1000, 0))
            consumer_state.idle_ms = idle_ms
            consumers.append({"name": consumer_name, "idle": idle_ms})
        return consumers

    def xtrim(
        self,
        stream: str,
        maxlen: int | None = None,
        approximate: bool = True,
        minid: str | None = None,
        limit: int | None = None,
    ) -> int:
        _ = approximate
        _ = limit
        messages = self._streams.get(stream, [])
        removed = 0
        if minid is not None:
            retained: list[tuple[str, dict[str, Any]]] = []
            for message_id, fields in messages:
                if self._compare_stream_ids(message_id, minid) < 0:
                    removed += 1
                    continue
                retained.append((message_id, fields))
            self._streams[stream] = retained
            return removed
        if maxlen is None or maxlen < 0 or len(messages) <= maxlen:
            return 0
        removed = len(messages) - maxlen
        self._streams[stream] = messages[removed:]
        return removed

    def xrevrange(
        self,
        stream: str,
        max: str = "+",
        min: str = "-",
        count: int | None = None,
    ) -> list[tuple[str, dict[str, Any]]]:
        _ = max
        _ = min
        entries = list(reversed(self._streams.get(stream, [])))
        if count is not None:
            entries = entries[:count]
        return [(message_id, dict(fields)) for message_id, fields in entries]

    def pending_count(self, stream: str, groupname: str) -> int:
        return len(self._groups.get(stream, {}).get(groupname, _GroupState()).pending)

    def stream_entries(self, stream: str) -> list[tuple[str, dict[str, Any]]]:
        return list(self._streams.get(stream, []))

    def _compare_stream_ids(self, left: str, right: str) -> int:
        left_head, _, left_tail = left.partition("-")
        right_head, _, right_tail = right.partition("-")
        left_value = (int(left_head or "0"), int(left_tail or "0"))
        right_value = (int(right_head or "0"), int(right_tail or "0"))
        if left_value < right_value:
            return -1
        if left_value > right_value:
            return 1
        return 0


class CrashBeforeAckRedis:
    """Wrap a fake Redis client and fail the next ack to simulate a crash window."""

    def __init__(self, base: FakeRuntimeIntentRedis, *, crash_count: int = 1) -> None:
        self._base = base
        self._remaining = crash_count

    def xack(self, stream: str, groupname: str, message_id: str) -> int:
        if self._remaining > 0:
            self._remaining -= 1
            raise RuntimeError("simulated consumer crash before ack")
        return self._base.xack(stream, groupname, message_id)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._base, name)


def build_json_logger(name: str) -> tuple[logging.Logger, StringIO]:
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonLogFormatter())

    logger = logging.getLogger(name)
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger, stream


def parse_json_logs(stream: StringIO) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for line in stream.getvalue().splitlines():
        line = line.strip()
        if not line:
            continue
        payloads.append(json.loads(line))
    return payloads
