"""Backend invariants for Organization -> Company -> PackInstallation -> generic primitives."""

from __future__ import annotations

from datetime import date
from typing import Any, cast
from uuid import uuid4

import pytest
from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.urls import URLPattern, URLResolver, get_resolver
from rest_framework.test import APIClient

from application.services import operating_model_packs
from application.services.operating_model_packs import (
    OperatingModelPackError,
    install_pack_for_company,
)
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import (
    Asset,
    CompanyAccessPolicy,
    CompanyAssignment,
    CompanyOperatingModelInstallation,
    Graph,
    MetricSnapshot,
    Organization,
    OrganizationMembership,
    PackNamespaceClaim,
    PeriodicReviewDefinition,
    ReportRun,
    StateProjection,
    User,
)

pytestmark = pytest.mark.django_db

FUNCTION_COMPANY_NAMES = {
    "Legacy Marketing",
    "Legacy Accounting",
    "Legacy Legal",
    "Legacy Consulting",
}


def _operator_org(user: User) -> Organization:
    organization = user.default_organization
    assert organization is not None
    organization.name = "ATLAS Test Operator Org"
    organization.save(update_fields=["name"])
    return organization


def _company(user: User, name: str = "Legacy Eyewear") -> Graph:
    organization = _operator_org(user)
    return cast(
        Graph,
        Graph.objects.create(
            owner=user,
            organization=organization,
            name=name,
            description="Legacy Eyewear customer company.",
        ),
    )


def _member_in_org(owner: User, *, role: str = "viewer") -> User:
    organization = _operator_org(owner)
    member = User.objects.create_user(
        email=f"product-mode-member-{uuid4().hex}@example.com",
        password="testpassword123",
    )
    ensure_default_organization(member)
    member.default_organization = organization
    member.save(update_fields=["default_organization"])
    OrganizationMembership.objects.update_or_create(
        organization=organization,
        user=member,
        defaults={"role": role, "is_default": True},
    )
    return member


def _restrict_company(company: Graph) -> None:
    CompanyAccessPolicy.objects.update_or_create(
        company=company,
        defaults={
            "organization": company.organization,
            "assignment_required": True,
            "org_admin_access_enabled": False,
        },
    )


def _assign_company(owner: User, company: Graph, member: User, *, role: str) -> None:
    CompanyAssignment.objects.update_or_create(
        organization=company.organization,
        company=company,
        user=member,
        defaults={"role": role, "status": "active", "created_by": owner},
    )


def _install_pack(
    client: APIClient,
    company: Graph,
    *,
    pack_id: str,
    role: str,
    key: str,
) -> dict[str, Any]:
    response = client.post(
        f"/api/companies/{company.id}/packs/install",
        data={
            "pack_id": pack_id,
            "role": role,
            "config": {"skip_graph_version": True, "selected_services": ["Operations"]},
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY=key,
    )
    assert response.status_code == 201, response.json()
    return cast(dict[str, Any], response.json()["data"]["installation"])


def _seed_company_history(owner: User, company: Graph) -> dict[str, Any]:
    organization = company.organization
    assert organization is not None
    artifact = Asset.objects.create(
        organization=organization,
        company=company,
        title="Legacy operating summary",
        asset_type="deliverable",
        created_by_type="system",
        metadata_json={"artifact_type": "operating_summary"},
    )
    review = PeriodicReviewDefinition.objects.create(
        organization=organization,
        company=company,
        pack_id="digital_marketing_pro.v1",
        template_id=f"monthly-review-{uuid4().hex}",
        display_name="Monthly operating review",
        cadence="monthly",
        report_template_id="legacy_monthly_report.v1",
        history_projection_type="client_service_history",
        created_by=owner,
    )
    snapshot = MetricSnapshot.objects.create(
        organization=organization,
        company=company,
        review_definition=review,
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 31),
        source_type="seed",
        metric_values_json={"stock_units_available": 62, "low_stock_products": 3},
        created_by=owner,
    )
    report = ReportRun.objects.create(
        organization=organization,
        company=company,
        review_definition=review,
        metric_snapshot=snapshot,
        artifact=artifact,
        report_template_id="legacy_monthly_report.v1",
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 31),
        generated_sections_json={"summary": "Legacy Eyewear monthly operating history."},
        created_by=owner,
    )
    projection = StateProjection.objects.create(
        organization=organization,
        company=company,
        projection_type="client_service_history",
        display_label="Service history",
        json_state={
            "company_name": "Legacy Eyewear",
            "entries": [{"report_run_id": str(report.id), "artifact_id": str(artifact.id)}],
        },
        markdown_summary="Legacy Eyewear service history.",
    )
    return {
        "artifact": artifact,
        "review": review,
        "snapshot": snapshot,
        "report": report,
        "projection": projection,
    }


