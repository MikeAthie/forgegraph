"""Generic markdown, PDF, manifest, and zip renderers for formatted deliverables."""

from __future__ import annotations

import hashlib
import json
import re
import textwrap
import unicodedata
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from typing import Any

from application.services.deliverable_format_profiles import FormatProfile
from application.services.deliverable_format_quality import QualityGateResult, RenderedSection

RENDERER_VERSION = "1"
_PDF_PAGE_WIDTH = 612
_PDF_PAGE_HEIGHT = 792
_PDF_MARGIN_X = 54
_PDF_MARGIN_TOP = 54
_PDF_MARGIN_BOTTOM = 54
_PDF_FONT_SIZE = 10
_PDF_LEADING = 14
_PDF_WRAP_CHARS = 92
_PDF_LINES_PER_PAGE = (_PDF_PAGE_HEIGHT - _PDF_MARGIN_TOP - _PDF_MARGIN_BOTTOM) // _PDF_LEADING


@dataclass(frozen=True)
class FormatSource:
    service_deliverable_id: str
    asset_version_id: str
    title: str
    source_role: str
    content: str
    content_hash: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_manifest_dict(self) -> dict[str, Any]:
        return {
            "service_deliverable_id": self.service_deliverable_id,
            "asset_version_id": self.asset_version_id,
            "title": self.title,
            "source_role": self.source_role,
            "content_hash": self.content_hash,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class FormatRenderContext:
    request_id: str
    profile: FormatProfile
    sources: list[FormatSource] | tuple[FormatSource, ...]
    idempotency_key: str = ""


@dataclass(frozen=True)
class RenderedArtifact:
    format: str
    renderer_name: str
    renderer_version: str
    filename: str
    mime_type: str
    content_bytes: bytes
    text: str
    bytes_sha256: str
    provenance: dict[str, Any]
    sections: tuple[RenderedSection, ...] = ()
    asset_id: str | None = None
    asset_version_id: str | None = None


def render_markdown_report(context: FormatRenderContext) -> RenderedArtifact:
    profile = context.profile
    naming = profile.naming
    header_lines = [
        f"# {profile.display_name}",
        "",
    ]
    if naming.get("client_display_name"):
        header_lines.append(f"Prepared for: {naming['client_display_name']}")
    if naming.get("provider_display_name"):
        header_lines.append(f"Prepared by: {naming['provider_display_name']}")
    if len(header_lines) > 2:
        header_lines.append("")

    rendered_sections: list[RenderedSection] = []
    lines = list(header_lines)
    for section in profile.sections:
        section_sources = _sources_for_section(
            tuple(context.sources), section.id, section.source_roles
        )
        section_content = _section_content(section_sources)
        rendered_sections.append(
            RenderedSection(
                id=section.id,
                title=section.title,
                content=section_content,
            )
        )
        lines.extend([f"## {section.title}", section_content or "No source material provided.", ""])

    policy_lines = _policy_lines(profile, tuple(context.sources))
    if policy_lines:
        lines.extend(policy_lines)

    text = "\n".join(lines).strip() + "\n"
    filename = f"{_slugify(profile.display_name)}.md"
    return _artifact(
        context=context,
        format_id="markdown_report",
        renderer_name="markdown_report",
        filename=filename,
        mime_type="text/markdown",
        content_bytes=text.encode("utf-8"),
        text=text,
        sections=tuple(rendered_sections),
        quality_result=None,
    )


def render_pdf_report(
    context: FormatRenderContext,
    *,
    markdown_report: RenderedArtifact,
    quality_result: QualityGateResult,
) -> RenderedArtifact:
    pdf_bytes = _pdf_document_bytes(_pdf_pages(markdown_report.text))
    return _artifact(
        context=context,
        format_id="pdf_report",
        renderer_name="pdf_report",
        filename=f"{_slugify(context.profile.display_name)}.pdf",
        mime_type="application/pdf",
        content_bytes=pdf_bytes,
        text="",
        sections=(),
        quality_result=quality_result,
    )


def render_manifest_json(
    context: FormatRenderContext,
    *,
    outputs: list[RenderedArtifact] | tuple[RenderedArtifact, ...],
    quality_result: QualityGateResult,
) -> RenderedArtifact:
    payload = {
        "schema_version": "deliverable_format_manifest.v1",
        "request": {
            "request_id": context.request_id,
            "idempotency_key": context.idempotency_key,
        },
        "profile": {
            "profile_ref": context.profile.profile_ref,
            "profile_sha256": context.profile.profile_sha256,
        },
        "sources": [source.as_manifest_dict() for source in context.sources],
        "outputs": [_output_manifest_entry(output) for output in outputs],
        "quality": quality_result.as_dict(),
        "deferred_formats": _deferred_formats(context=context, outputs=outputs),
    }
    text = json.dumps(payload, indent=2, sort_keys=True)
    return _artifact(
        context=context,
        format_id="manifest",
        renderer_name="manifest",
        filename=f"{_slugify(context.profile.display_name)}.manifest.json",
        mime_type="application/json",
        content_bytes=text.encode("utf-8"),
        text=text,
        sections=(),
        quality_result=quality_result,
    )


def render_zip_package(
    context: FormatRenderContext,
    *,
    outputs: list[RenderedArtifact] | tuple[RenderedArtifact, ...],
    quality_result: QualityGateResult,
) -> RenderedArtifact:
    package_bytes = _zip_bytes(outputs)
    return _artifact(
        context=context,
        format_id="zip_package",
        renderer_name="zip_package",
        filename=f"{_slugify(context.profile.display_name)}.zip",
        mime_type="application/zip",
        content_bytes=package_bytes,
        text="",
        sections=(),
        quality_result=quality_result,
    )


def _sources_for_section(
    sources: tuple[FormatSource, ...],
    section_id: str,
    source_roles: tuple[str, ...],
) -> tuple[FormatSource, ...]:
    accepted_roles = {section_id, *source_roles}
    return tuple(source for source in sources if source.source_role in accepted_roles)


def _section_content(sources: tuple[FormatSource, ...]) -> str:
    if not sources:
        return ""
    lines: list[str] = []
    for source in sources:
        content = source.content.strip()
        if not content:
            continue
        title = source.title.strip() or source.source_role
        lines.append(f"- **{title}**: {content}")
    return "\n".join(lines)


def _policy_lines(profile: FormatProfile, sources: tuple[FormatSource, ...]) -> list[str]:
    lines: list[str] = []
    requires_connector_caveat = profile.connector_policy.get(
        "require_caveats_for_unverified_sources"
    ) and any(_source_requires_connector_caveat(source) for source in sources)
    if requires_connector_caveat:
        caveat = profile.connector_policy.get("caveat_text") or (
            "Connector caveat: unverified connector outputs require receipt review."
        )
        lines.extend(["## Connector Caveats", str(caveat), ""])

    requires_approval = profile.connector_policy.get("require_approval_language") is True or any(
        source.metadata.get("requires_approval") is True for source in sources
    )
    if requires_approval:
        approval = profile.connector_policy.get("approval_text") or (
            "Approval required before production execution."
        )
        lines.extend(["## Approval", str(approval), ""])
    return lines


def _source_requires_connector_caveat(source: FormatSource) -> bool:
    return source.metadata.get("requires_connector_caveat") is True or str(
        source.metadata.get("connector_status") or ""
    ).lower() in {"unverified", "blocked", "missing"}


def _output_manifest_entry(output: RenderedArtifact) -> dict[str, Any]:
    return {
        "format": output.format,
        "renderer": {
            "name": output.renderer_name,
            "version": output.renderer_version,
        },
        "filename": output.filename,
        "mime_type": output.mime_type,
        "bytes_sha256": output.bytes_sha256,
        "asset_id": output.asset_id,
        "asset_version_id": output.asset_version_id,
    }


def _deferred_formats(
    *,
    context: FormatRenderContext,
    outputs: list[RenderedArtifact] | tuple[RenderedArtifact, ...],
) -> list[str]:
    produced_formats = {output.format for output in outputs}
    deferred: list[str] = []
    if "pdf_report" in context.profile.formats and "pdf_report" not in produced_formats:
        deferred.append("pdf_report")
    deferred.append("email_handoff")
    return deferred


def _artifact(
    *,
    context: FormatRenderContext,
    format_id: str,
    renderer_name: str,
    filename: str,
    mime_type: str,
    content_bytes: bytes,
    text: str,
    sections: tuple[RenderedSection, ...],
    quality_result: QualityGateResult | None,
) -> RenderedArtifact:
    output_hash = hashlib.sha256(content_bytes).hexdigest()
    provenance = _render_provenance(
        context=context,
        renderer_name=renderer_name,
        output_hash=output_hash,
        quality_result=quality_result,
    )
    return RenderedArtifact(
        format=format_id,
        renderer_name=renderer_name,
        renderer_version=RENDERER_VERSION,
        filename=filename,
        mime_type=mime_type,
        content_bytes=content_bytes,
        text=text,
        bytes_sha256=output_hash,
        provenance=provenance,
        sections=sections,
    )


def _pdf_pages(text: str) -> tuple[tuple[str, ...], ...]:
    lines = _pdf_wrapped_lines(text)
    pages = tuple(
        tuple(lines[index : index + _PDF_LINES_PER_PAGE])
        for index in range(0, len(lines), _PDF_LINES_PER_PAGE)
    )
    return pages or (("",),)


def _pdf_wrapped_lines(text: str) -> list[str]:
    wrapped_lines: list[str] = []
    for raw_line in str(text or "").splitlines() or [""]:
        line = _normalize_pdf_text(raw_line.rstrip())
        if not line:
            wrapped_lines.append("")
            continue
        wrapped_lines.extend(
            textwrap.wrap(
                line,
                width=_PDF_WRAP_CHARS,
                replace_whitespace=False,
                drop_whitespace=True,
                break_long_words=True,
                break_on_hyphens=False,
            )
            or [""]
        )
    return wrapped_lines or [""]


def _pdf_document_bytes(pages: tuple[tuple[str, ...], ...]) -> bytes:
    page_objects: list[bytes] = []
    content_objects: list[bytes] = []
    kids: list[str] = []
    for index, page in enumerate(pages):
        page_object_number = 4 + (index * 2)
        content_object_number = page_object_number + 1
        kids.append(f"{page_object_number} 0 R")
        content_stream = _pdf_content_stream(page)
        page_objects.append(
            (
                "<< /Type /Page /Parent 2 0 R "
                f"/MediaBox [0 0 {_PDF_PAGE_WIDTH} {_PDF_PAGE_HEIGHT}] "
                "/Resources << /Font << /F1 3 0 R >> >> "
                f"/Contents {content_object_number} 0 R >>"
            ).encode("ascii")
        )
        content_objects.append(
            b"<< /Length "
            + str(len(content_stream)).encode("ascii")
            + b" >>\nstream\n"
            + content_stream
            + b"endstream"
        )

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(pages)} >>".encode("ascii"),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for page_object, content_object in zip(page_objects, content_objects, strict=True):
        objects.extend([page_object, content_object])
    return _pdf_serialize_objects(tuple(objects))


