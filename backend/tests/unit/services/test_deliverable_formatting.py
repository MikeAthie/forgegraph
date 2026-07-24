from __future__ import annotations

import json
import zipfile
from io import BytesIO
from typing import cast

import pytest

from application.services.deliverable_formatting import (
    FormatDeliverablesRequest,
    format_service_deliverables,
)
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import (
    Asset,
    AssetVersion,
    CompanyProgram,
    Graph,
    Organization,
    ProgramStageState,
    ServiceCatalogItem,
    ServiceDeliverable,
    ServiceEngagement,
    User,
)

pytestmark = pytest.mark.django_db


def _organization(user: User) -> Organization:
    ensure_default_organization(user)
    organization = user.default_organization
    assert organization is not None
    return organization


def _company(user: User, name: str) -> Graph:
    organization = _organization(user)
    return cast(
        Graph,
        Graph.objects.create(
            owner=user,
            organization=organization,
            name=name,
            description="Formatting test company.",
        ),
    )


def _engagement(
    user: User,
    company: Graph,
    *,
    slug: str,
    profile_ref: str | None = None,
) -> ServiceEngagement:
    organization = _organization(user)
    catalog = ServiceCatalogItem.objects.create(
        organization=organization,
        slug=slug,
        title=slug.replace("-", " ").title(),
        status="active",
        visibility="customer",
        created_by=user,
    )
    metadata = {"formatting": {"profile_ref": profile_ref}} if profile_ref else {}
    return ServiceEngagement.objects.create(
        organization=organization,
        company=company,
        catalog_item=catalog,
        status="in_progress",
        customer_status="working",
        public_summary="Format handoff deliverables.",
        metadata_json=metadata,
        requested_by=user,
    )


def _program(
    user: User,
    company: Graph,
    *,
    profile_ref: str | None = None,
) -> CompanyProgram:
    organization = _organization(user)
    metadata = {"formatting": {"profile_ref": profile_ref}} if profile_ref else {}
    program = CompanyProgram.objects.create(
        organization=organization,
        company=company,
        template_id="formatting.test.v1",
        display_label="Formatting Program",
        title="Formatting Test Program",
        objective="Format existing deliverables into a package.",
        status="active",
        current_stage_id="handoff",
        metadata_json=metadata,
        created_by=user,
    )
    ProgramStageState.objects.create(
        organization=organization,
        company=company,
        program=program,
        stage_id="handoff",
        label="Handoff",
        sequence=1,
        status="completed",
        state_json={},
    )
    return program


def _source_deliverable(
    user: User,
    engagement: ServiceEngagement,
    *,
    title: str,
    role: str,
    content: str,
    metadata: dict[str, object] | None = None,
) -> ServiceDeliverable:
    asset = Asset.objects.create(
        organization=engagement.organization,
        company=engagement.company,
        title=title,
        asset_type="deliverable",
        created_by_type="system",
    )
    version = AssetVersion.objects.create(
        asset=asset,
        version_number=1,
        content_uri=f"forgegraph://tests/{asset.id}/inline",
        content_hash=f"hash-{asset.id}",
        mime_type="text/markdown",
        size_bytes=len(content.encode("utf-8")),
        provenance_json={"inline_content": content, "source": "formatting_test"},
    )
    return ServiceDeliverable.objects.create(
        organization=engagement.organization,
        company=engagement.company,
        engagement=engagement,
        title=title,
        deliverable_type=role,
        status="ready",
        visibility="customer",
        artifact=asset,
        summary=content[:240],
        metadata_json={
            "asset_version_id": str(version.id),
            "formatting": {"source_role": role},
            **(metadata or {}),
        },
        created_by=user,
    )


@pytest.mark.parametrize(
    ("company_name", "engagement_profile", "program_profile", "provider_name"),
    [
        (
            "Legacy",
            "format_profile:legacy.client_handoff@1",
            "format_profile:consulting.standard_handoff@1",
            "Atlas",
        ),
        (
            "Northstar Advisory",
            None,
            "format_profile:consulting.standard_handoff@1",
            "ForgeGraph Consulting",
        ),
    ],
)
def test_formatting_service_persists_generic_derived_artifacts_for_distinct_business_fixtures(
    user: User,
    company_name: str,
    engagement_profile: str | None,
    program_profile: str | None,
    provider_name: str,
) -> None:
    company = _company(user, company_name)
    engagement = _engagement(
        user,
        company,
        slug=f"{company_name.lower().replace(' ', '-')}-handoff",
        profile_ref=engagement_profile,
    )
    program = _program(user, company, profile_ref=program_profile)
    sources = [
        _source_deliverable(
            user,
            engagement,
            title="Summary",
            role="summary",
            content=f"{provider_name} prepared this handoff for {company_name}.",
            metadata={"requires_approval": True},
        ),
        _source_deliverable(
            user,
            engagement,
            title="Evidence",
            role="evidence",
            content="Facts: receipts, interviews, and metrics are attached.",
            metadata={"connector_status": "unverified"},
        ),
        _source_deliverable(
            user,
            engagement,
            title="Recommendations",
            role="recommendation",
            content="Recommendation: approve the next production step.",
        ),
    ]

    result = format_service_deliverables(
        FormatDeliverablesRequest(
            request_id=f"format-{company_name.lower().replace(' ', '-')}",
            company=company,
            engagement=engagement,
            program=program,
            source_deliverables=sources,
            requested_formats=("markdown_report", "manifest", "zip_package"),
            requested_by=user,
            idempotency_key=f"handoff:{company.id}:v1",
        )
    )

    assert result.profile.profile_ref == (engagement_profile or program_profile)
    assert result.persisted is True
    assert result.deferred_formats == ("pdf_report", "email_handoff")
    assert {artifact.format for artifact in result.artifacts} == {
        "markdown_report",
        "manifest",
        "zip_package",
    }
    assert all(artifact.asset_version_id for artifact in result.artifacts)
    assert all(
        artifact.renderer_name in {"markdown_report", "manifest", "zip_package"}
        for artifact in result.artifacts
    )
    assert result.quality_result.status == "passed"

    for artifact in result.artifacts:
        assert artifact.asset_version_id is not None
        version = AssetVersion.objects.get(id=artifact.asset_version_id)
        provenance = version.provenance_json["render_provenance"]
        assert provenance["profile"]["profile_ref"] == result.profile.profile_ref
        assert provenance["profile"]["profile_sha256"] == result.profile.profile_sha256
        assert provenance["renderer"]["name"] == artifact.renderer_name
        assert provenance["quality"]["status"] == "passed"
        assert provenance["sources"]["service_deliverable_ids"] == [
            str(source.id) for source in sources
        ]

    markdown_artifact = result.artifact_by_format("markdown_report")
    assert markdown_artifact.asset_version_id is not None
    markdown_version = AssetVersion.objects.get(id=markdown_artifact.asset_version_id)
    assert markdown_version.provenance_json["inline_content"] == markdown_artifact.text
    assert company_name in markdown_artifact.text