def _assert_no_marketing_specific_shape(payload: Any) -> None:
    serialized = str(payload).lower()
    assert "/api/marketing/" not in serialized
    assert "marketing_company" not in serialized
    assert "marketingmodel" not in serialized


def test_legacy_can_be_one_company_with_multiple_pack_installations(authenticated_client, user):
    company = _company(user)

    primary = _install_pack(
        authenticated_client,
        company,
        pack_id="digital_marketing_pro.v1",
        role="primary",
        key="product-mode-primary-pack",
    )
    addon = _install_pack(
        authenticated_client,
        company,
        pack_id="legal_ops_demo.v1",
        role="addon",
        key="product-mode-legal-addon",
    )

    assert Graph.objects.filter(name="Legacy Eyewear").count() == 1
    assert not Graph.objects.filter(name__in=FUNCTION_COMPANY_NAMES).exists()
    assert primary["role"] == "primary"
    assert addon["role"] == "addon"

    installations = CompanyOperatingModelInstallation.objects.filter(company=company)
    assert {item.company_id for item in installations} == {company.id}
    assert installations.filter(role="primary", status="active").count() == 1
    assert installations.filter(role="addon", status="active").count() >= 1

    model_response = authenticated_client.get(f"/api/companies/{company.id}/operating-model")
    assert model_response.status_code == 200
    model = model_response.json()["data"]["operating_model"]
    assert model["company_id"] == str(company.id)
    assert {pack["company_id"] for pack in model["installed_packs"]} == {str(company.id)}


def test_pack_defined_objects_are_exposed_with_pack_namespaced_ids(authenticated_client, user):
    company = _company(user)
    installation = _install_pack(
        authenticated_client,
        company,
        pack_id="digital_marketing_pro.v1",
        role="primary",
        key="product-mode-namespaced-pack",
    )

    objects_response = authenticated_client.get(
        f"/api/companies/{company.id}/packs/{installation['id']}/objects"
    )

    assert objects_response.status_code == 200
    objects = objects_response.json()["data"]["objects"]
    assert objects
    for item in objects:
        assert item["company_id"] == str(company.id)
        assert item["pack_id"] == "digital_marketing_pro.v1"
        assert item["namespaced_id"].startswith("digital_marketing_pro.v1.")


def test_pack_namespace_claim_validation_rejects_invalid_namespaced_ids(
    authenticated_client,
    user,
):
    company = _company(user)
    installation = _install_pack(
        authenticated_client,
        company,
        pack_id="digital_marketing_pro.v1",
        role="primary",
        key="product-mode-invalid-namespace-pack",
    )
    valid_claim = PackNamespaceClaim(
        organization=company.organization,
        company=company,
        installation_id=installation["id"],
        pack_id="digital_marketing_pro.v1",
        object_type="program_template",
        object_id="campaign_brief",
        namespaced_id="digital_marketing_pro.v1.campaign_brief",
        status="active",
    )
    valid_claim.full_clean()

    un_namespaced_claim = PackNamespaceClaim(
        organization=company.organization,
        company=company,
        installation_id=installation["id"],
        pack_id="digital_marketing_pro.v1",
        object_type="program_template",
        object_id="dmp.engagement",
        namespaced_id="dmp.engagement",
        status="active",
    )
    wrong_pack_claim = PackNamespaceClaim(
        organization=company.organization,
        company=company,
        installation_id=installation["id"],
        pack_id="digital_marketing_pro.v1",
        object_type="program_template",
        object_id="campaign_brief",
        namespaced_id="accounting_ops.v1.campaign_brief",
        status="active",
    )

    with pytest.raises(ValidationError, match="owning pack id plus a dot"):
        un_namespaced_claim.full_clean()

    with pytest.raises(ValidationError, match="owning pack id plus a dot"):
        wrong_pack_claim.full_clean()

    existing_claim = PackNamespaceClaim.objects.filter(
        company=company,
        status="active",
    ).first()
    assert existing_claim is not None
    with pytest.raises(IntegrityError):
        PackNamespaceClaim.objects.create(
            organization=company.organization,
            company=company,
            installation_id=installation["id"],
            pack_id=existing_claim.pack_id,
            object_type=existing_claim.object_type,
            object_id=existing_claim.object_id,
            namespaced_id=existing_claim.namespaced_id,
            status="active",
        )


