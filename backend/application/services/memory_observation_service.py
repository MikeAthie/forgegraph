from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, TypedDict, cast
from uuid import UUID

from asgiref.sync import async_to_sync
from django.conf import settings
from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone
from django.utils.text import slugify

from adapters.embedding.openai_embedder import OpenAIEmbedder
from application.services.embedding_service import CachedEmbeddingService
from application.services.memory_observation_indexing import (
    CeleryObservationIndexDispatcher,
    ObservationIndexDispatcher,
)
from application.services.redaction import redact_payload, redact_text
from application.services.vector_search_service import MemorySearchResult, VectorSearchService
from infrastructure.orm.models import MemoryObservation

MAX_OBSERVATION_CONTENT_LENGTH = 8_000
MAX_SEARCH_QUERY_LENGTH = 512


class MemoryObservationMetadata(TypedDict):
    source_event_id: str
    source_event_type: str
    fact_hash: str
    provenance_json: dict[str, object]
    cost_metadata_json: dict[str, object]
    retention_policy_json: dict[str, object]


@dataclass(slots=True)
class ObservationContext:
    observations: list[MemoryObservation]
    degraded: bool
    strategies: list[str]


class ObservationVectorSearchService(Protocol):
    async def search(
        self,
        *,
        tenant_id: UUID | str,
        query: str,
        graph_id: UUID | str | None = None,
        agent_id: UUID | str | None = None,
        run_id: UUID | str | None = None,
        session_id: UUID | str | None = None,
        top_k: int = 5,
        threshold: float = 0.7,
        recency_weight: float = 0.2,
        model: str | None = None,
    ) -> list[MemorySearchResult]: ...


