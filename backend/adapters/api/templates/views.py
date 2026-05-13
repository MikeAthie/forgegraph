"""
Template API views.

Provides listing and cloning of built-in graph templates.
"""

from __future__ import annotations

import copy
from typing import Any, cast
from uuid import UUID

from django.db import models
from django.db.models import Avg, Count, Q
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.responses import error_response, success_response
from adapters.api.templates.serializers import (
    TemplateCloneSerializer,
    TemplateListSerializer,
    TemplateRatingSerializer,
    TemplateShareSerializer,
    TemplateVersionCreateSerializer,
)
from application.services.audit_log import record_audit_log
from application.services.rbac import has_min_role
from infrastructure.orm.models import (
    APIKey,
    Graph,
    GraphTemplate,
    GraphVersion,
    MemoryConfiguration,
    Organization,
    TemplateRating,
    TemplateShare,
    TemplateUsage,
    User,
)


def _apply_prompt_overrides(
    graph_json: dict[str, Any],
    provider: str | None,
    model: str | None,
    credential_id: UUID | None,
) -> dict[str, Any]:
    data = copy.deepcopy(graph_json)
    nodes = data.get("nodes")
    if isinstance(nodes, list):
        _apply_prompt_overrides_to_nodes(nodes, provider, model, credential_id)
    return data


def _apply_prompt_overrides_to_nodes(
    nodes: list[dict[str, Any]],
    provider: str | None,
    model: str | None,
    credential_id: UUID | None,
) -> None:
    for node in nodes:
        if not isinstance(node, dict):
            continue
        raw_config = node.get("config")
        config: dict[str, Any] = raw_config if isinstance(raw_config, dict) else {}
        if node.get("type") == "prompt":
            _apply_prompt_config_overrides(config, provider, model, credential_id)
            node["config"] = config
            continue

        if node.get("type") != "subgraph" or not isinstance(config.get("graph_json"), dict):
            continue
        subgraph_json = cast(dict[str, Any], config["graph_json"])
        sub_nodes = subgraph_json.get("nodes")
        if isinstance(sub_nodes, list):
            _apply_prompt_overrides_to_nodes(sub_nodes, provider, model, credential_id)
        config["graph_json"] = subgraph_json
        node["config"] = config


def _apply_prompt_config_overrides(
    config: dict[str, Any],
    provider: str | None,
    model: str | None,
    credential_id: UUID | None,
) -> None:
    if provider:
        config["provider"] = provider
    if model:
        config["model"] = model
    if credential_id:
        config["credential_id"] = str(credential_id)


def _template_queryset_for_user(user: User) -> models.QuerySet[GraphTemplate]:
    org = user.default_organization
    if org is None:
        return GraphTemplate.objects.none()

    shared_ids = TemplateShare.objects.filter(organization=org).values_list(
        "template_id", flat=True
    )
    return GraphTemplate.objects.filter(is_active=True, is_latest=True).filter(
        Q(visibility="public") | Q(owner_organization=org) | Q(id__in=shared_ids)
    )


def _get_template_for_user(template_id: UUID, user: User) -> GraphTemplate | None:
    org = user.default_organization
    if org is None:
        return None

    shared_ids = TemplateShare.objects.filter(organization=org).values_list(
        "template_id", flat=True
    )
    return (
        GraphTemplate.objects.filter(is_active=True)
        .filter(Q(visibility="public") | Q(owner_organization=org) | Q(id__in=shared_ids))
        .filter(id=template_id)
        .first()
    )


class TemplateListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        templates = (
            _template_queryset_for_user(user)
            .annotate(
                rating_average=Avg("ratings__rating"),
                rating_count=Count("ratings", distinct=True),
                usage_count=Count("usage_events", distinct=True),
                run_total=Count("usage_events__graph__versions__runs", distinct=True),
                run_succeeded=Count(
                    "usage_events__graph__versions__runs",
                    filter=Q(usage_events__graph__versions__runs__status="succeeded"),
                    distinct=True,
                ),
            )
            .order_by("display_order", "name")
        )
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

        template = _get_template_for_user(template_id, cast(User, request.user))
        if template is None:
            return error_response(
                code="NOT_FOUND",
                message=f"Template with id '{template_id}' not found",
                status=status.HTTP_404_NOT_FOUND,
            )

        user = cast(User, request.user)
        if not has_min_role(user, "member"):
            return error_response(
                code="FORBIDDEN",
                message="You don't have permission to create graphs in this organization.",
                status=status.HTTP_403_FORBIDDEN,
            )

        provider = (serializer.validated_data.get("provider") or "").strip().lower() or None
        model = (serializer.validated_data.get("model") or "").strip() or None
        credential_id = serializer.validated_data.get("credential_id")

        if credential_id:
            credential_exists = APIKey.objects.filter(
                id=credential_id, organization=user.default_organization
            ).exists()
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

        if user.default_organization:
            TemplateUsage.objects.create(
                template=template,
                organization=user.default_organization,
                user=user,
                graph=graph,
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


class TemplateVersionsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, template_id: UUID) -> Response:
        user = cast(User, request.user)
        template = _get_template_for_user(template_id, user)
        if template is None:
            return error_response(
                code="NOT_FOUND",
                message=f"Template with id '{template_id}' not found",
                status=status.HTTP_404_NOT_FOUND,
            )

        versions = (
            GraphTemplate.objects.filter(group_id=template.group_id, is_active=True)
            .annotate(
                rating_average=Avg("ratings__rating"),
                rating_count=Count("ratings", distinct=True),
                usage_count=Count("usage_events", distinct=True),
                run_total=Count("usage_events__graph__versions__runs", distinct=True),
                run_succeeded=Count(
                    "usage_events__graph__versions__runs",
                    filter=Q(usage_events__graph__versions__runs__status="succeeded"),
                    distinct=True,
                ),
            )
            .order_by("-version")
        )
        data = TemplateListSerializer(versions, many=True).data
        return success_response(data)

    def post(self, request: Request, template_id: UUID) -> Response:
        serializer = TemplateVersionCreateSerializer(data=request.data)
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
        if not has_min_role(user, "admin"):
            return error_response(
                code="FORBIDDEN",
                message="You don't have permission to version templates in this organization.",
                status=status.HTTP_403_FORBIDDEN,
            )

        org = user.default_organization
        if org is None:
            return error_response(
                code="FORBIDDEN",
                message="No organization found for this user.",
                status=status.HTTP_403_FORBIDDEN,
            )

        template = GraphTemplate.objects.filter(
            id=template_id,
            owner_organization=org,
            is_active=True,
        ).first()
        if template is None:
            return error_response(
                code="NOT_FOUND",
                message=f"Template with id '{template_id}' not found",
                status=status.HTTP_404_NOT_FOUND,
            )

        latest = (
            GraphTemplate.objects.filter(group_id=template.group_id).order_by("-version").first()
        )
        next_version = (latest.version if latest else template.version) + 1

        payload = serializer.validated_data
        visibility = str(payload.get("visibility") or template.visibility)
        if visibility not in {"public", "organization", "private"}:
            return error_response(
                code="VALIDATION_ERROR",
                message="Invalid visibility value.",
                status=status.HTTP_400_BAD_REQUEST,
            )

        GraphTemplate.objects.filter(group_id=template.group_id, is_latest=True).update(
            is_latest=False
        )

        new_template = GraphTemplate.objects.create(
            group_id=template.group_id,
            name=payload["name"] if "name" in payload else template.name,
            description=payload["description"]
            if "description" in payload
            else template.description,
            category=payload["category"] if "category" in payload else template.category,
            tags=payload["tags"] if "tags" in payload else template.tags,
            estimated_minutes=payload["estimated_minutes"]
            if "estimated_minutes" in payload
            else template.estimated_minutes,
            graph_json=payload["graph_json"] if "graph_json" in payload else template.graph_json,
            sample_input=payload["sample_input"]
            if "sample_input" in payload
            else template.sample_input,
            guide_steps=payload["guide_steps"]
            if "guide_steps" in payload
            else template.guide_steps,
            version=next_version,
            changelog=payload["changelog"] if "changelog" in payload else "",
            is_latest=True,
            visibility=visibility,
            owner_organization=template.owner_organization,
            display_order=template.display_order,
            is_active=template.is_active,
        )

        annotated = (
            GraphTemplate.objects.filter(id=new_template.id)
            .annotate(
                rating_average=Avg("ratings__rating"),
                rating_count=Count("ratings", distinct=True),
                usage_count=Count("usage_events", distinct=True),
                run_total=Count("usage_events__graph__versions__runs", distinct=True),
                run_succeeded=Count(
                    "usage_events__graph__versions__runs",
                    filter=Q(usage_events__graph__versions__runs__status="succeeded"),
                    distinct=True,
                ),
            )
            .first()
        )
        data = (
            TemplateListSerializer(annotated).data
            if annotated
            else TemplateListSerializer(new_template).data
        )
        return success_response(data, status=status.HTTP_201_CREATED)


