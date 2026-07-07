"""ForgeGraph-native CareerOps URL/JD pipeline orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from django.db import transaction
from django.utils import timezone

from application.services.career_ops_approvals import request_packet_approval
from application.services.career_ops_artifacts import (
    write_career_ops_deliverable,
    write_career_ops_file_deliverable,
)
from application.services.career_ops_engagements import ensure_career_ops_application_engagement
from application.services.career_ops_graph_contract import (
    CAREER_OPS_APPLIED_COOLDOWN_DAYS,
    CAREER_OPS_PACK_ID,
    CAREER_OPS_STAGE_LABELS,
    CAREER_OPS_STAGE_SEQUENCE,
)
from application.services.career_ops_opportunities import (
    ensure_opportunity_for_signal,
    record_scanned_job,
    update_application_status,
)
from application.services.career_ops_packet_builder import build_career_ops_packet_payloads
from application.services.career_ops_projections import materialize_career_ops_pipeline_projection
from application.services.career_ops_recruiter_evaluation import (
    evaluate_career_ops_resume_professional_delivery,
)
from application.services.career_ops_resume_formatter import render_career_ops_ats_resume
from application.services.career_ops_tasks import materialize_url_pipeline_tasks
from infrastructure.orm.models import Asset, CompanyOpportunity, Graph, GraphVersion, Run, User


@dataclass(frozen=True, slots=True)
class CareerOpsPipelineResult:
    run_id: str
    signal_id: str | None = None
    opportunity_id: str | None = None
    task_ids: list[str] = field(default_factory=list)
    decision_id: str | None = None
    deliverable_ids: list[str] = field(default_factory=list)
    projection_id: str | None = None
    blocked_reasons: list[str] = field(default_factory=list)
    packet_asset_version_id: str | None = None


@dataclass(frozen=True, slots=True)
class CareerOpsApplicationPacketBuildResult:
    run_id: str
    opportunity_id: str
    task_ids: list[str] = field(default_factory=list)
    decision_id: str | None = None
    deliverable_ids: list[str] = field(default_factory=list)
    projection_id: str | None = None
    blocked_reasons: list[str] = field(default_factory=list)
    packet_asset_version_id: str | None = None
    tailored_resume_asset_version_id: str | None = None
    ats_resume_text_asset_version_id: str | None = None
    ats_resume_html_asset_version_id: str | None = None
    ats_resume_pdf_asset_version_id: str | None = None
    ats_resume_parseability_report_asset_version_id: str | None = None
    recruiter_evaluation_asset_version_id: str | None = None
    cover_letter_asset_version_id: str | None = None
    ats_simulation_asset_version_id: str | None = None


def ensure_career_ops_graph_version(*, company: Graph) -> GraphVersion:
    """Return the latest company graph version or create a minimal CareerOps contract version."""

    latest = GraphVersion.objects.filter(graph=company).order_by("-version").first()
    if latest is not None:
        return latest
    with transaction.atomic():
        latest = GraphVersion.objects.filter(graph=company).order_by("-version").first()
        if latest is not None:
            return latest
        return GraphVersion.objects.create(
            graph=company,
            version=1,
            external_idempotency_key=f"career-ops:{company.id}:initial-graph",
            graph_json={
                "nodes": [
                    {"id": stage, "type": "career_ops_stage", "label": CAREER_OPS_STAGE_LABELS[stage]}
                    for stage in CAREER_OPS_STAGE_SEQUENCE
                ],
                "edges": [
                    {"source": src, "target": dst}
                    for src, dst in zip(CAREER_OPS_STAGE_SEQUENCE, CAREER_OPS_STAGE_SEQUENCE[1:], strict=False)
                ],
                "metadata": {"pack_id": CAREER_OPS_PACK_ID, "source": "career_ops_pipeline"},
            },
        )


def create_career_ops_run(*, company: Graph, actor: User, posting: dict[str, Any], idempotency_key: str) -> Run:
    """Create a backend Run for a synchronous dry-run CareerOps URL pipeline."""

    graph_version = ensure_career_ops_graph_version(company=company)
    now = timezone.now()
    return Run.objects.create(
        owner=actor,
        organization=company.organization,
        graph_version=graph_version,
        status="running",
        started_at=now,
        last_progress_at=now,
        recovery_policy="resume",
        input_json={
            "career_ops": {
                "pipeline": "url_intake",
                "idempotency_key": idempotency_key,
                "posting": posting,
                "submit_mode": "manual_only",
                "dry_run": True,
                "external_side_effects_allowed": False,
            }
        },
    )


def run_career_ops_url_pipeline(
    *,
    company: Graph,
    actor: User,
    posting: dict[str, Any],
    idempotency_key: str,
    cooldown_days: int = CAREER_OPS_APPLIED_COOLDOWN_DAYS,
) -> CareerOpsPipelineResult:
    """Run the backend-owned, no-side-effect CareerOps URL pipeline."""

    if company.organization_id is None:
        raise ValueError("CareerOps URL pipeline requires an organization-scoped company.")
    if actor is None:
        raise ValueError("CareerOps URL pipeline requires an actor for Run.owner.")
    with transaction.atomic():
        run = create_career_ops_run(
            company=company,
            actor=actor,
            posting=posting,
            idempotency_key=idempotency_key,
        )
        signal = record_scanned_job(company=company, user=actor, posting=posting, cooldown_days=cooldown_days)
        opportunity = ensure_opportunity_for_signal(signal=signal, user=actor)
        if opportunity is None:
            raise ValueError("CareerOps signal did not produce an opportunity.")
        tasks = materialize_url_pipeline_tasks(
            company=company,
            run=run,
            opportunity_external_key=opportunity.external_key,
        )
        engagement = ensure_career_ops_application_engagement(company=company, actor=actor)
        payloads = build_career_ops_packet_payloads(company=company, opportunity=opportunity)
        tasks_by_stage = {task.source_node_id: task for task in tasks}
        deliverable_versions = []
        deliverable_ids = []
        content_versions_by_type = {}
        liveness_deliverable, liveness_version = write_career_ops_deliverable(
            engagement=engagement,
            run=run,
            task=tasks_by_stage.get("stage_04_liveness_and_dedupe"),
            opportunity=opportunity,
            deliverable_type="job_liveness_receipt",
            title=f"Liveness receipt — {opportunity.title}",
            payload=payloads.liveness,
        )
        if "posting_expired" in payloads.blocked_reasons:
            update_application_status(
                opportunity=opportunity,
                status="discarded",
                user=actor,
                metadata={
                    "blocked_reasons": payloads.blocked_reasons,
                    "tracker_status": "discarded",
                    "liveness": payloads.liveness["posting_legitimacy"]["liveness"],
                    "external_side_effects_allowed": False,
                },
            )
            for task in tasks:
                if task.source_node_id in {"stage_03_market_scan", "stage_04_liveness_and_dedupe"}:
                    task.status = "completed"
                else:
                    task.status = "cancelled"
                task.ended_at = timezone.now()
                task.save(update_fields=["status", "ended_at", "updated_at"])
            projection = materialize_career_ops_pipeline_projection(company=company)
            run.status = "succeeded"
            run.ended_at = timezone.now()
            run.output_json = {
                "career_ops": {
                    "signal_id": str(signal.id),
                    "opportunity_id": str(opportunity.id),
                    "task_ids": [str(task.id) for task in tasks],
                    "decision_id": None,
                    "deliverable_ids": [str(liveness_deliverable.id)],
                    "liveness_asset_version_id": str(liveness_version.id),
                    "packet_asset_version_id": None,
                    "projection_id": str(projection.id),
                    "blocked_reasons": payloads.blocked_reasons,
                    "external_side_effects_allowed": False,
                }
            }
            run.save(update_fields=["status", "ended_at", "output_json"])
            return CareerOpsPipelineResult(
                run_id=str(run.id),
                signal_id=str(signal.id),
                opportunity_id=str(opportunity.id),
                task_ids=[str(task.id) for task in tasks],
                decision_id=None,
                deliverable_ids=[str(liveness_deliverable.id)],
                projection_id=str(projection.id),
                blocked_reasons=payloads.blocked_reasons,
                packet_asset_version_id=None,
            )
        evaluation_deliverable, evaluation_version = write_career_ops_deliverable(
            engagement=engagement,
            run=run,
            task=tasks_by_stage.get("stage_05_fit_evaluation"),
            opportunity=opportunity,
            deliverable_type="job_evaluation_report",
            title=f"Evaluation report — {opportunity.title}",
            payload=payloads.evaluation,
        )
        draft_deliverable_versions = _write_application_draft_deliverables(
            engagement=engagement,
            run=run,
            task=tasks_by_stage.get("stage_06_application_packet"),
            opportunity=opportunity,
            packet=payloads.packet,
        )
        packet_deliverable, packet_version = write_career_ops_deliverable(
            engagement=engagement,
            run=run,
            task=tasks_by_stage.get("stage_06_application_packet"),
            opportunity=opportunity,
            deliverable_type="application_packet",
            title=f"Application packet — {opportunity.title}",
            payload=payloads.packet,
        )
        for deliverable, version in (
            (liveness_deliverable, liveness_version),
            (evaluation_deliverable, evaluation_version),
            *draft_deliverable_versions,
            (packet_deliverable, packet_version),
        ):
            deliverable_ids.append(str(deliverable.id))
            deliverable_versions.append(
                {
                    "deliverable_id": str(deliverable.id),
                    "deliverable_type": deliverable.deliverable_type,
                    "asset_version_id": str(version.id),
                }
            )
            content_versions_by_type[deliverable.deliverable_type] = str(version.id)
        approval_task = tasks_by_stage["stage_07_candidate_approval"]
        decision = request_packet_approval(
            run=run,
            approval_task=approval_task,
            opportunity=opportunity,
            packet_version=packet_version,
            deliverable_versions=deliverable_versions,
        )
        _mark_opportunity_approval_pending(
            opportunity=opportunity,
            blocked_reasons=payloads.blocked_reasons,
            packet_version_id=str(packet_version.id),
            evaluation=payloads.evaluation,
        )
        projection = materialize_career_ops_pipeline_projection(company=company)
        run.status = "succeeded"
        run.ended_at = timezone.now()
        run.output_json = {
            "career_ops": {
                "signal_id": str(signal.id),
                "opportunity_id": str(opportunity.id),
                "task_ids": [str(task.id) for task in tasks],
                "decision_id": str(decision.id),
                "deliverable_ids": deliverable_ids,
                "packet_asset_version_id": str(packet_version.id),
                "ats_simulation_asset_version_id": content_versions_by_type.get("ats_simulation_report"),
                "projection_id": str(projection.id),
                "blocked_reasons": payloads.blocked_reasons,
                "external_side_effects_allowed": False,
            }
        }
        run.save(update_fields=["status", "ended_at", "output_json"])
    return CareerOpsPipelineResult(
        run_id=str(run.id),
        signal_id=str(signal.id),
        opportunity_id=str(opportunity.id),
        task_ids=[str(task.id) for task in tasks],
        decision_id=str(decision.id),
        deliverable_ids=deliverable_ids,
        projection_id=str(projection.id),
        blocked_reasons=payloads.blocked_reasons,
        packet_asset_version_id=str(packet_version.id),
    )


def build_career_ops_application_packet_for_opportunity(
    *,
    company: Graph,
    actor: User,
    opportunity: CompanyOpportunity,
    idempotency_key: str,
) -> CareerOpsApplicationPacketBuildResult:
    """Build review-ready CareerOps application drafts for an existing opportunity."""

    if opportunity.company_id != company.id:
        raise ValueError("CareerOps application packet opportunity must belong to the target company.")
    if company.organization_id is None:
        raise ValueError("CareerOps application packet build requires an organization-scoped company.")
    with transaction.atomic():
        graph_version = ensure_career_ops_graph_version(company=company)
        now = timezone.now()
        run = Run.objects.create(
            owner=actor,
            organization=company.organization,
            graph_version=graph_version,
            status="running",
            started_at=now,
            last_progress_at=now,
            recovery_policy="resume",
            input_json={
                "career_ops": {
                    "pipeline": "application_packet_for_existing_opportunity",
                    "idempotency_key": idempotency_key,
                    "opportunity_id": str(opportunity.id),
                    "submit_mode": "manual_only",
                    "dry_run": True,
                    "external_side_effects_allowed": False,
                }
            },
        )
        tasks = materialize_url_pipeline_tasks(
            company=company,
            run=run,
            opportunity_external_key=opportunity.external_key,
        )
        tasks_by_stage = {task.source_node_id: task for task in tasks}
        engagement = ensure_career_ops_application_engagement(company=company, actor=actor)
        payloads = build_career_ops_packet_payloads(company=company, opportunity=opportunity)
        deliverable_versions = []
        deliverable_ids = []
        liveness_deliverable, liveness_version = write_career_ops_deliverable(
            engagement=engagement,
            run=run,
            task=tasks_by_stage.get("stage_04_liveness_and_dedupe"),
            opportunity=opportunity,
            deliverable_type="job_liveness_receipt",
            title=f"Liveness receipt — {opportunity.title}",
            payload=payloads.liveness,
        )
        evaluation_deliverable, evaluation_version = write_career_ops_deliverable(
            engagement=engagement,
            run=run,
            task=tasks_by_stage.get("stage_05_fit_evaluation"),
            opportunity=opportunity,
            deliverable_type="job_evaluation_report",
            title=f"Evaluation report — {opportunity.title}",
            payload=payloads.evaluation,
        )
        draft_versions = _write_application_draft_deliverables(
            engagement=engagement,
            run=run,
            task=tasks_by_stage.get("stage_06_application_packet"),
            opportunity=opportunity,
            packet=payloads.packet,
        )
        packet_deliverable, packet_version = write_career_ops_deliverable(
            engagement=engagement,
            run=run,
            task=tasks_by_stage.get("stage_06_application_packet"),
            opportunity=opportunity,
            deliverable_type="application_packet",
            title=f"Application packet — {opportunity.title}",
            payload=payloads.packet,
        )
        content_versions_by_type = {}
        for deliverable, version in (
            (liveness_deliverable, liveness_version),
            (evaluation_deliverable, evaluation_version),
            *draft_versions,
            (packet_deliverable, packet_version),
        ):
            deliverable_ids.append(str(deliverable.id))
            deliverable_versions.append(
                {
                    "deliverable_id": str(deliverable.id),
                    "deliverable_type": deliverable.deliverable_type,
                    "asset_version_id": str(version.id),
                }
            )
            content_versions_by_type[deliverable.deliverable_type] = str(version.id)
        decision = request_packet_approval(
            run=run,
            approval_task=tasks_by_stage["stage_07_candidate_approval"],
            opportunity=opportunity,
            packet_version=packet_version,
            deliverable_versions=deliverable_versions,
        )
        _mark_opportunity_approval_pending(
            opportunity=opportunity,
            blocked_reasons=payloads.blocked_reasons,
            packet_version_id=str(packet_version.id),
            evaluation=payloads.evaluation,
        )
        projection = materialize_career_ops_pipeline_projection(company=company)
        run.status = "succeeded"
        run.ended_at = timezone.now()
        run.output_json = {
            "career_ops": {
                "opportunity_id": str(opportunity.id),
                "task_ids": [str(task.id) for task in tasks],
                "decision_id": str(decision.id),
                "deliverable_ids": deliverable_ids,
                "packet_asset_version_id": str(packet_version.id),
                "tailored_resume_asset_version_id": content_versions_by_type.get("tailored_resume_html"),
                "ats_resume_text_asset_version_id": content_versions_by_type.get("ats_resume_text"),
                "ats_resume_html_asset_version_id": content_versions_by_type.get("ats_resume_html"),
                "ats_resume_pdf_asset_version_id": content_versions_by_type.get("ats_resume_pdf"),
                "ats_resume_parseability_report_asset_version_id": content_versions_by_type.get(
                    "ats_resume_parseability_report"
                ),
                "recruiter_evaluation_asset_version_id": content_versions_by_type.get("recruiter_evaluation_report"),
                "cover_letter_asset_version_id": content_versions_by_type.get("cover_letter_draft"),
                "ats_simulation_asset_version_id": content_versions_by_type.get("ats_simulation_report"),
                "projection_id": str(projection.id),
                "blocked_reasons": payloads.blocked_reasons,
                "external_side_effects_allowed": False,
            }
        }
        run.save(update_fields=["status", "ended_at", "output_json"])
    return CareerOpsApplicationPacketBuildResult(
        run_id=str(run.id),
        opportunity_id=str(opportunity.id),
        task_ids=[str(task.id) for task in tasks],
        decision_id=str(decision.id),
        deliverable_ids=deliverable_ids,
        projection_id=str(projection.id),
        blocked_reasons=payloads.blocked_reasons,
        packet_asset_version_id=str(packet_version.id),
        tailored_resume_asset_version_id=content_versions_by_type.get("tailored_resume_html"),
        ats_resume_text_asset_version_id=content_versions_by_type.get("ats_resume_text"),
        ats_resume_html_asset_version_id=content_versions_by_type.get("ats_resume_html"),
        ats_resume_pdf_asset_version_id=content_versions_by_type.get("ats_resume_pdf"),
        ats_resume_parseability_report_asset_version_id=content_versions_by_type.get(
            "ats_resume_parseability_report"
        ),
        recruiter_evaluation_asset_version_id=content_versions_by_type.get("recruiter_evaluation_report"),
        cover_letter_asset_version_id=content_versions_by_type.get("cover_letter_draft"),
        ats_simulation_asset_version_id=content_versions_by_type.get("ats_simulation_report"),
    )


def _write_application_draft_deliverables(
    *,
    engagement: Any,
    run: Run,
    task: Any,
    opportunity: CompanyOpportunity,
    packet: dict[str, Any],
) -> list[tuple[Any, Any]]:
    artifacts = packet.get("artifacts", {}) if isinstance(packet, dict) else {}
    if not isinstance(artifacts, dict):
        return []
    deliverable_versions = []
    tailored_resume = artifacts.get("tailored_resume")
    if isinstance(tailored_resume, dict):
        deliverable_versions.append(
            write_career_ops_deliverable(
                engagement=engagement,
                run=run,
                task=task,
                opportunity=opportunity,
                deliverable_type="tailored_resume_html",
                title=f"Tailored resume — {opportunity.title}",
                payload=tailored_resume,
            )
        )
        ats_artifacts = render_career_ops_ats_resume(
            tailored_resume=tailored_resume,
            opportunity=packet.get("opportunity") if isinstance(packet.get("opportunity"), dict) else None,
            candidate_identity=_candidate_identity(company=engagement.company),
        )
        common_payload = {
            "format": "career_ops_ats_resume_package_v1",
            "formatter_version": ats_artifacts.parseability_report.get("formatter_version"),
            "expected_text_sha256": ats_artifacts.parseability_report.get("expected_text_sha256"),
            "parseability_status": ats_artifacts.parseability_report.get("status"),
            "parseability_report": ats_artifacts.parseability_report,
        }
        ats_simulation = artifacts.get("ats_simulation")
        ats_score = ats_simulation.get("atsScore") if isinstance(ats_simulation, dict) else None
        recruiter_evaluation = evaluate_career_ops_resume_professional_delivery(
            resume_text=ats_artifacts.text,
            opportunity=packet.get("opportunity") if isinstance(packet.get("opportunity"), dict) else None,
            ats_score=ats_score if isinstance(ats_score, int) else None,
        )
        deliverable_versions.extend(
            [
                write_career_ops_file_deliverable(
                    engagement=engagement,
                    run=run,
                    task=task,
                    opportunity=opportunity,
                    deliverable_type="ats_resume_text",
                    title=f"ATS resume text — {opportunity.title}",
                    content_bytes=ats_artifacts.text.encode("utf-8"),
                    mime_type="text/plain",
                    file_extension="txt",
                    payload=common_payload,
                ),
                write_career_ops_file_deliverable(
                    engagement=engagement,
                    run=run,
                    task=task,
                    opportunity=opportunity,
                    deliverable_type="ats_resume_html",
                    title=f"ATS resume HTML — {opportunity.title}",
                    content_bytes=ats_artifacts.html.encode("utf-8"),
                    mime_type="text/html",
                    file_extension="html",
                    payload=common_payload,
                ),
                write_career_ops_file_deliverable(
                    engagement=engagement,
                    run=run,
                    task=task,
                    opportunity=opportunity,
                    deliverable_type="ats_resume_pdf",
                    title=f"ATS resume PDF — {opportunity.title}",
                    content_bytes=ats_artifacts.pdf_bytes,
                    mime_type="application/pdf",
                    file_extension="pdf",
                    payload=common_payload,
                ),
                write_career_ops_deliverable(
                    engagement=engagement,
                    run=run,
                    task=task,
                    opportunity=opportunity,
                    deliverable_type="ats_resume_parseability_report",
                    title=f"ATS resume parseability — {opportunity.title}",
                    payload=ats_artifacts.parseability_report,
                ),
                write_career_ops_deliverable(
                    engagement=engagement,
                    run=run,
                    task=task,
                    opportunity=opportunity,
                    deliverable_type="recruiter_evaluation_report",
                    title=f"Recruiter evaluation — {opportunity.title}",
                    payload=recruiter_evaluation,
                ),
            ]
        )
    cover_letter = artifacts.get("cover_letter")
    if isinstance(cover_letter, dict):
        deliverable_versions.append(
            write_career_ops_deliverable(
                engagement=engagement,
                run=run,
                task=task,
                opportunity=opportunity,
                deliverable_type="cover_letter_draft",
                title=f"Cover letter — {opportunity.title}",
                payload=cover_letter,
            )
        )
    ats_simulation = artifacts.get("ats_simulation")
    if isinstance(ats_simulation, dict):
        deliverable_versions.append(
            write_career_ops_deliverable(
                engagement=engagement,
                run=run,
                task=task,
                opportunity=opportunity,
                deliverable_type="ats_simulation_report",
                title=f"ATS simulation — {opportunity.title}",
                payload=ats_simulation,
            )
        )
    return deliverable_versions


def _candidate_identity(*, company: Graph) -> dict[str, Any]:
    asset = Asset.objects.filter(company=company, source_key="career_ops:cv_source", status="active").first()
    if asset is None:
        return {}
    metadata = asset.metadata_json or {}
    career_ops = metadata.get("career_ops", {}) if isinstance(metadata, dict) else {}
    career_ops = career_ops if isinstance(career_ops, dict) else {}
    identity: dict[str, Any] = {}
    for target_key, source_keys in {
        "name": ("name", "full_name", "candidate_name"),
        "title": ("title", "headline", "position"),
        "email": ("email",),
        "phone": ("phone", "telephone"),
        "location": ("location", "address"),
        "github": ("github", "github_url"),
        "linkedin": ("linkedin", "linkedin_url"),
        "website": ("website", "portfolio_url"),
        "professional_summary": ("professional_summary", "summary"),
    }.items():
        for source_key in source_keys:
            value = metadata.get(source_key) or career_ops.get(source_key)
            if str(value or "").strip():
                identity[target_key] = str(value).strip()
                break
    education = metadata.get("education") or career_ops.get("education")
    if isinstance(education, list | tuple):
        identity["education"] = list(education)
    elif isinstance(education, dict | str):
        identity["education"] = [education]
    for collection_key in ("experience", "projects", "skills", "certifications"):
        collection_value = metadata.get(collection_key) or career_ops.get(collection_key)
        if isinstance(collection_value, list | tuple):
            identity[collection_key] = list(collection_value)
        elif isinstance(collection_value, dict | str):
            identity[collection_key] = [collection_value]
    return identity


def _mark_opportunity_approval_pending(
    *,
    opportunity: CompanyOpportunity,
    blocked_reasons: list[str],
    packet_version_id: str,
    evaluation: dict[str, Any],
) -> None:
    career_ops = dict((opportunity.metadata_json or {}).get("career_ops", {}))
    career_ops["application_status"] = "approval_pending"
    career_ops["tracker_status"] = evaluation.get("tracker_status", "evaluated")
    career_ops["recommendation"] = evaluation.get("recommendation")
    career_ops["score"] = evaluation.get("score")
    career_ops["score_label"] = evaluation.get("score_label")
    career_ops["archetype"] = evaluation.get("archetype")
    career_ops["blocked_reasons"] = blocked_reasons
    career_ops["packet_asset_version_id"] = packet_version_id
    career_ops["external_side_effects_allowed"] = False
    opportunity.metadata_json = {**(opportunity.metadata_json or {}), "career_ops": career_ops}
    opportunity.next_action = "Review exact packet version before applying."
    opportunity.save(update_fields=["metadata_json", "next_action", "updated_at"])
