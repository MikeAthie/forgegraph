from __future__ import annotations

import json
import zipfile
from io import BytesIO

import pytest

from application.services.deliverable_format_profiles import load_format_profile_registry
from application.services.deliverable_format_quality import evaluate_render_quality
from application.services.deliverable_format_renderers import (
    FormatRenderContext,
    FormatSource,
    render_manifest_json,
    render_markdown_report,
    render_pdf_report,
    render_zip_package,
)


def _sources(kind: str) -> list[FormatSource]:
    if kind == "legacy":
        return [
            FormatSource(
                service_deliverable_id="legacy-summary",
                asset_version_id="legacy-summary-v1",
                title="Launch Summary",
                source_role="summary",
                content="Atlas prepared the launch handoff for Legacy.",
                content_hash="sha256:legacy-summary",
                metadata={"requires_approval": True},
            ),
            FormatSource(
                service_deliverable_id="legacy-evidence",
                asset_version_id="legacy-evidence-v1",
                title="Receipts",
                source_role="evidence",
                content="Facts: connector receipts and metric snapshots are attached.",
                content_hash="sha256:legacy-evidence",
                metadata={"connector_status": "unverified"},
            ),
            FormatSource(
                service_deliverable_id="legacy-recommendation",
                asset_version_id="legacy-recommendation-v1",
                title="Next Steps",
                source_role="recommendation",
                content="Recommendation: approve production execution after receipt review.",
                content_hash="sha256:legacy-recommendation",
                metadata={},
            ),
        ]
    return [
        FormatSource(
            service_deliverable_id="consulting-summary",
            asset_version_id="consulting-summary-v1",
            title="Assessment Summary",
            source_role="summary",
            content="ForgeGraph Consulting prepared the advisory handoff for Northstar Advisory.",
            content_hash="sha256:consulting-summary",
            metadata={"requires_approval": True},
        ),
        FormatSource(
            service_deliverable_id="consulting-evidence",
            asset_version_id="consulting-evidence-v1",
            title="Operating Facts",
            source_role="evidence",
            content="Facts: interviews and operating metrics are attached.",
            content_hash="sha256:consulting-evidence",
            metadata={"connector_status": "unverified"},
        ),
        FormatSource(
            service_deliverable_id="consulting-recommendation",
            asset_version_id="consulting-recommendation-v1",
            title="Recommendations",
            source_role="recommendation",
            content="Recommendation: approve the operating model changes.",
            content_hash="sha256:consulting-recommendation",
            metadata={},
        ),
    ]


@pytest.mark.parametrize(
    ("profile_ref", "kind", "expected_title"),
    [
        ("format_profile:legacy.client_handoff@1", "legacy", "Legacy Client Handoff"),
        (
            "format_profile:consulting.standard_handoff@1",
            "consulting",
            "Consulting Standard Handoff",
        ),
    ],
)
def test_markdown_report_uses_same_generic_renderer_for_legacy_and_consulting(
    profile_ref: str,
    kind: str,
    expected_title: str,
) -> None:
    profile = load_format_profile_registry().get(profile_ref)
    context = FormatRenderContext(
        request_id=f"request-{kind}",
        profile=profile,
        sources=_sources(kind),
        idempotency_key=f"handoff:{kind}",
    )

    report = render_markdown_report(context)
    quality = evaluate_render_quality(
        profile=profile,
        rendered_text=report.text,
        sections=report.sections,
        source_metadata=[source.metadata for source in context.sources],
    )

    assert report.renderer_name == "markdown_report"
    assert report.renderer_version == "1"
    assert report.provenance["renderer"]["implementation"] == (
        "application.services.deliverable_format_renderers.markdown_report"
    )
    assert report.filename.endswith(".md")
    assert f"# {expected_title}" in report.text
    assert report.text.index("## " + profile.section_by_id("executive_summary").title) < (
        report.text.index("## " + profile.section_by_id("evidence").title)
    )
    assert quality.status == "passed"


