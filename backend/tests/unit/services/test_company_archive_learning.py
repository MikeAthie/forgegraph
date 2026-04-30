from __future__ import annotations

import json
import uuid
from typing import Any, cast

import pytest

from application.services.company_archive import (
    MAX_CONTEXT_PACK_BYTES,
    ArchiveService,
    AssetExtractionService,
    ContextPackService,
    EvidenceLinkService,
    context_pack_payload,
)
from application.services.company_learning import (
    OutcomeReviewService,
    PolicyCandidateService,
    PreferenceEventService,
)
from infrastructure.orm.models import (
    ApprovalTask,
    Asset,
    AssetExtract,
    AssetVersion,
    ContextPack,
    DecisionRecord,
    EvidenceLink,
    Graph,
    GraphVersion,
    Organization,
    PolicyRule,
    PreferenceEvent,
    Run,
)

pytestmark = pytest.mark.django_db


def _create_company(user, *, name: str = "Atlas Growth Agency OS") -> Graph:
    organization = user.default_organization
    assert organization is not None
    company = cast(
        Graph,
        Graph.objects.create(
            owner=user,
            organization=organization,
            name=name,
            description="Operate growth systems for clients.",
        ),
    )
    GraphVersion.objects.create(
        graph=company,
        version=1,
        graph_json={"nodes": [], "edges": [], "metadata": {"company_profile": {}}},
    )
    return company


def _organization(company: Graph) -> Organization:
    organization = company.organization
    assert organization is not None
    return organization


def _create_run(user, company: Graph, *, output_json: dict[str, Any] | None = None) -> Run:
    version = company.versions.first()
    assert version is not None
    return Run.objects.create(
        owner=user,
        organization=_organization(company),
        graph_version=version,
        status="succeeded",
        input_json={"operation_brief": "Build enterprise lead generation."},
        output_json=output_json,
    )


def test_deliverable_archived_as_asset(user):
    company = _create_company(user)
    run = _create_run(
        user,
        company,
        output_json={"deliverable": "Enterprise lead generation playbook"},
    )

    archived = ArchiveService().archive_deliverable_as_asset(run=run)

    assert len(archived) == 1
    assert archived[0].asset.company == company
    assert archived[0].asset.asset_type == "deliverable"
    assert archived[0].asset.origin_operation == run


def test_archive_deliverable_is_idempotent(user):
    company = _create_company(user)
    run = _create_run(user, company, output_json={"deliverable": "A reusable report"})

    ArchiveService().archive_deliverable_as_asset(run=run)
    ArchiveService().archive_deliverable_as_asset(run=run)

    assert Asset.objects.filter(company=company).count() == 1
    assert AssetVersion.objects.count() == 1


def test_archive_deliverable_changed_retry_creates_new_version_not_new_asset(user):
    company = _create_company(user)
    run = _create_run(user, company, output_json={"deliverable": "Version one"})

    ArchiveService().archive_deliverable_as_asset(run=run)
    run.output_json = {"deliverable": "Version two"}
    run.save(update_fields=["output_json"])
    ArchiveService().archive_deliverable_as_asset(run=run)

    asset = Asset.objects.get(company=company)
    assert asset.versions.count() == 2
    assert list(
        asset.versions.order_by("version_number").values_list("version_number", flat=True)
    ) == [
        1,
        2,
    ]


def test_asset_version_created_for_deliverable(user):
    company = _create_company(user)
    run = _create_run(user, company, output_json={"report": {"summary": "Useful output"}})

    archived = ArchiveService().archive_deliverable_as_asset(run=run)

    assert archived[0].version.version_number == 1
    assert archived[0].version.content_uri.startswith("forgegraph://runs/")
    assert archived[0].version.content_hash


def test_asset_extract_pending_created(user):
    company = _create_company(user)
    run = _create_run(user, company, output_json={"report": "Markdown style report"})

    ArchiveService().archive_deliverable_as_asset(run=run)

    extract = AssetExtract.objects.get(company=company)
    assert extract.embedding_status in {"pending", "indexed"}
    assert extract.asset_version.asset.company == company


