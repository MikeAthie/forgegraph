from __future__ import annotations

from typing import Any, cast

import pytest

from application.services.company_archive import (
    ArchiveService,
    ContextPackService,
    EvidenceLinkService,
)
from application.services.company_learning import (
    PolicyCandidateService,
    PreferenceEventService,
)
from application.services.gemini_media import GeminiMediaBytes
from application.services.tenancy import ensure_default_organization
from infrastructure.crypto.encryption import encrypt_api_key
from infrastructure.orm.models import (
    APIKey,
    ApprovalTask,
    Graph,
    GraphVersion,
    MediaGenerationJob,
    Organization,
    Run,
    User,
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
        input_json={},
        output_json=output_json,
    )


def _google_credential(user: User) -> APIKey:
    organization = user.default_organization
    assert organization is not None
    return APIKey.objects.create(
        organization=organization,
        user=user,
        provider="google",
        name="Legacy Gemini BYOK",
        encrypted_key=encrypt_api_key("gemini-test-key"),
    )


def test_archive_assets_api_lists_company_assets(authenticated_client, user):
    company = _create_company(user)
    run = _create_run(user, company, output_json={"deliverable": "Reusable launch plan"})
    ArchiveService().archive_deliverable_as_asset(run=run)

    response = authenticated_client.get(
        "/api/archive/assets",
        {"company_id": str(company.id)},
    )

    assert response.status_code == 200
    assets = response.json()["data"]["assets"]
    assert len(assets) == 1
    assert assets[0]["asset_type"] == "deliverable"


def test_archive_asset_versions_api_returns_versions(authenticated_client, user):
    company = _create_company(user)
    run = _create_run(user, company, output_json={"deliverable": "Reusable launch plan"})
    asset = ArchiveService().archive_deliverable_as_asset(run=run)[0].asset

    response = authenticated_client.get(f"/api/archive/assets/{asset.id}/versions")

    assert response.status_code == 200
    versions = response.json()["data"]["versions"]
    assert versions[0]["content_uri"].startswith("forgegraph://runs/")


def test_media_generation_api_creates_image_and_downloads_content(
    authenticated_client,
    monkeypatch,
    settings,
    tmp_path,
    user,
):
    settings.MEDIA_GENERATION_ARTIFACT_ROOT = tmp_path
    company = _create_company(user)
    credential = _google_credential(user)

    def fake_generate_image(self, **kwargs):
        return GeminiMediaBytes(
            content=b"api-png",
            mime_type="image/png",
            response_json={"ok": True},
        )

    monkeypatch.setattr(
        "application.services.gemini_media.GoogleMediaClient.generate_image",
        fake_generate_image,
    )

    response = authenticated_client.post(
        "/api/archive/media-generations",
        data={
            "company_id": str(company.id),
            "credential_id": str(credential.id),
            "modality": "image",
            "prompt": "Legacy product image draft for buyer@example.com",
            "idempotency_key": "api-image",
        },
        format="json",
    )

    assert response.status_code == 201
    job = response.json()["data"]["media_generation"]
    assert job["status"] == "succeeded"
    assert job["provider"] == "google"
    assert "buyer@example.com" not in job["prompt"]
    content_response = authenticated_client.get(
        f"/api/archive/assets/{job['output_asset_id']}/versions/"
        f"{job['output_asset_version_id']}/content"
    )
    assert content_response.status_code == 200
    assert content_response.content == b"api-png"
    assert content_response["Content-Type"] == "image/png"


def test_media_generation_api_hides_other_organization_job(authenticated_client, user):
    other_user = User.objects.create_user(email="media-other@example.com", password="password123")
    ensure_default_organization(other_user)
    other_company = _create_company(other_user, name="Other Org Company")
    credential = _google_credential(other_user)
    organization = other_company.organization
    assert organization is not None
    job = MediaGenerationJob.objects.create(
        organization=organization,
        company=other_company,
        requested_by=other_user,
        credential=credential,
        modality="image",
        provider="google",
        model="imagen-4.0-generate-001",
        prompt="Legacy image draft",
        prompt_hash="hash",
        status="pending",
    )

    response = authenticated_client.get(f"/api/archive/media-generations/{job.id}")

    assert response.status_code == 404


def test_archive_api_does_not_cross_company_scope(authenticated_client, user):
    company = _create_company(user)
    other_company = _create_company(user, name="Other Company")
    run = _create_run(user, other_company, output_json={"deliverable": "Other plan"})
    ArchiveService().archive_deliverable_as_asset(run=run)

    response = authenticated_client.get(
        "/api/archive/assets",
        {"company_id": str(company.id)},
    )

    assert response.status_code == 200
    assert response.json()["data"]["assets"] == []


