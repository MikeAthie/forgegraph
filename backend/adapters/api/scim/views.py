from __future__ import annotations

import re
from typing import Any, cast

from django.utils import timezone
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.responses import error_response
from application.services.audit_log import record_audit_log
from application.services.rbac import has_min_role
from application.services.scim import generate_scim_token, hash_scim_token
from application.services.tenancy import get_tenant_id_for_user
from infrastructure.orm.models import Organization, OrganizationMembership, SCIMToken, User

from .authentication import ScimTokenAuthentication

SCIM_USER_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"
SCIM_LIST_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:ListResponse"


def _scim_user_resource(user: User) -> dict[str, Any]:
    return {
        "schemas": [SCIM_USER_SCHEMA],
        "id": str(user.id),
        "userName": user.email,
        "name": {"givenName": user.first_name or "", "familyName": user.last_name or ""},
        "active": user.is_active,
        "emails": [{"value": user.email, "primary": True}],
    }


def _parse_filter(filter_query: str | None) -> dict[str, Any]:
    if not filter_query:
        return {}
    match = re.match(r'(\w+)\s+eq\s+"([^"]+)"', filter_query)
    if not match:
        return {}
    field, value = match.groups()
    return {field: value}


class ScimUsersView(APIView):
    authentication_classes = [ScimTokenAuthentication]
    permission_classes = [AllowAny]

    def get(self, request: Request) -> Response:
        tenant_id = getattr(request, "scim_tenant_id", None)
        if not tenant_id:
            return error_response(
                code="UNAUTHORIZED",
                message="Missing SCIM token",
                status=401,
            )
        tenant_id = str(tenant_id)

        filter_query = request.query_params.get("filter")
        filters = _parse_filter(filter_query)

        qs = User.objects.filter(organization_memberships__organization_id=tenant_id).distinct()

        if "userName" in filters:
            qs = qs.filter(email__iexact=filters["userName"])
        if "active" in filters:
            active = filters["active"].lower() == "true"
            qs = qs.filter(is_active=active)

        start_index = int(request.query_params.get("startIndex", "1"))
        count = int(request.query_params.get("count", "100"))
        if start_index < 1:
            start_index = 1
        if count < 1:
            count = 1

        total = qs.count()
        offset = start_index - 1
        page = qs[offset : offset + count]

        return Response(
            {
                "schemas": [SCIM_LIST_SCHEMA],
                "totalResults": total,
                "startIndex": start_index,
                "itemsPerPage": len(page),
                "Resources": [_scim_user_resource(user) for user in page],
            }
        )

    def post(self, request: Request) -> Response:
        tenant_id = getattr(request, "scim_tenant_id", None)
        if not tenant_id:
            return error_response(
                code="UNAUTHORIZED",
                message="Missing SCIM token",
                status=401,
            )

        payload = request.data
        email = (payload.get("userName") or "").lower()
        if not email:
            return error_response(
                code="VALIDATION_ERROR",
                message="userName is required",
                status=400,
            )

        if User.objects.filter(email=email).exists():
            return error_response(
                code="CONFLICT",
                message="User already exists",
                status=409,
            )

        user = User(email=email)
        user.set_unusable_password()
        name = payload.get("name") or {}
        user.first_name = name.get("givenName", "") or ""
        user.last_name = name.get("familyName", "") or ""
        user.is_active = bool(payload.get("active", True))
        user.save()

        organization = Organization.objects.filter(id=tenant_id).first()
        if organization:
            OrganizationMembership.objects.get_or_create(
                organization=organization,
                user=user,
                defaults={"role": "member", "is_default": False},
            )

        record_audit_log(
            actor=None,
            tenant_id=str(tenant_id),
            action="scim.user_created",
            resource_type="user",
            resource_id=str(user.id),
            metadata={"email": user.email},
        )

        return Response(_scim_user_resource(user), status=201)


