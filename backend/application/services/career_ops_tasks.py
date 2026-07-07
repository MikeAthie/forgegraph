"""CareerOps task materialization helpers."""

from __future__ import annotations

import hashlib

from application.services.career_ops_graph_contract import (
    CAREER_OPS_STAGE_LABELS,
    CAREER_OPS_STAGE_TO_DEPARTMENT,
)
from infrastructure.orm.models import DepartmentRegistry, Graph, Run, TaskRecord

CAREER_OPS_URL_PIPELINE_TASK_STAGES: tuple[str, ...] = (
    "stage_03_market_scan",
    "stage_04_liveness_and_dedupe",
    "stage_05_fit_evaluation",
    "stage_06_application_packet",
    "stage_07_candidate_approval",
    "stage_08_submission_tracking",
)


def materialize_url_pipeline_tasks(
    *,
    company: Graph,
    run: Run,
    opportunity_external_key: str,
) -> list[TaskRecord]:
    """Create or update native task rows for a CareerOps URL pipeline."""

    organization = company.organization
    if organization is None:
        raise ValueError("CareerOps tasks require an organization-scoped company.")
    departments = {
        department.slug: department
        for department in DepartmentRegistry.objects.filter(
            organization=organization,
            slug__in=set(CAREER_OPS_STAGE_TO_DEPARTMENT.values()),
        )
    }
    tasks: list[TaskRecord] = []
    task_key_prefix = _task_external_key_prefix(opportunity_external_key)
    for stage_id in CAREER_OPS_URL_PIPELINE_TASK_STAGES:
        department_slug = CAREER_OPS_STAGE_TO_DEPARTMENT[stage_id]
        status = "waiting_for_decision" if stage_id == "stage_07_candidate_approval" else "pending"
        task, _ = TaskRecord.objects.update_or_create(
            organization=organization,
            external_key=f"{task_key_prefix}:{stage_id}",
            defaults={
                "execution": run,
                "department": departments.get(department_slug),
                "source_node_id": stage_id,
                "title": f"CareerOps — {CAREER_OPS_STAGE_LABELS[stage_id]}",
                "status": status,
                "priority": "high"
                if stage_id in {"stage_07_candidate_approval", "stage_08_submission_tracking"}
                else "normal",
                "summary": (
                    f"{CAREER_OPS_STAGE_LABELS[stage_id]} for CareerOps opportunity "
                    f"{opportunity_external_key}."
                ),
            },
        )
        tasks.append(task)
    return tasks


def _task_external_key_prefix(opportunity_external_key: str) -> str:
    """Return a stable TaskRecord.external_key prefix bounded by the 255-char column.

    Opportunity external keys can include full application URLs. TaskRecord.external_key
    must stay under 255 chars after appending `:<stage_id>`, so long source keys are
    represented by a readable prefix plus a content hash while the full key remains in
    the task summary.
    """

    raw = str(opportunity_external_key or "unknown")
    prefix = f"career_ops:url_pipeline:{raw}"
    max_stage_suffix = max(len(stage_id) for stage_id in CAREER_OPS_URL_PIPELINE_TASK_STAGES) + 1
    max_prefix_length = 255 - max_stage_suffix
    if len(prefix) <= max_prefix_length:
        return prefix
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    readable_budget = max_prefix_length - len(":sha256:") - len(digest)
    readable = prefix[: max(0, readable_budget)].rstrip(":-/")
    return f"{readable}:sha256:{digest}"
