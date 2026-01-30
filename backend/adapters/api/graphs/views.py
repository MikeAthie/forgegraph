"""
Graphs API views.

Clean Architecture: Interface Adapters layer.
"""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.graphs.serializers import (
    GraphCreateSerializer,
    GraphDetailSerializer,
    GraphListSerializer,
    GraphUpdateSerializer,
    GraphVersionCreateSerializer,
    GraphVersionDetailSerializer,
    GraphVersionSummarySerializer,
    MemoryConfigurationSerializer,
)
from adapters.api.responses import error_response, success_response
from domain.services.graph_validator import GraphValidator
from infrastructure.orm.models import Graph, GraphVersion, MemoryConfiguration


class GraphListCreateView(APIView):
    """List and create graphs."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        """List user's graphs."""
        graphs = Graph.objects.for_user(request.user).order_by("-updated_at")

        # Add version counts
        result = []
        for graph in graphs:
            latest_version = graph.versions.order_by("-version").first()
            result.append(
                {
                    "id": graph.id,
                    "name": graph.name,
                    "description": graph.description,
                    "created_at": graph.created_at,
                    "updated_at": graph.updated_at,
                    "version_count": graph.versions.count(),
                    "latest_version": latest_version.version if latest_version else None,
                }
            )

        serialized_data = GraphListSerializer(result, many=True).data
        return success_response(serialized_data)

    def post(self, request: Request) -> Response:
        """Create a new graph."""
        serializer = GraphCreateSerializer(data=request.data)

        if not serializer.is_valid():
            return error_response(
                code="VALIDATION_ERROR",
                message="The request contains invalid fields",
                status=status.HTTP_400_BAD_REQUEST,
                details=[
                    {"field": field, "issue": ", ".join(errors)}
                    for field, errors in serializer.errors.items()
                ],
            )

        graph = Graph.objects.create(
            owner=request.user,
            name=serializer.validated_data["name"],
            description=serializer.validated_data.get("description", ""),
        )

        default_config = MemoryConfiguration.objects.filter(user=request.user).first()
        if default_config:
            MemoryConfiguration.objects.create(
                graph=graph,
                buffer_enabled=default_config.buffer_enabled,
                buffer_size=default_config.buffer_size,
                auto_prepend=default_config.auto_prepend,
                redis_enabled=default_config.redis_enabled,
                redis_summary_ttl=default_config.redis_summary_ttl,
                redis_facts_ttl=default_config.redis_facts_ttl,
                vector_enabled=default_config.vector_enabled,
                vector_top_k=default_config.vector_top_k,
                vector_threshold=default_config.vector_threshold,
            )
        else:
            MemoryConfiguration.objects.create(graph=graph)

        graph_data = GraphListSerializer(
            {
                "id": graph.id,
                "name": graph.name,
                "description": graph.description,
                "created_at": graph.created_at,
                "updated_at": graph.updated_at,
                "version_count": 0,
                "latest_version": None,
            }
        ).data

        return success_response(graph_data, status=status.HTTP_201_CREATED)


