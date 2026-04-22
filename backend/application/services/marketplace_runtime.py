from __future__ import annotations

import copy
import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable
from typing import Any
from uuid import UUID

from django.utils import timezone

from infrastructure.orm.models import NodePackageInstallation, NodeRegistryRelease

MANIFEST_SCHEMA_VERSION = 2
RUNTIME_MODE_CLOUD = "cloud"
RUNTIME_MODE_SELF_HOSTED = "self_hosted"
TOOL_VISIBILITY_PUBLIC = "public"
TOOL_VISIBILITY_INTERNAL = "internal"
SIDE_EFFECT_TYPES = {"read", "write", "external"}
LEGACY_HTTP_METHOD_READS = {"GET", "HEAD", "OPTIONS"}


def normalize_runtime_mode(runtime_mode: str | None) -> str:
    normalized = str(runtime_mode or "").strip().lower()
    if normalized == RUNTIME_MODE_SELF_HOSTED:
        return RUNTIME_MODE_SELF_HOSTED
    return RUNTIME_MODE_CLOUD


def _normalize_checksum_payload(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _checksum(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_normalize_checksum_payload(payload)).hexdigest()


def _normalize_tool_visibility(raw_value: Any) -> str:
    normalized = str(raw_value or "").strip().lower()
    if normalized == TOOL_VISIBILITY_INTERNAL:
        return TOOL_VISIBILITY_INTERNAL
    return TOOL_VISIBILITY_PUBLIC


def _coerce_positive_int(raw_value: Any, default: int = 0) -> int:
    try:
        parsed = int(raw_value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _normalize_timeout_seconds(
    *,
    timeout_seconds: Any = None,
    timeout_ms: Any = None,
    default: int = 30,
) -> int:
    seconds = _coerce_positive_int(timeout_seconds)
    if seconds > 0:
        return seconds
    millis = _coerce_positive_int(timeout_ms)
    if millis > 0:
        return max(1, millis // 1000 if millis % 1000 == 0 else (millis // 1000) + 1)
    return default


def _normalize_tool_definition(definition: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(definition)
    normalized["definition_checksum"] = _checksum(
        {key: value for key, value in normalized.items() if key != "definition_checksum"}
    )
    return normalized


def _build_v2_http_definition(
    *,
    release: NodeRegistryRelease,
    runtime_manifest: dict[str, Any],
    category: str,
    description: str,
    visibility: str,
    input_schema: dict[str, Any],
    output_schema: dict[str, Any] | None,
    config_schema: dict[str, Any],
    default_config: dict[str, Any],
) -> dict[str, Any] | None:
    execution = runtime_manifest.get("execution")
    if not isinstance(execution, dict):
        return None
    http_config = execution.get("http")
    if not isinstance(http_config, dict):
        return None

    url = str(http_config.get("url") or "").strip()
    if not url:
        return None

    method = str(http_config.get("method") or "POST").strip().upper() or "POST"
    timeout_seconds = _normalize_timeout_seconds(
        timeout_seconds=execution.get("timeout_seconds"),
        timeout_ms=http_config.get("timeout_ms"),
    )
    headers = http_config.get("headers")

    side_effects = runtime_manifest.get("side_effects")
    if not isinstance(side_effects, dict):
        return None

    side_effect_type = str(side_effects.get("type") or "").strip().lower()
    if side_effect_type not in SIDE_EFFECT_TYPES:
        return None

    definition = {
        "name": str(runtime_manifest.get("name") or "").strip(),
        "version": str(runtime_manifest.get("version") or release.version).strip(),
        "category": category,
        "description": description,
        "visibility": visibility,
        "input_schema": input_schema,
        "output_schema": output_schema,
        "config_schema": config_schema,
        "default_config": default_config,
        "execution": {
            "type": "http",
            "timeout_seconds": timeout_seconds,
            "http": {
                "url": url,
                "method": method,
                "headers": headers if isinstance(headers, dict) else {},
            },
        },
        "side_effects": {
            "type": side_effect_type,
            "idempotent": bool(side_effects.get("idempotent")),
        },
        "max_result_size_chars": (
            int(runtime_manifest["max_result_size_chars"])
            if isinstance(runtime_manifest.get("max_result_size_chars"), int)
            else None
        ),
        "agent_hints": (
            runtime_manifest.get("agent_hints")
            if isinstance(runtime_manifest.get("agent_hints"), dict)
            else {}
        ),
    }
    return _normalize_tool_definition(definition)


def _build_v2_local_definition(
    *,
    release: NodeRegistryRelease,
    runtime_manifest: dict[str, Any],
    category: str,
    description: str,
    visibility: str,
    input_schema: dict[str, Any],
    output_schema: dict[str, Any] | None,
    config_schema: dict[str, Any],
    default_config: dict[str, Any],
) -> dict[str, Any] | None:
    execution = runtime_manifest.get("execution")
    if not isinstance(execution, dict):
        return None
    local_config = execution.get("local")
    if not isinstance(local_config, dict):
        return None
    handler = str(local_config.get("handler") or "").strip()
    if not handler:
        return None

    side_effects = runtime_manifest.get("side_effects")
    if not isinstance(side_effects, dict):
        return None
    side_effect_type = str(side_effects.get("type") or "").strip().lower()
    if side_effect_type not in SIDE_EFFECT_TYPES:
        return None

    definition = {
        "name": str(runtime_manifest.get("name") or "").strip(),
        "version": str(runtime_manifest.get("version") or release.version).strip(),
        "category": category,
        "description": description,
        "visibility": visibility,
        "input_schema": input_schema,
        "output_schema": output_schema,
        "config_schema": config_schema,
        "default_config": default_config,
        "execution": {
            "type": "local",
            "timeout_seconds": _normalize_timeout_seconds(
                timeout_seconds=execution.get("timeout_seconds"),
            ),
            "local": {
                "handler": handler,
            },
        },
        "side_effects": {
            "type": side_effect_type,
            "idempotent": bool(side_effects.get("idempotent")),
        },
        "max_result_size_chars": (
            int(runtime_manifest["max_result_size_chars"])
            if isinstance(runtime_manifest.get("max_result_size_chars"), int)
            else None
        ),
        "agent_hints": (
            runtime_manifest.get("agent_hints")
            if isinstance(runtime_manifest.get("agent_hints"), dict)
            else {}
        ),
    }
    return _normalize_tool_definition(definition)


def _normalize_v2_runtime_tool_manifest(
    release: NodeRegistryRelease,
) -> tuple[dict[str, Any] | None, str]:
    runtime_manifest = (
        release.runtime_manifest if isinstance(release.runtime_manifest, dict) else None
    )
    if runtime_manifest is None:
        return None, "missing_runtime_manifest"

    name = str(runtime_manifest.get("name") or "").strip()
    version = str(runtime_manifest.get("version") or release.version).strip()
    category = str(runtime_manifest.get("category") or release.package.category or "other").strip()
    description = str(runtime_manifest.get("description") or release.package.summary or "").strip()
    visibility = _normalize_tool_visibility(runtime_manifest.get("visibility"))

    if not name:
        return None, "missing_name"
    if not version:
        return None, "missing_version"
    if not category:
        return None, "missing_category"

    input_schema = runtime_manifest.get("input_schema")
    if not isinstance(input_schema, dict):
        return None, "missing_input_schema"

    output_schema = runtime_manifest.get("output_schema")
    if output_schema is not None and not isinstance(output_schema, dict):
        return None, "invalid_output_schema"

    config_schema = release.config_schema if isinstance(release.config_schema, dict) else {}
    default_config = release.config_defaults if isinstance(release.config_defaults, dict) else {}

    execution = runtime_manifest.get("execution")
    if not isinstance(execution, dict):
        return None, "missing_execution"

    execution_type = str(execution.get("type") or "").strip().lower()
    if execution_type == "http":
        definition = _build_v2_http_definition(
            release=release,
            runtime_manifest=runtime_manifest,
            category=category,
            description=description,
            visibility=visibility,
            input_schema=input_schema,
            output_schema=output_schema,
            config_schema=config_schema,
            default_config=default_config,
        )
        if definition is None:
            return None, "invalid_http_execution"
        return definition, "ready"
    if execution_type == "local":
        definition = _build_v2_local_definition(
            release=release,
            runtime_manifest=runtime_manifest,
            category=category,
            description=description,
            visibility=visibility,
            input_schema=input_schema,
            output_schema=output_schema,
            config_schema=config_schema,
            default_config=default_config,
        )
        if definition is None:
            return None, "invalid_local_execution"
        return definition, "ready"

    return None, "unsupported_execution_type"


def _translate_legacy_v1_runtime_tool_manifest(
    release: NodeRegistryRelease,
) -> tuple[dict[str, Any] | None, str]:
    runtime_manifest = (
        release.runtime_manifest if isinstance(release.runtime_manifest, dict) else None
    )
    if runtime_manifest is None:
        return None, "missing_runtime_manifest"

    kind = str(runtime_manifest.get("kind") or "").strip().lower()
    if kind == "exec":
        return None, "legacy_exec_not_supported"
    if kind != "http":
        return None, "unsupported_runtime_tool_kind"

    http_config = runtime_manifest.get("http")
    if not isinstance(http_config, dict):
        return None, "invalid_http_execution"
    url = str(http_config.get("url") or "").strip()
    if not url:
        return None, "invalid_http_execution"

    method = str(http_config.get("method") or "POST").strip().upper() or "POST"
    input_schema = runtime_manifest.get("input_schema")
    if not isinstance(input_schema, dict):
        return None, "missing_input_schema"
    output_schema = runtime_manifest.get("output_schema")
    if output_schema is not None and not isinstance(output_schema, dict):
        return None, "invalid_output_schema"

    side_effect_type = "read" if method in LEGACY_HTTP_METHOD_READS else "external"
    idempotent = method in LEGACY_HTTP_METHOD_READS

    definition = {
        "name": str(runtime_manifest.get("name") or "").strip(),
        "version": str(runtime_manifest.get("version") or release.version).strip(),
        "category": str(release.package.category or "other").strip() or "other",
        "description": str(
            runtime_manifest.get("description") or release.package.summary or ""
        ).strip(),
        "visibility": TOOL_VISIBILITY_PUBLIC,
        "input_schema": input_schema,
        "output_schema": output_schema,
        "config_schema": release.config_schema if isinstance(release.config_schema, dict) else {},
        "default_config": (
            release.config_defaults if isinstance(release.config_defaults, dict) else {}
        ),
        "execution": {
            "type": "http",
            "timeout_seconds": _normalize_timeout_seconds(timeout_ms=http_config.get("timeout_ms")),
            "http": {
                "url": url,
                "method": method,
                "headers": (
                    http_config.get("headers")
                    if isinstance(http_config.get("headers"), dict)
                    else {}
                ),
            },
        },
        "side_effects": {
            "type": side_effect_type,
            "idempotent": idempotent,
        },
        "max_result_size_chars": (
            int(runtime_manifest["max_result_size_chars"])
            if isinstance(runtime_manifest.get("max_result_size_chars"), int)
            else None
        ),
        "agent_hints": {},
    }
    return _normalize_tool_definition(definition), "translated_legacy_http_v1"


def normalize_runtime_tool_manifest(
    release: NodeRegistryRelease,
) -> tuple[dict[str, Any] | None, str]:
    manifest_version = int(release.manifest_version or 1)
    if manifest_version >= MANIFEST_SCHEMA_VERSION:
        return _normalize_v2_runtime_tool_manifest(release)
    return _translate_legacy_v1_runtime_tool_manifest(release)


def build_runtime_delivery_state(
    release: NodeRegistryRelease,
    runtime_mode: str = RUNTIME_MODE_CLOUD,
) -> dict[str, Any]:
    runtime_mode = normalize_runtime_mode(runtime_mode)
    package_kind = str(release.package_kind or "")
    manifest = release.runtime_manifest if isinstance(release.runtime_manifest, dict) else None

    if package_kind.startswith("template_"):
        return {
            "state": "template",
            "reason": "template_only",
            "package_kind": package_kind,
            "cloud_allowed": bool(release.cloud_allowed),
            "manifest_version": release.manifest_version,
            "checksum": None,
        }

    if manifest is None:
        return {
            "state": "invalid",
            "reason": "missing_runtime_manifest",
            "package_kind": package_kind,
            "cloud_allowed": bool(release.cloud_allowed),
            "manifest_version": release.manifest_version,
            "checksum": None,
        }

    if runtime_mode == RUNTIME_MODE_CLOUD and not release.cloud_allowed:
        return {
            "state": "blocked",
            "reason": "cloud_not_allowed",
            "package_kind": package_kind,
            "cloud_allowed": False,
            "manifest_version": release.manifest_version,
            "checksum": _checksum(manifest),
        }

    if package_kind == "runtime_transform":
        return {
            "state": "blocked",
            "reason": "runtime_transform_not_supported",
            "package_kind": package_kind,
            "cloud_allowed": bool(release.cloud_allowed),
            "manifest_version": release.manifest_version,
            "checksum": _checksum(manifest),
        }

    normalized_manifest, reason = normalize_runtime_tool_manifest(release)
    if normalized_manifest is None:
        state = "invalid"
        if runtime_mode == RUNTIME_MODE_CLOUD and reason == "legacy_exec_not_supported":
            state = "blocked"
            reason = "exec_not_supported_in_cloud"
        return {
            "state": state,
            "reason": reason,
            "package_kind": package_kind,
            "cloud_allowed": bool(release.cloud_allowed),
            "manifest_version": release.manifest_version,
            "checksum": _checksum(manifest),
        }

    return {
        "state": "ready",
        "reason": "ready",
        "package_kind": package_kind,
        "cloud_allowed": bool(release.cloud_allowed),
        "manifest_version": release.manifest_version,
        "checksum": normalized_manifest["definition_checksum"],
    }


def build_install_metadata(
    release: NodeRegistryRelease,
    runtime_mode: str = RUNTIME_MODE_CLOUD,
) -> dict[str, Any]:
    runtime_mode = normalize_runtime_mode(runtime_mode)
    runtime_delivery = build_runtime_delivery_state(release, runtime_mode)
    return {
        "source": "marketplace",
        "runtime_mode": runtime_mode,
        "package_kind": release.package_kind,
        "runtime_delivery": runtime_delivery,
    }


def is_release_installable_in_runtime_mode(
    release: NodeRegistryRelease,
    runtime_mode: str = RUNTIME_MODE_CLOUD,
) -> tuple[bool, dict[str, Any]]:
    delivery = build_runtime_delivery_state(release, runtime_mode)
    return delivery["state"] in {"ready", "template"}, delivery


def build_runtime_manifest_payload(
    tenant_id: str | UUID,
    runtime_mode: str = RUNTIME_MODE_CLOUD,
) -> dict[str, Any]:
    runtime_mode = normalize_runtime_mode(runtime_mode)
    tenant_str = str(tenant_id)
    installs = (
        NodePackageInstallation.objects.filter(organization_id=tenant_str, is_active=True)
        .select_related("package", "release")
        .order_by("package__slug", "-installed_at")
    )

    tools: list[dict[str, Any]] = []
    packages: list[dict[str, Any]] = []
    seen_package_slugs: set[str] = set()

    for install in installs:
        release = install.release
        delivery = build_runtime_delivery_state(release, runtime_mode)
        package_slug = str(install.package.slug)
        packages.append(
            {
                "package_slug": package_slug,
                "package_name": install.package.name,
                "release_id": str(release.id),
                "release_version": release.version,
                "package_kind": release.package_kind,
                "delivery_state": delivery["state"],
                "delivery_reason": delivery["reason"],
                "cloud_allowed": delivery["cloud_allowed"],
                "manifest_version": delivery["manifest_version"],
                "manifest_checksum": delivery["checksum"],
            }
        )

        if package_slug in seen_package_slugs:
            continue
        seen_package_slugs.add(package_slug)

        if delivery["state"] != "ready" or release.package_kind != "runtime_tool":
            continue

        normalized_tool, _ = normalize_runtime_tool_manifest(release)
        if normalized_tool is None:
            continue
        tools.append(normalized_tool)

    tools.sort(key=lambda item: (str(item.get("name") or ""), str(item.get("version") or "")))
    packages.sort(key=lambda item: (str(item["package_slug"]), str(item["release_version"])))

    canonical_payload = {
        "tenant_id": tenant_str,
        "manifest_version": MANIFEST_SCHEMA_VERSION,
        "tools": tools,
        "packages": packages,
    }
    checksum = _checksum(canonical_payload)
    generated_at = timezone.now().isoformat()

    return {
        **canonical_payload,
        "checksum": checksum,
        "generated_at": generated_at,
    }


def list_ready_runtime_tools(
    tenant_id: str | UUID,
    runtime_mode: str = RUNTIME_MODE_CLOUD,
) -> list[dict[str, Any]]:
    payload = build_runtime_manifest_payload(tenant_id, runtime_mode)
    tools = payload.get("tools")
    if not isinstance(tools, list):
        return []
    return [tool for tool in tools if isinstance(tool, dict)]


def _index_tools_by_name(
    tools: Iterable[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    indexed: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for tool in tools:
        name = str(tool.get("name") or "").strip()
        if not name:
            continue
        indexed[name].append(tool)
    for versions in indexed.values():
        versions.sort(
            key=lambda item: (str(item.get("name") or ""), str(item.get("version") or ""))
        )
    return indexed


def select_agent_runtime_tools(
    *,
    available_tools: list[dict[str, Any]],
    explicit_tool_names: list[str],
    tool_selection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    indexed = _index_tools_by_name(available_tools)
    selected_defs: list[dict[str, Any]] = []
    selected_names: list[str] = []
    unresolved_explicit_tools: list[str] = []
    seen_names: set[str] = set()

    def _append_tool(name: str, definition: dict[str, Any] | None) -> None:
        if name in seen_names:
            return
        seen_names.add(name)
        selected_names.append(name)
        if definition is not None:
            selected_defs.append(definition)

    for tool_name in explicit_tool_names:
        versions = indexed.get(tool_name)
        if not versions:
            unresolved_explicit_tools.append(tool_name)
            _append_tool(tool_name, None)
            continue
        _append_tool(tool_name, versions[-1])

    selection = tool_selection if isinstance(tool_selection, dict) else {}
    allowed_categories = {
        str(value).strip()
        for value in (selection.get("categories") or [])
        if isinstance(value, str) and value.strip()
    }
    include_names = {
        str(value).strip()
        for value in (selection.get("names") or [])
        if isinstance(value, str) and value.strip()
    }
    exclude_names = {
        str(value).strip()
        for value in (selection.get("exclude_names") or [])
        if isinstance(value, str) and value.strip()
    }
    max_tools = _coerce_positive_int(selection.get("max_tools"))

    candidates = [
        tool
        for tool in available_tools
        if _normalize_tool_visibility(tool.get("visibility")) != TOOL_VISIBILITY_INTERNAL
    ]
    if include_names:
        candidates = [tool for tool in candidates if str(tool.get("name") or "") in include_names]
    if allowed_categories:
        candidates = [
            tool for tool in candidates if str(tool.get("category") or "") in allowed_categories
        ]
    if exclude_names:
        candidates = [
            tool for tool in candidates if str(tool.get("name") or "") not in exclude_names
        ]

    candidates.sort(key=lambda item: (str(item.get("name") or ""), str(item.get("version") or "")))
    for candidate in candidates:
        candidate_name = str(candidate.get("name") or "").strip()
        if not candidate_name:
            continue
        _append_tool(candidate_name, candidate)
        if max_tools > 0 and len(selected_names) >= max_tools:
            break

    return {
        "tool_names": selected_names,
        "tool_definitions": selected_defs,
        "tool_versions": {
            str(definition.get("name")): str(definition.get("version"))
            for definition in selected_defs
            if definition.get("name") and definition.get("version")
        },
        "unresolved_explicit_tools": unresolved_explicit_tools,
    }
