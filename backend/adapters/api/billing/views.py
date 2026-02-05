from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import stripe
from django.conf import settings
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.responses import error_response, success_response
from application.services.audit_log import record_audit_log
from application.services.rbac import has_min_role
from application.services.tenancy import get_tenant_id_for_user
from infrastructure.orm.models import BillingPlan, TenantSubscription, User


def _ensure_admin(user: User) -> Response | None:
    if not (getattr(user, "is_staff", False) or has_min_role(user, "admin")):
        return error_response(
            code="FORBIDDEN",
            message="You don't have permission to manage billing in this organization.",
            status=403,
        )
    return None


def _frontend_url() -> str:
    return getattr(settings, "FRONTEND_URL", "http://localhost:3000").rstrip("/")


def _stripe_client() -> None:
    api_key = getattr(settings, "STRIPE_API_KEY", "")
    stripe.api_key = api_key


def _ensure_stripe_configured() -> Response | None:
    if not getattr(settings, "STRIPE_API_KEY", ""):
        return error_response(
            code="CONFIG_ERROR",
            message="Stripe API key is not configured.",
            status=500,
        )
    return None


def _get_plan_for_price(price_id: str) -> BillingPlan | None:
    return BillingPlan.objects.filter(stripe_price_id=price_id).first()


def _upsert_subscription_from_stripe(subscription: dict[str, Any]) -> TenantSubscription | None:
    metadata = subscription.get("metadata") or {}
    tenant_id = metadata.get("tenant_id")
    if not tenant_id:
        customer_id = subscription.get("customer", "")
        existing = TenantSubscription.objects.filter(stripe_customer_id=customer_id).first()
        if existing:
            tenant_id = existing.tenant_id

    if not tenant_id:
        return None

    items = subscription.get("items", {}).get("data", [])
    price_id = items[0]["price"]["id"] if items else ""
    plan = _get_plan_for_price(price_id) if price_id else None

    current_period_end = subscription.get("current_period_end")
    current_period_end_dt = (
        datetime.fromtimestamp(current_period_end, tz=UTC) if current_period_end else None
    )

    subscription_obj, _ = TenantSubscription.objects.update_or_create(
        tenant_id=tenant_id,
        defaults={
            "plan": plan,
            "stripe_customer_id": subscription.get("customer", "") or "",
            "stripe_subscription_id": subscription.get("id", "") or "",
            "status": subscription.get("status", "trialing"),
            "current_period_end": current_period_end_dt,
            "cancel_at_period_end": subscription.get("cancel_at_period_end", False),
        },
    )
    return subscription_obj


class BillingPlansView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        plans = BillingPlan.objects.filter(is_active=True).order_by("name")
        data = [
            {
                "id": str(plan.id),
                "name": plan.name,
                "stripe_price_id": plan.stripe_price_id,
                "stripe_product_id": plan.stripe_product_id,
                "entitlements": plan.entitlements,
            }
            for plan in plans
        ]
        return success_response(data)


class BillingSubscriptionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        tenant_id = get_tenant_id_for_user(cast(User, request.user))
        subscription = (
            TenantSubscription.objects.select_related("plan").filter(tenant_id=tenant_id).first()
        )
        if not subscription:
            return success_response({"subscription": None})

        return success_response(
            {
                "subscription": {
                    "plan": None
                    if not subscription.plan
                    else {
                        "id": str(subscription.plan.id),
                        "name": subscription.plan.name,
                        "entitlements": subscription.plan.entitlements,
                    },
                    "status": subscription.status,
                    "current_period_end": subscription.current_period_end.isoformat()
                    if subscription.current_period_end
                    else None,
                    "cancel_at_period_end": subscription.cancel_at_period_end,
                    "stripe_customer_id": subscription.stripe_customer_id,
                    "stripe_subscription_id": subscription.stripe_subscription_id,
                }
            }
        )


class BillingCheckoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        user = cast(User, request.user)
        denied = _ensure_admin(user)
        if denied:
            return denied

        config_error = _ensure_stripe_configured()
        if config_error:
            return config_error

        plan_id = request.data.get("plan_id")
        if not plan_id:
            return error_response(
                code="VALIDATION_ERROR",
                message="plan_id is required",
                status=400,
            )

        plan = BillingPlan.objects.filter(id=plan_id, is_active=True).first()
        if not plan or not plan.stripe_price_id:
            return error_response(
                code="NOT_FOUND",
                message="Billing plan not found or missing Stripe price id.",
                status=404,
            )

        tenant_id = get_tenant_id_for_user(user)
        subscription = TenantSubscription.objects.filter(tenant_id=tenant_id).first()

        _stripe_client()
        success_url = f"{_frontend_url()}/admin/billing?status=success"
        cancel_url = f"{_frontend_url()}/admin/billing?status=canceled"

        customer_id = subscription.stripe_customer_id if subscription else ""

        checkout_payload: dict[str, Any] = {
            "mode": "subscription",
            "line_items": [{"price": plan.stripe_price_id, "quantity": 1}],
            "success_url": success_url,
            "cancel_url": cancel_url,
            "client_reference_id": str(tenant_id),
            "subscription_data": {"metadata": {"tenant_id": str(tenant_id)}},
            "metadata": {"tenant_id": str(tenant_id), "plan_id": str(plan.id)},
        }
        if customer_id:
            checkout_payload["customer"] = customer_id

        checkout_session = stripe.checkout.Session.create(**checkout_payload)

        record_audit_log(
            actor=user,
            tenant_id=str(tenant_id),
            action="billing.checkout_started",
            resource_type="billing_plan",
            resource_id=str(plan.id),
            metadata={"stripe_session_id": checkout_session.id},
        )

        return success_response({"checkout_url": checkout_session.url})


class BillingPortalView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        user = cast(User, request.user)
        denied = _ensure_admin(user)
        if denied:
            return denied

        config_error = _ensure_stripe_configured()
        if config_error:
            return config_error

        tenant_id = get_tenant_id_for_user(user)
        subscription = TenantSubscription.objects.filter(tenant_id=tenant_id).first()
        if not subscription or not subscription.stripe_customer_id:
            return error_response(
                code="NOT_FOUND",
                message="No Stripe customer found for this tenant.",
                status=404,
            )

        _stripe_client()
        session = stripe.billing_portal.Session.create(
            customer=subscription.stripe_customer_id,
            return_url=f"{_frontend_url()}/admin/billing",
        )

        return success_response({"portal_url": session.url})


class StripeWebhookView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []

    def post(self, request: Request) -> Response:
        payload = request.body
        sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")
        webhook_secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", "")

        if not webhook_secret:
            return error_response(
                code="CONFIG_ERROR",
                message="Stripe webhook secret not configured.",
                status=500,
            )

        config_error = _ensure_stripe_configured()
        if config_error:
            return config_error

        _stripe_client()
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)  # type: ignore[no-untyped-call]
        except Exception as exc:
            return error_response(
                code="INVALID_SIGNATURE",
                message=f"Stripe webhook verification failed: {exc}",
                status=400,
            )

        event_type = event.get("type")
        data = event.get("data", {}).get("object", {})

        if event_type in {"customer.subscription.created", "customer.subscription.updated"}:
            subscription = _upsert_subscription_from_stripe(data)
            if subscription:
                record_audit_log(
                    actor=None,
                    tenant_id=str(subscription.tenant_id),
                    action="billing.subscription_updated",
                    resource_type="tenant_subscription",
                    resource_id=str(subscription.id),
                    metadata={"stripe_subscription_id": subscription.stripe_subscription_id},
                )

        if event_type == "customer.subscription.deleted":
            subscription = _upsert_subscription_from_stripe(data)
            if subscription:
                subscription.status = "canceled"
                subscription.save(update_fields=["status"])
                record_audit_log(
                    actor=None,
                    tenant_id=str(subscription.tenant_id),
                    action="billing.subscription_canceled",
                    resource_type="tenant_subscription",
                    resource_id=str(subscription.id),
                    metadata={"stripe_subscription_id": subscription.stripe_subscription_id},
                )

        if event_type == "checkout.session.completed":
            subscription_id = data.get("subscription")
            customer_id = data.get("customer")
            metadata = data.get("metadata") or {}
            tenant_id = metadata.get("tenant_id")
            if tenant_id:
                TenantSubscription.objects.update_or_create(
                    tenant_id=tenant_id,
                    defaults={
                        "stripe_customer_id": customer_id or "",
                        "stripe_subscription_id": subscription_id or "",
                        "status": "active",
                    },
                )

        return Response(status=200)
