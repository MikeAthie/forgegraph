from __future__ import annotations

import os

import pytest

from application.services.social_connectors import SocialPublishRequest, dry_run_social_publish
from tests.helpers.connector_contracts import assert_success_receipt_contract


def test_meta_social_connector_integration_is_opt_in_and_does_not_publish_by_default() -> None:
    if os.environ.get("RUN_SOCIAL_CONNECTOR_INTEGRATION", "").lower() != "true":
        pytest.skip(
            "Set RUN_SOCIAL_CONNECTOR_INTEGRATION=true to enable Meta social connector integration checks."
        )
    if os.environ.get("SOCIAL_CONNECTOR_PROVIDER", "").lower() != "meta_graph":
        pytest.skip(
            "Set SOCIAL_CONNECTOR_PROVIDER=meta_graph for Meta social connector integration checks."
        )
    if not os.environ.get("META_GRAPH_ACCESS_TOKEN"):
        pytest.skip("Set META_GRAPH_ACCESS_TOKEN for Meta social connector integration checks.")
    account = (
        os.environ.get("META_GRAPH_PAGE_ID_ALLOWLIST")
        or os.environ.get("META_GRAPH_IG_USER_ID_ALLOWLIST")
        or os.environ.get("SOCIAL_CONNECTOR_ACCOUNT_ALLOWLIST")
    )
    if not account:
        pytest.skip("Set a Meta account/page allowlist for social connector integration checks.")

    receipt = dry_run_social_publish(
        SocialPublishRequest(
            provider="meta_graph",
            platform="configured_platform",
            mode="dry_run",
            account_id=account.split(",")[0].strip(),
            asset_ids=["integration-dry-run-asset"],
            caption="Local dry run. No social provider publish is performed by this test.",
            idempotency_key="meta-social-integration-dry-run",
            asset_approved=True,
            caption_approved=True,
        )
    ).as_dict()

    assert_success_receipt_contract(receipt, expected_evidence_mode="sandbox")
    if os.environ.get("SOCIAL_CONNECTOR_ALLOW_PROVIDER_PUBLISH", "").lower() == "true":
        pytest.skip(
            "Real social publishes are intentionally excluded from the default integration test."
        )
