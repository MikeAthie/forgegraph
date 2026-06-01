from __future__ import annotations

from infrastructure.orm.models import WorkWhiteboard

ATLAS_DEPLOYMENT_POLICY_ID = "atlas_agency_ops.v1.launch_deployment"


def atlas_launch_deployment_policy() -> dict[str, object]:
    """ATLAS launch deployment policy as fixture data, not ForgeGraph core logic."""

    return {
        "policy_id": ATLAS_DEPLOYMENT_POLICY_ID,
        "source_policy_id": ATLAS_DEPLOYMENT_POLICY_ID,
        "pack_id": "atlas_agency_ops.v1",
        "required_whiteboard_status": WorkWhiteboard.STATUS_IN_APPROVAL,
        "required_approval_status": "approved",
        "channels": [
            {
                "id": "email",
                "display_name": "Email",
                "department": "crm",
                "department_name": "CRM",
                "required_connector": "email_connector",
                "tool_id": "email.send_dry_run",
                "asset_types": ["asset", "publication_draft"],
                "approval_required": True,
                "allow_dry_run": True,
                "allow_sandbox_evidence": True,
                "requires_unsubscribe_footer": True,
                "risk_level": "medium",
            },
            {
                "id": "whatsapp",
                "display_name": "WhatsApp",
                "department": "conversational-commerce",
                "department_name": "Conversational Commerce",
                "required_connector": "whatsapp_connector",
                "tool_id": "whatsapp.send_dry_run",
                "asset_types": ["publication_draft"],
                "approval_required": True,
                "allow_dry_run": True,
                "allow_sandbox_evidence": True,
                "allow_web_automation_evidence": False,
                "operator_confirmation_required": True,
                "risk_level": "high",
                "metadata": {
                    "provider_strategy": "experimental_manual_web_automation_optional",
                },
            },
            {
                "id": "instagram",
                "display_name": "Instagram",
                "department": "social",
                "department_name": "Social",
                "required_connector": "social_connector",
                "tool_id": "social.publish_dry_run",
                "platform": "instagram",
                "asset_types": ["publication_draft"],
                "approval_required": True,
                "allow_dry_run": True,
                "allow_sandbox_evidence": True,
                "allow_manual_publish_evidence": False,
                "allow_provider_publish": False,
                "requires_compliance_gate": True,
                "requires_originality_check": True,
                "risk_level": "high",
            },
            {
                "id": "facebook",
                "display_name": "Facebook",
                "department": "social",
                "department_name": "Social",
                "required_connector": "social_connector",
                "tool_id": "social.publish_dry_run",
                "platform": "facebook",
                "asset_types": ["publication_draft"],
                "approval_required": True,
                "allow_dry_run": True,
                "allow_sandbox_evidence": True,
                "allow_manual_publish_evidence": False,
                "allow_provider_publish": False,
                "requires_compliance_gate": True,
                "requires_originality_check": True,
                "risk_level": "high",
            },
            {
                "id": "tiktok",
                "display_name": "TikTok",
                "department": "social",
                "department_name": "Social",
                "required_connector": "tiktok_publishing_connector",
                "tool_id": "social.tiktok_publish",
                "asset_types": ["publication_draft"],
                "approval_required": True,
                "allow_dry_run": False,
                "risk_level": "high",
            },
            {
                "id": "landing_page",
                "display_name": "Landing Page",
                "department": "web",
                "department_name": "Web",
                "required_connector": "cms_landing_page_connector",
                "tool_id": "cms.landing_page_publish",
                "asset_types": ["asset", "publication_draft"],
                "approval_required": True,
                "allow_dry_run": False,
                "risk_level": "high",
            },
        ],
        "on_blocked": {
            "route_to_department": "deployment-ops",
        },
    }


def non_marketing_deployment_policy() -> dict[str, object]:
    return {
        "policy_id": "legal_ops.v1.client_notice_delivery",
        "source_policy_id": "legal_ops.v1.client_notice_delivery",
        "pack_id": "legal_ops.v1",
        "required_whiteboard_status": WorkWhiteboard.STATUS_IN_APPROVAL,
        "required_approval_status": "approved",
        "channels": [
            {
                "id": "client_notice_email",
                "display_name": "Client Notice Email",
                "department": "legal-ops",
                "department_name": "Legal Ops",
                "required_connector": "email_connector",
                "tool_id": "email.send_dry_run",
                "asset_types": ["document"],
                "approval_required": True,
                "allow_dry_run": True,
                "allow_sandbox_evidence": True,
            }
        ],
        "on_blocked": {"route_to_department": "legal-ops"},
    }


def non_marketing_messaging_deployment_policy() -> dict[str, object]:
    return {
        "policy_id": "legal_ops.v1.client_notice_messaging",
        "source_policy_id": "legal_ops.v1.client_notice_messaging",
        "pack_id": "legal_ops.v1",
        "required_whiteboard_status": WorkWhiteboard.STATUS_IN_APPROVAL,
        "required_approval_status": "approved",
        "channels": [
            {
                "id": "client_notice_message",
                "display_name": "Client Notice Message",
                "department": "legal-ops",
                "department_name": "Legal Ops",
                "required_connector": "whatsapp_connector",
                "tool_id": "whatsapp.send_dry_run",
                "asset_types": ["document"],
                "approval_required": True,
                "allow_dry_run": True,
                "allow_sandbox_evidence": True,
            }
        ],
        "on_blocked": {"route_to_department": "legal-ops"},
    }


def non_marketing_social_deployment_policy() -> dict[str, object]:
    return {
        "policy_id": "municipal_ops.v1.community_notice_social_publish",
        "source_policy_id": "municipal_ops.v1.community_notice_social_publish",
        "pack_id": "municipal_ops.v1",
        "required_whiteboard_status": WorkWhiteboard.STATUS_IN_APPROVAL,
        "required_approval_status": "approved",
        "channels": [
            {
                "id": "community_notice_social",
                "display_name": "Community Notice Social",
                "department": "public-communications",
                "department_name": "Public Communications",
                "required_connector": "social_connector",
                "tool_id": "social.publish_dry_run",
                "platform": "community_notice",
                "asset_types": ["document"],
                "approval_required": True,
                "allow_dry_run": True,
                "allow_sandbox_evidence": True,
                "allow_manual_publish_evidence": True,
                "allow_provider_publish": False,
            }
        ],
        "on_blocked": {"route_to_department": "public-communications"},
    }
