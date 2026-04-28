from __future__ import annotations

from typing import cast
from uuid import UUID

from django.db.models import QuerySet

from infrastructure.orm.models import Organization, OrganizationMembership, User


def get_tenant_id_for_user(user: User) -> str:
    if hasattr(user, "default_organization_id") and user.default_organization_id:
        return str(user.default_organization_id)
    return str(user.id)


def get_default_membership(user: User) -> OrganizationMembership | None:
    org_id = getattr(user, "default_organization_id", None)
    if org_id is None:
        return None
    org_id = cast(UUID, org_id)
    return OrganizationMembership.objects.filter(user=user, organization_id=org_id).first()


def get_memberships_for_user(user: User) -> QuerySet[OrganizationMembership]:
    return (
        OrganizationMembership.objects.select_related("organization")
        .filter(user=user)
        .order_by("-is_default", "organization__name", "created_at")
    )


def set_default_organization(user: User, organization_id: UUID) -> OrganizationMembership:
    membership = (
        OrganizationMembership.objects.select_related("organization")
        .filter(
            user=user,
            organization_id=organization_id,
        )
        .first()
    )
    if membership is None:
        raise PermissionError("User is not a member of this organization.")

    OrganizationMembership.objects.filter(user=user, is_default=True).exclude(
        pk=membership.pk
    ).update(is_default=False)
    if not membership.is_default:
        membership.is_default = True
        membership.save(update_fields=["is_default", "updated_at"])

    if user.default_organization_id != organization_id:
        user.default_organization = membership.organization
        user.save(update_fields=["default_organization"])

    return membership


def create_organization_for_user(
    user: User,
    *,
    name: str,
    make_default: bool = True,
) -> OrganizationMembership:
    normalized_name = name.strip()
    if not normalized_name:
        raise ValueError("Organization name is required.")

    organization = Organization.objects.create(name=normalized_name)
    membership = OrganizationMembership.objects.create(
        organization=organization,
        user=user,
        role="owner",
        is_default=False,
    )
    if make_default:
        membership = set_default_organization(user, organization.id)
    return membership


def ensure_default_organization(user: User) -> OrganizationMembership:
    """
    Ensure a user has a default organization and membership.

    Creates a new organization + owner membership if missing.
    """
    db_default_org_id = (
        User.objects.filter(pk=user.pk)
        .values_list(
            "default_organization_id",
            flat=True,
        )
        .first()
    )
    if db_default_org_id and user.default_organization_id != db_default_org_id:
        user.default_organization_id = db_default_org_id

    if user.default_organization_id:
        organization = Organization.objects.filter(pk=user.default_organization_id).first()
        if organization:
            user.default_organization = organization
            membership, _ = OrganizationMembership.objects.get_or_create(
                user=user,
                organization=organization,
                defaults={"role": "owner", "is_default": True},
            )
            OrganizationMembership.objects.filter(user=user, is_default=True).exclude(
                pk=membership.pk
            ).update(is_default=False)
            if not membership.is_default:
                membership.is_default = True
                membership.save(update_fields=["is_default", "updated_at"])
            return membership

    org_name = f"{(user.email or 'Organization').split('@')[0]}'s Organization"
    organization = Organization.objects.create(name=org_name)
    membership = OrganizationMembership.objects.create(
        organization=organization,
        user=user,
        role="owner",
        is_default=True,
    )
    user.default_organization = organization
    user.save(update_fields=["default_organization"])
    return membership