def test_formatting_service_is_idempotent_for_same_request_and_source_hashes(user: User) -> None:
    company = _company(user, "Legacy")
    engagement = _engagement(
        user,
        company,
        slug="legacy-idempotent-handoff",
        profile_ref="format_profile:legacy.client_handoff@1",
    )
    sources = [
        _source_deliverable(
            user,
            engagement,
            title="Summary",
            role="summary",
            content="Atlas prepared this handoff for Legacy.",
            metadata={"requires_approval": True},
        ),
        _source_deliverable(
            user,
            engagement,
            title="Evidence",
            role="evidence",
            content="Facts: source evidence is attached.",
            metadata={"connector_status": "unverified"},
        ),
        _source_deliverable(
            user,
            engagement,
            title="Recommendations",
            role="recommendation",
            content="Recommendation: approve the next production step.",
        ),
    ]
    request = FormatDeliverablesRequest(
        request_id="format-idempotent",
        company=company,
        engagement=engagement,
        source_deliverables=sources,
        requested_formats=("markdown_report", "manifest", "zip_package"),
        requested_by=user,
        idempotency_key=f"handoff:{company.id}:idempotent",
    )

    first = format_service_deliverables(request)
    second = format_service_deliverables(request)

    assert [artifact.asset_version_id for artifact in second.artifacts] == [
        artifact.asset_version_id for artifact in first.artifacts
    ]
    assert (
        Asset.objects.filter(
            company=company, metadata_json__source="deliverable_formatting"
        ).count()
        == 3
    )


def test_formatting_service_persists_pdf_and_packages_it_when_requested(user: User) -> None:
    company = _company(user, "Legacy")
    engagement = _engagement(
        user,
        company,
        slug="legacy-pdf-handoff",
        profile_ref="format_profile:legacy.client_handoff@1",
    )
    sources = [
        _source_deliverable(
            user,
            engagement,
            title="Summary",
            role="summary",
            content="Atlas prepared this handoff for Legacy.",
            metadata={"requires_approval": True},
        ),
        _source_deliverable(
            user,
            engagement,
            title="Evidence",
            role="evidence",
            content="Facts: source evidence is attached.",
            metadata={"connector_status": "unverified"},
        ),
        _source_deliverable(
            user,
            engagement,
            title="Recommendations",
            role="recommendation",
            content="Recommendation: approve the next production step.",
        ),
    ]

    result = format_service_deliverables(
        FormatDeliverablesRequest(
            request_id="format-legacy-pdf",
            company=company,
            engagement=engagement,
            source_deliverables=sources,
            requested_formats=("markdown_report", "pdf_report", "manifest", "zip_package"),
            requested_by=user,
            idempotency_key=f"handoff:{company.id}:pdf",
        )
    )

    assert {artifact.format for artifact in result.artifacts} == {
        "markdown_report",
        "pdf_report",
        "manifest",
        "zip_package",
    }
    assert result.deferred_formats == ("email_handoff",)

    pdf = result.artifact_by_format("pdf_report")
    assert pdf.asset_version_id is not None
    pdf_version = AssetVersion.objects.select_related("asset").get(id=pdf.asset_version_id)
    assert pdf.filename.endswith(".pdf")
    assert pdf.mime_type == "application/pdf"
    assert pdf_version.mime_type == "application/pdf"
    assert pdf_version.asset.metadata_json["source"] == "deliverable_formatting"
    assert pdf_version.asset.metadata_json["format"] == "pdf_report"
    assert pdf_version.provenance_json["source"] == "deliverable_formatting"
    assert pdf_version.provenance_json["format"] == "pdf_report"
    assert pdf_version.provenance_json["render_provenance"]["quality"]["status"] == "passed"

    manifest = result.artifact_by_format("manifest")
    manifest_payload = json.loads(manifest.text)
    output_formats = {output["format"] for output in manifest_payload["outputs"]}
    assert "pdf_report" in output_formats
    assert manifest_payload["deferred_formats"] == ["email_handoff"]

    package = result.artifact_by_format("zip_package")
    with zipfile.ZipFile(BytesIO(package.content_bytes)) as archive:
        names = set(archive.namelist())
        assert names == {
            result.artifact_by_format(format_id).filename
            for format_id in (
                "markdown_report",
                "pdf_report",
                "manifest",
            )
        }
        pdf_bytes = archive.read(pdf.filename)
        assert pdf_bytes.startswith(b"%PDF-")
        assert pdf_bytes.rstrip().endswith(b"%%EOF")