def _pdf_content_stream(lines: tuple[str, ...]) -> bytes:
    parts = [
        b"BT",
        f"/F1 {_PDF_FONT_SIZE} Tf".encode("ascii"),
        f"{_PDF_LEADING} TL".encode("ascii"),
        f"{_PDF_MARGIN_X} {_PDF_PAGE_HEIGHT - _PDF_MARGIN_TOP} Td".encode("ascii"),
    ]
    for index, line in enumerate(lines):
        if index:
            parts.append(b"T*")
        if line:
            parts.append(b"(" + _escape_pdf_literal(line) + b") Tj")
    parts.append(b"ET")
    return b"\n".join(parts) + b"\n"


def _pdf_serialize_objects(objects: tuple[bytes, ...]) -> bytes:
    output = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for object_number, payload in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{object_number} 0 obj\n".encode("ascii"))
        output.extend(payload)
        output.extend(b"\nendobj\n")

    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(output)


def _escape_pdf_literal(value: str) -> bytes:
    escaped = bytearray()
    for byte in _normalize_pdf_text(value).encode("latin-1", errors="replace"):
        if byte in {0x28, 0x29, 0x5C}:
            escaped.extend(b"\\" + bytes([byte]))
        elif byte == 0x09:
            escaped.extend(b"\\t")
        elif byte == 0x0A:
            escaped.extend(b"\\n")
        elif byte == 0x0D:
            escaped.extend(b"\\r")
        elif byte < 32 or byte > 126:
            escaped.extend(f"\\{byte:03o}".encode("ascii"))
        else:
            escaped.append(byte)
    return bytes(escaped)


