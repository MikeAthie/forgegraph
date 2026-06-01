from __future__ import annotations

from decimal import Decimal
from typing import cast

import pytest

from application.services.company_ops import create_company_signal
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import (
    CompanyOperationObjective,
    CompanySignal,
    Graph,
    GraphVersion,
    InventoryProduct,
    InventoryStockUnit,
    Organization,
    OrganizationMembership,
    User,
)

pytestmark = pytest.mark.django_db


def _create_company(user: User, *, name: str = "Company Ops API Test") -> Graph:
    ensure_default_organization(user)
    organization = user.default_organization
    assert organization is not None
    company = cast(
        Graph,
        Graph.objects.create(
            owner=user,
            organization=organization,
            name=name,
            description="Company ops API test company.",
        ),
    )
    GraphVersion.objects.create(
        graph=company,
        version=1,
        graph_json={"nodes": [], "edges": [], "metadata": {}},
    )
    return company


def _organization(company: Graph) -> Organization:
    organization = company.organization
    assert organization is not None
    return organization


def _create_product(company: Graph) -> InventoryProduct:
    product = InventoryProduct.objects.create(
        organization=_organization(company),
        company=company,
        sku="SKU-1",
        model="Model 1",
        name="Model 1",
        price_amount=Decimal("700.00"),
        cost_amount=Decimal("350.00"),
        price_mxn=Decimal("700.00"),
        cost_mxn=Decimal("350.00"),
    )
    InventoryStockUnit.objects.create(
        organization=_organization(company),
        company=company,
        product=product,
        unit_number=1,
        status="available",
    )
    return product


def test_company_ops_overview_allows_viewer(authenticated_client, user):
    company = _create_company(user)
    OrganizationMembership.objects.filter(
        organization=user.default_organization,
        user=user,
    ).update(role="viewer")

    response = authenticated_client.get(
        "/api/company-ops/overview", {"company_id": str(company.id)}
    )

    assert response.status_code == 200
    assert response.json()["data"]["company_ops"]["summary"]["signals_new"] == 0


def test_company_ops_overview_uses_same_stock_semantics_as_inventory(authenticated_client, user):
    company = _create_company(user)
    for sku, quantity in {"ACTIVE": 3, "LOW": 2, "LAST": 1, "SOLDOUT": 0}.items():
        product = InventoryProduct.objects.create(
            organization=_organization(company),
            company=company,
            sku=sku,
            model=sku,
            name=sku,
            price_amount=Decimal("700.00"),
            cost_amount=Decimal("350.00"),
            price_mxn=Decimal("700.00"),
            cost_mxn=Decimal("350.00"),
        )
        for unit_number in range(1, quantity + 1):
            InventoryStockUnit.objects.create(
                organization=_organization(company),
                company=company,
                product=product,
                unit_number=unit_number,
                status="available",
            )

    inventory_response = authenticated_client.get(
        "/api/inventory/overview", {"company_id": str(company.id)}
    )
    company_ops_response = authenticated_client.get(
        "/api/company-ops/overview", {"company_id": str(company.id)}
    )

    assert inventory_response.status_code == 200
    assert company_ops_response.status_code == 200
    inventory = inventory_response.json()["data"]["inventory"]
    company_ops = company_ops_response.json()["data"]["company_ops"]
    assert company_ops["stock_state_summary"] == inventory["stock_state_summary"]
    assert company_ops["summary"]["low_stock_products"] == 1


