"""Installable company operating model pack services."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import yaml
from django.db import transaction
from django.db.models import Max

from application.services.audit_log import record_audit_log
from application.services.company_access import ensure_default_company_access_policy
from domain.services.graph_validator import GraphValidator
from infrastructure.orm.models import (
    CompanyOperatingModelInstallation,
    CompanyTeamRole,
    EvaluationProfile,
    Graph,
    GraphTemplate,
    GraphVersion,
    OperatingModelPackRelease,
    PackInstallationConfigRevision,
    PackNamespaceClaim,
    PolicyPack,
    PolicyRule,
    SignalTaxonomy,
    User,
)

PACK_SCHEMA = "operating_model_pack.v1"
PACKS_ROOT = Path(__file__).resolve().parents[3] / "operating_model_packs"
DEFAULT_PROVIDER = "openai"
DEFAULT_MODEL = "gpt-4.1-mini"


class OperatingModelPackError(ValueError):
    """Raised when an operating model pack cannot be loaded, compiled, or installed."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.details = details or []
        super().__init__(message)


@dataclass(frozen=True)
class PackDefinition:
    pack_id: str
    base_pack_id: str
    version: str
    display_name: str
    description: str
    company_type_label: str
    checksum: str
    manifest: dict[str, Any]
    files: dict[str, Any]

    def as_payload(self) -> dict[str, Any]:
        return {
            "pack_id": self.pack_id,
            "base_pack_id": self.base_pack_id,
            "version": self.version,
            "display_name": self.display_name,
            "description": self.description,
            "company_type_label": self.company_type_label,
            "checksum": self.checksum,
            "manifest": copy.deepcopy(self.manifest),
            "files": copy.deepcopy(self.files),
        }


@dataclass(frozen=True)
class PackCompileResult:
    pack: PackDefinition
    graph_json: dict[str, Any]
    departments: list[dict[str, Any]]
    capabilities: list[dict[str, Any]]
    modules: list[dict[str, Any]]
    program_templates: list[dict[str, Any]]
    operation_templates: list[dict[str, Any]]
    artifact_schemas: list[dict[str, Any]]
    evaluation_profiles: list[dict[str, Any]]
    policy_packs: list[dict[str, Any]]
    tool_packages: list[dict[str, Any]]
    department_tools: list[dict[str, Any]]
    dashboard_panels: list[dict[str, Any]]
    warnings: list[dict[str, Any]]

    def as_payload(self) -> dict[str, Any]:
        return {
            "pack": self.pack.as_payload(),
            "graph_json": copy.deepcopy(self.graph_json),
            "departments": copy.deepcopy(self.departments),
            "capabilities": copy.deepcopy(self.capabilities),
            "modules": copy.deepcopy(self.modules),
            "program_templates": copy.deepcopy(self.program_templates),
            "operation_templates": copy.deepcopy(self.operation_templates),
            "artifact_schemas": copy.deepcopy(self.artifact_schemas),
            "evaluation_profiles": copy.deepcopy(self.evaluation_profiles),
            "policy_packs": copy.deepcopy(self.policy_packs),
            "tool_packages": copy.deepcopy(self.tool_packages),
            "department_tools": copy.deepcopy(self.department_tools),
            "dashboard_panels": copy.deepcopy(self.dashboard_panels),
            "warnings": copy.deepcopy(self.warnings),
        }


def list_available_packs() -> list[dict[str, Any]]:
    return [pack.as_payload() for pack in sorted(_load_all_packs(), key=lambda item: item.pack_id)]


def load_pack_definition(pack_id: str) -> PackDefinition:
    normalized = _normalize_pack_id(pack_id)
    for pack_dir in _pack_dirs():
        manifest = _read_yaml(pack_dir / "manifest.yml")
        if str(manifest.get("pack_id") or "") == normalized:
            return _definition_from_manifest(pack_dir=pack_dir, manifest=manifest)
    raise OperatingModelPackError(
        "pack_not_found",
        "Operating model pack was not found.",
        details=[{"pack_id": pack_id}],
    )


def sync_pack_release(pack_id: str) -> OperatingModelPackRelease:
    definition = load_pack_definition(pack_id)
    manifest_checksum = str(definition.manifest.get("checksum") or "").strip().lower()
    if manifest_checksum and manifest_checksum not in {"auto", definition.checksum}:
        raise OperatingModelPackError(
            "checksum_mismatch",
            "Operating model pack checksum does not match its manifest.",
            details=[{"pack_id": pack_id}],
        )
    release, _ = OperatingModelPackRelease.objects.update_or_create(
        pack_id=definition.pack_id,
        defaults={
            "base_pack_id": definition.base_pack_id,
            "version": definition.version,
            "display_name": definition.display_name,
            "description": definition.description,
            "checksum": definition.checksum,
            "manifest_json": definition.manifest,
            "files_json": definition.files,
            "compatibility_json": definition.manifest.get("compatibility")
            if isinstance(definition.manifest.get("compatibility"), dict)
            else {},
            "status": "active",
        },
    )
    return release


