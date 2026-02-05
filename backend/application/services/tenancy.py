from __future__ import annotations

from typing import cast
from uuid import UUID

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


def ensure_default_organization(user: User) -> OrganizationMembership:
    """
    Ensure a user has a default organization and membership.

    Creates a new organization + owner membership if missing.
    """
    org = getattr(user, "default_organization", None)
    if org:
        membership = OrganizationMembership.objects.filter(
            user=user,
            organization=org,
        ).first()
        if membership:
            if not membership.is_default:
                membership.is_default = True
                membership.save(update_fields=["is_default"])
            return membership

    org_name = f"{(user.email or 'Workspace').split('@')[0]}'s Workspace"
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
