from __future__ import annotations

import os

import pytest

from application.services.social_connectors import MetaGraphSocialAdapter

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_SOCIAL_CONNECTOR_INTEGRATION", "").lower() not in {"1", "true", "yes"},
    reason="Set RUN_SOCIAL_CONNECTOR_INTEGRATION=true to run Meta social connector integration checks.",
)


def test_meta_social_connector_integration_is_config_validation_only_by_default() -> None:
    if os.environ.get("SOCIAL_CONNECTOR_PROVIDER", "").lower() != "meta_graph":
        pytest.skip("SOCIAL_CONNECTOR_PROVIDER must be meta_graph for this integration check.")
    if not os.environ.get("META_GRAPH_ACCESS_TOKEN"):
        pytest.skip("META_GRAPH_ACCESS_TOKEN is required for this integration check.")
    if not (
        os.environ.get("SOCIAL_CONNECTOR_ACCOUNT_ALLOWLIST")
        or os.environ.get("META_GRAPH_PAGE_ID_ALLOWLIST")
        or os.environ.get("META_GRAPH_IG_USER_ID_ALLOWLIST")
    ):
        pytest.skip("A social account allowlist is required for this integration check.")

    adapter = MetaGraphSocialAdapter()

    assert adapter.credentials_configured() is True
    if os.environ.get("SOCIAL_CONNECTOR_ALLOW_PROVIDER_PUBLISH", "").lower() in {
        "1",
        "true",
        "yes",
    }:
        pytest.skip(
            "Real Meta provider publish integration is not implemented in this safe config check."
        )
