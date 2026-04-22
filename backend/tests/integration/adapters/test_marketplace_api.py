from django.test import override_settings
from django.utils import timezone

from infrastructure.orm.models import (
    NodePackageInstallation,
    NodeRegistryPackage,
    NodeRegistryRelease,
    Organization,
)
from infrastructure.security import s2s


def test_marketplace_catalog_install_and_list_installed(authenticated_client, user):
    package = NodeRegistryPackage.objects.create(
        slug="test-webhook-tools",
        name="Webhook Tools",
        summary="Utilities for webhook automation.",
        category="developer",
    )
    release = NodeRegistryRelease.objects.create(
        package=package,
        version="1.0.0",
        status="approved",
        package_kind="template_http",
        execution_node_type="http",
        ui_schema={"label": "Webhook Tools"},
        config_schema={"type": "object"},
        config_defaults={"method": "GET", "url": "https://example.com"},
        cloud_allowed=True,
    )

    catalog_response = authenticated_client.get("/api/marketplace/packages")
    assert catalog_response.status_code == 200
    catalog_items = catalog_response.json()["data"]
    assert any(item["slug"] == package.slug for item in catalog_items)

    install_response = authenticated_client.post(
        f"/api/marketplace/packages/{package.slug}/install",
        data={},
        format="json",
    )
    assert install_response.status_code == 201
    assert install_response.json()["data"]["installed_release"]["version"] == release.version

    assert NodePackageInstallation.objects.filter(
        organization=user.default_organization,
        package=package,
        release=release,
    ).exists()

    installed_response = authenticated_client.get("/api/marketplace/installed")
    assert installed_response.status_code == 200
    installed_items = installed_response.json()["data"]
    assert any(item["slug"] == package.slug for item in installed_items)


def test_marketplace_release_submission_and_review(authenticated_client):
    submit_response = authenticated_client.post(
        "/api/marketplace/releases",
        data={
            "package_slug": "acme-release-test",
            "package_name": "Acme Release Test",
            "version": "1.0.0",
            "manifest_version": 2,
            "package_kind": "runtime_tool",
            "execution_node_type": "tool",
            "ui_schema": {"label": "Acme Tool"},
            "config_schema": {"type": "object"},
            "config_defaults": {"tool": "acme_lookup"},
            "runtime_manifest": {
                "name": "acme_lookup",
                "version": "1.0.0",
                "category": "crm",
                "input_schema": {"type": "object"},
                "execution": {
                    "type": "http",
                    "timeout_seconds": 10,
                    "http": {"url": "https://example.com/tool", "method": "POST"},
                },
                "side_effects": {"type": "read", "idempotent": True},
                "visibility": "public",
            },
            "cloud_allowed": True,
        },
        format="json",
    )
    assert submit_response.status_code == 201
    release_id = submit_response.json()["data"]["id"]
    assert submit_response.json()["data"]["package_kind"] == "runtime_tool"

    review_response = authenticated_client.patch(
        f"/api/marketplace/releases/{release_id}/review",
        data={"decision": "approved"},
        format="json",
    )
    assert review_response.status_code == 200

    release = NodeRegistryRelease.objects.get(id=release_id)
    assert release.status == "approved"
    assert isinstance(release.runtime_manifest, dict)
    assert release.runtime_manifest["name"] == "acme_lookup"


