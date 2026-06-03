from __future__ import annotations

from infrastructure.orm.models import User

from .rbac import has_min_role

OPS_DEAD_LETTER_READ = "ops.dead_letter.read"
OPS_DEAD_LETTER_REPLAY = "ops.dead_letter.replay"
OPS_PROJECTION_READ = "ops.projection.read"
OPS_SNAPSHOT_RECOVERY_DRILL = "ops.snapshot_recovery_drill"

OPS_PERMISSIONS = {
    OPS_DEAD_LETTER_READ,
    OPS_DEAD_LETTER_REPLAY,
    OPS_PROJECTION_READ,
    OPS_SNAPSHOT_RECOVERY_DRILL,
}


def has_ops_permission(
    user: User,
    permission: str,
    organization_id: str | None = None,
) -> bool:
    if permission not in OPS_PERMISSIONS:
        return False
    return has_min_role(user, "admin", organization_id)
