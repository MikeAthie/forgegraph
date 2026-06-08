from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import os
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402
from django.apps import apps  # noqa: E402

if not apps.ready:
    django.setup()

from application.services.deliverable_formatting import (  # noqa: E402
    FormatDeliverablesRequest,
    format_service_deliverables,
)
from application.services.tenancy import ensure_default_organization  # noqa: E402
from infrastructure.orm.models import (  # noqa: E402
    Asset,
    AssetVersion,
    CompanyProgram,
    Graph,
    ServiceCatalogItem,
    ServiceDeliverable,
    ServiceEngagement,
    TaskRoutingRecord,
    User,
    WorkWhiteboard,
)

ENGAGEMENT_ID = "d3dc8dbd-9eb4-4361-a24d-7d1006e57cf9"
PROGRAM_ID = "6f0c1926-c222-40d2-8b54-3c797c16668e"
WHITEBOARD_ID = "f4f52d28-502b-449f-b133-f6caba760113"
LEGACY_HANDOFF_PROFILE_REF = "format_profile:legacy.client_handoff@1"
DEFAULT_RECIPIENT = "admin@intlabs.dev"
DEFAULT_SUBJECT = "Legacy Optical Noir - ForgeGraph/Codex company run deliverables ready"
OUT_DIR = Path(__file__).resolve().parents[2] / ".hermes" / "legacy_client_handoff_email"

_DETERMINISTIC_SOURCE_KEY = "legacy-client-handoff-deterministic-fixture:v1"
_EXPORT_FILE_SUFFIXES = frozenset({".html", ".json", ".md", ".pdf", ".zip"})


def prepare_legacy_handoff(
    *,
    engagement: ServiceEngagement,
    output_dir: Path = OUT_DIR,
    recipient: str = DEFAULT_RECIPIENT,
    subject: str = DEFAULT_SUBJECT,
    source_deliverables: Iterable[ServiceDeliverable] | None = None,
    program: CompanyProgram | None = None,
    profile_ref: str | None = LEGACY_HANDOFF_PROFILE_REF,
    requested_by: User | None = None,
    request_id: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, object]:
    """Persist and export the Legacy handoff package from generic formatter output."""

    sources = tuple(source_deliverables or _source_deliverables_for_engagement(engagement))
    if not sources:
        raise ValueError("Legacy handoff requires at least one source ServiceDeliverable.")

    request = FormatDeliverablesRequest(
        request_id=request_id or f"legacy-client-handoff:{engagement.id}",
        company=engagement.company,
        engagement=engagement,
        program=program,
        source_deliverables=list(sources),
        requested_formats=("markdown_report", "pdf_report", "manifest", "zip_package"),
        profile_ref=profile_ref,
        requested_by=requested_by or engagement.assigned_operator or engagement.requested_by,
        idempotency_key=idempotency_key or f"legacy-client-handoff:{engagement.id}:v1",
    )
    formatted = format_service_deliverables(request)

    markdown = formatted.artifact_by_format("markdown_report")
    pdf = formatted.artifact_by_format("pdf_report")
    manifest = formatted.artifact_by_format("manifest")
    package = formatted.artifact_by_format("zip_package")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    _clear_previous_exports(output_dir)
    markdown_path = _export_artifact(markdown.asset_version_id, output_dir / markdown.filename)
    pdf_path = _export_artifact(pdf.asset_version_id, output_dir / pdf.filename)
    manifest_path = _export_artifact(manifest.asset_version_id, output_dir / manifest.filename)
    package_path = _export_artifact(package.asset_version_id, output_dir / package.filename)

    markdown_text = markdown_path.read_text(encoding="utf-8")
    (output_dir / "email_body.md").write_text(markdown_text, encoding="utf-8")
    (output_dir / "email_body.html").write_text(_markdown_email_html(markdown_text), encoding="utf-8")

    summary: dict[str, object] = {
        "recipient": recipient,
        "subject": subject,
        "package_path": str(package_path.resolve()),
        "package_asset_version_id": package.asset_version_id,
        "markdown_asset_version_id": markdown.asset_version_id,
        "pdf_asset_version_id": pdf.asset_version_id,
        "manifest_asset_version_id": manifest.asset_version_id,
        "profile_ref": formatted.profile.profile_ref,
        "quality_status": formatted.quality_result.status,
        "source_deliverable_count": len(sources),
        "package_dir": str(output_dir.resolve()),
        "markdown_path": str(markdown_path.resolve()),
        "pdf_path": str(pdf_path.resolve()),
        "manifest_path": str(manifest_path.resolve()),
        "markdown_filename": markdown.filename,
        "pdf_filename": pdf.filename,
        "manifest_filename": manifest.filename,
        "package_filename": package.filename,
        "deferred_formats": list(formatted.deferred_formats),
    }
    summary_path = output_dir / "handoff_summary.json"
    summary["summary_path"] = str(summary_path.resolve())
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return summary


