from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from opentelemetry.trace import Span
else:
    Span = Any

otel_propagate: Any | None
otel_trace: Any | None
OTelTracerProvider: type[Any] | None
OTelNoOpTracerProvider: type[Any] | None

try:
    from opentelemetry import propagate as _otel_propagate
    from opentelemetry import trace as _otel_trace
    from opentelemetry.sdk.trace import TracerProvider as _OTelTracerProvider
    from opentelemetry.trace import NoOpTracerProvider as _OTelNoOpTracerProvider
except ImportError:  # pragma: no cover - dependency guard for local bootstrapping
    otel_propagate = None
    otel_trace = None
    OTelTracerProvider = None
    OTelNoOpTracerProvider = None
else:
    otel_propagate = _otel_propagate
    otel_trace = _otel_trace
    OTelTracerProvider = _OTelTracerProvider
    OTelNoOpTracerProvider = _OTelNoOpTracerProvider


def _ensure_tracer_provider() -> None:
    if otel_trace is None or OTelTracerProvider is None or OTelNoOpTracerProvider is None:
        return
    provider = otel_trace.get_tracer_provider()
    if isinstance(provider, OTelNoOpTracerProvider):
        otel_trace.set_tracer_provider(OTelTracerProvider())


def _coerce_attribute(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


@contextmanager
def start_backend_span(
    name: str,
    *,
    traceparent: str | None = None,
    tracestate: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> Iterator[Span | None]:
    if otel_trace is None or otel_propagate is None:
        yield None
        return

    _ensure_tracer_provider()
    carrier: dict[str, str] = {}
    if traceparent:
        carrier["traceparent"] = traceparent
    if tracestate:
        carrier["tracestate"] = tracestate
    context = otel_propagate.extract(carrier=carrier)
    tracer = otel_trace.get_tracer("forgegraph.backend")
    with tracer.start_as_current_span(name, context=context) as span:
        for key, value in (attributes or {}).items():
            coerced = _coerce_attribute(value)
            if coerced is not None:
                span.set_attribute(key, coerced)
        yield span
