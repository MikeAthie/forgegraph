"""Backend-owned Atlas agency playbook template catalog."""

from __future__ import annotations

from dataclasses import dataclass

from application.services.agency_account_catalog import ATLAS_DEPARTMENT_SLUGS
from application.services.agency_deliverable_catalog import MVP_DELIVERABLE_TYPES


@dataclass(frozen=True, slots=True)
class PlaybookTemplateDefinition:
    slug: str
    label: str
    description: str
    required_context_keys: tuple[str, ...]
    output_deliverable_type: str
    owner_department_slug: str
    audience: str
    risk_classification: str
    enabled: bool = True


ALLOWED_PLAYBOOK_AUDIENCES = ("agency_operator", "client", "executive")
ALLOWED_PLAYBOOK_RISK_CLASSIFICATIONS = ("low", "medium", "high")
ATLAS_PLAYBOOK_TEMPLATE_SLUGS = (
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
_SENSITIVE_TEXT_TOKENS = (
    "api-key",
    "api_key",
    "apikey",
    "access_token",
    "bearer ",
    "credential",
    "password",
    "private_key",
    "secret",
    "token",
)


PLAYBOOK_TEMPLATE_DEFINITIONS: tuple[PlaybookTemplateDefinition, ...] = (
    PlaybookTemplateDefinition(
        slug="agency.discovery_to_proposal",
        label="Discovery to Proposal",
        description="Convert discovery inputs into a proposal-ready strategy brief.",
        required_context_keys=(
            "client_profile",
            "brand_context",
            "service_goals",
            "commercial_context",
        ),
        output_deliverable_type="strategy_brief",
        owner_department_slug="strategy_research",
        audience="executive",
        risk_classification="medium",
    ),
    PlaybookTemplateDefinition(
        slug="agency.client_onboarding",
        label="Client Onboarding",
        description="Assemble onboarding context for an active agency engagement.",
        required_context_keys=(
            "client_profile",
            "brand_context",
            "service_engagement",
            "connector_readiness",
        ),
        output_deliverable_type="client_brief",
        owner_department_slug="client_approval_ops",
        audience="agency_operator",
        risk_classification="medium",
    ),
    PlaybookTemplateDefinition(
        slug="agency.campaign_audit",
        label="Campaign Audit",
        description="Review campaign evidence and summarize performance improvement paths.",
        required_context_keys=(
            "performance_summary",
            "connector_readiness",
            "recent_deliverables",
            "client_objectives",
        ),
        output_deliverable_type="performance_report",
        owner_department_slug="analytics_performance",
        audience="client",
        risk_classification="medium",
    ),
    PlaybookTemplateDefinition(
        slug="agency.campaign_plan",
        label="Campaign Plan",
        description="Turn strategy, audience, channel, and measurement inputs into a launch plan.",
        required_context_keys=(
            "strategy_brief",
            "target_audience",
            "channel_plan",
            "measurement_plan",
        ),
        output_deliverable_type="campaign_launch_package",
        owner_department_slug="strategy_research",
        audience="client",
        risk_classification="high",
    ),
    PlaybookTemplateDefinition(
        slug="agency.launch_readiness_review",
        label="Launch Readiness Review",
        description="Evaluate launch blockers before customer-facing execution begins.",
        required_context_keys=(
            "connector_readiness",
            "approval_state",
            "deliverable_state",
            "qa_state",
            "tracking_state",
        ),
        output_deliverable_type="launch_readiness_checklist",
        owner_department_slug="qa_compliance",
        audience="agency_operator",
        risk_classification="high",
    ),
    PlaybookTemplateDefinition(
        slug="agency.weekly_pulse",
        label="Weekly Pulse",
        description="Summarize short-cycle performance signals and next actions.",
        required_context_keys=(
            "performance_summary",
            "recent_deliverables",
            "open_approvals",
        ),
        output_deliverable_type="performance_report",
        owner_department_slug="analytics_performance",
        audience="client",
        risk_classification="medium",
    ),
    PlaybookTemplateDefinition(
        slug="agency.monthly_review",
        label="Monthly Review",
        description="Package monthly progress, learnings, and recommended priorities.",
        required_context_keys=(
            "monthly_performance_summary",
            "service_history",
            "deliverable_status",
            "recommendations",
        ),
        output_deliverable_type="performance_report",
        owner_department_slug="analytics_performance",
        audience="client",
        risk_classification="medium",
    ),
    PlaybookTemplateDefinition(
        slug="agency.qbr",
        label="QBR",
        description="Prepare quarterly business review narrative and executive actions.",
        required_context_keys=(
            "quarterly_performance_summary",
            "commercial_context",
            "strategic_priorities",
            "service_history",
        ),
        output_deliverable_type="performance_report",
        owner_department_slug="strategy_research",
        audience="executive",
        risk_classification="medium",
    ),
    PlaybookTemplateDefinition(
        slug="agency.deliverable_qa",
        label="Deliverable QA",
        description="Check customer-facing deliverables for approval readiness.",
        required_context_keys=(
            "deliverable_state",
            "quality_gate",
            "approval_requirements",
        ),
        output_deliverable_type="approval_packet",
        owner_department_slug="qa_compliance",
        audience="agency_operator",
        risk_classification="high",
    ),
    PlaybookTemplateDefinition(
        slug="agency.connector_gap_explainer",
        label="Connector Gap Explainer",
        description="Explain connector readiness gaps and the customer-safe path to resolution.",
        required_context_keys=(
            "connector_readiness",
            "service_engagement",
            "blocked_channels",
        ),
        output_deliverable_type="connector_gap_report",
        owner_department_slug="channel_execution",
        audience="client",
        risk_classification="low",
    ),
)
_PLAYBOOKS_BY_SLUG = {template.slug: template for template in PLAYBOOK_TEMPLATE_DEFINITIONS}


def list_playbook_templates() -> tuple[PlaybookTemplateDefinition, ...]:
    return PLAYBOOK_TEMPLATE_DEFINITIONS


def list_enabled_playbook_templates() -> tuple[PlaybookTemplateDefinition, ...]:
    return tuple(template for template in PLAYBOOK_TEMPLATE_DEFINITIONS if template.enabled)


def get_playbook_template(slug: str) -> PlaybookTemplateDefinition | None:
    return _PLAYBOOKS_BY_SLUG.get(slug)


def playbook_template_payload(template: PlaybookTemplateDefinition | None) -> dict[str, object]:
    if template is None:
        raise ValueError("Playbook template is required.")
    return {
        "slug": template.slug,
        "label": template.label,
        "description": template.description,
        "required_context_keys": list(template.required_context_keys),
        "output_deliverable_type": template.output_deliverable_type,
        "owner_department_slug": template.owner_department_slug,
        "audience": template.audience,
        "risk_classification": template.risk_classification,
        "enabled": template.enabled,
    }


def validate_playbook_template_catalog(
    templates: tuple[PlaybookTemplateDefinition, ...] | None = None,
) -> tuple[str, ...]:
    catalog = templates or PLAYBOOK_TEMPLATE_DEFINITIONS
    errors: list[str] = []
    seen_slugs: set[str] = set()
    for template in catalog:
        errors.extend(_template_validation_errors(template, seen_slugs=seen_slugs))
    return tuple(errors)


def _template_validation_errors(
    template: PlaybookTemplateDefinition,
    *,
    seen_slugs: set[str],
) -> tuple[str, ...]:
    prefix = template.slug or "playbook_template"
    duplicate = bool(template.slug and template.slug in seen_slugs)
    if template.slug:
        seen_slugs.add(template.slug)
    checks = (
        ("slug", not template.slug),
        ("duplicate_slug", duplicate),
        ("label", not template.label.strip()),
        ("description", not template.description.strip()),
        ("required_context_keys", not _valid_context_keys(template.required_context_keys)),
        ("output_deliverable_type", template.output_deliverable_type not in MVP_DELIVERABLE_TYPES),
        ("owner_department_slug", template.owner_department_slug not in ATLAS_DEPARTMENT_SLUGS),
        ("audience", template.audience not in ALLOWED_PLAYBOOK_AUDIENCES),
        (
            "risk_classification",
            template.risk_classification not in ALLOWED_PLAYBOOK_RISK_CLASSIFICATIONS,
        ),
        ("enabled", not isinstance(template.enabled, bool)),
        ("sensitive_text", _contains_sensitive_text(playbook_template_payload(template))),
    )
    return tuple(f"{prefix}.{field}" for field, invalid in checks if invalid)


def _valid_context_keys(keys: tuple[str, ...]) -> bool:
    if not keys:
        return False
    normalized = [key.strip() for key in keys if isinstance(key, str)]
    return len(normalized) == len(keys) and all(normalized) and len(set(normalized)) == len(keys)


def _contains_sensitive_text(value: object) -> bool:
    if isinstance(value, str):
        normalized = value.strip().lower()
        return any(token in normalized for token in _SENSITIVE_TEXT_TOKENS)
    if isinstance(value, dict):
        return any(
            _contains_sensitive_text(key) or _contains_sensitive_text(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple, set)):
        return any(_contains_sensitive_text(item) for item in value)
    return False


_CATALOG_VALIDATION_ERRORS = validate_playbook_template_catalog()
if _CATALOG_VALIDATION_ERRORS:
    joined_errors = ", ".join(_CATALOG_VALIDATION_ERRORS)
    raise ValueError(f"Invalid Atlas agency playbook template catalog: {joined_errors}")