def run(
    *,
    engagement_id: str = ENGAGEMENT_ID,
    program_id: str = PROGRAM_ID,
    whiteboard_id: str = WHITEBOARD_ID,
    output_dir: Path = OUT_DIR,
    recipient: str = DEFAULT_RECIPIENT,
    subject: str = DEFAULT_SUBJECT,
) -> dict[str, object]:
    engagement = ServiceEngagement.objects.select_related(
        "company",
        "organization",
        "requested_by",
        "assigned_operator",
    ).get(id=engagement_id)
    program = CompanyProgram.objects.filter(id=program_id).first() if program_id else None
    result = prepare_legacy_handoff(
        engagement=engagement,
        program=program,
        output_dir=output_dir,
        recipient=recipient,
        subject=subject,
    )
    if program_id:
        result["program_id"] = program_id
        result["routing_task_count"] = TaskRoutingRecord.objects.filter(
            metadata_json__company_run_task__program_id=program_id
        ).count()
    if whiteboard_id:
        whiteboard = WorkWhiteboard.objects.filter(id=whiteboard_id).first()
        snapshot = (whiteboard.metadata_json or {}).get("company_run_task_snapshot", {}) if whiteboard else {}
        tasks = snapshot.get("tasks", []) if isinstance(snapshot, dict) else []
        result["whiteboard_id"] = whiteboard_id
        result["whiteboard_snapshot_task_count"] = len(tasks)
    return result


def run_deterministic_fixture(
    *,
    operator_email: str = "admin@forgegraph.local",
    output_dir: Path = OUT_DIR,
    recipient: str = DEFAULT_RECIPIENT,
    subject: str = DEFAULT_SUBJECT,
) -> dict[str, object]:
    """Create deterministic source deliverables and format them without Codex/network work."""

    user = _operator_user(operator_email)
    engagement = _deterministic_engagement(user)
    sources = _deterministic_sources(user=user, engagement=engagement)
    return prepare_legacy_handoff(
        engagement=engagement,
        output_dir=output_dir,
        recipient=recipient,
        subject=subject,
        source_deliverables=sources,
        requested_by=user,
        request_id="legacy-client-handoff:deterministic-fixture",
        idempotency_key=f"legacy-client-handoff:{engagement.id}:deterministic:v1",
    )


def _source_deliverables_for_engagement(
    engagement: ServiceEngagement,
) -> Sequence[ServiceDeliverable]:
    return tuple(
        ServiceDeliverable.objects.filter(
            engagement=engagement,
            status__in=["ready", "delivered", "accepted"],
            visibility__in=["customer", "operator"],
        )
        .select_related("artifact")
        .order_by("created_at", "id")
    )


def _export_artifact(asset_version_id: str | None, path: Path) -> Path:
    if not asset_version_id:
        raise ValueError("Formatted artifact was not persisted.")
    version = AssetVersion.objects.get(id=asset_version_id)
    path.write_bytes(_asset_version_bytes(version))
    return path


