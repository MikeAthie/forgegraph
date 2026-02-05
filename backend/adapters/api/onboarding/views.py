"""
Onboarding API views.
"""

from __future__ import annotations

from typing import Any, cast

from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.onboarding.serializers import OnboardingMilestoneUpdateSerializer
from adapters.api.responses import error_response, success_response
from application.services.tenancy import get_tenant_id_for_user
from infrastructure.orm.models import OnboardingMilestone, User

MILESTONE_DEFINITIONS: list[dict[str, Any]] = [
    {
        "key": "select_template",
        "label": "Select a template",
        "description": "Pick a starter workflow to clone.",
    },
    {
        "key": "attach_credential",
        "label": "Attach credentials",
        "description": "Add an LLM credential for the template.",
    },
    {
        "key": "run_template",
        "label": "Start a run",
        "description": "Launch your first run from a template.",
    },
]


class OnboardingMilestonesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        tenant_id = get_tenant_id_for_user(user)
        records = OnboardingMilestone.objects.filter(user=user, tenant_id=tenant_id)
        record_map = {record.milestone: record for record in records}

        payload: list[dict[str, Any]] = []
        for definition in MILESTONE_DEFINITIONS:
            record = record_map.get(definition["key"])
            payload.append(
                {
                    "key": definition["key"],
                    "label": definition["label"],
                    "description": definition.get("description"),
                    "completed": record is not None,
                    "completed_at": record.completed_at.isoformat() if record else None,
                }
            )

        return success_response(payload)

    def post(self, request: Request) -> Response:
        serializer = OnboardingMilestoneUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                code="VALIDATION_ERROR",
                message="The request contains invalid fields",
                status=status.HTTP_400_BAD_REQUEST,
                details=[
                    {"field": field, "issue": ", ".join(errors)}
                    for field, errors in serializer.errors.items()
                ],
            )

        user = cast(User, request.user)
        tenant_id = get_tenant_id_for_user(user)
        milestone = serializer.validated_data["milestone"]
        metadata = serializer.validated_data.get("metadata") or {}

        if milestone not in {item["key"] for item in MILESTONE_DEFINITIONS}:
            return error_response(
                code="VALIDATION_ERROR",
                message="Unknown onboarding milestone.",
                status=status.HTTP_400_BAD_REQUEST,
            )

        completed_at = timezone.now()
        OnboardingMilestone.objects.update_or_create(
            user=user,
            milestone=milestone,
            defaults={
                "tenant_id": tenant_id,
                "metadata": metadata,
                "completed_at": completed_at,
            },
        )

        return success_response({"milestone": milestone, "completed_at": completed_at.isoformat()})
