"""Company-first blueprint API views."""

from __future__ import annotations

from typing import Any, cast

from rest_framework import status as http_status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.company_blueprints.serializers import (
    CompanyBlueprintCompileSerializer,
    CompanyFromBlueprintSerializer,
)
from adapters.api.responses import error_response, success_response
from application.services.company_blueprints import (
    CompanyBlueprintCompiler,
    CompanyBlueprintError,
    create_company_from_blueprint,
)
from application.services.llm_access import LLMAccessValidationError
from application.services.processed_commands import (
    IdempotencyConflict,
    build_idempotency_context,
    idempotency_key_from_request,
    record_processed_command,
    replay_processed_command,
)
from application.services.rbac import has_min_role
from infrastructure.orm.models import User


class CompanyBlueprintCompileView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        user = cast(User, request.user)
        if not has_min_role(user, "viewer"):
            return _forbidden("You do not have permission to compile company blueprints.")
        serializer = CompanyBlueprintCompileSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        try:
            result = CompanyBlueprintCompiler().compile(**serializer.validated_data)
        except CompanyBlueprintError as exc:
            return _blueprint_error_response(exc)
        return success_response(result.as_payload())


class CompanyFromBlueprintView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        user = cast(User, request.user)
        if not has_min_role(user, "member"):
            return _forbidden("You do not have permission to create companies.")
        if not idempotency_key_from_request(request):
            return error_response(
                "IDEMPOTENCY_KEY_REQUIRED",
                "Idempotency-Key is required for company blueprint creation.",
                status=http_status.HTTP_400_BAD_REQUEST,
            )
        serializer = CompanyFromBlueprintSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)

        context = build_idempotency_context(
            request=request,
            organization=user.default_organization,
            action="companies.from_blueprint",
            request_payload=request.data,
        )
        try:
            replay = replay_processed_command(context)
        except IdempotencyConflict as exc:
            return _idempotency_conflict_response(exc)
        if replay is not None:
            _mark_idempotent_replay(replay)
            return replay

        try:
            result = create_company_from_blueprint(user=user, **serializer.validated_data)
        except CompanyBlueprintError as exc:
            return _blueprint_error_response(exc)
        except LLMAccessValidationError as exc:
            return error_response(
                "INVALID_LLM_ACCESS",
                "LLM access configuration is invalid.",
                status=http_status.HTTP_400_BAD_REQUEST,
                details=cast(list[dict[str, Any]], exc.details),
            )

        response = success_response(
            result.as_payload(),
            status=http_status.HTTP_201_CREATED,
        )
        return record_processed_command(
            context=context,
            response=response,
            resource_type="company",
            resource_id=result.company_id,
        )


def _mark_idempotent_replay(response: Response) -> None:
    body = response.data
    if not isinstance(body, dict):
        return
    data = body.get("data")
    if isinstance(data, dict):
        data["idempotent_replay"] = True


def _validation_error(details: Any) -> Response:
    return error_response(
        "VALIDATION_ERROR",
        "Request validation failed.",
        status=http_status.HTTP_400_BAD_REQUEST,
        details=[{"field": key, "errors": value} for key, value in dict(details).items()],
    )


def _forbidden(message: str) -> Response:
    return error_response("FORBIDDEN", message, status=http_status.HTTP_403_FORBIDDEN)


def _idempotency_conflict_response(exc: IdempotencyConflict) -> Response:
    return error_response(
        "IDEMPOTENCY_CONFLICT",
        str(exc),
        status=http_status.HTTP_409_CONFLICT,
        details=[{"action": exc.action, "idempotency_key": exc.idempotency_key}],
    )


def _blueprint_error_response(exc: CompanyBlueprintError) -> Response:
    response_status: int = http_status.HTTP_400_BAD_REQUEST
    if exc.code == "invalid_graph_json":
        response_status = http_status.HTTP_409_CONFLICT
    return error_response(
        exc.code.upper(),
        exc.message,
        status=response_status,
        details=exc.details,
    )
