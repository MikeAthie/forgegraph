"""
Graphs API serializers.

Clean Architecture: Interface Adapters layer.
"""

from rest_framework import serializers

from infrastructure.orm.models import MemoryConfiguration


class GraphCreateSerializer(serializers.Serializer):
    """Serializer for creating a graph."""

    name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, default="", allow_blank=True)


class GraphUpdateSerializer(serializers.Serializer):
    """Serializer for updating a graph."""

    name = serializers.CharField(max_length=255, required=False)
    description = serializers.CharField(required=False, allow_blank=True)


class GraphVersionSummarySerializer(serializers.Serializer):
    """Serializer for graph version in list views."""

    id = serializers.UUIDField(read_only=True)
    version = serializers.IntegerField(read_only=True)
    checksum = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)


class GraphListSerializer(serializers.Serializer):
    """Serializer for graph list output."""

    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)
    version_count = serializers.IntegerField(read_only=True)
    latest_version = serializers.IntegerField(read_only=True, allow_null=True)


class GraphDetailSerializer(serializers.Serializer):
    """Serializer for graph detail output."""

    id = serializers.UUIDField(read_only=True)
    owner_id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)
    versions = GraphVersionSummarySerializer(many=True, read_only=True)


class GraphVersionCreateSerializer(serializers.Serializer):
    """Serializer for creating a graph version."""

    graph_json = serializers.JSONField()

    def validate_graph_json(self, value):
        """Validate the graph JSON structure."""
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

        return value


class GraphVersionDetailSerializer(serializers.Serializer):
    """Serializer for graph version detail output."""

    id = serializers.UUIDField(read_only=True)
    graph_id = serializers.UUIDField(read_only=True)
    version = serializers.IntegerField(read_only=True)
    graph_json = serializers.JSONField(read_only=True)
    checksum = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)


class MemoryConfigurationSerializer(serializers.ModelSerializer):
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

    def validate_buffer_size(self, value):
        if value < 1 or value > 200:
            raise serializers.ValidationError("buffer_size must be between 1 and 200")
        return value

    def validate_vector_threshold(self, value):
        if value < 0.5 or value > 0.99:
            raise serializers.ValidationError("vector_threshold must be between 0.5 and 0.99")
        return value

    def validate_vector_recency_weight(self, value):
        if value < 0 or value > 1:
            raise serializers.ValidationError("vector_recency_weight must be between 0 and 1")
        return value

    def validate_vector_top_k(self, value):
        if value < 1 or value > 50:
            raise serializers.ValidationError("vector_top_k must be between 1 and 50")
        return value

    def validate_embedding_model(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("embedding_model cannot be empty")
        return value.strip()

    def validate(self, attrs):
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
