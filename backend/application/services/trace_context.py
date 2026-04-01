from __future__ import annotations

import secrets
from typing import Any

TRACEPARENT_VERSION = "00"


def generate_trace_id() -> str:
    return secrets.token_hex(16)


def generate_span_id() -> str:
    return secrets.token_hex(8)


def parse_traceparent(traceparent: str | None) -> dict[str, str] | None:
    raw = str(traceparent or "").strip()
    parts = raw.split("-")
    if len(parts) != 4:
        return None
    version, trace_id, span_id, trace_flags = parts
    if len(version) != 2 or len(trace_id) != 32 or len(span_id) != 16 or len(trace_flags) != 2:
        return None
    try:
        int(version, 16)
        int(trace_id, 16)
        int(span_id, 16)
        int(trace_flags, 16)
    except ValueError:
        return None
    if trace_id == "0" * 32 or span_id == "0" * 16:
        return None
    return {
        "version": version.lower(),
        "trace_id": trace_id.lower(),
        "span_id": span_id.lower(),
        "trace_flags": trace_flags.lower(),
    }


def format_traceparent(
    *,
    trace_id: str,
    span_id: str,
    trace_flags: str = "01",
    version: str = TRACEPARENT_VERSION,
) -> str:
    return f"{version}-{trace_id}-{span_id}-{trace_flags}"


def ensure_trace_context(
    *,
    traceparent: str | None = None,
    tracestate: str | None = None,
    trace_id: str | None = None,
) -> dict[str, str]:
    parsed = parse_traceparent(traceparent)
    if parsed:
        return {
            "trace_id": parsed["trace_id"],
            "span_id": parsed["span_id"],
            "trace_flags": parsed["trace_flags"],
            "traceparent": format_traceparent(
                trace_id=parsed["trace_id"],
                span_id=parsed["span_id"],
                trace_flags=parsed["trace_flags"],
                version=parsed["version"],
            ),
            "tracestate": str(tracestate or "").strip(),
        }

    effective_trace_id = str(trace_id or "").strip().lower() or generate_trace_id()
    effective_span_id = generate_span_id()
    return {
        "trace_id": effective_trace_id,
        "span_id": effective_span_id,
        "trace_flags": "01",
        "traceparent": format_traceparent(trace_id=effective_trace_id, span_id=effective_span_id),
        "tracestate": str(tracestate or "").strip(),
    }


def default_runtime_limits(settings_obj: Any) -> dict[str, int]:
    return {
        "max_run_duration_ms": int(
            getattr(settings_obj, "RUN_RUNTIME_LIMIT_MAX_DURATION_MS", 300000)
        ),
        "max_tool_calls_total": int(getattr(settings_obj, "RUN_RUNTIME_LIMIT_MAX_TOOL_CALLS", 32)),
        "max_llm_calls_total": int(getattr(settings_obj, "RUN_RUNTIME_LIMIT_MAX_LLM_CALLS", 24)),
    }
