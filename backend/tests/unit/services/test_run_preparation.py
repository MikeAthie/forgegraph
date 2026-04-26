"""Unit tests for run preparation helpers."""

from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone

from application.services.llm_access import LLMAccessConfig
from application.services.run_preparation import (
    PromptTemplateResolutionError,
    RunPreparationError,
    prepare_graph_for_engine,
    resolve_prompt_templates,
    validate_prompt_credentials,
)
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import (
    APIKey,
    NodePackageInstallation,
    NodeRegistryPackage,
    NodeRegistryRelease,
    PromptTemplate,
    User,
)

pytestmark = pytest.mark.django_db


def test_resolve_prompt_templates_replaces_prompt_id_with_content() -> None:
    owner = User.objects.create_user(email="owner@example.com", password="password123")
    prompt = PromptTemplate.objects.create(
        owner=owner,
        title="Greeting",
        category="other",
        content="Hello {{input.name}}",
        visibility="private",
    )
    graph_json: dict[str, Any] = {
        "nodes": [
            {
                "id": "prompt-1",
                "type": "prompt",
                "name": "Prompt",
                "config": {"prompt_id": str(prompt.id), "prompt_template": "stale"},
            }
        ],
        "edges": [],
    }

    resolved = resolve_prompt_templates(graph_json, owner)

    assert resolved["nodes"][0]["config"]["prompt_template"] == "Hello {{input.name}}"
    assert resolved["nodes"][0]["config"]["prompt_id"] == str(prompt.id)
    assert graph_json["nodes"][0]["config"]["prompt_template"] == "stale"


def test_resolve_prompt_templates_rejects_inaccessible_prompt_id() -> None:
    owner = User.objects.create_user(email="owner@example.com", password="password123")
    other = User.objects.create_user(email="other@example.com", password="password123")
    prompt = PromptTemplate.objects.create(
        owner=other,
        title="Other Prompt",
        category="other",
        content="Restricted",
        visibility="private",
    )
    graph_json: dict[str, Any] = {
        "nodes": [
            {
                "id": "prompt-1",
                "type": "prompt",
                "name": "Prompt",
                "config": {"prompt_id": str(prompt.id)},
            }
        ],
        "edges": [],
    }

    with pytest.raises(PromptTemplateResolutionError, match="not accessible"):
        resolve_prompt_templates(graph_json, owner)


def test_prepare_graph_for_engine_requires_prompt_template_or_prompt_id() -> None:
    owner = User.objects.create_user(email="owner@example.com", password="password123")
    graph_json: dict[str, Any] = {
        "nodes": [{"id": "prompt-1", "type": "prompt", "name": "Prompt", "config": {}}],
        "edges": [],
    }

    with pytest.raises(PromptTemplateResolutionError, match="prompt_template"):
        prepare_graph_for_engine(graph_json, owner)


def test_prepare_graph_for_engine_resolves_nested_subgraph_prompt_ids() -> None:
    owner = User.objects.create_user(email="owner@example.com", password="password123")
    prompt = PromptTemplate.objects.create(
        owner=owner,
        title="Nested Prompt",
        category="other",
        content="Nested template",
        visibility="private",
    )
    graph_json: dict[str, Any] = {
        "nodes": [
            {
                "id": "sub-1",
                "type": "subgraph",
                "name": "Subgraph",
                "config": {
                    "graph_json": {
                        "nodes": [
                            {
                                "id": "prompt-nested",
                                "type": "prompt",
                                "name": "Nested Prompt",
                                "config": {"prompt_id": str(prompt.id)},
                            }
                        ],
                        "edges": [],
                    }
                },
            }
        ],
        "edges": [],
    }

    prepared = prepare_graph_for_engine(graph_json, owner)
    nested_config = prepared["nodes"][0]["config"]["graph_json"]["nodes"][0]["config"]
    assert nested_config["prompt_template"] == "Nested template"


