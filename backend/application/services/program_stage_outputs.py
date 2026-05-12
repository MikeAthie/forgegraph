"""Pack-driven output generation for generic company program stages."""

from __future__ import annotations

import re
from typing import Any

from django.db import transaction
from django.utils import timezone

from application.services.audit_log import record_audit_log
from application.services.company_ops import create_company_signal
from application.services.evaluations import evaluation_payload, run_evaluation
from application.services.operating_model_packs import load_pack_definition
from application.services.state_projections import (
    materialize_current_truth_projection,
    materialize_service_history_projection,
    projection_payload,
)
from application.services.work_artifacts import (
    artifact_payload,
    canonical_version,
    create_work_artifact,
)
from infrastructure.orm.models import (
    AssertionRecord,
    Asset,
    AssetDependency,
    CompanyOperatingModelInstallation,
    CompanyProgram,
    CompanySignal,
    Graph,
    ProgramStageState,
    StateProjection,
    User,
)


class ProgramStageOutputError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def execute_stage_output_generation(
    *,
    program: CompanyProgram,
    user: User,
    stage_id: str,
    workflow_id: str = "",
    artifact_schema_ids: list[str] | None = None,
    selected_family_ids: list[str] | None = None,
    source_artifact_ids: list[str] | None = None,
    notes: str = "",
    evaluation_inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create generic artifacts/signals from pack-defined stage metadata."""

    stage = ProgramStageState.objects.filter(program=program, stage_id=stage_id).first()
    if stage is None:
        raise ProgramStageOutputError("stage_not_found", "Program stage was not found.")
    definition = load_pack_definition(program.pack_id) if program.pack_id else None
    files = definition.files if definition else {}
    template = _stage_template(stage=stage, files=files)
    clean_workflow_id = _safe_key(workflow_id) or f"{stage.stage_id}.outputs"
    source_assets = _source_assets(program=program, source_artifact_ids=source_artifact_ids or [])
    selected_schemas, skipped = _selected_schema_ids(
        program=program,
        template=template,
        requested_schema_ids=artifact_schema_ids or [],
        selected_family_ids=selected_family_ids or [],
    )
    blockers = _prerequisite_blockers(
        program=program,
        template=template,
        source_assets=source_assets,
        selected_schema_ids=selected_schemas,
    )
    if blockers:
        _mark_stage_blocked(stage=stage, blockers=blockers, workflow_id=clean_workflow_id)
        projection = _materialize_projection(program=program, definition_files=files)
        _audit(
            user=user,
            program=program,
            stage=stage,
            action="company_program.stage_outputs_blocked",
            metadata={"workflow_id": clean_workflow_id, "blockers": blockers},
        )
        return _payload(
            stage=stage,
            workflow_id=clean_workflow_id,
            artifacts=[],
            evaluations=[],
            signals=[],
            blockers=blockers,
            skipped=skipped,
            projection=projection,
        )

    artifacts: list[Asset] = []
    evaluations: list[dict[str, Any]] = []
    signals: list[CompanySignal] = []
    generated_at = timezone.now().isoformat()
    install_config = _install_config(program)
    source_assets = source_assets or _default_source_assets(program=program, template=template)

    with transaction.atomic():
        for schema_id in selected_schemas:
            asset, _version = create_work_artifact(
                company=program.company,
                program=program,
                user=user,
                title=_artifact_title(schema_id=schema_id, stage=stage),
                artifact_type=schema_id,
                content=_artifact_content(
                    schema_id=schema_id,
                    program=program,
                    stage=stage,
                    source_assets=source_assets,
                    install_config=install_config,
                    generated_at=generated_at,
                    notes=notes,
                ),
                metadata={
                    "stage_id": stage.stage_id,
                    "workflow_id": clean_workflow_id,
                    "source": "program_stage_output",
                    "generated_at": generated_at,
                },
                source_key=(
                    f"program-stage-output:{program.id}:{stage.stage_id}:"
                    f"{clean_workflow_id}:{schema_id}"
                ),
            )
            artifacts.append(asset)
            _link_sources(
                company=program.company,
                target_asset=asset,
                source_assets=source_assets,
                workflow_id=clean_workflow_id,
            )
            for profile_id in _evaluation_profile_ids(template):
                evaluation = run_evaluation(
                    company=program.company,
                    user=user,
                    profile_id=profile_id,
                    asset=asset,
                    program=program,
                    input_refs=[
                        {"type": "program_stage", "id": stage.stage_id},
                        {"type": "artifact_schema", "id": schema_id},
                    ],
                )
                evaluations.append(evaluation_payload(evaluation))

        if _safe_key(str(template.get("signal_taxonomy_id") or "")):
            signals = _create_stage_signals(
                program=program,
                user=user,
                stage=stage,
                template=template,
                workflow_id=clean_workflow_id,
            )

        scorecard_profile_id = _safe_key(str(template.get("scorecard_profile_id") or ""))
        if scorecard_profile_id:
            evaluation = run_evaluation(
                company=program.company,
                user=user,
                profile_id=scorecard_profile_id,
                program=program,
                input_refs=[
                    {"type": "program_stage", "id": stage.stage_id},
                    {"type": "workflow", "id": clean_workflow_id},
                ],
                inputs=evaluation_inputs or {},
            )
            evaluations.append(evaluation_payload(evaluation))

        _mark_stage_ready(
            stage=stage,
            workflow_id=clean_workflow_id,
            artifacts=artifacts,
            signals=signals,
            skipped=skipped,
        )

    projection = _materialize_projection(program=program, definition_files=files)
    if _safe_key(str(template.get("service_history_projection_type") or "")):
        materialize_service_history_projection(
            company=program.company,
            program=program,
            projection_type=str(template.get("service_history_projection_type")),
            display_label=str(
                template.get("service_history_projection_label") or "Service History"
            ),
        )
    _audit(
        user=user,
        program=program,
        stage=stage,
        action="company_program.stage_outputs_generated",
        metadata={
            "workflow_id": clean_workflow_id,
            "artifact_ids": [str(item.id) for item in artifacts],
            "signal_ids": [str(item.id) for item in signals],
        },
    )
    return _payload(
        stage=stage,
        workflow_id=clean_workflow_id,
        artifacts=artifacts,
        evaluations=evaluations,
        signals=signals,
        blockers=[],
        skipped=skipped,
        projection=projection,
    )


def _stage_template(*, stage: ProgramStageState, files: dict[str, Any]) -> dict[str, Any]:
    state = stage.state_json if isinstance(stage.state_json, dict) else {}
    template = state.get("template")
    if isinstance(template, dict):
        return template
    stages_file = files.get("stages") if isinstance(files, dict) else {}
    stages = stages_file.get("stages") if isinstance(stages_file, dict) else []
    if isinstance(stages, list):
        for item in stages:
            if isinstance(item, dict) and item.get("id") == stage.stage_id:
                return item
    return {}


def _selected_schema_ids(
    *,
    program: CompanyProgram,
    template: dict[str, Any],
    requested_schema_ids: list[str],
    selected_family_ids: list[str],
) -> tuple[list[str], list[dict[str, Any]]]:
    requested = [_safe_key(item) for item in requested_schema_ids if _safe_key(item)]
    if requested:
        return _dedupe(requested), []
    families = template.get("channel_families")
    if isinstance(families, list):
        selected = _selected_families(
            program=program,
            families=[item for item in families if isinstance(item, dict)],
            selected_family_ids=selected_family_ids,
        )
        schemas: list[str] = []
        skipped: list[dict[str, Any]] = []
        selected_ids = {str(item.get("id") or "") for item in selected}
        for family in families:
            family_id = str(family.get("id") or "")
            family_schemas = _string_list(family.get("artifact_schema_ids"))
            if family_id in selected_ids:
                schemas.extend(family_schemas)
            else:
                skipped.append(
                    {
                        "family_id": family_id,
                        "label": str(family.get("label") or family_id),
                        "reason": "not_selected",
                    }
                )
        return _dedupe(schemas), skipped
    return _dedupe(_string_list(template.get("expected_artifact_schema_ids"))), []


def _selected_families(
    *,
    program: CompanyProgram,
    families: list[dict[str, Any]],
    selected_family_ids: list[str],
) -> list[dict[str, Any]]:
    clean_requested = {_safe_key(item) for item in selected_family_ids if _safe_key(item)}
    if clean_requested:
        return [family for family in families if _safe_key(family.get("id")) in clean_requested]
    selected_services = [
        item.lower() for item in _install_config(program).get("selected_services", [])
    ]
    selected: list[dict[str, Any]] = []
    for family in families:
        keywords = [item.lower() for item in _string_list(family.get("service_keywords"))]
        if any(
            keyword and keyword in service for keyword in keywords for service in selected_services
        ):
            selected.append(family)
    return selected


def _prerequisite_blockers(
    *,
    program: CompanyProgram,
    template: dict[str, Any],
    source_assets: list[Asset],
    selected_schema_ids: list[str],
) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    if not selected_schema_ids:
        blockers.append(
            {
                "code": "no_outputs_selected",
                "message": "No output schemas were selected for this stage.",
            }
        )
    required = _string_list(template.get("required_source_artifact_schema_ids"))
    if not required:
        return blockers
    available = {
        str((asset.metadata_json or {}).get("artifact_type") or asset.asset_type)
        for asset in (source_assets or _default_source_assets(program=program, template=template))
    }
    missing = [schema_id for schema_id in required if schema_id not in available]
    mode = str(template.get("source_requirement_mode") or "all").lower()
    if mode == "any":
        if not any(schema_id in available for schema_id in required):
            blockers.append(
                {
                    "code": "missing_source_artifact",
                    "message": "At least one prerequisite artifact is required.",
                    "missing_artifact_schema_ids": missing,
                }
            )
        return blockers
    if missing:
        blockers.append(
            {
                "code": "missing_source_artifact",
                "message": "One or more prerequisite artifacts are missing.",
                "missing_artifact_schema_ids": missing,
            }
        )
    return blockers


def _source_assets(*, program: CompanyProgram, source_artifact_ids: list[str]) -> list[Asset]:
    clean_ids = [item for item in source_artifact_ids if str(item).strip()]
    if not clean_ids:
        return []
    return list(
        Asset.objects.filter(
            company=program.company,
            id__in=clean_ids,
            metadata_json__program_id=str(program.id),
        )
    )


def _default_source_assets(*, program: CompanyProgram, template: dict[str, Any]) -> list[Asset]:
    required = _string_list(template.get("required_source_artifact_schema_ids"))
    queryset = Asset.objects.filter(
        company=program.company, metadata_json__program_id=str(program.id)
    )
    if required:
        queryset = queryset.filter(metadata_json__artifact_type__in=required)
    return list(queryset.order_by("-updated_at")[:40])


def _link_sources(
    *,
    company: Graph,
    target_asset: Asset,
    source_assets: list[Asset],
    workflow_id: str,
) -> None:
    target_version = canonical_version(target_asset)
    for source_asset in source_assets:
        source_version = canonical_version(source_asset)
        if source_asset.id == target_asset.id:
            continue
        AssetDependency.objects.get_or_create(
            organization=company.organization,
            company=company,
            source_asset=source_asset,
            source_asset_version=source_version,
            target_asset=target_asset,
            target_asset_version=target_version,
            dependency_type="informs",
            defaults={
                "reason": "Pack-defined stage output used this source artifact.",
                "metadata_json": {"workflow_id": workflow_id},
            },
        )


def _create_stage_signals(
    *,
    program: CompanyProgram,
    user: User,
    stage: ProgramStageState,
    template: dict[str, Any],
    workflow_id: str,
) -> list[CompanySignal]:
    recommended = _string_list(template.get("recommended_operation_template_ids"))
    signal_defs = [
        ("performance_insight", "Performance insight ready for review."),
        ("operating_signal_summary", "Operating signal summary was generated."),
        ("next_operation_recommendation", "Next operation recommendations were produced."),
    ]
    signals: list[CompanySignal] = []
    for signal_key, summary in signal_defs:
        external_key = (
            f"program-stage-signal:{program.id}:{stage.stage_id}:{workflow_id}:{signal_key}"
        )
        signals.append(
            create_company_signal(
                company=program.company,
                actor=user,
                signal_type="manual",
                title=_label_from_id(signal_key),
                summary=summary,
                source="program_stage_output",
                external_key=external_key,
                metadata={
                    "program_id": str(program.id),
                    "stage_id": stage.stage_id,
                    "pack_id": program.pack_id,
                    "taxonomy_id": str(template.get("signal_taxonomy_id") or ""),
                    "taxonomy_signal_id": signal_key,
                    "recommended_operation_template_ids": recommended,
                },
            )
        )
    return signals


def _mark_stage_blocked(
    *,
    stage: ProgramStageState,
    blockers: list[dict[str, Any]],
    workflow_id: str,
) -> None:
    state = stage.state_json if isinstance(stage.state_json, dict) else {}
    state["blockers"] = blockers
    state["last_output_generation"] = {
        "workflow_id": workflow_id,
        "status": "blocked",
        "generated_at": timezone.now().isoformat(),
    }
    stage.status = "blocked"
    stage.state_json = state
    stage.save(update_fields=["status", "state_json", "updated_at"])


def _mark_stage_ready(
    *,
    stage: ProgramStageState,
    workflow_id: str,
    artifacts: list[Asset],
    signals: list[CompanySignal],
    skipped: list[dict[str, Any]],
) -> None:
    state = stage.state_json if isinstance(stage.state_json, dict) else {}
    state.pop("blockers", None)
    state["last_output_generation"] = {
        "workflow_id": workflow_id,
        "status": "generated",
        "generated_at": timezone.now().isoformat(),
        "artifact_ids": [str(item.id) for item in artifacts],
        "signal_ids": [str(item.id) for item in signals],
        "skipped": skipped,
    }
    stage.status = "awaiting_validation"
    stage.state_json = state
    stage.save(update_fields=["status", "state_json", "updated_at"])


def _materialize_projection(
    *,
    program: CompanyProgram,
    definition_files: dict[str, Any],
) -> StateProjection:
    del definition_files
    installation = program.installation
    if installation is None and program.pack_id:
        installation = (
            CompanyOperatingModelInstallation.objects.select_related("pack_release")
            .filter(
                company=program.company,
                pack_id=program.pack_id,
                status="active",
            )
            .first()
        )
    manifest = (
        installation.pack_release.manifest_json
        if installation
        and installation.pack_release
        and isinstance(installation.pack_release.manifest_json, dict)
        else {}
    )
    install = manifest.get("install") if isinstance(manifest, dict) else {}
    return materialize_current_truth_projection(
        company=program.company,
        program=program,
        projection_type=str(install.get("default_projection_type") or "currently_true_state")
        if isinstance(install, dict)
        else "currently_true_state",
        display_label=str(install.get("default_projection_label") or "Currently True")
        if isinstance(install, dict)
        else "Currently True",
    )


def _install_config(program: CompanyProgram) -> dict[str, Any]:
    installation = program.installation
    if installation is None and program.pack_id:
        installation = CompanyOperatingModelInstallation.objects.filter(
            company=program.company,
            pack_id=program.pack_id,
            status="active",
        ).first()
    config = (
        installation.config_json
        if installation and isinstance(installation.config_json, dict)
        else {}
    )
    return {
        "selected_services": _string_list(config.get("selected_services")),
        "regions": _string_list(config.get("regions")),
        **config,
    }


def _artifact_content(
    *,
    schema_id: str,
    program: CompanyProgram,
    stage: ProgramStageState,
    source_assets: list[Asset],
    install_config: dict[str, Any],
    generated_at: str,
    notes: str,
) -> dict[str, Any]:
    canonical_sources = [_asset_source_ref(asset) for asset in source_assets[:20]]
    accepted_assertions = [
        {
            "id": str(item.id),
            "kind": item.kind,
            "statement": item.statement,
            "category": item.category,
        }
        for item in AssertionRecord.objects.filter(
            company=program.company,
            program=program,
            validation_status="validated",
        ).order_by("category")[:20]
    ]
    return {
        "schema_id": schema_id,
        "title": _artifact_title(schema_id=schema_id, stage=stage),
        "program_id": str(program.id),
        "program_label": program.display_label,
        "stage_id": stage.stage_id,
        "stage_label": stage.label,
        "generated_at": generated_at,
        "source_summary": _source_summary(
            schema_id=schema_id,
            program=program,
            selected_services=_string_list(install_config.get("selected_services")),
            regions=_string_list(install_config.get("regions")),
            notes=notes,
        ),
        "sections": _sections_for_schema(
            schema_id=schema_id,
            selected_services=_string_list(install_config.get("selected_services")),
            regions=_string_list(install_config.get("regions")),
        ),
        "validated_assertion_refs": accepted_assertions,
        "source_artifact_refs": canonical_sources,
        "approval_requirements": _approval_requirements(schema_id),
    }


def _sections_for_schema(
    *,
    schema_id: str,
    selected_services: list[str],
    regions: list[str],
) -> list[dict[str, Any]]:
    service_text = ", ".join(selected_services[:8]) or "selected company services"
    region_text = ", ".join(regions[:8]) or "configured operating regions"
    common_context = (
        f"This artifact is generated from backend-owned program state, validated assertions, "
        f"canonical artifacts, selected services ({service_text}), and regions ({region_text})."
    )
    if schema_id == "growth_plan":
        headings = [
            "Executive direction",
            "Market and audience context",
            "Positioning and offer strategy",
            "Channel system",
            "Content system",
            "Conversion path",
            "CRM and lifecycle",
            "Measurement model",
            "Operating cadence",
            "Risk and approvals",
            "Next operations",
        ]
    elif schema_id == "yearly_planner":
        headings = [
            "12-month operating calendar",
            "Campaign waves",
            "Channel priorities",
            "Content themes",
            "Measurement checkpoints",
            "Approval milestones",
            "Quarterly review windows",
        ]
    elif schema_id.endswith("_strategy"):
        headings = [
            "Channel role",
            "Audience and message fit",
            "Execution requirements",
            "Measurement checkpoints",
            "Risks and blockers",
            "Next artifacts",
        ]
    elif schema_id in {"creative_instruction", "visual_asset_brief", "video_brief", "image_brief"}:
        headings = [
            "Objective",
            "Audience",
            "Brand constraints",
            "Channel and format",
            "Visual direction",
            "Forbidden elements",
            "Required text",
            "Localization notes",
            "Approval requirements",
        ]
    elif schema_id in {"quarterly_brief", "ad_hoc_brief", "performance_insight"}:
        headings = [
            "Observed performance",
            "Signals",
            "Hypotheses",
            "Recommended operations",
            "Projection updates",
        ]
    else:
        headings = [
            "Purpose",
            "Inputs",
            "Decisions",
            "Requirements",
            "Risks",
            "Next actions",
        ]
    return [
        {
            "heading": heading,
            "body": f"{heading} for {_label_from_id(schema_id)}. {common_context}",
        }
        for heading in headings
    ]


def _asset_source_ref(asset: Asset) -> dict[str, Any]:
    version = canonical_version(asset)
    return {
        "asset_id": str(asset.id),
        "artifact_type": (asset.metadata_json or {}).get("artifact_type") or asset.asset_type,
        "title": asset.title,
        "canonical_revision_id": str(version.id) if version is not None else None,
    }


def _source_summary(
    *,
    schema_id: str,
    program: CompanyProgram,
    selected_services: list[str],
    regions: list[str],
    notes: str,
) -> str:
    service_summary = ", ".join(selected_services[:8]) or "no services configured"
    region_summary = ", ".join(regions[:8]) or "no regions configured"
    note_suffix = f" Operator notes: {notes.strip()}" if notes.strip() else ""
    return (
        f"{_label_from_id(schema_id)} for {program.title}. Inputs include selected services "
        f"({service_summary}), regions ({region_summary}), validated assertions, canonical "
        f"artifacts, validation history, and current-state projection.{note_suffix}"
    )


def _approval_requirements(schema_id: str) -> list[str]:
    if schema_id in {
        "ad_copy",
        "email_copy",
        "landing_page_copy",
        "social_post_copy",
        "campaign_message_set",
        "creative_instruction",
    }:
        return ["evaluation", "policy_if_external_action", "human_approval_if_high_risk"]
    if schema_id in {"approval_chain", "operating_checklist"}:
        return ["human_review"]
    return ["review_before_external_use"]


def _artifact_title(*, schema_id: str, stage: ProgramStageState) -> str:
    return f"{stage.label} - {_label_from_id(schema_id)}"


def _evaluation_profile_ids(template: dict[str, Any]) -> list[str]:
    return _string_list(template.get("evaluation_profile_ids"))[:3]


def _payload(
    *,
    stage: ProgramStageState,
    workflow_id: str,
    artifacts: list[Asset],
    evaluations: list[dict[str, Any]],
    signals: list[CompanySignal],
    blockers: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
    projection: StateProjection,
) -> dict[str, Any]:
    return {
        "workflow_id": workflow_id,
        "program_id": str(stage.program_id),
        "stage_id": stage.stage_id,
        "status": stage.status,
        "created_artifacts": [artifact_payload(item, include_versions=True) for item in artifacts],
        "evaluations": evaluations,
        "created_signals": [
            {
                "id": str(item.id),
                "title": item.title,
                "summary": item.summary,
                "status": item.status,
                "metadata": item.metadata_json,
            }
            for item in signals
        ],
        "blockers": blockers,
        "skipped": skipped,
        "state_projection": projection_payload(projection),
    }


def _audit(
    *,
    user: User,
    program: CompanyProgram,
    stage: ProgramStageState,
    action: str,
    metadata: dict[str, Any],
) -> None:
    record_audit_log(
        actor=user,
        tenant_id=str(program.organization_id),
        action=action,
        resource_type="program_stage",
        resource_id=str(stage.id),
        metadata={"program_id": str(program.id), "stage_id": stage.stage_id, **metadata},
    )


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _safe_key(value: Any) -> str:
    return re.sub(r"[^a-zA-Z0-9_.:-]+", "_", str(value or "").strip()).strip("_")


def _label_from_id(value: str) -> str:
    return re.sub(r"[_-]+", " ", str(value or "")).strip().title()