def test_manifest_and_zip_include_hashes_sources_outputs_and_no_deferred_formats() -> None:
    profile = load_format_profile_registry().get("format_profile:legacy.client_handoff@1")
    context = FormatRenderContext(
        request_id="request-legacy-package",
        profile=profile,
        sources=_sources("legacy"),
        idempotency_key="handoff:legacy:package",
    )
    report = render_markdown_report(context)
    quality = evaluate_render_quality(
        profile=profile,
        rendered_text=report.text,
        sections=report.sections,
        source_metadata=[source.metadata for source in context.sources],
    )
    manifest = render_manifest_json(context, outputs=[report], quality_result=quality)
    package = render_zip_package(context, outputs=[report, manifest], quality_result=quality)

    manifest_payload = json.loads(manifest.text)
    assert manifest_payload["profile"]["profile_ref"] == profile.profile_ref
    assert manifest_payload["profile"]["profile_sha256"] == profile.profile_sha256
    assert [source["asset_version_id"] for source in manifest_payload["sources"]] == [
        "legacy-summary-v1",
        "legacy-evidence-v1",
        "legacy-recommendation-v1",
    ]
    assert manifest_payload["outputs"][0]["format"] == "markdown_report"
    assert manifest_payload["quality"]["status"] == "passed"
    assert "pdf_report" not in {output["format"] for output in manifest_payload["outputs"]}
    assert "email_handoff" not in {output["format"] for output in manifest_payload["outputs"]}
    assert manifest_payload["deferred_formats"] == ["pdf_report", "email_handoff"]

    with zipfile.ZipFile(BytesIO(package.content_bytes)) as archive:
        names = set(archive.namelist())
        assert names == {report.filename, manifest.filename}
        assert archive.read(report.filename).decode("utf-8") == report.text
        assert json.loads(archive.read(manifest.filename).decode("utf-8")) == manifest_payload

    assert package.mime_type == "application/zip"
    assert package.bytes_sha256
    assert package.provenance["quality"]["status"] == "passed"


def test_pdf_report_renders_valid_pdf_with_readable_report_text() -> None:
    profile = load_format_profile_registry().get("format_profile:legacy.client_handoff@1")
    sources = [
        *_sources("legacy"),
        FormatSource(
            service_deliverable_id="legacy-escape",
            asset_version_id="legacy-escape-v1",
            title="Escaping Sample",
            source_role="evidence",
            content="Escaping check: client path C:\\Legacy\\handoff (review).",
            content_hash="sha256:legacy-escape",
            metadata={},
        ),
    ]
    context = FormatRenderContext(
        request_id="request-legacy-pdf",
        profile=profile,
        sources=sources,
        idempotency_key="handoff:legacy:pdf",
    )
    report = render_markdown_report(context)
    quality = evaluate_render_quality(
        profile=profile,
        rendered_text=report.text,
        sections=report.sections,
        source_metadata=[source.metadata for source in context.sources],
    )

    pdf = render_pdf_report(context, markdown_report=report, quality_result=quality)

    assert pdf.format == "pdf_report"
    assert pdf.renderer_name == "pdf_report"
    assert pdf.renderer_version == "1"
    assert pdf.filename == "legacy-client-handoff.pdf"
    assert pdf.mime_type == "application/pdf"
    assert pdf.content_bytes.startswith(b"%PDF-")
    assert pdf.content_bytes.rstrip().endswith(b"%%EOF")
    assert b"Legacy Client Handoff" in pdf.content_bytes
    assert b"Atlas prepared the launch handoff for Legacy." in pdf.content_bytes
    assert (
        b"Recommendation: approve production execution after receipt review." in pdf.content_bytes
    )
    assert b"C:\\\\Legacy\\\\handoff \\(review\\)" in pdf.content_bytes
    assert pdf.provenance["renderer"]["name"] == "pdf_report"
    assert pdf.provenance["profile"]["profile_ref"] == profile.profile_ref
    assert pdf.provenance["sources"]["asset_version_ids"] == [
        "legacy-summary-v1",
        "legacy-evidence-v1",
        "legacy-recommendation-v1",
        "legacy-escape-v1",
    ]
    assert pdf.provenance["quality"]["status"] == "passed"
    assert pdf.provenance["output"]["bytes_sha256"] == pdf.bytes_sha256

    manifest = render_manifest_json(context, outputs=[report, pdf], quality_result=quality)
    manifest_payload = json.loads(manifest.text)
    assert {output["format"] for output in manifest_payload["outputs"]} == {
        "markdown_report",
        "pdf_report",
    }
    assert manifest_payload["deferred_formats"] == ["email_handoff"]
