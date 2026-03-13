"""Unit tests for run preparation helpers."""

from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone

from application.services.run_preparation import (
    PromptTemplateResolutionError,
    prepare_graph_for_engine,
    resolve_prompt_templates,
    validate_prompt_credentials,
)
from application.services.tenancy import ensure_default_organization
from infrastructure.orm.models import APIKey, PromptTemplate, User

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
