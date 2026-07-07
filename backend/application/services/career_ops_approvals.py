"""CareerOps human approval decision helpers."""

from __future__ import annotations

from django.utils import timezone

from infrastructure.orm.models import (
    AssetVersion,
    CompanyOpportunity,
    DecisionRecord,
    Run,
    TaskRecord,
)


def request_packet_approval(
    *,
    run: Run,
    approval_task: TaskRecord,
    opportunity: CompanyOpportunity,
    packet_version: AssetVersion,
    deliverable_versions: list[dict[str, str]],
) -> DecisionRecord:
    """Create or replay an exact-version packet approval decision."""

    context_json = {
        "career_ops": {
            "approval_type": "application_packet",
            "opportunity_id": str(opportunity.id),
            "packet_asset_id": str(packet_version.asset_id),
            "packet_asset_version_id": str(packet_version.id),
            "deliverable_versions": deliverable_versions,
            "external_side_effects_allowed": False,
        }
    }
    decision, created = DecisionRecord.objects.get_or_create(
        organization=run.organization,
        external_key=f"career_ops:packet:{opportunity.id}:approval:{packet_version.id}",
        defaults={
            "execution": run,
            "task": approval_task,
            "decision_type": "human_approval",
            "status": "pending",
            "requested_at": timezone.now(),
            "context_json": context_json,
        },
    )
    if not created:
        update_fields = ["execution", "task", "decision_type", "context_json", "updated_at"]
        decision.execution = run
        decision.task = approval_task
        decision.decision_type = "human_approval"
        decision.context_json = context_json
        if decision.status == "pending":
            decision.requested_at = timezone.now()
            update_fields.append("requested_at")
        decision.save(update_fields=update_fields)
    approval_task.current_decision = decision
    approval_task.status = "waiting_for_decision"
    approval_task.save(update_fields=["current_decision", "status", "updated_at"])
    return decision