class ScimUserDetailView(APIView):
    authentication_classes = [ScimTokenAuthentication]
    permission_classes = [AllowAny]

    def get(self, request: Request, user_id: str) -> Response:
        tenant_id = getattr(request, "scim_tenant_id", None)
        if not tenant_id:
            return error_response(
                code="UNAUTHORIZED",
                message="Missing SCIM token",
                status=401,
            )
        tenant_id = str(tenant_id)
        user = User.objects.filter(
            id=user_id,
            organization_memberships__organization_id=tenant_id,
        ).first()
        if not user:
            return Response(status=404)
        return Response(_scim_user_resource(user))

    def put(self, request: Request, user_id: str) -> Response:
        tenant_id = getattr(request, "scim_tenant_id", None)
        if not tenant_id:
            return error_response(
                code="UNAUTHORIZED",
                message="Missing SCIM token",
                status=401,
            )
        tenant_id = str(tenant_id)
        user = User.objects.filter(
            id=user_id,
            organization_memberships__organization_id=tenant_id,
        ).first()
        if not user:
            return Response(status=404)

        payload = request.data
        email = payload.get("userName")
        if email:
            user.email = email.lower()
        name = payload.get("name") or {}
        user.first_name = name.get("givenName", user.first_name or "")
        user.last_name = name.get("familyName", user.last_name or "")
        if "active" in payload:
            user.is_active = bool(payload.get("active"))
        user.save()

        record_audit_log(
            actor=None,
            tenant_id=str(tenant_id),
            action="scim.user_updated",
            resource_type="user",
            resource_id=str(user.id),
            metadata={"email": user.email},
        )

        return Response(_scim_user_resource(user))

    def patch(self, request: Request, user_id: str) -> Response:
        tenant_id = getattr(request, "scim_tenant_id", None)
        if not tenant_id:
            return error_response(
                code="UNAUTHORIZED",
                message="Missing SCIM token",
                status=401,
            )
        tenant_id = str(tenant_id)
        user = User.objects.filter(
            id=user_id,
            organization_memberships__organization_id=tenant_id,
        ).first()
        if not user:
            return Response(status=404)

        payload = request.data
        operations = payload.get("Operations", [])
        for op in operations:
            value = op.get("value")
            path = (op.get("path") or "").lower()
            if path == "active" and value is not None:
                user.is_active = bool(value)
            if path in {"username", "userName"} and value:
                user.email = str(value).lower()

        user.save()

        record_audit_log(
            actor=None,
            tenant_id=str(tenant_id),
            action="scim.user_updated",
            resource_type="user",
            resource_id=str(user.id),
            metadata={"email": user.email},
        )

        return Response(_scim_user_resource(user))

    def delete(self, request: Request, user_id: str) -> Response:
        tenant_id = getattr(request, "scim_tenant_id", None)
        if not tenant_id:
            return error_response(
                code="UNAUTHORIZED",
                message="Missing SCIM token",
                status=401,
            )
        tenant_id = str(tenant_id)
        user = User.objects.filter(
            id=user_id,
            organization_memberships__organization_id=tenant_id,
        ).first()
        if not user:
            return Response(status=404)

        user.is_active = False
        user.save(update_fields=["is_active"])

        record_audit_log(
            actor=None,
            tenant_id=str(tenant_id),
            action="scim.user_deactivated",
            resource_type="user",
            resource_id=str(user.id),
            metadata={"email": user.email},
        )

        return Response(status=204)


class ScimTokenView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        if not (getattr(user, "is_staff", False) or has_min_role(user, "admin")):
            return error_response(
                code="FORBIDDEN",
                message="You don't have permission to view SCIM tokens.",
                status=403,
            )

        tenant_id = get_tenant_id_for_user(user)
        token = SCIMToken.objects.filter(tenant_id=tenant_id).first()
        if not token:
            return Response(
                {"token_last4": None, "created_at": None, "last_used_at": None, "rotated_at": None}
            )

        return Response(
            {
                "token_last4": token.token_hash[-4:],
                "created_at": token.created_at,
                "last_used_at": token.last_used_at,
                "rotated_at": token.rotated_at,
            }
        )


class ScimTokenRotateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        user = cast(User, request.user)
        if not (getattr(user, "is_staff", False) or has_min_role(user, "admin")):
            return error_response(
                code="FORBIDDEN",
                message="You don't have permission to rotate SCIM tokens.",
                status=403,
            )

        tenant_id = get_tenant_id_for_user(user)
        raw_token = generate_scim_token()
        token_hash = hash_scim_token(raw_token)
        token, created = SCIMToken.objects.update_or_create(
            tenant_id=tenant_id,
            defaults={
                "token_hash": token_hash,
                "rotated_at": timezone.now(),
            },
        )

        record_audit_log(
            actor=user,
            tenant_id=str(tenant_id),
            action="scim.token_rotated",
            resource_type="scim_token",
            resource_id=str(token.id),
            metadata={"created": created},
        )

        return Response({"token": raw_token})
