"""CareerOps graph contract derived from docs/operating-model-packs/career-ops-company-graph.mmd."""

from __future__ import annotations

CAREER_OPS_PACK_ID = "career_ops.v1"
CAREER_OPS_BASE_PACK_ID = "career_ops"
CAREER_OPS_COMPANY_TYPE_LABEL = "Career Operations Company"
CAREER_OPS_DEFAULT_DISCOVERY_CRON = "0 10 * * *"
CAREER_OPS_APPLIED_COOLDOWN_DAYS = 30
CAREER_OPS_BASE_CV_ARTIFACT_TYPE = "cv_source"

CAREER_OPS_DEPARTMENTS: tuple[dict[str, object], ...] = (
    {
        "slug": "candidate_profile_strategy",
        "label": "Candidate Profile & Strategy",
        "responsibilities": (
            "Own CV, target roles, constraints, positioning, and proof points.",
            "Maintain candidate profile and source-of-truth career positioning.",
        ),
    },
    {
        "slug": "market_role_discovery",
        "label": "Market & Role Discovery",
        "responsibilities": (
            "Scan job sources cheaply before expensive agent work.",
            "Normalize, filter, and dedupe job leads with source receipts.",
        ),
    },
    {
        "slug": "opportunity_evaluation",
        "label": "Opportunity Evaluation",
        "responsibilities": (
            "Score fit, legitimacy, compensation, and apply/no-apply recommendations.",
            "Produce A-G evaluation reports backed by evidence.",
        ),
    },
    {
        "slug": "application_packet_studio",
        "label": "Application Packet Studio",
        "responsibilities": (
            "Produce truthful tailored resumes, cover letters, and application answers.",
            "Maintain ATS, PDF, packet manifest, and artifact quality.",
        ),
    },
    {
        "slug": "application_operations",
        "label": "Application Operations",
        "responsibilities": (
            "Track application status, next actions, follow-ups, and receipts.",
            "Coordinate submission readiness after candidate approval.",
        ),
    },
    {
        "slug": "interview_negotiation_prep",
        "label": "Interview & Negotiation Prep",
        "responsibilities": (
            "Build reusable STAR+Reflection story bank.",
            "Prepare company-specific interview and negotiation briefs.",
        ),
    },
    {
        "slug": "pipeline_integrity_analytics",
        "label": "Pipeline Integrity & Analytics",
        "responsibilities": (
            "Keep the pipeline trustworthy through dedupe and artifact checks.",
            "Report conversion, stale follow-ups, and score calibration feedback.",
        ),
    },
    {
        "slug": "candidate_approval_governance",
        "label": "Candidate Approval & Governance",
        "responsibilities": (
            "Enforce human-in-the-loop approval before external side effects.",
            "Prevent auto-apply, false claims, privacy leaks, and invented experience.",
        ),
    },
)

CAREER_OPS_STAGE_SEQUENCE: tuple[str, ...] = (
    "stage_01_candidate_onboarding",
    "stage_02_search_strategy",
    "stage_03_market_scan",
    "stage_04_liveness_and_dedupe",
    "stage_05_fit_evaluation",
    "stage_06_application_packet",
    "stage_07_candidate_approval",
    "stage_08_submission_tracking",
    "stage_09_interview_prep",
    "stage_10_followup_negotiation",
    "stage_11_pipeline_review",
    "stage_12_learning_update",
)

CAREER_OPS_STAGE_LABELS: dict[str, str] = {
    "stage_01_candidate_onboarding": "Candidate onboarding",
    "stage_02_search_strategy": "Search strategy",
    "stage_03_market_scan": "Market scan",
    "stage_04_liveness_and_dedupe": "Liveness and dedupe",
    "stage_05_fit_evaluation": "Fit evaluation",
    "stage_06_application_packet": "Application packet",
    "stage_07_candidate_approval": "Candidate approval gate",
    "stage_08_submission_tracking": "Submission tracking",
    "stage_09_interview_prep": "Interview prep",
    "stage_10_followup_negotiation": "Follow-up and negotiation",
    "stage_11_pipeline_review": "Pipeline review",
    "stage_12_learning_update": "Learning update",
}

CAREER_OPS_STAGE_TO_DEPARTMENT: dict[str, str] = {
    "stage_01_candidate_onboarding": "candidate_profile_strategy",
    "stage_02_search_strategy": "candidate_profile_strategy",
    "stage_03_market_scan": "market_role_discovery",
    "stage_04_liveness_and_dedupe": "market_role_discovery",
    "stage_05_fit_evaluation": "opportunity_evaluation",
    "stage_06_application_packet": "application_packet_studio",
    "stage_07_candidate_approval": "candidate_approval_governance",
    "stage_08_submission_tracking": "application_operations",
    "stage_09_interview_prep": "interview_negotiation_prep",
    "stage_10_followup_negotiation": "interview_negotiation_prep",
    "stage_11_pipeline_review": "pipeline_integrity_analytics",
    "stage_12_learning_update": "candidate_profile_strategy",
}

CAREER_OPS_DURABLE_STATE_KEYS: tuple[str, ...] = (
    "career_ops:candidate_profile",
    "career_ops:career_positioning",
    "career_ops:cv_source",
    "career_ops:proof_point_digest",
    "career_ops:pipeline_snapshot",
    "career_ops:interview_story_bank",
)

CAREER_OPS_DELIVERABLE_TYPES: tuple[str, ...] = (
    "job_liveness_receipt",
    "job_evaluation_report",
    "posting_legitimacy_report",
    "tailored_resume_html",
    "tailored_resume_pdf",
    "cover_letter_draft",
    "cover_letter_pdf",
    "application_answers",
    "application_packet",
    "company_interview_prep",
    "interview_story_bank",
    "negotiation_script",
    "followup_plan",
    "pipeline_health_report",
)

CAREER_OPS_PIPELINE_STATUSES: tuple[str, ...] = (
    "discovered",
    "liveness_checked",
    "evaluated",
    "packet_ready",
    "approval_pending",
    "approved",
    "applied",
    "interview",
    "offer",
    "rejected",
    "skip",
)
