"""Department registry and ownership permission helpers."""

from __future__ import annotations

from typing import Any

from django.db.models import Q, QuerySet
from django.utils import timezone

from application.services.company_access import has_company_access
from application.services.rbac import has_min_role
from infrastructure.orm.models import (
    DepartmentMembership,
    DepartmentRegistry,
    Graph,
    Organization,
    OrganizationMembership,
    User,
)

DEPARTMENT_ROLE_RANK = {
    "viewer": 1,
    "member": 2,
    "lead": 3,
}


class DepartmentError(ValueError):
    """Domain error for department registry and RBAC operations."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.details = details or []
        super().__init__(message)


def department_queryset_for_user(user: User) -> QuerySet[DepartmentRegistry]:
    organization = user.default_organization
    if organization is None:
        return DepartmentRegistry.objects.none()
    queryset = DepartmentRegistry.objects.filter(organization=organization)
    if is_department_admin(user, organization):
        return queryset
    return queryset.filter(memberships__in=_active_memberships(user=user)).distinct()


def is_department_admin(user: User, organization: Organization) -> bool:
    return has_min_role(user, "admin", str(organization.id))


def has_department_role(
    user: User,
    department: DepartmentRegistry,
    minimum_role: str,
) -> bool:
    """Return whether user has a department role, with org admin/owner override."""

    if is_department_admin(user, department.organization):
        return True
    required_rank = DEPARTMENT_ROLE_RANK.get(minimum_role, DEPARTMENT_ROLE_RANK["viewer"])
    membership = active_department_membership(user=user, department=department)
    return membership is not None and DEPARTMENT_ROLE_RANK.get(membership.role, 0) >= required_rank


def active_department_membership(
    *,
    user: User,
    department: DepartmentRegistry,
) -> DepartmentMembership | None:
    return _active_memberships(user=user).filter(department=department).first()


def can_read_department(user: User, department: DepartmentRegistry) -> bool:
    return has_department_role(user, department, "viewer")


def can_manage_department(user: User, department: DepartmentRegistry) -> bool:
    return has_department_role(user, department, "lead")


def can_manage_department_member(
    *,
    actor: User,
    department: DepartmentRegistry,
    target_role: str,
) -> bool:
    if is_department_admin(actor, department.organization):
        return True
    if target_role == "lead":
        return False
    return has_department_role(actor, department, "lead")


def can_read_department_work(
    *,
    user: User,
    company: Graph,
    department: DepartmentRegistry,
) -> bool:
    if department.organization_id != company.organization_id:
        return False
    if not has_company_access(user, company, "viewer"):
        return False
    return has_department_role(user, department, "viewer")


def can_mutate_department_work(
    *,
    user: User,
    company: Graph,
    department: DepartmentRegistry,
) -> bool:
    if department.organization_id != company.organization_id:
        return False
    if not has_company_access(user, company, "member"):
        return False
    return has_department_role(user, department, "lead")


def department_payload(
    department: DepartmentRegistry, *, user: User | None = None
) -> dict[str, Any]:
    payload = {
        "id": str(department.id),
        "organization_id": str(department.organization_id),
        "slug": department.slug,
        "name": department.name,
        "department_type": department.department_type,
        "lead_user_id": str(department.lead_user_id) if department.lead_user_id else None,
        "service_tags": list(department.service_tags_json or []),
        "active": department.active,
        "metadata": dict(department.metadata_json or {}),
        "created_at": department.created_at.isoformat(),
        "updated_at": department.updated_at.isoformat(),
    }
    if user is not None:
        payload["role"] = department_role_for_user(user=user, department=department)
        payload["can_manage"] = can_manage_department(user, department)
    return payload


def department_membership_payload(membership: DepartmentMembership) -> dict[str, Any]:
    return {
        "id": str(membership.id),
        "organization_id": str(membership.organization_id),
        "department_id": str(membership.department_id),
        "user_id": str(membership.user_id),
        "role": membership.role,
        "status": membership.status,
        "expires_at": membership.expires_at.isoformat() if membership.expires_at else None,
        "metadata": dict(membership.metadata_json or {}),
        "created_by_id": str(membership.created_by_id) if membership.created_by_id else None,
        "created_at": membership.created_at.isoformat(),
        "updated_at": membership.updated_at.isoformat(),
    }


def department_role_for_user(*, user: User, department: DepartmentRegistry) -> str | None:
    if is_department_admin(user, department.organization):
        return "admin"
    membership = active_department_membership(user=user, department=department)
    return membership.role if membership is not None else None


def assert_user_belongs_to_department_org(
    *,
    user: User,
    department: DepartmentRegistry,
) -> None:
    if not OrganizationMembership.objects.filter(
        organization=department.organization,
        user=user,
    ).exists():
        raise DepartmentError(
            "user_not_in_organization",
            "Department members must belong to the department organization.",
        )


def _active_memberships(*, user: User) -> QuerySet[DepartmentMembership]:
    now = timezone.now()
    return (
        DepartmentMembership.objects.filter(user=user, status="active")
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
        .select_related("department")
    )
