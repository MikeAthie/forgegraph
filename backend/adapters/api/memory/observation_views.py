from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.memory.serializers import (
    MemoryObservationContextSerializer,
    MemoryObservationCreateSerializer,
    MemoryObservationDetailSerializer,
    MemoryObservationQuerySerializer,
    MemoryObservationTimelineSerializer,
    MemoryObservationUpdateSerializer,
)
from adapters.api.responses import error_response, success_response
from application.services.memory_observation_service import (
    MemoryObservationService,
    ObservationContext,
)
from application.services.rbac import has_min_role
from application.services.tenancy import get_tenant_id_for_user
from infrastructure.orm.models import MemoryObservation, User


def _observation_payload(observation: MemoryObservation) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        MemoryObservationDetailSerializer(
            {
                "id": observation.id,
                "tenant_id": observation.tenant_id,
                "graph_id": observation.graph_id,
                "run_id": observation.run_id,
                "session_id": observation.session_id,
                "agent_id": observation.agent_id,
                "memory_chunk_id": observation.memory_chunk_id,
                "type": observation.type,
                "title": observation.title,
                "content": observation.content,
                "scope": observation.scope,
                "topic_key": observation.topic_key,
                "tool_name": observation.tool_name,
                "revision_count": observation.revision_count,
                "duplicate_count": observation.duplicate_count,
                "last_seen_at": observation.last_seen_at,
                "created_at": observation.created_at,
                "updated_at": observation.updated_at,
                "deleted_at": observation.deleted_at,
                "is_deleted": observation.deleted_at is not None,
            }
        ).data,
    )


def _observation_list_payload(observations: list[MemoryObservation]) -> list[dict[str, Any]]:
    return [_observation_payload(observation) for observation in observations]


def _validation_error(serializer: object) -> Response:
    serializer_errors = cast(dict[str, list[str]], getattr(serializer, "errors", {}))
    return error_response(
        code="VALIDATION_ERROR",
        message="The request contains invalid fields",
        status=status.HTTP_400_BAD_REQUEST,
        details=[
            {"field": field, "issue": ", ".join(str(error) for error in errors)}
            for field, errors in serializer_errors.items()
        ],
    )


class MemoryObservationListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        user = cast(User, request.user)
        if not has_min_role(user, "member"):
            return error_response(
                code="FORBIDDEN",
                message="You don't have permission to create memory observations.",
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = MemoryObservationCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer)

        service = MemoryObservationService()
        try:
            observation = service.create_observation(
                tenant_id=get_tenant_id_for_user(user),
                **serializer.validated_data,
            )
        except ValueError as exc:
            return error_response(
                code="VALIDATION_ERROR",
                message=str(exc),
                status=status.HTTP_400_BAD_REQUEST,
            )

        return success_response(_observation_payload(observation), status=status.HTTP_201_CREATED)


class MemoryObservationDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, observation_id: UUID) -> Response:
        include_deleted = request.query_params.get("include_deleted", "").strip().lower() in {
            "1",
            "true",
            "yes",
        }
        service = MemoryObservationService()
        try:
            observation = service.get_observation(
                tenant_id=get_tenant_id_for_user(cast(User, request.user)),
                observation_id=observation_id,
                include_deleted=include_deleted,
            )
        except LookupError:
            return error_response(
                code="NOT_FOUND",
                message=f"Memory observation '{observation_id}' was not found.",
                status=status.HTTP_404_NOT_FOUND,
            )

        return success_response(_observation_payload(observation))

    def patch(self, request: Request, observation_id: UUID) -> Response:
        user = cast(User, request.user)
        if not has_min_role(user, "member"):
            return error_response(
                code="FORBIDDEN",
                message="You don't have permission to update memory observations.",
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = MemoryObservationUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer)

        service = MemoryObservationService()
        try:
            observation = service.update_observation(
                tenant_id=get_tenant_id_for_user(user),
                observation_id=observation_id,
                **serializer.validated_data,
            )
        except LookupError:
            return error_response(
                code="NOT_FOUND",
                message=f"Memory observation '{observation_id}' was not found.",
                status=status.HTTP_404_NOT_FOUND,
            )
        except ValueError as exc:
            return error_response(
                code="VALIDATION_ERROR",
                message=str(exc),
                status=status.HTTP_400_BAD_REQUEST,
            )

        return success_response(_observation_payload(observation))

    def delete(self, request: Request, observation_id: UUID) -> Response:
        user = cast(User, request.user)
        if not has_min_role(user, "member"):
            return error_response(
                code="FORBIDDEN",
                message="You don't have permission to delete memory observations.",
                status=status.HTTP_403_FORBIDDEN,
            )

        service = MemoryObservationService()
        try:
            service.delete_observation(
                tenant_id=get_tenant_id_for_user(user),
                observation_id=observation_id,
            )
        except LookupError:
            return error_response(
                code="NOT_FOUND",
                message=f"Memory observation '{observation_id}' was not found.",
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(status=status.HTTP_204_NO_CONTENT)


class MemoryObservationSearchView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        serializer = MemoryObservationQuerySerializer(data=request.query_params)
        if not serializer.is_valid():
            return _validation_error(serializer)

        service = MemoryObservationService()
        observations = service.search_observations(
            tenant_id=get_tenant_id_for_user(cast(User, request.user)),
            **serializer.validated_data,
        )
        return success_response(
            _observation_list_payload(observations),
            meta={"limit": serializer.validated_data["limit"]},
        )


class MemoryObservationTimelineView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        serializer = MemoryObservationTimelineSerializer(data=request.query_params)
        if not serializer.is_valid():
            return _validation_error(serializer)

        service = MemoryObservationService()
        observations = service.get_timeline(
            tenant_id=get_tenant_id_for_user(cast(User, request.user)),
            **serializer.validated_data,
        )
        return success_response(
            _observation_list_payload(observations),
            meta={"limit": serializer.validated_data["limit"]},
        )


class MemoryObservationContextView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        serializer = MemoryObservationContextSerializer(data=request.query_params)
        if not serializer.is_valid():
            return _validation_error(serializer)

        service = MemoryObservationService()
        context = service.get_context(
            tenant_id=get_tenant_id_for_user(cast(User, request.user)),
            **serializer.validated_data,
        )
        return success_response(_context_payload(context, serializer.validated_data["limit"]))


def _context_payload(context: ObservationContext, limit: int) -> dict[str, Any]:
    return {
        "observations": _observation_list_payload(context.observations),
        "degraded": context.degraded,
        "strategies": context.strategies,
        "limit": limit,
    }