def compile_pack(
    *,
    pack_id: str,
    company_name: str = "Company",
    objective: str = "Operate this company using the installed operating model pack.",
    autonomy_mode: str = "assisted",
    ai_access_mode: str = "managed",
    intelligence_provider: str = DEFAULT_PROVIDER,
    selected_services: list[str] | None = None,
    regions: list[str] | None = None,
) -> PackCompileResult:
    definition = load_pack_definition(pack_id)
    departments = _list_from_file(definition, "departments", "departments")
    if not departments:
        departments = [
            {
                "id": "operations",
                "label": "Operations",
                "responsibility": "Plan, execute, review, and improve company work.",
            }
        ]
    capabilities = _list_from_file(definition, "agents", "capabilities")
    graph_json = _build_graph_json(
        definition=definition,
        company_name=_safe_text(company_name, 255) or "Company",
        objective=_safe_text(objective, 2000)
        or "Operate this company using the installed operating model pack.",
        departments=departments,
        capabilities=capabilities,
        autonomy_mode=_safe_text(autonomy_mode, 64) or "assisted",
        ai_access_mode=_safe_text(ai_access_mode, 64) or "managed",
        intelligence_provider=_safe_key(intelligence_provider) or DEFAULT_PROVIDER,
        selected_services=_safe_string_list(selected_services),
        regions=_safe_string_list(regions),
    )
    issues = GraphValidator().validate(graph_json, strict=True, require_entry_exit=True)
    errors = [issue for issue in issues if issue.get("severity") != "warning"]
    if errors:
        raise OperatingModelPackError(
            "invalid_graph_json",
            "Compiled operating model pack produced invalid GraphJson.",
            details=errors,
        )
    return PackCompileResult(
        pack=definition,
        graph_json=graph_json,
        departments=departments,
        capabilities=capabilities,
        modules=_list_from_file(definition, "modules", "modules"),
        program_templates=_list_from_file(definition, "programs", "program_templates"),
        operation_templates=_list_from_file(definition, "operations", "operation_templates"),
        artifact_schemas=_list_from_file(definition, "artifacts", "artifact_schemas"),
        evaluation_profiles=_list_from_file(definition, "evaluations", "profiles"),
        policy_packs=_list_from_file(definition, "policies", "policy_packs"),
        tool_packages=_list_from_file(definition, "tools", "tool_packages"),
        department_tools=_list_from_file(definition, "tools", "department_tools"),
        dashboard_panels=_list_from_file(definition, "dashboards", "panels"),
        warnings=issues,
    )


def install_pack_for_company(
    *,
    company: Graph,
    user: User,
    pack_id: str,
    config: dict[str, Any] | None = None,
    role: str | None = None,
) -> CompanyOperatingModelInstallation:
    if company.organization_id is None:
        raise OperatingModelPackError(
            "company_requires_organization", "Company is not tenant-scoped."
        )
    release = sync_pack_release(pack_id)
    definition = load_pack_definition(pack_id)
    clean_config = {
        key: value for key, value in (config or {}).items() if key != "skip_graph_version"
    }
    compiled = compile_pack(
        pack_id=pack_id,
        company_name=company.name,
        objective=company.description or definition.description,
        selected_services=_safe_string_list(clean_config.get("selected_services")),
        regions=_safe_string_list(clean_config.get("regions")),
    )
    dashboards = definition.files.get("dashboards") if isinstance(definition.files, dict) else {}
    dashboard_json = dashboards if isinstance(dashboards, dict) else {}
    existing_installation = CompanyOperatingModelInstallation.objects.filter(
        company=company,
        pack_id=definition.pack_id,
    ).first()
    next_role = _installation_role(
        company=company,
        requested_role=role or (existing_installation.role if existing_installation else None),
        current_installation=existing_installation,
    )
    namespace = definition.pack_id

    with transaction.atomic():
        ensure_default_company_access_policy(company)
        _assert_primary_role_available(
            company=company,
            pack_id=definition.pack_id,
            role=next_role,
            current_installation=existing_installation,
        )
        installation, _ = CompanyOperatingModelInstallation.objects.update_or_create(
            company=company,
            pack_id=definition.pack_id,
            defaults={
                "organization": company.organization,
                "pack_release": release,
                "base_pack_id": definition.base_pack_id,
                "role": next_role,
                "namespace": namespace,
                "status": "active",
                "installed_by": user,
                "config_json": clean_config,
                "public_config_json": clean_config,
                "private_config_ref": "",
                "dashboard_json": dashboard_json,
                "install_metadata_json": {
                    "checksum": definition.checksum,
                    "company_type_label": definition.company_type_label,
                    "namespace": namespace,
                },
                "active_since": timezone_now(),
                "disabled_at": None,
                "removed_at": None,
                "archived_at": None,
                "last_error": "",
            },
        )
        _create_config_revision(
            installation=installation,
            user=user,
            public_config=clean_config,
            private_config_ref="",
            reason="install",
        )
        _claim_pack_namespace(installation=installation, definition=definition)
        if not bool((config or {}).get("skip_graph_version")):
            _create_graph_version(company=company, graph_json=compiled.graph_json)
        _install_graph_templates(company=company, release=release, definition=definition)
        _install_evaluation_profiles(company=company, release=release, definition=definition)
        _install_periodic_review_definitions(company=company, user=user, definition=definition)
        _install_policy_packs(company=company, release=release, definition=definition)
        _install_signal_taxonomies(company=company, release=release, definition=definition)
        _install_team_roles(company=company, installation=installation, definition=definition)

    record_audit_log(
        actor=user,
        tenant_id=str(company.organization_id),
        action="operating_model_pack.installed",
        resource_type="operating_model_pack",
        resource_id=str(installation.id),
        metadata={"company_id": str(company.id), "pack_id": definition.pack_id},
    )
    return installation


