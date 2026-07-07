from __future__ import annotations

from application.services import atlas_prompt_delivery, codex_media_worker


def test_codex_spec_renderer_quality_contract_is_placeholder_not_production() -> None:
    contract = codex_media_worker.codex_spec_renderer_quality_contract()

    assert contract["renderer"] == "codex_spec_renderer"
    assert contract["quality_tier"] == "placeholder"
    assert contract["production_quality"] is False
    assert contract["codex_agent_artifacts_can_be_production_quality"] is True
    assert "real artifacts" in contract["upgrade_path"]


def test_client_handoff_html_renders_department_deliverable_substance() -> None:
    manifest = _manifest()
    sections = _substantive_sections()

    html = atlas_prompt_delivery._client_html(  # noqa: SLF001
        prompt="Create a client-ready Legacy Optical Noir weekend social launch package.",
        manifest=manifest,
        deliverable_sections=sections,
    )

    assert "Executive summary: make Optical Noir" in html
    assert "WhatsApp response scripts" in html
    assert "Measurement plan" in html
    assert "QA report" in html
    assert "assets/legacy_optical_noir_post_01.png" in html
    assert "Approval checkpoint" in html
    assert "Artifact Index" in html
    assert "Create a client-ready Legacy Optical Noir weekend social launch package" not in html
    assert "engagement-123" not in html
    assert "whiteboard-456" not in html
    assert len(html) > 3500


def test_client_handoff_html_converts_internal_markdown_to_polished_visible_html() -> None:
    manifest = _manifest()
    sections = _substantive_sections()
    sections[0]["content"] = """
# Strategy Brief: Legacy Optical Noir Weekend Social Launch

## Run Context

**Client:** Legacy
**Stage:** `strategy_research`
**Run Owner:** ForgeGraph
**Delivery Recipient:** Mike only
**Client File Rule:** Do not send Markdown files.
**Intended use:** Internal lineage for downstream HTML/PDF packaging.

## Recommendation
- Approve the Optical Noir visual system.
- Keep inventory language gated until final approval.

asset_version_id: av_123
service_deliverable_id: sd_456
"""

    html = atlas_prompt_delivery._client_html(  # noqa: SLF001
        prompt="Create a client-ready Legacy Optical Noir weekend social launch package.",
        manifest=manifest,
        deliverable_sections=sections,
    )

    visible_text = html
    assert "# Strategy Brief" not in visible_text
    assert "## Run Context" not in visible_text
    assert "Run Context" not in visible_text
    assert "**Client:**" not in visible_text
    assert "Stage:" not in visible_text
    assert "strategy_research" not in visible_text
    assert "Run Owner" not in visible_text
    assert "Delivery Recipient" not in visible_text
    assert "Client File Rule" not in visible_text
    assert "Intended use" not in visible_text
    assert "asset_version_id" not in visible_text
    assert "service_deliverable_id" not in visible_text
    assert "<h3>Strategy Brief: Legacy Optical Noir Weekend Social Launch</h3>" in html
    assert "<strong>Client:</strong> Legacy" in html
    assert "<li>Approve the Optical Noir visual system.</li>" in html
    assert "<li>Keep inventory language gated until final approval.</li>" in html


def test_client_handoff_pdf_text_removes_internal_markdown_and_ids() -> None:
    text = atlas_prompt_delivery._client_package_text(  # noqa: SLF001
        prompt="Create a client-ready Legacy package.",
        manifest=_manifest(),
        deliverable_sections=[
            {
                "title": "Strategy & Research",
                "content": """
# Strategy Brief
**Client:** Legacy
**Stage:** `strategy_research`
**Run Owner:** ForgeGraph
**Delivery Recipient:** Mike only
**Client File Rule:** Do not send Markdown files.
**Intended use:** Internal lineage.
- Approve Optical Noir.
asset_version_id: av_123
""",
            }
        ],
    )

    assert "# Strategy Brief" not in text
    assert "**Client:**" not in text
    assert "Stage:" not in text
    assert "strategy_research" not in text
    assert "Run Owner" not in text
    assert "Delivery Recipient" not in text
    assert "Client File Rule" not in text
    assert "Intended use" not in text
    assert "asset_version_id" not in text
    assert "Strategy Brief" in text
    assert "Client: Legacy" in text
    assert "Approve Optical Noir." in text
    assert "Create a client-ready Legacy package." not in text
    assert "Source prompt" not in text
    assert "engagement-123" not in text
    assert "whiteboard-456" not in text


