from __future__ import annotations

from infrastructure.orm.models import WorkWhiteboard

ATLAS_PERFORMANCE_POLICY_ID = "atlas_agency_ops.v1.launch_performance_review"


def atlas_launch_performance_policy() -> dict[str, object]:
    """ATLAS performance policy as fixture data, not ForgeGraph core logic."""

    return {
        "policy_id": ATLAS_PERFORMANCE_POLICY_ID,
        "source_policy_id": ATLAS_PERFORMANCE_POLICY_ID,
        "pack_id": "atlas_agency_ops.v1",
        "required_whiteboard_status": WorkWhiteboard.STATUS_IN_DEPLOYMENT,
        "cadence": "weekly",
        "metric_sources": [
            {
                "id": "email",
                "display_name": "Email",
                "department": "crm",
                "department_name": "CRM",
                "required_connector": "email_service_connector",
                "tool_id": "dmp.email_draft_send_schedule",
                "metrics": [
                    "open_rate",
                    "click_rate",
                    "unsubscribe_rate",
                    "execution_completeness",
                    "channel_signal_quality",
                    "optimization_confidence",
                ],
                "sample_metrics": {
                    "open_rate": 0.42,
                    "click_rate": 0.11,
                    "unsubscribe_rate": 0.01,
                    "execution_completeness": 86,
                    "channel_signal_quality": 74,
                    "optimization_confidence": 78,
                },
            },
            {
                "id": "whatsapp",
                "display_name": "WhatsApp",
                "department": "deployment-ops",
                "department_name": "Deployment Ops",
                "required_connector": "whatsapp_business_connector",
                "tool_id": "messaging.whatsapp_metrics",
                "metrics": ["delivered", "replies", "conversion_intent"],
            },
            {
                "id": "social",
                "display_name": "Social",
                "department": "analytics",
                "department_name": "Analytics",
                "required_connector": "social_analytics_connector",
                "tool_id": "social.analytics_snapshot",
                "metrics": ["reach", "engagement", "clicks"],
            },
            {
                "id": "landing_page",
                "display_name": "Landing Page",
                "department": "analytics",
                "department_name": "Analytics",
                "required_connector": "analytics_connector",
                "tool_id": "analytics.landing_page_snapshot",
                "metrics": ["visits", "conversion_rate"],
            },
        ],
        "evaluation_criteria": [
            {"key": "channel_signal_quality", "value_type": "number", "operator": ">=", "threshold": 70},
            {"key": "execution_completeness", "value_type": "number", "operator": ">=", "threshold": 80},
            {"key": "optimization_confidence", "value_type": "number", "operator": ">=", "threshold": 75},
        ],
        "routing_rules": [
            {
                "condition": "creative_fatigue",
                "route_to_department": "content",
                "priority": "normal",
                "create_signal": True,
            },
            {
                "condition": "poor_audience_fit",
                "route_to_department": "strategy",
                "priority": "normal",
                "create_signal": True,
            },
            {
                "condition": "missing_metric_connector",
                "route_to_department": "deployment-ops",
                "priority": "high",
                "create_signal": False,
            },
        ],
        "on_blocked": {"route_to_department": "deployment-ops"},
    }


def non_marketing_performance_policy() -> dict[str, object]:
    return {
        "policy_id": "legal_ops.v1.contract_outcome_review",
        "source_policy_id": "legal_ops.v1.contract_outcome_review",
        "pack_id": "legal_ops.v1",
        "required_whiteboard_status": WorkWhiteboard.STATUS_IN_DEPLOYMENT,
        "cadence": "monthly",
        "metric_sources": [
            {
                "id": "case_management",
                "display_name": "Case Management",
                "department": "legal-ops",
                "department_name": "Legal Ops",
                "required_connector": "",
                "tool_id": "",
                "metrics": ["review_completion_score", "client_revision_count"],
                "sample_metrics": {
                    "review_completion_score": 96,
                    "client_revision_count": 1,
                },
            }
        ],
        "evaluation_criteria": [
            {"key": "review_completion_score", "value_type": "number", "operator": ">=", "threshold": 90},
            {"key": "client_revision_count", "value_type": "number", "operator": "<=", "threshold": 2},
        ],
        "routing_rules": [
            {
                "condition": "client_revision_count",
                "route_to_department": "legal-ops",
                "priority": "normal",
                "create_signal": True,
            }
        ],
        "on_blocked": {"route_to_department": "legal-ops"},
    }