class TemplateRatingView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, template_id: UUID) -> Response:
        serializer = TemplateRatingSerializer(data=request.data)
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
        org = user.default_organization
        if org is None:
            return error_response(
                code="FORBIDDEN",
                message="No organization found for this user.",
                status=status.HTTP_403_FORBIDDEN,
            )

        template = _get_template_for_user(template_id, user)
        if template is None:
            return error_response(
                code="NOT_FOUND",
                message=f"Template with id '{template_id}' not found",
                status=status.HTTP_404_NOT_FOUND,
            )

        rating = int(serializer.validated_data["rating"])
        comment = serializer.validated_data.get("comment") or ""

        TemplateRating.objects.update_or_create(
            template=template,
            user=user,
            defaults={
                "organization": org,
                "rating": rating,
                "comment": comment,
            },
        )

        return success_response({"template_id": str(template.id), "rating": rating})


class TemplateShareView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, template_id: UUID) -> Response:
        serializer = TemplateShareSerializer(data=request.data)
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
        if not has_min_role(user, "admin"):
            return error_response(
                code="FORBIDDEN",
                message="You don't have permission to share templates in this organization.",
                status=status.HTTP_403_FORBIDDEN,
            )

        org = user.default_organization
        if org is None:
            return error_response(
                code="FORBIDDEN",
                message="No organization found for this user.",
                status=status.HTTP_403_FORBIDDEN,
            )

        template = GraphTemplate.objects.filter(
            id=template_id,
            owner_organization=org,
            is_active=True,
        ).first()
        if template is None:
            return error_response(
                code="NOT_FOUND",
                message=f"Template with id '{template_id}' not found",
                status=status.HTTP_404_NOT_FOUND,
            )

        target_org_id = serializer.validated_data["organization_id"]
        try:
            target_org = Organization.objects.get(id=target_org_id)
        except Organization.DoesNotExist:
            return error_response(
                code="NOT_FOUND",
                message=f"Organization with id '{target_org_id}' not found",
                status=status.HTTP_404_NOT_FOUND,
            )

        share, _ = TemplateShare.objects.get_or_create(
            template=template,
            organization=target_org,
            defaults={"shared_by": user},
        )

        record_audit_log(
            actor=user,
            tenant_id=str(org.id),
            action="template.shared",
            resource_type="graph_template",
            resource_id=str(template.id),
            metadata={
                "shared_with_organization_id": str(target_org.id),
                "template_group_id": str(template.group_id),
            },
        )

        return success_response(
            {
                "template_id": str(template.id),
                "organization_id": str(share.organization_id),
            }
        )

    def delete(self, request: Request, template_id: UUID, organization_id: UUID) -> Response:
        user = cast(User, request.user)
        if not has_min_role(user, "admin"):
            return error_response(
                code="FORBIDDEN",
                message="You don't have permission to unshare templates in this organization.",
                status=status.HTTP_403_FORBIDDEN,
            )

        org = user.default_organization
        if org is None:
            return error_response(
                code="FORBIDDEN",
                message="No organization found for this user.",
                status=status.HTTP_403_FORBIDDEN,
            )

        deleted, _ = TemplateShare.objects.filter(
            template_id=template_id,
            organization_id=organization_id,
            template__owner_organization=org,
        ).delete()

        if not deleted:
            return error_response(
                code="NOT_FOUND",
                message="Share record not found.",
                status=status.HTTP_404_NOT_FOUND,
            )

        record_audit_log(
            actor=user,
            tenant_id=str(org.id),
            action="template.unshared",
            resource_type="graph_template",
            resource_id=str(template_id),
            metadata={
                "unshared_organization_id": str(organization_id),
            },
        )

        return success_response({"deleted": True})
