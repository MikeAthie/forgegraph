from __future__ import annotations

from uuid import uuid4

import pytest

from application.services.marketplace_runtime import (
    build_runtime_delivery_state,
    build_runtime_manifest_payload,
    is_release_installable_in_runtime_mode,
    normalize_runtime_tool_manifest,
    select_agent_runtime_tools,
)
from infrastructure.orm.models import (
    NodePackageInstallation,
    NodeRegistryPackage,
    NodeRegistryRelease,
    Organization,
)


@pytest.mark.django_db
def test_build_runtime_delivery_state_marks_templates_as_template(user):
    package = NodeRegistryPackage.objects.create(
        slug="template-http",
        name="Template HTTP",
        summary="Preset",
        category="developer",
    )
    release = NodeRegistryRelease.objects.create(
        package=package,
        version="1.0.0",
        status="approved",
        package_kind="template_http",
        execution_node_type="http",
        config_defaults={"url": "https://example.com"},
    )

    result = build_runtime_delivery_state(release)

    assert result["state"] == "template"
    assert result["reason"] == "template_only"


@pytest.mark.django_db
def test_build_runtime_manifest_payload_includes_only_ready_runtime_tools(user):
    org = user.default_organization
    assert org is not None

    runtime_package = NodeRegistryPackage.objects.create(
        slug="crm-lookup",
        name="CRM Lookup",
        summary="Runtime tool",
        category="developer",
    )
    runtime_release = NodeRegistryRelease.objects.create(
        package=runtime_package,
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
            "input_schema": {"type": "object"},
            "execution": {
                "type": "http",
                "timeout_seconds": 10,
                "http": {"url": "https://example.com/crm", "method": "POST"},
            },
            "side_effects": {"type": "read", "idempotent": True},
            "visibility": "public",
        },
    )
    NodePackageInstallation.objects.create(
        organization=org,
        package=runtime_package,
        release=runtime_release,
        install_metadata={},
    )

    blocked_package = NodeRegistryPackage.objects.create(
        slug="blocked-exec",
        name="Blocked Exec",
        summary="Exec tool",
        category="developer",
    )
    blocked_release = NodeRegistryRelease.objects.create(
        package=blocked_package,
        version="1.0.0",
        status="approved",
        package_kind="runtime_tool",
        execution_node_type="tool",
        cloud_allowed=False,
        manifest_version=1,
        config_defaults={"tool": "blocked_exec"},
        runtime_manifest={
            "name": "blocked_exec",
            "version": "1.0.0",
            "kind": "exec",
            "input_schema": {"type": "object"},
            "exec": {"command": "python"},
        },
    )
    NodePackageInstallation.objects.create(
        organization=org,
        package=blocked_package,
        release=blocked_release,
        install_metadata={},
    )

    template_package = NodeRegistryPackage.objects.create(
        slug="template-http",
        name="Template HTTP",
        summary="Preset",
        category="developer",
    )
    template_release = NodeRegistryRelease.objects.create(
        package=template_package,
        version="1.0.0",
        status="approved",
        package_kind="template_http",
        execution_node_type="http",
        config_defaults={"url": "https://example.com"},
    )
    NodePackageInstallation.objects.create(
        organization=org,
        package=template_package,
        release=template_release,
        install_metadata={},
    )

    payload = build_runtime_manifest_payload(str(org.id))

    assert payload["tenant_id"] == str(org.id)
    assert payload["manifest_version"] == 2
    assert len(payload["tools"]) == 1
    assert payload["tools"][0]["name"] == "crm_lookup"
    assert payload["tools"][0]["execution"]["type"] == "http"
    assert payload["tools"][0]["definition_checksum"]
    package_states = {item["package_slug"]: item["delivery_state"] for item in payload["packages"]}
    assert package_states["crm-lookup"] == "ready"
    assert package_states["blocked-exec"] == "blocked"
    assert package_states["template-http"] == "template"
    assert isinstance(payload["checksum"], str)
    assert payload["checksum"]


@pytest.mark.django_db
def test_build_runtime_manifest_payload_is_tenant_scoped(user):
    other_org = Organization.objects.create(id=uuid4(), name="Other Tenant")
    package = NodeRegistryPackage.objects.create(
        slug="tenant-only-tool",
        name="Tenant Only Tool",
        summary="Runtime tool",
        category="developer",
    )
    release = NodeRegistryRelease.objects.create(
        package=package,
        version="1.0.0",
        status="approved",
        package_kind="runtime_tool",
        execution_node_type="tool",
        manifest_version=2,
        config_defaults={"tool": "tenant_only"},
        runtime_manifest={
            "name": "tenant_only",
            "version": "1.0.0",
            "category": "developer",
            "input_schema": {"type": "object"},
            "execution": {
                "type": "http",
                "timeout_seconds": 10,
                "http": {"url": "https://example.com/tool", "method": "POST"},
            },
            "side_effects": {"type": "read", "idempotent": True},
        },
    )
    NodePackageInstallation.objects.create(
        organization=other_org,
        package=package,
        release=release,
        install_metadata={},
    )

    payload = build_runtime_manifest_payload(str(user.default_organization_id))

    assert payload["tools"] == []
    assert payload["packages"] == []


