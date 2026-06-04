from __future__ import annotations

import json

from application.services.agency_account_catalog import ATLAS_DEPARTMENT_SLUGS
from application.services.agency_deliverable_catalog import MVP_DELIVERABLE_TYPES
from application.services.agency_playbooks import (
    ALLOWED_PLAYBOOK_AUDIENCES,
    ALLOWED_PLAYBOOK_RISK_CLASSIFICATIONS,
    ATLAS_PLAYBOOK_TEMPLATE_SLUGS,
    PlaybookTemplateDefinition,
    get_playbook_template,
    list_enabled_playbook_templates,
    list_playbook_templates,
    playbook_template_payload,
    validate_playbook_template_catalog,
)


def test_atlas_seed_playbook_slugs_are_stable_and_ordered() -> None:
    assert ATLAS_PLAYBOOK_TEMPLATE_SLUGS == (
        "agency.discovery_to_proposal",
        "agency.client_onboarding",
        "agency.campaign_audit",
        "agency.campaign_plan",
        "agency.launch_readiness_review",
        "agency.weekly_pulse",
        "agency.monthly_review",
        "agency.qbr",
        "agency.deliverable_qa",
        "agency.connector_gap_explainer",
    )

    templates = list_playbook_templates()

    assert tuple(template.slug for template in templates) == ATLAS_PLAYBOOK_TEMPLATE_SLUGS
    assert len({template.slug for template in templates}) == len(templates)
    assert list_enabled_playbook_templates() == templates


def test_atlas_seed_playbooks_have_required_metadata() -> None:
    templates = list_playbook_templates()

    assert validate_playbook_template_catalog() == ()
    for template in templates:
        assert template.label
        assert template.description
        assert template.required_context_keys
        assert all(key and key == key.strip() for key in template.required_context_keys)
        assert len(set(template.required_context_keys)) == len(template.required_context_keys)
        assert template.output_deliverable_type in MVP_DELIVERABLE_TYPES
        assert template.owner_department_slug in ATLAS_DEPARTMENT_SLUGS
        assert template.audience in ALLOWED_PLAYBOOK_AUDIENCES
        assert template.risk_classification in ALLOWED_PLAYBOOK_RISK_CLASSIFICATIONS
        assert isinstance(template.enabled, bool)


def test_get_playbook_template_returns_stable_seed_definitions() -> None:
    readiness = get_playbook_template("agency.launch_readiness_review")
    gap_explainer = get_playbook_template("agency.connector_gap_explainer")

    assert readiness is not None
    assert readiness.output_deliverable_type == "launch_readiness_checklist"
    assert readiness.owner_department_slug == "qa_compliance"
    assert readiness.risk_classification == "high"
    assert readiness.required_context_keys == (
        "connector_readiness",
        "approval_state",
        "deliverable_state",
        "qa_state",
        "tracking_state",
    )

    assert gap_explainer is not None
    assert gap_explainer.output_deliverable_type == "connector_gap_report"
    assert gap_explainer.owner_department_slug == "channel_execution"
    assert gap_explainer.audience == "client"

    assert get_playbook_template("agency.unknown") is None


def test_playbook_template_payload_is_client_safe_metadata() -> None:
    payload = playbook_template_payload(get_playbook_template("agency.weekly_pulse"))

    assert payload == {
        "slug": "agency.weekly_pulse",
        "label": "Weekly Pulse",
        "description": "Summarize short-cycle performance signals and next actions.",
        "required_context_keys": [
            "performance_summary",
            "recent_deliverables",
            "open_approvals",
        ],
        "output_deliverable_type": "performance_report",
        "owner_department_slug": "analytics_performance",
        "audience": "client",
        "risk_classification": "medium",
        "enabled": True,
    }

    serialized = json.dumps(
        [playbook_template_payload(template) for template in list_playbook_templates()],
        sort_keys=True,
    ).lower()
    for blocked in (
        "api-key",
        "api_key",
        "apikey",
        "access_token",
        "bearer ",
        "credential",
        "password",
        "private_key",
        "secret",
        "token=",
    ):
        assert blocked not in serialized


def test_catalog_validation_flags_invalid_metadata_and_sensitive_text() -> None:
    invalid = PlaybookTemplateDefinition(
        slug="agency.invalid",
        label="Invalid",
        description="Contains api_key=should-not-ship.",
        required_context_keys=(),
        output_deliverable_type="not_a_deliverable",
        owner_department_slug="unknown_department",
        audience="partner",
        risk_classification="critical",
        enabled="yes",  # type: ignore[arg-type]
    )

    errors = validate_playbook_template_catalog((invalid,))

    assert set(errors) == {
        "agency.invalid.required_context_keys",
        "agency.invalid.output_deliverable_type",
        "agency.invalid.owner_department_slug",
        "agency.invalid.audience",
        "agency.invalid.risk_classification",
        "agency.invalid.enabled",
        "agency.invalid.sensitive_text",
    }