class GraphDetailView(APIView):
    """Get, update, delete a graph."""

    permission_classes = [IsAuthenticated]

    def get_object(self, graph_id, user):
        """Get graph or raise 404."""
        try:
            return Graph.objects.get(id=graph_id, owner=user)
        except Graph.DoesNotExist:
            return None

    def get(self, request: Request, graph_id) -> Response:
        """Get graph details with versions."""
        graph = self.get_object(graph_id, request.user)
        if not graph:
            return error_response(
                code="NOT_FOUND",
                message=f"Graph with id '{graph_id}' not found or you do not have access to it",
                status=status.HTTP_404_NOT_FOUND,
            )

        versions = graph.versions.order_by("-version").values(
            "id", "version", "checksum", "created_at"
        )

        graph_data = GraphDetailSerializer(
            {
                "id": graph.id,
                "owner_id": graph.owner_id,
                "name": graph.name,
                "description": graph.description,
                "created_at": graph.created_at,
                "updated_at": graph.updated_at,
                "versions": list(versions),
            }
        ).data

        return success_response(graph_data)

    def patch(self, request: Request, graph_id) -> Response:
        """Update graph metadata."""
        graph = self.get_object(graph_id, request.user)
        if not graph:
            return error_response(
                code="NOT_FOUND",
                message=f"Graph with id '{graph_id}' not found or you do not have access to it",
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = GraphUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                code="VALIDATION_ERROR",
                message="The request contains invalid fields",
                status=status.HTTP_400_BAD_REQUEST,
                details=[
                    {"field": field, "issue": ", ".join(errors)}
                    for field, errors in serializer.errors.items()
                ],
            )

        if "name" in serializer.validated_data:
            graph.name = serializer.validated_data["name"]
        if "description" in serializer.validated_data:
            graph.description = serializer.validated_data["description"]

        graph.save()

        graph_data = GraphListSerializer(
            {
                "id": graph.id,
                "name": graph.name,
                "description": graph.description,
                "created_at": graph.created_at,
                "updated_at": graph.updated_at,
                "version_count": graph.versions.count(),
                "latest_version": graph.versions.order_by("-version").first().version
                if graph.versions.exists()
                else None,
            }
        ).data

        return success_response(graph_data)

    def delete(self, request: Request, graph_id) -> Response:
        """Delete graph and all versions."""
        graph = self.get_object(graph_id, request.user)
        if not graph:
            return error_response(
                code="NOT_FOUND",
                message=f"Graph with id '{graph_id}' not found or you do not have access to it",
                status=status.HTTP_404_NOT_FOUND,
            )

        graph.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class GraphVersionListCreateView(APIView):
    """List and create graph versions."""

    permission_classes = [IsAuthenticated]

    def get_graph(self, graph_id, user):
        """Get graph or None."""
        try:
            return Graph.objects.get(id=graph_id, owner=user)
        except Graph.DoesNotExist:
            return None

    def get(self, request: Request, graph_id) -> Response:
        """List graph versions."""
        graph = self.get_graph(graph_id, request.user)
        if not graph:
            return error_response(
                code="NOT_FOUND",
                message=f"Graph with id '{graph_id}' not found or you do not have access to it",
                status=status.HTTP_404_NOT_FOUND,
            )

        versions = graph.versions.order_by("-version").values(
            "id", "version", "checksum", "created_at"
        )

        versions_data = GraphVersionSummarySerializer(list(versions), many=True).data
        return success_response(versions_data)

    def post(self, request: Request, graph_id) -> Response:
        """Create a new graph version."""
        graph = self.get_graph(graph_id, request.user)
        if not graph:
            return error_response(
                code="NOT_FOUND",
                message=f"Graph with id '{graph_id}' not found or you do not have access to it",
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = GraphVersionCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                code="VALIDATION_ERROR",
                message="The request contains invalid fields",
                status=status.HTTP_400_BAD_REQUEST,
                details=[
                    {"field": field, "issue": ", ".join(errors)}
                    for field, errors in serializer.errors.items()
                ],
            )

        graph_json = serializer.validated_data["graph_json"]

        # Validate graph structure
        validator = GraphValidator()
        errors = validator.validate(graph_json)
        if errors:
            return error_response(
                code="GRAPH_VALIDATION_ERROR",
                message="Graph validation failed",
                status=status.HTTP_400_BAD_REQUEST,
                details=errors,
            )

        # Get next version number
        latest = graph.versions.order_by("-version").first()
        next_version = (latest.version + 1) if latest else 1

        # Create version
        version = GraphVersion.objects.create(
            graph=graph,
            version=next_version,
            graph_json=graph_json,
        )

        # Update graph timestamp
        graph.save()  # This triggers auto_now on updated_at

        version_data = GraphVersionDetailSerializer(
            {
                "id": version.id,
                "graph_id": version.graph_id,
                "version": version.version,
                "graph_json": version.graph_json,
                "checksum": version.checksum,
                "created_at": version.created_at,
            }
        ).data

        return success_response(version_data, status=status.HTTP_201_CREATED)


class GraphVersionDetailView(APIView):
    """Get a specific graph version."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, graph_id, version_id) -> Response:
        """Get graph version details."""
        try:
            version = GraphVersion.objects.select_related("graph").get(
                id=version_id,
                graph_id=graph_id,
                graph__owner=request.user,
            )
        except GraphVersion.DoesNotExist:
            return error_response(
                code="NOT_FOUND",
                message=f"Graph version with id '{version_id}' not found for graph '{graph_id}'",
                status=status.HTTP_404_NOT_FOUND,
            )

        version_data = GraphVersionDetailSerializer(
            {
                "id": version.id,
                "graph_id": version.graph_id,
                "version": version.version,
                "graph_json": version.graph_json,
                "checksum": version.checksum,
                "created_at": version.created_at,
            }
        ).data

        return success_response(version_data)


class GraphVersionLatestView(APIView):
    """Get the latest graph version."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, graph_id) -> Response:
        """Get latest graph version."""
        try:
            graph = Graph.objects.get(id=graph_id, owner=request.user)
        except Graph.DoesNotExist:
            return error_response(
                code="NOT_FOUND",
                message=f"Graph with id '{graph_id}' not found or you do not have access to it",
                status=status.HTTP_404_NOT_FOUND,
            )

        version = graph.versions.order_by("-version").first()
        if not version:
            return error_response(
                code="NOT_FOUND",
                message=f"No versions found for graph '{graph_id}'",
                status=status.HTTP_404_NOT_FOUND,
            )

        version_data = GraphVersionDetailSerializer(
            {
                "id": version.id,
                "graph_id": version.graph_id,
                "version": version.version,
                "graph_json": version.graph_json,
                "checksum": version.checksum,
                "created_at": version.created_at,
            }
        ).data

        return success_response(version_data)


