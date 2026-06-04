"""Gateway platform API views."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.responses import error_response, success_response
from application.services.audit_log import record_audit_log
from application.services.gateway_registry import (
    capability_payload,
    connection_diagnostics,
    connection_payload,
    create_connection,
    list_capabilities,
    record_connection_health,
    update_connection,
)
from application.services.gateway_schedules import (
    GatewayScheduleError,
    create_schedule,
    run_schedule,
    schedule_payload,
    update_schedule,
)
from application.services.rbac import has_min_role
from application.services.tenancy import get_tenant_id_for_user
from infrastructure.orm.models import (
    APIKey,
    GatewayAutomationSchedule,
    GatewayConnection,
    GraphVersion,
    User,
)


class GatewayCapabilityListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        if not has_min_role(user, "member"):
            return _forbidden("You do not have permission to view gateway capabilities.")
        return success_response(
            {
                "capabilities": [
                    capability_payload(capability) for capability in list_capabilities()
                ]
            }
        )


class GatewayConnectionListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        if not has_min_role(user, "member"):
            return _forbidden("You do not have permission to view gateway connections.")
        org = user.default_organization
        if org is None:
            return success_response({"connections": []})
        queryset = (
            GatewayConnection.objects.filter(organization=org)
            .select_related("credential", "graph_version")
            .order_by("platform", "provider", "name")
        )
        return success_response({"connections": [connection_payload(item) for item in queryset]})

    def post(self, request: Request) -> Response:
        user = cast(User, request.user)
        if not has_min_role(user, "admin"):
            return _forbidden("You do not have permission to create gateway connections.")
        org = user.default_organization
        if org is None:
            return _forbidden("No organization found for this user.")
        payload = _payload(request)
        graph_version = _graph_version_for_user(user, payload.get("graph_version_id"))
        if isinstance(graph_version, Response):
            return graph_version
        credential = _credential_for_user(user, payload.get("credential_id"))
        if isinstance(credential, Response):
            return credential
        try:
            connection = create_connection(
                organization=org,
                platform=str(payload.get("platform") or ""),
                provider=str(payload.get("provider") or ""),
                name=str(payload.get("name") or ""),
                graph_version=graph_version,
                credential=credential,
                config=_dict(payload.get("config")),
                allowlist=_list(payload.get("allowlist")),
            )
        except ValueError as exc:
            return error_response(
                code="VALIDATION_ERROR",
                message=str(exc),
                status=status.HTTP_400_BAD_REQUEST,
            )
        _audit(user, "gateway.connection.created", "gateway_connection", connection.id)
        return success_response({"connection": connection_payload(connection)}, status=status.HTTP_201_CREATED)


class GatewayConnectionDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request: Request, connection_id: UUID) -> Response:
        user = cast(User, request.user)
        if not has_min_role(user, "admin"):
            return _forbidden("You do not have permission to update gateway connections.")
        connection = _connection_for_user(user, connection_id)
        if isinstance(connection, Response):
            return connection
        payload = _payload(request)
        graph_version = _graph_version_for_user(user, payload.get("graph_version_id"))
        if isinstance(graph_version, Response):
            return graph_version
        credential = _credential_for_user(user, payload.get("credential_id"))
        if isinstance(credential, Response):
            return credential
        connection = update_connection(
            connection,
            status=str(payload["status"]) if "status" in payload else None,
            graph_version=graph_version,
            credential=credential,
            config=_dict(payload["config"]) if "config" in payload else None,
            allowlist=_list(payload["allowlist"]) if "allowlist" in payload else None,
        )
        _audit(user, "gateway.connection.updated", "gateway_connection", connection.id)
        return success_response({"connection": connection_payload(connection)})


class GatewayConnectionHealthView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, connection_id: UUID) -> Response:
        user = cast(User, request.user)
        if not has_min_role(user, "admin"):
            return _forbidden("You do not have permission to check gateway connections.")
        connection = _connection_for_user(user, connection_id)
        if isinstance(connection, Response):
            return connection
        diagnostics = record_connection_health(connection)
        _audit(user, "gateway.connection.health_checked", "gateway_connection", connection.id)
        return success_response({"diagnostics": diagnostics.as_dict(), "connection": connection_payload(connection)})


class GatewayConnectionDiagnosticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, connection_id: UUID) -> Response:
        user = cast(User, request.user)
        if not has_min_role(user, "member"):
            return _forbidden("You do not have permission to view gateway diagnostics.")
        connection = _connection_for_user(user, connection_id)
        if isinstance(connection, Response):
            return connection
        return success_response({"diagnostics": connection_diagnostics(connection).as_dict()})


class GatewayScheduleListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        if not has_min_role(user, "member"):
            return _forbidden("You do not have permission to view gateway schedules.")
        org = user.default_organization
        if org is None:
            return success_response({"schedules": []})
        queryset = (
            GatewayAutomationSchedule.objects.filter(organization=org)
            .select_related("graph_version", "connection", "last_materialized_run")
            .order_by("next_run_at", "name")
        )
        return success_response({"schedules": [schedule_payload(item) for item in queryset]})

    def post(self, request: Request) -> Response:
        user = cast(User, request.user)
        if not has_min_role(user, "admin"):
            return _forbidden("You do not have permission to create gateway schedules.")
        payload = _payload(request)
        graph_version = _graph_version_for_user(user, payload.get("graph_version_id"), required=True)
        if isinstance(graph_version, Response):
            return graph_version
        connection = _connection_for_user(user, payload.get("connection_id"), required=False)
        if isinstance(connection, Response):
            return connection
        try:
            schedule = create_schedule(
                graph_version=graph_version,
                user=user,
                connection=connection,
                platform=str(payload.get("platform") or (connection.platform if connection else "")),
                provider=str(payload.get("provider") or (connection.provider if connection else "")),
                name=str(payload.get("name") or ""),
                schedule_type=str(payload.get("schedule_type") or ""),
                schedule_json=_dict(payload.get("schedule")),
                input_template_json=_dict(payload.get("input_template")),
                timezone_name=str(payload.get("timezone") or "UTC"),
                status=str(payload.get("status") or "enabled"),
            )
        except GatewayScheduleError as exc:
            return error_response(
                code=exc.code,
                message=exc.message,
                status=status.HTTP_400_BAD_REQUEST,
            )
        _audit(user, "gateway.schedule.created", "gateway_automation_schedule", schedule.id)
        return success_response({"schedule": schedule_payload(schedule)}, status=status.HTTP_201_CREATED)


class GatewayScheduleDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request: Request, schedule_id: UUID) -> Response:
        user = cast(User, request.user)
        if not has_min_role(user, "admin"):
            return _forbidden("You do not have permission to update gateway schedules.")
        schedule = _schedule_for_user(user, schedule_id)
        if isinstance(schedule, Response):
            return schedule
        payload = _payload(request)
        try:
            schedule = update_schedule(
                schedule,
                status=str(payload["status"]) if "status" in payload else None,
                schedule_json=_dict(payload["schedule"]) if "schedule" in payload else None,
                input_template_json=(
                    _dict(payload["input_template"]) if "input_template" in payload else None
                ),
                timezone_name=str(payload["timezone"]) if "timezone" in payload else None,
            )
        except GatewayScheduleError as exc:
            return error_response(
                code=exc.code,
                message=exc.message,
                status=status.HTTP_400_BAD_REQUEST,
            )
        _audit(user, "gateway.schedule.updated", "gateway_automation_schedule", schedule.id)
        return success_response({"schedule": schedule_payload(schedule)})

    def delete(self, request: Request, schedule_id: UUID) -> Response:
        user = cast(User, request.user)
        if not has_min_role(user, "admin"):
            return _forbidden("You do not have permission to delete gateway schedules.")
        schedule = _schedule_for_user(user, schedule_id)
        if isinstance(schedule, Response):
            return schedule
        _audit(user, "gateway.schedule.deleted", "gateway_automation_schedule", schedule.id)
        schedule.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class GatewayScheduleRunNowView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, schedule_id: UUID) -> Response:
        user = cast(User, request.user)
        if not has_min_role(user, "admin"):
            return _forbidden("You do not have permission to run gateway schedules.")
        schedule = _schedule_for_user(user, schedule_id)
        if isinstance(schedule, Response):
            return schedule
        try:
            result = run_schedule(schedule_id=schedule.id, force=True)
        except GatewayScheduleError as exc:
            return error_response(
                code=exc.code,
                message=exc.message,
                status=status.HTTP_400_BAD_REQUEST,
            )
        if result is None:
            return error_response(
                code="SCHEDULE_NOT_RUN",
                message="Gateway schedule was not run.",
                status=status.HTTP_409_CONFLICT,
            )
        _audit(user, "gateway.schedule.run_now", "gateway_automation_schedule", schedule.id)
        return success_response({"result": result.as_dict()}, status=status.HTTP_202_ACCEPTED)


def _connection_for_user(
    user: User,
    connection_id: UUID | str | None,
    *,
    required: bool = True,
) -> GatewayConnection | Response | None:
    if not connection_id:
        if required:
            return error_response(
                code="NOT_FOUND",
                message="Gateway connection was not found.",
                status=status.HTTP_404_NOT_FOUND,
            )
        return None
    org = user.default_organization
    connection = (
        GatewayConnection.objects.select_related("credential", "graph_version")
        .filter(id=connection_id, organization=org)
        .first()
    )
    if connection is None:
        return error_response(
            code="NOT_FOUND",
            message="Gateway connection was not found.",
            status=status.HTTP_404_NOT_FOUND,
        )
    return connection


def _schedule_for_user(user: User, schedule_id: UUID | str) -> GatewayAutomationSchedule | Response:
    schedule = (
        GatewayAutomationSchedule.objects.select_related(
            "graph_version",
            "connection",
            "last_materialized_run",
        )
        .filter(id=schedule_id, organization=user.default_organization)
        .first()
    )
    if schedule is None:
        return error_response(
            code="NOT_FOUND",
            message="Gateway schedule was not found.",
            status=status.HTTP_404_NOT_FOUND,
        )
    return schedule


def _graph_version_for_user(
    user: User,
    graph_version_id: Any,
    *,
    required: bool = False,
) -> GraphVersion | Response | None:
    if not graph_version_id:
        if required:
            return error_response(
                code="VALIDATION_ERROR",
                message="graph_version_id is required.",
                status=status.HTTP_400_BAD_REQUEST,
            )
        return None
    graph_version = (
        GraphVersion.objects.select_related("graph__organization", "graph__owner")
        .filter(id=graph_version_id, graph__organization=user.default_organization)
        .first()
    )
    if graph_version is None:
        return error_response(
            code="NOT_FOUND",
            message="Graph version was not found.",
            status=status.HTTP_404_NOT_FOUND,
        )
    return graph_version


def _credential_for_user(user: User, credential_id: Any) -> APIKey | Response | None:
    if not credential_id:
        return None
    credential = APIKey.objects.filter(id=credential_id, organization=user.default_organization).first()
    if credential is None:
        return error_response(
            code="NOT_FOUND",
            message="Credential was not found.",
            status=status.HTTP_404_NOT_FOUND,
        )
    return credential


def _payload(request: Request) -> dict[str, Any]:
    return request.data if isinstance(request.data, dict) else {}


def _dict(value: Any) -> dict[str, Any]:
    return {str(key): item for key, item in value.items()} if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _audit(user: User, action: str, resource_type: str, resource_id: UUID) -> None:
    record_audit_log(
        actor=user,
        tenant_id=get_tenant_id_for_user(user),
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id),
        metadata={},
    )


def _forbidden(message: str) -> Response:
    return error_response(code="FORBIDDEN", message=message, status=status.HTTP_403_FORBIDDEN)
