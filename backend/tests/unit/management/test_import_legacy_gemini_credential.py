from __future__ import annotations

import json
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from infrastructure.crypto.encryption import decrypt_api_key
from infrastructure.orm.management.commands.seed_legacy_glasswear_phase0 import (
    DEFAULT_EMAIL,
)
from infrastructure.orm.models import APIKey, Graph, GraphVersion, User

pytestmark = pytest.mark.django_db


def _seed_phase0() -> None:
    call_command(
        "seed_legacy_glasswear_phase0",
        email=DEFAULT_EMAIL,
        password="legacy-password-123",
        output_json=True,
        stdout=StringIO(),
    )


def test_import_legacy_gemini_credential_creates_google_api_key_without_leaking_secret(
    monkeypatch,
):
    _seed_phase0()
    monkeypatch.setenv("GEMINI_LEGACY", "gemini-secret-test-key")
    out = StringIO()

    call_command("import_legacy_gemini_credential", output_json=True, stdout=out)

    output = out.getvalue()
    assert "gemini-secret-test-key" not in output
    payload = json.loads(output)
    assert payload["provider"] == "google"
    assert payload["key_present"] is True
    credential = APIKey.objects.get(id=payload["credential_id"])
    assert credential.provider == "google"
    assert decrypt_api_key(bytes(credential.encrypted_key)) == "gemini-secret-test-key"

    user = User.objects.get(email=DEFAULT_EMAIL)
    graph = Graph.objects.for_user(user).get()
    latest = graph.versions.order_by("-version").first()
    assert latest is not None
    metadata = latest.graph_json["metadata"]
    assert metadata["llm_access"]["provider"] == "google"
    assert metadata["llm_access"]["credential_id"] == str(credential.id)
    assert metadata["phase_1_gemini_byok"]["api_key_present"] is True
    assert metadata["company_profile"]["byokCredentialId"] == str(credential.id)


def test_import_legacy_gemini_credential_requires_env(monkeypatch):
    _seed_phase0()
    monkeypatch.delenv("GEMINI_LEGACY", raising=False)

    with pytest.raises(CommandError, match="GEMINI_LEGACY"):
        call_command("import_legacy_gemini_credential", output_json=True, stdout=StringIO())


def test_import_legacy_openrouter_credential_creates_openrouter_api_key_without_leaking_secret(
    monkeypatch,
):
    _seed_phase0()
    monkeypatch.setenv("OPENROUTER", "openrouter-secret-test-key")
    out = StringIO()

    call_command("import_legacy_openrouter_credential", output_json=True, stdout=out)

    output = out.getvalue()
    assert "openrouter-secret-test-key" not in output
    payload = json.loads(output)
    assert payload["provider"] == "openrouter"
    assert payload["key_present"] is True
    credential = APIKey.objects.get(id=payload["credential_id"])
    assert credential.provider == "openrouter"
    assert decrypt_api_key(bytes(credential.encrypted_key)) == "openrouter-secret-test-key"

    user = User.objects.get(email=DEFAULT_EMAIL)
    graph = Graph.objects.for_user(user).get()
    latest = graph.versions.order_by("-version").first()
    assert latest is not None
    metadata = latest.graph_json["metadata"]
    assert metadata["llm_access"]["provider"] == "openrouter"
    assert metadata["llm_access"]["credential_id"] == str(credential.id)
    assert metadata["phase_1_openrouter_byok"]["api_key_present"] is True
    assert metadata["phase_1_openrouter_byok"]["image_model"] == "black-forest-labs/flux.2-klein-4b"
    assert metadata["company_profile"]["intelligenceProvider"] == "openrouter"
    assert metadata["company_profile"]["byokCredentialId"] == str(credential.id)
    for node in latest.graph_json["nodes"]:
        config = node.get("config") if isinstance(node, dict) else None
        if isinstance(config, dict) and config.get("provider"):
            assert config["provider"] == "openrouter"
            assert config["credential_id"] == str(credential.id)


def test_import_legacy_openrouter_credential_accepts_api_key_fallback_env(monkeypatch):
    _seed_phase0()
    monkeypatch.delenv("OPENROUTER", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "openrouter-fallback-secret")
    out = StringIO()

    call_command("import_legacy_openrouter_credential", output_json=True, stdout=out)

    payload = json.loads(out.getvalue())
    credential = APIKey.objects.get(id=payload["credential_id"])
    assert credential.provider == "openrouter"
    assert decrypt_api_key(bytes(credential.encrypted_key)) == "openrouter-fallback-secret"


def test_import_legacy_openrouter_credential_requires_env(monkeypatch):
    _seed_phase0()
    monkeypatch.delenv("OPENROUTER", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    with pytest.raises(CommandError, match="OPENROUTER"):
        call_command("import_legacy_openrouter_credential", output_json=True, stdout=StringIO())


def test_import_legacy_gemini_credential_allows_legacy_operation_graphs(monkeypatch):
    _seed_phase0()
    user = User.objects.get(email=DEFAULT_EMAIL)
    operation_graph = Graph.objects.create(
        owner=user,
        organization=user.default_organization,
        name="Legacy Phase 6 Visual Asset Brief Objective",
        description="Phase 6 operation graph.",
    )
    GraphVersion.objects.create(
        graph=operation_graph,
        version=1,
        graph_json={
            "nodes": [],
            "edges": [],
            "metadata": {"name": operation_graph.name, "legacy_phase": "phase-6"},
        },
    )
    monkeypatch.setenv("GEMINI_LEGACY", "gemini-secret-test-key")
    out = StringIO()

    call_command("import_legacy_gemini_credential", output_json=True, stdout=out)

    payload = json.loads(out.getvalue())
    assert payload["provider"] == "google"
    assert payload["key_present"] is True