def test_validate_prompt_credentials_rejects_revoked_credential() -> None:
    owner = User.objects.create_user(email="owner@example.com", password="password123")
    ensure_default_organization(owner)
    assert owner.default_organization is not None
    credential = APIKey.objects.create(
        organization=owner.default_organization,
        user=owner,
        provider="openai",
        name="revoked-openai",
        encrypted_key=b"opaque",
        token_metadata={"revoked": True},
    )
    graph_json: dict[str, Any] = {
        "nodes": [
            {
                "id": "prompt-1",
                "type": "prompt",
                "name": "Prompt",
                "config": {
                    "provider": "openai",
                    "credential_id": str(credential.id),
                    "prompt_template": "Hello",
                },
            }
        ],
        "edges": [],
    }

    errors = validate_prompt_credentials(graph_json, owner)
    assert any("revoked credential" in str(error.get("message", "")).lower() for error in errors)


def test_validate_prompt_credentials_allows_openai_fallback_key(settings) -> None:
    owner = User.objects.create_user(email="owner-fallback@example.com", password="password123")
    ensure_default_organization(owner)
    settings.OPENAI_API_KEY = "local-runner-key"
    graph_json: dict[str, Any] = {
        "nodes": [
            {
                "id": "prompt-1",
                "type": "prompt",
                "name": "Prompt",
                "config": {
                    "provider": "openai",
                    "prompt_template": "Hello",
                },
            }
        ],
        "edges": [],
    }

    errors = validate_prompt_credentials(graph_json, owner)
    assert errors == []


def test_validate_prompt_credentials_allows_run_level_byok(settings) -> None:
    owner = User.objects.create_user(email="owner-byok@example.com", password="password123")
    ensure_default_organization(owner)
    settings.OPENAI_API_KEY = ""
    graph_json: dict[str, Any] = {
        "nodes": [
            {
                "id": "prompt-1",
                "type": "prompt",
                "name": "Prompt",
                "config": {
                    "provider": "openai",
                    "prompt_template": "Hello",
                },
            }
        ],
        "edges": [],
    }

    errors = validate_prompt_credentials(
        graph_json,
        owner,
        llm_access=LLMAccessConfig(
            llm_mode="byok",
            provider="openai",
            credential_id="run-level-openai",
            api_key="sk-test-byok",
        ),
    )

    assert errors == []


def test_prepare_graph_for_engine_assigns_tool_provider_and_credential() -> None:
    owner = User.objects.create_user(email="owner@example.com", password="password123")
    ensure_default_organization(owner)
    assert owner.default_organization is not None

    credential = APIKey.objects.create(
        organization=owner.default_organization,
        user=owner,
        provider="google_tasks",
        name="tasks-oauth",
        encrypted_key=b"opaque",
        token_metadata={"provider": "google_tasks"},
        token_expires_at=timezone.now() + timedelta(hours=1),
    )

    graph_json: dict[str, Any] = {
        "nodes": [
            {
                "id": "tool-1",
                "type": "tool",
                "name": "Tasks",
                "config": {"tool_name": "google_tasks"},
            }
        ],
        "edges": [],
    }

    prepared = prepare_graph_for_engine(graph_json, owner)
    config = prepared["nodes"][0]["config"]
    assert config["provider"] == "google_tasks"
    assert config["credential_id"] == str(credential.id)


def test_prepare_graph_for_engine_ignores_revoked_tool_credentials() -> None:
    owner = User.objects.create_user(email="owner@example.com", password="password123")
    ensure_default_organization(owner)
    assert owner.default_organization is not None

    APIKey.objects.create(
        organization=owner.default_organization,
        user=owner,
        provider="google_calendar",
        name="calendar-oauth-revoked",
        encrypted_key=b"opaque",
        token_metadata={"revoked": True},
    )

    graph_json: dict[str, Any] = {
        "nodes": [
            {
                "id": "tool-1",
                "type": "tool",
                "name": "Calendar",
                "config": {"tool_name": "google_calendar"},
            }
        ],
        "edges": [],
    }

    prepared = prepare_graph_for_engine(graph_json, owner)
    config = prepared["nodes"][0]["config"]
    assert config["provider"] == "google_calendar"
    assert "credential_id" not in config


