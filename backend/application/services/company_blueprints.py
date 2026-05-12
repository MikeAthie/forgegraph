"""Company blueprint compatibility services backed by operating model packs."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import Any, cast

from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from application.services.llm_access import (
    LLMAccessConfig,
    attach_llm_access_to_graph,
    resolve_llm_access_for_dispatch,
    validate_llm_access_config,
)
from application.services.operating_model_packs import (
    OperatingModelPackError,
    compile_pack,
    install_pack_for_company,
)
from application.services.run_queue import enqueue_run
from application.services.run_state_machine import create_backend_owned_run
from application.services.task_lifecycle import initialize_lifecycle_tasks_for_run
from application.services.tenancy import ensure_default_organization
from domain.services.graph_validator import GraphValidator
from infrastructure.orm.models import Graph, GraphVersion, MemoryConfiguration, Run, User

DEFAULT_BLUEPRINT_ID = "digital_marketing_pro.v1"
DEFAULT_PROVIDER = "openai"

_BLUEPRINT_ALIASES = {
    "digital_marketing_pro.v1": DEFAULT_BLUEPRINT_ID,
    "digital_marketing_pro": DEFAULT_BLUEPRINT_ID,
    "digital-marketing-pro": DEFAULT_BLUEPRINT_ID,
    "dmp": DEFAULT_BLUEPRINT_ID,
    "growth_marketing": DEFAULT_BLUEPRINT_ID,
    "growth-marketing": DEFAULT_BLUEPRINT_ID,
    "growth marketing": DEFAULT_BLUEPRINT_ID,
}

_MEMORY_CONFIG_COPY_FIELDS = [
    "buffer_enabled",
    "buffer_size",
    "auto_prepend",
    "redis_enabled",
    "redis_summary_ttl",
    "redis_facts_ttl",
    "vector_enabled",
    "vector_top_k",
    "vector_threshold",
    "vector_recency_weight",
    "embedding_model",
    "summarization_enabled",
    "summarization_threshold",
    "summarization_keep_recent",
    "summarization_model",
]


@dataclass(frozen=True)
class CompanyBlueprintCompileResult:
    graph_json: dict[str, Any]
    template_ids: list[str]
    department_groups: list[dict[str, Any]]
    warnings: list[dict[str, Any]]

    def as_payload(self) -> dict[str, Any]:
        return {
            "graph_json": copy.deepcopy(self.graph_json),
            "template_ids": list(self.template_ids),
            "department_groups": copy.deepcopy(self.department_groups),
            "warnings": copy.deepcopy(self.warnings),
        }


@dataclass(frozen=True)
class CompanyFromBlueprintResult:
    company_id: str
    graph_version_id: str
    graph_json: dict[str, Any]
    template_ids: list[str]
    department_groups: list[dict[str, Any]]
    first_operation_id: str | None
    idempotent_replay: bool = False

    def as_payload(self) -> dict[str, Any]:
        return {
            "company_id": self.company_id,
            "graph_version_id": self.graph_version_id,
            "graph_json": copy.deepcopy(self.graph_json),
            "template_ids": list(self.template_ids),
            "department_groups": copy.deepcopy(self.department_groups),
            "first_operation_id": self.first_operation_id,
            "idempotent_replay": self.idempotent_replay,
        }


class CompanyBlueprintError(ValueError):
    """Raised when a company blueprint cannot be compiled or created."""

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


class CompanyBlueprintCompiler:
    """Compile company blueprint requests through installable operating model packs."""

    def compile(
        self,
        *,
        company_name: str,
        objective: str,
        blueprint_id: str = DEFAULT_BLUEPRINT_ID,
        services: list[str] | None = None,
        regions: list[str] | None = None,
        autonomy_mode: str = "assisted",
        ai_access_mode: str = "managed",
        intelligence_provider: str | None = None,
        credential_id: str | None = None,
    ) -> CompanyBlueprintCompileResult:
        del credential_id
        clean_objective = _safe_text(objective, limit=2000)
        if not clean_objective:
            raise CompanyBlueprintError(
                "objective_required",
                "A company objective is required to compile a blueprint.",
                details=[{"field": "objective"}],
            )
        pack_id = _normalize_blueprint_id(blueprint_id)
        try:
            compiled = compile_pack(
                pack_id=pack_id,
                company_name=_safe_text(company_name, limit=255) or "Untitled Company",
                objective=clean_objective,
                autonomy_mode=autonomy_mode,
                ai_access_mode=ai_access_mode,
                intelligence_provider=intelligence_provider or DEFAULT_PROVIDER,
                selected_services=_safe_string_list(services),
                regions=_safe_string_list(regions),
            )
        except OperatingModelPackError as exc:
            raise CompanyBlueprintError(exc.code, exc.message, details=exc.details) from exc

        validation_issues = GraphValidator().validate(
            compiled.graph_json,
            strict=True,
            require_entry_exit=True,
        )
        validation_errors = [
            issue for issue in validation_issues if issue.get("severity") != "warning"
        ]
        if validation_errors:
            raise CompanyBlueprintError(
                "invalid_graph_json",
                "Compiled company blueprint produced invalid GraphJson.",
                details=validation_errors,
            )
        return CompanyBlueprintCompileResult(
            graph_json=compiled.graph_json,
            template_ids=_template_ids(
                pack_id=pack_id, program_templates=compiled.program_templates
            ),
            department_groups=_department_groups(compiled.departments),
            warnings=[*compiled.warnings, *validation_issues],
        )


def create_company_from_blueprint(
    *,
    user: User,
    company_name: str,
    objective: str,
    blueprint_id: str = DEFAULT_BLUEPRINT_ID,
    services: list[str] | None = None,
    regions: list[str] | None = None,
    autonomy_mode: str = "assisted",
    ai_access_mode: str = "managed",
    intelligence_provider: str | None = None,
    launch_first_operation: bool = False,
    operation_brief: str | None = None,
    credential_id: str | None = None,
    compiler: CompanyBlueprintCompiler | None = None,
) -> CompanyFromBlueprintResult:
    """Persist a company from a pack-backed blueprint through backend-owned state paths."""

    membership = ensure_default_organization(user)
    organization = membership.organization
    compiler = compiler or CompanyBlueprintCompiler()
    pack_id = _normalize_blueprint_id(blueprint_id)
    compiled = compiler.compile(
        company_name=company_name,
        objective=objective,
        blueprint_id=pack_id,
        services=services,
        regions=regions,
        autonomy_mode=autonomy_mode,
        ai_access_mode=ai_access_mode,
        intelligence_provider=intelligence_provider,
        credential_id=credential_id,
    )

    llm_access = validate_llm_access_config(
        LLMAccessConfig(
            llm_mode=ai_access_mode,
            provider=intelligence_provider or DEFAULT_PROVIDER,
            credential_id=str(credential_id or ""),
        )
    )
    if llm_access.is_byok:
        resolve_llm_access_for_dispatch(llm_access, user)

    graph_json = attach_llm_access_to_graph(compiled.graph_json, llm_access)
    first_operation: Run | None = None

    with transaction.atomic():
        company = Graph.objects.create(
            owner=user,
            organization=organization,
            name=_safe_text(company_name, limit=255) or "Untitled Company",
            description=_safe_text(objective, limit=2000),
            external_source="operating_model_pack",
            external_ref="",
        )
        _create_graph_memory_config(company, user)
        version = GraphVersion.objects.create(graph=company, version=1, graph_json=graph_json)
        install_pack_for_company(
            company=company,
            user=user,
            pack_id=pack_id,
            config={
                "skip_graph_version": True,
                "selected_services": _safe_string_list(services),
                "regions": _safe_string_list(regions),
            },
        )
        version = _latest_graph_version(company) or version
        if launch_first_operation:
            first_operation = _create_first_operation(
                company=company,
                version=version,
                user=user,
                graph_json=version.graph_json,
                operation_brief=operation_brief,
            )

    return CompanyFromBlueprintResult(
        company_id=str(company.id),
        graph_version_id=str(version.id),
        graph_json=version.graph_json,
        template_ids=compiled.template_ids,
        department_groups=compiled.department_groups,
        first_operation_id=str(first_operation.id) if first_operation is not None else None,
        idempotent_replay=False,
    )


def _create_first_operation(
    *,
    company: Graph,
    version: GraphVersion,
    user: User,
    graph_json: dict[str, Any],
    operation_brief: str | None,
) -> Run:
    metadata_raw = graph_json.get("metadata")
    metadata: dict[str, Any] = metadata_raw if isinstance(metadata_raw, dict) else {}
    profile_raw = metadata.get("company_profile")
    profile: dict[str, Any] = profile_raw if isinstance(profile_raw, dict) else {}
    pack_raw = metadata.get("operating_model_pack")
    pack: dict[str, Any] = pack_raw if isinstance(pack_raw, dict) else {}
    departments_raw = profile.get("departments")
    departments = departments_raw if isinstance(departments_raw, list) else []
    brief = _safe_text(operation_brief, limit=2000) or str(
        profile.get("objective") or company.description
    )
    input_json = {
        "company_name": company.name,
        "company_type": profile.get("companyType") or "Company",
        "objective": profile.get("objective") or company.description,
        "autonomy_mode": profile.get("autonomyMode") or "assisted",
        "ai_access_mode": profile.get("aiAccessMode") or "managed",
        "operation_type": "first_company_operation",
        "operation_brief": brief,
        "departments": [
            str(department.get("label"))
            for department in departments
            if isinstance(department, dict) and department.get("label")
        ],
        "operating_model_pack": pack,
    }
    dispatch_graph_json = copy.deepcopy(graph_json)
    dispatch_metadata = dict(dispatch_graph_json.get("metadata") or {})
    dispatch_metadata["company_blueprint_operation"] = {
        "operation_type": "first_company_operation",
        "created_by": "backend",
    }
    dispatch_graph_json["metadata"] = dispatch_metadata
    run = create_backend_owned_run(
        owner=user,
        organization=cast(Any, company.organization),
        graph_version=version,
        status="pending",
        started_at=timezone.now(),
        input_json=input_json,
        dispatch_graph_json=dispatch_graph_json,
        output_json=None,
        error_message="",
    )
    queue_enabled = bool(getattr(settings, "RUN_QUEUE_ENABLED", False))
    initialize_lifecycle_tasks_for_run(
        run,
        source="company_blueprint",
        initial_status="queued" if queue_enabled else "created",
        reason="company blueprint first operation created",
    )
    if queue_enabled:
        enqueue_run(run, tenant_id=str(company.organization_id))
    return run


def _create_graph_memory_config(graph: Graph, user: User) -> None:
    default_config = MemoryConfiguration.objects.filter(user=user).first()
    if default_config is None:
        MemoryConfiguration.objects.create(graph=graph)
        return
    defaults = {
        field_name: getattr(default_config, field_name)
        for field_name in _MEMORY_CONFIG_COPY_FIELDS
        if hasattr(default_config, field_name)
    }
    MemoryConfiguration.objects.create(graph=graph, **defaults)


def _latest_graph_version(company: Graph) -> GraphVersion | None:
    latest = GraphVersion.objects.filter(graph=company).aggregate(Max("version"))["version__max"]
    if latest is None:
        return None
    return cast(
        GraphVersion | None, GraphVersion.objects.filter(graph=company, version=latest).first()
    )


def _normalize_blueprint_id(value: str) -> str:
    normalized = re.sub(r"\s+", " ", str(value or DEFAULT_BLUEPRINT_ID).strip().lower())
    return _BLUEPRINT_ALIASES.get(normalized, normalized)


def _template_ids(*, pack_id: str, program_templates: list[dict[str, Any]]) -> list[str]:
    return [
        f"operating_model_pack:{pack_id}",
        *[
            f"program_template:{template.get('id')}"
            for template in program_templates
            if template.get("id")
        ],
    ]


def _department_groups(departments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": "installed-pack-departments",
            "label": "Installed Pack Departments",
            "department_ids": [
                str(department.get("id"))
                for department in departments
                if isinstance(department, dict) and department.get("id")
            ],
        }
    ]


def _safe_text(value: Any, *, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _safe_string_list(value: list[str] | None) -> list[str]:
    cleaned: list[str] = []
    for item in value or []:
        text = _safe_text(item, limit=120)
        if text:
            cleaned.append(text)
    return cleaned[:50]