def upgrade_pack_for_company(
    *,
    company: Graph,
    user: User,
    pack_id: str,
    config: dict[str, Any] | None = None,
) -> CompanyOperatingModelInstallation:
    existing = CompanyOperatingModelInstallation.objects.filter(
        company=company,
        pack_id=_normalize_pack_id(pack_id),
    ).first()
    return install_pack_for_company(
        company=company,
        user=user,
        pack_id=pack_id,
        config=config,
        role=existing.role if existing is not None else None,
    )


def upgrade_pack_installation(
    *,
    installation: CompanyOperatingModelInstallation,
    user: User,
    config: dict[str, Any] | None = None,
) -> CompanyOperatingModelInstallation:
    return upgrade_pack_for_company(
        company=installation.company,
        user=user,
        pack_id=installation.pack_id,
        config=config if config is not None else installation.public_config_json,
    )


def remove_pack_from_company(
    *,
    company: Graph,
    user: User,
    pack_id: str,
) -> CompanyOperatingModelInstallation:
    installation = CompanyOperatingModelInstallation.objects.filter(
        company=company,
        pack_id=_normalize_pack_id(pack_id),
    ).first()
    if installation is None:
        raise OperatingModelPackError(
            "installation_not_found", "Pack is not installed for company."
        )
    return archive_pack_installation(installation=installation, user=user, reason="legacy_remove")


def archive_pack_installation(
    *,
    installation: CompanyOperatingModelInstallation,
    user: User,
    reason: str = "",
) -> CompanyOperatingModelInstallation:
    installation.status = "archived"
    installation.removed_at = timezone_now()
    installation.archived_at = installation.removed_at
    metadata = dict(installation.install_metadata_json or {})
    metadata["archive_reason"] = reason
    installation.install_metadata_json = metadata
    installation.save(
        update_fields=[
            "status",
            "removed_at",
            "archived_at",
            "install_metadata_json",
            "updated_at",
        ]
    )
    PackNamespaceClaim.objects.filter(installation=installation, status="active").update(
        status="released",
        updated_at=timezone_now(),
    )
    record_audit_log(
        actor=user,
        tenant_id=str(installation.company.organization_id),
        action="operating_model_pack.archived",
        resource_type="operating_model_pack",
        resource_id=str(installation.id),
        metadata={
            "company_id": str(installation.company_id),
            "pack_id": installation.pack_id,
            "reason": reason,
        },
    )
    return installation


def update_pack_installation(
    *,
    installation: CompanyOperatingModelInstallation,
    user: User,
    role: str | None = None,
    status: str | None = None,
    config: dict[str, Any] | None = None,
) -> CompanyOperatingModelInstallation:
    update_fields: list[str] = ["updated_at"]
    if role is not None:
        next_role = _installation_role(
            company=installation.company,
            requested_role=role,
            current_installation=installation,
        )
        _assert_primary_role_available(
            company=installation.company,
            pack_id=installation.pack_id,
            role=next_role,
            current_installation=installation,
        )
        installation.role = next_role
        update_fields.append("role")
    if status is not None:
        next_status = _normalize_installation_status(status)
        installation.status = next_status
        update_fields.append("status")
        now = timezone_now()
        if next_status == "active":
            installation.active_since = installation.active_since or now
            installation.disabled_at = None
            installation.archived_at = None
            installation.removed_at = None
            update_fields.extend(["active_since", "disabled_at", "archived_at", "removed_at"])
        elif next_status == "disabled":
            installation.disabled_at = now
            update_fields.append("disabled_at")
        elif next_status == "archived":
            installation.archived_at = now
            installation.removed_at = now
            update_fields.extend(["archived_at", "removed_at"])
    if config is not None:
        installation.config_json = config
        installation.public_config_json = config
        update_fields.extend(["config_json", "public_config_json"])
        _create_config_revision(
            installation=installation,
            user=user,
            public_config=config,
            private_config_ref=installation.private_config_ref,
            reason="update",
        )
    installation.save(update_fields=sorted(set(update_fields)))
    if installation.status == "archived":
        PackNamespaceClaim.objects.filter(installation=installation, status="active").update(
            status="released",
            updated_at=timezone_now(),
        )
    return installation