class MemoryObservationService:
    """Service layer for curated memory observation lifecycle and queries."""

    def __init__(
        self,
        *,
        index_dispatcher: ObservationIndexDispatcher | None = None,
        vector_search_service: ObservationVectorSearchService | None = None,
    ) -> None:
        self._index_dispatcher = index_dispatcher or CeleryObservationIndexDispatcher()
        self._vector_search_service: ObservationVectorSearchService | None
        if vector_search_service is not None:
            self._vector_search_service = vector_search_service
        elif getattr(settings, "FF_CURATED_MEMORY_VECTOR_INDEXING", True):
            self._vector_search_service = VectorSearchService(
                CachedEmbeddingService(
                    OpenAIEmbedder(
                        model=getattr(
                            settings, "CURATED_MEMORY_EMBEDDING_MODEL", "text-embedding-ada-002"
                        )
                    )
                )
            )
        else:
            self._vector_search_service = None

    def create_observation(
        self,
        *,
        tenant_id: UUID | str,
        type: str,
        title: str,
        content: str,
        scope: str,
        graph_id: UUID | str | None = None,
        run_id: UUID | str | None = None,
        session_id: UUID | str | None = None,
        agent_id: UUID | str | None = None,
        topic_key: str | None = None,
        tool_name: str | None = None,
        source_event_id: str | None = None,
        source_event_type: str | None = None,
        fact_hash: str | None = None,
        provenance_json: dict[str, object] | None = None,
        cost_metadata_json: dict[str, object] | None = None,
        retention_policy_json: dict[str, object] | None = None,
        dedupe: bool = True,
        update_topic: bool = False,
    ) -> MemoryObservation:
        normalized = self._normalize_payload(
            type=type,
            title=title,
            content=content,
            scope=scope,
            topic_key=topic_key,
            tool_name=tool_name,
        )
        scope_ids = self._normalize_scope_ids(
            graph_id=graph_id,
            run_id=run_id,
            session_id=session_id,
            agent_id=agent_id,
        )
        tenant_uuid = self._require_uuid(tenant_id, "tenant_id")
        metadata = self._normalize_metadata(
            source_event_id=source_event_id,
            source_event_type=source_event_type,
            fact_hash=fact_hash,
            provenance_json=provenance_json,
            cost_metadata_json=cost_metadata_json,
            retention_policy_json=retention_policy_json,
        )
        now = timezone.now()

        with transaction.atomic():
            if dedupe:
                duplicate = self._find_duplicate(
                    tenant_id=tenant_uuid,
                    type=normalized["type"],
                    title=normalized["title"],
                    content=normalized["content"],
                    scope=normalized["scope"],
                    topic_key=normalized["topic_key"],
                    tool_name=normalized["tool_name"],
                    **scope_ids,
                )
                if duplicate is not None:
                    duplicate.duplicate_count += 1
                    duplicate.last_seen_at = now
                    duplicate.save(update_fields=["duplicate_count", "last_seen_at", "updated_at"])
                    cast(Any, duplicate)._domain_event_created = False
                    return duplicate

            if update_topic and normalized["topic_key"]:
                topic_match = self._find_latest_topic_match(
                    tenant_id=tenant_uuid,
                    scope=normalized["scope"],
                    topic_key=normalized["topic_key"],
                    **scope_ids,
                )
                if topic_match is not None:
                    changed_fields = self._apply_updates(
                        topic_match,
                        title=normalized["title"],
                        content=normalized["content"],
                        topic_key=normalized["topic_key"],
                        tool_name=normalized["tool_name"],
                    )
                    changed_fields.update(self._apply_metadata(topic_match, **metadata))
                    topic_match.revision_count += 1
                    topic_match.last_seen_at = now
                    topic_match.save(
                        update_fields=sorted(
                            {
                                *changed_fields,
                                "revision_count",
                                "last_seen_at",
                                "updated_at",
                            }
                        )
                    )
                    self._schedule_index_upsert(topic_match.id)
                    cast(Any, topic_match)._domain_event_created = False
                    return topic_match

            observation = cast(
                MemoryObservation,
                MemoryObservation.objects.create(
                    tenant_id=tenant_uuid,
                    graph_id=scope_ids["graph_id"],
                    run_id=scope_ids["run_id"],
                    session_id=scope_ids["session_id"],
                    agent_id=scope_ids["agent_id"],
                    type=normalized["type"],
                    title=normalized["title"],
                    content=normalized["content"],
                    scope=normalized["scope"],
                    topic_key=normalized["topic_key"],
                    tool_name=normalized["tool_name"],
                    source_event_id=metadata["source_event_id"],
                    source_event_type=metadata["source_event_type"],
                    fact_hash=metadata["fact_hash"],
                    provenance_json=metadata["provenance_json"],
                    cost_metadata_json=metadata["cost_metadata_json"],
                    retention_policy_json=metadata["retention_policy_json"],
                    last_seen_at=now,
                ),
            )
            self._schedule_index_upsert(observation.id)
            cast(Any, observation)._domain_event_created = True
            return observation

    def update_observation(
        self,
        *,
        tenant_id: UUID | str,
        observation_id: UUID | str,
        type: str | None = None,
        title: str | None = None,
        content: str | None = None,
        topic_key: str | None = None,
        tool_name: str | None = None,
    ) -> MemoryObservation:
        observation = self.get_observation(tenant_id=tenant_id, observation_id=observation_id)
        changed_fields = self._apply_updates(
            observation,
            type=type,
            title=title,
            content=content,
            topic_key=topic_key,
            tool_name=tool_name,
        )
        if not changed_fields:
            return observation

        observation.revision_count += 1
        observation.last_seen_at = timezone.now()
        observation.save(
            update_fields=sorted(
                {
                    *changed_fields,
                    "revision_count",
                    "last_seen_at",
                    "updated_at",
                }
            )
        )
        self._schedule_index_upsert(observation.id)
        return observation

    def delete_observation(
        self,
        *,
        tenant_id: UUID | str,
        observation_id: UUID | str,
    ) -> MemoryObservation:
        observation = self.get_observation(tenant_id=tenant_id, observation_id=observation_id)
        observation.deleted_at = timezone.now()
        observation.save(update_fields=["deleted_at", "updated_at"])
        self._schedule_index_delete(observation.id)
        return observation

    def get_observation(
        self,
        *,
        tenant_id: UUID | str,
        observation_id: UUID | str,
        include_deleted: bool = False,
    ) -> MemoryObservation:
        queryset = self._base_queryset(tenant_id=tenant_id, include_deleted=include_deleted)
        observation = queryset.filter(
            id=self._require_uuid(observation_id, "observation_id")
        ).first()
        if observation is None:
            raise LookupError("Observation not found")
        return observation

    def search_observations(
        self,
        *,
        tenant_id: UUID | str,
        query: str = "",
        graph_id: UUID | str | None = None,
        run_id: UUID | str | None = None,
        session_id: UUID | str | None = None,
        agent_id: UUID | str | None = None,
        scope: str | None = None,
        type: str | None = None,
        topic_key: str | None = None,
        limit: int = 20,
        include_deleted: bool = False,
    ) -> list[MemoryObservation]:
        queryset = self._apply_filters(
            self._base_queryset(tenant_id=tenant_id, include_deleted=include_deleted),
            graph_id=graph_id,
            run_id=run_id,
            session_id=session_id,
            agent_id=agent_id,
            scope=scope,
            type=type,
            topic_key=topic_key,
        )
        if query.strip():
            safe_query = redact_text(query.strip())[:MAX_SEARCH_QUERY_LENGTH]
            search_filter = Q()
            for term in self._expand_query_terms(safe_query):
                search_filter |= (
                    Q(title__icontains=term)
                    | Q(content__icontains=term)
                    | Q(topic_key__icontains=self._normalize_topic_key(term))
                )
            queryset = queryset.filter(search_filter)
        return list(queryset.order_by("-last_seen_at", "-created_at")[:limit])

    def get_timeline(
        self,
        *,
        tenant_id: UUID | str,
        graph_id: UUID | str | None = None,
        run_id: UUID | str | None = None,
        session_id: UUID | str | None = None,
        agent_id: UUID | str | None = None,
        scope: str | None = None,
        limit: int = 50,
        include_deleted: bool = False,
    ) -> list[MemoryObservation]:
        queryset = self._apply_filters(
            self._base_queryset(tenant_id=tenant_id, include_deleted=include_deleted),
            graph_id=graph_id,
            run_id=run_id,
            session_id=session_id,
            agent_id=agent_id,
            scope=scope,
        )
        return list(queryset.order_by("-last_seen_at", "-created_at")[:limit])

    def get_context(
        self,
        *,
        tenant_id: UUID | str,
        graph_id: UUID | str | None = None,
        run_id: UUID | str | None = None,
        session_id: UUID | str | None = None,
        agent_id: UUID | str | None = None,
        query: str = "",
        limit: int = 10,
    ) -> ObservationContext:
        observations = self.search_observations(
            tenant_id=tenant_id,
            query=query,
            graph_id=graph_id,
            run_id=run_id,
            session_id=session_id,
            agent_id=agent_id,
            limit=limit,
        )
        strategies = ["fts"]
        degraded = True

        if (
            query.strip()
            and self._vector_search_service is not None
            and self._has_indexed_observations(
                tenant_id=tenant_id,
                graph_id=graph_id,
                run_id=run_id,
                session_id=session_id,
                agent_id=agent_id,
            )
        ):
            try:
                vector_observations = self._search_vector_observations(
                    tenant_id=tenant_id,
                    query=query,
                    graph_id=graph_id,
                    run_id=run_id,
                    session_id=session_id,
                    agent_id=agent_id,
                    limit=limit,
                )
                if vector_observations:
                    strategies.append("vector")
                observations = self._merge_results(vector_observations, observations, limit=limit)
                degraded = False
            except Exception:
                degraded = True

        return ObservationContext(
            observations=observations[:limit],
            degraded=degraded,
            strategies=[*strategies, "timeline"],
        )

    def _base_queryset(
        self,
        *,
        tenant_id: UUID | str,
        include_deleted: bool,
    ) -> QuerySet[MemoryObservation]:
        tenant_uuid = self._as_uuid(tenant_id)
        if tenant_uuid is None:
            raise ValueError("tenant_id is required")
        if include_deleted:
            return cast(
                QuerySet[MemoryObservation], MemoryObservation.objects.for_tenant(tenant_uuid)
            )
        return cast(
            QuerySet[MemoryObservation], MemoryObservation.objects.for_tenant(tenant_uuid).active()
        )

    def _apply_filters(
        self,
        queryset: QuerySet[MemoryObservation],
        *,
        graph_id: UUID | str | None = None,
        run_id: UUID | str | None = None,
        session_id: UUID | str | None = None,
        agent_id: UUID | str | None = None,
        scope: str | None = None,
        type: str | None = None,
        topic_key: str | None = None,
    ) -> QuerySet[MemoryObservation]:
        if graph_id is not None:
            queryset = queryset.filter(graph_id=self._as_uuid(graph_id))
        if run_id is not None:
            queryset = queryset.filter(run_id=self._as_uuid(run_id))
        if session_id is not None:
            queryset = queryset.filter(session_id=self._as_uuid(session_id))
        if agent_id is not None:
            queryset = queryset.filter(agent_id=self._as_uuid(agent_id))
        if scope is not None:
            queryset = queryset.filter(scope=self._normalize_scope(scope))
        if type is not None:
            queryset = queryset.filter(type=self._normalize_type(type))
        if topic_key is not None:
            queryset = queryset.filter(topic_key=self._normalize_topic_key(topic_key))
        return queryset

    def _find_duplicate(
        self,
        *,
        tenant_id: UUID,
        graph_id: UUID | None,
        run_id: UUID | None,
        session_id: UUID | None,
        agent_id: UUID | None,
        type: str,
        title: str,
        content: str,
        scope: str,
        topic_key: str,
        tool_name: str,
    ) -> MemoryObservation | None:
        return cast(
            MemoryObservation | None,
            MemoryObservation.objects.active()
            .filter(
                tenant_id=tenant_id,
                graph_id=graph_id,
                run_id=run_id,
                session_id=session_id,
                agent_id=agent_id,
                type=type,
                title=title,
                content=content,
                scope=scope,
                topic_key=topic_key,
                tool_name=tool_name,
            )
            .order_by("-last_seen_at")
            .first(),
        )

    def _find_latest_topic_match(
        self,
        *,
        tenant_id: UUID,
        graph_id: UUID | None,
        run_id: UUID | None,
        session_id: UUID | None,
        agent_id: UUID | None,
        scope: str,
        topic_key: str,
    ) -> MemoryObservation | None:
        return cast(
            MemoryObservation | None,
            MemoryObservation.objects.active()
            .filter(
                tenant_id=tenant_id,
                graph_id=graph_id,
                run_id=run_id,
                session_id=session_id,
                agent_id=agent_id,
                scope=scope,
                topic_key=topic_key,
            )
            .order_by("-last_seen_at")
            .first(),
        )

    def _apply_updates(
        self,
        observation: MemoryObservation,
        *,
        type: str | None = None,
        title: str | None = None,
        content: str | None = None,
        topic_key: str | None = None,
        tool_name: str | None = None,
    ) -> set[str]:
        changed_fields: set[str] = set()
        if type is not None:
            self._update_observation_field(
                observation, "type", self._normalize_type(type), changed_fields
            )
        if title is not None:
            self._update_observation_field(
                observation, "title", self._normalize_title(title), changed_fields
            )
        if content is not None:
            self._update_observation_field(
                observation, "content", self._normalize_content(content), changed_fields
            )
        if topic_key is not None:
            self._update_observation_field(
                observation,
                "topic_key",
                self._normalize_topic_key(topic_key),
                changed_fields,
            )
        if tool_name is not None:
            self._update_observation_field(
                observation,
                "tool_name",
                self._normalize_tool_name(tool_name),
                changed_fields,
            )
        return changed_fields

    def _update_observation_field(
        self,
        observation: MemoryObservation,
        field_name: str,
        value: object,
        changed_fields: set[str],
    ) -> None:
        if getattr(observation, field_name) == value:
            return
        setattr(observation, field_name, value)
        changed_fields.add(field_name)

    def _apply_metadata(
        self,
        observation: MemoryObservation,
        *,
        source_event_id: str,
        source_event_type: str,
        fact_hash: str,
        provenance_json: dict[str, object],
        cost_metadata_json: dict[str, object],
        retention_policy_json: dict[str, object],
    ) -> set[str]:
        changed_fields: set[str] = set()
        updates: dict[str, object] = {
            "source_event_id": source_event_id,
            "source_event_type": source_event_type,
            "fact_hash": fact_hash,
            "provenance_json": provenance_json,
            "cost_metadata_json": cost_metadata_json,
            "retention_policy_json": retention_policy_json,
        }
        for field, value in updates.items():
            if value in ("", {}) and getattr(observation, field) not in ("", {}):
                continue
            if getattr(observation, field) != value:
                setattr(observation, field, value)
                changed_fields.add(field)
        return changed_fields

    def _normalize_payload(
        self,
        *,
        type: str,
        title: str,
        content: str,
        scope: str,
        topic_key: str | None,
        tool_name: str | None,
    ) -> dict[str, str]:
        normalized_content = self._normalize_content(content)
        normalized_title = self._normalize_title(title) or normalized_content[:80]
        if not normalized_title:
            raise ValueError("title or content is required")
        return {
            "type": self._normalize_type(type),
            "title": normalized_title,
            "content": normalized_content,
            "scope": self._normalize_scope(scope),
            "topic_key": self._normalize_topic_key(topic_key or normalized_title),
            "tool_name": self._normalize_tool_name(tool_name),
        }

    def _normalize_metadata(
        self,
        *,
        source_event_id: str | None,
        source_event_type: str | None,
        fact_hash: str | None,
        provenance_json: dict[str, object] | None,
        cost_metadata_json: dict[str, object] | None,
        retention_policy_json: dict[str, object] | None,
    ) -> MemoryObservationMetadata:
        return {
            "source_event_id": redact_text(str(source_event_id or "").strip())[:128],
            "source_event_type": redact_text(str(source_event_type or "").strip())[:128],
            "fact_hash": redact_text(str(fact_hash or "").strip())[:64],
            "provenance_json": provenance_json if isinstance(provenance_json, dict) else {},
            "cost_metadata_json": cost_metadata_json
            if isinstance(cost_metadata_json, dict)
            else {},
            "retention_policy_json": retention_policy_json
            if isinstance(retention_policy_json, dict)
            else {},
        }

    def _normalize_scope_ids(
        self,
        *,
        graph_id: UUID | str | None,
        run_id: UUID | str | None,
        session_id: UUID | str | None,
        agent_id: UUID | str | None,
    ) -> dict[str, UUID | None]:
        scope_ids = {
            "graph_id": self._as_uuid(graph_id),
            "run_id": self._as_uuid(run_id),
            "session_id": self._as_uuid(session_id),
            "agent_id": self._as_uuid(agent_id),
        }
        if (
            scope_ids["graph_id"] is None
            and scope_ids["run_id"] is None
            and scope_ids["session_id"] is None
        ):
            raise ValueError("At least one of graph_id, run_id, or session_id is required")
        return scope_ids

    def _normalize_type(self, value: str) -> str:
        normalized = slugify(value.strip()).replace("-", "_")
        if not normalized:
            raise ValueError("type is required")
        return normalized[:64]

    def _normalize_title(self, value: str) -> str:
        return " ".join(redact_text(value).split())[:255]

    def _normalize_content(self, value: str) -> str:
        normalized = " ".join(redact_text(value).split())
        if not normalized:
            raise ValueError("content is required")
        return normalized[:MAX_OBSERVATION_CONTENT_LENGTH]

    def _normalize_scope(self, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"graph", "run", "session"}:
            raise ValueError("scope must be one of graph, run, or session")
        return normalized

    def _normalize_topic_key(self, value: str) -> str:
        normalized = slugify(redact_text(value).strip())
        return normalized[:128]

    def _normalize_tool_name(self, value: str | None) -> str:
        if value is None:
            return ""
        return slugify(redact_text(value).strip()).replace("-", "_")[:128]

    def _schedule_index_upsert(self, observation_id: UUID) -> None:
        transaction.on_commit(
            lambda: self._index_dispatcher.enqueue_upsert(observation_id=observation_id)
        )

    def _schedule_index_delete(self, observation_id: UUID) -> None:
        transaction.on_commit(
            lambda: self._index_dispatcher.enqueue_delete(observation_id=observation_id)
        )

    def _expand_query_terms(self, query: str) -> list[str]:
        terms = [query, *query.split()]
        expanded: list[str] = []
        seen: set[str] = set()

        for raw_term in terms:
            term = raw_term.strip().lower()
            if not term:
                continue

            variants = {term}
            if term.endswith("ies") and len(term) > 4:
                variants.add(f"{term[:-3]}y")
            elif term.endswith("y") and len(term) > 3:
                variants.add(f"{term[:-1]}ies")
            elif term.endswith("s") and len(term) > 3:
                variants.add(term[:-1])
            else:
                variants.add(f"{term}s")

            for variant in variants:
                if variant not in seen:
                    seen.add(variant)
                    expanded.append(variant)

        return expanded

    def _has_indexed_observations(
        self,
        *,
        tenant_id: UUID | str,
        graph_id: UUID | str | None = None,
        run_id: UUID | str | None = None,
        session_id: UUID | str | None = None,
        agent_id: UUID | str | None = None,
    ) -> bool:
        queryset = self._apply_filters(
            self._base_queryset(tenant_id=tenant_id, include_deleted=False),
            graph_id=graph_id,
            run_id=run_id,
            session_id=session_id,
            agent_id=agent_id,
        )
        return queryset.filter(memory_chunk__isnull=False).exists()

    def _search_vector_observations(
        self,
        *,
        tenant_id: UUID | str,
        query: str,
        graph_id: UUID | str | None = None,
        run_id: UUID | str | None = None,
        session_id: UUID | str | None = None,
        agent_id: UUID | str | None = None,
        limit: int,
    ) -> list[MemoryObservation]:
        if self._vector_search_service is None:
            return []

        results = async_to_sync(self._vector_search_service.search)(
            tenant_id=tenant_id,
            query=query,
            graph_id=graph_id,
            run_id=run_id,
            session_id=session_id,
            agent_id=agent_id,
            top_k=limit,
            model=getattr(settings, "CURATED_MEMORY_EMBEDDING_MODEL", "text-embedding-ada-002"),
        )
        observation_ids = [
            self._as_uuid(result.metadata.get("observation_id"))
            for result in results
            if result.metadata.get("observation_id")
        ]
        ordered_ids = [
            observation_id for observation_id in observation_ids if observation_id is not None
        ]
        if not ordered_ids:
            return []

        observations = {
            observation.id: observation
            for observation in self._apply_filters(
                self._base_queryset(tenant_id=tenant_id, include_deleted=False),
                graph_id=graph_id,
                run_id=run_id,
                session_id=session_id,
                agent_id=agent_id,
            ).filter(id__in=ordered_ids)
        }
        return [
            observations[observation_id]
            for observation_id in ordered_ids
            if observation_id in observations
        ]

    def _merge_results(
        self,
        primary: list[MemoryObservation],
        secondary: list[MemoryObservation],
        *,
        limit: int,
    ) -> list[MemoryObservation]:
        merged: list[MemoryObservation] = []
        seen: set[UUID] = set()
        for observation in [*primary, *secondary]:
            if observation.id in seen:
                continue
            seen.add(observation.id)
            merged.append(observation)
            if len(merged) >= limit:
                break
        return merged

    def _as_uuid(self, value: UUID | str | None) -> UUID | None:
        if value is None or value == "":
            return None
        if isinstance(value, UUID):
            return value
        return UUID(str(redact_payload(value)))

    def _require_uuid(self, value: UUID | str | None, field_name: str) -> UUID:
        normalized = self._as_uuid(value)
        if normalized is None:
            raise ValueError(f"{field_name} is required")
        return normalized
