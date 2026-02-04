"""
Template API views.

Provides listing and cloning of built-in graph templates.
"""

from __future__ import annotations

import copy
from typing import Any, cast
from uuid import UUID

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.responses import error_response, success_response
from adapters.api.templates.serializers import TemplateCloneSerializer, TemplateListSerializer
from infrastructure.orm.models import (
    APIKey,
    Graph,
    GraphTemplate,
    GraphVersion,
    MemoryConfiguration,
    User,
)


def _apply_prompt_overrides(
    graph_json: dict[str, Any],
    provider: str | None,
    model: str | None,
    credential_id: UUID | None,
) -> dict[str, Any]:
    data = copy.deepcopy(graph_json)

    def _walk(nodes: list[dict[str, Any]]) -> None:
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_type = node.get("type")
            config = node.get("config")
            if not isinstance(config, dict):
                config = {}

            if node_type == "prompt":
                if provider:
                    config["provider"] = provider
                if model:
                    config["model"] = model
                if credential_id:
                    config["credential_id"] = str(credential_id)
                node["config"] = config
                continue

            if node_type == "subgraph" and isinstance(config.get("graph_json"), dict):
                subgraph_json = config["graph_json"]
                sub_nodes = subgraph_json.get("nodes")
                if isinstance(sub_nodes, list):
                    _walk(sub_nodes)
                config["graph_json"] = subgraph_json
                node["config"] = config

    nodes = data.get("nodes")
    if isinstance(nodes, list):
        _walk(nodes)
    return data


class TemplateListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        templates = GraphTemplate.objects.filter(is_active=True).order_by("display_order", "name")
        data = TemplateListSerializer(templates, many=True).data
        return success_response(data)


class TemplateCloneView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, template_id: UUID) -> Response:
        serializer = TemplateCloneSerializer(data=request.data)
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

        try:
            template = GraphTemplate.objects.get(id=template_id, is_active=True)
        except GraphTemplate.DoesNotExist:
            return error_response(
                code="NOT_FOUND",
                message=f"Template with id '{template_id}' not found",
                status=status.HTTP_404_NOT_FOUND,
            )

        user = cast(User, request.user)

        provider = (serializer.validated_data.get("provider") or "").strip().lower() or None
        model = (serializer.validated_data.get("model") or "").strip() or None
        credential_id = serializer.validated_data.get("credential_id")

        if credential_id:
            credential_exists = APIKey.objects.filter(id=credential_id, user=user).exists()
            if not credential_exists:
                return error_response(
                    code="INVALID_CREDENTIAL",
                    message="Credential not found or not owned by user",
                    status=status.HTTP_400_BAD_REQUEST,
                )

        graph_name = serializer.validated_data.get("name") or f"{template.name} (Copy)"
        graph_description = serializer.validated_data.get("description") or template.description

        graph_json = _apply_prompt_overrides(
            template.graph_json,
            provider=provider,
            model=model,
            credential_id=credential_id,
        )

        graph = Graph.objects.create(
            owner=user,
            name=graph_name,
            description=graph_description,
        )

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

        version = GraphVersion.objects.create(
            graph=graph,
            version=1,
            graph_json=graph_json,
        )

        return success_response(
            {
                "graph_id": str(graph.id),
                "graph_version_id": str(version.id),
                "graph_name": graph.name,
                "template_id": str(template.id),
            },
            status=status.HTTP_201_CREATED,
        )
