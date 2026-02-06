from infrastructure.orm.models import (
    NodePackageInstallation,
    NodeRegistryPackage,
    NodeRegistryRelease,
)


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
        execution_node_type="http",
        ui_schema={"label": "Webhook Tools"},
        config_schema={"type": "object"},
        config_defaults={"method": "GET", "url": "https://example.com"},
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
            "execution_node_type": "tool",
            "ui_schema": {"label": "Acme Tool"},
            "config_schema": {"type": "object"},
            "config_defaults": {"tool": "acme_lookup"},
        },
        format="json",
    )
    assert submit_response.status_code == 201
    release_id = submit_response.json()["data"]["id"]

    review_response = authenticated_client.patch(
        f"/api/marketplace/releases/{release_id}/review",
        data={"decision": "approved"},
        format="json",
    )
    assert review_response.status_code == 200

    release = NodeRegistryRelease.objects.get(id=release_id)
    assert release.status == "approved"


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
                "execution_node_type": "tool",
                "ui_schema": {"label": name},
                "config_schema": {"type": "object"},
                "config_defaults": {},
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
        execution_node_type="http",
        ui_schema={"label": "Quick Contract Node"},
        config_schema={"type": "object"},
        config_defaults={"method": "POST", "url": "https://example.com/hook"},
    )
    NodePackageInstallation.objects.create(
        organization=user.default_organization,
        package=package,
        release=release,
    )

    response = authenticated_client.get("/api/marketplace/installed")
    assert response.status_code == 200
    data = response.json()["data"]
    item = next(entry for entry in data if entry["slug"] == package.slug)
    assert item["name"] == package.name
    assert item["icon"] == package.icon
    assert item["installed_release"]["execution_node_type"] == "http"
    assert item["installed_release"]["config_defaults"]["url"] == "https://example.com/hook"
    assert item["latest_release"]["ui_schema"]["label"] == "Quick Contract Node"
