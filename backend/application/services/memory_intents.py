from __future__ import annotations

import hashlib
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from application.services.idempotency import (
    hash_request_payload,
    normalize_idempotency_key,
    record_idempotency_observation,
)
from application.services.memory_observation_service import MemoryObservationService
from application.services.tenancy import get_tenant_id_for_user
from infrastructure.orm.models import (
    AgentRegistryEntry,
    MemoryObservation,
    ProcessedMemoryEvent,
    Run,
)


@dataclass(frozen=True, slots=True)
class MemoryIntentResult:
    observations: list[MemoryObservation]
    duplicate: bool = False

    @property
    def observation_count(self) -> int:
        return len(self.observations)


class NoopObservationIndexDispatcher:
    """Avoid making engine callback success depend on async indexing infrastructure."""

    def enqueue_upsert(
        self,
        *,
        observation_id: UUID | str,
        embedding_model: str | None = None,
    ) -> None:
        _ = observation_id
        _ = embedding_model

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
        event_type = _normalize_memory_event_type(event_type)
        payload = _normalize_memory_payload(event_type=event_type, payload=payload)
        tenant_id = str(run.organization_id or get_tenant_id_for_user(run.owner))
        graph_id = run.graph_version.graph_id
        self._validate_memory_context(run=run, tenant_id=tenant_id, payload=payload)
        event_key = normalize_idempotency_key(
            _optional_text(payload, "idempotency_key") or event_id,
            max_length=128,
        )
        if event_key:
            request_hash = hash_request_payload(
                {
                    "event_type": event_type,
                    "payload": payload,
                    "run_id": str(run.id),
                }
            )
            existing = ProcessedMemoryEvent.objects.filter(
                organization_id=tenant_id,
                event_id=event_key,
            ).first()
            if existing is not None:
                if existing.request_hash != request_hash:
                    raise ValueError("memory event idempotency key reused with different payload")
                observations = list(
                    MemoryObservation.objects.filter(
                        tenant_id=tenant_id,
                        id__in=list(existing.observation_ids_json or []),
                    )
                )
                record_idempotency_observation(
                    boundary="memory_write",
                    status="already_applied",
                    idempotency_key=event_key,
                    resource_type="memory_observation",
                    organization_id=tenant_id,
                    run_id=run.id,
                )
                return MemoryIntentResult(observations=observations, duplicate=True)

            with transaction.atomic():
                locked_existing = (
                    ProcessedMemoryEvent.objects.select_for_update()
                    .filter(organization_id=tenant_id, event_id=event_key)
                    .first()
                )
                if locked_existing is not None:
                    observations = list(
                        MemoryObservation.objects.filter(
                            tenant_id=tenant_id,
                            id__in=list(locked_existing.observation_ids_json or []),
                        )
                    )
                    return MemoryIntentResult(observations=observations, duplicate=True)
                result = self._apply_engine_memory_intent_unchecked(
                    tenant_id=tenant_id,
                    graph_id=graph_id,
                    run=run,
                    event_type=event_type,
                    payload=payload,
                    event_id=event_id,
                )
                ProcessedMemoryEvent.objects.create(
                    organization_id=tenant_id,
                    event_id=event_key,
                    idempotency_key=event_key,
                    event_type=event_type,
                    request_hash=request_hash,
                    observation_ids_json=[
                        str(observation.id) for observation in result.observations
                    ],
                    response_status=200,
                    response_body={
                        "observation_ids": [
                            str(observation.id) for observation in result.observations
                        ],
                        "observation_count": result.observation_count,
                    },
                )
                record_idempotency_observation(
                    boundary="memory_write",
                    status="applied",
                    idempotency_key=event_key,
                    resource_type="memory_observation",
                    organization_id=tenant_id,
                    run_id=run.id,
                )
                return result

        return self._apply_engine_memory_intent_unchecked(
            tenant_id=tenant_id,
            graph_id=graph_id,
            run=run,
            event_type=event_type,
            payload=payload,
            event_id=event_id,
        )

    def _apply_engine_memory_intent_unchecked(
        self,
        *,
        tenant_id: str,
        graph_id: UUID,
        run: Run,
        event_type: str,
        payload: dict[str, Any],
        event_id: str,
    ) -> MemoryIntentResult:
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

    def _validate_memory_context(
        self,
        *,
        run: Run,
        tenant_id: str,
        payload: dict[str, Any],
    ) -> None:
        for field_name in ("tenant_id", "organization_id", "org_id"):
            field_value = _optional_text(payload, field_name)
            if field_value and field_value != tenant_id:
                raise ValueError(f"{field_name} does not match run organization")

        payload_run_id = _optional_text(payload, "run_id")
        if payload_run_id and payload_run_id != str(run.id):
            raise ValueError("run_id does not match callback run")

        agent_id = _optional_text(payload, "agent_id")
        if (
            agent_id
            and not AgentRegistryEntry.objects.filter(
                organization_id=tenant_id,
                id=agent_id,
            ).exists()
        ):
            raise ValueError("agent_id does not belong to the run organization")

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
        agent_id = _optional_text(payload, "agent_id") or None
        return self._observations.create_observation(
            tenant_id=tenant_id,
            graph_id=graph_id,
            run_id=run_id,
            agent_id=agent_id,
            type="summary",
            title=f"Engine summary {summary_id}",
            content=content,
            scope="run",
            topic_key=f"engine-summary-{summary_id}",
            tool_name="engine_summarizer",
            source_event_id=event_id,
            source_event_type="summary_created",
            provenance_json=_provenance(
                payload=payload,
                event_id=event_id,
                event_type="summary_created",
                memory_kind="summary",
                summary_id=summary_id,
            ),
            cost_metadata_json=_cost_metadata(payload),
            retention_policy_json=_retention_policy(payload),
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
        raw_facts = _fact_items(payload)
        summary_id = _optional_text(payload, "summary_id") or event_id or "unknown"
        agent_id = _optional_text(payload, "agent_id") or None
        observations: list[MemoryObservation] = []
        for index, raw_fact in enumerate(raw_facts):
            if not isinstance(raw_fact, dict):
                raise ValueError("memory_fact_extracted facts must be objects")
            key = _optional_text(raw_fact, "key") or f"fact-{index + 1}"
            value = _required_text(raw_fact, "value")
            source_span = _optional_text(raw_fact, "source_span") or _optional_text(
                payload, "source_span"
            )
            confidence = _confidence(raw_fact.get("confidence", payload.get("confidence")))
            fact_hash = _fact_hash(
                tenant_id=tenant_id,
                run_id=run_id,
                agent_id=agent_id,
                key=key,
                value=value,
                source_span=source_span,
            )
            existing = (
                MemoryObservation.objects.active()
                .filter(
                    tenant_id=tenant_id,
                    fact_hash=fact_hash,
                )
                .first()
            )
            if existing is not None:
                existing.duplicate_count += 1
                existing.last_seen_at = timezone.now()
                existing.save(update_fields=["duplicate_count", "last_seen_at", "updated_at"])
                observations.append(existing)
                continue
            observations.append(
                self._observations.create_observation(
                    tenant_id=tenant_id,
                    graph_id=graph_id,
                    run_id=run_id,
                    agent_id=agent_id,
                    type="fact",
                    title=key,
                    content=value,
                    scope="run",
                    topic_key=f"engine-fact-{summary_id}-{key}",
                    tool_name="engine_summarizer",
                    source_event_id=event_id,
                    source_event_type="memory_fact_extracted",
                    fact_hash=fact_hash,
                    provenance_json=_provenance(
                        payload=payload,
                        event_id=event_id,
                        event_type="memory_fact_extracted",
                        memory_kind="fact",
                        summary_id=summary_id,
                        fact_key=key,
                        source_span=source_span,
                        confidence=confidence,
                        fact_hash=fact_hash,
                    ),
                    cost_metadata_json=_cost_metadata(payload),
                    retention_policy_json=_retention_policy(payload),
                    dedupe=True,
                    update_topic=False,
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
        agent_id = _optional_text(payload, "agent_id") or None
        return self._observations.create_observation(
            tenant_id=tenant_id,
            graph_id=graph_id,
            run_id=run_id,
            agent_id=agent_id,
            type=memory_type,
            title=title,
            content=content,
            scope="run",
            topic_key=f"engine-memory-{topic_key}",
            tool_name=_optional_text(payload, "tool_name") or "engine",
            source_event_id=event_id,
            source_event_type="memory_write_requested",
            provenance_json=_provenance(
                payload=payload,
                event_id=event_id,
                event_type="memory_write_requested",
                memory_kind=memory_type,
            ),
            cost_metadata_json=_cost_metadata(payload),
            retention_policy_json=_retention_policy(payload),
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


def _normalize_memory_event_type(event_type: str) -> str:
    normalized = str(event_type or "").strip()
    return {
        "memory.write_requested": "memory_write_requested",
        "memory.fact_extracted": "memory_fact_extracted",
        "summary.created": "summary_created",
    }.get(normalized, normalized)


def _normalize_memory_payload(*, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload or {})
    nested = normalized.get("payload")
    if isinstance(nested, dict):
        merged = dict(nested)
        for key in (
            "tenant_id",
            "organization_id",
            "org_id",
            "run_id",
            "agent_id",
            "idempotency_key",
        ):
            if key in normalized and key not in merged:
                merged[key] = normalized[key]
        normalized = merged
    if event_type == "memory_fact_extracted" and "facts" not in normalized:
        fact = _optional_text(normalized, "fact")
        if fact:
            normalized["facts"] = [
                {
                    "key": _optional_text(normalized, "key") or "fact",
                    "value": fact,
                    "confidence": normalized.get("confidence"),
                    "source_span": normalized.get("source_span"),
                }
            ]
    return normalized


def _fact_items(payload: dict[str, Any]) -> list[Any]:
    raw_facts = payload.get("facts")
    if not isinstance(raw_facts, list):
        raise ValueError("memory_fact_extracted requires a facts array")
    return raw_facts


def _confidence(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        confidence = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("confidence must be a number between 0 and 1") from exc
    if confidence < 0 or confidence > 1:
        raise ValueError("confidence must be a number between 0 and 1")
    return confidence


def _fact_hash(
    *,
    tenant_id: str,
    run_id: UUID,
    agent_id: str | None,
    key: str,
    value: str,
    source_span: str,
) -> str:
    hash_input = "|".join(
        [
            tenant_id,
            str(run_id),
            str(agent_id or ""),
            "fact",
            key.strip().lower(),
            value.strip().lower(),
            source_span.strip().lower(),
        ]
    )
    return hashlib.sha256(hash_input.encode("utf-8")).hexdigest()


def _provenance(
    *,
    payload: dict[str, Any],
    event_id: str,
    event_type: str,
    memory_kind: str,
    summary_id: str = "",
    fact_key: str = "",
    source_span: str = "",
    confidence: float | None = None,
    fact_hash: str = "",
) -> dict[str, object]:
    provenance: dict[str, object] = {
        "source": "engine_memory_intent",
        "backend_owner": "memory_service",
        "event_id": event_id,
        "event_type": event_type,
        "memory_kind": memory_kind,
    }
    if summary_id:
        provenance["summary_id"] = summary_id
    if fact_key:
        provenance["fact_key"] = fact_key
    if source_span:
        provenance["source_span"] = source_span
    if confidence is not None:
        provenance["confidence"] = confidence
    if fact_hash:
        provenance["fact_hash"] = fact_hash
    if _optional_text(payload, "model"):
        provenance["model"] = _optional_text(payload, "model")
    return provenance


def _cost_metadata(payload: dict[str, Any]) -> dict[str, object]:
    cost_usd = _optional_decimal(payload, "cost_usd")
    total_tokens = _optional_int(payload, "total_tokens")
    prompt_tokens = _optional_int(payload, "prompt_tokens")
    completion_tokens = _optional_int(payload, "completion_tokens")
    metadata: dict[str, object] = {}
    if cost_usd is not None:
        metadata["cost_usd"] = str(cost_usd)
        metadata["currency"] = "USD"
    if total_tokens is not None:
        metadata["total_tokens"] = total_tokens
    if prompt_tokens is not None:
        metadata["prompt_tokens"] = prompt_tokens
    if completion_tokens is not None:
        metadata["completion_tokens"] = completion_tokens
    if _optional_text(payload, "model"):
        metadata["model"] = _optional_text(payload, "model")
    if _optional_text(payload, "provider"):
        metadata["provider"] = _optional_text(payload, "provider")
    return metadata


def _retention_policy(payload: dict[str, Any]) -> dict[str, object]:
    ttl_seconds = _optional_int(payload, "ttl_seconds")
    policy: dict[str, object] = {"source": "backend_memory_service"}
    if ttl_seconds is not None:
        if ttl_seconds < 0:
            raise ValueError("ttl_seconds must be non-negative")
        policy["ttl_seconds"] = ttl_seconds
    if _optional_text(payload, "retention_policy"):
        policy["policy"] = _optional_text(payload, "retention_policy")
    return policy


def _optional_decimal(payload: dict[str, Any], key: str) -> Decimal | None:
    value = payload.get(key)
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{key} must be decimal-compatible") from exc


def _optional_int(payload: dict[str, Any], key: str) -> int | None:
    value = payload.get(key)
    if value in (None, ""):
        return None
    try:
        return int(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be an integer") from exc
