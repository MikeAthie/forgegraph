from __future__ import annotations

from application.services.agency_deliverable_catalog import (
    MVP_DELIVERABLE_TYPES,
    get_deliverable_definition,
    list_deliverable_definitions,
)


def test_mvp_catalog_contains_all_deliverable_types() -> None:
    assert MVP_DELIVERABLE_TYPES == (
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

    definitions = list_deliverable_definitions()

    assert tuple(definition.type for definition in definitions) == MVP_DELIVERABLE_TYPES
    for definition in definitions:
        assert definition.label
        assert definition.group
        assert definition.owner_department_slug
        assert definition.visibility == "customer"
        assert isinstance(definition.requires_approval, bool)
        assert definition.source_kinds


def test_mvp_catalog_owner_department_slugs_are_atlas_department_slugs() -> None:
    allowed_slugs = {
        "strategy_research",
        "brand_content",
        "channel_execution",
        "crm_lifecycle",
        "analytics_performance",
        "qa_compliance",
        "client_approval_ops",
    }
    expected_mapping = {
        "client_brief": "client_approval_ops",
        "strategy_brief": "strategy_research",
        "message_house": "brand_content",
        "launch_readiness_checklist": "qa_compliance",
        "connector_gap_report": "channel_execution",
        "measurement_plan": "analytics_performance",
        "approval_packet": "client_approval_ops",
        "execution_receipt": "channel_execution",
        "performance_report": "analytics_performance",
        "campaign_launch_package": "client_approval_ops",
    }

    actual_mapping = {
        definition.type: definition.owner_department_slug
        for definition in list_deliverable_definitions()
    }

    assert set(actual_mapping.values()) <= allowed_slugs
    assert actual_mapping == expected_mapping


def test_get_deliverable_definition_returns_known_definition() -> None:
    definition = get_deliverable_definition("strategy_brief")

    assert definition is not None
    assert definition.type == "strategy_brief"
    assert definition.owner_department_slug == "strategy_research"


def test_get_deliverable_definition_returns_none_for_unknown_type() -> None:
    assert get_deliverable_definition("unknown") is None
