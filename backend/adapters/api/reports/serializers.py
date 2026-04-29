from __future__ import annotations

from typing import Any

from rest_framework import serializers


class StrategyReportRequestSerializer(serializers.Serializer[Any]):
    company_id = serializers.UUIDField()
    operation_id = serializers.UUIDField()
    audience = serializers.ChoiceField(
        choices=["client", "executive", "internal"],
        required=False,
        default="client",
    )
    format = serializers.ChoiceField(
        choices=["md", "html", "pdf"],
        required=False,
        default="md",
    )