def operating_model_payload(company: Graph) -> dict[str, Any]:
    installations = (
        CompanyOperatingModelInstallation.objects.filter(company=company)
        .exclude(status__in=["archived", "removed"])
        .select_related("pack_release")
    )
    return {
        "company_id": str(company.id),
        "installed_packs": [installation_payload(item) for item in installations],
    }


def installation_payload(installation: CompanyOperatingModelInstallation) -> dict[str, Any]:
    release = installation.pack_release
    config_revision_count = getattr(installation, "config_revision_count", None)
    if config_revision_count is None:
        config_revision_count = installation.config_revisions.count()
    namespace_claim_count = getattr(installation, "namespace_claim_count", None)
    if namespace_claim_count is None:
        namespace_claim_count = installation.namespace_claims.filter(status="active").count()
    return {
        "id": str(installation.id),
        "company_id": str(installation.company_id),
        "pack_id": installation.pack_id,
        "base_pack_id": installation.base_pack_id or release.base_pack_id,
        "role": installation.role,
        "namespace": installation.namespace or installation.pack_id,
        "status": installation.status,
        "display_name": release.display_name,
        "version": release.version,
        "checksum": release.checksum,
        "company_type_label": release.manifest_json.get("company_type_label"),
        "config": copy.deepcopy(installation.config_json),
        "public_config": copy.deepcopy(installation.public_config_json),
        "dashboard": copy.deepcopy(installation.dashboard_json),
        "active_since": installation.active_since.isoformat()
        if installation.active_since
        else None,
        "archived_at": installation.archived_at.isoformat() if installation.archived_at else None,
        "config_revision_count": int(config_revision_count),
        "namespace_claim_count": int(namespace_claim_count),
        "installed_at": installation.installed_at.isoformat(),
        "updated_at": installation.updated_at.isoformat(),
    }


def config_revision_payload(revision: PackInstallationConfigRevision) -> dict[str, Any]:
    return {
        "id": str(revision.id),
        "installation_id": str(revision.installation_id),
        "version": revision.version,
        "public_config": copy.deepcopy(revision.public_config_json),
        "change_reason": revision.change_reason,
        "created_by_id": str(revision.created_by_id) if revision.created_by_id else None,
        "created_at": revision.created_at.isoformat(),
    }


def namespace_claim_payload(claim: PackNamespaceClaim) -> dict[str, Any]:
    return {
        "id": str(claim.id),
        "installation_id": str(claim.installation_id),
        "company_id": str(claim.company_id),
        "pack_id": claim.pack_id,
        "object_type": claim.object_type,
        "object_id": claim.object_id,
        "namespaced_id": claim.namespaced_id,
        "status": claim.status,
        "source_checksum": claim.source_checksum,
    }


def installation_detail_payload(installation: CompanyOperatingModelInstallation) -> dict[str, Any]:
    return {
        **installation_payload(installation),
        "config_revisions": [
            config_revision_payload(item)
            for item in installation.config_revisions.order_by("-version")[:20]
        ],
        "namespace_claims": [
            namespace_claim_payload(item)
            for item in installation.namespace_claims.order_by("object_type", "namespaced_id")
        ],
    }


def timezone_now() -> datetime:
    from django.utils import timezone

    return timezone.now()


def _installation_role(
    *,
    company: Graph,
    requested_role: str | None,
    current_installation: CompanyOperatingModelInstallation | None = None,
) -> str:
    normalized = str(requested_role or "").strip().lower()
    if normalized in {"primary", "addon"}:
        return normalized
    existing_primary = CompanyOperatingModelInstallation.objects.filter(
        company=company,
        role="primary",
        status="active",
    )
    if current_installation is not None:
        existing_primary = existing_primary.exclude(id=current_installation.id)
    return "addon" if existing_primary.exists() else "primary"


def _normalize_installation_status(status: str) -> str:
    normalized = str(status or "").strip().lower()
    if normalized == "removed":
        return "archived"
    valid_statuses = {
        "installing",
        "active",
        "disabled",
        "archived",
        "upgrading",
        "rollback_pending",
        "failed",
        "upgrade_available",
    }
    if normalized not in valid_statuses:
        raise OperatingModelPackError(
            "invalid_installation_status",
            "Pack installation status is not supported.",
            details=[{"status": status}],
        )
    return normalized


def _assert_primary_role_available(
    *,
    company: Graph,
    pack_id: str,
    role: str,
    current_installation: CompanyOperatingModelInstallation | None = None,
) -> None:
    if role != "primary":
        return
    existing = CompanyOperatingModelInstallation.objects.filter(
        company=company,
        role="primary",
        status="active",
    )
    if current_installation is not None:
        existing = existing.exclude(id=current_installation.id)
    conflict = existing.first()
    if conflict is not None:
        raise OperatingModelPackError(
            "primary_pack_conflict",
            "Company already has an active primary pack.",
            details=[
                {
                    "requested_pack_id": pack_id,
                    "active_primary_pack_id": conflict.pack_id,
                    "active_primary_installation_id": str(conflict.id),
                }
            ],
        )


