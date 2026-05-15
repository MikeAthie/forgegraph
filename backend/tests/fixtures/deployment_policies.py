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
                "required_connector": "email_service_connector",
                "tool_id": "dmp.email_draft_send_schedule",
                "asset_types": ["asset", "publication_draft"],
                "approval_required": True,
                "allow_dry_run": True,
                "risk_level": "medium",
            },
            {
                "id": "whatsapp",
                "display_name": "WhatsApp",
                "department": "conversational-commerce",
                "department_name": "Conversational Commerce",
                "required_connector": "whatsapp_business_connector",
                "tool_id": "messaging.whatsapp_template_send",
                "asset_types": ["publication_draft"],
                "approval_required": True,
                "allow_dry_run": False,
                "risk_level": "high",
            },
            {
                "id": "instagram",
                "display_name": "Instagram",
                "department": "social",
                "department_name": "Social",
                "required_connector": "instagram_publishing_connector",
                "tool_id": "social.instagram_publish",
                "asset_types": ["publication_draft"],
                "approval_required": True,
                "allow_dry_run": False,
                "risk_level": "high",
            },
            {
                "id": "facebook",
                "display_name": "Facebook",
                "department": "social",
                "department_name": "Social",
                "required_connector": "facebook_publishing_connector",
                "tool_id": "social.facebook_publish",
                "asset_types": ["publication_draft"],
                "approval_required": True,
                "allow_dry_run": False,
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
        "policy_id": "legal_ops.v1.contract_delivery",
        "source_policy_id": "legal_ops.v1.contract_delivery",
        "pack_id": "legal_ops.v1",
        "required_whiteboard_status": WorkWhiteboard.STATUS_IN_APPROVAL,
        "required_approval_status": "approved",
        "channels": [
            {
                "id": "client_portal",
                "display_name": "Client Portal",
                "department": "legal-ops",
                "department_name": "Legal Ops",
                "required_connector": "",
                "tool_id": "",
                "asset_types": ["document"],
                "approval_required": True,
                "allow_dry_run": False,
            }
        ],
        "on_blocked": {"route_to_department": "legal-ops"},
    }
