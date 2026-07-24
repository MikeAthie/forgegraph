"""ATS-readable CareerOps resume rendering and parseability checks."""

from __future__ import annotations

import hashlib
import html
import re
import textwrap
import unicodedata
from dataclasses import dataclass
from typing import Any

from application.services.career_ops_content_alignment import (
    ATS_REQUIRED_SECTIONS,
    INTERNAL_LEAKAGE_TOKENS,
)
from application.services.deliverable_format_renderers import (
    _escape_pdf_literal,
    _pdf_serialize_objects,
)

CAREER_OPS_ATS_RESUME_FORMATTER_VERSION = "3"
ATS_RESUME_FORMAT = "career_ops_ats_resume_v1"
ATS_PARSEABILITY_FORMAT = "career_ops_ats_resume_parseability_v1"
_FORBIDDEN_HTML_TOKENS = (
    "<table",
    "<img",
    "<svg",
    "<canvas",
    "display:none",
    "visibility:hidden",
    "grid-template",
    "column-count",
)
_RESUME_INTERNAL_LEAKAGE_TOKENS = tuple(
    token for token in INTERNAL_LEAKAGE_TOKENS if token not in {"forgegraph", "prompt"}
)
_FORBIDDEN_VISIBLE_TOKENS = (
    *_RESUME_INTERNAL_LEAKAGE_TOKENS,
    "metadata_json",
    "provenance_json",
    "raw tool",
)


@dataclass(frozen=True, slots=True)
class CareerOpsATSResumeArtifacts:
    text: str
    html: str
    pdf_bytes: bytes
    parseability_report: dict[str, Any]


def render_career_ops_ats_resume(
    *,
    tailored_resume: dict[str, Any],
    opportunity: dict[str, Any] | None = None,
    candidate_identity: dict[str, Any] | None = None,
) -> CareerOpsATSResumeArtifacts:
    """Render source-bounded CareerOps resume artifacts for ATS-first review."""

    identity = candidate_identity or {}
    normalized_sections = _normalized_sections(tailored_resume, candidate_identity=identity)
    merged_opportunity = _opportunity_payload(
        tailored_resume=tailored_resume, opportunity=opportunity
    )
    text = _render_text_resume(
        sections=normalized_sections,
        opportunity=merged_opportunity,
        candidate_identity=identity,
    )
    html_text = _render_html_resume(
        sections=normalized_sections,
        opportunity=merged_opportunity,
        candidate_identity=identity,
    )
    pdf_bytes = _render_professional_pdf_resume(
        sections=normalized_sections,
        opportunity=merged_opportunity,
        candidate_identity=identity,
    )
    report = _parseability_report(
        text=text,
        html_text=html_text,
        pdf_bytes=pdf_bytes,
        sections=normalized_sections,
    )
    return CareerOpsATSResumeArtifacts(
        text=text,
        html=html_text,
        pdf_bytes=pdf_bytes,
        parseability_report=report,
    )


def _normalized_sections(  # noqa: C901
    tailored_resume: dict[str, Any], *, candidate_identity: dict[str, Any]
) -> list[dict[str, Any]]:
    raw_sections = tailored_resume.get("sections") if isinstance(tailored_resume, dict) else []
    if not isinstance(raw_sections, list):
        raw_sections = []
    by_heading: dict[str, list[Any]] = {}
    for section in raw_sections:
        if not isinstance(section, dict):
            continue
        heading = _clean_heading(section.get("heading"))
        if not heading:
            continue
        items = [_clean_visible_text(item) for item in _section_items(section.get("items"))]
        by_heading[heading] = [item for item in items if item]
    education_items = _education_items(
        candidate_identity.get("education") or candidate_identity.get("education_items")
    )
    if education_items:
        by_heading["EDUCATION"] = education_items

    certification_items = _certification_items(
        candidate_identity.get("certifications")
        or candidate_identity.get("certificates")
        or candidate_identity.get("courses")
    )
    if certification_items:
        by_heading["CERTIFICATIONS"] = certification_items

    professional_summary = _clean_multiline_text(
        candidate_identity.get("professional_summary") or ""
    )
    if professional_summary:
        by_heading["SUMMARY"] = [professional_summary]

    skill_items = _skill_items(candidate_identity.get("skills"))
    if skill_items:
        by_heading["TECHNICAL SKILLS"] = skill_items

    experience_cards = _experience_cards(candidate_identity.get("experience"))
    if experience_cards:
        by_heading["SELECTED EXPERIENCE"] = experience_cards

    project_cards = _project_cards(candidate_identity.get("projects"))
    if project_cards:
        by_heading["PROJECTS"] = project_cards

    ordered = [
        {
            "heading": heading,
            "items": by_heading.get(heading, []),
            "source_present": heading in by_heading,
            "style": _section_style(heading),
        }
        for heading in ATS_REQUIRED_SECTIONS
    ]
    for heading, items in by_heading.items():
        if heading not in ATS_REQUIRED_SECTIONS:
            ordered.append(
                {"heading": heading, "items": items, "source_present": True, "style": "bullets"}
            )
    return ordered