def test_archive_asset_detail_api_hides_other_organization_asset(authenticated_client, user):
    other_user = User.objects.create_user(email="archive-other@example.com", password="password123")
    ensure_default_organization(other_user)
    other_company = _create_company(other_user, name="Other Org Company")
    other_run = _create_run(
        other_user, other_company, output_json={"deliverable": "Other org plan"}
    )
    asset = ArchiveService().archive_deliverable_as_asset(run=other_run)[0].asset

    response = authenticated_client.get(f"/api/archive/assets/{asset.id}")

    assert response.status_code == 404


def test_evidence_links_api_does_not_cross_company_scope(authenticated_client, user):
    company = _create_company(user)
    other_company = _create_company(user, name="Other Company")
    other_run = _create_run(user, other_company, output_json={"deliverable": "Other plan"})
    ArchiveService().archive_deliverable_as_asset(run=other_run)
    context_pack = ContextPackService().build_context_pack(company_id=other_company.id)
    EvidenceLinkService().record_context_usage(
        context_pack_id=context_pack.id,
        operation_id=other_run.id,
        used_for="planning",
    )

    response = authenticated_client.get(
        "/api/archive/evidence-links",
        {"company_id": str(company.id)},
    )

    assert response.status_code == 200
    assert response.json()["data"]["evidence_links"] == []


def test_create_outcome_review_api(authenticated_client, user):
    company = _create_company(user)
    run = _create_run(user, company, output_json={"deliverable": "Reusable launch plan"})
    asset = ArchiveService().archive_deliverable_as_asset(run=run)[0].asset

    response = authenticated_client.post(
        "/api/learning/outcome-reviews",
        data={
            "company_id": str(company.id),
            "operation_id": str(run.id),
            "asset_id": str(asset.id),
            "success_score": 0.4,
            "human_feedback": "Missed the buyer segment.",
            "root_cause": "Targeting was too broad.",
        },
        format="json",
    )

    assert response.status_code == 201
    payload = response.json()["data"]["outcome_review"]
    assert payload["asset_id"] == str(asset.id)
    assert payload["root_cause"] == "Targeting was too broad."


def test_create_outcome_review_api_rejects_foreign_asset_same_org(authenticated_client, user):
    company = _create_company(user)
    other_company = _create_company(user, name="Other Company")
    other_run = _create_run(user, other_company, output_json={"deliverable": "Other plan"})
    foreign_asset = ArchiveService().archive_deliverable_as_asset(run=other_run)[0].asset

    response = authenticated_client.post(
        "/api/learning/outcome-reviews",
        data={
            "company_id": str(company.id),
            "asset_id": str(foreign_asset.id),
            "success_score": 0.4,
        },
        format="json",
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_preference_events_api_does_not_cross_company_scope(authenticated_client, user):
    company = _create_company(user)
    other_company = _create_company(user, name="Other Company")
    other_run = _create_run(user, other_company)
    approval = ApprovalTask.objects.create(
        run=other_run,
        node_id="approval",
        status="approved",
        payload={"approved": True},
        result={"approved": True},
    )
    PreferenceEventService().record_approval_event(approval_task=approval, actor=user)

    response = authenticated_client.get(
        "/api/learning/preference-events",
        {"company_id": str(company.id)},
    )

    assert response.status_code == 200
    assert response.json()["data"]["preference_events"] == []


def test_policy_candidate_api_requires_explicit_promotion(authenticated_client, user):
    company = _create_company(user)

    create_response = authenticated_client.post(
        "/api/learning/policy-rules",
        data={
            "company_id": str(company.id),
            "title": "Prefer private service",
            "condition": {"category": "luxury"},
            "recommendation": {"cta": "request private fitting"},
            "confidence": 0.7,
        },
        format="json",
    )

    assert create_response.status_code == 201
    rule = create_response.json()["data"]["policy_rule"]
    assert rule["status"] == "candidate"

    promote_response = authenticated_client.post(
        f"/api/learning/policy-rules/{rule['id']}/promote",
        data={},
        format="json",
    )

    assert promote_response.status_code == 200
    assert promote_response.json()["data"]["policy_rule"]["status"] == "active"


def test_policy_list_api_filters_candidates(authenticated_client, user):
    company = _create_company(user)
    PolicyCandidateService().create_policy_candidate(
        company=company,
        title="Candidate policy",
        condition={},
        recommendation={},
    )

    response = authenticated_client.get(
        "/api/learning/policy-rules",
        {"company_id": str(company.id), "status": "candidate"},
    )

    assert response.status_code == 200
    rules = response.json()["data"]["policy_rules"]
    assert len(rules) == 1
    assert rules[0]["status"] == "candidate"
