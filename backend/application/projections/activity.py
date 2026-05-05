from __future__ import annotations

from infrastructure.orm.models import DomainEvent


def apply(event: DomainEvent) -> None:
    """Activity summaries read backend-owned run/task state directly in Phase 1."""

    return None
