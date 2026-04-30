"""
Interaction layer domain entities.

Clean Architecture: Enterprise Business Rules layer.
These objects are framework-free and represent the Living Operating Brief contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class InteractionEventType(StrEnum):
    CREATE = "CREATE"
    MODIFY = "MODIFY"
    CLARIFY = "CLARIFY"
    CONSTRAINT = "CONSTRAINT"
    PRIORITY_SHIFT = "PRIORITY_SHIFT"
    APPROVE = "APPROVE"
    OVERRIDE = "OVERRIDE"


class InteractionActor(StrEnum):
    USER = "user"
    SYSTEM = "system"


class ProjectManagerAction(StrEnum):
    EXECUTE = "EXECUTE"
    ASK_CLARIFICATION = "ASK_CLARIFICATION"
    ASSUME_AND_CONTINUE = "ASSUME_AND_CONTINUE"
    BLOCK = "BLOCK"


class AutonomyMode(StrEnum):
    MANUAL = "manual"
    ASSISTED = "assisted"
    AUTONOMOUS = "autonomous"


@dataclass(slots=True)
class PriorityFrame:
    speed: float = 0.5
    cost: float = 0.5
    quality: float = 0.5
    risk: float = 0.5

    def normalized(self) -> PriorityFrame:
        return PriorityFrame(
            speed=_clamp_priority(self.speed),
            cost=_clamp_priority(self.cost),
            quality=_clamp_priority(self.quality),
            risk=_clamp_priority(self.risk),
        )


@dataclass(slots=True)
class AssumptionItem:
    field: str
    value: Any
    confidence: float
    created_at: datetime


@dataclass(slots=True)
class ClarificationItem:
    question: str
    blocking: bool
    related_field: str


@dataclass(slots=True)
class OperatingBrief:
    objective: str | None = None
    deliverable: str | None = None
    constraints: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)
    stakeholders: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    assumptions: list[AssumptionItem] = field(default_factory=list)
    clarifications: list[ClarificationItem] = field(default_factory=list)
    priority_frame: PriorityFrame = field(default_factory=PriorityFrame)
    autonomy_mode: AutonomyMode = AutonomyMode.ASSISTED


@dataclass(slots=True)
class InteractionEvent:
    type: InteractionEventType
    delta: dict[str, Any]
    actor: InteractionActor
    timestamp: datetime


def utc_now() -> datetime:
    return datetime.now(UTC)


def _clamp_priority(value: float) -> float:
    if value < 0:
        return 0.0
    if value > 1:
        return 1.0
    return round(value, 2)
