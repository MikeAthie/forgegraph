from __future__ import annotations

from typing import Any, cast

from django.db.models import Q
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.responses import error_response, paginated_response
from application.services.rbac import has_min_role
from application.services.tenancy import get_tenant_id_for_user
from infrastructure.orm.models import AuditLog, User


class AuditLogListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        action = (request.query_params.get("action") or "").strip()
        resource_type = (request.query_params.get("resource_type") or "").strip()
        actor_email = (request.query_params.get("actor_email") or "").strip()
        tenant_id = (request.query_params.get("tenant_id") or "").strip()

        limit_raw = request.query_params.get("limit")
        offset_raw = request.query_params.get("offset")
        try:
            limit = int(limit_raw) if limit_raw is not None else 100
            offset = int(offset_raw) if offset_raw is not None else 0
        except ValueError:
            return error_response(
                code="VALIDATION_ERROR",
                message="limit and offset must be integers",
                status=400,
            )
        if limit <= 0 or limit > 500:
            return error_response(
                code="VALIDATION_ERROR",
                message="limit must be between 1 and 500",
                status=400,
            )
        if offset < 0:
            return error_response(
                code="VALIDATION_ERROR",
                message="offset must be >= 0",
                status=400,
            )

        qs = AuditLog.objects.select_related("actor").all()
        if not getattr(user, "is_staff", False):
            if not has_min_role(user, "admin"):
                return error_response(
                    code="FORBIDDEN",
                    message="You don't have permission to view audit logs in this organization.",
                    status=403,
                )
            tenant_id = get_tenant_id_for_user(user)
            qs = qs.filter(tenant_id=tenant_id)
        elif tenant_id:
            qs = qs.filter(tenant_id=tenant_id)
        if action:
            qs = qs.filter(action=action)
        if resource_type:
            qs = qs.filter(resource_type=resource_type)
        if actor_email:
            qs = qs.filter(Q(actor__email__icontains=actor_email))

        total_count = qs.count()
        page = qs.order_by("-created_at")[offset : offset + limit]

        data: list[dict[str, Any]] = []
        for entry in page:
            data.append(
                {
                    "id": entry.id,
                    "tenant_id": entry.tenant_id,
                    "actor_email": entry.actor.email if entry.actor else None,
                    "action": entry.action,
                    "resource_type": entry.resource_type,
                    "resource_id": entry.resource_id,
                    "metadata": entry.metadata,
                    "created_at": entry.created_at,
                }
            )

        return paginated_response(
            data=data,
            page=(offset // limit) + 1,
            page_size=limit,
            total_count=total_count,
        )
