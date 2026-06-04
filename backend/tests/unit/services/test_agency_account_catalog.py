from __future__ import annotations

from application.services.agency_account_catalog import (
    ATLAS_DEPARTMENT_SLUGS,
    list_connector_definitions,
    list_health_dimension_definitions,
    list_onboarding_item_definitions,
)


def test_agency_account_catalog_uses_actual_atlas_department_slugs() -> None:
    expected_slugs = {
        "strategy_research",
        "brand_content",
        "channel_execution",
        "crm_lifecycle",
        "analytics_performance",
        "qa_compliance",
        "client_approval_ops",
    }

    assert ATLAS_DEPARTMENT_SLUGS == expected_slugs

    owner_slugs = {
        item.owner_department_slug
        for item in (
            *list_health_dimension_definitions(),
            *list_onboarding_item_definitions(),
            *list_connector_definitions(),
        )
    }
    assert owner_slugs <= expected_slugs


def test_agency_account_catalog_definitions_are_stable_and_unique() -> None:
    dimensions = list_health_dimension_definitions()
    onboarding_items = list_onboarding_item_definitions()
    connectors = list_connector_definitions()

    assert tuple(item.slug for item in dimensions) == (
        "onboarding",
        "connector_readiness",
        "delivery",
        "reporting",
        "approvals",
        "commercial",
    )
    assert sum(item.weight for item in dimensions) == 100
    assert len({item.slug for item in onboarding_items}) == len(onboarding_items)
    assert len({item.slug for item in connectors}) == len(connectors)
    assert {item.slug for item in connectors} >= {
        "email_connector",
        "whatsapp_connector",
        "social_connector",
        "analytics_connector",
    }