@override_settings(FORGEGRAPH_RUNTIME_MODE="cloud")
def test_marketplace_release_review_blocks_exec_runtime_release_in_cloud(authenticated_client):
    package = NodeRegistryPackage.objects.create(
        slug="blocked-exec-review",
        name="Blocked Exec Review",
        summary="Exec runtime release",
        category="developer",
    )
    release = NodeRegistryRelease.objects.create(
        package=package,
        version="1.0.0",
        status="pending_review",
        package_kind="runtime_tool",
        execution_node_type="tool",
        manifest_version=1,
        config_defaults={"tool": "blocked_exec_review"},
        runtime_manifest={
            "name": "blocked_exec_review",
            "version": "1.0.0",
            "kind": "exec",
            "input_schema": {"type": "object"},
            "exec": {"command": "python"},
        },
        cloud_allowed=True,
    )

    response = authenticated_client.patch(
        f"/api/marketplace/releases/{release.id}/review",
        data={"decision": "approved"},
        format="json",
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "POLICY_DENIED"
    release.refresh_from_db()
    assert release.status == "pending_review"


def test_marketplace_release_submission_rejects_runtime_release_without_manifest(
    authenticated_client,
):
    response = authenticated_client.post(
        "/api/marketplace/releases",
        data={
            "package_slug": "missing-runtime-manifest",
            "package_name": "Missing Runtime Manifest",
            "version": "1.0.0",
            "package_kind": "runtime_tool",
            "execution_node_type": "tool",
            "config_defaults": {"tool": "lookup_customer"},
        },
        format="json",
    )

    assert response.status_code == 400
    details = response.json()["error"]["details"]
    assert any(detail["field"] == "runtime_manifest" for detail in details)


def test_marketplace_release_submission_rejects_template_release_with_runtime_manifest(
    authenticated_client,
):
    response = authenticated_client.post(
        "/api/marketplace/releases",
        data={
            "package_slug": "template-release-invalid",
            "package_name": "Template Release Invalid",
            "version": "1.0.0",
            "manifest_version": 2,
            "package_kind": "template_http",
            "execution_node_type": "http",
            "config_defaults": {"url": "https://example.com"},
            "runtime_manifest": {
                "name": "should_not_exist",
                "version": "1.0.0",
                "category": "developer",
                "input_schema": {"type": "object"},
                "execution": {
                    "type": "http",
                    "timeout_seconds": 10,
                    "http": {"url": "https://example.com/tool"},
                },
                "side_effects": {"type": "read", "idempotent": True},
            },
        },
        format="json",
    )

    assert response.status_code == 400
    details = response.json()["error"]["details"]
    assert any(detail["field"] == "runtime_manifest" for detail in details)


def test_marketplace_catalog_includes_seeded_top_integrations(authenticated_client):
    required_packages = [
        ("slack-alerts", "Slack Alerts", "communication"),
        ("notion-page-upsert", "Notion Page Upsert", "productivity"),
        ("jira-issue-create", "Jira Issue Create", "developer"),
        ("linear-issue-create", "Linear Issue Create", "developer"),
        ("gmail-send-email", "Gmail Send Email", "communication"),
        ("google-drive-file-create", "Google Drive File Create", "storage"),
        ("hubspot-contact-upsert", "HubSpot Contact Upsert", "crm"),
        ("telegram-send-message", "Telegram Send Message", "communication"),
        ("discord-send-message", "Discord Send Message", "communication"),
        ("webhook-dispatch", "Webhook Dispatch", "developer"),
    ]
    for slug, name, category in required_packages:
        package, _ = NodeRegistryPackage.objects.update_or_create(
            slug=slug,
            defaults={
                "name": name,
                "summary": f"{name} integration",
                "category": category,
                "is_active": True,
            },
        )
        NodeRegistryRelease.objects.update_or_create(
            package=package,
            version="1.0.0",
            defaults={
                "status": "approved",
                "package_kind": "runtime_tool",
                "execution_node_type": "tool",
                "manifest_version": 2,
                "ui_schema": {"label": name},
                "config_schema": {"type": "object"},
                "config_defaults": {"tool": slug.replace("-", "_")},
                "runtime_manifest": {
                    "name": slug.replace("-", "_"),
                    "version": "1.0.0",
                    "category": category,
                    "input_schema": {"type": "object"},
                    "execution": {
                        "type": "http",
                        "timeout_seconds": 10,
                        "http": {"url": f"https://example.com/{slug}", "method": "POST"},
                    },
                    "side_effects": {"type": "read", "idempotent": True},
                },
                "cloud_allowed": True,
            },
        )

    response = authenticated_client.get("/api/marketplace/packages")
    assert response.status_code == 200
    slugs = {item["slug"] for item in response.json()["data"]}
    assert len(slugs) >= 10
    assert "slack-alerts" in slugs
    assert "notion-page-upsert" in slugs
    assert "jira-issue-create" in slugs
    assert "linear-issue-create" in slugs
    assert "gmail-send-email" in slugs
    assert "google-drive-file-create" in slugs
    assert "hubspot-contact-upsert" in slugs
    assert "telegram-send-message" in slugs


@override_settings(FORGEGRAPH_RUNTIME_MODE="cloud")
def test_marketplace_install_blocks_exec_runtime_release_in_cloud(authenticated_client, user):
    package = NodeRegistryPackage.objects.create(
        slug="blocked-exec-install",
        name="Blocked Exec Install",
        summary="Exec runtime release",
        category="developer",
    )
    NodeRegistryRelease.objects.create(
        package=package,
        version="1.0.0",
        status="approved",
        package_kind="runtime_tool",
        execution_node_type="tool",
        manifest_version=1,
        config_defaults={"tool": "blocked_exec_install"},
        runtime_manifest={
            "name": "blocked_exec_install",
            "version": "1.0.0",
            "kind": "exec",
            "input_schema": {"type": "object"},
            "exec": {"command": "python"},
        },
        cloud_allowed=True,
    )

    response = authenticated_client.post(
        f"/api/marketplace/packages/{package.slug}/install",
        data={},
        format="json",
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "POLICY_DENIED"
    assert not NodePackageInstallation.objects.filter(
        organization=user.default_organization,
        package=package,
    ).exists()


def test_marketplace_installed_payload_supports_quick_toolbar_contract(authenticated_client, user):
    package = NodeRegistryPackage.objects.create(
        slug="quick-toolbar-contract",
        name="Quick Toolbar Contract",
        summary="Contract test package for quick toolbar integration",
        category="developer",
        icon="sparkles",
    )
    release = NodeRegistryRelease.objects.create(
        package=package,
        version="1.0.0",
        status="approved",
        package_kind="template_http",
        execution_node_type="http",
        ui_schema={"label": "Quick Contract Node"},
        config_schema={"type": "object"},
        config_defaults={"method": "POST", "url": "https://example.com/hook"},
        cloud_allowed=True,
    )
    NodePackageInstallation.objects.create(
        organization=user.default_organization,
        package=package,
        release=release,
        install_metadata={
            "source": "marketplace",
            "runtime_delivery": {"state": "template"},
        },
    )

    response = authenticated_client.get("/api/marketplace/installed")
    assert response.status_code == 200
    data = response.json()["data"]
    item = next(entry for entry in data if entry["slug"] == package.slug)
    assert item["name"] == package.name
    assert item["icon"] == package.icon
    assert item["install_metadata"]["source"] == "marketplace"
    assert item["install_metadata"]["runtime_delivery"]["state"] == "template"
    assert item["installed_release"]["package_kind"] == "template_http"
    assert item["installed_release"]["cloud_allowed"] is True
    assert item["installed_release"]["execution_node_type"] == "http"
    assert item["installed_release"]["config_defaults"]["url"] == "https://example.com/hook"
    assert item["latest_release"]["ui_schema"]["label"] == "Quick Contract Node"
    assert item["runtime_delivery"]["state"] == "template"


@override_settings(ENGINE_CALLBACK_SECRET="test-secret")
def test_marketplace_runtime_manifest_endpoint_returns_ready_runtime_tools(api_client, user):
    org = user.default_organization
    assert org is not None

    ready_package = NodeRegistryPackage.objects.create(
        slug="crm-lookup",
        name="CRM Lookup",
        summary="Runtime tool",
        category="developer",
    )
    ready_release = NodeRegistryRelease.objects.create(
        package=ready_package,
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
        },
    )
    NodePackageInstallation.objects.create(
        organization=org,
        package=ready_package,
        release=ready_release,
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

    timestamp_ms = str(int(timezone.now().timestamp() * 1000))
    signature = s2s.build_signature("test-secret", timestamp_ms, b"")
    response = api_client.get(
        f"/api/marketplace/runtime-manifests?tenant_id={org.id}",
        HTTP_X_FORGEGRAPH_TIMESTAMP=timestamp_ms,
        HTTP_X_FORGEGRAPH_SIGNATURE=signature,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["tenant_id"] == str(org.id)
    assert data["manifest_version"] == 2
    assert len(data["tools"]) == 1
    assert data["tools"][0]["name"] == "crm_lookup"
    assert data["tools"][0]["execution"]["type"] == "http"
    assert {item["package_slug"] for item in data["packages"]} == {"crm-lookup", "template-http"}
    assert response["ETag"] == data["checksum"]


@override_settings(ENGINE_CALLBACK_SECRET="test-secret")
def test_marketplace_runtime_manifest_endpoint_supports_etag(api_client, user):
    org = user.default_organization
    assert org is not None

    package = NodeRegistryPackage.objects.create(
        slug="crm-lookup",
        name="CRM Lookup",
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
        config_defaults={"tool": "crm_lookup"},
        runtime_manifest={
            "name": "crm_lookup",
            "version": "1.0.0",
            "category": "crm",
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
        organization=org,
        package=package,
        release=release,
        install_metadata={},
    )

    timestamp_ms = str(int(timezone.now().timestamp() * 1000))
    signature = s2s.build_signature("test-secret", timestamp_ms, b"")
    first = api_client.get(
        f"/api/marketplace/runtime-manifests?tenant_id={org.id}",
        HTTP_X_FORGEGRAPH_TIMESTAMP=timestamp_ms,
        HTTP_X_FORGEGRAPH_SIGNATURE=signature,
    )

    etag = first["ETag"]
    second = api_client.get(
        f"/api/marketplace/runtime-manifests?tenant_id={org.id}",
        HTTP_X_FORGEGRAPH_TIMESTAMP=timestamp_ms,
        HTTP_X_FORGEGRAPH_SIGNATURE=signature,
        HTTP_IF_NONE_MATCH=etag,
    )

    assert second.status_code == 304
    assert second["ETag"] == etag


def test_marketplace_runtime_manifest_preview_requires_admin(authenticated_client, user):
    membership = user.organization_memberships.get(organization=user.default_organization)
    membership.role = "member"
    membership.save(update_fields=["role"])

    response = authenticated_client.get("/api/marketplace/runtime-manifest-preview")
    assert response.status_code == 403


def test_marketplace_runtime_manifest_preview_returns_tenant_payload(authenticated_client, user):
    org = user.default_organization
    assert org is not None

    package = NodeRegistryPackage.objects.create(
        slug="preview-ready-tool",
        name="Preview Ready Tool",
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
        config_defaults={"tool": "preview_ready_tool"},
        runtime_manifest={
            "name": "preview_ready_tool",
            "version": "1.0.0",
            "category": "developer",
            "input_schema": {"type": "object"},
            "execution": {
                "type": "http",
                "timeout_seconds": 10,
                "http": {"url": "https://example.com/preview", "method": "POST"},
            },
            "side_effects": {"type": "read", "idempotent": True},
        },
    )
    NodePackageInstallation.objects.create(
        organization=org,
        package=package,
        release=release,
        install_metadata={},
    )

    response = authenticated_client.get("/api/marketplace/runtime-manifest-preview")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["tenant_id"] == str(org.id)
    assert len(data["tools"]) == 1
    assert data["tools"][0]["name"] == "preview_ready_tool"
    assert data["packages"][0]["delivery_state"] == "ready"
    assert data["packages"][0]["package_slug"] == "preview-ready-tool"


@override_settings(ENGINE_CALLBACK_SECRET="test-secret")
def test_marketplace_runtime_manifest_endpoint_is_tenant_scoped(api_client, user):
    org = user.default_organization
    assert org is not None
    other_org = Organization.objects.create(
        id="00000000-0000-0000-0000-000000000123",
        name="Other Tenant",
    )

    package = NodeRegistryPackage.objects.create(
        slug="other-tenant-tool",
        name="Other Tenant Tool",
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
        config_defaults={"tool": "other_tenant"},
        runtime_manifest={
            "name": "other_tenant",
            "version": "1.0.0",
            "category": "developer",
            "input_schema": {"type": "object"},
            "execution": {
                "type": "http",
                "timeout_seconds": 10,
                "http": {"url": "https://example.com/other", "method": "POST"},
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

    timestamp_ms = str(int(timezone.now().timestamp() * 1000))
    signature = s2s.build_signature("test-secret", timestamp_ms, b"")
    response = api_client.get(
        f"/api/marketplace/runtime-manifests?tenant_id={org.id}",
        HTTP_X_FORGEGRAPH_TIMESTAMP=timestamp_ms,
        HTTP_X_FORGEGRAPH_SIGNATURE=signature,
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["tools"] == []
    assert data["packages"] == []
