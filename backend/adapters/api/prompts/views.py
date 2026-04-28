"""
Prompts API views.

Clean Architecture: Interface Adapters layer.
"""

from typing import cast
from uuid import UUID

from django.db.models import Q
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.prompts.serializers import (
    PromptCreateSerializer,
    PromptDetailSerializer,
    PromptListSerializer,
    PromptPublishSerializer,
    PromptUpdateSerializer,
)
from adapters.api.responses import error_response, success_response
from application.services.rbac import has_min_role
from infrastructure.orm.models import PromptTemplate, User


def _prompt_organization_filter(user: User) -> Q:
    if not user.default_organization_id:
        return Q(pk__isnull=True)
    return Q(organization_id=user.default_organization_id) | Q(
        organization__isnull=True,
        owner__default_organization_id=user.default_organization_id,
    )


class PromptListCreateView(APIView):
    """List and create prompts."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        """List prompts (user's + public built-in)."""
        # Get filter params
        category = request.query_params.get("category")
        ownership = request.query_params.get("ownership", "all")  # all, mine, builtin
        search = request.query_params.get("search")

        user = cast(User, request.user)
        prompts = PromptTemplate.objects.for_user(user)

        # Apply filters
        if category:
            prompts = prompts.filter(category=category)

        if ownership == "mine":
            prompts = prompts.filter(owner=user)
        elif ownership == "builtin":
            prompts = prompts.filter(owner__isnull=True)

        if search:
            prompts = prompts.filter(Q(title__icontains=search) | Q(description__icontains=search))

        prompts = prompts.order_by("-created_at")

        result = []
        for prompt in prompts:
            result.append(
                {
                    "id": prompt.id,
                    "title": prompt.title,
                    "description": prompt.description,
                    "category": prompt.category,
                    "visibility": prompt.visibility,
                    "is_builtin": prompt.owner is None,
                    "created_at": prompt.created_at,
                }
            )

        serialized_data = PromptListSerializer(result, many=True).data
        return success_response(serialized_data)

    def post(self, request: Request) -> Response:
        """Create a new prompt."""
        serializer = PromptCreateSerializer(data=request.data)

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
                message="You don't have permission to create prompts in this organization.",
                status=status.HTTP_403_FORBIDDEN,
            )
        prompt = PromptTemplate.objects.create(
            owner=user,
            organization=user.default_organization,
            title=serializer.validated_data["title"],
            description=serializer.validated_data.get("description", ""),
            category=serializer.validated_data["category"],
            content=serializer.validated_data["content"],
            variables_schema=serializer.validated_data.get("variables_schema", {}),
            visibility="private",
        )

        prompt_data = PromptDetailSerializer(
            {
                "id": prompt.id,
                "owner_id": prompt.owner_id,
                "title": prompt.title,
                "description": prompt.description,
                "category": prompt.category,
                "content": prompt.content,
                "variables_schema": prompt.variables_schema,
                "version": prompt.version,
                "license": prompt.license,
                "visibility": prompt.visibility,
                "is_builtin": False,
                "created_at": prompt.created_at,
                "updated_at": prompt.updated_at,
            }
        ).data

        return success_response(prompt_data, status=status.HTTP_201_CREATED)


