from __future__ import annotations

from uuid import UUID

from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.responses import error_response, success_response
from infrastructure.crypto.encryption import decrypt_api_key
from infrastructure.orm.models import APIKey, User
from infrastructure.security import s2s


def _tenant_id_for_user(user: User) -> str:
    if hasattr(user, "tenant_id") and user.tenant_id:
        return str(user.tenant_id)
    return str(user.id)


class EngineCredentialDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request: Request, credential_id: UUID) -> Response:
        timestamp_header = request.headers.get("X-Forgegraph-Timestamp", "")
        signature_header = request.headers.get("X-Forgegraph-Signature", "")
        ok, reason = s2s.verify_request(
            timestamp_ms=timestamp_header,
            signature=signature_header,
            body=request.body or b"",
        )
        if not ok:
            return Response({"detail": "Unauthorized", "reason": reason}, status=401)

        tenant_id = request.query_params.get("tenant_id", "")
        if not tenant_id:
            return error_response(
                code="VALIDATION_ERROR",
                message="tenant_id is required",
                status=400,
            )

        try:
            key = APIKey.objects.select_related("user").get(id=credential_id)
        except APIKey.DoesNotExist:
            return error_response(
                code="NOT_FOUND",
                message="Credential not found",
                status=404,
            )

        owner = key.user
        owner_tenant_id = _tenant_id_for_user(owner)
        if owner_tenant_id != tenant_id:
            return error_response(
                code="FORBIDDEN",
                message="Credential does not belong to tenant",
                status=403,
            )

        try:
            api_key = decrypt_api_key(bytes(key.encrypted_key))
        except Exception:
            return error_response(
                code="DECRYPTION_ERROR",
                message="Failed to decrypt credential",
                status=500,
            )

        return success_response(
            {
                "credential_id": str(key.id),
                "provider": key.provider,
                "api_key": api_key,
            }
        )
