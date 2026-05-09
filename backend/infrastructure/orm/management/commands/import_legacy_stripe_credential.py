from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db.models import Q

from application.services.commerce import ensure_storefront_profile, safe_json_dump
from application.services.provider_credentials import (
    ProviderCredentialImportError,
    import_provider_credential,
)
from infrastructure.orm.management.commands.seed_legacy_glasswear_phase0 import (
    DEFAULT_COMPANY_NAME,
    DEFAULT_EMAIL,
    EXTERNAL_REF,
    EXTERNAL_SOURCE,
)
from infrastructure.orm.models import Graph, OrganizationMembership, User

LEGACY_STRIPE_ENV = "STRIPE_LEGACY"
LEGACY_STRIPE_CREDENTIAL_NAME = "Legacy Stripe Test"


class Command(BaseCommand):
    help = "Import STRIPE_LEGACY into the Legacy organization as an encrypted Stripe key."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--email", default=DEFAULT_EMAIL)
        parser.add_argument("--env-var", default=LEGACY_STRIPE_ENV)
        parser.add_argument("--json", action="store_true", dest="output_json")

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            result = _import_legacy_stripe_credential(
                email=str(options["email"]),
                env_var=str(options["env_var"]),
            )
        except ProviderCredentialImportError as exc:
            raise CommandError(str(exc)) from exc

        payload = result
        if options["output_json"]:
            self.stdout.write(safe_json_dump(payload))
            return

        self.stdout.write(
            self.style.SUCCESS(
                "Imported Legacy Stripe credential "
                f"(credential_id={payload['credential_id']}, key_present={payload['key_present']})"
            )
        )


def _import_legacy_stripe_credential(*, email: str, env_var: str) -> dict[str, Any]:
    email = email.strip().lower() or DEFAULT_EMAIL
    user = User.objects.select_related("default_organization").filter(email=email).first()
    if user is None or user.default_organization_id is None:
        raise ProviderCredentialImportError(
            "Legacy Phase 0 workspace is missing. Run seed_legacy_glasswear_phase0 first."
        )
    memberships = OrganizationMembership.objects.filter(user=user)
    if memberships.count() != 1:
        raise ProviderCredentialImportError(
            "Legacy user must have exactly one organization membership before Phase 3."
        )
    organization = user.default_organization
    if organization is None:
        raise ProviderCredentialImportError(
            "Legacy Phase 0 organization is missing. Run seed_legacy_glasswear_phase0 first."
        )
    graph = (
        Graph.objects.filter(
            organization=organization,
            external_source=EXTERNAL_SOURCE,
            external_ref=EXTERNAL_REF,
        )
        .select_related("organization")
        .first()
    )
    if graph is None:
        raise ProviderCredentialImportError(
            "Legacy company graph is missing. Run seed_legacy_glasswear_phase0 first."
        )
    visible_company_count = (
        Graph.objects.filter(Q(owner=user) | Q(organization=organization)).distinct().count()
    )
    if visible_company_count != 1:
        raise ProviderCredentialImportError(
            "Legacy user must see exactly one company before Phase 3."
        )

    credential, result = import_provider_credential(
        organization=organization,
        user=user,
        provider="stripe",
        name=LEGACY_STRIPE_CREDENTIAL_NAME,
        env_var=env_var,
        purpose="legacy_stripe_phase_3",
    )
    profile = ensure_storefront_profile(
        company=graph,
        slug="legacy-glasswear",
        display_name=DEFAULT_COMPANY_NAME,
        currency="mxn",
        stripe_credential=credential,
        metadata={"source": "legacy_phase_3"},
    )
    return {
        **result.as_dict(),
        "company_id": str(graph.id),
        "storefront_profile_id": str(profile.id),
        "storefront_slug": profile.slug,
    }
