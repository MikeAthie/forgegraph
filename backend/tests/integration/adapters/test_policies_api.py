from django.test import override_settings
from rest_framework import status

from infrastructure.orm.models import TenantPolicy


@override_settings(
    FORGEGRAPH_RUNTIME_MODE="cloud",
    FF_CURATED_MEMORY_ENABLED=True,
    FF_CURATED_MEMORY_VECTOR_INDEXING=False,
)
def test_policy_api_returns_operator_summary(authenticated_client, user):
    TenantPolicy.objects.create(
        tenant_id=user.default_organization_id,
        http_allowlist=["api.openai.com"],
        http_denylist=["example.com"],
        http_default_deny=True,
        allowed_providers=["openai"],
        allowed_models=["gpt-5"],
    )

    response = authenticated_client.get("/api/policies/guardrails")

    assert response.status_code == status.HTTP_200_OK
    payload = response.data["data"]
    assert payload["http_default_deny"] is True
    assert payload["allowed_providers"] == ["openai"]
    assert payload["allowed_models"] == ["gpt-5"]
    assert payload["summary"] == {
        "runtime_mode": "cloud",
        "http_access_mode": "default_deny",
        "egress_allowlist_count": 1,
        "egress_denylist_count": 1,
        "provider_allowlist_count": 1,
        "model_allowlist_count": 1,
        "exec_tools_policy": "restricted_in_cloud",
        "curated_memory_enabled": True,
        "curated_memory_vector_indexing_enabled": False,
    }


@override_settings(FORGEGRAPH_RUNTIME_MODE="self_hosted")
def test_policy_api_returns_default_summary_when_no_policy_exists(authenticated_client):
    response = authenticated_client.get("/api/policies/guardrails")

    assert response.status_code == status.HTTP_200_OK
    payload = response.data["data"]
    assert payload["http_allowlist"] == []
    assert payload["summary"]["runtime_mode"] == "self_hosted"
    assert payload["summary"]["http_access_mode"] == "open"
    assert payload["summary"]["exec_tools_policy"] == "package_and_policy_controlled"