def _create_config_revision(
    *,
    installation: CompanyOperatingModelInstallation,
    user: User,
    public_config: dict[str, Any],
    private_config_ref: str,
    reason: str,
) -> PackInstallationConfigRevision:
    latest_version = (
        PackInstallationConfigRevision.objects.filter(installation=installation)
        .aggregate(Max("version"))
        .get("version__max")
    )
    return PackInstallationConfigRevision.objects.create(
        organization=installation.organization,
        company=installation.company,
        installation=installation,
        version=int(latest_version or 0) + 1,
        public_config_json=copy.deepcopy(public_config),
        private_config_ref=private_config_ref,
        change_reason=reason,
        created_by=user,
    )


def _claim_pack_namespace(
    *,
    installation: CompanyOperatingModelInstallation,
    definition: PackDefinition,
) -> None:
    claims = _pack_namespace_claims(definition)
    seen: set[str] = set()
    duplicate_claims: list[dict[str, str]] = []
    for claim in claims:
        namespaced_id = claim["namespaced_id"]
        _validate_pack_namespace_claim(
            pack_id=definition.pack_id,
            object_id=claim["object_id"],
            namespaced_id=namespaced_id,
        )
        if namespaced_id in seen:
            duplicate_claims.append(claim)
        seen.add(namespaced_id)
    if duplicate_claims:
        raise OperatingModelPackError(
            "pack_namespace_duplicate",
            "Pack defines duplicate namespaced object ids.",
            details=duplicate_claims[:20],
        )

    conflicts = list(
        PackNamespaceClaim.objects.filter(
            company=installation.company,
            namespaced_id__in=seen,
            status="active",
        )
        .exclude(installation=installation)
        .values("namespaced_id", "pack_id", "installation_id")[:20]
    )
    if conflicts:
        raise OperatingModelPackError(
            "pack_namespace_conflict",
            "Pack installation would collide with active pack namespace claims.",
            details=[
                {
                    "namespaced_id": str(item["namespaced_id"]),
                    "pack_id": str(item["pack_id"]),
                    "installation_id": str(item["installation_id"]),
                }
                for item in conflicts
            ],
        )

    PackNamespaceClaim.objects.filter(installation=installation).exclude(
        namespaced_id__in=seen
    ).update(status="released", updated_at=timezone_now())
    for claim in claims:
        PackNamespaceClaim.objects.update_or_create(
            company=installation.company,
            installation=installation,
            namespaced_id=claim["namespaced_id"],
            defaults={
                "organization": installation.organization,
                "pack_id": definition.pack_id,
                "object_type": claim["object_type"],
                "object_id": claim["object_id"],
                "status": "active",
                "source_checksum": definition.checksum,
                "metadata_json": {"source": "operating_model_pack"},
            },
        )


def _validate_pack_namespace_claim(
    *,
    pack_id: str,
    object_id: str,
    namespaced_id: str,
) -> None:
    expected_prefix = f"{pack_id}."
    if not namespaced_id.startswith(expected_prefix):
        raise OperatingModelPackError(
            "invalid_pack_namespace",
            "Pack-defined object namespaced_id must start with the owning pack id plus a dot.",
            details=[
                {
                    "pack_id": pack_id,
                    "object_id": object_id,
                    "namespaced_id": namespaced_id,
                    "expected_prefix": expected_prefix,
                }
            ],
        )


def _pack_namespace_claims(definition: PackDefinition) -> list[dict[str, str]]:
    object_lists = [
        ("department", "departments", "departments"),
        ("capability", "agents", "capabilities"),
        ("module", "modules", "modules"),
        ("program_template", "programs", "program_templates"),
        ("operation_template", "operations", "operation_templates"),
        ("artifact_schema", "artifacts", "artifact_schemas"),
        ("evaluation_profile", "evaluations", "profiles"),
        ("policy_pack", "policies", "policy_packs"),
        ("tool_package", "tools", "tool_packages"),
        ("department_tool", "tools", "department_tools"),
        ("dashboard_panel", "dashboards", "panels"),
        ("service_section", "service_model", "service_sections"),
        ("periodic_review", "reports", "periodic_review_templates"),
        ("report_template", "reports", "report_templates"),
        ("signal_taxonomy", "signals", "taxonomies"),
    ]
    claims: list[dict[str, str]] = []
    for object_type, file_key, list_key in object_lists:
        for item in _list_from_file(definition, file_key, list_key):
            object_id = _safe_key(item.get("id"))
            if not object_id:
                continue
            claims.append(
                {
                    "object_type": object_type,
                    "object_id": object_id,
                    "namespaced_id": _namespaced_object_id(definition.pack_id, object_id),
                }
            )
    return claims


def _namespaced_object_id(pack_id: str, object_id: str) -> str:
    if object_id.startswith(f"{pack_id}."):
        return object_id
    return f"{pack_id}.{object_id}"


