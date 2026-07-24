"""Atlas agency account catalog definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

ATLAS_DEPARTMENT_SLUGS = {
    "strategy_research",
    "brand_content",
    "channel_execution",
    "crm_lifecycle",
    "analytics_performance",
    "qa_compliance",
    "client_approval_ops",
}


@dataclass(frozen=True, slots=True)
class HealthDimensionDefinition:
    slug: str
    label: str
    weight: int
    owner_department_slug: str


@dataclass(frozen=True, slots=True)
class OnboardingItemDefinition:
    slug: str
    label: str
    owner_department_slug: str


@dataclass(frozen=True, slots=True)
class ConnectorDefinition:
    slug: str
    label: str
    category: str
    owner_department_slug: str
    required: bool = True
    aliases: tuple[str, ...] = ()
    platforms: tuple[str, ...] = ()


HEALTH_DIMENSION_DEFINITIONS: tuple[HealthDimensionDefinition, ...] = (
    HealthDimensionDefinition(
        slug="onboarding",
        label="Onboarding",
        weight=20,
        owner_department_slug="client_approval_ops",
    ),
    HealthDimensionDefinition(
        slug="connector_readiness",
        label="Connector Readiness",
        weight=25,
        owner_department_slug="channel_execution",
    ),
    HealthDimensionDefinition(
        slug="delivery",
        label="Delivery",
        weight=20,
        owner_department_slug="qa_compliance",
    ),
    HealthDimensionDefinition(
        slug="reporting",
        label="Reporting",
        weight=15,
        owner_department_slug="analytics_performance",
    ),
    HealthDimensionDefinition(
        slug="approvals",
        label="Approvals",
        weight=10,
        owner_department_slug="client_approval_ops",
    ),
    HealthDimensionDefinition(
        slug="commercial",
        label="Commercial",
        weight=10,
        owner_department_slug="strategy_research",
    ),
)

ONBOARDING_ITEM_DEFINITIONS: tuple[OnboardingItemDefinition, ...] = (
    OnboardingItemDefinition(
        slug="client_profile",
        label="Client profile",
        owner_department_slug="client_approval_ops",
    ),
    OnboardingItemDefinition(
        slug="brand_context",
        label="Brand context",
        owner_department_slug="brand_content",
    ),
    OnboardingItemDefinition(
        slug="service_engagement",
        label="Service engagement",
        owner_department_slug="client_approval_ops",
    ),
    OnboardingItemDefinition(
        slug="connector_setup",
        label="Connector setup",
        owner_department_slug="channel_execution",
    ),
    OnboardingItemDefinition(
        slug="approval_workflow",
        label="Approval workflow",
        owner_department_slug="client_approval_ops",
    ),
    OnboardingItemDefinition(
        slug="reporting_cadence",
        label="Reporting cadence",
        owner_department_slug="analytics_performance",
    ),
)

CONNECTOR_DEFINITIONS: tuple[ConnectorDefinition, ...] = (
    ConnectorDefinition(
        slug="email_connector",
        label="Email",
        category="owned_channel",
        owner_department_slug="channel_execution",
        aliases=("email", "gmail", "smtp"),
        platforms=("email",),
    ),
    ConnectorDefinition(
        slug="whatsapp_connector",
        label="WhatsApp",
        category="messaging",
        owner_department_slug="channel_execution",
        aliases=("whatsapp", "twilio_whatsapp", "whatsapp_cloud_api"),
        platforms=("whatsapp",),
    ),
    ConnectorDefinition(
        slug="social_connector",
        label="Social publishing",
        category="paid_social",
        owner_department_slug="channel_execution",
        aliases=(
            "social",
            "social_publishing",
            "meta",
            "facebook",
            "instagram",
            "tiktok",
            "tiktok_publishing_connector",
        ),
        platforms=("social", "facebook", "instagram", "tiktok"),
    ),
    ConnectorDefinition(
        slug="analytics_connector",
        label="Analytics",
        category="measurement",
        owner_department_slug="analytics_performance",
        aliases=(
            "analytics",
            "google_analytics",
            "ga4",
            "social_analytics_connector",
            "measurement_connector",
        ),
        platforms=("analytics", "google_analytics", "ga4"),
    ),
)


def list_health_dimension_definitions() -> tuple[HealthDimensionDefinition, ...]:
    return HEALTH_DIMENSION_DEFINITIONS


def list_onboarding_item_definitions() -> tuple[OnboardingItemDefinition, ...]:
    return ONBOARDING_ITEM_DEFINITIONS


def list_connector_definitions() -> tuple[ConnectorDefinition, ...]:
    return CONNECTOR_DEFINITIONS


def get_health_dimension_definition(slug: str) -> HealthDimensionDefinition | None:
    return _by_slug(HEALTH_DIMENSION_DEFINITIONS).get(slug)


def get_onboarding_item_definition(slug: str) -> OnboardingItemDefinition | None:
    return _by_slug(ONBOARDING_ITEM_DEFINITIONS).get(slug)


def get_connector_definition(slug: str) -> ConnectorDefinition | None:
    return _by_slug(CONNECTOR_DEFINITIONS).get(slug)


def connector_slug_for_value(value: object) -> str:
    normalized = _normalize_slug(value)
    for definition in CONNECTOR_DEFINITIONS:
        candidates = {definition.slug, *definition.aliases, *definition.platforms}
        if normalized in {_normalize_slug(candidate) for candidate in candidates}:
            return definition.slug
    return normalized


class _SlugDefinition(Protocol):
    @property
    def slug(self) -> str: ...


def _by_slug[SlugDefinitionT: _SlugDefinition](
    items: tuple[SlugDefinitionT, ...],
) -> dict[str, SlugDefinitionT]:
    return {item.slug: item for item in items}


def _normalize_slug(value: object) -> str:
    return str(value or "").strip().lower().replace("-", "_")
