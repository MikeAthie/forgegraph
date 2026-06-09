from __future__ import annotations

import pytest
from django.test import override_settings

from application.services.llm_access import (
    LLMAccessConfig,
    LLMAccessValidationError,
    attach_llm_access_to_graph,
    engine_input_with_llm_access,
    engine_llm_access_from_graph,
    public_llm_access_from_graph,
    validate_llm_access_config,
)


def test_codex_session_llm_access_rejected_when_disabled():
    with override_settings(
        ENABLE_CODEX_SESSION_RUNTIME=False, ALLOWED_LLM_PROVIDERS=["openai", "codex"]
    ):
        with pytest.raises(LLMAccessValidationError) as exc_info:
            validate_llm_access_config(LLMAccessConfig(llm_mode="codex_session", provider="codex"))

    assert exc_info.value.details[0]["field"] == "llm_mode"


def test_codex_session_llm_access_is_sanitized_when_enabled(user):
    with override_settings(
        ENABLE_CODEX_SESSION_RUNTIME=True, ALLOWED_LLM_PROVIDERS=["openai", "codex"]
    ):
        config = validate_llm_access_config(
            LLMAccessConfig(llm_mode="codex_session", provider="codex")
        )
        graph = attach_llm_access_to_graph({"nodes": [], "metadata": {}}, config)
        public = public_llm_access_from_graph(graph)
        engine_config = engine_llm_access_from_graph(graph, user)
        engine_input = engine_input_with_llm_access({}, engine_config)

    assert public == {
        "llm_mode": "codex_session",
        "provider": "codex",
        "api_key_present": False,
        "credential_id": None,
        "local_session_required": True,
    }
    assert graph["metadata"]["llm_access"] == public
    assert engine_config.llm_mode == "codex_session"
    assert engine_config.provider == "codex"
    assert engine_config.api_key == ""
    assert "_forgegraph_llm_access" not in engine_input
