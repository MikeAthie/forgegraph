"""Company access policy helpers.

These helpers keep company authorization in the backend control plane.  A user
must first belong to the organization, then either inherit access through the
company policy or hold an active company assignment.
"""

from __future__ import annotations

from django.db.models import Q, QuerySet
from django.utils import timezone

from application.services.rbac import ROLE_RANK, get_membership
from infrastructure.orm.models import CompanyAccessPolicy, CompanyAssignment, Graph, User

COMPANY_ROLE_RANK = {
    "viewer": 1,
    "member": 2,
    "admin": 3,
}


def has_company_access(user: User, company: Graph, minimum_role: str = "viewer") -> bool:
    """Return whether user can access company at the requested company role."""

    organization_id = getattr(company, "organization_id", None)
    if organization_id is None:
        return company.owner_id == user.id

    membership = get_membership(user, str(organization_id))
    if membership is None:
        return False

    required_rank = COMPANY_ROLE_RANK.get(minimum_role, COMPANY_ROLE_RANK["viewer"])
    assignment = _active_assignment(user=user, company=company)
    if assignment is not None and COMPANY_ROLE_RANK.get(assignment.role, 0) >= required_rank:
        return True

    policy = _policy_for_company(company)
    if policy.assignment_required:
        return bool(
            policy.org_admin_access_enabled
            and ROLE_RANK.get(membership.role, 0) >= ROLE_RANK["admin"]
            and _org_role_satisfies_company_role(membership.role, minimum_role)
        )

    return _org_role_satisfies_company_role(membership.role, minimum_role)


def accessible_company_queryset(
    user: User,
    *,
    minimum_role: str = "viewer",
) -> QuerySet[Graph]:
    """Return companies accessible to the user for list/read surfaces."""

    tenant_id = getattr(user, "default_organization_id", None)
    if not tenant_id:
        return Graph.objects.filter(owner=user)

    membership = get_membership(user, str(tenant_id))
    if membership is None:
        return Graph.objects.none()

    required_rank = COMPANY_ROLE_RANK.get(minimum_role, COMPANY_ROLE_RANK["viewer"])
    if _org_role_satisfies_company_role(membership.role, minimum_role):
        unrestricted = Q(access_policy__isnull=True) | Q(access_policy__assignment_required=False)
        if ROLE_RANK.get(membership.role, 0) >= ROLE_RANK["admin"]:
            unrestricted |= Q(
                access_policy__assignment_required=True,
                access_policy__org_admin_access_enabled=True,
            )
        assigned_company_ids = CompanyAssignment.objects.filter(
            user=user,
            organization_id=tenant_id,
            status="active",
        ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()))
        assigned_company_ids = assigned_company_ids.filter(
            role__in=_roles_at_or_above(required_rank)
        ).values("company_id")
        return Graph.objects.filter(
            Q(organization_id=tenant_id, organization__isnull=False) & unrestricted
            | Q(id__in=assigned_company_ids)
            | Q(organization__isnull=True, owner__default_organization_id=tenant_id)
        ).distinct()

    assigned_company_ids = CompanyAssignment.objects.filter(
        user=user,
        organization_id=tenant_id,
        status="active",
    ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()))
    assigned_company_ids = assigned_company_ids.filter(
        role__in=_roles_at_or_above(required_rank)
    ).values("company_id")
    return Graph.objects.filter(id__in=assigned_company_ids)


def ensure_default_company_access_policy(company: Graph) -> CompanyAccessPolicy | None:
    """Create the default compatible access policy for an organization-scoped company."""

    if company.organization_id is None:
        return None
    policy, _ = CompanyAccessPolicy.objects.get_or_create(
        company=company,
        defaults={"organization": company.organization},
    )
    return policy


def _policy_for_company(company: Graph) -> CompanyAccessPolicy:
    try:
        policy = company.access_policy
    except CompanyAccessPolicy.DoesNotExist:
        policy = None
    if isinstance(policy, CompanyAccessPolicy):
        return policy
    return CompanyAccessPolicy(
        organization=company.organization,
        company=company,
        assignment_required=False,
        org_admin_access_enabled=True,
        cross_client_learning_enabled=False,
    )


def _active_assignment(user: User, company: Graph) -> CompanyAssignment | None:
    now = timezone.now()
    return (
        CompanyAssignment.objects.filter(user=user, company=company, status="active")
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
        .first()
    )


def _org_role_satisfies_company_role(org_role: str, company_role: str) -> bool:
    org_rank = ROLE_RANK.get(org_role, 0)
    required_rank = COMPANY_ROLE_RANK.get(company_role, COMPANY_ROLE_RANK["viewer"])
    return org_rank >= required_rank


def _roles_at_or_above(required_rank: int) -> list[str]:
    return [
        role
        for role, rank in COMPANY_ROLE_RANK.items()
        if rank >= required_rank
    ]
