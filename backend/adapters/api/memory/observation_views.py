from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from django.db import transaction
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
from application.services.audit_log import record_audit_log
from application.services.idempotency import (
    annotate_response,
    annotated_response_from_body,
    hash_request_payload,
    normalize_idempotency_key,
    record_idempotency_observation,
    response_body,
)
from application.services.memory_observation_service import (
    MemoryObservationService,
    ObservationContext,
)
from application.services.rbac import has_min_role
from application.services.tenancy import get_tenant_id_for_user
from infrastructure.orm.models import MemoryObservation, ProcessedMemoryEvent, User


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
                "source_event_id": observation.source_event_id,
                "source_event_type": observation.source_event_type,
                "fact_hash": observation.fact_hash,
                "provenance": observation.provenance_json
                if isinstance(observation.provenance_json, dict)
                else {},
                "cost_metadata": observation.cost_metadata_json
                if isinstance(observation.cost_metadata_json, dict)
                else {},
                "retention_policy": observation.retention_policy_json
                if isinstance(observation.retention_policy_json, dict)
                else {},
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


def _record_memory_observation_audit(
    *,
    user: User,
    action: str,
    observation: MemoryObservation,
    changed_fields: list[str] | None = None,
) -> None:
    metadata: dict[str, Any] = {
        "type": observation.type,
        "title": observation.title,
        "scope": observation.scope,
        "topic_key": observation.topic_key,
        "graph_id": str(observation.graph_id) if observation.graph_id else None,
        "run_id": str(observation.run_id) if observation.run_id else None,
        "session_id": str(observation.session_id) if observation.session_id else None,
    }
    if changed_fields:
        metadata["changed_fields"] = changed_fields

    record_audit_log(
        actor=user,
        tenant_id=get_tenant_id_for_user(user),
        action=action,
        resource_type="memory_observation",
        resource_id=str(observation.id),
        metadata=metadata,
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

        tenant_id = get_tenant_id_for_user(user)
        validated_data = dict(serializer.validated_data)
        body_idempotency_key = str(validated_data.pop("idempotency_key", "") or "").strip()
        idempotency_key = normalize_idempotency_key(
            body_idempotency_key or request.headers.get("Idempotency-Key"),
            max_length=128,
        )
        request_hash = hash_request_payload(validated_data)
        if idempotency_key:
            processed = ProcessedMemoryEvent.objects.filter(
                organization_id=tenant_id,
                event_id=idempotency_key,
            ).first()
            if processed is not None:
                if processed.request_hash != request_hash:
                    record_idempotency_observation(
                        boundary="memory_write",
                        status="rejected",
                        idempotency_key=idempotency_key,
                        resource_type="memory_observation",
                        organization_id=tenant_id,
                    )
                    return error_response(
                        code="IDEMPOTENCY_CONFLICT",
                        message="Idempotency key was already used with a different request body.",
                        status=status.HTTP_409_CONFLICT,
                        details=[{"idempotency_key": idempotency_key}],
                    )
                record_idempotency_observation(
                    boundary="memory_write",
                    status="already_applied",
                    idempotency_key=idempotency_key,
                    resource_type="memory_observation",
                    organization_id=tenant_id,
                )
                return annotated_response_from_body(
                    processed.response_body,
                    response_status=processed.response_status,
                    status="already_applied",
                    idempotency_key=idempotency_key,
                    resource_type="memory_observation",
                    resource_id=str((processed.observation_ids_json or [""])[0] or ""),
                )

        service = MemoryObservationService()
        try:
            with transaction.atomic():
                observation = service.create_observation(
                    tenant_id=tenant_id,
                    **validated_data,
                )
                _record_memory_observation_audit(
                    user=user,
                    action="memory.observation_created",
                    observation=observation,
                )
                response = success_response(
                    _observation_payload(observation),
                    status=status.HTTP_201_CREATED,
                )
                if idempotency_key:
                    annotate_response(
                        response,
                        status="applied",
                        idempotency_key=idempotency_key,
                        resource_type="memory_observation",
                        resource_id=str(observation.id),
                    )
                    ProcessedMemoryEvent.objects.create(
                        organization_id=tenant_id,
                        event_id=idempotency_key,
                        idempotency_key=idempotency_key,
                        event_type="memory.observation.create",
                        request_hash=request_hash,
                        observation_ids_json=[str(observation.id)],
                        response_status=response.status_code,
                        response_body=response_body(response),
                    )
                    record_idempotency_observation(
                        boundary="memory_write",
                        status="applied",
                        idempotency_key=idempotency_key,
                        resource_type="memory_observation",
                        organization_id=tenant_id,
                    )
        except ValueError as exc:
            return error_response(
                code="VALIDATION_ERROR",
                message=str(exc),
                status=status.HTTP_400_BAD_REQUEST,
            )

        return response


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
        changed_fields = sorted(serializer.validated_data.keys())

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

        _record_memory_observation_audit(
            user=user,
            action="memory.observation_updated",
            observation=observation,
            changed_fields=changed_fields,
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
            observation = service.get_observation(
                tenant_id=get_tenant_id_for_user(user),
                observation_id=observation_id,
            )
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

        _record_memory_observation_audit(
            user=user,
            action="memory.observation_deleted",
            observation=observation,
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
