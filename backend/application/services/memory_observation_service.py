from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone
from django.utils.text import slugify

from application.services.redaction import redact_payload, redact_text
from infrastructure.orm.models import MemoryObservation

MAX_OBSERVATION_CONTENT_LENGTH = 8_000
MAX_SEARCH_QUERY_LENGTH = 512


@dataclass(slots=True)
class ObservationContext:
    observations: list[MemoryObservation]
    degraded: bool
    strategies: list[str]


class MemoryObservationService:
    """Service layer for curated memory observation lifecycle and queries."""

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
        tenant_uuid = self._as_uuid(tenant_id)
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
                    return topic_match

            return MemoryObservation.objects.create(
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
                last_seen_at=now,
            )

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
        return observation

    def get_observation(
        self,
        *,
        tenant_id: UUID | str,
        observation_id: UUID | str,
        include_deleted: bool = False,
    ) -> MemoryObservation:
        queryset = self._base_queryset(tenant_id=tenant_id, include_deleted=include_deleted)
        observation = queryset.filter(id=self._as_uuid(observation_id)).first()
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
            queryset = queryset.filter(
                Q(title__icontains=safe_query)
                | Q(content__icontains=safe_query)
                | Q(topic_key__icontains=self._normalize_topic_key(safe_query))
            )
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
        return ObservationContext(
            observations=observations,
            degraded=True,
            strategies=["fts", "timeline"],
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
        queryset = MemoryObservation.objects.for_tenant(tenant_uuid)
        if not include_deleted:
            queryset = queryset.active()
        return queryset

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
        return (
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
            .first()
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
        return (
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
            .first()
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
            normalized_type = self._normalize_type(type)
            if observation.type != normalized_type:
                observation.type = normalized_type
                changed_fields.add("type")
        if title is not None:
            normalized_title = self._normalize_title(title)
            if observation.title != normalized_title:
                observation.title = normalized_title
                changed_fields.add("title")
        if content is not None:
            normalized_content = self._normalize_content(content)
            if observation.content != normalized_content:
                observation.content = normalized_content
                changed_fields.add("content")
        if topic_key is not None:
            normalized_topic = self._normalize_topic_key(topic_key)
            if observation.topic_key != normalized_topic:
                observation.topic_key = normalized_topic
                changed_fields.add("topic_key")
        if tool_name is not None:
            normalized_tool = self._normalize_tool_name(tool_name)
            if observation.tool_name != normalized_tool:
                observation.tool_name = normalized_tool
                changed_fields.add("tool_name")
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

    def _as_uuid(self, value: UUID | str | None) -> UUID | None:
        if value is None or value == "":
            return None
        if isinstance(value, UUID):
            return value
        return UUID(str(redact_payload(value)))