class GraphMemoryConfigView(APIView):
    """Get or update memory configuration for a graph."""

    permission_classes = [IsAuthenticated]

    def get_object(self, graph_id, user):
        try:
            return Graph.objects.get(id=graph_id, owner=user)
        except Graph.DoesNotExist:
            return None

    def get_or_create_config(self, graph, user):
        if hasattr(graph, "memory_config") and graph.memory_config:
            return graph.memory_config

        default_config = MemoryConfiguration.objects.filter(user=user).first()
        if default_config:
            return MemoryConfiguration.objects.create(
                graph=graph,
                buffer_enabled=default_config.buffer_enabled,
                buffer_size=default_config.buffer_size,
                auto_prepend=default_config.auto_prepend,
                redis_enabled=default_config.redis_enabled,
                redis_summary_ttl=default_config.redis_summary_ttl,
                redis_facts_ttl=default_config.redis_facts_ttl,
                vector_enabled=default_config.vector_enabled,
                vector_top_k=default_config.vector_top_k,
                vector_threshold=default_config.vector_threshold,
            )

        return MemoryConfiguration.objects.create(graph=graph)

    def get(self, request: Request, graph_id) -> Response:
        graph = self.get_object(graph_id, request.user)
        if not graph:
            return error_response(
                code="NOT_FOUND",
                message=f"Graph with id '{graph_id}' not found or you do not have access to it",
                status=status.HTTP_404_NOT_FOUND,
            )

        config = self.get_or_create_config(graph, request.user)
        data = MemoryConfigurationSerializer(config).data
        return success_response(data)

    def patch(self, request: Request, graph_id) -> Response:
        graph = self.get_object(graph_id, request.user)
        if not graph:
            return error_response(
                code="NOT_FOUND",
                message=f"Graph with id '{graph_id}' not found or you do not have access to it",
                status=status.HTTP_404_NOT_FOUND,
            )

        config = self.get_or_create_config(graph, request.user)
        serializer = MemoryConfigurationSerializer(config, data=request.data, partial=True)
        if not serializer.is_valid():
            return error_response(
                code="VALIDATION_ERROR",
                message="The request contains invalid fields",
                status=status.HTTP_400_BAD_REQUEST,
                details=[
                    {"field": field, "issue": ", ".join(errors)}
                    for field, errors in serializer.errors.items()
                ],
            )

        serializer.save()
        return success_response(serializer.data)

class GraphValidateView(APIView):
    """Validate a graph JSON without saving it."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        """
        Validate a graph JSON structure.

        Request body:
            graph_json: dict - The graph to validate
            strict: bool (optional) - Enable strict config validation

        Response:
            valid: bool - Whether the graph is valid (no errors)
            errors: list - Validation errors
            warnings: list - Validation warnings
        """
        graph_json = request.data.get("graph_json")
        strict = request.data.get("strict", False)

        if not graph_json:
            return error_response(
                code="VALIDATION_ERROR",
                message="Missing 'graph_json' in request body",
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not isinstance(graph_json, dict):
            return error_response(
                code="VALIDATION_ERROR",
                message="'graph_json' must be an object",
                status=status.HTTP_400_BAD_REQUEST,
            )

        validator = GraphValidator()

        try:
            all_issues = validator.validate(graph_json, strict=strict)
        except Exception as e:
            return error_response(
                code="GRAPH_VALIDATION_ERROR",
                message=str(e),
                status=status.HTTP_400_BAD_REQUEST,
                details=getattr(e, "errors", []),
            )

        # Separate errors from warnings
        errors = [
            issue for issue in all_issues
            if issue.get("severity") != "warning"
        ]
        warnings = [
            issue for issue in all_issues
            if issue.get("severity") == "warning"
        ]

        return success_response({
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        })
