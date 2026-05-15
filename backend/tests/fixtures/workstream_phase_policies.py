from __future__ import annotations

from infrastructure.orm.models import WorkWhiteboard

ATLAS_CONTENT_PHASE_ID = "atlas_agency_ops.v1.content_production"


def atlas_content_production_policy() -> dict[str, object]:
    """ATLAS content-production policy as fixture data, not ForgeGraph core logic."""

    return {
        "phase_id": ATLAS_CONTENT_PHASE_ID,
        "source_policy_id": "atlas_agency_ops.v1.content_production",
        "pack_id": "atlas_agency_ops.v1",
        "phase_name": "Content Production",
        "whiteboard_required_status": WorkWhiteboard.STATUS_READY_FOR_STRATEGY,
        "set_status_on_start": WorkWhiteboard.STATUS_IN_CONTENT,
        "workstreams": [
            {
                "id": "copywriting",
                "name": "Copywriting",
                "department": "content",
                "department_name": "Content",
                "output_type": "asset",
                "required": True,
            },
            {
                "id": "social_content",
                "name": "Social Content",
                "department": "social",
                "department_name": "Social",
                "output_type": "publication_draft",
                "required": True,
            },
            {
                "id": "email_sequence",
                "name": "Email Sequence",
                "department": "crm",
                "department_name": "CRM",
                "output_type": "publication_draft",
                "required": True,
            },
            {
                "id": "whatsapp_script",
                "name": "WhatsApp Script",
                "department": "messaging-ops",
                "department_name": "Messaging Ops",
                "output_type": "publication_draft",
                "required": True,
            },
            {
                "id": "landing_page_copy",
                "name": "Landing Page Copy",
                "department": "web",
                "department_name": "Web",
                "output_type": "publication_draft",
                "required": True,
            },
            {
                "id": "ad_copy",
                "name": "Ad Copy",
                "department": "paid-media",
                "department_name": "Paid Media",
                "output_type": "publication_draft",
                "required": True,
            },
            {
                "id": "visual_concepts",
                "name": "Visual Concepts",
                "department": "creative",
                "department_name": "Creative",
                "output_type": "asset",
                "required": True,
            },
            {
                "id": "video_storyboard",
                "name": "Video Storyboard",
                "department": "video",
                "department_name": "Video",
                "output_type": "asset",
                "required": True,
            },
        ],
        "gate": {
            "gate_id": "atlas_agency_ops.v1.content_quality_gate",
            "criteria": [
                {
                    "key": "brand_alignment",
                    "value_type": "number",
                    "operator": ">=",
                    "threshold": 90,
                    "required": True,
                },
                {
                    "key": "strategy_alignment",
                    "value_type": "number",
                    "operator": ">=",
                    "threshold": 90,
                    "required": True,
                },
                {
                    "key": "channel_fit",
                    "value_type": "number",
                    "operator": ">=",
                    "threshold": 90,
                    "required": True,
                },
                {
                    "key": "claim_support",
                    "value_type": "enum",
                    "operator": "in",
                    "expected": ["pass", 100],
                    "required": True,
                    "hard_fail": True,
                },
                {
                    "key": "legal_compliance",
                    "value_type": "enum",
                    "operator": "in",
                    "expected": ["pass", 100],
                    "required": True,
                    "hard_fail": True,
                },
                {
                    "key": "format_compliance",
                    "value_type": "number",
                    "operator": ">=",
                    "threshold": 95,
                    "required": True,
                },
                {
                    "key": "execution_readiness",
                    "value_type": "number",
                    "operator": ">=",
                    "threshold": 85,
                    "required": True,
                },
            ],
            "approval_required": True,
            "signal_on_fail": True,
            "on_pass": {
                "set_whiteboard_status": WorkWhiteboard.STATUS_IN_APPROVAL,
                "route_to_department": "client-services",
                "approval_required": True,
            },
            "on_fail": {
                "set_whiteboard_status": WorkWhiteboard.STATUS_IN_CONTENT,
                "route_to_department": "content-revision",
                "create_signal": True,
            },
        },
    }


def passing_atlas_content_scorecard() -> dict[str, object]:
    return {
        "brand_alignment": 93,
        "strategy_alignment": 92,
        "channel_fit": 91,
        "claim_support": "pass",
        "legal_compliance": 100,
        "format_compliance": 97,
        "execution_readiness": 88,
    }


def failing_atlas_content_scorecard() -> dict[str, object]:
    return {
        "brand_alignment": 93,
        "strategy_alignment": 89,
        "channel_fit": 91,
        "claim_support": "pass",
        "legal_compliance": "fail",
        "format_compliance": 97,
        "execution_readiness": 88,
    }


def legal_contract_review_policy() -> dict[str, object]:
    return {
        "phase_id": "legal_ops.v1.contract_review",
        "source_policy_id": "legal_ops.v1.contract_review_policy",
        "pack_id": "legal_ops.v1",
        "phase_name": "Contract Review",
        "workstreams": [
            {"id": "clause_extraction", "name": "Clause Extraction", "department": "legal", "required": True},
            {"id": "risk_review", "name": "Risk Review", "department": "legal", "required": True},
        ],
        "gate": {
            "gate_id": "legal_ops.v1.contract_review_gate",
            "criteria": [
                {"key": "missing_required_clause_count", "value_type": "number", "operator": "==", "threshold": 0},
                {"key": "high_risk_clause_count", "value_type": "number", "operator": "<=", "threshold": 2},
            ],
            "on_pass": {"set_whiteboard_status": WorkWhiteboard.STATUS_IN_APPROVAL},
            "on_fail": {"set_whiteboard_status": WorkWhiteboard.STATUS_IN_CONTENT, "create_signal": True},
        },
    }
