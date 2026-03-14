import pytest
from rest_framework import status

from infrastructure.orm.models import BillingPlan, Graph, GraphVersion, TenantSubscription

pytestmark = pytest.mark.django_db


def test_entitlement_blocks_run_start(authenticated_client, user):
    graph = Graph.objects.create(owner=user, name="Billing Graph")
    version = GraphVersion.objects.create(
        graph=graph, version=1, graph_json={"nodes": [], "edges": []}
    )

    plan = BillingPlan.objects.create(
        name="Starter",
        stripe_price_id="price_test",
        entitlements={"max_runs_per_month": 0},
    )
    TenantSubscription.objects.create(
        tenant_id=user.default_organization_id,
        plan=plan,
        status="active",
    )

    response = authenticated_client.post(
        "/api/runs/start",
        {"graph_version_id": str(version.id), "input_json": {}},
        format="json",
    )

    assert response.status_code == status.HTTP_402_PAYMENT_REQUIRED
    assert response.data["error"]["code"] == "ENTITLEMENT_LIMIT"
    assert response.data["error"]["details"][0]["reason"] == "plan_entitlement"
    assert response.data["error"]["details"][0]["scope"] == "plan_monthly_runs"
