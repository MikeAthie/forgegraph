from __future__ import annotations

from application.services.llm_access import LLMAccessConfig, validate_llm_access_config


def test_google_is_allowed_llm_provider_by_default():
    config = validate_llm_access_config(
        LLMAccessConfig(
            llm_mode="byok",
            provider="google",
            credential_id="00000000-0000-0000-0000-000000000001",
        )
    )

    assert config.provider == "google"