def test_pack_install_service_rejects_invalid_namespace_claims(monkeypatch, user):
    company = _company(user)

    def invalid_claims(_definition):
        return [
            {
                "object_type": "program_template",
                "object_id": "campaign_brief",
                "namespaced_id": "campaign_brief",
            }
        ]

    monkeypatch.setattr(operating_model_packs, "_pack_namespace_claims", invalid_claims)

    with pytest.raises(OperatingModelPackError, match="owning pack id plus a dot"):
        install_pack_for_company(
            company=company,
            user=user,
            pack_id="digital_marketing_pro.v1",
            config={"skip_graph_version": True},
            role="primary",
        )

    assert not PackNamespaceClaim.objects.filter(
        company=company,
        namespaced_id="campaign_brief",
    ).exists()


def test_generic_artifacts_reports_and_history_are_company_scoped(api_client, user):
    legacy_company = _company(user)
    other_company = _company(user, "Other Client")
    _seed_company_history(user, legacy_company)
    _seed_company_history(user, other_company)
    legacy_member = _member_in_org(user, role="viewer")
    other_member = _member_in_org(user, role="viewer")
    for company in [legacy_company, other_company]:
        _restrict_company(company)
    _assign_company(user, legacy_company, legacy_member, role="viewer")
    _assign_company(user, other_company, other_member, role="viewer")

    api_client.force_authenticate(user=legacy_member)
    artifacts = api_client.get("/api/work-artifacts", {"company_id": str(legacy_company.id)})
    reports = api_client.get("/api/report-runs", {"company_id": str(legacy_company.id)})
    history = api_client.get(
        "/api/state-projections",
        {"company_id": str(legacy_company.id), "projection_type": "client_service_history"},
    )
    other_artifacts = api_client.get("/api/work-artifacts", {"company_id": str(other_company.id)})

    assert artifacts.status_code == 200
    assert reports.status_code == 200
    assert history.status_code == 200
    assert other_artifacts.status_code == 404
    assert {item["company_id"] for item in artifacts.json()["data"]["artifacts"]} == {
        str(legacy_company.id)
    }
    assert {item["company_id"] for item in reports.json()["data"]["report_runs"]} == {
        str(legacy_company.id)
    }
    assert {item["company_id"] for item in history.json()["data"]["state_projections"]} == {
        str(legacy_company.id)
    }

    api_client.force_authenticate(user=other_member)
    blocked_history = api_client.get(
        "/api/state-projections",
        {"company_id": str(legacy_company.id), "projection_type": "client_service_history"},
    )
    assert blocked_history.status_code == 404
    _assert_no_marketing_specific_shape(artifacts.json())
    _assert_no_marketing_specific_shape(reports.json())
    _assert_no_marketing_specific_shape(history.json())