def _pack_dirs() -> list[Path]:
    if not PACKS_ROOT.exists():
        return []
    return [item for item in PACKS_ROOT.iterdir() if (item / "manifest.yml").exists()]


def _load_all_packs() -> list[PackDefinition]:
    packs: list[PackDefinition] = []
    for pack_dir in _pack_dirs():
        manifest = _read_yaml(pack_dir / "manifest.yml")
        packs.append(_definition_from_manifest(pack_dir=pack_dir, manifest=manifest))
    return packs


def _definition_from_manifest(*, pack_dir: Path, manifest: dict[str, Any]) -> PackDefinition:
    pack_id = str(manifest.get("pack_id") or "").strip()
    if not pack_id:
        raise OperatingModelPackError("invalid_manifest", "Pack manifest is missing pack_id.")
    files: dict[str, Any] = {}
    file_map = manifest.get("files") if isinstance(manifest.get("files"), dict) else {}
    if not isinstance(file_map, dict):
        file_map = {}
    for key, rel_path in file_map.items():
        if not rel_path:
            continue
        files[str(key)] = _read_yaml(pack_dir / str(rel_path))
    checksum = _pack_checksum(manifest=manifest, files=files)
    return PackDefinition(
        pack_id=pack_id,
        base_pack_id=str(manifest.get("base_pack_id") or pack_id.split(".")[0]),
        version=str(manifest.get("version") or "0.0.0"),
        display_name=str(manifest.get("display_name") or pack_id),
        description=str(manifest.get("description") or ""),
        company_type_label=str(manifest.get("company_type_label") or "Company"),
        checksum=checksum,
        manifest=manifest,
        files=files,
    )


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return cast(dict[str, Any], loaded if isinstance(loaded, dict) else {})


def _pack_checksum(*, manifest: dict[str, Any], files: dict[str, Any]) -> str:
    sanitized_manifest = copy.deepcopy(manifest)
    sanitized_manifest["checksum"] = "auto"
    payload = {"manifest": sanitized_manifest, "files": files}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _list_from_file(
    definition: PackDefinition, file_key: str, list_key: str
) -> list[dict[str, Any]]:
    payload = definition.files.get(file_key) if isinstance(definition.files, dict) else {}
    values = payload.get(list_key) if isinstance(payload, dict) else None
    return [item for item in values if isinstance(item, dict)] if isinstance(values, list) else []


