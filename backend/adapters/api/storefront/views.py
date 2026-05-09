"""Public storefront and Stripe webhook API views."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from rest_framework import status as http_status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.responses import error_response, success_response
from adapters.api.storefront.serializers import StorefrontCheckoutSessionSerializer
from application.services.commerce import (
    CommerceError,
    company_for_storefront_slug,
    create_public_checkout_session,
    handle_stripe_event,
    public_order_status_payload,
    storefront_products_payload,
)
from application.services.processed_commands import (
    IdempotencyConflict,
    build_idempotency_context,
    idempotency_key_from_request,
    record_processed_command,
    replay_processed_command,
)

try:
    import stripe
except ModuleNotFoundError:  # pragma: no cover - optional dependency guard
    stripe = None  # type: ignore[assignment]


class StorefrontProductsView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []

    def get(self, request: Request, company_slug: str) -> Response:
        _ = request
        company = company_for_storefront_slug(company_slug)
        if company is None:
            return _not_found("Storefront company was not found.")
        return success_response(storefront_products_payload(company))


class StorefrontCheckoutSessionView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []

    def post(self, request: Request, company_slug: str) -> Response:
        serializer = StorefrontCheckoutSessionSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        company = company_for_storefront_slug(company_slug)
        if company is None:
            return _not_found("Storefront company was not found.")

        idempotency_key = idempotency_key_from_request(request)
        if not idempotency_key:
            return error_response(
                "IDEMPOTENCY_KEY_REQUIRED",
                "Idempotency-Key is required for storefront checkout commands.",
                status=http_status.HTTP_400_BAD_REQUEST,
            )
        context = build_idempotency_context(
            request=request,
            organization=company.organization,
            action=f"storefront.create_checkout_session:{company_slug}",
            request_payload=request.data,
        )
        try:
            replay = replay_processed_command(context)
        except IdempotencyConflict as exc:
            return _idempotency_conflict_response(exc)
        if replay is not None:
            return replay

        try:
            payload = create_public_checkout_session(
                company=company,
                idempotency_key=idempotency_key,
                product_id=str(serializer.validated_data.get("product_id") or ""),
                sku=str(serializer.validated_data.get("sku") or ""),
                quantity=int(serializer.validated_data["quantity"]),
                buyer_alias=str(serializer.validated_data.get("buyer_alias") or ""),
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


class StorefrontOrderStatusView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []

    def get(self, request: Request, company_slug: str, public_status_token: str) -> Response:
        _ = request
        payload = public_order_status_payload(
            company_slug=company_slug,
            public_status_token=public_status_token,
        )
        if payload is None:
            return _not_found("Order status was not found.")
        return success_response(payload)


class StripeWebhookView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []

    def post(self, request: Request) -> Response:
        if stripe is None:
            return error_response("CONFIG_ERROR", "Stripe SDK is not installed.", status=500)
        webhook_secret = getattr(settings, "COMMERCE_STRIPE_WEBHOOK_SECRET", "")
        if not webhook_secret:
            return error_response(
                "CONFIG_ERROR",
                "Commerce Stripe webhook secret is not configured.",
                status=500,
            )
        payload = request.body
        sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)  # type: ignore[no-untyped-call]
        except Exception as exc:
            return error_response(
                "INVALID_SIGNATURE",
                f"Stripe webhook verification failed: {exc}",
                status=http_status.HTTP_400_BAD_REQUEST,
            )
        try:
            result = handle_stripe_event(event)
        except CommerceError as exc:
            return _commerce_error_response(exc)
        return success_response(result)


def _validation_error(details: Any) -> Response:
    return error_response(
        "VALIDATION_ERROR",
        "Request validation failed.",
        status=http_status.HTTP_400_BAD_REQUEST,
        details=[{"field": key, "errors": value} for key, value in dict(details).items()],
    )


def _not_found(message: str) -> Response:
    return error_response("NOT_FOUND", message, status=http_status.HTTP_404_NOT_FOUND)


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
    }:
        status = http_status.HTTP_409_CONFLICT
    if exc.code in {"product_not_found"}:
        status = http_status.HTTP_404_NOT_FOUND
    if exc.code in {"stripe_credential_missing", "stripe_sdk_missing"}:
        status = http_status.HTTP_500_INTERNAL_SERVER_ERROR
    return error_response(exc.code.upper(), exc.message, status=status)
