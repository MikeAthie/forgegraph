from __future__ import annotations

from typing import Any, cast

from django.db.models import Q
from django.utils.dateparse import parse_datetime
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.responses import error_response, paginated_response
from application.services.audit_log import describe_audit_log
from application.services.rbac import has_min_role
from application.services.redaction import redact_payload
from application.services.tenancy import get_tenant_id_for_user
from infrastructure.orm.models import AuditLog, User


class AuditLogListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        action = (request.query_params.get("action") or "").strip()
        resource_type = (request.query_params.get("resource_type") or "").strip()
        resource_id = (request.query_params.get("resource_id") or "").strip()
        actor_email = (request.query_params.get("actor_email") or "").strip()
        action_prefix = (request.query_params.get("action_prefix") or "").strip()
        run_id = (request.query_params.get("run_id") or "").strip()
        search = (request.query_params.get("q") or "").strip()
        created_from_raw = (request.query_params.get("created_from") or "").strip()
        created_to_raw = (request.query_params.get("created_to") or "").strip()
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
        if resource_id:
            qs = qs.filter(resource_id=resource_id)
        if action_prefix:
            qs = qs.filter(action__startswith=action_prefix)
        if run_id:
            qs = qs.filter(
                Q(resource_type="run", resource_id=run_id)
                | Q(metadata__run_id=run_id)
                | Q(metadata__source_run_id=run_id)
            )
        if created_from_raw:
            created_from = parse_datetime(created_from_raw)
            if created_from is None:
                return error_response(
                    code="VALIDATION_ERROR",
                    message="created_from must be an ISO datetime",
                    status=400,
                )
            qs = qs.filter(created_at__gte=created_from)
        if created_to_raw:
            created_to = parse_datetime(created_to_raw)
            if created_to is None:
                return error_response(
                    code="VALIDATION_ERROR",
                    message="created_to must be an ISO datetime",
                    status=400,
                )
            qs = qs.filter(created_at__lte=created_to)
        if search:
            qs = qs.filter(
                Q(action__icontains=search)
                | Q(resource_type__icontains=search)
                | Q(resource_id__icontains=search)
                | Q(actor__email__icontains=search)
            )

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
                    "description": describe_audit_log(
                        action=entry.action,
                        resource_type=entry.resource_type,
                        resource_id=entry.resource_id,
                        metadata=cast(dict[str, Any], redact_payload(entry.metadata)),
                    ),
                    "metadata": redact_payload(entry.metadata),
                    "created_at": entry.created_at,
                }
            )

        return paginated_response(
            data=data,
            page=(offset // limit) + 1,
            page_size=limit,
            total_count=total_count,
        )
