"""
Auth API serializers.

Clean Architecture: Interface Adapters layer.
"""

from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from application.services.tenancy import get_default_membership

User = get_user_model()


class RegisterSerializer(serializers.Serializer[Any]):
    """Serializer for user registration."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate_email(self, value: str) -> str:
        """Validate email is unique."""
        email = value.lower().strip()
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return email

    def validate_password(self, value: str) -> str:
        """Validate password using Django's configured validators."""
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value


class LoginSerializer(serializers.Serializer[Any]):
    """Serializer for user login."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class LogoutSerializer(serializers.Serializer[Any]):
    """Serializer for user logout."""

    refresh = serializers.CharField(write_only=True, required=False, allow_blank=True)


class UserSerializer(serializers.Serializer[Any]):
    """Serializer for user output."""

    id = serializers.UUIDField(read_only=True)
    email = serializers.EmailField(read_only=True)
    created_at = serializers.DateTimeField(source="date_joined", read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    default_organization_id = serializers.UUIDField(read_only=True)
    organization_role = serializers.SerializerMethodField()

    def get_organization_role(self, obj: Any) -> str | None:
        membership = get_default_membership(obj)
        return membership.role if membership else None


class TokenSerializer(serializers.Serializer[Any]):
    """Serializer for token output."""

    access = serializers.CharField(read_only=True)
    refresh = serializers.CharField(read_only=True)