def test_prepare_graph_for_engine_ignores_non_oauth_keys_for_oauth_tool_provider() -> None:
    owner = User.objects.create_user(email="owner@example.com", password="password123")
    ensure_default_organization(owner)
    assert owner.default_organization is not None

    APIKey.objects.create(
        organization=owner.default_organization,
        user=owner,
        provider="gmail",
        name="gmail-api-key",
        encrypted_key=b"opaque",
    )
    oauth_credential = APIKey.objects.create(
        organization=owner.default_organization,
        user=owner,
        provider="gmail",
        name="gmail-oauth",
        encrypted_key=b"opaque",
        token_metadata={"provider": "gmail"},
        token_expires_at=timezone.now() + timedelta(hours=1),
    )

    graph_json: dict[str, Any] = {
        "nodes": [
            {
                "id": "tool-1",
                "type": "tool",
                "name": "Gmail",
                "config": {"tool_name": "gmail_reader"},
            }
        ],
        "edges": [],
    }

    prepared = prepare_graph_for_engine(graph_json, owner)
    config = prepared["nodes"][0]["config"]
    assert config["provider"] == "gmail"
    assert config["credential_id"] == str(oauth_credential.id)


def test_prepare_graph_for_engine_injects_runtime_contract_metadata() -> None:
    owner = User.objects.create_user(email="owner@example.com", password="password123")
    graph_json: dict[str, Any] = {
        "nodes": [
            {
                "id": "prompt-1",
                "type": "prompt",
                "name": "Prompt",
                "config": {"prompt_template": "Hello"},
            }
        ],
        "edges": [],
    }

    prepared = prepare_graph_for_engine(
        graph_json,
        owner,
        traceparent="00-0123456789abcdef0123456789abcdef-0123456789abcdef-01",
        tracestate="vendor=test",
    )

    metadata = prepared["metadata"]
    assert metadata["engine_contract_version"] == "2"
    assert "dispatch_transformations" in metadata
    assert "trace" in metadata
    assert metadata["trace"]["trace_id"] == "0123456789abcdef0123456789abcdef"
    assert metadata["trace"]["tracestate"] == "vendor=test"
    assert metadata["runtime_limits"]["max_run_duration_ms"] > 0


