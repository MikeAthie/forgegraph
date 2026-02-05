from __future__ import annotations

from typing import cast
from uuid import UUID

from django.db import IntegrityError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.credentials.serializers import APIKeyCreateSerializer, APIKeySerializer
from adapters.api.responses import error_response, success_response
from application.services.audit_log import record_audit_log
from application.services.rbac import has_min_role
from application.services.tenancy import get_tenant_id_for_user
from infrastructure.crypto.encryption import encrypt_api_key
from infrastructure.orm.models import APIKey, User


class CredentialsListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        if not has_min_role(user, "admin"):
            return error_response(
                code="FORBIDDEN",
                message="You don't have permission to view credentials in this organization.",
                status=403,
            )
        if not user.default_organization:
            return error_response(
                code="NOT_FOUND",
                message="No default organization found for this user.",
                status=404,
            )
        organization = user.default_organization
        keys = APIKey.objects.filter(organization=organization).order_by("-created_at")
        data = [APIKeySerializer(key).data for key in keys]
        return success_response(data)

    def post(self, request: Request) -> Response:
        serializer = APIKeyCreateSerializer(data=request.data)
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
                message="You don't have permission to create credentials in this organization.",
                status=403,
            )
        if not user.default_organization:
            return error_response(
                code="NOT_FOUND",
                message="No default organization found for this user.",
                status=404,
            )
        organization = user.default_organization
        provider = serializer.validated_data["provider"]
        name = serializer.validated_data["name"]
        api_key = serializer.validated_data["api_key"]

        try:
            key = APIKey.objects.create(
                organization=organization,
                user=user,
                provider=provider,
                name=name,
                encrypted_key=encrypt_api_key(api_key),
            )
        except IntegrityError:
            return error_response(
                code="DUPLICATE_KEY",
                message="A credential with this provider and name already exists",
                status=400,
            )

        record_audit_log(
            actor=user,
            tenant_id=get_tenant_id_for_user(user),
            action="credential.created",
            resource_type="credential",
            resource_id=str(key.id),
            metadata={"provider": provider, "name": name},
        )

        return success_response(APIKeySerializer(key).data)


class CredentialsDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request: Request, credential_id: UUID) -> Response:
        user = cast(User, request.user)
        if not has_min_role(user, "admin"):
            return error_response(
                code="FORBIDDEN",
                message="You don't have permission to delete credentials in this organization.",
                status=403,
            )
        if not user.default_organization:
            return error_response(
                code="NOT_FOUND",
                message="No default organization found for this user.",
                status=404,
            )
        organization = user.default_organization
        try:
            key = APIKey.objects.get(id=credential_id, organization=organization)
        except APIKey.DoesNotExist:
            return error_response(
                code="NOT_FOUND",
                message="Credential not found",
                status=404,
            )

        record_audit_log(
            actor=user,
            tenant_id=get_tenant_id_for_user(user),
            action="credential.deleted",
            resource_type="credential",
            resource_id=str(key.id),
            metadata={"provider": key.provider, "name": key.name},
        )

        key.delete()
        return success_response({"deleted": True})