def test_company_scope_enforced_for_assets(user):
    company = _create_company(user)
    other_company = _create_company(user, name="Other Company")
    run = _create_run(user, company, output_json={"deliverable": "Company A output"})

    ArchiveService().archive_deliverable_as_asset(run=run)

    assert Asset.objects.filter(company=company).count() == 1
    assert Asset.objects.filter(company=other_company).count() == 0


def test_context_pack_includes_relevant_prior_deliverable(user):
    company = _create_company(user)
    run_a = _create_run(
        user,
        company,
        output_json={"deliverable": "Enterprise account based lead generation system"},
    )
    ArchiveService().archive_deliverable_as_asset(run=run_a)
    run_b = _create_run(user, company)

    context_pack = ContextPackService().build_context_pack(
        company_id=company.id,
        operation_id=run_b.id,
        brief_snapshot={"objective": "Build enterprise lead generation"},
        created_for="operation_planning",
    )

    assert context_pack.asset_refs_json
    assert "enterprise" in context_pack.asset_refs_json[0]["summary"].lower()


def test_context_pack_includes_active_policy(user):
    company = _create_company(user)
    PolicyRule.objects.create(
        organization=_organization(company),
        company=company,
        title="Prefer referral-led acquisition",
        condition_json={"channel": "acquisition"},
        recommendation_json={"avoid": "paid-first launch"},
        confidence=0.9,
        status="active",
    )

    context_pack = ContextPackService().build_context_pack(company_id=company.id)

    assert context_pack.policy_refs_json[0]["title"] == "Prefer referral-led acquisition"


def test_context_pack_does_not_include_other_company_assets(user):
    company = _create_company(user)
    other_company = _create_company(user, name="Other Company")
    other_run = _create_run(
        user,
        other_company,
        output_json={"deliverable": "Enterprise lead generation secret"},
    )
    ArchiveService().archive_deliverable_as_asset(run=other_run)

    context_pack = ContextPackService().build_context_pack(
        company_id=company.id,
        brief_snapshot={"objective": "Enterprise lead generation"},
    )

    assert context_pack.asset_refs_json == []


def test_context_pack_does_not_include_other_company_decisions_in_same_org(user):
    company = _create_company(user)
    other_company = _create_company(user, name="Other Company")
    other_run = _create_run(user, other_company)
    DecisionRecord.objects.create(
        organization=_organization(company),
        execution=other_run,
        decision_type="operator_intervention",
        status="resolved",
        external_key=f"decision:{uuid.uuid4()}",
        context_json={"secret": "other company decision"},
        resolution_json={"decision": "do not leak"},
    )

    context_pack = ContextPackService().build_context_pack(company_id=company.id)

    assert context_pack.decision_refs_json == []


def test_context_pack_rejects_foreign_operation_scope(user):
    company = _create_company(user)
    other_company = _create_company(user, name="Other Company")
    other_run = _create_run(user, other_company)

    with pytest.raises(ValueError, match="Operation does not belong to company"):
        ContextPackService().build_context_pack(company_id=company.id, operation_id=other_run.id)


def test_context_pack_is_bounded(user):
    company = _create_company(user)
    for index in range(12):
        run = _create_run(
            user,
            company,
            output_json={"deliverable": f"Enterprise lead generation artifact {index}"},
        )
        ArchiveService().archive_deliverable_as_asset(run=run)

    context_pack = ContextPackService().build_context_pack(
        company_id=company.id,
        brief_snapshot={"objective": "Enterprise lead generation"},
    )

    assert len(context_pack.asset_refs_json) <= 8


