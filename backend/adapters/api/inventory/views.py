"""Reusable inventory API views."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from rest_framework import status as http_status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.inventory.serializers import (
    InventoryOverviewQuerySerializer,
    ReservationCreateSerializer,
    ReservationExpireDueSerializer,
    ReservationExtendSerializer,
    ReservationOrderShellSerializer,
    ReservationReleaseSerializer,
)
from adapters.api.responses import error_response, success_response
from application.services.inventory import (
    InventoryError,
    create_order_shell,
    create_reservation,
    expire_due_reservations,
    extend_reservation,
    inventory_order_shell_payload,
    inventory_overview_payload,
    inventory_reservation_payload,
    release_reservation,
)
from application.services.processed_commands import (
    IdempotencyConflict,
    build_idempotency_context,
    idempotency_key_from_request,
    record_processed_command,
    replay_processed_command,
)
from application.services.rbac import has_min_role
from infrastructure.orm.models import Graph, InventoryReservation, User


class InventoryOverviewView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        serializer = InventoryOverviewQuerySerializer(data=request.query_params)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        user = cast(User, request.user)
        company = _get_company(user, serializer.validated_data["company_id"])
        if company is None:
            return _not_found("Company was not found or you do not have access to it.")
        if not _has_company_role(user, company, "viewer"):
            return _forbidden("You do not have permission to view this inventory.")
        return success_response({"inventory": inventory_overview_payload(company)})


class ReservationCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = ReservationCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        user = cast(User, request.user)
        company = _get_company(user, serializer.validated_data["company_id"])
        if company is None:
            return _not_found("Company was not found or you do not have access to it.")
        if not _has_company_role(user, company, "member"):
            return _forbidden("You do not have permission to reserve inventory.")

        context, error = _command_context(
            request=request,
            company=company,
            action="inventory.create_reservation",
            require_key=True,
        )
        if error is not None:
            return error
        try:
            replay = replay_processed_command(context)
        except IdempotencyConflict as exc:
            return _idempotency_conflict_response(exc)
        if replay is not None:
            return replay

        try:
            reservation = create_reservation(
                company=company,
                product_id=str(serializer.validated_data.get("product_id") or ""),
                sku=str(serializer.validated_data.get("sku") or ""),
                quantity=int(serializer.validated_data["quantity"]),
                buyer_alias=str(serializer.validated_data.get("buyer_alias") or ""),
                channel=str(serializer.validated_data.get("channel") or "manual"),
                note=str(serializer.validated_data.get("note") or ""),
                ttl_minutes=int(serializer.validated_data.get("ttl_minutes") or 30),
                actor=user,
                idempotency_key=idempotency_key_from_request(request),
            )
        except InventoryError as exc:
            return _inventory_error_response(exc)
        response = success_response(
            {"reservation": inventory_reservation_payload(reservation)},
            status=http_status.HTTP_201_CREATED,
        )
        return record_processed_command(
            context=context,
            response=response,
            resource_type="inventory_reservation",
            resource_id=str(reservation.id),
        )


class ReservationReleaseView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, reservation_id: UUID) -> Response:
        serializer = ReservationReleaseSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        lookup = _reservation_for_mutation(request, reservation_id, action="release")
        if isinstance(lookup, Response):
            return lookup
        user, reservation = lookup
        context, error = _command_context(
            request=request,
            company=reservation.company,
            action=f"inventory.release_reservation:{reservation_id}",
            require_key=True,
        )
        if error is not None:
            return error
        try:
            replay = replay_processed_command(context)
        except IdempotencyConflict as exc:
            return _idempotency_conflict_response(exc)
        if replay is not None:
            return replay

        try:
            reservation = release_reservation(
                reservation=reservation,
                actor=user,
                reason=str(serializer.validated_data.get("reason") or ""),
            )
        except InventoryError as exc:
            return _inventory_error_response(exc)
        response = success_response({"reservation": inventory_reservation_payload(reservation)})
        return record_processed_command(
            context=context,
            response=response,
            resource_type="inventory_reservation",
            resource_id=str(reservation.id),
        )


class ReservationExtendView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, reservation_id: UUID) -> Response:
        serializer = ReservationExtendSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        lookup = _reservation_for_mutation(request, reservation_id, action="extend")
        if isinstance(lookup, Response):
            return lookup
        user, reservation = lookup
        context, error = _command_context(
            request=request,
            company=reservation.company,
            action=f"inventory.extend_reservation:{reservation_id}",
            require_key=True,
        )
        if error is not None:
            return error
        try:
            replay = replay_processed_command(context)
        except IdempotencyConflict as exc:
            return _idempotency_conflict_response(exc)
        if replay is not None:
            return replay

        try:
            reservation = extend_reservation(
                reservation=reservation,
                minutes=int(serializer.validated_data["minutes"]),
                actor=user,
            )
        except InventoryError as exc:
            return _inventory_error_response(exc)
        response = success_response({"reservation": inventory_reservation_payload(reservation)})
        return record_processed_command(
            context=context,
            response=response,
            resource_type="inventory_reservation",
            resource_id=str(reservation.id),
        )


class ReservationOrderShellView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, reservation_id: UUID) -> Response:
        serializer = ReservationOrderShellSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        lookup = _reservation_for_mutation(request, reservation_id, action="create order shell")
        if isinstance(lookup, Response):
            return lookup
        user, reservation = lookup
        context, error = _command_context(
            request=request,
            company=reservation.company,
            action=f"inventory.create_order_shell:{reservation_id}",
            require_key=True,
        )
        if error is not None:
            return error
        try:
            replay = replay_processed_command(context)
        except IdempotencyConflict as exc:
            return _idempotency_conflict_response(exc)
        if replay is not None:
            return replay

        try:
            order = create_order_shell(
                reservation=reservation,
                actor=user,
                idempotency_key=idempotency_key_from_request(request),
            )
        except InventoryError as exc:
            return _inventory_error_response(exc)
        response = success_response(
            {"order_shell": inventory_order_shell_payload(order)},
            status=http_status.HTTP_201_CREATED,
        )
        return record_processed_command(
            context=context,
            response=response,
            resource_type="inventory_order_shell",
            resource_id=str(order.id),
        )


class ReservationExpireDueView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = ReservationExpireDueSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        user = cast(User, request.user)
        company = _get_company(user, serializer.validated_data["company_id"])
        if company is None:
            return _not_found("Company was not found or you do not have access to it.")
        if not _has_company_role(user, company, "member"):
            return _forbidden("You do not have permission to expire reservations.")
        context, error = _command_context(
            request=request,
            company=company,
            action="inventory.expire_due_reservations",
            require_key=True,
        )
        if error is not None:
            return error
        try:
            replay = replay_processed_command(context)
        except IdempotencyConflict as exc:
            return _idempotency_conflict_response(exc)
        if replay is not None:
            return replay

        try:
            expired = expire_due_reservations(company=company, actor=user)
        except InventoryError as exc:
            return _inventory_error_response(exc)
        response = success_response(
            {
                "expired_count": len(expired),
                "reservations": [inventory_reservation_payload(item) for item in expired],
            }
        )
        return record_processed_command(
            context=context,
            response=response,
            resource_type="inventory_reservation_expiry",
            resource_id=str(company.id),
        )


def _get_company(user: User, company_id: UUID) -> Graph | None:
    return cast(
        Graph | None,
        Graph.objects.for_user(user).filter(id=company_id).select_related("organization").first(),
    )


def _get_reservation_for_user(user: User, reservation_id: UUID) -> InventoryReservation | None:
    return (
        InventoryReservation.objects.select_related("company", "company__organization", "product")
        .filter(id=reservation_id, company__in=Graph.objects.for_user(user))
        .first()
    )


def _reservation_for_mutation(
    request: Request,
    reservation_id: UUID,
    *,
    action: str,
) -> tuple[User, InventoryReservation] | Response:
    user = cast(User, request.user)
    reservation = _get_reservation_for_user(user, reservation_id)
    if reservation is None:
        return _not_found("Reservation was not found.")
    if not _has_company_role(user, reservation.company, "member"):
        return _forbidden(f"You do not have permission to {action} this reservation.")
    return user, reservation


def _has_company_role(user: User, company: Graph, minimum_role: str) -> bool:
    return has_min_role(user, minimum_role, organization_id=str(company.organization_id))


def _command_context(
    *,
    request: Request,
    company: Graph,
    action: str,
    require_key: bool,
) -> tuple[Any, Response | None]:
    key = idempotency_key_from_request(request)
    if require_key and not key:
        return None, error_response(
            "IDEMPOTENCY_KEY_REQUIRED",
            "Idempotency-Key is required for inventory mutation commands.",
            status=http_status.HTTP_400_BAD_REQUEST,
        )
    return (
        build_idempotency_context(
            request=request,
            organization=company.organization,
            action=action,
            request_payload=request.data,
        ),
        None,
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


def _idempotency_conflict_response(exc: IdempotencyConflict) -> Response:
    return error_response(
        "IDEMPOTENCY_CONFLICT",
        str(exc),
        status=http_status.HTTP_409_CONFLICT,
        details=[{"action": exc.action, "idempotency_key": exc.idempotency_key}],
    )


def _inventory_error_response(exc: InventoryError) -> Response:
    status: int = http_status.HTTP_400_BAD_REQUEST
    if exc.code in {"insufficient_stock", "reservation_not_active"}:
        status = http_status.HTTP_409_CONFLICT
    if exc.code in {"product_not_found"}:
        status = http_status.HTTP_404_NOT_FOUND
    return error_response(exc.code.upper(), exc.message, status=status)
