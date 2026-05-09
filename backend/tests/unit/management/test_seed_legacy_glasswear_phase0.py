from __future__ import annotations

import json
from io import StringIO
from typing import Any

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from infrastructure.orm.management.commands.seed_legacy_glasswear_phase0 import (
    DEFAULT_COMPANY_NAME,
    DEFAULT_EMAIL,
    DEFAULT_GEMINI_MODEL,
    DEFAULT_ORG_NAME,
    EXTERNAL_REF,
    EXTERNAL_SOURCE,
)
from infrastructure.orm.models import (
    Asset,
    Graph,
    GraphVersion,
    Organization,
    OrganizationMembership,
    User,
)


def _run_command(*, password: str = "LegacyPhase0!12345") -> dict[str, Any]:
    output = StringIO()
    call_command(
        "seed_legacy_glasswear_phase0",
        password=password,
        output_json=True,
        stdout=output,
    )
    payload = json.loads(output.getvalue())
    assert isinstance(payload, dict)
    return payload


@pytest.mark.django_db
def test_seed_legacy_glasswear_phase0_creates_clean_workspace():
    payload = _run_command()

    user = User.objects.get(email=DEFAULT_EMAIL)
    organization = Organization.objects.get(id=payload["organization_id"])
    graph = Graph.objects.get(id=payload["company_id"])
    version = GraphVersion.objects.get(id=payload["graph_version_id"])

    assert user.is_active is True
    assert user.check_password("LegacyPhase0!12345")
    assert user.default_organization_id == organization.id
    assert organization.name == DEFAULT_ORG_NAME
    assert OrganizationMembership.objects.filter(user=user).count() == 1
    assert OrganizationMembership.objects.get(user=user, organization=organization).role == "owner"
    assert graph.name == DEFAULT_COMPANY_NAME
    assert graph.organization_id == organization.id
    assert graph.owner_id == user.id
    assert graph.external_source == EXTERNAL_SOURCE
    assert graph.external_ref == EXTERNAL_REF
    assert version.graph_id == graph.id
    assert payload["membership_count"] == 1
    assert payload["company_count"] == 1


@pytest.mark.django_db
def test_seed_legacy_glasswear_phase0_is_idempotent():
    first = _run_command()
    second = _run_command()

    assert second["user_id"] == first["user_id"]
    assert second["organization_id"] == first["organization_id"]
    assert second["company_id"] == first["company_id"]
    assert second["graph_version_id"] == first["graph_version_id"]
    assert User.objects.filter(email=DEFAULT_EMAIL).count() == 1
    assert OrganizationMembership.objects.filter(user__email=DEFAULT_EMAIL).count() == 1
    assert (
        Graph.objects.filter(
            external_source=EXTERNAL_SOURCE,
            external_ref=EXTERNAL_REF,
        ).count()
        == 1
    )
    assert GraphVersion.objects.filter(graph_id=first["company_id"]).count() == 1


@pytest.mark.django_db
def test_seed_legacy_glasswear_phase0_allows_legacy_operation_graphs():
    first = _run_command()
    user = User.objects.get(email=DEFAULT_EMAIL)
    organization = Organization.objects.get(id=first["organization_id"])
    operation_graph = Graph.objects.create(
        owner=user,
        organization=organization,
        name="Legacy Phase 6 Evidence Judge Operation",
        description="Backend-owned Phase 6 judge operation.",
    )
    GraphVersion.objects.create(
        graph=operation_graph,
        version=1,
        graph_json={
            "nodes": [],
            "edges": [],
            "metadata": {"name": operation_graph.name, "legacy_phase": "phase-6"},
        },
    )

    second = _run_command()

    assert second["company_count"] == 1
    assert second["support_graph_count"] == 1
    assert second["visible_graph_count"] == 2
    assert second["company_id"] == first["company_id"]


@pytest.mark.django_db
def test_seed_legacy_glasswear_phase0_reruns_after_restoring_company_graph():
    first = _run_command()
    graph = Graph.objects.get(id=first["company_id"])
    latest = graph.versions.order_by("-version").first()
    assert latest is not None
    GraphVersion.objects.create(
        graph=graph,
        version=latest.version + 1,
        graph_json={
            "nodes": [],
            "edges": [],
            "metadata": {"name": "Legacy Phase 6 Visual Asset Brief"},
        },
    )

    restored = _run_command()
    rerun = _run_command()

    assert restored["company_id"] == first["company_id"]
    assert rerun["company_id"] == first["company_id"]
    phase0_key_count = GraphVersion.objects.filter(
        graph=graph,
        external_idempotency_key="legacy-glasswear:phase-0-company:v1",
    ).count()
    assert phase0_key_count == 1