def test_client_handoff_rendering_converts_markdown_tables_to_client_copy() -> None:
    table_content = """
## Weekend Social Rollout
| Timing | Social Role | CTA |
|---|---|---|
| Friday evening | Launch the mood | View the collection |
| Saturday morning | Product clarity | Book a fitting |
"""

    html = atlas_prompt_delivery._client_section_body_html(table_content)  # noqa: SLF001
    text = atlas_prompt_delivery._client_plain_text(table_content)  # noqa: SLF001

    assert "|---|" not in html
    assert "| Timing |" not in html
    assert "<li><strong>Timing:</strong> Friday evening; <strong>Social Role:</strong> Launch the mood; <strong>CTA:</strong> View the collection</li>" in html
    assert "<li><strong>Timing:</strong> Saturday morning; <strong>Social Role:</strong> Product clarity; <strong>CTA:</strong> Book a fitting</li>" in html
    assert "|---|" not in text
    assert "Timing: Friday evening; Social Role: Launch the mood; CTA: View the collection" in text


def test_client_package_media_content_prefers_review_asset_override(tmp_path, monkeypatch) -> None:
    override_dir = tmp_path / "review-assets"
    override_dir.mkdir()
    override_asset = override_dir / "legacy_optical_noir_post_01.png"
    override_asset.write_bytes(b"review-ready-png")
    monkeypatch.setenv("FORGEGRAPH_ATLAS_REVIEW_ASSETS_DIR", str(override_dir))

    content, metadata = atlas_prompt_delivery._client_package_media_content(  # noqa: SLF001
        job=object(), index=1
    )

    assert content == b"review-ready-png"
    assert metadata["asset_source"] == "operator_review_assets_override"
    assert metadata["quality_tier"] == "review_ready_ai_generated"
    assert metadata["production_quality"] is True


def test_client_handoff_pdf_prefers_html_browser_renderer(tmp_path, monkeypatch) -> None:
    html_path = tmp_path / "Legacy_Optical_Noir_Handoff.html"
    html_path.write_text("<html><body><h1>Premium HTML report</h1></body></html>", encoding="utf-8")
    rendered = b"%PDF-1.4\nhtml-rendered-pdf\n%%EOF\n"

    def fake_render(path):
        assert path == html_path
        assert "Premium HTML report" in path.read_text(encoding="utf-8")
        return rendered

    monkeypatch.setattr(atlas_prompt_delivery, "_render_html_pdf_with_playwright", fake_render)

    pdf = atlas_prompt_delivery._client_pdf_bytes(  # noqa: SLF001
        html_path=html_path,
        fallback_text="plain fallback that should not be used",
    )

    assert pdf == rendered
    assert b"plain fallback" not in pdf


def test_client_handoff_pdf_falls_back_to_plain_renderer_when_browser_unavailable(tmp_path, monkeypatch) -> None:
    html_path = tmp_path / "Legacy_Optical_Noir_Handoff.html"
    html_path.write_text("<html><body><h1>HTML report</h1></body></html>", encoding="utf-8")

    def fake_render(path):
        raise RuntimeError("playwright unavailable")

    monkeypatch.setattr(atlas_prompt_delivery, "_render_html_pdf_with_playwright", fake_render)

    pdf = atlas_prompt_delivery._client_pdf_bytes(  # noqa: SLF001
        html_path=html_path,
        fallback_text="Fallback client PDF text with Measurement plan",
    )

    assert pdf.startswith(b"%PDF-")
    assert pdf.rstrip().endswith(b"%%EOF")
    assert b"Measurement plan" in pdf


def test_html_pdf_playwright_script_uses_print_css_and_container_safe_chromium() -> None:
    script = atlas_prompt_delivery._HTML_TO_PDF_PLAYWRIGHT_SCRIPT  # noqa: SLF001

    assert "await page.emulateMedia({ media: 'print' });" in script
    assert "process.getuid && process.getuid() === 0" in script
    assert "--no-sandbox" in script
    assert "--disable-dev-shm-usage" in script


def test_legacy_strategy_copy_explains_noir_without_nighttime_sunglasses_confusion() -> None:
    content = atlas_prompt_delivery._message_house(  # noqa: SLF001
        "Create a client-ready Legacy Optical Noir weekend social launch package."
    )

    lowered = content.lower()
    assert "strategic rationale" in lowered
    assert "contrast" in lowered
    assert "product photography" in lowered
    assert "not a literal night-use claim" in lowered
    assert "source request:" not in lowered


def test_legacy_measurement_copy_distinguishes_social_rollout_from_shipping() -> None:
    content = atlas_prompt_delivery._measurement_plan()  # noqa: SLF001

    lowered = content.lower()
    assert "weekend social rollout" in lowered
    assert "posting" in lowered
    assert "not a shipping or fulfillment timeline" in lowered
    assert "distribution" not in lowered


