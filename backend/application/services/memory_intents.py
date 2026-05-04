from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from application.services.memory_observation_service import MemoryObservationService
from application.services.tenancy import get_tenant_id_for_user
from infrastructure.orm.models import MemoryObservation, Run


@dataclass(frozen=True, slots=True)
class MemoryIntentResult:
    observations: list[MemoryObservation]

    @property
    def observation_count(self) -> int:
        return len(self.observations)


class NoopObservationIndexDispatcher:
    """Avoid making engine callback success depend on async indexing infrastructure."""

    def enqueue_upsert(self, *, observation_id: UUID | str) -> None:
        _ = observation_id

    def enqueue_delete(self, *, observation_id: UUID | str) -> None:
        _ = observation_id


class NoopObservationVectorSearchService:
    async def search(self, **kwargs: Any) -> list[Any]:
        _ = kwargs
        return []


class BackendMemoryIntentService:
    """Apply engine memory intent events through backend-owned memory records."""

    def __init__(self, observation_service: MemoryObservationService | None = None) -> None:
        self._observations = observation_service or MemoryObservationService(
            index_dispatcher=NoopObservationIndexDispatcher(),
            vector_search_service=NoopObservationVectorSearchService(),
        )

    def apply_engine_memory_intent(
        self,
        *,
        run: Run,
        event_type: str,
        payload: dict[str, Any],
        event_id: str = "",
    ) -> MemoryIntentResult:
        tenant_id = str(run.organization_id or get_tenant_id_for_user(run.owner))
        graph_id = run.graph_version.graph_id

        if event_type == "summary_created":
            return MemoryIntentResult(
                [
                    self._create_summary_observation(
                        tenant_id=tenant_id,
                        graph_id=graph_id,
                        run_id=run.id,
                        payload=payload,
                        event_id=event_id,
                    )
                ]
            )

        if event_type == "memory_fact_extracted":
            return MemoryIntentResult(
                self._create_fact_observations(
                    tenant_id=tenant_id,
                    graph_id=graph_id,
                    run_id=run.id,
                    payload=payload,
                    event_id=event_id,
                )
            )

        if event_type == "memory_write_requested":
            return MemoryIntentResult(
                [
                    self._create_requested_memory_observation(
                        tenant_id=tenant_id,
                        graph_id=graph_id,
                        run_id=run.id,
                        payload=payload,
                        event_id=event_id,
                    )
                ]
            )

        raise ValueError(f"Unsupported memory intent event type: {event_type}")

    def _create_summary_observation(
        self,
        *,
        tenant_id: str,
        graph_id: UUID,
        run_id: UUID,
        payload: dict[str, Any],
        event_id: str,
    ) -> MemoryObservation:
        content = _required_text(payload, "content")
        summary_id = _optional_text(payload, "summary_id") or event_id or "unknown"
        return self._observations.create_observation(
            tenant_id=tenant_id,
            graph_id=graph_id,
            run_id=run_id,
            type="summary",
            title=f"Engine summary {summary_id}",
            content=content,
            scope="run",
            topic_key=f"engine-summary-{summary_id}",
            tool_name="engine_summarizer",
            dedupe=True,
            update_topic=True,
        )

    def _create_fact_observations(
        self,
        *,
        tenant_id: str,
        graph_id: UUID,
        run_id: UUID,
        payload: dict[str, Any],
        event_id: str,
    ) -> list[MemoryObservation]:
        raw_facts = payload.get("facts")
        if not isinstance(raw_facts, list):
            raise ValueError("memory_fact_extracted requires a facts array")

        summary_id = _optional_text(payload, "summary_id") or event_id or "unknown"
        observations: list[MemoryObservation] = []
        for index, raw_fact in enumerate(raw_facts):
            if not isinstance(raw_fact, dict):
                raise ValueError("memory_fact_extracted facts must be objects")
            key = _optional_text(raw_fact, "key") or f"fact-{index + 1}"
            value = _required_text(raw_fact, "value")
            observations.append(
                self._observations.create_observation(
                    tenant_id=tenant_id,
                    graph_id=graph_id,
                    run_id=run_id,
                    type="fact",
                    title=key,
                    content=value,
                    scope="run",
                    topic_key=f"engine-fact-{summary_id}-{key}",
                    tool_name="engine_summarizer",
                    dedupe=True,
                    update_topic=True,
                )
            )

        if not observations:
            raise ValueError("memory_fact_extracted requires at least one fact")
        return observations

    def _create_requested_memory_observation(
        self,
        *,
        tenant_id: str,
        graph_id: UUID,
        run_id: UUID,
        payload: dict[str, Any],
        event_id: str,
    ) -> MemoryObservation:
        content = _optional_text(payload, "content") or _required_text(payload, "value")
        title = (
            _optional_text(payload, "title") or _optional_text(payload, "key") or "Engine memory"
        )
        memory_type = _optional_text(payload, "type") or "engine_memory_write"
        topic_key = (
            _optional_text(payload, "idempotency_key")
            or _optional_text(payload, "topic_key")
            or event_id
            or title
        )
        return self._observations.create_observation(
            tenant_id=tenant_id,
            graph_id=graph_id,
            run_id=run_id,
            type=memory_type,
            title=title,
            content=content,
            scope="run",
            topic_key=f"engine-memory-{topic_key}",
            tool_name=_optional_text(payload, "tool_name") or "engine",
            dedupe=True,
            update_topic=True,
        )


def _optional_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if value is None:
        return ""
    return str(value).strip()


def _required_text(payload: dict[str, Any], key: str) -> str:
    value = _optional_text(payload, key)
    if not value:
        raise ValueError(f"{key} is required")
    return value
