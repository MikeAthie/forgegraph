from __future__ import annotations

from copy import deepcopy

from tests.fixtures.deployment_policies import (
    atlas_launch_deployment_policy,
    non_marketing_deployment_policy,
    non_marketing_social_deployment_policy,
)


def atlas_connector_test_deployment_policy() -> dict[str, object]:
    policy = deepcopy(atlas_launch_deployment_policy())
    policy["policy_id"] = "atlas_agency_ops.v1.connector_test_deployment"
    policy["source_policy_id"] = "atlas_agency_ops.v1.connector_test_deployment"
    return policy


def legal_client_notice_delivery_policy() -> dict[str, object]:
    return deepcopy(non_marketing_deployment_policy())


def accounting_statement_delivery_policy() -> dict[str, object]:
    return {
        "policy_id": "accounting_ops.v1.statement_delivery",
        "source_policy_id": "accounting_ops.v1.statement_delivery",
        "pack_id": "accounting_ops.v1",
        "required_whiteboard_status": "in_approval",
        "required_approval_status": "approved",
        "channels": [
            {
                "id": "statement_email",
                "display_name": "Statement Email",
                "department": "accounting-ops",
                "department_name": "Accounting Ops",
                "required_connector": "email_connector",
                "tool_id": "email.send_dry_run",
                "asset_types": ["document"],
                "approval_required": True,
                "allow_dry_run": True,
                "allow_sandbox_evidence": True,
            }
        ],
        "on_blocked": {"route_to_department": "accounting-ops"},
    }


def municipal_public_notice_social_policy() -> dict[str, object]:
    return deepcopy(non_marketing_social_deployment_policy())


def sandbox_evidence_allowed_policy() -> dict[str, object]:
    policy = legal_client_notice_delivery_policy()
    policy["policy_id"] = "connector_contracts.v1.sandbox_allowed"
    policy["source_policy_id"] = "connector_contracts.v1.sandbox_allowed"
    policy["channels"][0]["allow_sandbox_evidence"] = True  # type: ignore[index]
    return policy


def sandbox_evidence_disallowed_policy() -> dict[str, object]:
    policy = legal_client_notice_delivery_policy()
    policy["policy_id"] = "connector_contracts.v1.sandbox_disallowed"
    policy["source_policy_id"] = "connector_contracts.v1.sandbox_disallowed"
    policy["channels"][0]["allow_sandbox_evidence"] = False  # type: ignore[index]
    return policy


def manual_evidence_allowed_policy() -> dict[str, object]:
    policy = municipal_public_notice_social_policy()
    policy["policy_id"] = "connector_contracts.v1.manual_allowed"
    policy["source_policy_id"] = "connector_contracts.v1.manual_allowed"
    policy["channels"][0]["allow_manual_publish_evidence"] = True  # type: ignore[index]
    return policy


def manual_evidence_disallowed_policy() -> dict[str, object]:
    policy = municipal_public_notice_social_policy()
    policy["policy_id"] = "connector_contracts.v1.manual_disallowed"
    policy["source_policy_id"] = "connector_contracts.v1.manual_disallowed"
    policy["channels"][0]["allow_manual_publish_evidence"] = False  # type: ignore[index]
    return policy
