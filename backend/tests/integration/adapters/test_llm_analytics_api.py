from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework import status

from infrastructure.orm.models import Graph, GraphVersion, LLMBudget, LLMQuota, LLMUsage, Run

pytestmark = pytest.mark.django_db


def _create_run(user):
    graph = Graph.objects.create(owner=user, name="Analytics Graph")
    version = GraphVersion.objects.create(
        graph=graph,
        version=1,
        graph_json={"nodes": [], "edges": []},
    )
    return Run.objects.create(
        owner=user,
        graph_version=version,
        status="succeeded",
        started_at=timezone.now(),
        ended_at=timezone.now(),
    )


def test_llm_export_supports_costs_budget_and_quota_datasets(authenticated_client, user):
    run = _create_run(user)
    LLMUsage.objects.create(
        tenant_id=user.default_organization_id,
        run=run,
        node_id="prompt-1",
        provider="openai",
        model="gpt-4.1-mini",
        prompt_tokens=120,
        completion_tokens=30,
        total_tokens=150,
        cost_usd=Decimal("1.25"),
    )
    LLMBudget.objects.create(
        tenant_id=user.default_organization_id,
        monthly_limit_usd=Decimal("20.00"),
        warning_threshold_pct=Decimal("0.80"),
    )
    LLMQuota.objects.create(
        tenant_id=user.default_organization_id,
        monthly_token_limit=1000,
        monthly_cost_limit_usd=Decimal("25.00"),
    )

    costs_response = authenticated_client.get(
        "/api/analytics/llm/export",
        {"dataset": "costs", "format": "json", "period": "30d"},
    )
    assert costs_response.status_code == status.HTTP_200_OK
    costs_payload = costs_response.data["data"]
    assert costs_payload["dataset"] == "costs"
    assert costs_payload["rows"][0]["provider"] == "openai"
    assert costs_payload["rows"][0]["model"] == "gpt-4.1-mini"
    assert costs_payload["rows"][0]["cost_usd"] == 1.25

    budget_response = authenticated_client.get(
        "/api/analytics/llm/export",
        {"dataset": "budget", "format": "json", "period": "30d"},
    )
    assert budget_response.status_code == status.HTTP_200_OK
    budget_payload = budget_response.data["data"]
    assert budget_payload["dataset"] == "budget"
    assert budget_payload["budget"]["monthly_limit_usd"] == 20.0
    assert budget_payload["usage"]["month_cost_usd"] == 1.25

    quota_response = authenticated_client.get(
        "/api/analytics/llm/export",
        {"dataset": "quota", "export_format": "csv", "period": "30d"},
    )
    assert quota_response.status_code == status.HTTP_200_OK
    assert quota_response["Content-Type"].startswith("text/csv")
    body = quota_response.content.decode()
    assert "monthly_token_limit" in body
    assert "1000" in body


def test_llm_quota_view_returns_usage_and_limits(authenticated_client, user):
    run = _create_run(user)
    LLMUsage.objects.create(
        tenant_id=user.default_organization_id,
        run=run,
        node_id="prompt-1",
        provider="anthropic",
        model="claude-3-5-sonnet",
        prompt_tokens=300,
        completion_tokens=75,
        total_tokens=375,
        cost_usd=Decimal("2.50"),
    )
    LLMQuota.objects.create(
        tenant_id=user.default_organization_id,
        monthly_token_limit=5000,
        monthly_cost_limit_usd=Decimal("40.00"),
    )

    response = authenticated_client.get("/api/analytics/llm/quota")

    assert response.status_code == status.HTTP_200_OK
    payload = response.data["data"]
    assert payload["quota"]["monthly_token_limit"] == 5000
    assert payload["quota"]["monthly_cost_limit_usd"] == 40.0
    assert payload["usage"]["month_total_tokens"] == 375
    assert payload["usage"]["month_cost_usd"] == 2.5
