"""
Graphs API views.

Clean Architecture: Interface Adapters layer.
"""

import hashlib
import json
from typing import Any, cast
from uuid import UUID

from django.db import IntegrityError, transaction
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
)
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.graphs.serializers import (
    ExternalWorkflowCreateResponseSerializer,
    ExternalWorkflowCreateSerializer,
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
from application.services.rbac import has_min_role
from domain.services.graph_validator import GraphValidator
from infrastructure.orm.models import Graph, GraphVersion, MemoryConfiguration, User


def _create_graph_memory_config(graph: Graph, user: User) -> None:
    default_config = MemoryConfiguration.objects.filter(user=user).first()
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
            vector_recency_weight=default_config.vector_recency_weight,
            embedding_model=default_config.embedding_model,
        )
    else:
        MemoryConfiguration.objects.create(graph=graph)


def _graph_checksum(graph_json: dict[str, Any]) -> str:
    json_str = json.dumps(graph_json, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(json_str.encode()).hexdigest()


def _external_workflow_response_payload(
    *,
    graph: Graph,
    version: GraphVersion,
    external_source: str,
    external_ref: str,
    idempotency_key: str,
    created_graph: bool,
    created_version: bool,
    idempotent_replay: bool,
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        ExternalWorkflowCreateResponseSerializer(
            {
                "graph_id": graph.id,
                "graph_version_id": version.id,
                "graph_name": graph.name,
                "graph_description": graph.description,
                "graph_version": version.version,
                "checksum": version.checksum,
                "external_source": external_source,
                "external_ref": external_ref,
                "idempotency_key": idempotency_key,
                "created_graph": created_graph,
                "created_version": created_version,
                "idempotent_replay": idempotent_replay,
                "warnings": warnings,
            }
        ).data,
    )


class GraphListCreateView(APIView):
    """List and create graphs."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        """List user's graphs."""
        user = cast(User, request.user)
        graphs = Graph.objects.for_user(user).order_by("-updated_at")

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

        user = cast(User, request.user)
        if not has_min_role(user, "member"):
            return error_response(
                code="FORBIDDEN",
                message="You don't have permission to create graphs in this organization.",
                status=status.HTTP_403_FORBIDDEN,
            )
        graph = Graph.objects.create(
            owner=user,
            name=serializer.validated_data["name"],
            description=serializer.validated_data.get("description", ""),
        )
        _create_graph_memory_config(graph, user)

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

    def get_object(self, graph_id: UUID, user: User) -> Graph | None:
        """Get graph or raise 404."""
        try:
            return cast(Graph, Graph.objects.for_user(user).get(id=graph_id))
        except Graph.DoesNotExist:
            return None

    def get(self, request: Request, graph_id: UUID) -> Response:
        """Get graph details with versions."""
        graph = self.get_object(graph_id, cast(User, request.user))
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

    def patch(self, request: Request, graph_id: UUID) -> Response:
        """Update graph metadata."""
        user = cast(User, request.user)
        if not has_min_role(user, "member"):
            return error_response(
                code="FORBIDDEN",
                message="You don't have permission to update graphs in this organization.",
                status=status.HTTP_403_FORBIDDEN,
            )
        graph = self.get_object(graph_id, user)
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

        latest_version = graph.versions.order_by("-version").first()
        graph_data = GraphListSerializer(
            {
                "id": graph.id,
                "name": graph.name,
                "description": graph.description,
                "created_at": graph.created_at,
                "updated_at": graph.updated_at,
                "version_count": graph.versions.count(),
                "latest_version": latest_version.version if latest_version else None,
            }
        ).data

        return success_response(graph_data)

    def delete(self, request: Request, graph_id: UUID) -> Response:
        """Delete graph and all versions."""
        user = cast(User, request.user)
        if not has_min_role(user, "member"):
            return error_response(
                code="FORBIDDEN",
                message="You don't have permission to delete graphs in this organization.",
                status=status.HTTP_403_FORBIDDEN,
            )
        graph = self.get_object(graph_id, user)
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

    def get_graph(self, graph_id: UUID, user: User) -> Graph | None:
        """Get graph or None."""
        try:
            return cast(Graph, Graph.objects.for_user(user).get(id=graph_id))
        except Graph.DoesNotExist:
            return None

    def get(self, request: Request, graph_id: UUID) -> Response:
        """List graph versions."""
        graph = self.get_graph(graph_id, cast(User, request.user))
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

    def post(self, request: Request, graph_id: UUID) -> Response:
        """Create a new graph version."""
        user = cast(User, request.user)
        if not has_min_role(user, "member"):
            return error_response(
                code="FORBIDDEN",
                message="You don't have permission to create graph versions in this organization.",
                status=status.HTTP_403_FORBIDDEN,
            )
        graph = self.get_graph(graph_id, user)
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
        issues = validator.validate(graph_json, require_entry_exit=False)
        errors = [issue for issue in issues if issue.get("severity") != "warning"]
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

    def get(self, request: Request, graph_id: UUID, version_id: UUID) -> Response:
        """Get graph version details."""
        user = cast(User, request.user)
        try:
            version = GraphVersion.objects.select_related("graph").get(
                id=version_id,
                graph_id=graph_id,
                graph__owner__default_organization_id=user.default_organization_id,
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


class ExternalWorkflowCreateView(APIView):
    """Create a workflow from external clients in one request."""

    permission_classes = [IsAuthenticated]

    def _find_idempotent_version(
        self,
        *,
        user: User,
        external_source: str,
        external_ref: str,
        idempotency_key: str,
    ) -> GraphVersion | None:
        if not idempotency_key:
            return None

        versions = GraphVersion.objects.select_related("graph").filter(
            graph__owner_id=user.id,
            graph__external_source=external_source,
            external_idempotency_key=idempotency_key,
        )
        if external_ref:
            versions = versions.filter(graph__external_ref=external_ref)
        return cast(GraphVersion | None, versions.order_by("-created_at").first())

    @extend_schema(
        tags=["graphs"],
        operation_id="graphs_external_workflow_create",
        summary="Create external workflow",
        description=(
            "Create or update a workflow from an external system. "
            "Use `external_ref` to keep importing into the same graph, and "
            "`idempotency_key` (or `Idempotency-Key` header) to safely retry."
        ),
        request=ExternalWorkflowCreateSerializer,
        parameters=[
            OpenApiParameter(
                name="Idempotency-Key",
                location=OpenApiParameter.HEADER,
                required=False,
                type=str,
                description=(
                    "Optional idempotency key for retry-safe imports. "
                    "Used when body `idempotency_key` is omitted."
                ),
            )
        ],
        responses={
            200: OpenApiResponse(
                response=ExternalWorkflowCreateResponseSerializer,
                description="Existing graph/version reused.",
            ),
            201: OpenApiResponse(
                response=ExternalWorkflowCreateResponseSerializer,
                description="Graph and/or version created.",
            ),
            400: OpenApiResponse(description="Validation error"),
            403: OpenApiResponse(description="Forbidden"),
        },
        examples=[
            OpenApiExample(
                "Create Or Update Workflow",
                request_only=True,
                value={
                    "name": "QA Lead Capture",
                    "description": "Imported from qa-seed",
                    "external_source": "qa",
                    "external_ref": "qa-workflow-001",
                    "idempotency_key": "qa-workflow-001:v3",
                    "strict": False,
                    "require_entry_exit": True,
                    "graph_json": {
                        "nodes": [
                            {"id": "prompt1", "type": "prompt", "name": "Prompt", "config": {}},
                            {"id": "out1", "type": "output", "name": "Output", "config": {}},
                        ],
                        "edges": [
                            {"id": "e1", "from": "START", "to": "prompt1"},
                            {"id": "e2", "from": "prompt1", "to": "out1"},
                        ],
                    },
                },
            ),
            OpenApiExample(
                "Idempotent Replay Response",
                response_only=True,
                status_codes=["200"],
                value={
                    "data": {
                        "graph_id": "2e6876db-3436-4f77-9670-9873bc89e495",
                        "graph_version_id": "03cd36f8-c4b4-4fd6-99d6-c04955af7f74",
                        "graph_name": "QA Lead Capture",
                        "graph_description": "Imported from qa-seed",
                        "graph_version": 3,
                        "checksum": "a72f97f3f5a4eb9af2f4a289d39cd43c4f68e82f9f65ae3a6a0e97a0de7ea1fe",
                        "external_source": "qa",
                        "external_ref": "qa-workflow-001",
                        "idempotency_key": "qa-workflow-001:v3",
                        "created_graph": False,
                        "created_version": False,
                        "idempotent_replay": True,
                        "warnings": [],
                    }
                },
            ),
        ],
    )
    def post(self, request: Request) -> Response:
        user = cast(User, request.user)
        if not has_min_role(user, "member"):
            return error_response(
                code="FORBIDDEN",
                message="You don't have permission to create workflows in this organization.",
                status=status.HTTP_403_FORBIDDEN,
            )

        request_data: dict[str, Any] = dict(request.data) if isinstance(request.data, dict) else {}
        header_idempotency_key = (request.headers.get("Idempotency-Key") or "").strip()
        if header_idempotency_key and not request_data.get("idempotency_key"):
            request_data["idempotency_key"] = header_idempotency_key

        serializer = ExternalWorkflowCreateSerializer(data=request_data)
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

        name = serializer.validated_data["name"]
        description = serializer.validated_data.get("description", "")
        graph_json = serializer.validated_data["graph_json"]
        external_source = serializer.validated_data["external_source"]
        external_ref = serializer.validated_data.get("external_ref", "")
        idempotency_key = serializer.validated_data.get("idempotency_key", "")
        strict = serializer.validated_data["strict"]
        require_entry_exit = serializer.validated_data["require_entry_exit"]

        replay_version = self._find_idempotent_version(
            user=user,
            external_source=external_source,
            external_ref=external_ref,
            idempotency_key=idempotency_key,
        )
        if replay_version is not None:
            payload = _external_workflow_response_payload(
                graph=replay_version.graph,
                version=replay_version,
                external_source=external_source,
                external_ref=external_ref,
                idempotency_key=idempotency_key,
                created_graph=False,
                created_version=False,
                idempotent_replay=True,
                warnings=[],
            )
            return success_response(payload)

        validator = GraphValidator()
        try:
            issues = validator.validate(
                graph_json,
                strict=strict,
                require_entry_exit=require_entry_exit,
            )
        except Exception as e:
            return error_response(
                code="GRAPH_VALIDATION_ERROR",
                message=str(e),
                status=status.HTTP_400_BAD_REQUEST,
                details=getattr(e, "errors", []),
            )

        errors = [issue for issue in issues if issue.get("severity") != "warning"]
        warnings = [issue for issue in issues if issue.get("severity") == "warning"]
        if errors:
            return error_response(
                code="GRAPH_VALIDATION_ERROR",
                message="Graph validation failed",
                status=status.HTTP_400_BAD_REQUEST,
                details=errors,
            )

        incoming_checksum = _graph_checksum(graph_json)
        try:
            with transaction.atomic():
                created_graph = False
                created_version = False

                if external_ref:
                    graph = (
                        Graph.objects.select_for_update()
                        .filter(owner=user)
                        .filter(external_source=external_source, external_ref=external_ref)
                        .first()
                    )
                    if graph is None:
                        graph = Graph.objects.create(
                            owner=user,
                            name=name,
                            description=description,
                            external_source=external_source,
                            external_ref=external_ref,
                        )
                        _create_graph_memory_config(graph, user)
                        created_graph = True
                    else:
                        graph_update_fields: list[str] = []
                        if graph.name != name:
                            graph.name = name
                            graph_update_fields.append("name")
                        if graph.description != description:
                            graph.description = description
                            graph_update_fields.append("description")
                        if graph_update_fields:
                            graph.save(update_fields=graph_update_fields)
                else:
                    graph = Graph.objects.create(
                        owner=user,
                        name=name,
                        description=description,
                        external_source=external_source,
                    )
                    _create_graph_memory_config(graph, user)
                    created_graph = True

                latest = graph.versions.order_by("-version").first()
                if latest and latest.checksum == incoming_checksum:
                    version = latest
                    if idempotency_key and not version.external_idempotency_key:
                        version.external_idempotency_key = idempotency_key
                        version.save(update_fields=["external_idempotency_key"])
                else:
                    next_version = (latest.version + 1) if latest else 1
                    version = GraphVersion.objects.create(
                        graph=graph,
                        version=next_version,
                        graph_json=graph_json,
                        external_idempotency_key=idempotency_key,
                    )
                    created_version = True
                    if not created_graph:
                        graph.save()  # Trigger updated_at on graph when a new version is added.
        except IntegrityError:
            replay_version = self._find_idempotent_version(
                user=user,
                external_source=external_source,
                external_ref=external_ref,
                idempotency_key=idempotency_key,
            )
            if replay_version is None:
                return error_response(
                    code="CONFLICT",
                    message="External workflow import conflicted with an existing resource.",
                    status=status.HTTP_409_CONFLICT,
                )
            payload = _external_workflow_response_payload(
                graph=replay_version.graph,
                version=replay_version,
                external_source=external_source,
                external_ref=external_ref,
                idempotency_key=idempotency_key,
                created_graph=False,
                created_version=False,
                idempotent_replay=True,
                warnings=[],
            )
            return success_response(payload)

        payload = _external_workflow_response_payload(
            graph=graph,
            version=version,
            external_source=external_source,
            external_ref=external_ref,
            idempotency_key=idempotency_key,
            created_graph=created_graph,
            created_version=created_version,
            idempotent_replay=False,
            warnings=warnings,
        )
        response_status = (
            status.HTTP_201_CREATED if (created_graph or created_version) else status.HTTP_200_OK
        )
        return success_response(payload, status=response_status)


class GraphVersionLatestView(APIView):
    """Get the latest graph version."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, graph_id: UUID) -> Response:
        """Get latest graph version."""
        try:
            graph = Graph.objects.for_user(cast(User, request.user)).get(id=graph_id)
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

    def get_object(self, graph_id: UUID, user: User) -> Graph | None:
        try:
            return cast(Graph, Graph.objects.for_user(user).get(id=graph_id))
        except Graph.DoesNotExist:
            return None

    def get_or_create_config(self, graph: Graph, user: User) -> MemoryConfiguration:
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
                vector_recency_weight=default_config.vector_recency_weight,
                embedding_model=default_config.embedding_model,
            )

        return MemoryConfiguration.objects.create(graph=graph)

    def get(self, request: Request, graph_id: UUID) -> Response:
        user = cast(User, request.user)
        graph = self.get_object(graph_id, user)
        if not graph:
            return error_response(
                code="NOT_FOUND",
                message=f"Graph with id '{graph_id}' not found or you do not have access to it",
                status=status.HTTP_404_NOT_FOUND,
            )

        config = self.get_or_create_config(graph, user)
        data = MemoryConfigurationSerializer(config).data
        return success_response(data)

    def patch(self, request: Request, graph_id: UUID) -> Response:
        user = cast(User, request.user)
        if not has_min_role(user, "member"):
            return error_response(
                code="FORBIDDEN",
                message="You don't have permission to update memory configuration in this organization.",
                status=status.HTTP_403_FORBIDDEN,
            )
        graph = self.get_object(graph_id, user)
        if not graph:
            return error_response(
                code="NOT_FOUND",
                message=f"Graph with id '{graph_id}' not found or you do not have access to it",
                status=status.HTTP_404_NOT_FOUND,
            )

        config = self.get_or_create_config(graph, user)
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
        graph_json: Any = request.data.get("graph_json")
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
        errors = [issue for issue in all_issues if issue.get("severity") != "warning"]
        warnings = [issue for issue in all_issues if issue.get("severity") == "warning"]

        return success_response(
            {
                "valid": len(errors) == 0,
                "errors": errors,
                "warnings": warnings,
            }
        )
