from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import cast
from zipfile import ZipFile

import pytest

from application.services.company_run_task_routing import (
    TASK_SNAPSHOT_METADATA_KEY,
    refresh_whiteboard_task_snapshot,
)
from application.services.legacy_weekend_pipeline import run_legacy_weekend_pipeline
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import (
    Asset,
    AssetVersion,
    CompanyProgram,
    DepartmentRegistry,
    Graph,
    Organization,
    ProgramStageState,
    ServiceCatalogItem,
    ServiceDeliverable,
    ServiceEngagement,
    TaskRoutingRecord,
    User,
    WorkWhiteboard,
)
from scripts.prepare_legacy_handoff_email import (
    LEGACY_HANDOFF_PROFILE_REF,
    prepare_legacy_handoff,
)

pytestmark = pytest.mark.django_db

_STAGE_SLUGS = [
    "strategy_research",
    "brand_content",
    "channel_execution",
    "crm_lifecycle",
    "analytics_performance",
    "qa_compliance",
    "client_approval_ops",
]


def _organization(user: User) -> Organization:
    ensure_default_organization(user)
    organization = user.default_organization
    assert organization is not None
    return organization


def _departments(user: User) -> None:
    organization = _organization(user)
    for slug in _STAGE_SLUGS:
        DepartmentRegistry.objects.get_or_create(
            organization=organization,
            slug=slug,
            defaults={
                "name": slug.replace("_", " ").title(),
                "department_type": "atlas_agency",
                "service_tags_json": ["atlas", "digital_marketing_pro"],
            },
        )


