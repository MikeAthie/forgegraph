"""
Onboarding API serializers.
"""

from typing import Any

from rest_framework import serializers


class OnboardingMilestoneUpdateSerializer(serializers.Serializer[Any]):
    milestone = serializers.CharField()
    metadata = serializers.JSONField(required=False)
