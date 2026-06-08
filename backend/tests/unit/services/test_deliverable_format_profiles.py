from __future__ import annotations

from types import SimpleNamespace

import pytest

from application.services.deliverable_format_profiles import (
    DEFAULT_FORMAT_PROFILE_REF,
    FormatProfile,
    FormatProfileError,
    load_format_profile_registry,
    parse_profile_ref,
    profile_ref_for,
)


def test_registry_loads_versioned_hashable_profiles_from_config() -> None:
    registry = load_format_profile_registry()

    legacy = registry.get("format_profile:legacy.client_handoff@1")
    consulting = registry.get("format_profile:consulting.standard_handoff@1")
    default = registry.get(DEFAULT_FORMAT_PROFILE_REF)

    assert legacy.profile_ref == "format_profile:legacy.client_handoff@1"
    assert legacy.profile_sha256 == registry.get(legacy.profile_ref).profile_sha256
    assert legacy.formats == ("markdown_report", "pdf_report", "manifest", "zip_package")
    assert [section.id for section in legacy.required_sections] == [
        "executive_summary",
        "evidence",
        "recommendations",
    ]
    assert consulting.renderer_policy_key == legacy.renderer_policy_key
    assert default.profile_id == "default"
    assert len({legacy.profile_sha256, consulting.profile_sha256, default.profile_sha256}) == 3


def test_profile_ref_parsing_is_strict_and_round_trippable() -> None:
    assert parse_profile_ref("format_profile:legacy.client_handoff@1") == (
        "legacy.client_handoff",
        1,
    )
    assert profile_ref_for("consulting.standard_handoff", 1) == (
        "format_profile:consulting.standard_handoff@1"
    )

    with pytest.raises(FormatProfileError) as exc_info:
        parse_profile_ref("legacy.client_handoff@1")

    assert exc_info.value.code == "invalid_profile_ref"


def test_profile_validation_rejects_unsafe_or_ambiguous_configs() -> None:
    valid = {
        "profile_id": "safe.profile",
        "version": 1,
        "display_name": "Safe Profile",
        "formats": ["markdown_report", "manifest"],
        "voice": {
            "audience": "operator",
            "tone": "plain",
            "forbidden_phrases": ["as an AI"],
            "naming": {"client_display_name": "Client", "provider_display_name": "Provider"},
        },
        "sections": [
            {"id": "executive_summary", "title": "Executive Summary", "required": True},
            {"id": "evidence", "title": "Evidence", "required": True},
        ],
        "quality_gates": ["client_handoff@1"],
        "connector_policy": {},
        "layout": {},
    }

    with pytest.raises(FormatProfileError) as unsafe_exc:
        FormatProfile.from_dict({**valid, "profile_id": "../unsafe"})
    assert unsafe_exc.value.code == "invalid_profile_id"

    pdf_profile = FormatProfile.from_dict({**valid, "formats": ["markdown_report", "pdf_report"]})
    assert pdf_profile.formats == ("markdown_report", "pdf_report")

    with pytest.raises(FormatProfileError) as renderer_exc:
        FormatProfile.from_dict({**valid, "formats": ["markdown_report", "email_handoff"]})
    assert renderer_exc.value.code == "unsupported_format"

    duplicate_sections = {
        **valid,
        "sections": [
            {"id": "evidence", "title": "Evidence", "required": True},
            {"id": "evidence", "title": "Duplicate Evidence", "required": False},
        ],
    }
    with pytest.raises(FormatProfileError) as duplicate_exc:
        FormatProfile.from_dict(duplicate_sections)
    assert duplicate_exc.value.code == "duplicate_section_id"


def test_registry_resolution_precedence_is_backend_metadata_then_default() -> None:
    registry = load_format_profile_registry()
    program = SimpleNamespace(
        metadata_json={
            "formatting": {"profile_ref": "format_profile:legacy.client_handoff@1"}
        }
    )
    engagement = SimpleNamespace(
        metadata_json={
            "formatting": {"profile_ref": "format_profile:consulting.standard_handoff@1"}
        }
    )

    explicit = registry.resolve(
        profile_ref="format_profile:default@1",
        engagement=engagement,
        program=program,
    )
    assert explicit.profile_ref == "format_profile:default@1"

    engagement_selected = registry.resolve(engagement=engagement, program=program)
    assert engagement_selected.profile_ref == "format_profile:consulting.standard_handoff@1"

    program_selected = registry.resolve(program=program)
    assert program_selected.profile_ref == "format_profile:legacy.client_handoff@1"

    assert registry.resolve().profile_ref == DEFAULT_FORMAT_PROFILE_REF