def _clear_previous_exports(output_dir: Path) -> None:
    for path in output_dir.iterdir():
        if path.is_file() and path.suffix.lower() in _EXPORT_FILE_SUFFIXES:
            path.unlink()


def _asset_version_bytes(version: AssetVersion) -> bytes:
    provenance = version.provenance_json if isinstance(version.provenance_json, dict) else {}
    inline = provenance.get("inline_content")
    if isinstance(inline, str):
        return inline.encode("utf-8")
    if inline is not None:
        return json.dumps(inline, sort_keys=True, default=str).encode("utf-8")
    encoded = provenance.get("inline_content_base64")
    if isinstance(encoded, str) and encoded:
        return base64.b64decode(encoded.encode("ascii"))
    raise ValueError(f"AssetVersion {version.id} has no inline formatter content.")


def _markdown_email_html(markdown_text: str) -> str:
    return "<html><body><pre>" + html.escape(markdown_text) + "</pre></body></html>"


def _operator_user(email: str) -> User:
    user = User.objects.filter(email=email).first() or User.objects.order_by("date_joined").first()
    if user is None:
        user = User.objects.create_user(email=email)
    ensure_default_organization(user)
    return user


def _deterministic_engagement(user: User) -> ServiceEngagement:
    ensure_default_organization(user)
    organization = user.default_organization
    if organization is None:
        raise ValueError("Deterministic Legacy handoff fixture requires an organization.")
    company, _ = Graph.objects.get_or_create(
        organization=organization,
        external_source="legacy_handoff_fixture",
        external_ref="deterministic",
        defaults={
            "owner": user,
            "name": "Legacy",
            "description": "Deterministic Legacy handoff fixture company.",
        },
    )
    company.owner = user
    company.name = "Legacy"
    company.description = "Deterministic Legacy handoff fixture company."
    company.save(update_fields=["owner", "name", "description", "updated_at"])

    catalog, _ = ServiceCatalogItem.objects.get_or_create(
        organization=organization,
        slug="legacy-client-handoff-deterministic-fixture",
        defaults={
            "title": "Legacy Client Handoff Deterministic Fixture",
            "created_by": user,
        },
    )
    catalog.title = "Legacy Client Handoff Deterministic Fixture"
    catalog.status = "active"
    catalog.visibility = "organization"
    catalog.save()

    engagement, _ = ServiceEngagement.objects.get_or_create(
        company=company,
        source_key=_DETERMINISTIC_SOURCE_KEY,
        defaults={
            "organization": organization,
            "catalog_item": catalog,
            "status": "in_progress",
            "customer_status": "review_ready",
            "requested_by": user,
            "assigned_operator": user,
        },
    )
    engagement.organization = organization
    engagement.catalog_item = catalog
    engagement.status = "in_progress"
    engagement.customer_status = "review_ready"
    engagement.public_summary = "Deterministic Legacy Codex deliverables for formatter handoff."
    engagement.metadata_json = {
        "source": _DETERMINISTIC_SOURCE_KEY,
        "formatting": {"profile_ref": LEGACY_HANDOFF_PROFILE_REF},
    }
    engagement.requested_by = user
    engagement.assigned_operator = user
    engagement.save()
    return engagement


def _deterministic_sources(
    *,
    user: User,
    engagement: ServiceEngagement,
) -> tuple[ServiceDeliverable, ...]:
    definitions = (
        {
            "deliverable_type": "codex_strategy_brief",
            "title": "Legacy Codex Strategy Brief",
            "content": (
                "Atlas prepared this handoff for Legacy. Executive summary: "
                "the Optical Noir launch package is ready for review."
            ),
            "metadata": {"requires_approval": True},
        },
        {
            "deliverable_type": "codex_qa_report",
            "title": "Legacy Codex Launch QA Report",
            "content": "Facts: source receipts, routing evidence, and QA findings are attached.",
            "metadata": {"connector_status": "unverified"},
        },
        {
            "deliverable_type": "codex_client_approval_packet",
            "title": "Legacy Codex Client Approval Packet",
            "content": "Recommendation: approve the next production step after receipt review.",
            "metadata": {},
        },
    )
    return tuple(
        _upsert_fixture_source_deliverable(
            user=user,
            engagement=engagement,
            deliverable_type=str(item["deliverable_type"]),
            title=str(item["title"]),
            content=str(item["content"]),
            metadata=dict(item["metadata"]),
        )
        for item in definitions
    )