def test_context_pack_payload_is_byte_bounded(user):
    company = _create_company(user)
    long_text = "enterprise " + ("x" * 50_000)
    run = _create_run(user, company, output_json={"deliverable": long_text})
    ArchiveService().archive_deliverable_as_asset(run=run)
    PolicyRule.objects.create(
        organization=_organization(company),
        company=company,
        title="Large active policy",
        condition_json={"category": long_text},
        recommendation_json={"guidance": long_text},
        confidence=0.9,
        status="active",
    )
    DecisionRecord.objects.create(
        organization=_organization(company),
        execution=run,
        decision_type="operator_intervention",
        status="resolved",
        external_key=f"decision:{uuid.uuid4()}",
        context_json={"context": long_text},
        resolution_json={"resolution": long_text},
    )

    context_pack = ContextPackService().build_context_pack(
        company_id=company.id,
        operation_id=run.id,
        brief_snapshot={
            "objective": long_text,
            "assumptions": [{"field": "audience", "value": long_text, "confidence": 0.5}],
        },
    )

    payload_size = len(
        json.dumps(
            context_pack_payload(context_pack),
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    )
    assert payload_size <= MAX_CONTEXT_PACK_BYTES


def test_attach_context_pack_to_run_preserves_user_input_and_returns_dispatch_payload(user):
    company = _create_company(user)
    run = _create_run(user, company)
    run.input_json = {"hello": "world"}
    run.dispatch_graph_json = {"nodes": [], "edges": [], "metadata": {"existing": True}}
    run.save(update_fields=["input_json", "dispatch_graph_json"])

    context_pack, outbound_graph = ContextPackService().attach_context_pack_to_run(
        run=run,
        outbound_graph={"nodes": [], "edges": [], "metadata": {"backend_attempt_id": "attempt"}},
    )
    in_memory_dispatch_graph = cast(dict[str, Any], run.dispatch_graph_json)
    in_memory_metadata = cast(dict[str, Any], in_memory_dispatch_graph["metadata"])
    run.refresh_from_db()

    assert run.input_json == {"hello": "world"}
    assert run.dispatch_graph_json["metadata"] == {"existing": True}
    assert in_memory_metadata["context_pack_id"] == str(context_pack.id)
    assert "backend_attempt_id" not in in_memory_metadata
    assert outbound_graph is not None
    assert outbound_graph["metadata"]["context_pack_id"] == str(context_pack.id)
    assert outbound_graph["metadata"]["backend_attempt_id"] == "attempt"


def test_attach_context_pack_to_run_reuses_existing_context_for_same_run(user):
    company = _create_company(user)
    run = _create_run(user, company)
    service = ContextPackService()

    first_pack, _ = service.attach_context_pack_to_run(run=run)
    second_pack, _ = service.attach_context_pack_to_run(run=run)

    assert second_pack == first_pack
    assert ContextPack.objects.filter(company=company, operation=run).count() == 1


def test_context_usage_creates_evidence_links(user):
    company = _create_company(user)
    run = _create_run(user, company, output_json={"deliverable": "Enterprise guide"})
    ArchiveService().archive_deliverable_as_asset(run=run)
    context_pack = ContextPackService().build_context_pack(company_id=company.id)

    links = EvidenceLinkService().record_context_usage(
        context_pack_id=context_pack.id,
        operation_id=run.id,
        used_for="planning",
    )

    assert len(links) == 1
    assert EvidenceLink.objects.filter(operation=run).count() == 1


def test_context_usage_is_idempotent_for_same_context_pack(user):
    company = _create_company(user)
    run = _create_run(user, company, output_json={"deliverable": "Enterprise guide"})
    ArchiveService().archive_deliverable_as_asset(run=run)
    context_pack = ContextPackService().build_context_pack(company_id=company.id)

    first = EvidenceLinkService().record_context_usage(
        context_pack_id=context_pack.id,
        operation_id=run.id,
        used_for="planning",
    )
    second = EvidenceLinkService().record_context_usage(
        context_pack_id=context_pack.id,
        operation_id=run.id,
        used_for="planning",
    )

    assert [link.id for link in second] == [link.id for link in first]
    assert EvidenceLink.objects.filter(operation=run).count() == 1


def test_context_usage_rejects_foreign_operation(user):
    company = _create_company(user)
    other_company = _create_company(user, name="Other Company")
    other_run = _create_run(user, other_company)
    run = _create_run(user, company, output_json={"deliverable": "Enterprise guide"})
    ArchiveService().archive_deliverable_as_asset(run=run)
    context_pack = ContextPackService().build_context_pack(company_id=company.id)

    with pytest.raises(ValueError, match="Operation does not belong to company"):
        EvidenceLinkService().record_context_usage(
            context_pack_id=context_pack.id,
            operation_id=other_run.id,
            used_for="planning",
        )


def test_evidence_link_points_to_asset_version_used(user):
    company = _create_company(user)
    run = _create_run(user, company, output_json={"deliverable": "Enterprise guide"})
    archived = ArchiveService().archive_deliverable_as_asset(run=run)[0]
    context_pack = ContextPack.objects.create(
        organization=_organization(company),
        company=company,
        asset_refs_json=[
            {
                "asset_id": str(archived.asset.id),
                "asset_version_id": str(archived.version.id),
                "asset_extract_id": str(archived.extract.id) if archived.extract else None,
            }
        ],
        created_for="operation_planning",
    )

    link = EvidenceLinkService().record_context_usage(
        context_pack_id=context_pack.id,
        operation_id=run.id,
        used_for="planning",
    )[0]

    assert link.asset_version == archived.version


def test_evidence_links_can_be_listed_for_operation(user):
    company = _create_company(user)
    run = _create_run(user, company, output_json={"deliverable": "Enterprise guide"})
    ArchiveService().archive_deliverable_as_asset(run=run)
    context_pack = ContextPackService().build_context_pack(company_id=company.id)
    EvidenceLinkService().record_context_usage(
        context_pack_id=context_pack.id,
        operation_id=run.id,
        used_for="planning",
    )

    assert EvidenceLink.objects.filter(company=company, operation=run).count() == 1


def test_approval_creates_preference_event(user):
    company = _create_company(user)
    run = _create_run(user, company)
    approval = ApprovalTask.objects.create(
        run=run,
        node_id="approval",
        status="approved",
        payload={"approved": True},
        result={"approved": True},
    )

    event = PreferenceEventService().record_approval_event(approval_task=approval, actor=user)

    assert event.event_type == "approved"
    assert PreferenceEvent.objects.count() == 1


def test_repeated_hitl_feedback_is_idempotent(user):
    company = _create_company(user)
    run = _create_run(user, company)
    approval = ApprovalTask.objects.create(
        run=run,
        node_id="approval",
        status="approved",
        payload={"approved": True},
        result={"approved": True},
    )

    first = PreferenceEventService().record_approval_event(approval_task=approval, actor=user)
    second = PreferenceEventService().record_approval_event(approval_task=approval, actor=user)

    assert second.id == first.id
    assert PreferenceEvent.objects.filter(approval_task=approval).count() == 1


def test_preference_event_rejects_foreign_context_pack(user):
    company = _create_company(user)
    other_company = _create_company(user, name="Other Company")
    run = _create_run(user, company)
    other_context_pack = ContextPackService().build_context_pack(company_id=other_company.id)
    approval = ApprovalTask.objects.create(
        run=run,
        node_id="approval",
        status="approved",
        payload={"approved": True},
        result={"approved": True},
    )

    with pytest.raises(ValueError, match="Context pack does not belong to company"):
        PreferenceEventService().record_hitl_feedback(
            approval_task=approval,
            actor=user,
            final_value={"approved": True},
            context_pack=other_context_pack,
        )


def test_rejection_creates_preference_event(user):
    company = _create_company(user)
    run = _create_run(user, company)
    approval = ApprovalTask.objects.create(
        run=run,
        node_id="approval",
        status="rejected",
        payload={"approved": True},
        result={"approved": False, "rationale": "Too risky"},
    )

    event = PreferenceEventService().record_approval_event(approval_task=approval, actor=user)

    assert event.event_type == "rejected"
    assert event.rationale == "Too risky"


def test_human_edit_stores_diff(user):
    company = _create_company(user)
    run = _create_run(user, company)
    approval = ApprovalTask.objects.create(
        run=run,
        node_id="approval",
        status="approved",
        payload={"headline": "Old"},
        result={"headline": "New", "approved": True, "edited": True},
    )

    event = PreferenceEventService().record_approval_event(approval_task=approval, actor=user)

    assert event.event_type == "edited"
    diff_json = cast(dict[str, Any], event.diff_json)
    assert diff_json["changed"]["headline"] == {"from": "Old", "to": "New"}


def test_preference_event_links_to_context_pack_when_available(user):
    company = _create_company(user)
    run = _create_run(user, company)
    context_pack = ContextPackService().build_context_pack(
        company_id=company.id,
        operation_id=run.id,
    )
    approval = ApprovalTask.objects.create(
        run=run,
        node_id="approval",
        status="approved",
        payload={"approved": True},
        result={"approved": True},
    )

    event = PreferenceEventService().record_approval_event(approval_task=approval, actor=user)

    assert event.context_pack == context_pack


def test_outcome_review_can_attach_to_deliverable(user):
    company = _create_company(user)
    deliverable_id = uuid.uuid4()

    review = OutcomeReviewService().attach_outcome_to_deliverable(
        company=company,
        deliverable_id=deliverable_id,
        success_score=0.8,
    )

    assert review.deliverable_id == deliverable_id
    assert review.success_score == 0.8


def test_outcome_review_can_record_failure_root_cause(user):
    company = _create_company(user)

    review = OutcomeReviewService().create_outcome_review(
        company=company,
        success_score=0.2,
        root_cause="Wrong buyer segment",
        issues=[{"issue": "low conversion"}],
    )

    assert review.root_cause == "Wrong buyer segment"
    assert review.issues_json == [{"issue": "low conversion"}]


def test_outcome_review_is_company_scoped(user):
    company = _create_company(user)
    other_company = _create_company(user, name="Other")
    other_run = _create_run(user, other_company, output_json={"deliverable": "Other output"})
    asset = ArchiveService().archive_deliverable_as_asset(run=other_run)[0].asset

    with pytest.raises(ValueError):
        OutcomeReviewService().create_outcome_review(company=company, asset=asset)


def test_asset_extraction_does_not_read_foreign_company_run_uri(user):
    company = _create_company(user)
    other_company = _create_company(user, name="Other")
    other_run = _create_run(
        user,
        other_company,
        output_json={"deliverable": "Other company confidential output"},
    )
    asset = ArchiveService().create_asset(
        company=company,
        title="Suspicious pointer",
        asset_type="deliverable",
        source_key=f"manual:{uuid.uuid4()}",
    )
    version = ArchiveService().create_asset_version(
        asset=asset,
        content_uri=f"forgegraph://runs/{other_run.id}/output/deliverable",
        content=b"placeholder",
        mime_type="text/plain",
    )

    extract = AssetExtractionService().extract_asset_version(version)

    assert extract.embedding_status == "failed"
    assert not extract.text_content


def test_policy_candidate_can_be_created_from_preference_events(user):
    company = _create_company(user)
    run = _create_run(user, company)
    approval = ApprovalTask.objects.create(
        run=run,
        node_id="approval",
        status="approved",
        payload={"approved": True},
        result={"approved": True},
    )
    preference = PreferenceEventService().record_approval_event(
        approval_task=approval,
        actor=user,
    )

    rule = PolicyCandidateService().create_policy_candidate(
        company=company,
        title="Keep private-service positioning",
        condition={"operation_type": "launch"},
        recommendation={"positioning": "private-service"},
        supporting_preference_event_ids=[preference.id],
    )

    assert rule.status == "candidate"
    assert rule.supporting_preference_event_ids_json == [str(preference.id)]


def test_policy_candidate_requires_explicit_promotion(user):
    company = _create_company(user)

    rule = PolicyCandidateService().create_policy_candidate(
        company=company,
        title="Candidate only",
        condition={},
        recommendation={},
    )

    assert rule.status == "candidate"


def test_active_policy_appears_in_future_context_pack(user):
    company = _create_company(user)
    rule = PolicyCandidateService().create_policy_candidate(
        company=company,
        title="Use concierge referrals",
        condition={"buyer": "premium"},
        recommendation={"channel": "concierge"},
    )
    PolicyCandidateService().promote_policy_rule(policy_rule=rule)

    context_pack = ContextPackService().build_context_pack(company_id=company.id)

    assert context_pack.policy_refs_json[0]["policy_rule_id"] == str(rule.id)


def test_rejected_policy_does_not_appear_in_context_pack(user):
    company = _create_company(user)
    rule = PolicyCandidateService().create_policy_candidate(
        company=company,
        title="Rejected policy",
        condition={},
        recommendation={},
    )
    PolicyCandidateService().reject_policy_candidate(policy_rule=rule)

    context_pack = ContextPackService().build_context_pack(company_id=company.id)

    assert context_pack.policy_refs_json == []
