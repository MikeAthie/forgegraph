from __future__ import annotations

import json
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from application.services.inventory import InventoryError, import_inventory_csv
from infrastructure.orm.management.commands.seed_legacy_glasswear_phase0 import (
    DEFAULT_EMAIL,
    EXTERNAL_REF,
    EXTERNAL_SOURCE,
)
from infrastructure.orm.models import Graph, InventoryProduct, User

DEFAULT_LEGACY_INVENTORY_CSV = "docs/legacy-ultimate-test/Análisis costos.csv"
LEGACY_ANCHOR_MODELS = {"TAYLOR", "ROBBIE", "VICE", "HUNT", "WATSON", "MAVERICK"}
LEGACY_PUBLIC_CATALOG_REFERENCES = {
    "ZD-8809T": {
        "photo_url": "https://legacy-five-beta.vercel.app/catalog/depp/gallery-1.webp",
        "source_url": "https://legacy-five-beta.vercel.app/_next/image?url=%2Fcatalog%2Fdepp%2Fgallery-1.webp&w=1200&q=75",
        "visual_description": (
            "Rose-gold geometric octagonal metal sunglasses with dark gray lenses, "
            "slim gold temples, and brown tortoiseshell ear tips on a white catalog background."
        ),
        "visual_traits": [
            "rose-gold thin metal frame",
            "geometric octagonal lens shape",
            "dark gray lenses",
            "slim gold temples",
            "brown tortoiseshell ear tips",
        ],
        "source": "legacy_public_catalog",
    }
}


class Command(BaseCommand):
    help = "Import the Legacy Glasswear Phase 2 inventory CSV into reusable inventory tables."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--email", default=DEFAULT_EMAIL)
        parser.add_argument("--csv", default=str(DEFAULT_LEGACY_INVENTORY_CSV))
        parser.add_argument("--json", action="store_true", dest="output_json")

    def handle(self, *args: Any, **options: Any) -> None:
        user = User.objects.filter(email=str(options["email"])).first()
        if user is None:
            raise CommandError("Legacy user was not found. Run seed_legacy_glasswear_phase0 first.")
        company = (
            Graph.objects.filter(
                owner=user,
                organization=user.default_organization,
                external_source=EXTERNAL_SOURCE,
                external_ref=EXTERNAL_REF,
            )
            .select_related("organization")
            .first()
        )
        if company is None:
            raise CommandError(
                "Legacy company was not found. Run seed_legacy_glasswear_phase0 first."
            )

        try:
            result = import_inventory_csv(
                company=company,
                csv_path=str(options["csv"]),
                actor=user,
                source="legacy_cost_analysis_csv",
                anchor_models=LEGACY_ANCHOR_MODELS,
                currency="mxn",
            )
        except InventoryError as exc:
            raise CommandError(exc.message) from exc
        catalog_references_applied = _apply_public_catalog_references(company)

        payload = {
            "user_id": str(user.id),
            "organization_id": str(user.default_organization_id),
            "company_id": str(company.id),
            "catalog_references_applied": catalog_references_applied,
            **result.as_payload(),
        }
        if options["output_json"]:
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
            return

        self.stdout.write(
            self.style.SUCCESS(
                "Imported Legacy inventory "
                f"({payload['products_seen']} products, "
                f"{payload['total_active_units']} active units)."
            )
        )


def _apply_public_catalog_references(company: Graph) -> int:
    applied = 0
    for sku, reference in LEGACY_PUBLIC_CATALOG_REFERENCES.items():
        product = InventoryProduct.objects.filter(company=company, sku=sku).first()
        if product is None:
            continue
        metadata = dict(product.metadata_json or {})
        metadata["visual_reference_source"] = reference["source"]
        metadata["visual_reference_source_url"] = reference["source_url"]
        metadata["visual_description"] = reference["visual_description"]
        metadata["visual_traits"] = list(reference["visual_traits"])
        product.photo_url = str(reference["photo_url"])
        product.metadata_json = metadata
        product.save(update_fields=["photo_url", "metadata_json", "updated_at"])
        applied += 1
    return applied
