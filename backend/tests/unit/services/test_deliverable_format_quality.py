from __future__ import annotations

import pytest

from application.services.deliverable_format_profiles import load_format_profile_registry
from application.services.deliverable_format_quality import (
    RenderedSection,
    evaluate_render_quality,
)


def _sections() -> list[RenderedSection]:
    return [
        RenderedSection(
            id="executive_summary",
            title="Executive Summary",
            content="Legacy is ready to review the handoff package.",
        ),
        RenderedSection(
            id="evidence",
            title="Evidence",
            content="Facts: source receipts and metric snapshots are attached.",
        ),
        RenderedSection(
            id="recommendations",
            title="Recommendations",
            content="Recommendation: approve the next production step.",
        ),
    ]


def test_quality_gates_pass_client_ready_marketing_and_consulting_reports() -> None:
    registry = load_format_profile_registry()
    cases = [
        (
            "format_profile:legacy.client_handoff@1",
            "Legacy",
            "Atlas",
            "Connector caveat: unverified connector outputs require receipt review.",
        ),
        (
            "format_profile:consulting.standard_handoff@1",
            "Northstar Advisory",
            "ForgeGraph Consulting",
            "Connector caveat: source-system extracts require client verification.",
        ),
    ]

    for profile_ref, client_name, provider_name, caveat in cases:
        profile = registry.get(profile_ref)
        sections = [
            RenderedSection(
                id="executive_summary",
                title=profile.section_by_id("executive_summary").title,
                content=f"{provider_name} prepared this package for {client_name}.",
            ),
            RenderedSection(
                id="evidence",
                title=profile.section_by_id("evidence").title,
                content="Facts: source evidence is separated here.",
            ),
            RenderedSection(
                id="recommendations",
                title=profile.section_by_id("recommendations").title,
                content="Recommendation: approve the next production step.",
            ),
        ]
        text = "\n\n".join(
            [section.content for section in sections]
            + [
                caveat,
                "Approval required before production execution.",
            ]
        )

        result = evaluate_render_quality(
            profile=profile,
            rendered_text=text,
            sections=sections,
            source_metadata=[{"connector_status": "unverified", "requires_approval": True}],
        )

        assert result.status == "passed"
        assert not result.blocked_reasons
        assert {check.id for check in result.checks if check.status == "passed"} >= {
            "no_placeholders",
            "no_ai_meta_language",
            "required_sections",
            "naming_consistency",
            "evidence_recommendation_separation",
            "connector_caveats",
            "approval_language",
        }


@pytest.mark.parametrize(
    ("text", "expected_check_id"),
    [
        ("Executive Summary for {{ client_name }}.", "no_placeholders"),
        ("As an AI, I recommend this.", "no_ai_meta_language"),
    ],
)
def test_quality_gates_block_unresolved_tokens_and_ai_meta_language(
    text: str,
    expected_check_id: str,
) -> None:
    profile = load_format_profile_registry().get("format_profile:legacy.client_handoff@1")

    result = evaluate_render_quality(
        profile=profile,
        rendered_text=text,
        sections=_sections(),
        source_metadata=[],
    )

    assert result.status == "blocked"
    assert expected_check_id in {check.id for check in result.checks if check.status == "failed"}


def test_quality_gates_block_missing_sections_and_missing_policy_language() -> None:
    profile = load_format_profile_registry().get("format_profile:legacy.client_handoff@1")
    incomplete_sections = [
        RenderedSection(
            id="executive_summary",
            title="Executive Summary",
            content="Atlas prepared this package for Legacy.",
        ),
        RenderedSection(
            id="recommendations",
            title="Recommendations",
            content="Recommendation: approve launch.",
        ),
    ]

    result = evaluate_render_quality(
        profile=profile,
        rendered_text="Atlas prepared this package for Legacy.",
        sections=incomplete_sections,
        source_metadata=[{"connector_status": "unverified", "requires_approval": True}],
    )

    failed_checks = {check.id for check in result.checks if check.status == "failed"}
    assert result.status == "blocked"
    assert {
        "required_sections",
        "evidence_recommendation_separation",
        "connector_caveats",
        "approval_language",
    } <= failed_checks