def test_customer_cannot_read_internal_pack_config_references(api_client, user):
    company = _company(user)
    api_client.force_authenticate(user=user)
    installation_payload = _install_pack(
        api_client,
        company,
        pack_id="digital_marketing_pro.v1",
        role="primary",
        key="product-mode-private-config-pack",
    )
    installation = CompanyOperatingModelInstallation.objects.get(id=installation_payload["id"])
    installation.private_config_ref = "vault://product-mode/private-config"
    installation.save(update_fields=["private_config_ref", "updated_at"])
    _restrict_company(company)
    _assign_company(user, company, user, role="admin")
    customer = _member_in_org(user, role="viewer")
    _assign_company(user, company, customer, role="viewer")

    api_client.force_authenticate(user=user)
    operator_response = api_client.get(f"/api/companies/{company.id}/packs/{installation.id}")
    assert operator_response.status_code == 200
    assert operator_response.json()["data"]["installation"]["public_config"]

    api_client.force_authenticate(user=customer)
    customer_response = api_client.get(f"/api/companies/{company.id}/packs/{installation.id}")
    assert customer_response.status_code == 200
    serialized = str(customer_response.json())
    assert "vault://product-mode/private-config" not in serialized
    assert "private_config_ref" not in serialized


def test_non_admin_capability_actor_cannot_mutate_another_pack_config(api_client, user):
    company = _company(user)
    api_client.force_authenticate(user=user)
    first = _install_pack(
        api_client,
        company,
        pack_id="digital_marketing_pro.v1",
        role="primary",
        key="product-mode-pack-a",
    )
    second = _install_pack(
        api_client,
        company,
        pack_id="legal_ops_demo.v1",
        role="addon",
        key="product-mode-pack-b",
    )
    _restrict_company(company)
    member = _member_in_org(user, role="member")
    _assign_company(user, company, member, role="member")
    target = CompanyOperatingModelInstallation.objects.get(id=second["id"])

    api_client.force_authenticate(user=member)
    response = api_client.patch(
        f"/api/companies/{company.id}/packs/{target.id}",
        data={
            "config": {
                "source_pack_id": first["pack_id"],
                "attempted_private_write": "blocked",
            }
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="product-mode-cross-pack-config-write",
    )

    assert response.status_code == 403
    target.refresh_from_db()
    assert "attempted_private_write" not in target.config_json


def test_archived_pack_is_not_active_but_company_history_remains_readable(
    authenticated_client,
    user,
):
    company = _company(user)
    _install_pack(
        authenticated_client,
        company,
        pack_id="digital_marketing_pro.v1",
        role="primary",
        key="product-mode-archive-primary",
    )
    addon = _install_pack(
        authenticated_client,
        company,
        pack_id="legal_ops_demo.v1",
        role="addon",
        key="product-mode-archive-addon",
    )
    _seed_company_history(user, company)

    archive_response = authenticated_client.post(
        f"/api/companies/{company.id}/packs/{addon['id']}/archive",
        data={"reason": "product-mode invariant"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="product-mode-archive-addon-command",
    )

    assert archive_response.status_code == 200
    assert archive_response.json()["data"]["installation"]["status"] == "archived"
    assert not CompanyOperatingModelInstallation.objects.filter(
        id=addon["id"],
        status="active",
    ).exists()
    assert not PackNamespaceClaim.objects.filter(
        installation_id=addon["id"],
        status="active",
    ).exists()

    artifacts = authenticated_client.get("/api/work-artifacts", {"company_id": str(company.id)})
    reports = authenticated_client.get("/api/report-runs", {"company_id": str(company.id)})
    history = authenticated_client.get(
        "/api/state-projections",
        {"company_id": str(company.id), "projection_type": "client_service_history"},
    )
    assert artifacts.status_code == 200
    assert artifacts.json()["data"]["artifacts"]
    assert reports.status_code == 200
    assert reports.json()["data"]["report_runs"]
    assert history.status_code == 200
    assert history.json()["data"]["state_projections"]


def test_product_mode_routes_and_models_remain_generic():
    paths: set[str] = set()

    def walk(patterns: list[URLPattern | URLResolver], prefix: str = "") -> None:
        for pattern in patterns:
            route_part = str(pattern.pattern)
            if isinstance(pattern, URLResolver):
                walk(pattern.url_patterns, prefix + route_part)
                continue
            paths.add(("/" + prefix + route_part).replace("//", "/"))

    walk(get_resolver().url_patterns)
    marketing_routes = [
        path for path in paths if path.startswith("/api/marketing/") or path == "/api/marketing"
    ]
    marketing_models = [
        model.__name__ for model in apps.get_models() if model.__name__.startswith("Marketing")
    ]

    assert marketing_routes == []
    assert marketing_models == []
