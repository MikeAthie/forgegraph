"""Authenticated commerce API views."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from rest_framework import status as http_status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.commerce.serializers import (
    CommerceCompanyQuerySerializer,
    FulfillmentBlockSerializer,
    FulfillmentDeliverSerializer,
    FulfillmentReadySerializer,
    FulfillmentShipSerializer,
    OperatorCheckoutSessionSerializer,
    OperatorNoteSerializer,
)
from adapters.api.responses import error_response, success_response
from application.services.commerce import (
    CommerceError,
    add_order_operator_note,
    commerce_order_payload,
    commerce_orders_payload,
    commerce_overview_payload,
    create_operator_checkout_session,
    fulfillment_payload,
    transition_fulfillment,
)
from application.services.processed_commands import (
    IdempotencyConflict,
    build_idempotency_context,
    idempotency_key_from_request,
    record_processed_command,
    replay_processed_command,
)
from application.services.rbac import has_min_role
from infrastructure.orm.models import Graph, InventoryOrderShell, User


class OperatorCheckoutSessionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = OperatorCheckoutSessionSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)

        user = cast(User, request.user)
        company = _get_company(user, serializer.validated_data["company_id"])
        if company is None:
            return _not_found("Company was not found or you do not have access to it.")
        if not has_min_role(user, "member", organization_id=str(company.organization_id)):
            return _forbidden("You do not have permission to create commerce checkout sessions.")

        idempotency_key = idempotency_key_from_request(request)
        if not idempotency_key:
            return error_response(
                "IDEMPOTENCY_KEY_REQUIRED",
                "Idempotency-Key is required for commerce checkout commands.",
                status=http_status.HTTP_400_BAD_REQUEST,
            )
        context = build_idempotency_context(
            request=request,
            organization=company.organization,
            action="commerce.create_checkout_session",
            request_payload=request.data,
        )
        try:
            replay = replay_processed_command(context)
        except IdempotencyConflict as exc:
            return _idempotency_conflict_response(exc)
        if replay is not None:
            return replay

        try:
            payload = create_operator_checkout_session(
                company=company,
                actor=user,
                idempotency_key=idempotency_key,
                reservation_id=str(serializer.validated_data.get("reservation_id") or ""),
                order_shell_id=str(serializer.validated_data.get("order_shell_id") or ""),
            )
        except CommerceError as exc:
            return _commerce_error_response(exc)

        response = success_response(payload, status=http_status.HTTP_201_CREATED)
        return record_processed_command(
            context=context,
            response=response,
            resource_type="commerce_payment",
            resource_id=str(payload.get("payment", {}).get("id", "")),
        )


class CommerceOverviewView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        serializer = CommerceCompanyQuerySerializer(data=request.query_params)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        user = cast(User, request.user)
        company = _get_company(user, serializer.validated_data["company_id"])
        if company is None:
            return _not_found("Company was not found or you do not have access to it.")
        if not has_min_role(user, "viewer", organization_id=str(company.organization_id)):
            return _forbidden("You do not have permission to view commerce operations.")
        return success_response({"commerce": commerce_overview_payload(company)})


class CommerceOrdersView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        serializer = CommerceCompanyQuerySerializer(data=request.query_params)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        user = cast(User, request.user)
        company = _get_company(user, serializer.validated_data["company_id"])
        if company is None:
            return _not_found("Company was not found or you do not have access to it.")
        if not has_min_role(user, "viewer", organization_id=str(company.organization_id)):
            return _forbidden("You do not have permission to view commerce orders.")
        return success_response(commerce_orders_payload(company))


class CommerceOrderDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, order_id: UUID) -> Response:
        lookup = _order_for_user(request, order_id, minimum_role="viewer")
        if isinstance(lookup, Response):
            return lookup
        _, order = lookup
        return success_response({"order": commerce_order_payload(order)})


class FulfillmentActionView(APIView):
    permission_classes = [IsAuthenticated]
    action = ""
    serializer_class: type[Any] = FulfillmentReadySerializer

    def post(self, request: Request, order_id: UUID) -> Response:
        serializer = self.serializer_class(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        lookup = _order_for_user(request, order_id, minimum_role="member")
        if isinstance(lookup, Response):
            return lookup
        user, order = lookup
        context, error = _command_context(
            request=request,
            company=order.company,
            action=f"commerce.fulfillment.{self.action}:{order_id}",
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
            fulfillment = transition_fulfillment(
                order=order,
                actor=user,
                action=self.action,
                note=str(serializer.validated_data.get("note") or ""),
                reason_code=str(serializer.validated_data.get("reason_code") or ""),
                carrier=str(serializer.validated_data.get("carrier") or ""),
                tracking_number=str(serializer.validated_data.get("tracking_number") or ""),
                tracking_url=str(serializer.validated_data.get("tracking_url") or ""),
            )
        except CommerceError as exc:
            return _commerce_error_response(exc)
        response = success_response({"fulfillment": fulfillment_payload(fulfillment)})
        return record_processed_command(
            context=context,
            response=response,
            resource_type="commerce_fulfillment",
            resource_id=str(fulfillment.id),
        )


class FulfillmentBlockView(FulfillmentActionView):
    action = "block"
    serializer_class = FulfillmentBlockSerializer


class FulfillmentReadyView(FulfillmentActionView):
    action = "mark-ready"
    serializer_class = FulfillmentReadySerializer


class FulfillmentShipView(FulfillmentActionView):
    action = "ship"
    serializer_class = FulfillmentShipSerializer


class FulfillmentDeliverView(FulfillmentActionView):
    action = "deliver"
    serializer_class = FulfillmentDeliverSerializer


class OperatorNoteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, order_id: UUID) -> Response:
        serializer = OperatorNoteSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        lookup = _order_for_user(request, order_id, minimum_role="member")
        if isinstance(lookup, Response):
            return lookup
        user, order = lookup
        context, error = _command_context(
            request=request,
            company=order.company,
            action=f"commerce.order_note:{order_id}",
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
            fulfillment = add_order_operator_note(
                order=order,
                actor=user,
                note=str(serializer.validated_data["note"]),
            )
        except CommerceError as exc:
            return _commerce_error_response(exc)
        response = success_response({"fulfillment": fulfillment_payload(fulfillment)})
        return record_processed_command(
            context=context,
            response=response,
            resource_type="commerce_fulfillment_note",
            resource_id=str(fulfillment.id),
        )


def _get_company(user: User, company_id: Any) -> Graph | None:
    return cast(
        Graph | None,
        Graph.objects.for_user(user).filter(id=company_id).select_related("organization").first(),
    )


def _order_for_user(
    request: Request, order_id: UUID, *, minimum_role: str
) -> tuple[User, InventoryOrderShell] | Response:
    user = cast(User, request.user)
    order = (
        InventoryOrderShell.objects.select_related(
            "company", "company__organization", "reservation"
        )
        .filter(id=order_id, company__in=Graph.objects.for_user(user))
        .first()
    )
    if order is None:
        return _not_found("Commerce order was not found.")
    if not has_min_role(user, minimum_role, organization_id=str(order.company.organization_id)):
        return _forbidden("You do not have permission to operate this commerce order.")
    return user, order


def _command_context(
    *,
    request: Request,
    company: Graph,
    action: str,
) -> tuple[Any, Response | None]:
    if not idempotency_key_from_request(request):
        return None, error_response(
            "IDEMPOTENCY_KEY_REQUIRED",
            "Idempotency-Key is required for commerce mutation commands.",
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


def _commerce_error_response(exc: CommerceError) -> Response:
    status: int = http_status.HTTP_400_BAD_REQUEST
    if exc.code in {
        "insufficient_stock",
        "order_not_payable",
        "payment_exists",
        "reservation_not_active",
        "reservation_not_converted",
        "invalid_fulfillment_transition",
    }:
        status = http_status.HTTP_409_CONFLICT
    if exc.code in {
        "order_not_found",
        "reservation_not_found",
        "product_not_found",
        "fulfillment_not_found",
    }:
        status = http_status.HTTP_404_NOT_FOUND
    if exc.code in {"stripe_credential_missing", "stripe_sdk_missing"}:
        status = http_status.HTTP_500_INTERNAL_SERVER_ERROR
    return error_response(exc.code.upper(), exc.message, status=status)
