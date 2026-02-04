from __future__ import annotations

from typing import cast

from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.policies.serializers import TenantPolicySerializer
from adapters.api.responses import error_response, success_response
from infrastructure.orm.models import TenantPolicy, User


class TenantPolicyView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        policy = TenantPolicy.objects.filter(tenant_id=user.id).first()
        if not policy:
            return success_response(
                {
                    "http_allowlist": [],
                    "http_denylist": [],
                    "http_default_deny": False,
                    "allowed_providers": [],
                    "allowed_models": [],
                }
            )
        return success_response(
            {
                "http_allowlist": policy.http_allowlist,
                "http_denylist": policy.http_denylist,
                "http_default_deny": policy.http_default_deny,
                "allowed_providers": policy.allowed_providers,
                "allowed_models": policy.allowed_models,
            }
        )

    def put(self, request: Request) -> Response:
        serializer = TenantPolicySerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                code="VALIDATION_ERROR",
                message="The request contains invalid fields",
                status=400,
                details=[
                    {"field": field, "issue": ", ".join(errors)}
                    for field, errors in serializer.errors.items()
                ],
            )

        user = cast(User, request.user)
        data = serializer.validated_data
        policy, _ = TenantPolicy.objects.update_or_create(
            tenant_id=user.id,
            defaults={
                "http_allowlist": data.get("http_allowlist", []),
                "http_denylist": data.get("http_denylist", []),
                "http_default_deny": data.get("http_default_deny", False),
                "allowed_providers": data.get("allowed_providers", []),
                "allowed_models": data.get("allowed_models", []),
            },
        )

        return success_response(
            {
                "http_allowlist": policy.http_allowlist,
                "http_denylist": policy.http_denylist,
                "http_default_deny": policy.http_default_deny,
                "allowed_providers": policy.allowed_providers,
                "allowed_models": policy.allowed_models,
            }
        )