class PromptDetailView(APIView):
    """Get, update, delete a prompt."""

    permission_classes = [IsAuthenticated]

    def get_object(self, prompt_id: UUID, user: User) -> PromptTemplate | None:
        """Get prompt if user has access."""
        return cast(
            PromptTemplate | None,
            PromptTemplate.objects.for_user(user).filter(id=prompt_id).first(),
        )

    def get(self, request: Request, prompt_id: UUID) -> Response:
        """Get prompt details."""
        prompt = self.get_object(prompt_id, cast(User, request.user))
        if not prompt:
            return error_response(
                code="NOT_FOUND",
                message=f"Prompt with id '{prompt_id}' not found or you do not have access to it",
                status=status.HTTP_404_NOT_FOUND,
            )

        prompt_data = PromptDetailSerializer(
            {
                "id": prompt.id,
                "owner_id": prompt.owner_id,
                "title": prompt.title,
                "description": prompt.description,
                "category": prompt.category,
                "content": prompt.content,
                "variables_schema": prompt.variables_schema,
                "version": prompt.version,
                "license": prompt.license,
                "visibility": prompt.visibility,
                "is_builtin": prompt.owner is None,
                "created_at": prompt.created_at,
                "updated_at": prompt.updated_at,
            }
        ).data

        return success_response(prompt_data)

    def patch(self, request: Request, prompt_id: UUID) -> Response:
        """Update prompt (owner only)."""
        user = cast(User, request.user)
        if not has_min_role(user, "member"):
            return error_response(
                code="FORBIDDEN",
                message="You don't have permission to update prompts in this organization.",
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            prompt = PromptTemplate.objects.get(
                _prompt_organization_filter(user),
                id=prompt_id,
            )
        except PromptTemplate.DoesNotExist:
            return error_response(
                code="NOT_FOUND",
                message=f"Prompt with id '{prompt_id}' not found or you do not have permission to edit it",
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = PromptUpdateSerializer(data=request.data)
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

        if "title" in serializer.validated_data:
            prompt.title = serializer.validated_data["title"]
        if "description" in serializer.validated_data:
            prompt.description = serializer.validated_data["description"]
        if "content" in serializer.validated_data:
            prompt.content = serializer.validated_data["content"]
        if "variables_schema" in serializer.validated_data:
            prompt.variables_schema = serializer.validated_data["variables_schema"]

        prompt.save()

        prompt_data = PromptDetailSerializer(
            {
                "id": prompt.id,
                "owner_id": prompt.owner_id,
                "title": prompt.title,
                "description": prompt.description,
                "category": prompt.category,
                "content": prompt.content,
                "variables_schema": prompt.variables_schema,
                "version": prompt.version,
                "license": prompt.license,
                "visibility": prompt.visibility,
                "is_builtin": False,
                "created_at": prompt.created_at,
                "updated_at": prompt.updated_at,
            }
        ).data

        return success_response(prompt_data)

    def delete(self, request: Request, prompt_id: UUID) -> Response:
        """Delete prompt (owner only, not built-in)."""
        user = cast(User, request.user)
        if not has_min_role(user, "member"):
            return error_response(
                code="FORBIDDEN",
                message="You don't have permission to delete prompts in this organization.",
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            prompt = PromptTemplate.objects.get(
                _prompt_organization_filter(user),
                id=prompt_id,
            )
        except PromptTemplate.DoesNotExist:
            return error_response(
                code="NOT_FOUND",
                message=f"Prompt with id '{prompt_id}' not found or you do not have permission to delete it",
                status=status.HTTP_404_NOT_FOUND,
            )

        prompt.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PromptCloneView(APIView):
    """Clone a prompt to user's library."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request, prompt_id: UUID) -> Response:
        """Clone a prompt."""
        try:
            user = cast(User, request.user)
            original = PromptTemplate.objects.for_user(user).get(id=prompt_id)
        except PromptTemplate.DoesNotExist:
            return error_response(
                code="NOT_FOUND",
                message=f"Prompt with id '{prompt_id}' not found",
                status=status.HTTP_404_NOT_FOUND,
            )

        clone = original.clone_for_user(cast(User, request.user))

        clone_data = PromptDetailSerializer(
            {
                "id": clone.id,
                "owner_id": clone.owner_id,
                "title": clone.title,
                "description": clone.description,
                "category": clone.category,
                "content": clone.content,
                "variables_schema": clone.variables_schema,
                "version": clone.version,
                "license": clone.license,
                "visibility": clone.visibility,
                "is_builtin": False,
                "created_at": clone.created_at,
                "updated_at": clone.updated_at,
            }
        ).data

        return success_response(clone_data, status=status.HTTP_201_CREATED)


class PromptPublishView(APIView):
    """Publish a prompt (make public)."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request, prompt_id: UUID) -> Response:
        """Publish a prompt."""
        user = cast(User, request.user)
        if not has_min_role(user, "admin"):
            return error_response(
                code="FORBIDDEN",
                message="You don't have permission to publish prompts in this organization.",
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            prompt = PromptTemplate.objects.get(
                _prompt_organization_filter(user),
                id=prompt_id,
            )
        except PromptTemplate.DoesNotExist:
            return error_response(
                code="NOT_FOUND",
                message=f"Prompt with id '{prompt_id}' not found or you do not have permission to publish it",
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = PromptPublishSerializer(data=request.data)
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

        prompt.visibility = "public"
        prompt.license = serializer.validated_data.get("license", "MIT")
        prompt.save()

        prompt_data = PromptDetailSerializer(
            {
                "id": prompt.id,
                "owner_id": prompt.owner_id,
                "title": prompt.title,
                "description": prompt.description,
                "category": prompt.category,
                "content": prompt.content,
                "variables_schema": prompt.variables_schema,
                "version": prompt.version,
                "license": prompt.license,
                "visibility": prompt.visibility,
                "is_builtin": False,
                "created_at": prompt.created_at,
                "updated_at": prompt.updated_at,
            }
        ).data

        return success_response(prompt_data)