@pytest.mark.django_db
def test_seed_legacy_glasswear_phase0_still_fails_for_unrelated_graphs():
    first = _run_command()
    user = User.objects.get(email=DEFAULT_EMAIL)
    organization = Organization.objects.get(id=first["organization_id"])
    Graph.objects.create(
        owner=user,
        organization=organization,
        name="Existing Unrelated Company",
        description="Should not be accepted by the Legacy seed command.",
    )

    with pytest.raises(CommandError, match="unrelated company graphs"):
        _run_command()


@pytest.mark.django_db
def test_seed_legacy_glasswear_phase0_fails_for_unrelated_organizations():
    user = User.objects.create_user(email=DEFAULT_EMAIL, password="Existing!12345")
    extra_org = Organization.objects.create(name="Unrelated Org")
    OrganizationMembership.objects.create(
        organization=extra_org,
        user=user,
        role="owner",
        is_default=False,
    )

    with pytest.raises(CommandError, match="more than one organization membership"):
        _run_command()


@pytest.mark.django_db
def test_seed_legacy_glasswear_phase0_fails_for_single_non_legacy_organization():
    user = User.objects.create_user(email=DEFAULT_EMAIL, password="Existing!12345")
    user.refresh_from_db()
    organization = user.default_organization
    assert organization is not None
    organization.name = "Existing Business"
    organization.save(update_fields=["name", "updated_at"])

    with pytest.raises(CommandError, match="non-Legacy organization"):
        _run_command()


@pytest.mark.django_db
def test_seed_legacy_glasswear_phase0_fails_without_password_for_new_user(monkeypatch):
    monkeypatch.delenv("LEGACY_TEST_PASSWORD", raising=False)

    with pytest.raises(CommandError, match="Password is required"):
        call_command("seed_legacy_glasswear_phase0")

    assert not User.objects.filter(email=DEFAULT_EMAIL).exists()


@pytest.mark.django_db
def test_seed_legacy_glasswear_phase0_graph_metadata_contains_legacy_profile():
    payload = _run_command()
    version = GraphVersion.objects.get(id=payload["graph_version_id"])
    graph_json = version.graph_json
    metadata = graph_json["metadata"]
    profile = metadata["company_profile"]
    departments = profile["departments"]

    assert profile["companyName"] == DEFAULT_COMPANY_NAME
    assert profile["autonomyMode"] == "assisted"
    assert profile["aiAccessMode"] == "byok"
    assert profile["intelligenceProvider"] == "google"
    assert profile["intelligenceModel"] == DEFAULT_GEMINI_MODEL
    assert profile["geminiMediaGeneration"]["provider"] == "google"
    assert profile["geminiMediaGeneration"]["durable_artifact_owner"] == "backend"
    assert [department["label"] for department in departments] == [
        "Operating System",
        "Content Studio",
        "Social Desk",
        "Sales Desk",
        "Ops & Inventory",
        "Finance & Procurement",
    ]
    assert metadata["legacy_glasswear"]["source_docs"] == [
        "docs/legacy-ultimate-test/legacy-report.md",
        "docs/legacy-ultimate-test/legacy-company-architecture-roadmap.md",
        "docs/architecture/runtime-invariants.md",
    ]
    media_generation = metadata["legacy_glasswear"]["gemini_media_generation"]
    assert media_generation["status"] == "planned_phase_1"
    assert media_generation["provider"] == "google"
    assert media_generation["artifact_types"] == ["image", "video"]
    assert media_generation["durable_artifact_owner"] == "backend"
    assert media_generation["operation_state_owner"] == "backend"
    assert media_generation["approval_required_before_publish"] is True
    assert metadata["runtime_contract"]["durable_source_of_truth"] == "backend"
    assert metadata["runtime_contract"]["engine_owns_durable_state"] is False
    content_studio = next(
        department for department in departments if department["id"] == "content-studio"
    )
    assert "gemini_image_draft" in content_studio["tools"]
    assert "gemini_video_brief" in content_studio["tools"]
    assert all(node["config"]["provider"] == "google" for node in graph_json["nodes"][:-1])
    assert all(node["config"]["model"] == DEFAULT_GEMINI_MODEL for node in graph_json["nodes"][:-1])


def test_company_assets_support_video_outputs():
    assert ("image", "Image") in Asset.ASSET_TYPE_CHOICES
    assert ("video", "Video") in Asset.ASSET_TYPE_CHOICES
