from __future__ import annotations

from typing import cast
from uuid import UUID

from infrastructure.orm.models import OrganizationMembership, User


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
