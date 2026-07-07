from __future__ import annotations

from application.services.career_ops_graph_contract import (
    CAREER_OPS_APPLIED_COOLDOWN_DAYS,
    CAREER_OPS_BASE_CV_ARTIFACT_TYPE,
    CAREER_OPS_DEFAULT_DISCOVERY_CRON,
    CAREER_OPS_DELIVERABLE_TYPES,
    CAREER_OPS_DEPARTMENTS,
    CAREER_OPS_DURABLE_STATE_KEYS,
    CAREER_OPS_STAGE_SEQUENCE,
    CAREER_OPS_STAGE_TO_DEPARTMENT,
)


def test_career_ops_graph_contract_matches_mermaid_source_of_truth() -> None:
    assert len(CAREER_OPS_DEPARTMENTS) == 8
    assert len(CAREER_OPS_STAGE_SEQUENCE) == 12
    assert CAREER_OPS_STAGE_SEQUENCE[0] == "stage_01_candidate_onboarding"
    assert CAREER_OPS_STAGE_SEQUENCE[-1] == "stage_12_learning_update"
    assert CAREER_OPS_STAGE_TO_DEPARTMENT["stage_07_candidate_approval"] == (
        "candidate_approval_governance"
    )
    assert "application_packet" in CAREER_OPS_DELIVERABLE_TYPES
    assert "career_ops:candidate_profile" in CAREER_OPS_DURABLE_STATE_KEYS


def test_career_ops_contract_includes_daily_discovery_and_application_cooldown() -> None:
    assert CAREER_OPS_DEFAULT_DISCOVERY_CRON == "0 10 * * *"
    assert CAREER_OPS_APPLIED_COOLDOWN_DAYS == 30


def test_career_ops_contract_requires_base_cv_state() -> None:
    assert CAREER_OPS_BASE_CV_ARTIFACT_TYPE == "cv_source"
    assert "career_ops:cv_source" in CAREER_OPS_DURABLE_STATE_KEYS