def _build_graph_json(
    *,
    definition: PackDefinition,
    company_name: str,
    objective: str,
    departments: list[dict[str, Any]],
    capabilities: list[dict[str, Any]],
    autonomy_mode: str,
    ai_access_mode: str,
    intelligence_provider: str,
    selected_services: list[str],
    regions: list[str],
) -> dict[str, Any]:
    context_node = {
        "id": "company_context",
        "type": "observation_context",
        "name": "Company Context",
        "config": {
            "query_template": "{{ input.company_name }} current operating context",
            "limit": 5,
        },
    }
    branch_node = {
        "id": "department_fanout",
        "type": "branch",
        "name": "Department Fan-out",
        "config": {"condition": "route_pack_departments"},
    }
    agent_nodes = [
        _department_agent_node(
            department=department,
            capabilities=[
                capability
                for capability in capabilities
                if capability.get("department_id") == department.get("id")
            ],
            provider=intelligence_provider,
            index=index,
        )
        for index, department in enumerate(departments)
    ]
    merge_node = {
        "id": "department_merge",
        "type": "merge",
        "name": "Department Merge",
        "config": {"merge_strategy": "namespaced"},
    }
    approval_node = {
        "id": "approval_gate",
        "type": "human_gate",
        "name": "Approval Gate",
        "config": {
            "prompt_message": "Review the proposed company work before external side effects.",
            "required_fields": ["approved", "notes"],
            "auto_approve": False,
        },
    }
    output_node = {
        "id": "final_deliverable",
        "type": "output",
        "name": "Final Deliverable",
        "config": {
            "output_mapping": {
                "deliverable": "node.department_merge.output",
                "approval": "node.approval_gate.output",
            }
        },
    }
    nodes = [context_node, branch_node, *agent_nodes, merge_node, approval_node, output_node]
    edges = [
        {"id": "start-context", "from": "START", "to": "company_context"},
        {"id": "context-branch", "from": "company_context", "to": "department_fanout"},
    ]
    for node in agent_nodes:
        edges.append({"id": f"branch-{node['id']}", "from": "department_fanout", "to": node["id"]})
        edges.append({"id": f"{node['id']}-merge", "from": node["id"], "to": "department_merge"})
    edges.extend(
        [
            {"id": "merge-approval", "from": "department_merge", "to": "approval_gate"},
            {"id": "approval-output", "from": "approval_gate", "to": "final_deliverable"},
            {"id": "output-end", "from": "final_deliverable", "to": "END"},
        ]
    )
    return {
        "nodes": nodes,
        "edges": edges,
        "metadata": {
            "name": company_name,
            "description": objective,
            "schema": "company_workspace.v1",
            "operating_model_pack": {
                "pack_id": definition.pack_id,
                "display_name": definition.display_name,
                "version": definition.version,
                "checksum": definition.checksum,
            },
            "company_profile": {
                "schema": "company_workspace.v1",
                "companyName": company_name,
                "companyType": definition.company_type_label,
                "objective": objective,
                "autonomyMode": autonomy_mode,
                "aiAccessMode": ai_access_mode,
                "intelligenceProvider": intelligence_provider,
                "selectedServices": selected_services,
                "regions": regions,
                "departments": copy.deepcopy(departments),
                "capabilities": copy.deepcopy(capabilities),
            },
        },
        "editor_state": {
            "viewport": {"x": 0, "y": 0, "zoom": 1},
            "nodePositions": {
                str(node["id"]): {"x": 160 + (index % 4) * 260, "y": 120 + (index // 4) * 180}
                for index, node in enumerate(nodes)
            },
        },
    }


def _department_agent_node(
    *,
    department: dict[str, Any],
    capabilities: list[dict[str, Any]],
    provider: str,
    index: int,
) -> dict[str, Any]:
    label = str(department.get("label") or f"Department {index + 1}")
    capability_labels = [
        str(item.get("label") or item.get("id"))
        for item in capabilities
        if item.get("label") or item.get("id")
    ]
    node_id = f"department_{index + 1}_{_slugify(label)}"
    return {
        "id": node_id,
        "type": "agent",
        "name": label,
        "config": {
            "role": label,
            "job_description": str(department.get("responsibility") or ""),
            "instructions": " ".join(
                [
                    f"Operate as the {label} department.",
                    str(department.get("responsibility") or ""),
                    "Return concrete company work and cite assumptions separately from validated facts.",
                    "Do not perform external side effects; prepare governed proposals for approval.",
                ]
            ),
            "system_prompt": f"You are the {label} department in a ForgeGraph company.",
            "provider": provider,
            "model": DEFAULT_MODEL,
            "temperature": 0.3,
            "tools": capability_labels[:8] or ["Company reasoning"],
            "max_steps": 4,
            "max_tool_calls": 4,
        },
        "retry_policy": {
            "max_attempts": 1,
            "backoff_ms": 0,
            "backoff_strategy": "fixed",
        },
        "timeout_ms": 180_000,
    }


def _create_graph_version(*, company: Graph, graph_json: dict[str, Any]) -> GraphVersion:
    latest_version = GraphVersion.objects.filter(graph=company).aggregate(Max("version"))[
        "version__max"
    ]
    return cast(
        GraphVersion,
        GraphVersion.objects.create(
            graph=company,
            version=int(latest_version or 0) + 1,
            graph_json=graph_json,
        ),
    )


def _install_graph_templates(
    *,
    company: Graph,
    release: OperatingModelPackRelease,
    definition: PackDefinition,
) -> None:
    programs = _list_from_file(definition, "programs", "program_templates")
    for program in programs:
        template_id = str(program.get("id") or "")
        if not template_id:
            continue
        if GraphTemplate.objects.filter(
            owner_organization=company.organization,
            category=definition.pack_id,
            name=str(program.get("display_label") or template_id),
        ).exists():
            continue
        compiled = compile_pack(
            pack_id=definition.pack_id,
            company_name=company.name,
            objective=company.description or definition.description,
        )
        GraphTemplate.objects.create(
            name=str(program.get("display_label") or template_id),
            description=str(program.get("objective_template") or definition.description),
            category=definition.pack_id,
            tags=[template_id, definition.pack_id, release.pack_id],
            graph_json=compiled.graph_json,
            sample_input={"company_id": str(company.id), "template_id": template_id},
            guide_steps=definition.files.get("stages", {}).get("stages", [])
            if isinstance(definition.files.get("stages"), dict)
            else [],
            visibility="organization",
            owner_organization=company.organization,
        )


def _install_evaluation_profiles(
    *,
    company: Graph,
    release: OperatingModelPackRelease,
    definition: PackDefinition,
) -> None:
    for profile in _list_from_file(definition, "evaluations", "profiles"):
        profile_id = str(profile.get("id") or "")
        if not profile_id:
            continue
        default_thresholds = (
            definition.files.get("evaluations", {}).get("thresholds", {})
            if isinstance(definition.files.get("evaluations"), dict)
            else {}
        )
        EvaluationProfile.objects.update_or_create(
            company=company,
            profile_id=profile_id,
            defaults={
                "organization": company.organization,
                "pack_release": release,
                "display_name": str(profile.get("label") or profile_id),
                "mode": str(profile.get("mode") or ""),
                "rubric_json": profile.get("rubric")
                if isinstance(profile.get("rubric"), dict)
                else {},
                "weights_json": profile.get("weights")
                if isinstance(profile.get("weights"), dict)
                else {},
                "thresholds_json": profile.get("thresholds")
                if isinstance(profile.get("thresholds"), dict)
                else default_thresholds,
                "status": "active",
            },
        )


def _install_periodic_review_definitions(
    *,
    company: Graph,
    user: User,
    definition: PackDefinition,
) -> None:
    reports = definition.files.get("reports") if isinstance(definition.files, dict) else {}
    if not isinstance(reports, dict):
        return
    templates = reports.get("periodic_review_templates")
    if not isinstance(templates, list):
        return
    report_templates = {
        str(item.get("id") or ""): item
        for item in reports.get("report_templates", [])
        if isinstance(item, dict) and item.get("id")
    }
    from application.services.periodic_reviews import upsert_review_definition_from_template

    for template in templates:
        if not isinstance(template, dict):
            continue
        report_template_id = str(template.get("report_template_id") or "")
        enriched = {
            **template,
            "report_template": report_templates.get(report_template_id, {}),
        }
        upsert_review_definition_from_template(
            company=company,
            user=user,
            pack_id=definition.pack_id,
            template=enriched,
        )


def _install_policy_packs(
    *,
    company: Graph,
    release: OperatingModelPackRelease,
    definition: PackDefinition,
) -> None:
    for pack in _list_from_file(definition, "policies", "policy_packs"):
        policy_pack_id = str(pack.get("id") or "")
        if not policy_pack_id:
            continue
        policy_pack, _ = PolicyPack.objects.update_or_create(
            company=company,
            policy_pack_id=policy_pack_id,
            defaults={
                "organization": company.organization,
                "pack_release": release,
                "display_name": str(pack.get("label") or policy_pack_id),
                "rules_json": pack.get("rules") if isinstance(pack.get("rules"), list) else [],
                "status": "active",
            },
        )
        for rule in policy_pack.rules_json if isinstance(policy_pack.rules_json, list) else []:
            if not isinstance(rule, dict):
                continue
            action_type = str(rule.get("action_type") or "")
            if not action_type:
                continue
            PolicyRule.objects.update_or_create(
                company=company,
                scope_type="operation_type",
                scope_id=action_type,
                title=str(rule.get("id") or f"{policy_pack_id}:{action_type}")[:255],
                defaults={
                    "organization": company.organization,
                    "condition_json": rule,
                    "recommendation_json": {
                        "policy_pack_id": policy_pack_id,
                        "approval_required_at": rule.get("approval_required_at"),
                    },
                    "confidence": 1.0,
                    "status": "active",
                },
            )


def _install_signal_taxonomies(
    *,
    company: Graph,
    release: OperatingModelPackRelease,
    definition: PackDefinition,
) -> None:
    for taxonomy in _list_from_file(definition, "signals", "taxonomies"):
        taxonomy_id = str(taxonomy.get("id") or "")
        if not taxonomy_id:
            continue
        SignalTaxonomy.objects.update_or_create(
            company=company,
            taxonomy_id=taxonomy_id,
            defaults={
                "organization": company.organization,
                "pack_release": release,
                "display_name": str(taxonomy.get("label") or taxonomy_id),
                "definitions_json": taxonomy.get("signals")
                if isinstance(taxonomy.get("signals"), list)
                else [],
                "status": "active",
            },
        )


def _install_team_roles(
    *,
    company: Graph,
    installation: CompanyOperatingModelInstallation,
    definition: PackDefinition,
) -> None:
    role_defaults = [
        ("brand_manager", "Brand Manager", "HIGH", 15),
        ("strategist", "Strategist", "MEDIUM", 15),
        ("researcher", "Researcher", "LOW", 18),
        ("content_lead", "Content Lead", "MEDIUM", 20),
        ("copywriter", "Copywriter", "LOW", 20),
        ("media_buyer", "Media Buyer", "MEDIUM", 15),
        ("crm_specialist", "CRM Specialist", "MEDIUM", 18),
        ("analyst", "Analyst", "LOW", 15),
        ("qa_compliance", "QA Compliance", "HIGH", 12),
        ("approver", "Approver", "HIGH", 10),
        ("client_stakeholder", "Client Stakeholder", "MEDIUM", 8),
    ]
    for role_key, label, approval_level, capacity in role_defaults:
        CompanyTeamRole.objects.update_or_create(
            company=company,
            role_key=role_key,
            defaults={
                "organization": company.organization,
                "installation": installation,
                "display_label": label,
                "permissions_json": [],
                "approval_level": approval_level,
                "capacity_per_week": capacity,
                "metadata_json": {"source_pack_id": definition.pack_id},
            },
        )


def _normalize_pack_id(value: str) -> str:
    return str(value or "").strip()


def _safe_text(value: Any, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _safe_key(value: Any) -> str:
    return re.sub(r"[^a-zA-Z0-9_.:-]+", "_", str(value or "").strip().lower()).strip("_")


def _safe_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned: list[str] = []
    for item in value:
        text = _safe_text(item, 120)
        if text:
            cleaned.append(text)
    return cleaned[:50]


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")
    return slug or "item"
