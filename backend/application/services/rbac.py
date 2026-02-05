from __future__ import annotations

from infrastructure.orm.models import OrganizationMembership, User

ROLE_RANK = {
    "viewer": 1,
    "member": 2,
    "admin": 3,
    "owner": 4,
}


def get_membership(user: User, organization_id: str | None = None) -> OrganizationMembership | None:
    org_id = organization_id or getattr(user, "default_organization_id", None)
    if not org_id:
        return None
    return OrganizationMembership.objects.filter(user=user, organization_id=org_id).first()


def has_min_role(user: User, minimum_role: str, organization_id: str | None = None) -> bool:
    membership = get_membership(user, organization_id)
    if not membership:
        return False
    return ROLE_RANK.get(membership.role, 0) >= ROLE_RANK.get(minimum_role, 0)


def has_any_role(user: User, roles: set[str], organization_id: str | None = None) -> bool:
    membership = get_membership(user, organization_id)
    if not membership:
        return False
    return membership.role in roles