def _fixture_root(tmp_path: Path) -> Path:
    root = tmp_path / "legacy_deliverables"
    media = root / "media"
    media.mkdir(parents=True)
    manifest = {
        "posts": [
            {
                "id": "ig01",
                "date": "2026-06-05",
                "theme": "Launch",
                "headline": "La noche empieza antes",
                "caption": "Legacy abre el fin de semana con Optical Noir.",
                "cta": "Pide disponibilidad por DM.",
                "asset": "legacy_ig_01_launch.png",
            },
            {
                "id": "ig02",
                "date": "2026-06-06",
                "theme": "Monroe",
                "headline": "Monroe after dark",
                "caption": "Una silueta para salir tarde.",
                "cta": "Reserva tu pieza.",
                "asset": "legacy_ig_02_monroe.png",
            },
        ]
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    for filename in [
        "legacy_brand_context.json",
        "legacy_marketing_strategy.md",
        "legacy_social_media_calendar.md",
        "legacy_instagram_copy_pack.md",
        "legacy_creative_direction_brief.md",
        "legacy_client_approval_packet.md",
        "legacy_campaign_launch_package.md",
    ]:
        (root / filename).write_text(
            f"# {filename}\nLegacy weekend fixture content.\n", encoding="utf-8"
        )
    for filename in ["legacy_ig_01_launch.png", "legacy_ig_02_monroe.png"]:
        (media / filename).write_bytes(b"fixture-png-bytes")
    (media / "legacy_reel_01_optical_noir.mp4").write_bytes(b"fixture-mp4-bytes")
    return root


def _handoff_engagement(user: User) -> ServiceEngagement:
    organization = _organization(user)
    company = cast(
        Graph,
        Graph.objects.create(
            organization=organization,
            owner=user,
            name="Legacy",
            description="Legacy handoff test company.",
        ),
    )
    catalog = ServiceCatalogItem.objects.create(
        organization=organization,
        slug="legacy-codex-handoff-test",
        title="Legacy Codex Handoff Test",
        status="active",
        visibility="customer",
        created_by=user,
    )
    return ServiceEngagement.objects.create(
        organization=organization,
        company=company,
        catalog_item=catalog,
        status="in_progress",
        customer_status="review_ready",
        public_summary="Legacy Codex run deliverables are ready for client handoff.",
        metadata_json={"formatting": {"profile_ref": LEGACY_HANDOFF_PROFILE_REF}},
        requested_by=user,
    )


def _legacy_handoff_source(
    user: User,
    engagement: ServiceEngagement,
    *,
    deliverable_type: str,
    title: str,
    content: str,
    metadata: dict[str, object] | None = None,
) -> ServiceDeliverable:
    data = content.encode("utf-8")
    digest = hashlib.sha256(data).hexdigest()
    asset = Asset.objects.create(
        organization=engagement.organization,
        company=engagement.company,
        title=title,
        asset_type="deliverable",
        source_key=f"legacy-codex-test:{engagement.id}:{deliverable_type}",
        created_by_type="agent",
        created_by_id=user.id,
        metadata_json={
            "source": "codex_session_runtime",
            "deliverable_type": deliverable_type,
            "inline_preview": content,
        },
    )
    version = AssetVersion.objects.create(
        asset=asset,
        version_number=1,
        content_uri=f"forgegraph://codex-session/{engagement.id}/{deliverable_type}.md",
        content_hash=digest,
        mime_type="text/markdown",
        size_bytes=len(data),
        provenance_json={
            "source": "codex_session_runtime",
            "inline_content": content,
        },
    )
    return ServiceDeliverable.objects.create(
        organization=engagement.organization,
        company=engagement.company,
        engagement=engagement,
        title=title,
        deliverable_type=deliverable_type,
        status="ready",
        visibility="customer",
        artifact=asset,
        summary=content[:240],
        metadata_json={
            "source": "codex_session_runtime",
            "asset_version_id": str(version.id),
            **(metadata or {}),
        },
        created_by=user,
    )


def _legacy_handoff_sources(user: User, engagement: ServiceEngagement) -> list[ServiceDeliverable]:
    return [
        _legacy_handoff_source(
            user,
            engagement,
            deliverable_type="codex_strategy_brief",
            title="Legacy Codex Strategy Brief",
            content=(
                "Atlas prepared this handoff for Legacy. Executive summary: "
                "the Optical Noir launch package is ready for review."
            ),
            metadata={"requires_approval": True},
        ),
        _legacy_handoff_source(
            user,
            engagement,
            deliverable_type="codex_qa_report",
            title="Legacy Codex Launch QA Report",
            content="Facts: source receipts, routing evidence, and QA findings are attached.",
            metadata={"connector_status": "unverified"},
        ),
        _legacy_handoff_source(
            user,
            engagement,
            deliverable_type="codex_client_approval_packet",
            title="Legacy Codex Client Approval Packet",
            content="Recommendation: approve the next production step after receipt review.",
        ),
    ]


def test_prepare_legacy_handoff_uses_formatter_persisted_package(user, tmp_path):
    engagement = _handoff_engagement(user)
    _legacy_handoff_sources(user, engagement)

    result = prepare_legacy_handoff(
        engagement=engagement,
        output_dir=tmp_path / "handoff",
        recipient="admin@intlabs.dev",
        subject="Legacy handoff ready",
    )

    assert result["recipient"] == "admin@intlabs.dev"
    assert result["subject"] == "Legacy handoff ready"
    assert result["profile_ref"] == LEGACY_HANDOFF_PROFILE_REF
    assert result["quality_status"] == "passed"
    assert result["source_deliverable_count"] == 3
    assert result["pdf_asset_version_id"]
    assert cast(str, result["pdf_filename"]).endswith(".pdf")

    package_version = AssetVersion.objects.select_related("asset").get(
        id=cast(str, result["package_asset_version_id"])
    )
    assert package_version.asset.metadata_json["source"] == "deliverable_formatting"
    assert package_version.asset.metadata_json["format"] == "zip_package"
    assert package_version.provenance_json["source"] == "deliverable_formatting"
    assert package_version.provenance_json["format"] == "zip_package"
    assert package_version.provenance_json["render_provenance"]["profile"]["profile_ref"] == (
        LEGACY_HANDOFF_PROFILE_REF
    )

    exported_package = Path(str(result["package_path"]))
    assert exported_package.exists()
    assert exported_package.read_bytes() == base64.b64decode(
        package_version.provenance_json["inline_content_base64"].encode("ascii")
    )
    exported_pdf = Path(str(result["pdf_path"]))
    assert exported_pdf.exists()
    assert exported_pdf.read_bytes().startswith(b"%PDF-")
    assert exported_pdf.read_bytes().rstrip().endswith(b"%%EOF")


def test_legacy_handoff_zip_contains_formatter_report_manifest_and_quality_data(
    user,
    tmp_path,
):
    engagement = _handoff_engagement(user)
    sources = _legacy_handoff_sources(user, engagement)

    result = prepare_legacy_handoff(
        engagement=engagement,
        output_dir=tmp_path / "handoff",
        recipient="admin@intlabs.dev",
        subject="Legacy handoff ready",
    )

    with ZipFile(Path(str(result["package_path"]))) as archive:
        names = set(archive.namelist())
        assert names == {
            result["markdown_filename"],
            result["manifest_filename"],
            result["pdf_filename"],
        }
        assert "manifest.json" not in names
        markdown_text = archive.read(str(result["markdown_filename"])).decode("utf-8")
        pdf_bytes = archive.read(str(result["pdf_filename"]))
        manifest_payload = json.loads(
            archive.read(str(result["manifest_filename"])).decode("utf-8")
        )

    assert "# Legacy Client Handoff" in markdown_text
    assert pdf_bytes.startswith(b"%PDF-")
    assert pdf_bytes.rstrip().endswith(b"%%EOF")
    assert b"Legacy Client Handoff" in pdf_bytes
    assert manifest_payload["schema_version"] == "deliverable_format_manifest.v1"
    assert manifest_payload["profile"]["profile_ref"] == LEGACY_HANDOFF_PROFILE_REF
    assert manifest_payload["profile"]["profile_sha256"]
    assert manifest_payload["deferred_formats"] == ["email_handoff"]
    assert manifest_payload["quality"]["status"] == "passed"
    assert [source["service_deliverable_id"] for source in manifest_payload["sources"]] == [
        str(source.id) for source in sources
    ]
    assert [source["content_hash"] for source in manifest_payload["sources"]] == [
        source_asset.versions.get().content_hash
        for source in sources
        if (source_asset := source.artifact) is not None
    ]
    manifest_sources_by_id = {
        source["service_deliverable_id"]: source for source in manifest_payload["sources"]
    }
    expected_sources_by_id = {
        str(source.id): source.artifact.versions.get().content_hash for source in sources
    }
    assert set(manifest_sources_by_id) == set(expected_sources_by_id)
    assert {
        source_id: source["content_hash"] for source_id, source in manifest_sources_by_id.items()
    } == expected_sources_by_id
    assert manifest_payload["outputs"][0]["format"] == "markdown_report"
    assert manifest_payload["outputs"][0]["asset_version_id"] == result["markdown_asset_version_id"]
    assert any(
        output["format"] == "pdf_report"
        and output["asset_version_id"] == result["pdf_asset_version_id"]
        for output in manifest_payload["outputs"]
    )
    assert "deliverables" not in manifest_payload
    assert "to" not in manifest_payload


def test_legacy_weekend_pipeline_creates_stage_owned_deliverables(user, tmp_path):
    _departments(user)
    root = _fixture_root(tmp_path)

    result = run_legacy_weekend_pipeline(user=user, root=root, company_name="Legacy")

    engagement = ServiceEngagement.objects.get(id=result["service_engagement"]["id"])
    stages = {
        stage.stage_id: stage
        for stage in ProgramStageState.objects.filter(
            program__metadata_json__service_engagement_id=str(engagement.id)
        )
    }
    assert set(stages) == set(_STAGE_SLUGS)
    assert all(stage.status == "completed" for stage in stages.values())
    assert stages["strategy_research"].state_json["outputs"]
    assert stages["brand_content"].state_json["outputs"]
    assert stages["channel_execution"].state_json["outputs"]
    assert stages["crm_lifecycle"].state_json["outputs"]
    assert stages["analytics_performance"].state_json["outputs"]
    assert stages["qa_compliance"].state_json["outputs"]
    assert stages["client_approval_ops"].state_json["outputs"]

    deliverables = list(ServiceDeliverable.objects.filter(engagement=engagement))
    assert result["deliverable_count"] == len(deliverables) >= 13
    for deliverable in deliverables:
        lineage = deliverable.metadata_json.get("department_pipeline")
        assert lineage is not None, deliverable.deliverable_type
        assert lineage["created_via_department_pipeline"] is True
        assert lineage["stage_id"] in _STAGE_SLUGS
        task_routing = deliverable.metadata_json.get("task_routing")
        assert task_routing is not None, deliverable.deliverable_type
        assert task_routing["routing_record_id"]
        assert task_routing["stage_id"] in _STAGE_SLUGS
        assert str(deliverable.id) in {
            str(output.get("id"))
            for stage in stages.values()
            for output in stage.state_json["outputs"]
        }

    assert ServiceDeliverable.objects.filter(
        engagement=engagement,
        deliverable_type="crm_dm_response_scripts",
        department__slug="crm_lifecycle",
    ).exists()
    assert ServiceDeliverable.objects.filter(
        engagement=engagement,
        deliverable_type="manual_metrics_template",
        department__slug="analytics_performance",
    ).exists()
    assert ServiceDeliverable.objects.filter(
        engagement=engagement,
        deliverable_type="qa_report",
        department__slug="qa_compliance",
    ).exists()


def test_legacy_weekend_pipeline_routes_social_tasks_through_channel_execution(user, tmp_path):
    _departments(user)
    root = _fixture_root(tmp_path)

    result = run_legacy_weekend_pipeline(user=user, root=root, company_name="Legacy")

    engagement = ServiceEngagement.objects.get(id=result["service_engagement"]["id"])
    tasks = list(TaskRoutingRecord.objects.filter(service_engagement=engagement))
    stage_tasks = [task for task in tasks if (task.metadata_json or {}).get("company_run_task")]
    social_tasks = [task for task in tasks if (task.metadata_json or {}).get("department_pipeline")]
    assert len(stage_tasks) == 7
    assert len(social_tasks) == 2
    assert result["routing_task_count"] == 9
    assert {task.metadata_json["company_run_task"]["stage_id"] for task in stage_tasks} == set(
        _STAGE_SLUGS
    )
    assert {task.to_department.slug for task in social_tasks} == {"channel_execution"}
    for task in social_tasks:
        lineage = task.metadata_json.get("department_pipeline")
        assert lineage["stage_id"] == "channel_execution"
        assert lineage["created_via_department_pipeline"] is True


def test_legacy_weekend_pipeline_bootstraps_whiteboard_cards_from_product_entrypoint(
    user,
    tmp_path,
):
    _departments(user)
    root = _fixture_root(tmp_path)

    first = run_legacy_weekend_pipeline(user=user, root=root, company_name="Legacy")
    second = run_legacy_weekend_pipeline(user=user, root=root, company_name="Legacy")

    assert first["service_engagement"]["id"] == second["service_engagement"]["id"]
    engagement = ServiceEngagement.objects.get(id=first["service_engagement"]["id"])
    company = cast(Graph, engagement.company)
    program = CompanyProgram.objects.get(
        company=company,
        metadata_json__service_engagement_id=str(engagement.id),
    )
    whiteboard = WorkWhiteboard.objects.get(service_engagement=engagement)

    assert (
        ServiceDeliverable.objects.filter(engagement=engagement).count()
        == first["deliverable_count"]
    )
    stages = list(ProgramStageState.objects.filter(program=program).order_by("sequence"))
    assert {stage.stage_id for stage in stages} == set(_STAGE_SLUGS)
    assert len(stages) == 7

    stage_cards = list(
        TaskRoutingRecord.objects.filter(
            company=company,
            service_engagement=engagement,
            metadata_json__company_run_task__program_id=str(program.id),
        ).order_by("metadata_json__company_run_task__sequence")
    )
    social_cards = list(
        TaskRoutingRecord.objects.filter(
            company=company,
            service_engagement=engagement,
            metadata_json__department_pipeline__stage_id="channel_execution",
        )
    )
    assert len(stage_cards) == 7
    assert len(social_cards) == 2
    assert (
        TaskRoutingRecord.objects.filter(
            company=company,
            service_engagement=engagement,
        ).count()
        == 9
    )
    assert {card.metadata_json["company_run_task"]["stage_id"] for card in stage_cards} == set(
        _STAGE_SLUGS
    )
    assert {card.metadata_json["whiteboard_id"] for card in stage_cards} == {str(whiteboard.id)}
    assert all(card.metadata_json["board_card"] is True for card in stage_cards)

    snapshot = whiteboard.metadata_json[TASK_SNAPSHOT_METADATA_KEY]
    assert snapshot["snapshot_source"] == "backend_db"
    assert snapshot["program_id"] == str(program.id)
    assert snapshot["whiteboard_id"] == str(whiteboard.id)
    assert {task["stage_id"] for task in snapshot["tasks"]} == set(_STAGE_SLUGS)
    assert len(snapshot["tasks"]) == 7
    assert {task["status"] for task in snapshot["tasks"]} == {"completed"}
    assert {task["routing_record_id"] for task in snapshot["tasks"]} == {
        str(card.id) for card in stage_cards
    }

    metadata_without_snapshot = dict(whiteboard.metadata_json)
    metadata_without_snapshot.pop(TASK_SNAPSHOT_METADATA_KEY)
    WorkWhiteboard.objects.filter(id=whiteboard.id).update(metadata_json=metadata_without_snapshot)
    rebuilt_whiteboard = refresh_whiteboard_task_snapshot(
        WorkWhiteboard.objects.get(id=whiteboard.id),
        program,
    )
    rebuilt_snapshot = rebuilt_whiteboard.metadata_json[TASK_SNAPSHOT_METADATA_KEY]
    assert rebuilt_snapshot["snapshot_source"] == "backend_db"
    assert {task["stage_id"] for task in rebuilt_snapshot["tasks"]} == set(_STAGE_SLUGS)
    assert {task["routing_record_id"] for task in rebuilt_snapshot["tasks"]} == {
        str(card.id) for card in stage_cards
    }
