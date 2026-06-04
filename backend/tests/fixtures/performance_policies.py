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
        "allow_sandbox_deployment_evidence": True,
        "allow_web_automation_deployment_evidence": False,
        "allow_manual_publish_deployment_evidence": False,
        "cadence": "weekly",
        "metric_sources": [
            {
                "id": "email",
                "display_name": "Email",
                "department": "crm",
                "department_name": "CRM",
                "required_connector": "email_connector",
                "tool_id": "email.send_dry_run",
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
                "baseline_metrics": {
                    "open_rate": 0.26,
                    "click_rate": 0.031,
                    "unsubscribe_rate": 0.012,
                },
                "target_metrics": {
                    "open_rate": 0.32,
                    "click_rate": 0.045,
                    "unsubscribe_rate": 0.01,
                },
                "attribution_scope": "local_sandbox_email_receipt",
                "evidence_mode": "sandbox",
                "optimization_actions": [
                    {
                        "id": "email_subject_line_test",
                        "title": "Test appointment-proof subject line against price-led subject line",
                        "owner_department": "analytics",
                        "trigger_metric": "click_rate",
                        "next_action": "Promote the variant that beats the click-rate target without increasing unsubscribe rate.",
                    }
                ],
            },
            {
                "id": "whatsapp",
                "display_name": "WhatsApp",
                "department": "deployment-ops",
                "department_name": "Deployment Ops",
                "required_connector": "whatsapp_connector",
                "tool_id": "whatsapp.send_dry_run",
                "metrics": ["delivered", "replies", "conversion_intent"],
                "sample_metrics": {
                    "delivered": 120,
                    "replies": 10,
                    "conversion_intent": 6,
                },
                "baseline_metrics": {
                    "delivered": 0,
                    "replies": 0,
                    "conversion_intent": 0,
                },
                "target_metrics": {
                    "delivered": 100,
                    "replies": 8,
                    "conversion_intent": 5,
                },
                "attribution_scope": "local_sandbox_message_receipt",
                "evidence_mode": "sandbox",
                "optimization_actions": [
                    {
                        "id": "whatsapp_consent_copy_check",
                        "title": "Review reply intent before expanding WhatsApp volume",
                        "owner_department": "analytics",
                        "trigger_metric": "replies",
                        "next_action": "Keep WhatsApp as an approved follow-up channel only if consent-safe replies exceed target.",
                    }
                ],
            },
            {
                "id": "social",
                "display_name": "Social",
                "department": "analytics",
                "department_name": "Analytics",
                "required_connector": "social_analytics_connector",
                "tool_id": "social.analytics_snapshot",
                "metrics": ["reach", "engagement", "clicks"],
                "sample_metrics": {
                    "reach": 12400,
                    "engagement": 0.062,
                    "clicks": 410,
                },
                "baseline_metrics": {
                    "reach": 8200,
                    "engagement": 0.045,
                    "clicks": 250,
                },
                "target_metrics": {
                    "reach": 11000,
                    "engagement": 0.06,
                    "clicks": 400,
                },
                "attribution_scope": "local_sandbox_social_snapshot",
                "evidence_mode": "sandbox",
                "optimization_actions": [
                    {
                        "id": "social_creative_rotation",
                        "title": "Rotate proof-led creative if engagement falls below target",
                        "owner_department": "analytics",
                        "trigger_metric": "engagement",
                        "next_action": "Move budget toward the creative variant with stronger qualified click signal.",
                    }
                ],
            },
            {
                "id": "landing_page",
                "display_name": "Landing Page",
                "department": "analytics",
                "department_name": "Analytics",
                "required_connector": "analytics_connector",
                "tool_id": "analytics.landing_page_snapshot",
                "metrics": ["visits", "conversion_rate"],
                "sample_metrics": {
                    "visits": 980,
                    "conversion_rate": 0.175,
                },
                "baseline_metrics": {
                    "visits": 720,
                    "conversion_rate": 0.155,
                },
                "target_metrics": {
                    "visits": 900,
                    "conversion_rate": 0.18,
                },
                "attribution_scope": "local_sandbox_landing_snapshot",
                "evidence_mode": "sandbox",
                "optimization_actions": [
                    {
                        "id": "landing_cta_alignment",
                        "title": "Align CTA copy with appointment-proof offer",
                        "owner_department": "analytics",
                        "trigger_metric": "conversion_rate",
                        "next_action": "Test proof-first CTA placement before increasing traffic.",
                    }
                ],
            },
        ],
        "evaluation_criteria": [
            {
                "key": "channel_signal_quality",
                "value_type": "number",
                "operator": ">=",
                "threshold": 70,
            },
            {
                "key": "execution_completeness",
                "value_type": "number",
                "operator": ">=",
                "threshold": 80,
            },
            {
                "key": "optimization_confidence",
                "value_type": "number",
                "operator": ">=",
                "threshold": 75,
            },
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
        "allow_sandbox_deployment_evidence": True,
        "allow_web_automation_deployment_evidence": False,
        "allow_manual_publish_deployment_evidence": False,
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
            {
                "key": "review_completion_score",
                "value_type": "number",
                "operator": ">=",
                "threshold": 90,
            },
            {
                "key": "client_revision_count",
                "value_type": "number",
                "operator": "<=",
                "threshold": 2,
            },
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
