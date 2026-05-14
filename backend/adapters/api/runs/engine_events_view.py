"""Engine callback event adapter."""

# ruff: noqa: F403,F405,I001

from adapters.api.runs.common import *  # noqa: F403
from adapters.api.runs.engine_callback_ingestion import EngineCallbackIngestionMixin
from adapters.api.runs.engine_callback_observability import EngineCallbackObservabilityMixin
from adapters.api.runs.engine_node_lifecycle import EngineNodeLifecycleMixin
from adapters.api.runs.engine_run_lifecycle import EngineRunLifecycleMixin


class EngineRunEventsView(
    EngineCallbackIngestionMixin,
    EngineCallbackObservabilityMixin,
    EngineRunLifecycleMixin,
    EngineNodeLifecycleMixin,
    APIView,
):
    """Persist + broadcast engine execution events (S2S).

    Events never mutate durable state directly. The backend validates, deduplicates,
    enforces monotonicity/ownership rules, and then performs durable writes.
    """

    permission_classes = [AllowAny]
    throttle_classes: list[type] = []

    def post(self, request: Request) -> Response:
        for attempt in range(_DEADLOCK_RETRY_ATTEMPTS):
            try:
                return self._post_once(
                    request,
                    verify_signature=not bool(getattr(request, "_forgegraph_s2s_verified", False)),
                )
            except OperationalError as exc:
                if (
                    not _is_deadlock(exc)
                    or attempt >= _DEADLOCK_RETRY_ATTEMPTS - 1
                    or not bool(getattr(request, "_forgegraph_s2s_verified", False))
                ):
                    raise
                time.sleep(0.02 * (attempt + 1))
        raise RuntimeError("unreachable engine callback retry state")
