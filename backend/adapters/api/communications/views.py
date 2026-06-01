"""Generic communication API views."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from django.conf import settings
from rest_framework import status as http_status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.communications.serializers import (
    CommunicationAttachmentCreateSerializer,
    CommunicationMessageCreateSerializer,
    CommunicationThreadCreateSerializer,
    CommunicationThreadQuerySerializer,
)
from adapters.api.responses import error_response, success_response
from application.services.communications import (
    CommunicationError,
    attach_objects_to_message,
    can_create_message,
    can_read_thread,
    create_message,
    create_thread,
    get_thread_for_user,
    list_messages_for_user,
    list_threads_for_user,
    message_payload,
    thread_payload,
)
from application.services.company_access import accessible_company_queryset, has_company_access
from application.services.processed_commands import (
    IdempotencyConflict,
    build_idempotency_context,
    idempotency_key_from_request,
    record_processed_command,
    replay_processed_command,
)
from application.services.rbac import has_min_role
from application.services.request_router import RequestRouterError, classify_and_route_request
from application.services.work_whiteboards import whiteboard_payload
from infrastructure.orm.models import CommunicationMessage, Graph, User


class CommunicationThreadListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        if (disabled := _communication_disabled()) is not None:
            return disabled
        user = cast(User, request.user)
        serializer = CommunicationThreadQuerySerializer(data=request.query_params)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        threads = list_threads_for_user(
            user=user,
            company_id=serializer.validated_data.get("company_id"),
            status=str(serializer.validated_data.get("status") or ""),
            service_engagement_id=serializer.validated_data.get("service_engagement_id"),
            operation_id=serializer.validated_data.get("operation_id"),
        )
        return success_response(
            {"threads": [thread_payload(thread, user=user) for thread in threads]}
        )

    def post(self, request: Request) -> Response:
        if (disabled := _communication_disabled()) is not None:
            return disabled
        user = cast(User, request.user)
        serializer = CommunicationThreadCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        company = _company_for_user(user, serializer.validated_data["company_id"])
        if company is None:
            return _not_found("Company was not found or you do not have access.")
        command = _prepare_command(
            request=request,
            company=company,
            action="communication.thread.create",
        )
        if isinstance(command, Response):
            return command
        context, replay = command
        if replay is not None:
            return replay
        try:
            thread = create_thread(
                company=company,
                user=user,
                data=dict(serializer.validated_data),
            )
        except CommunicationError as exc:
            return _communication_error(exc)
        response = success_response(
            {"thread": thread_payload(thread, user=user)},
            status=http_status.HTTP_201_CREATED,
        )
        return record_processed_command(
            context=context,
            response=response,
            resource_type="communication_thread",
            resource_id=str(thread.id),
        )


class CommunicationThreadDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, thread_id: UUID) -> Response:
        if (disabled := _communication_disabled()) is not None:
            return disabled
        user = cast(User, request.user)
        thread = get_thread_for_user(user=user, thread_id=thread_id)
        if thread is None:
            return _not_found("Communication thread was not found.")
        return success_response({"thread": thread_payload(thread, user=user)})


class CommunicationMessageListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, thread_id: UUID) -> Response:
        if (disabled := _communication_disabled()) is not None:
            return disabled
        user = cast(User, request.user)
        thread = get_thread_for_user(user=user, thread_id=thread_id)
        if thread is None:
            return _not_found("Communication thread was not found.")
        messages = list_messages_for_user(user=user, thread=thread)
        return success_response(
            {"messages": [message_payload(message, user=user) for message in messages]}
        )

    def post(self, request: Request, thread_id: UUID) -> Response:
        if (disabled := _communication_disabled()) is not None:
            return disabled
        user = cast(User, request.user)
        thread = get_thread_for_user(user=user, thread_id=thread_id)
        if thread is None:
            return _not_found("Communication thread was not found.")
        serializer = CommunicationMessageCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        if not can_create_message(
            user=user,
            thread=thread,
            visibility=str(serializer.validated_data.get("visibility") or "customer"),
        ):
            return _forbidden("You do not have permission to create this communication message.")
        command = _prepare_command(
            request=request,
            company=thread.company,
            action=f"communication.message.create:{thread.id}",
        )
        if isinstance(command, Response):
            return command
        context, replay = command
        if replay is not None:
            return replay
        try:
            message = create_message(
                thread=thread,
                sender_user=user,
                sender_kind="user",
                message_kind=str(serializer.validated_data.get("message_kind") or "note"),
                body=str(serializer.validated_data.get("body") or ""),
                body_format=str(serializer.validated_data.get("body_format") or "plain"),
                visibility=str(serializer.validated_data.get("visibility") or "customer"),
                idempotency_key=idempotency_key_from_request(request),
                metadata=dict(serializer.validated_data.get("metadata") or {}),
                attachments=list(serializer.validated_data.get("attachments") or []),
            )
        except CommunicationError as exc:
            return _communication_error(exc)
        response = success_response(
            {"message": message_payload(message, user=user)},
            status=http_status.HTTP_201_CREATED,
        )
        return record_processed_command(
            context=context,
            response=response,
            resource_type="communication_message",
            resource_id=str(message.id),
        )


class CommunicationAttachmentCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, message_id: UUID) -> Response:
        if (disabled := _communication_disabled()) is not None:
            return disabled
        user = cast(User, request.user)
        message = (
            CommunicationMessage.objects.select_related(
                "thread__company", "company", "organization"
            )
            .prefetch_related("attachments")
            .filter(id=message_id)
            .first()
        )
        if message is None or not can_read_thread(user=user, thread=message.thread):
            return _not_found("Communication message was not found.")
        if not can_create_message(user=user, thread=message.thread, visibility=message.visibility):
            return _forbidden("You do not have permission to attach objects to this message.")
        serializer = CommunicationAttachmentCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        command = _prepare_command(
            request=request,
            company=message.company,
            action=f"communication.attachment.create:{message.id}",
        )
        if isinstance(command, Response):
            return command
        context, replay = command
        if replay is not None:
            return replay
        try:
            attachments = attach_objects_to_message(
                user=user,
                message=message,
                attachments=list(serializer.validated_data["attachments"]),
            )
        except CommunicationError as exc:
            return _communication_error(exc)
        message = (
            CommunicationMessage.objects.select_related(
                "thread__company", "company", "organization"
            )
            .prefetch_related("attachments")
            .get(id=message.id)
        )
        response = success_response(
            {
                "message": message_payload(message, user=user),
                "attachment_ids": [str(attachment.id) for attachment in attachments],
            },
            status=http_status.HTTP_201_CREATED,
        )
        return record_processed_command(
            context=context,
            response=response,
            resource_type="communication_message",
            resource_id=str(message.id),
        )


class CommunicationMessageRouteRequestView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, message_id: UUID) -> Response:
        if (disabled := _communication_disabled()) is not None:
            return disabled
        user = cast(User, request.user)
        message = (
            CommunicationMessage.objects.select_related(
                "thread__service_engagement",
                "thread__company",
                "company",
                "organization",
                "sender_user",
            )
            .filter(id=message_id)
            .first()
        )
        if message is None or not can_read_thread(user=user, thread=message.thread):
            return _not_found("Communication message was not found.")
        if message.company is None:
            return _not_found("Communication message was not company-scoped.")
        if not (
            has_company_access(user, message.company, "member")
            and has_min_role(user, "member", str(message.organization_id))
        ):
            return _forbidden("You do not have permission to route this communication request.")
        command = _prepare_command(
            request=request,
            company=message.company,
            action=f"communication.message.route_request:{message.id}",
        )
        if isinstance(command, Response):
            return command
        context, replay = command
        if replay is not None:
            return replay
        try:
            classification, whiteboard, routing_records = classify_and_route_request(
                message=message,
                idempotency_key=f"request-router:message:{message.id}",
            )
        except RequestRouterError as exc:
            return error_response(
                exc.code.upper(), exc.message, status=http_status.HTTP_400_BAD_REQUEST
            )
        response = success_response(
            {
                "classification": _classification_payload(classification),
                "whiteboard": whiteboard_payload(whiteboard, user=user)
                if whiteboard is not None
                else None,
                "routing_record_ids": [str(record.id) for record in routing_records],
            },
            status=http_status.HTTP_200_OK,
        )
        return record_processed_command(
            context=context,
            response=response,
            resource_type="request_classification",
            resource_id=str(classification.id),
        )


def _company_for_user(user: User, company_id: UUID) -> Graph | None:
    return (
        accessible_company_queryset(user, minimum_role="viewer")
        .filter(id=company_id)
        .select_related("organization")
        .first()
    )


def _communication_disabled() -> Response | None:
    if getattr(settings, "COMMUNICATION_ENABLED", True):
        return None
    return _not_found("Communication is disabled.")


def _prepare_command(
    *,
    request: Request,
    company: Graph | None,
    action: str,
) -> tuple[Any, Response | None] | Response:
    if company is None:
        return _not_found("Company was not found for this communication resource.")
    if not idempotency_key_from_request(request):
        return error_response(
            "IDEMPOTENCY_KEY_REQUIRED",
            "Idempotency-Key is required for communication mutations.",
            status=http_status.HTTP_400_BAD_REQUEST,
        )
    context = build_idempotency_context(
        request=request,
        organization=company.organization,
        action=action,
        request_payload=request.data,
    )
    try:
        replay = replay_processed_command(context)
    except IdempotencyConflict as exc:
        return error_response(
            "IDEMPOTENCY_CONFLICT",
            str(exc),
            status=http_status.HTTP_409_CONFLICT,
            details=[{"action": exc.action, "idempotency_key": exc.idempotency_key}],
        )
    return context, replay


def _communication_error(exc: CommunicationError) -> Response:
    status_code: int = http_status.HTTP_400_BAD_REQUEST
    if exc.code in {
        "company_not_found",
        "linked_object_not_found",
        "attachment_target_not_found",
        "linked_object_scope_mismatch",
    }:
        status_code = http_status.HTTP_404_NOT_FOUND
    if exc.code == "permission_denied":
        status_code = http_status.HTTP_403_FORBIDDEN
    return error_response(
        exc.code.upper(),
        exc.message,
        status=status_code,
        details=exc.details,
    )


def _validation_error(details: Any) -> Response:
    return error_response(
        "VALIDATION_ERROR",
        "Request validation failed.",
        status=http_status.HTTP_400_BAD_REQUEST,
        details=[{"field": key, "errors": value} for key, value in dict(details).items()],
    )


def _not_found(message: str) -> Response:
    return error_response("NOT_FOUND", message, status=http_status.HTTP_404_NOT_FOUND)


def _forbidden(message: str) -> Response:
    return error_response("FORBIDDEN", message, status=http_status.HTTP_403_FORBIDDEN)


def _classification_payload(classification: Any) -> dict[str, Any]:
    return {
        "id": str(classification.id),
        "organization_id": str(classification.organization_id),
        "company_id": str(classification.company_id),
        "communication_thread_id": str(classification.communication_thread_id)
        if classification.communication_thread_id
        else None,
        "communication_message_id": str(classification.communication_message_id)
        if classification.communication_message_id
        else None,
        "service_engagement_id": str(classification.service_engagement_id)
        if classification.service_engagement_id
        else None,
        "classification": classification.classification,
        "confidence": float(classification.confidence),
        "rationale": classification.rationale,
        "matched_whiteboard_id": str(classification.matched_whiteboard_id)
        if classification.matched_whiteboard_id
        else None,
        "matched_service_engagement_id": str(classification.matched_service_engagement_id)
        if classification.matched_service_engagement_id
        else None,
        "created_at": classification.created_at.isoformat(),
    }
