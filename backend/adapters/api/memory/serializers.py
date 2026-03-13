from __future__ import annotations

from typing import Any, cast

from rest_framework import serializers


def _strip_or_none(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


class MemoryObservationDetailSerializer(serializers.Serializer[Any]):
    id = serializers.UUIDField()
    tenant_id = serializers.UUIDField()
    graph_id = serializers.UUIDField(allow_null=True)
    run_id = serializers.UUIDField(allow_null=True)
    session_id = serializers.UUIDField(allow_null=True)
    agent_id = serializers.UUIDField(allow_null=True)
    memory_chunk_id = serializers.UUIDField(allow_null=True)
    type = serializers.CharField()
    title = serializers.CharField()
    content = serializers.CharField()
    scope = serializers.CharField()
    topic_key = serializers.CharField()
    tool_name = serializers.CharField()
    revision_count = serializers.IntegerField()
    duplicate_count = serializers.IntegerField()
    last_seen_at = serializers.DateTimeField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    deleted_at = serializers.DateTimeField(allow_null=True)
    is_deleted = serializers.BooleanField()


class MemoryObservationCreateSerializer(serializers.Serializer[Any]):
    type = serializers.CharField(max_length=64)
    title = serializers.CharField(required=False, allow_blank=True, max_length=255)
    content = serializers.CharField()
    scope = serializers.ChoiceField(choices=["graph", "run", "session"])
    graph_id = serializers.UUIDField(required=False, allow_null=True)
    run_id = serializers.UUIDField(required=False, allow_null=True)
    session_id = serializers.UUIDField(required=False, allow_null=True)
    agent_id = serializers.UUIDField(required=False, allow_null=True)
    topic_key = serializers.CharField(required=False, allow_blank=True, max_length=128)
    tool_name = serializers.CharField(required=False, allow_blank=True, max_length=128)
    dedupe = serializers.BooleanField(required=False, default=True)
    update_topic = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        if not any(attrs.get(field) for field in ("graph_id", "run_id", "session_id")):
            raise serializers.ValidationError(
                "At least one of graph_id, run_id, or session_id is required."
            )
        return attrs


class MemoryObservationUpdateSerializer(serializers.Serializer[Any]):
    type = serializers.CharField(required=False, max_length=64)
    title = serializers.CharField(required=False, allow_blank=True, max_length=255)
    content = serializers.CharField(required=False)
    topic_key = serializers.CharField(required=False, allow_blank=True, max_length=128)
    tool_name = serializers.CharField(required=False, allow_blank=True, max_length=128)

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        if not attrs:
            raise serializers.ValidationError("At least one field must be provided.")
        return attrs


class MemoryObservationQuerySerializer(serializers.Serializer[Any]):
    query = serializers.CharField(required=False, allow_blank=True)
    graph_id = serializers.UUIDField(required=False, allow_null=True)
    run_id = serializers.UUIDField(required=False, allow_null=True)
    session_id = serializers.UUIDField(required=False, allow_null=True)
    agent_id = serializers.UUIDField(required=False, allow_null=True)
    scope = serializers.ChoiceField(choices=["graph", "run", "session"], required=False)
    type = serializers.CharField(required=False, allow_blank=True, max_length=64)
    topic_key = serializers.CharField(required=False, allow_blank=True, max_length=128)
    limit = serializers.IntegerField(required=False, min_value=1, max_value=100, default=20)
    include_deleted = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        attrs["query"] = _strip_or_none(cast(str | None, attrs.get("query"))) or ""
        attrs["type"] = _strip_or_none(cast(str | None, attrs.get("type")))
        attrs["topic_key"] = _strip_or_none(cast(str | None, attrs.get("topic_key")))
        return attrs


class MemoryObservationTimelineSerializer(serializers.Serializer[Any]):
    graph_id = serializers.UUIDField(required=False, allow_null=True)
    run_id = serializers.UUIDField(required=False, allow_null=True)
    session_id = serializers.UUIDField(required=False, allow_null=True)
    agent_id = serializers.UUIDField(required=False, allow_null=True)
    scope = serializers.ChoiceField(choices=["graph", "run", "session"], required=False)
    limit = serializers.IntegerField(required=False, min_value=1, max_value=100, default=50)
    include_deleted = serializers.BooleanField(required=False, default=False)


class MemoryObservationContextSerializer(serializers.Serializer[Any]):
    query = serializers.CharField(required=False, allow_blank=True)
    graph_id = serializers.UUIDField(required=False, allow_null=True)
    run_id = serializers.UUIDField(required=False, allow_null=True)
    session_id = serializers.UUIDField(required=False, allow_null=True)
    agent_id = serializers.UUIDField(required=False, allow_null=True)
    limit = serializers.IntegerField(required=False, min_value=1, max_value=100, default=10)

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        attrs["query"] = _strip_or_none(cast(str | None, attrs.get("query"))) or ""
        return attrs