@pytest.mark.django_db
def test_normalize_runtime_tool_manifest_translates_legacy_http_v1(user):
    package = NodeRegistryPackage.objects.create(
        slug="legacy-http",
        name="Legacy HTTP",
        summary="Legacy tool",
        category="developer",
    )
    release = NodeRegistryRelease.objects.create(
        package=package,
        version="1.0.0",
        status="approved",
        package_kind="runtime_tool",
        execution_node_type="tool",
        manifest_version=1,
        runtime_manifest={
            "name": "legacy_http",
            "version": "1.0.0",
            "kind": "http",
            "input_schema": {"type": "object"},
            "http": {"url": "https://example.com/legacy", "method": "GET"},
        },
    )

    normalized, reason = normalize_runtime_tool_manifest(release)

    assert reason == "translated_legacy_http_v1"
    assert normalized is not None
    assert normalized["execution"]["type"] == "http"
    assert normalized["side_effects"]["type"] == "read"
    assert normalized["side_effects"]["idempotent"] is True


@pytest.mark.django_db
def test_is_release_installable_in_runtime_mode_blocks_exec_in_cloud(user):
    package = NodeRegistryPackage.objects.create(
        slug="blocked-exec",
        name="Blocked Exec",
        summary="Exec tool",
        category="developer",
    )
    release = NodeRegistryRelease.objects.create(
        package=package,
        version="1.0.0",
        status="approved",
        package_kind="runtime_tool",
        execution_node_type="tool",
        cloud_allowed=True,
        manifest_version=1,
        runtime_manifest={
            "name": "blocked_exec",
            "version": "1.0.0",
            "kind": "exec",
            "input_schema": {"type": "object"},
            "exec": {"command": "python"},
        },
    )

    installable, delivery = is_release_installable_in_runtime_mode(release, runtime_mode="cloud")

    assert installable is False
    assert delivery["state"] == "blocked"
    assert delivery["reason"] == "exec_not_supported_in_cloud"


def test_select_agent_runtime_tools_prefers_explicit_pins_and_excludes_internal_tools():
    available_tools = [
        {
            "name": "crm_lookup",
            "version": "1.2.0",
            "category": "crm",
            "visibility": "public",
        },
        {
            "name": "crm_sync_internal",
            "version": "1.0.0",
            "category": "crm",
            "visibility": "internal",
        },
        {
            "name": "email_send",
            "version": "2.0.0",
            "category": "communication",
            "visibility": "public",
        },
    ]

    result = select_agent_runtime_tools(
        available_tools=available_tools,
        explicit_tool_names=["missing_tool", "crm_lookup"],
        tool_selection={
            "categories": ["crm", "communication"],
            "exclude_names": ["email_send"],
        },
    )

    assert result["tool_names"] == ["missing_tool", "crm_lookup"]
    assert result["tool_versions"] == {"crm_lookup": "1.2.0"}
    assert result["unresolved_explicit_tools"] == ["missing_tool"]
    assert result["tool_definitions"] == [
        {
            "name": "crm_lookup",
            "version": "1.2.0",
            "category": "crm",
            "visibility": "public",
        }
    ]


def test_select_agent_runtime_tools_applies_filters_max_tools_and_stable_order():
    available_tools = [
        {
            "name": "zeta_lookup",
            "version": "1.0.0",
            "category": "crm",
            "visibility": "public",
        },
        {
            "name": "alpha_lookup",
            "version": "1.0.0",
            "category": "crm",
            "visibility": "public",
        },
        {
            "name": "alpha_lookup",
            "version": "2.0.0",
            "category": "crm",
            "visibility": "public",
        },
        {
            "name": "beta_lookup",
            "version": "1.0.0",
            "category": "crm",
            "visibility": "public",
        },
    ]

    result = select_agent_runtime_tools(
        available_tools=available_tools,
        explicit_tool_names=[],
        tool_selection={"categories": ["crm"], "max_tools": 2},
    )

    assert result["tool_names"] == ["alpha_lookup", "beta_lookup"]
    assert result["tool_versions"] == {
        "alpha_lookup": "1.0.0",
        "beta_lookup": "1.0.0",
    }