def test_company_signal_api_requires_idempotency(authenticated_client, user):
    company = _create_company(user)

    response = authenticated_client.post(
        "/api/company-ops/signals",
        data={"company_id": str(company.id), "signal_type": "demand", "title": "Demand"},
        format="json",
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"


def test_company_signal_api_is_idempotent(authenticated_client, user):
    company = _create_company(user)
    payload = {
        "company_id": str(company.id),
        "signal_type": "demand",
        "source": "manual",
        "external_key": "signal-1",
        "title": "Demand signal",
        "metadata": {
            "customer_email": "buyer@example.com",
            "safe": "visible",
        },
    }

    first = authenticated_client.post(
        "/api/company-ops/signals",
        data=payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY="signal-create",
    )
    second = authenticated_client.post(
        "/api/company-ops/signals",
        data=payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY="signal-create",
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["data"]["duplicate"] is True
    assert first.json()["data"]["signal"]["signal_kind"] == "opportunity"
    assert first.json()["data"]["signal"]["domain_context"] == "general"
    assert first.json()["data"]["signal"]["semantic_aliases"]["signal_type"] == "demand"
    assert CompanySignal.objects.filter(company=company).count() == 1
    assert "buyer@example.com" not in str(first.json()["data"]["signal"]["metadata"])


def test_company_signal_api_accepts_generic_semantic_fields(authenticated_client, user):
    company = _create_company(user)

    response = authenticated_client.post(
        "/api/company-ops/signals",
        data={
            "company_id": str(company.id),
            "signal_type": "manual",
            "signal_kind": "capability_gap",
            "domain_context": "connector",
            "source": "manual",
            "external_key": "gap-1",
            "title": "Connector missing",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="generic-signal-create",
    )

    assert response.status_code == 201
    signal = response.json()["data"]["signal"]
    assert signal["signal_type"] == "manual"
    assert signal["signal_kind"] == "capability_gap"
    assert signal["domain_context"] == "connector"


def test_company_signal_qualify_creates_opportunity(authenticated_client, user):
    company = _create_company(user)
    signal = create_company_signal(
        company=company,
        actor=user,
        signal_type="lead",
        source="manual",
        external_key="lead-1",
        title="Lead",
    )

    response = authenticated_client.post(
        f"/api/company-ops/signals/{signal.id}/qualify",
        data={"next_action": "Follow up"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="qualify-lead",
    )

    assert response.status_code == 200
    assert response.json()["data"]["opportunity"]["signal_id"] == str(signal.id)


def test_company_ops_tenant_isolation_blocks_cross_company_signal(authenticated_client, user):
    other_user = User.objects.create_user(email="other-company@example.com", password="pw")
    other_company = _create_company(other_user, name="Other Company")
    signal = create_company_signal(
        company=other_company,
        actor=other_user,
        signal_type="manual",
        source="manual",
        external_key="other-signal",
        title="Other tenant signal",
    )

    response = authenticated_client.post(
        f"/api/company-ops/signals/{signal.id}/qualify",
        data={},
        format="json",
        HTTP_IDEMPOTENCY_KEY="cross-tenant",
    )

    assert response.status_code == 404


def test_publication_and_procurement_approval_requests_create_human_gates(
    authenticated_client, user
):
    company = _create_company(user)
    product = _create_product(company)
    pub = authenticated_client.post(
        "/api/company-ops/publication-drafts",
        data={
            "company_id": str(company.id),
            "title": "Content draft",
            "channel": "manual",
            "body": "Draft body",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="pub-create",
    )
    procurement = authenticated_client.post(
        "/api/company-ops/procurement-drafts",
        data={
            "company_id": str(company.id),
            "title": "Procurement draft",
            "budget_amount": "1000.00",
            "lines": [
                {
                    "product_id": str(product.id),
                    "quantity": 2,
                    "unit_cost_amount": "100.00",
                }
            ],
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="proc-create",
    )

    pub_approval = authenticated_client.post(
        f"/api/company-ops/publication-drafts/{pub.json()['data']['publication_draft']['id']}/request-approval",
        data={"note": "review"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="pub-approval",
    )
    proc_approval = authenticated_client.post(
        f"/api/company-ops/procurement-drafts/{procurement.json()['data']['procurement_draft']['id']}/request-approval",
        data={"note": "review"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="proc-approval",
    )

    assert pub.status_code == 201
    assert procurement.status_code == 201
    assert pub_approval.status_code == 200
    assert proc_approval.status_code == 200
    assert pub_approval.json()["data"]["publication_draft"]["status"] == "approval_requested"
    assert proc_approval.json()["data"]["procurement_draft"]["status"] == "approval_requested"


def test_company_operation_launch_api_creates_inspectable_operation(authenticated_client, user):
    company = _create_company(user)

    response = authenticated_client.post(
        "/api/company-ops/operations",
        data={
            "company_id": str(company.id),
            "operation_type": "daily_operating_brief",
            "operation_family": "brief",
            "domain_context": "general",
            "context_note": "Daily loop",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="launch-daily",
    )

    assert response.status_code == 201
    operation = response.json()["data"]["operation"]
    assert operation["operation_type"] == "daily_operating_brief"
    assert operation["operation_family"] == "brief"
    assert operation["domain_context"] == "general"
    assert operation["context_pack_id"]
    assert operation["objective_contract_id"]
    assert operation["objective_contract"]["run_type"] == "rehearsal"
    assert operation["objective_contract"]["operation_family"] == "brief"


def test_company_operation_objective_evaluation_api_records_result(authenticated_client, user):
    company = _create_company(user)
    launch = authenticated_client.post(
        "/api/company-ops/operations",
        data={
            "company_id": str(company.id),
            "operation_type": "daily_operating_brief",
            "run_goal": "Rehearse company next-action learning.",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="launch-objective",
    )
    operation_id = launch.json()["data"]["operation"]["id"]

    response = authenticated_client.post(
        f"/api/company-ops/operations/{operation_id}/objective-evaluation",
        data={
            "success_score": 91,
            "miss_analysis": "No miss; rehearsal produced the next action.",
            "next_decision": "Run the first content-drop rehearsal.",
            "integrity_gates": {
                "state_drift": {"observed": 0, "status": "pass"},
            },
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="objective-eval",
    )

    assert response.status_code == 200
    objective = response.json()["data"]["objective_contract"]
    assert objective["success_score"] == 91
    assert objective["status"] == "evaluated"
    assert CompanyOperationObjective.objects.get(operation_id=operation_id).success_score == 91
