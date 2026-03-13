"""
Graphs API serializers.

Clean Architecture: Interface Adapters layer.
"""

from typing import Any

from rest_framework import serializers

from infrastructure.orm.models import MemoryConfiguration


def _validate_graph_json_payload(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise serializers.ValidationError("graph_json must be an object")

    if "nodes" not in value:
        raise serializers.ValidationError("graph_json must contain 'nodes'")

    if "edges" not in value:
        raise serializers.ValidationError("graph_json must contain 'edges'")

    if not isinstance(value.get("nodes"), list):
        raise serializers.ValidationError("'nodes' must be an array")

    if not isinstance(value.get("edges"), list):
        raise serializers.ValidationError("'edges' must be an array")

    if "metadata" in value and not isinstance(value.get("metadata"), dict):
        raise serializers.ValidationError("'metadata' must be an object")

    if "editor_state" in value and not isinstance(value.get("editor_state"), dict):
        raise serializers.ValidationError("'editor_state' must be an object")

    if "graph_id" in value and not isinstance(value.get("graph_id"), str):
        raise serializers.ValidationError("'graph_id' must be a string")

    if "version_id" in value and not isinstance(value.get("version_id"), str):
        raise serializers.ValidationError("'version_id' must be a string")

    return value


class GraphCreateSerializer(serializers.Serializer[Any]):
    """Serializer for creating a graph."""

    name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, default="", allow_blank=True)


class GraphUpdateSerializer(serializers.Serializer[Any]):
    """Serializer for updating a graph."""

    name = serializers.CharField(max_length=255, required=False)
    description = serializers.CharField(required=False, allow_blank=True)


class GraphVersionSummarySerializer(serializers.Serializer[Any]):
    """Serializer for graph version in list views."""

    id = serializers.UUIDField(read_only=True)
    version = serializers.IntegerField(read_only=True)
    checksum = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)


class GraphListSerializer(serializers.Serializer[Any]):
    """Serializer for graph list output."""

    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)
    version_count = serializers.IntegerField(read_only=True)
    latest_version = serializers.IntegerField(read_only=True, allow_null=True)


class GraphDetailSerializer(serializers.Serializer[Any]):
    """Serializer for graph detail output."""

    id = serializers.UUIDField(read_only=True)
    owner_id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)
    versions = GraphVersionSummarySerializer(many=True, read_only=True)


class GraphVersionCreateSerializer(serializers.Serializer[Any]):
    """Serializer for creating a graph version."""

    graph_json = serializers.JSONField()

    def validate_graph_json(self, value: Any) -> dict[str, Any]:
        """Validate the graph JSON structure."""
        return _validate_graph_json_payload(value)


class ExternalWorkflowCreateSerializer(serializers.Serializer[Any]):
    """Serializer for creating a graph and initial version in one request."""

    name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, default="", allow_blank=True)
    graph_json = serializers.JSONField()
    external_source = serializers.CharField(required=False, default="external", max_length=64)
    external_ref = serializers.CharField(required=False, max_length=255)
    idempotency_key = serializers.CharField(required=False, max_length=255)
    strict = serializers.BooleanField(required=False, default=False)
    require_entry_exit = serializers.BooleanField(required=False, default=False)

    def validate_graph_json(self, value: Any) -> dict[str, Any]:
        return _validate_graph_json_payload(value)

    def validate_external_source(self, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise serializers.ValidationError("external_source cannot be empty")
        return normalized

    def validate_external_ref(self, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise serializers.ValidationError("external_ref cannot be blank")
        return normalized

    def validate_idempotency_key(self, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise serializers.ValidationError("idempotency_key cannot be blank")
        return normalized


class ExternalWorkflowCreateResponseSerializer(serializers.Serializer[Any]):
    """Serializer for external workflow create response payload."""

    graph_id = serializers.UUIDField(read_only=True)
    graph_version_id = serializers.UUIDField(read_only=True)
    graph_name = serializers.CharField(read_only=True)
    graph_description = serializers.CharField(read_only=True)
    graph_version = serializers.IntegerField(read_only=True)
    checksum = serializers.CharField(read_only=True)
    external_source = serializers.CharField(read_only=True)
    external_ref = serializers.CharField(read_only=True, allow_blank=True)
    idempotency_key = serializers.CharField(read_only=True, allow_blank=True)
    created_graph = serializers.BooleanField(read_only=True)
    created_version = serializers.BooleanField(read_only=True)
    idempotent_replay = serializers.BooleanField(read_only=True)
    warnings = serializers.ListField(
        child=serializers.DictField(child=serializers.JSONField()),
        read_only=True,
    )


class GraphVersionDetailSerializer(serializers.Serializer[Any]):
    """Serializer for graph version detail output."""

    id = serializers.UUIDField(read_only=True)
    graph_id = serializers.UUIDField(read_only=True)
    version = serializers.IntegerField(read_only=True)
    graph_json = serializers.JSONField(read_only=True)
    checksum = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)


class MemoryConfigurationSerializer(serializers.ModelSerializer[MemoryConfiguration]):
    """Serializer for memory configuration."""

    class Meta:
        model = MemoryConfiguration
        fields = [
            "id",
            "graph",
            "user",
            "buffer_enabled",
            "buffer_size",
            "auto_prepend",
            "redis_enabled",
            "redis_summary_ttl",
            "redis_facts_ttl",
            "vector_enabled",
            "vector_top_k",
            "vector_threshold",
            "vector_recency_weight",
            "embedding_model",
            "summarization_enabled",
            "summarization_threshold",
            "summarization_keep_recent",
            "summarization_model",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "graph", "user", "created_at", "updated_at"]

    def validate_buffer_size(self, value: int) -> int:
        if value < 1 or value > 200:
            raise serializers.ValidationError("buffer_size must be between 1 and 200")
        return value

    def validate_vector_threshold(self, value: float) -> float:
        if value < 0.5 or value > 0.99:
            raise serializers.ValidationError("vector_threshold must be between 0.5 and 0.99")
        return value

    def validate_vector_recency_weight(self, value: float) -> float:
        if value < 0 or value > 1:
            raise serializers.ValidationError("vector_recency_weight must be between 0 and 1")
        return value

    def validate_vector_top_k(self, value: int) -> int:
        if value < 1 or value > 50:
            raise serializers.ValidationError("vector_top_k must be between 1 and 50")
        return value

    def validate_embedding_model(self, value: str) -> str:
        if not value or not value.strip():
            raise serializers.ValidationError("embedding_model cannot be empty")
        return value.strip()

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        instance = getattr(self, "instance", None)
        threshold = attrs.get(
            "summarization_threshold",
            instance.summarization_threshold if instance else 30,
        )
        keep_recent = attrs.get(
            "summarization_keep_recent",
            instance.summarization_keep_recent if instance else 10,
        )
        if threshold < keep_recent + 10:
            raise serializers.ValidationError(
                "summarization_threshold must be at least keep_recent + 10"
            )
        return attrs