def _normalize_pdf_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).replace("\t", "    ")
    characters: list[str] = []
    for character in normalized:
        codepoint = ord(character)
        if character in {"\n", "\r"}:
            characters.append(" ")
        elif codepoint < 32:
            continue
        elif codepoint <= 255:
            characters.append(character)
        else:
            fallback = (
                unicodedata.normalize("NFKD", character)
                .encode("latin-1", errors="ignore")
                .decode("latin-1")
            )
            characters.append(fallback or "?")
    return "".join(characters)


def _render_provenance(
    *,
    context: FormatRenderContext,
    renderer_name: str,
    output_hash: str,
    quality_result: QualityGateResult | None,
) -> dict[str, Any]:
    return {
        "renderer": {
            "name": renderer_name,
            "version": RENDERER_VERSION,
            "implementation": (
                f"application.services.deliverable_format_renderers.{renderer_name}"
            ),
        },
        "profile": {
            "profile_ref": context.profile.profile_ref,
            "profile_sha256": context.profile.profile_sha256,
        },
        "sources": {
            "service_deliverable_ids": [
                source.service_deliverable_id for source in context.sources
            ],
            "asset_version_ids": [source.asset_version_id for source in context.sources],
            "source_hashes": [source.content_hash for source in context.sources],
        },
        "request": {
            "request_id": context.request_id,
            "idempotency_key": context.idempotency_key,
        },
        "quality": {
            "gate_result_id": quality_result.gate_result_id if quality_result else None,
            "status": quality_result.status if quality_result else "not_run",
        },
        "output": {
            "bytes_sha256": output_hash,
            "asset_id": None,
            "asset_version_id": None,
        },
        "runtime": {"created_by": "backend_formatting_service"},
    }


def _zip_bytes(outputs: list[RenderedArtifact] | tuple[RenderedArtifact, ...]) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_STORED) as archive:
        for output in sorted(outputs, key=lambda item: item.filename):
            info = zipfile.ZipInfo(filename=output.filename, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, output.content_bytes)
    return buffer.getvalue()


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "deliverable-format"
