from __future__ import annotations

from typing import cast
from uuid import UUID

from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.organizations.serializers import (
    OrganizationMemberCreateSerializer,
    OrganizationMemberSerializer,
    OrganizationMemberUpdateSerializer,
    OrganizationSerializer,
)
from adapters.api.responses import error_response, success_response
from application.services.rbac import has_min_role
from application.services.tenancy import get_default_membership
from infrastructure.orm.models import OrganizationMembership, User


class OrganizationMeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        membership = get_default_membership(user)
        if not membership:
            return error_response(
                code="NO_ORGANIZATION",
                message="No default organization set for user.",
                status=404,
            )

        org = membership.organization
        payload = {
            "organization": OrganizationSerializer(org).data,
            "role": membership.role,
        }
        return success_response(payload)


class OrganizationMembersView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        membership = get_default_membership(user)
        if not membership:
            return error_response(
                code="NO_ORGANIZATION",
                message="No default organization set for user.",
                status=404,
            )

        if not has_min_role(user, "admin"):
            return error_response(
                code="FORBIDDEN",
                message="You don't have permission to list members in this organization.",
                status=403,
            )

        members = (
            OrganizationMembership.objects.select_related("user")
            .filter(organization=membership.organization)
            .order_by("-created_at")
        )

        data = [
            OrganizationMemberSerializer(
                {
                    "user_id": member.user_id,
                    "email": member.user.email,
                    "role": member.role,
                    "is_default": member.is_default,
                    "joined_at": member.created_at,
                }
            ).data
            for member in members
        ]

        return success_response(data)

    def post(self, request: Request) -> Response:
        user = cast(User, request.user)
        membership = get_default_membership(user)
        if not membership:
            return error_response(
                code="NO_ORGANIZATION",
                message="No default organization set for user.",
                status=404,
            )

        if not has_min_role(user, "admin"):
            return error_response(
                code="FORBIDDEN",
                message="You don't have permission to add members in this organization.",
                status=403,
            )

        serializer = OrganizationMemberCreateSerializer(data=request.data)
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

        email = serializer.validated_data["email"].lower().strip()
        role = serializer.validated_data["role"]

        try:
            target_user = User.objects.get(email=email)
        except User.DoesNotExist:
            return error_response(
                code="NOT_FOUND",
                message="User with that email does not exist.",
                status=404,
            )

        if OrganizationMembership.objects.filter(
            organization=membership.organization, user=target_user
        ).exists():
            return error_response(
                code="ALREADY_MEMBER",
                message="User is already a member of this organization.",
                status=409,
            )

        member = OrganizationMembership.objects.create(
            organization=membership.organization,
            user=target_user,
            role=role,
            is_default=False,
        )

        return success_response(
            OrganizationMemberSerializer(
                {
                    "user_id": member.user_id,
                    "email": member.user.email,
                    "role": member.role,
                    "is_default": member.is_default,
                    "joined_at": member.created_at,
                }
            ).data,
            status=201,
        )


class OrganizationMemberDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request: Request, user_id: UUID) -> Response:
        user = cast(User, request.user)
        membership = get_default_membership(user)
        if not membership:
            return error_response(
                code="NO_ORGANIZATION",
                message="No default organization set for user.",
                status=404,
            )

        if not has_min_role(user, "admin"):
            return error_response(
                code="FORBIDDEN",
                message="You don't have permission to update members in this organization.",
                status=403,
            )

        serializer = OrganizationMemberUpdateSerializer(data=request.data)
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

        try:
            target = OrganizationMembership.objects.select_related("user").get(
                organization=membership.organization,
                user_id=user_id,
            )
        except OrganizationMembership.DoesNotExist:
            return error_response(
                code="NOT_FOUND",
                message="Member not found in this organization.",
                status=404,
            )

        new_role = serializer.validated_data["role"]
        if target.role == "owner" and new_role != "owner":
            owner_count = OrganizationMembership.objects.filter(
                organization=membership.organization, role="owner"
            ).count()
            if owner_count <= 1:
                return error_response(
                    code="LAST_OWNER",
                    message="Cannot remove the last owner from the organization.",
                    status=409,
                )

        target.role = new_role
        target.save(update_fields=["role"])

        return success_response(
            OrganizationMemberSerializer(
                {
                    "user_id": target.user_id,
                    "email": target.user.email,
                    "role": target.role,
                    "is_default": target.is_default,
                    "joined_at": target.created_at,
                }
            ).data
        )

    def delete(self, request: Request, user_id: UUID) -> Response:
        user = cast(User, request.user)
        membership = get_default_membership(user)
        if not membership:
            return error_response(
                code="NO_ORGANIZATION",
                message="No default organization set for user.",
                status=404,
            )

        if not has_min_role(user, "admin"):
            return error_response(
                code="FORBIDDEN",
                message="You don't have permission to remove members in this organization.",
                status=403,
            )

        try:
            target = OrganizationMembership.objects.select_related("user").get(
                organization=membership.organization,
                user_id=user_id,
            )
        except OrganizationMembership.DoesNotExist:
            return error_response(
                code="NOT_FOUND",
                message="Member not found in this organization.",
                status=404,
            )

        if target.role == "owner":
            owner_count = OrganizationMembership.objects.filter(
                organization=membership.organization, role="owner"
            ).count()
            if owner_count <= 1:
                return error_response(
                    code="LAST_OWNER",
                    message="Cannot remove the last owner from the organization.",
                    status=409,
                )

        if target.user.default_organization_id == membership.organization_id:
            User.objects.filter(pk=target.user_id).update(default_organization=None)

        target.delete()
        return success_response({"deleted": True})