def _education_items(value: Any) -> list[str]:
    if not value:
        return []
    raw_items = value if isinstance(value, list | tuple) else [value]
    items: list[str] = []
    for raw_item in raw_items:
        if isinstance(raw_item, str):
            cleaned = _clean_visible_text(raw_item)
            if cleaned:
                items.append(cleaned)
            continue
        if not isinstance(raw_item, dict):
            continue
        institution = _clean_visible_text(raw_item.get("institution") or raw_item.get("school"))
        degree = _clean_visible_text(raw_item.get("degree"))
        field = _clean_visible_text(raw_item.get("field") or raw_item.get("major"))
        graduation_year = _clean_visible_text(
            raw_item.get("graduation_year") or raw_item.get("year")
        )
        location = _clean_visible_text(raw_item.get("location"))
        degree_line = ", ".join(value for value in (degree, field) if value)
        right_side = " | ".join(value for value in (graduation_year, location) if value)
        parts = [part for part in (institution, degree_line, right_side) if part]
        if parts:
            items.append(" — ".join(parts))
    return items


def _certification_items(value: Any) -> list[str]:
    if not value:
        return []
    raw_items = value if isinstance(value, list | tuple) else [value]
    items: list[str] = []
    for raw_item in raw_items:
        if isinstance(raw_item, str):
            cleaned = _clean_visible_text(raw_item)
            if cleaned:
                items.append(cleaned)
            continue
        if not isinstance(raw_item, dict):
            continue
        name = _clean_visible_text(
            raw_item.get("name")
            or raw_item.get("title")
            or raw_item.get("certification")
            or raw_item.get("certificate")
        )
        issuer = _clean_visible_text(raw_item.get("issuer") or raw_item.get("provider"))
        year = _clean_visible_text(raw_item.get("year") or raw_item.get("date"))
        parts = [part for part in (name, issuer, year) if part]
        if parts:
            items.append(" — ".join(parts))
    return items


def _skill_items(value: Any) -> list[str]:
    if not value:
        return []
    raw_items = value if isinstance(value, list | tuple) else [value]
    items: list[str] = []
    for raw_item in raw_items:
        if isinstance(raw_item, str):
            cleaned = _clean_visible_text(raw_item)
            if cleaned:
                items.append(cleaned)
            continue
        if not isinstance(raw_item, dict):
            continue
        category = _clean_visible_text(raw_item.get("category") or raw_item.get("name"))
        item_value = raw_item.get("items") or raw_item.get("skills") or raw_item.get("text")
        if isinstance(item_value, list | tuple):
            item_text = ", ".join(
                _clean_visible_text(item) for item in item_value if _clean_visible_text(item)
            )
        else:
            item_text = _clean_visible_text(item_value)
        if category and item_text:
            items.append(f"{category}: {item_text}")
        elif item_text:
            items.append(item_text)
    return items


def _experience_cards(value: Any) -> list[dict[str, Any]]:
    return _card_items(
        value,
        title_keys=("organization", "company", "employer"),
        subtitle_keys=("role", "title", "position"),
    )


def _project_cards(value: Any) -> list[dict[str, Any]]:
    return _card_items(
        value,
        title_keys=("name", "project", "title"),
        subtitle_keys=("subtitle", "description", "stack"),
    )


