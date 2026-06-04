"""Canonical Atlas agency deliverable definitions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DeliverableDefinition:
    type: str
    label: str
    group: str
    owner_department_slug: str
    visibility: str = "customer"
    requires_approval: bool = False
    source_kinds: tuple[str, ...] = ()


MVP_DELIVERABLE_TYPES = (
    "client_brief",
    "strategy_brief",
    "message_house",
    "launch_readiness_checklist",
    "connector_gap_report",
    "measurement_plan",
    "approval_packet",
    "execution_receipt",
    "performance_report",
    "campaign_launch_package",
)

DELIVERABLE_DEFINITIONS: dict[str, DeliverableDefinition] = {
    "client_brief": DeliverableDefinition(
        type="client_brief",
        label="Client Brief",
        group="intake",
        owner_department_slug="client_approval_ops",
        source_kinds=("whiteboard",),
    ),
    "strategy_brief": DeliverableDefinition(
        type="strategy_brief",
        label="Strategy Brief",
        group="strategy",
        owner_department_slug="strategy_research",
        source_kinds=("whiteboard", "phase"),
    ),
    "message_house": DeliverableDefinition(
        type="message_house",
        label="Message House",
        group="strategy",
        owner_department_slug="brand_content",
        source_kinds=("whiteboard", "phase"),
    ),
    "launch_readiness_checklist": DeliverableDefinition(
        type="launch_readiness_checklist",
        label="Launch Readiness Checklist",
        group="deployment",
        owner_department_slug="qa_compliance",
        requires_approval=True,
        source_kinds=("whiteboard", "phase", "approval"),
    ),
    "connector_gap_report": DeliverableDefinition(
        type="connector_gap_report",
        label="Connector Gap Report",
        group="deployment",
        owner_department_slug="channel_execution",
        source_kinds=("whiteboard", "deployment"),
    ),
    "measurement_plan": DeliverableDefinition(
        type="measurement_plan",
        label="Measurement Plan",
        group="measurement",
        owner_department_slug="analytics_performance",
        source_kinds=("whiteboard", "performance"),
    ),
    "approval_packet": DeliverableDefinition(
        type="approval_packet",
        label="Approval Packet",
        group="approval",
        owner_department_slug="client_approval_ops",
        requires_approval=True,
        source_kinds=("whiteboard", "approval"),
    ),
    "execution_receipt": DeliverableDefinition(
        type="execution_receipt",
        label="Execution Receipt",
        group="deployment",
        owner_department_slug="channel_execution",
        source_kinds=("whiteboard", "deployment"),
    ),
    "performance_report": DeliverableDefinition(
        type="performance_report",
        label="Performance Report",
        group="measurement",
        owner_department_slug="analytics_performance",
        source_kinds=("whiteboard", "performance"),
    ),
    "campaign_launch_package": DeliverableDefinition(
        type="campaign_launch_package",
        label="Campaign Launch Package",
        group="package",
        owner_department_slug="client_approval_ops",
        requires_approval=True,
        source_kinds=("whiteboard", "phase", "deployment", "performance", "approval", "package"),
    ),
}


def list_deliverable_definitions() -> tuple[DeliverableDefinition, ...]:
    return tuple(DELIVERABLE_DEFINITIONS[deliverable_type] for deliverable_type in MVP_DELIVERABLE_TYPES)


def get_deliverable_definition(deliverable_type: str) -> DeliverableDefinition | None:
    return DELIVERABLE_DEFINITIONS.get(deliverable_type)
