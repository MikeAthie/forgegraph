from __future__ import annotations

from typing import Any

from rest_framework import serializers

from infrastructure.orm.models import OrganizationMembership


class OrganizationSerializer(serializers.Serializer[Any]):
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


class OrganizationListItemSerializer(OrganizationSerializer):
    role = serializers.ChoiceField(choices=OrganizationMembership.ROLE_CHOICES)
    is_default = serializers.BooleanField(read_only=True)
    joined_at = serializers.DateTimeField(read_only=True)


class OrganizationCreateSerializer(serializers.Serializer[Any]):
    name = serializers.CharField(max_length=255, trim_whitespace=True)
    make_default = serializers.BooleanField(required=False, default=True)


class OrganizationSwitchSerializer(serializers.Serializer[Any]):
    organization_id = serializers.UUIDField()


class OrganizationMemberSerializer(serializers.Serializer[Any]):
    user_id = serializers.UUIDField(read_only=True)
    email = serializers.EmailField(read_only=True)
    role = serializers.ChoiceField(choices=OrganizationMembership.ROLE_CHOICES)
    is_default = serializers.BooleanField(read_only=True)
    joined_at = serializers.DateTimeField(read_only=True)


class OrganizationMemberCreateSerializer(serializers.Serializer[Any]):
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=OrganizationMembership.ROLE_CHOICES)


class OrganizationMemberUpdateSerializer(serializers.Serializer[Any]):
    role = serializers.ChoiceField(choices=OrganizationMembership.ROLE_CHOICES)