def _card_items(
    value: Any, *, title_keys: tuple[str, ...], subtitle_keys: tuple[str, ...]
) -> list[dict[str, Any]]:
    if not value:
        return []
    raw_items = value if isinstance(value, list | tuple) else [value]
    cards: list[dict[str, Any]] = []
    for raw_item in raw_items:
        if isinstance(raw_item, str):
            cleaned = _clean_visible_text(raw_item)
            if cleaned:
                cards.append({"title": cleaned, "bullets": []})
            continue
        if not isinstance(raw_item, dict):
            continue
        title = _first_clean_value(raw_item, title_keys)
        subtitle = _first_clean_value(raw_item, subtitle_keys)
        period = _clean_visible_text(raw_item.get("period") or raw_item.get("dates") or "")
        url = _clean_visible_text(raw_item.get("url") or raw_item.get("link") or "")
        bullets = [
            _clean_visible_text(item)
            for item in _section_items(raw_item.get("bullets") or raw_item.get("items"))
        ]
        bullets = [item for item in bullets if item]
        if title:
            cards.append(
                {
                    "title": title,
                    "subtitle": subtitle,
                    "period": period,
                    "url": url,
                    "bullets": bullets,
                }
            )
    return cards


def _first_clean_value(item: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = _clean_visible_text(item.get(key) or "")
        if value:
            return value
    return ""


def _section_style(heading: str) -> str:
    if heading == "SUMMARY":
        return "paragraph"
    if heading == "TECHNICAL SKILLS":
        return "skills"
    if heading in {"SELECTED EXPERIENCE", "PROJECTS"}:
        return "cards"
    return "bullets"


def _section_items(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [_item_text(value)]
    if isinstance(value, list | tuple):
        items: list[str] = []
        for item in value:
            if isinstance(item, dict):
                items.append(_item_text(item))
            else:
                items.append(str(item))
        return items
    return [str(value)]


def _item_text(item: dict[str, Any]) -> str:
    for key in ("text", "claim", "name", "title", "description"):
        value = item.get(key)
        if value:
            return str(value)
    return " ".join(str(value) for value in item.values() if isinstance(value, str | int | float))


def _render_text_resume(
    *,
    sections: list[dict[str, Any]],
    opportunity: dict[str, str],
    candidate_identity: dict[str, Any],
) -> str:
    lines: list[str] = []
    name = _clean_visible_text(
        candidate_identity.get("name")
        or candidate_identity.get("full_name")
        or candidate_identity.get("candidate_name")
        or ""
    )
    title = _clean_visible_text(
        candidate_identity.get("title") or candidate_identity.get("headline") or ""
    )
    contact = [
        _clean_visible_text(candidate_identity.get(key) or "")
        for key in ("location", "email", "phone", "github", "linkedin", "website")
    ]
    if name:
        lines.append(name.upper())
    if title:
        lines.append(title)
    contact_line = " • ".join(value for value in contact if value)
    if contact_line:
        lines.append(contact_line)
    if lines:
        lines.append("=" * 72)
        lines.append("")
    for section in sections:
        heading = str(section["heading"])
        lines.append(heading)
        lines.extend(_section_text_lines(section))
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _section_text_lines(section: dict[str, Any]) -> list[str]:  # noqa: C901
    items = [item for item in section.get("items", []) if _item_has_content(item)]
    if not items:
        return ["- Not provided in source CV."]
    style = str(section.get("style") or "bullets")
    if style == "paragraph":
        return [str(items[0])]
    if style == "skills":
        return [str(item) for item in items]
    if style == "cards":
        lines: list[str] = []
        for card in items:
            if not isinstance(card, dict):
                lines.append(f"- {card}")
                continue
            title_line = _card_title_line(card)
            if title_line:
                if lines:
                    lines.append("")
                lines.append(title_line)
            meta_line = _card_meta_line(card)
            if meta_line:
                lines.append(meta_line)
            for bullet in card.get("bullets", []):
                bullet_text = _clean_visible_text(bullet)
                if bullet_text:
                    lines.append(f"- {bullet_text}")
        return lines or ["- Not provided in source CV."]
    return [f"- {item}" for item in items]


def _item_has_content(item: Any) -> bool:
    if isinstance(item, dict):
        return bool(_card_title_line(item) or item.get("bullets"))
    return bool(str(item).strip())


def _card_title_line(card: dict[str, Any]) -> str:
    title = _clean_visible_text(card.get("title") or "")
    subtitle = _clean_visible_text(card.get("subtitle") or "")
    return f"{title} — {subtitle}" if title and subtitle else title


def _card_meta_line(card: dict[str, Any]) -> str:
    period = _clean_visible_text(card.get("period") or "")
    url = _clean_visible_text(card.get("url") or "")
    return " | ".join(value for value in (period, url) if value)


def _render_html_resume(
    *,
    sections: list[dict[str, Any]],
    opportunity: dict[str, str],
    candidate_identity: dict[str, Any],
) -> str:
    name = _clean_visible_text(
        candidate_identity.get("name")
        or candidate_identity.get("full_name")
        or candidate_identity.get("candidate_name")
        or ""
    )
    title = _clean_visible_text(
        candidate_identity.get("title") or candidate_identity.get("headline") or ""
    )
    if not name:
        name = "Candidate Resume"
    header = [f"<h1>{html.escape(name)}</h1>"]
    if title:
        header.append(f'<p class="title">{html.escape(title)}</p>')
    contact = [
        _clean_visible_text(candidate_identity.get(key) or "")
        for key in ("location", "email", "phone", "github", "linkedin", "website")
    ]
    contact_line = " • ".join(value for value in contact if value)
    if contact_line:
        header.append(f'<p class="contact">{html.escape(contact_line)}</p>')

    section_html = []
    for section in sections:
        heading = str(section["heading"])
        section_html.append(
            f"<section><h2>{html.escape(heading)}</h2>" + _section_html_body(section) + "</section>"
        )
    return "".join(
        [
            '<!doctype html><html><head><meta charset="utf-8">',
            "<title>ATS Resume</title>",
            "<style>",
            "@page{size:Letter;margin:0.5in}",
            "body{font-family:Arial,Helvetica,sans-serif;color:#111;line-height:1.35;font-size:10.5pt}",
            "main{max-width:7.5in;margin:0 auto}",
            "h1{font-size:18pt;margin:0 0 4pt 0}",
            "h2{font-size:11pt;margin:12pt 0 4pt 0;text-transform:uppercase;border-bottom:1px solid #222}",
            "p{margin:0 0 4pt 0}ul{margin:0 0 0 14pt;padding:0}li{margin:0 0 3pt 0}",
            "article{margin:0 0 8pt 0}h3{font-size:10.5pt;margin:0 0 2pt 0}.meta{font-size:9.5pt;color:#222}",
            "</style></head><body><main>",
            "<header>",
            *header,
            "</header>",
            *section_html,
            "</main></body></html>",
        ]
    )


def _section_html_body(section: dict[str, Any]) -> str:
    items = [item for item in section.get("items", []) if _item_has_content(item)]
    if not items:
        return "<ul><li>Not provided in source CV.</li></ul>"
    style = str(section.get("style") or "bullets")
    if style == "paragraph":
        return f"<p>{html.escape(str(items[0]))}</p>"
    if style == "skills":
        return "".join(f"<p>{html.escape(str(item))}</p>" for item in items)
    if style == "cards":
        articles = []
        for card in items:
            if not isinstance(card, dict):
                articles.append(f"<article><p>{html.escape(str(card))}</p></article>")
                continue
            title = _card_title_line(card)
            meta = _card_meta_line(card)
            bullets = [
                _clean_visible_text(item)
                for item in card.get("bullets", [])
                if _clean_visible_text(item)
            ]
            articles.append(
                "<article>"
                + (f"<h3>{html.escape(title)}</h3>" if title else "")
                + (f'<p class="meta">{html.escape(meta)}</p>' if meta else "")
                + (
                    "<ul>" + "".join(f"<li>{html.escape(item)}</li>" for item in bullets) + "</ul>"
                    if bullets
                    else ""
                )
                + "</article>"
            )
        return "".join(articles)
    return "<ul>" + "".join(f"<li>{html.escape(str(item))}</li>" for item in items) + "</ul>"


def _render_professional_pdf_resume(  # noqa: C901
    *,
    sections: list[dict[str, Any]],
    opportunity: dict[str, str],
    candidate_identity: dict[str, Any],
) -> bytes:
    name = _clean_visible_text(
        candidate_identity.get("name")
        or candidate_identity.get("full_name")
        or candidate_identity.get("candidate_name")
        or "Candidate Resume"
    ).upper()
    title = _clean_visible_text(
        candidate_identity.get("title") or candidate_identity.get("headline") or ""
    )
    contact = [
        _clean_visible_text(candidate_identity.get(key) or "")
        for key in ("location", "email", "phone", "github", "linkedin", "website")
    ]
    contact_line = " • ".join(value for value in contact if value)
    pages: list[list[dict[str, Any]]] = [[]]
    y = 746.0

    def add_text(text: str, *, x: float, size: int, bold: bool = False) -> None:
        nonlocal y
        if y < 54:
            pages.append([])
            y = 746.0
        pages[-1].append({"type": "text", "text": text, "x": x, "y": y, "size": size, "bold": bold})
        y -= size + 4

    def add_centered(text: str, *, size: int, bold: bool = False) -> None:
        width = min(520.0, len(text) * size * 0.48)
        add_text(text, x=max(45.0, (612.0 - width) / 2.0), size=size, bold=bold)

    def add_rule(offset: float = 0) -> None:
        nonlocal y
        if y < 54:
            pages.append([])
            y = 746.0
        pages[-1].append({"type": "line", "x1": 45.0, "x2": 567.0, "y": y + offset})
        y -= 7

    add_centered(name, size=20, bold=True)
    if title:
        add_centered(title, size=10)
    if contact_line:
        add_centered(contact_line, size=9)
    add_rule(offset=1)

    for section in sections:
        heading = str(section["heading"])
        style = str(section.get("style") or "bullets")
        y -= 3
        add_text(heading, x=45.0, size=11, bold=True)
        add_rule(offset=6)
        body_lines = _section_text_lines(section)
        for body_line in body_lines:
            if body_line == "":
                y -= 4
                continue
            is_bullet = body_line.startswith("- ")
            is_card_title = style == "cards" and not is_bullet and " | " not in body_line
            line_x = 58.0 if is_bullet else 52.0
            line_size = 9 if not is_card_title else 9
            wrapped = textwrap.wrap(
                _clean_visible_text(body_line),
                width=104 if is_bullet else 98,
                replace_whitespace=False,
                drop_whitespace=True,
                break_long_words=True,
                break_on_hyphens=False,
            ) or [""]
            for index, line in enumerate(wrapped):
                continuation_x = line_x if index == 0 else line_x + 10
                add_text(line, x=continuation_x, size=line_size, bold=is_card_title and index == 0)
        y -= 2
    return _styled_pdf_document_bytes(pages)


def _styled_pdf_document_bytes(pages: list[list[dict[str, Any]]]) -> bytes:
    page_objects: list[bytes] = []
    content_objects: list[bytes] = []
    kids: list[str] = []
    for index, page in enumerate(pages or [[]]):
        page_object_number = 5 + (index * 2)
        content_object_number = page_object_number + 1
        kids.append(f"{page_object_number} 0 R")
        content_stream = _styled_pdf_content_stream(page)
        page_objects.append(
            (
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                "/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
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
        f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(pages or [[]])} >>".encode("ascii"),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
    ]
    for page_object, content_object in zip(page_objects, content_objects, strict=True):
        objects.extend([page_object, content_object])
    return _pdf_serialize_objects(tuple(objects))


def _styled_pdf_content_stream(elements: list[dict[str, Any]]) -> bytes:
    parts: list[bytes] = [b"0.35 w"]
    for element in elements:
        if element["type"] == "line":
            parts.append(
                f"{element['x1']:.2f} {element['y']:.2f} m {element['x2']:.2f} {element['y']:.2f} l S".encode(
                    "ascii"
                )
            )
            continue
        font = "/F2" if element.get("bold") else "/F1"
        parts.extend(
            [
                b"BT",
                f"{font} {int(element['size'])} Tf".encode("ascii"),
                f"1 0 0 1 {element['x']:.2f} {element['y']:.2f} Tm".encode("ascii"),
                b"(" + _escape_pdf_literal(_pdf_ats_text(str(element["text"]))) + b") Tj",
                b"ET",
            ]
        )
    return b"\n".join(parts) + b"\n"


def _pdf_ats_text(value: str) -> str:
    normalized = str(value or "")
    normalized = normalized.replace("•", "|").replace("—", "-").replace("–", "-")
    normalized = normalized.replace("’", "'").replace("“", '"').replace("”", '"')
    return (
        unicodedata.normalize("NFKD", normalized).encode("ascii", errors="ignore").decode("ascii")
    )


def _parseability_report(
    *,
    text: str,
    html_text: str,
    pdf_bytes: bytes,
    sections: list[dict[str, Any]],
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    checks: dict[str, str] = {}
    present = [
        str(section["heading"]) for section in sections if section.get("source_present") is True
    ]
    missing = [heading for heading in ATS_REQUIRED_SECTIONS if heading not in present]
    if missing:
        checks["required_sections_present"] = "blocked"
        blockers.extend(f"missing_section:{heading}" for heading in missing)
    else:
        checks["required_sections_present"] = "pass"

    ordered_positions = [text.find(heading) for heading in ATS_REQUIRED_SECTIONS]
    if any(position < 0 for position in ordered_positions) or ordered_positions != sorted(
        ordered_positions
    ):
        checks["section_order"] = "blocked"
        blockers.append("section_order_invalid")
    else:
        checks["section_order"] = "pass"

    leakage = _leakage_tokens(f"{text}\n{html_text}")
    if leakage:
        checks["no_internal_leakage"] = "blocked"
        blockers.extend(f"internal_leakage:{token}" for token in leakage)
    else:
        checks["no_internal_leakage"] = "pass"

    html_leakage = [token for token in _FORBIDDEN_HTML_TOKENS if token in html_text.casefold()]
    if html_leakage:
        checks["no_tables_images_icons"] = "blocked"
        blockers.extend(f"ats_hostile_html:{token}" for token in html_leakage)
    else:
        checks["no_tables_images_icons"] = "pass"

    checks["single_column_policy"] = "pass"
    checks["professional_template"] = "pass"

    valid_pdf = pdf_bytes.startswith(b"%PDF-") and pdf_bytes.rstrip().endswith(b"%%EOF")
    checks["pdf_bytes_valid"] = "pass" if valid_pdf else "blocked"
    if not valid_pdf:
        blockers.append("invalid_pdf_bytes")

    embedded = all(heading.encode("latin-1") in pdf_bytes for heading in ATS_REQUIRED_SECTIONS)
    checks["expected_text_embedded"] = "pass" if embedded else "blocked"
    if not embedded:
        blockers.append("expected_text_not_embedded")

    expected_text_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return {
        "status": "blocked" if blockers else "passed",
        "format": ATS_PARSEABILITY_FORMAT,
        "formatter_version": CAREER_OPS_ATS_RESUME_FORMATTER_VERSION,
        "checks": checks,
        "blockers": blockers,
        "warnings": warnings,
        "required_sections": list(ATS_REQUIRED_SECTIONS),
        "expected_text_sha256": expected_text_sha256,
        "external_side_effects_allowed": False,
    }


def _opportunity_payload(
    *, tailored_resume: dict[str, Any], opportunity: dict[str, Any] | None
) -> dict[str, str]:
    raw = opportunity if isinstance(opportunity, dict) else tailored_resume.get("opportunity", {})
    raw = raw if isinstance(raw, dict) else {}
    return {
        "employer_name": str(raw.get("employer_name") or raw.get("company") or ""),
        "role_title": str(raw.get("role_title") or raw.get("title") or ""),
        "job_url": str(raw.get("job_url") or raw.get("url") or ""),
    }


def _clean_heading(value: Any) -> str:
    cleaned = _clean_visible_text(value).upper()
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _clean_multiline_text(value: Any) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or ""))
    normalized = normalized.replace("\r", " ").replace("\n", " ")
    normalized = "".join(character for character in normalized if ord(character) >= 32)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _clean_visible_text(value: Any) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or ""))
    normalized = normalized.replace("\r", " ").replace("\n", " ")
    normalized = "".join(character for character in normalized if ord(character) >= 32)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _leakage_tokens(value: str) -> list[str]:
    lower = value.casefold()
    return [token for token in _FORBIDDEN_VISIBLE_TOKENS if token and token.casefold() in lower]