def _upsert_fixture_source_deliverable(
    *,
    user: User,
    engagement: ServiceEngagement,
    deliverable_type: str,
    title: str,
    content: str,
    metadata: dict[str, Any],
) -> ServiceDeliverable:
    data = content.encode("utf-8")
    digest = hashlib.sha256(data).hexdigest()
    asset, _ = Asset.objects.get_or_create(
        company=engagement.company,
        source_key=f"{_DETERMINISTIC_SOURCE_KEY}:{engagement.id}:{deliverable_type}",
        defaults={
            "organization": engagement.organization,
            "title": title,
            "asset_type": "deliverable",
            "created_by_type": "agent",
            "created_by_id": user.id,
        },
    )
    asset.organization = engagement.organization
    asset.title = title
    asset.asset_type = "deliverable"
    asset.status = "active"
    asset.metadata_json = {
        "source": _DETERMINISTIC_SOURCE_KEY,
        "deliverable_type": deliverable_type,
        "inline_preview": content,
    }
    asset.save()

    version = AssetVersion.objects.filter(asset=asset, content_hash=digest).first()
    if version is None:
        latest = (
            AssetVersion.objects.filter(asset=asset)
            .order_by("-version_number")
            .values_list("version_number", flat=True)
            .first()
            or 0
        )
        version = AssetVersion.objects.create(
            asset=asset,
            version_number=int(latest) + 1,
            content_uri=f"forgegraph://deterministic-legacy-handoff/{engagement.id}/{deliverable_type}.md",
            content_hash=digest,
            mime_type="text/markdown",
            size_bytes=len(data),
            provenance_json={
                "source": _DETERMINISTIC_SOURCE_KEY,
                "inline_content": content,
            },
        )

    deliverable, _ = ServiceDeliverable.objects.get_or_create(
        engagement=engagement,
        deliverable_type=deliverable_type,
        defaults={
            "organization": engagement.organization,
            "company": engagement.company,
            "created_by": user,
        },
    )
    deliverable.organization = engagement.organization
    deliverable.company = engagement.company
    deliverable.title = title
    deliverable.status = "ready"
    deliverable.visibility = "customer"
    deliverable.artifact = asset
    deliverable.summary = content[:240]
    deliverable.metadata_json = {
        "source": _DETERMINISTIC_SOURCE_KEY,
        "asset_version_id": str(version.id),
        **metadata,
    }
    deliverable.created_by = user
    deliverable.save()
    asset.origin_deliverable_id = deliverable.id
    asset.save(update_fields=["origin_deliverable_id", "updated_at"])
    return deliverable


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare the Legacy formatter-backed handoff package.")
    parser.add_argument("--deterministic-fixture", action="store_true")
    parser.add_argument("--operator-email", default="admin@forgegraph.local")
    parser.add_argument("--recipient", default=DEFAULT_RECIPIENT)
    parser.add_argument("--subject", default=DEFAULT_SUBJECT)
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--engagement-id", default=ENGAGEMENT_ID)
    parser.add_argument("--program-id", default=PROGRAM_ID)
    parser.add_argument("--whiteboard-id", default=WHITEBOARD_ID)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if args.deterministic_fixture:
        payload = run_deterministic_fixture(
            operator_email=args.operator_email,
            output_dir=args.output_dir,
            recipient=args.recipient,
            subject=args.subject,
        )
    else:
        payload = run(
            engagement_id=args.engagement_id,
            program_id=args.program_id,
            whiteboard_id=args.whiteboard_id,
            output_dir=args.output_dir,
            recipient=args.recipient,
            subject=args.subject,
        )
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