def test_prepare_graph_for_engine_resolves_backend_selected_tools_and_pins_versions() -> None:
    owner = User.objects.create_user(email="owner@example.com", password="password123")
    ensure_default_organization(owner)
    assert owner.default_organization is not None

    package = NodeRegistryPackage.objects.create(
        slug="crm-lookup",
        name="CRM Lookup",
        summary="Lookup customer records",
        category="crm",
    )
    release = NodeRegistryRelease.objects.create(
        package=package,
        version="1.2.0",
        status="approved",
        package_kind="runtime_tool",
        execution_node_type="tool",
        manifest_version=2,
        config_defaults={"tool": "crm_lookup"},
        runtime_manifest={
            "name": "crm_lookup",
            "version": "1.2.0",
            "category": "crm",
            "description": "Lookup CRM records",
            "visibility": "public",
            "input_schema": {"type": "object"},
            "execution": {
                "type": "http",
                "timeout_seconds": 10,
                "http": {"url": "https://example.com/crm", "method": "POST"},
            },
            "side_effects": {"type": "read", "idempotent": True},
        },
    )
    NodePackageInstallation.objects.create(
        organization=owner.default_organization,
        package=package,
        release=release,
        install_metadata={},
    )

    internal_package = NodeRegistryPackage.objects.create(
        slug="crm-sync-internal",
        name="CRM Sync Internal",
        summary="Internal sync helper",
        category="crm",
    )
    internal_release = NodeRegistryRelease.objects.create(
        package=internal_package,
        version="1.0.0",
        status="approved",
        package_kind="runtime_tool",
        execution_node_type="tool",
        manifest_version=2,
        config_defaults={"tool": "crm_sync_internal"},
        runtime_manifest={
            "name": "crm_sync_internal",
            "version": "1.0.0",
            "category": "crm",
            "visibility": "internal",
            "input_schema": {"type": "object"},
            "execution": {
                "type": "http",
                "timeout_seconds": 10,
                "http": {"url": "https://example.com/internal", "method": "POST"},
            },
            "side_effects": {"type": "read", "idempotent": True},
        },
    )
    NodePackageInstallation.objects.create(
        organization=owner.default_organization,
        package=internal_package,
        release=internal_release,
        install_metadata={},
    )

    graph_json: dict[str, Any] = {
        "nodes": [
            {
                "id": "agent-1",
                "type": "agent",
                "name": "Agent",
                "config": {
                    "tool_selection": {"categories": ["crm"], "max_tools": 5},
                    "approval_required_tools": ["crm_lookup"],
                },
            },
            {
                "id": "tool-1",
                "type": "tool",
                "name": "Lookup",
                "config": {"tool": "crm_lookup"},
            },
        ],
        "edges": [],
    }

    prepared = prepare_graph_for_engine(graph_json, owner)

    agent_config = prepared["nodes"][0]["config"]
    tool_config = prepared["nodes"][1]["config"]
    tool_resolution = prepared["metadata"]["tool_resolution"]

    assert agent_config["tools"] == ["crm_lookup"]
    assert agent_config["tool_versions"] == {"crm_lookup": "1.2.0"}
    assert tool_config["version"] == "1.2.0"
    assert tool_resolution["manifest_version"] == 2
    assert tool_resolution["tenant_id"] == str(owner.default_organization_id)
    assert tool_resolution["runtime_mode"] == "cloud"
    assert tool_resolution["tool_catalog_size"] == 2
    assert tool_resolution["agent_nodes"]["agent-1"] == {
        "tools": ["crm_lookup"],
        "tool_versions": {"crm_lookup": "1.2.0"},
        "unresolved_explicit_tools": [],
    }
    assert [tool["name"] for tool in tool_resolution["pinned_tools"]] == ["crm_lookup"]
    assert tool_resolution["pinned_tools"][0]["version"] == "1.2.0"
    assert tool_resolution["manifest_checksum"]


def test_prepare_graph_for_engine_rejects_unresolved_approval_required_tools() -> None:
    owner = User.objects.create_user(email="owner@example.com", password="password123")
    ensure_default_organization(owner)
    assert owner.default_organization is not None

    package = NodeRegistryPackage.objects.create(
        slug="crm-lookup",
        name="CRM Lookup",
        summary="Lookup customer records",
        category="crm",
    )
    release = NodeRegistryRelease.objects.create(
        package=package,
        version="1.2.0",
        status="approved",
        package_kind="runtime_tool",
        execution_node_type="tool",
        manifest_version=2,
        config_defaults={"tool": "crm_lookup"},
        runtime_manifest={
            "name": "crm_lookup",
            "version": "1.2.0",
            "category": "crm",
            "visibility": "public",
            "input_schema": {"type": "object"},
            "execution": {
                "type": "http",
                "timeout_seconds": 10,
                "http": {"url": "https://example.com/crm", "method": "POST"},
            },
            "side_effects": {"type": "read", "idempotent": True},
        },
    )
    NodePackageInstallation.objects.create(
        organization=owner.default_organization,
        package=package,
        release=release,
        install_metadata={},
    )

    graph_json: dict[str, Any] = {
        "nodes": [
            {
                "id": "agent-1",
                "type": "agent",
                "name": "Agent",
                "config": {
                    "tool_selection": {"categories": ["crm"], "max_tools": 5},
                    "approval_required_tools": ["send_email"],
                },
            }
        ],
        "edges": [],
    }

    with pytest.raises(
        RunPreparationError,
        match="approval_required_tools must be included in the resolved tool set",
    ):
        prepare_graph_for_engine(graph_json, owner)
