from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable

from django.conf import settings


@dataclass(frozen=True)
class EngineTarget:
    engine_id: str
    host: str
    port: int

    @property
    def callback_url(self) -> str:
        template = str(getattr(settings, "ENGINE_CALLBACK_URL", "") or "").strip()
        return template


class EngineAssignmentError(ValueError):
    pass


def _raw_engine_targets() -> list[str]:
    raw = str(getattr(settings, "ENGINE_TARGETS", "") or "").strip()
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def _parse_target(raw: str, index: int) -> EngineTarget:
    engine_id = ""
    host_port = raw
    if "=" in raw:
        engine_id, host_port = [part.strip() for part in raw.split("=", 1)]
    if ":" not in host_port:
        raise ValueError(f"ENGINE_TARGETS entry '{raw}' must be 'id=host:port' or 'host:port'")
    host, port_raw = [part.strip() for part in host_port.rsplit(":", 1)]
    port = int(port_raw)
    resolved_engine_id = engine_id or f"engine-{index}"
    return EngineTarget(engine_id=resolved_engine_id, host=host, port=port)


def _default_target() -> EngineTarget:
    configured_id = str(getattr(settings, "ENGINE_INSTANCE_ID", "") or "").strip()
    host = str(getattr(settings, "ENGINE_HOST", "localhost") or "localhost").strip()
    port = int(getattr(settings, "ENGINE_PORT", 50051))
    engine_id = configured_id or f"{host}:{port}"
    return EngineTarget(engine_id=engine_id, host=host, port=port)


def get_engine_targets() -> list[EngineTarget]:
    raw_targets = _raw_engine_targets()
    if not raw_targets:
        return [_default_target()]
    return [_parse_target(raw, index + 1) for index, raw in enumerate(raw_targets)]


def get_default_engine_target() -> EngineTarget:
    return get_engine_targets()[0]


def get_default_engine_instance_id() -> str:
    return get_default_engine_target().engine_id


def is_multi_engine_enabled() -> bool:
    return len(get_engine_targets()) > 1


def _stable_hash(value: str) -> int:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def select_engine_target(*, run_id: str) -> EngineTarget:
    targets = get_engine_targets()
    if len(targets) == 1:
        return targets[0]
    index = _stable_hash(run_id) % len(targets)
    return targets[index]


def get_engine_target_by_id(engine_id: str) -> EngineTarget | None:
    normalized = str(engine_id or "").strip()
    if not normalized:
        return None
    for target in get_engine_targets():
        if target.engine_id == normalized:
            return target
    return None


def resolve_engine_callback_url(*, run_id: str) -> str:
    template = str(getattr(settings, "ENGINE_CALLBACK_URL", "") or "").strip()
    if "{run_id}" in template:
        return template.format(run_id=run_id)
    return template


def reconcile_run_engine_instance(
    *,
    assigned_engine_id: str,
    callback_engine_id: str | None,
) -> tuple[str, bool]:
    assigned = str(assigned_engine_id or "").strip()
    callback_value = str(callback_engine_id or "").strip()

    if not callback_value and not is_multi_engine_enabled():
        callback_value = get_default_engine_instance_id()

    if assigned:
        if callback_value and callback_value != assigned:
            raise EngineAssignmentError(
                f"engine instance mismatch: expected {assigned}, got {callback_value}"
            )
        return assigned, False

    if callback_value:
        return callback_value, True

    if is_multi_engine_enabled():
        raise EngineAssignmentError(
            "engine_instance_id is required for callbacks when multi-engine mode is enabled"
        )

    fallback = get_default_engine_instance_id()
    return fallback, True


def serialize_engine_targets(targets: Iterable[EngineTarget]) -> list[dict[str, object]]:
    return [
        {"engine_id": target.engine_id, "host": target.host, "port": target.port}
        for target in targets
    ]
