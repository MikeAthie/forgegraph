from __future__ import annotations

from infrastructure.orm.models import DomainEvent


def apply(event: DomainEvent) -> None:
    """Memory observations are already backend-owned canonical rows in Phase 1."""

    return None
