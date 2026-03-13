from __future__ import annotations

import copy
import hashlib
import json
from typing import Any
from uuid import UUID

from django.utils import timezone

from infrastructure.orm.models import NodePackageInstallation, NodeRegistryRelease

MANIFEST_SCHEMA_VERSION = 1
RUNTIME_MODE_CLOUD = "cloud"
RUNTIME_MODE_SELF_HOSTED = "self_hosted"


def normalize_runtime_mode(runtime_mode: str | None) -> str:
    normalized = str(runtime_mode or "").strip().lower()
    if normalized == RUNTIME_MODE_SELF_HOSTED:
        return RUNTIME_MODE_SELF_HOSTED
    return RUNTIME_MODE_CLOUD


def _normalize_checksum_payload(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _checksum(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_normalize_checksum_payload(payload)).hexdigest()


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

    manifest_kind = str(manifest.get("kind") or "").strip().lower()
    if (
        package_kind == "runtime_tool"
        and manifest_kind == "exec"
        and runtime_mode == RUNTIME_MODE_CLOUD
    ):
        return {
            "state": "blocked",
            "reason": "exec_not_supported_in_cloud",
            "package_kind": package_kind,
            "cloud_allowed": True,
            "manifest_version": release.manifest_version,
            "checksum": _checksum(manifest),
        }

    if (
        package_kind == "runtime_tool"
        and manifest_kind != "http"
        and not (runtime_mode == RUNTIME_MODE_SELF_HOSTED and manifest_kind == "exec")
    ):
        return {
            "state": "invalid",
            "reason": "unsupported_runtime_tool_kind",
            "package_kind": package_kind,
            "cloud_allowed": True,
            "manifest_version": release.manifest_version,
            "checksum": _checksum(manifest),
        }

    return {
        "state": "ready",
        "reason": "ready",
        "package_kind": package_kind,
        "cloud_allowed": bool(release.cloud_allowed),
        "manifest_version": release.manifest_version,
        "checksum": _checksum(manifest),
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

        if delivery["state"] != "ready":
            continue
        if release.package_kind != "runtime_tool":
            continue
        if not isinstance(release.runtime_manifest, dict):
            continue

        tool_def = copy.deepcopy(release.runtime_manifest)
        tool_def.setdefault("version", release.version)
        tool_def.setdefault("description", install.package.summary)
        tool_def.setdefault("config_schema", copy.deepcopy(release.config_schema))
        tool_def.setdefault("default_config", copy.deepcopy(release.config_defaults))
        tools.append(tool_def)

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
