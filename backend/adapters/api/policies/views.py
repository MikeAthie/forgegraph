from __future__ import annotations

from typing import cast

from django.conf import settings
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.policies.serializers import TenantPolicySerializer
from adapters.api.responses import error_response, success_response
from application.services.rbac import has_min_role
from application.services.tenancy import get_tenant_id_for_user
from infrastructure.orm.models import TenantPolicy, User


def _policy_payload(policy: TenantPolicy | None) -> dict[str, object]:
    http_allowlist = policy.http_allowlist if policy else []
    http_denylist = policy.http_denylist if policy else []
    http_default_deny = policy.http_default_deny if policy else False
    allowed_providers = policy.allowed_providers if policy else []
    allowed_models = policy.allowed_models if policy else []
    runtime_mode = getattr(settings, "FORGEGRAPH_RUNTIME_MODE", "cloud")

    if http_default_deny:
        http_access_mode = "default_deny"
    elif http_allowlist:
        http_access_mode = "allowlist_first"
    else:
        http_access_mode = "open"

    return {
        "http_allowlist": http_allowlist,
        "http_denylist": http_denylist,
        "http_default_deny": http_default_deny,
        "allowed_providers": allowed_providers,
        "allowed_models": allowed_models,
        "summary": {
            "runtime_mode": runtime_mode,
            "http_access_mode": http_access_mode,
            "egress_allowlist_count": len(http_allowlist),
            "egress_denylist_count": len(http_denylist),
            "provider_allowlist_count": len(allowed_providers),
            "model_allowlist_count": len(allowed_models),
            "exec_tools_policy": (
                "restricted_in_cloud"
                if runtime_mode == "cloud"
                else "package_and_policy_controlled"
            ),
            "curated_memory_enabled": getattr(settings, "FF_CURATED_MEMORY_ENABLED", True),
            "curated_memory_vector_indexing_enabled": getattr(
                settings, "FF_CURATED_MEMORY_VECTOR_INDEXING", True
            ),
        },
    }


class TenantPolicyView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        policy = TenantPolicy.objects.filter(tenant_id=get_tenant_id_for_user(user)).first()
        return success_response(_policy_payload(policy))

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
        if not has_min_role(user, "admin"):
            return error_response(
                code="FORBIDDEN",
                message="You don't have permission to update policies in this organization.",
                status=403,
            )
        data = serializer.validated_data
        policy, _ = TenantPolicy.objects.update_or_create(
            tenant_id=get_tenant_id_for_user(user),
            defaults={
                "http_allowlist": data.get("http_allowlist", []),
                "http_denylist": data.get("http_denylist", []),
                "http_default_deny": data.get("http_default_deny", False),
                "allowed_providers": data.get("allowed_providers", []),
                "allowed_models": data.get("allowed_models", []),
            },
        )

        return success_response(_policy_payload(policy))
