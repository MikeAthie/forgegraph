"""
Graphs API serializers.

Clean Architecture: Interface Adapters layer.
"""

from rest_framework import serializers


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
