"""Versioned formatting profile schema and registry."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_FORMAT_PROFILE_REF = "format_profile:default@1"
SUPPORTED_FORMATS = frozenset({"markdown_report", "pdf_report", "manifest", "zip_package"})

_PROFILE_REF_RE = re.compile(r"^format_profile:([a-z][a-z0-9_.-]*[a-z0-9])@([1-9][0-9]*)$")
_PROFILE_ID_RE = re.compile(r"^[a-z][a-z0-9_.-]*[a-z0-9]$")
_SECTION_ID_RE = re.compile(r"^[a-z][a-z0-9_]*[a-z0-9]$")


class FormatProfileError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class FormatProfileSection:
    id: str
    title: str
    required: bool = False
    source_roles: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> FormatProfileSection:
        section_id = str(value.get("id") or "").strip()
        if not _SECTION_ID_RE.match(section_id):
            raise FormatProfileError("invalid_section_id", "Profile section id is invalid.")
        title = _clean_text(value.get("title"))
        if not title:
            raise FormatProfileError("missing_section_title", "Profile section title is required.")
        source_roles = _tuple_of_clean_strings(value.get("source_roles"))
        return cls(
            id=section_id,
            title=title,
            required=value.get("required") is True,
            source_roles=source_roles,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "required": self.required,
            "source_roles": list(self.source_roles),
        }


@dataclass(frozen=True)
class FormatProfile:
    profile_id: str
    version: int
    display_name: str
    formats: tuple[str, ...]
    voice: dict[str, Any]
    sections: tuple[FormatProfileSection, ...]
    quality_gates: tuple[str, ...]
    connector_policy: dict[str, Any]
    layout: dict[str, Any]
    business_domain: str = ""

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> FormatProfile:
        profile_id = _clean_text(value.get("profile_id"))
        if ".." in profile_id or not _PROFILE_ID_RE.match(profile_id):
            raise FormatProfileError("invalid_profile_id", "Profile id is invalid.")

        version = value.get("version")
        if not isinstance(version, int) or version < 1:
            raise FormatProfileError("invalid_profile_version", "Profile version is invalid.")

        display_name = _clean_text(value.get("display_name"))
        if not display_name:
            raise FormatProfileError("missing_display_name", "Profile display name is required.")

        formats = _validated_formats(value.get("formats"))
        sections = _validated_sections(value.get("sections"))

        voice = _dict_or_empty(value.get("voice"))
        connector_policy = _dict_or_empty(value.get("connector_policy"))
        layout = _dict_or_empty(value.get("layout"))
        quality_gates = _tuple_of_clean_strings(value.get("quality_gates"))

        return cls(
            profile_id=profile_id,
            version=version,
            display_name=display_name,
            formats=formats,
            voice=_canonical_data(voice),
            sections=sections,
            quality_gates=quality_gates,
            connector_policy=_canonical_data(connector_policy),
            layout=_canonical_data(layout),
            business_domain=_clean_text(value.get("business_domain")),
        )

    @property
    def profile_ref(self) -> str:
        return profile_ref_for(self.profile_id, self.version)

    @property
    def profile_sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self.as_dict()).encode("utf-8")).hexdigest()

    @property
    def renderer_policy_key(self) -> str:
        return "generic_format_renderers.v1"

    @property
    def required_sections(self) -> tuple[FormatProfileSection, ...]:
        return tuple(section for section in self.sections if section.required)

    @property
    def forbidden_phrases(self) -> tuple[str, ...]:
        return _tuple_of_clean_strings(self.voice.get("forbidden_phrases"))

    @property
    def naming(self) -> dict[str, str]:
        raw = self.voice.get("naming")
        if not isinstance(raw, dict):
            return {}
        return {str(key): str(value) for key, value in raw.items() if str(value).strip()}

    def section_by_id(self, section_id: str) -> FormatProfileSection:
        for section in self.sections:
            if section.id == section_id:
                return section
        raise FormatProfileError("section_not_found", f"Profile section not found: {section_id}")

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "version": self.version,
            "display_name": self.display_name,
            "business_domain": self.business_domain,
            "formats": list(self.formats),
            "voice": _canonical_data(self.voice),
            "sections": [section.as_dict() for section in self.sections],
            "quality_gates": list(self.quality_gates),
            "connector_policy": _canonical_data(self.connector_policy),
            "layout": _canonical_data(self.layout),
        }


class FormatProfileRegistry:
    def __init__(
        self,
        profiles: list[FormatProfile],
        *,
        default_profile_ref: str = DEFAULT_FORMAT_PROFILE_REF,
    ) -> None:
        self.default_profile_ref = default_profile_ref
        self._profiles_by_ref: dict[str, FormatProfile] = {}
        for profile in profiles:
            if profile.profile_ref in self._profiles_by_ref:
                raise FormatProfileError(
                    "duplicate_profile_ref",
                    f"Duplicate profile ref: {profile.profile_ref}",
                )
            self._profiles_by_ref[profile.profile_ref] = profile
        if default_profile_ref not in self._profiles_by_ref:
            raise FormatProfileError(
                "missing_default_profile",
                f"Default profile not loaded: {default_profile_ref}",
            )

    @classmethod
    def from_directory(cls, config_dir: Path) -> FormatProfileRegistry:
        if not config_dir.exists():
            raise FormatProfileError(
                "profile_config_missing",
                f"Format profile directory does not exist: {config_dir}",
            )
        profiles: list[FormatProfile] = []
        for path in sorted(config_dir.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise FormatProfileError(
                    "invalid_profile_json",
                    f"Profile JSON is invalid: {path.name}",
                ) from exc
            if not isinstance(payload, dict):
                raise FormatProfileError(
                    "invalid_profile_config",
                    f"Profile config must be an object: {path.name}",
                )
            profiles.append(FormatProfile.from_dict(payload))
        return cls(profiles)

    def get(self, profile_ref: str) -> FormatProfile:
        parse_profile_ref(profile_ref)
        profile = self._profiles_by_ref.get(profile_ref)
        if profile is None:
            raise FormatProfileError("profile_not_found", f"Format profile not found: {profile_ref}")
        return profile

    def resolve(
        self,
        *,
        profile_ref: str | None = None,
        engagement: Any | None = None,
        program: Any | None = None,
        company: Any | None = None,
    ) -> FormatProfile:
        for candidate in (
            profile_ref,
            _profile_ref_from_metadata_owner(engagement),
            _profile_ref_from_metadata_owner(program),
            _profile_ref_from_metadata_owner(company),
            self.default_profile_ref,
        ):
            if candidate:
                return self.get(candidate)
        return self.get(self.default_profile_ref)


def load_format_profile_registry(config_dir: Path | None = None) -> FormatProfileRegistry:
    path = config_dir or Path(__file__).resolve().parents[2] / "config" / "format_profiles"
    return FormatProfileRegistry.from_directory(path)


def profile_ref_for(profile_id: str, version: int) -> str:
    if ".." in profile_id or not _PROFILE_ID_RE.match(profile_id):
        raise FormatProfileError("invalid_profile_id", "Profile id is invalid.")
    if version < 1:
        raise FormatProfileError("invalid_profile_version", "Profile version is invalid.")
    return f"format_profile:{profile_id}@{version}"


def parse_profile_ref(profile_ref: str) -> tuple[str, int]:
    match = _PROFILE_REF_RE.match(str(profile_ref or "").strip())
    if not match:
        raise FormatProfileError("invalid_profile_ref", "Profile ref must be format_profile:<id>@<version>.")
    return match.group(1), int(match.group(2))


def _profile_ref_from_metadata_owner(owner: Any | None) -> str:
    if owner is None:
        return ""
    metadata = getattr(owner, "metadata_json", None)
    if not isinstance(metadata, dict):
        metadata = getattr(owner, "metadata", None)
    if not isinstance(metadata, dict):
        return ""
    formatting = metadata.get("formatting")
    if not isinstance(formatting, dict):
        return ""
    return _clean_text(formatting.get("profile_ref"))


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _tuple_of_clean_strings(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def _validated_formats(value: Any) -> tuple[str, ...]:
    formats = _tuple_of_clean_strings(value)
    if not formats:
        raise FormatProfileError("missing_formats", "At least one format is required.")
    for renderer_id in formats:
        if renderer_id not in SUPPORTED_FORMATS:
            raise FormatProfileError(
                "unsupported_format",
                f"Format renderer is not supported: {renderer_id}",
            )
    return formats


def _validated_sections(value: Any) -> tuple[FormatProfileSection, ...]:
    sections = tuple(FormatProfileSection.from_dict(item) for item in _list_of_dicts(value))
    if not sections:
        raise FormatProfileError("missing_sections", "At least one section is required.")
    seen_section_ids: set[str] = set()
    for section in sections:
        if section.id in seen_section_ids:
            raise FormatProfileError(
                "duplicate_section_id",
                f"Duplicate section id: {section.id}",
            )
        seen_section_ids.add(section.id)
    if not any(section.required for section in sections):
        raise FormatProfileError("missing_required_sections", "At least one section is required.")
    return sections


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _canonical_data(value: Any) -> Any:
    return json.loads(_canonical_json(value))
