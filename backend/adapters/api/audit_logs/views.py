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

    def _pagination_params(self, request: Request) -> tuple[int, int, Response | None]:
        limit_raw = request.query_params.get("limit")
        offset_raw = request.query_params.get("offset")
        try:
            limit = int(limit_raw) if limit_raw is not None else 100
            offset = int(offset_raw) if offset_raw is not None else 0
        except ValueError:
            return (
                100,
                0,
                error_response(
                    code="VALIDATION_ERROR",
                    message="limit and offset must be integers",
                    status=400,
                ),
            )
        if limit <= 0 or limit > 500:
            return (
                limit,
                offset,
                error_response(
                    code="VALIDATION_ERROR",
                    message="limit must be between 1 and 500",
                    status=400,
                ),
            )
        if offset < 0:
            return (
                limit,
                offset,
                error_response(
                    code="VALIDATION_ERROR",
                    message="offset must be >= 0",
                    status=400,
                ),
            )
        return limit, offset, None

    def _base_queryset_for_user(
        self,
        *,
        user: User,
        tenant_id: str,
    ) -> tuple[Any, str, Response | None]:
        qs = AuditLog.objects.select_related("actor").all()
        if getattr(user, "is_staff", False):
            if tenant_id:
                qs = qs.filter(tenant_id=tenant_id)
            return qs, tenant_id, None
        if not has_min_role(user, "admin"):
            return (
                qs,
                tenant_id,
                error_response(
                    code="FORBIDDEN",
                    message="You don't have permission to view audit logs in this organization.",
                    status=403,
                ),
            )
        tenant_id = get_tenant_id_for_user(user)
        return qs.filter(tenant_id=tenant_id), tenant_id, None

    def _apply_text_filters(self, *, qs: Any, filters: dict[str, str]) -> Any:
        if filters["action"]:
            qs = qs.filter(action=filters["action"])
        if filters["resource_type"]:
            qs = qs.filter(resource_type=filters["resource_type"])
        if filters["actor_email"]:
            qs = qs.filter(Q(actor__email__icontains=filters["actor_email"]))
        if filters["resource_id"]:
            qs = qs.filter(resource_id=filters["resource_id"])
        if filters["action_prefix"]:
            qs = qs.filter(action__startswith=filters["action_prefix"])
        if filters["run_id"]:
            qs = qs.filter(
                Q(resource_type="run", resource_id=filters["run_id"])
                | Q(metadata__run_id=filters["run_id"])
                | Q(metadata__source_run_id=filters["run_id"])
            )
        if filters["search"]:
            qs = qs.filter(
                Q(action__icontains=filters["search"])
                | Q(resource_type__icontains=filters["search"])
                | Q(resource_id__icontains=filters["search"])
                | Q(actor__email__icontains=filters["search"])
            )
        return qs

    def _apply_created_filter(
        self,
        *,
        qs: Any,
        raw_value: str,
        param_name: str,
        field_name: str,
    ) -> tuple[Any, Response | None]:
        if not raw_value:
            return qs, None
        parsed = parse_datetime(raw_value)
        if parsed is None:
            return qs, error_response(
                code="VALIDATION_ERROR",
                message=f"{param_name} must be an ISO datetime",
                status=400,
            )
        return qs.filter(**{field_name: parsed}), None

    def _serialize_entries(self, page: Any) -> list[dict[str, Any]]:
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
        return data

    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        filters = {
            "action": (request.query_params.get("action") or "").strip(),
            "resource_type": (request.query_params.get("resource_type") or "").strip(),
            "resource_id": (request.query_params.get("resource_id") or "").strip(),
            "actor_email": (request.query_params.get("actor_email") or "").strip(),
            "action_prefix": (request.query_params.get("action_prefix") or "").strip(),
            "run_id": (request.query_params.get("run_id") or "").strip(),
            "search": (request.query_params.get("q") or "").strip(),
        }
        created_from_raw = (request.query_params.get("created_from") or "").strip()
        created_to_raw = (request.query_params.get("created_to") or "").strip()
        tenant_id = (request.query_params.get("tenant_id") or "").strip()

        limit, offset, pagination_error = self._pagination_params(request)
        if pagination_error is not None:
            return pagination_error

        qs, tenant_id, access_error = self._base_queryset_for_user(user=user, tenant_id=tenant_id)
        if access_error is not None:
            return access_error
        qs = self._apply_text_filters(qs=qs, filters=filters)
        qs, created_error = self._apply_created_filter(
            qs=qs,
            raw_value=created_from_raw,
            param_name="created_from",
            field_name="created_at__gte",
        )
        if created_error is not None:
            return created_error
        qs, created_error = self._apply_created_filter(
            qs=qs,
            raw_value=created_to_raw,
            param_name="created_to",
            field_name="created_at__lte",
        )
        if created_error is not None:
            return created_error

        total_count = qs.count()
        page = qs.order_by("-created_at")[offset : offset + limit]

        return paginated_response(
            data=self._serialize_entries(page),
            page=(offset // limit) + 1,
            page_size=limit,
            total_count=total_count,
        )