def test_media_prompts_include_legacy_brand_presence_requirement() -> None:
    prompts = atlas_prompt_delivery._media_prompts(  # noqa: SLF001
        "Create Legacy social posts with logo on each post."
    )

    assert prompts
    assert all("Legacy" in prompt for prompt in prompts)
    assert all("logo" in prompt.lower() or "brand mark" in prompt.lower() for prompt in prompts)
    assert all("no logos" not in prompt.lower() for prompt in prompts)
    assert all("fake brand marks" in prompt.lower() for prompt in prompts)


def test_asset_quality_gate_blocks_missing_logo_and_client_flagged_assets() -> None:
    requirements = atlas_prompt_delivery._legacy_brand_requirements()  # noqa: SLF001

    report = atlas_prompt_delivery._asset_quality_gate_status(  # noqa: SLF001
        [
            {
                "post": 1,
                "production_quality": True,
                "brand_mark_applied": False,
            },
            {
                "post": 2,
                "production_quality": True,
                "brand_mark_applied": True,
                "client_flagged_bad": True,
            },
            {
                "post": 3,
                "production_quality": False,
                "brand_mark_applied": True,
            },
        ],
        logo_required=requirements["logo_required_on_posts"],
    )

    assert report["ready"] is False
    assert {issue["code"] for issue in report["issues"]} == {
        "missing_brand_mark",
        "client_flagged_bad",
        "not_production_quality",
    }
    assert {issue["post"] for issue in report["issues"]} == {1, 2, 3}


def test_client_package_gate_report_requires_strategy_brand_assets_and_safe_copy() -> None:
    report = atlas_prompt_delivery._client_package_gate_report(  # noqa: SLF001
        manifest={
            "media": [
                {
                    "post": 1,
                    "production_quality": True,
                    "brand_mark_applied": False,
                }
            ],
            "brand_requirements": {"logo_required_on_posts": True},
        },
        deliverable_sections=[
            {
                "title": "Strategy & Research",
                "content": "Optical Noir weekend distribution plan with no rationale.",
            }
        ],
    )

    assert report["ready"] is False
    assert {issue["code"] for issue in report["issues"]} >= {
        "missing_strategy_rationale",
        "ambiguous_distribution_copy",
        "missing_brand_mark",
    }


def test_client_handoff_pdf_contains_substantive_source_text() -> None:
    body_text = "\n".join(
        [
            "Legacy Optical Noir — client handoff",
            "Executive summary: make Optical Noir feel premium, local, and appointment-worthy.",
            "Strategy: focus the launch around evening use cases, smoked glass styling, and approval-gated scarcity.",
            "Brand content: Spanish-first, low-hype, confident copy with clear review CTAs and no fake launch claims.",
            "Creative direction: use noir surfaces, warm ivory contrast, copper details, and green lens reflections.",
            "CRM scripts: handle price, availability, holds, and follow-up objections without overpromising inventory.",
            "Measurement plan: saves, replies, profile visits, link clicks, DMs, holds, and sold status.",
            "QA report: no live publishing claim; approval required before production launch.",
        ]
        * 4
    )

    pdf = atlas_prompt_delivery._client_pdf_bytes(body_text)  # noqa: SLF001

    assert pdf.startswith(b"%PDF-")
    assert pdf.rstrip().endswith(b"%%EOF")
    assert b"Executive summary" in pdf
    assert b"Measurement plan" in pdf
    assert len(pdf) > 2200


def _manifest() -> dict:
    return {
        "engagement_id": "engagement-123",
        "whiteboard_id": "whiteboard-456",
        "media": [
            {"post": 1, "filename": "assets/legacy_optical_noir_post_01.png"},
            {"post": 2, "filename": "assets/legacy_optical_noir_post_02.png"},
        ],
    }


def _substantive_sections() -> list[dict[str, str]]:
    return [
        {
            "title": "Strategy & Research",
            "content": "Executive summary: make Optical Noir feel premium, local, and appointment-worthy.",
        },
        {
            "title": "Brand & Content",
            "content": "Message house: Spanish-first, low-hype, confident, with approval-first CTA.",
        },
        {
            "title": "CRM & Lifecycle",
            "content": "WhatsApp response scripts for price, availability, hold, and follow-up objections.",
        },
        {
            "title": "Analytics & Performance",
            "content": "Measurement plan: saves, replies, profile visits, link clicks, DMs, holds, and sold status.",
        },
        {
            "title": "QA & Compliance",
            "content": "QA report: no live publishing claim, connector caveats, and approval before launch.",
        },
    ]
