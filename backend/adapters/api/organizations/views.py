from __future__ import annotations

from typing import cast
from uuid import UUID

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.organizations.serializers import (
    OrganizationCreateSerializer,
    OrganizationListItemSerializer,
    OrganizationMemberCreateSerializer,
    OrganizationMemberSerializer,
    OrganizationMemberUpdateSerializer,
    OrganizationSerializer,
    OrganizationSwitchSerializer,
)
from adapters.api.responses import error_response, success_response
from application.services.audit_log import record_audit_log
from application.services.rbac import has_min_role
from application.services.tenancy import (
    create_organization_for_user,
    ensure_default_organization,
    get_default_membership,
    get_memberships_for_user,
    set_default_organization,
)
from infrastructure.orm.models import OrganizationMembership, User


def _role_capabilities() -> dict[str, dict[str, bool]]:
    return {
        "owner": {
            "can_view_observations": True,
            "can_delete_observations": True,
            "can_manage_retention": True,
            "can_export_memory_data": True,
            "can_manage_members": True,
        },
        "admin": {
            "can_view_observations": True,
            "can_delete_observations": True,
            "can_manage_retention": True,
            "can_export_memory_data": True,
            "can_manage_members": True,
        },
        "member": {
            "can_view_observations": True,
            "can_delete_observations": True,
            "can_manage_retention": False,
            "can_export_memory_data": False,
            "can_manage_members": False,
        },
        "viewer": {
            "can_view_observations": True,
            "can_delete_observations": False,
            "can_manage_retention": False,
            "can_export_memory_data": False,
            "can_manage_members": False,
        },
    }


def _organization_list_item(member: OrganizationMembership) -> dict[str, object]:
    return {
        "id": member.organization_id,
        "name": member.organization.name,
        "created_at": member.organization.created_at,
        "updated_at": member.organization.updated_at,
        "role": member.role,
        "is_default": member.is_default,
        "joined_at": member.created_at,
    }


def _validation_error(serializer: object) -> Response:
    serializer_errors = cast(dict[str, list[str]], getattr(serializer, "errors", {}))
    return error_response(
        code="VALIDATION_ERROR",
        message="The request contains invalid fields",
        status=status.HTTP_400_BAD_REQUEST,
        details=[
            {"field": field, "issue": ", ".join(str(error) for error in errors)}
            for field, errors in serializer_errors.items()
        ],
    )


class OrganizationListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        ensure_default_organization(user)
        memberships = get_memberships_for_user(user)
        data = OrganizationListItemSerializer(
            [_organization_list_item(member) for member in memberships],
            many=True,
        ).data
        return success_response(data)

    def post(self, request: Request) -> Response:
        user = cast(User, request.user)
        serializer = OrganizationCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer)

        try:
            membership = create_organization_for_user(
                user,
                name=serializer.validated_data["name"],
                make_default=serializer.validated_data["make_default"],
            )
        except ValueError as exc:
            return error_response(
                code="VALIDATION_ERROR",
                message=str(exc),
                status=status.HTTP_400_BAD_REQUEST,
            )

        return success_response(
            OrganizationListItemSerializer(_organization_list_item(membership)).data,
            status=status.HTTP_201_CREATED,
        )


class OrganizationCurrentView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request: Request) -> Response:
        user = cast(User, request.user)
        serializer = OrganizationSwitchSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer)

        try:
            membership = set_default_organization(
                user,
                serializer.validated_data["organization_id"],
            )
        except PermissionError:
            return error_response(
                code="FORBIDDEN",
                message="You are not a member of that organization.",
                status=status.HTTP_403_FORBIDDEN,
            )

        return success_response(
            OrganizationListItemSerializer(_organization_list_item(membership)).data
        )


class OrganizationMeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        membership = ensure_default_organization(user)

        org = membership.organization
        role_capabilities = _role_capabilities()
        payload = {
            "organization": OrganizationSerializer(org).data,
            "organizations": OrganizationListItemSerializer(
                [_organization_list_item(member) for member in get_memberships_for_user(user)],
                many=True,
            ).data,
            "role": membership.role,
            "governance": {
                "current_role_capabilities": role_capabilities[membership.role],
                "role_capabilities": role_capabilities,
            },
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
        record_audit_log(
            actor=user,
            tenant_id=str(membership.organization_id),
            action="org.member_added",
            resource_type="organization_membership",
            resource_id=str(member.id),
            metadata={
                "target_user_id": str(target_user.id),
                "role": role,
            },
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
        record_audit_log(
            actor=user,
            tenant_id=str(membership.organization_id),
            action="org.member_role_updated",
            resource_type="organization_membership",
            resource_id=str(target.id),
            metadata={
                "target_user_id": str(target.user_id),
                "role": new_role,
            },
        )

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

        target_id = str(target.id)
        target_user_id = str(target.user_id)
        target_role = target.role
        target.delete()
        record_audit_log(
            actor=user,
            tenant_id=str(membership.organization_id),
            action="org.member_removed",
            resource_type="organization_membership",
            resource_id=target_id,
            metadata={
                "target_user_id": target_user_id,
                "role": target_role,
            },
        )
        return success_response({"deleted": True})
