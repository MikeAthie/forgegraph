import uuid

from django.db import migrations, models


def seed_marketplace_packages(apps, schema_editor):
    NodeRegistryPackage = apps.get_model("orm", "NodeRegistryPackage")
    NodeRegistryRelease = apps.get_model("orm", "NodeRegistryRelease")

    packages = [
        {
            "slug": "slack-alerts",
            "name": "Slack Alerts",
            "summary": "Send formatted alerts and workflow summaries to Slack channels.",
            "category": "communication",
            "icon": "slack",
            "execution_node_type": "http",
            "config_defaults": {
                "method": "POST",
                "url": "https://slack.com/api/chat.postMessage",
                "headers": {"Content-Type": "application/json"},
                "body": '{"channel":"#ops","text":"{{input.message}}"}',
                "output_key": "slack_response",
            },
        },
        {
            "slug": "notion-page-upsert",
            "name": "Notion Page Upsert",
            "summary": "Create or update Notion pages from workflow data.",
            "category": "productivity",
            "icon": "notion",
            "execution_node_type": "http",
            "config_defaults": {
                "method": "POST",
                "url": "https://api.notion.com/v1/pages",
                "headers": {"Notion-Version": "2022-06-28", "Content-Type": "application/json"},
                "body": '{"parent":{"database_id":"{{input.database_id}}"},"properties":{{input.properties}}}',
                "output_key": "notion_response",
            },
        },
        {
            "slug": "jira-issue-create",
            "name": "Jira Issue Create",
            "summary": "Create Jira issues from incidents and approval outcomes.",
            "category": "developer",
            "icon": "jira",
            "execution_node_type": "http",
            "config_defaults": {
                "method": "POST",
                "url": "https://your-domain.atlassian.net/rest/api/3/issue",
                "headers": {"Content-Type": "application/json"},
                "body": '{"fields":{{input.fields}}}',
                "output_key": "jira_issue",
            },
        },
    ]

    for item in packages:
        package, _ = NodeRegistryPackage.objects.get_or_create(
            slug=item["slug"],
            defaults={
                "id": uuid.uuid4(),
                "name": item["name"],
                "summary": item["summary"],
                "category": item["category"],
                "icon": item["icon"],
                "is_active": True,
            },
        )

        NodeRegistryRelease.objects.get_or_create(
            package=package,
            version="1.0.0",
            defaults={
                "status": "approved",
                "execution_node_type": item["execution_node_type"],
                "changelog": "Initial marketplace release.",
                "ui_schema": {
                    "label": item["name"],
                    "description": item["summary"],
                    "category": "integration",
                },
                "config_schema": {
                    "type": "object",
                    "properties": {
                        "method": {"type": "string"},
                        "url": {"type": "string"},
                        "headers": {"type": "object"},
                        "body": {"type": "string"},
                        "output_key": {"type": "string"},
                    },
                    "required": ["method", "url"],
                },
                "config_defaults": item["config_defaults"],
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("orm", "0030_run_queue"),
    ]

    operations = [
        migrations.CreateModel(
            name="NodeRegistryPackage",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)),
                ("slug", models.SlugField(max_length=100, unique=True)),
                ("name", models.CharField(max_length=120)),
                ("summary", models.TextField(blank=True, default="")),
                (
                    "category",
                    models.CharField(
                        max_length=32,
                        choices=[
                            ("communication", "Communication"),
                            ("productivity", "Productivity"),
                            ("crm", "CRM"),
                            ("storage", "Storage"),
                            ("developer", "Developer"),
                            ("other", "Other"),
                        ],
                        default="other",
                    ),
                ),
                ("icon", models.CharField(max_length=32, blank=True, default="")),
                ("docs_url", models.URLField(blank=True, default="")),
                ("homepage_url", models.URLField(blank=True, default="")),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "owner_organization",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.SET_NULL,
                        related_name="published_node_packages",
                        to="orm.organization",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.SET_NULL,
                        related_name="published_node_packages",
                        to="orm.user",
                    ),
                ),
            ],
            options={
                "db_table": "node_registry_packages",
                "ordering": ["name"],
            },
        ),
        migrations.AddIndex(
            model_name="noderegistrypackage",
            index=models.Index(
                fields=["is_active", "category"], name="node_pkg_active_category_idx"
            ),
        ),
        migrations.CreateModel(
            name="NodeRegistryRelease",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)),
                ("version", models.CharField(max_length=32)),
                ("changelog", models.TextField(blank=True, default="")),
                (
                    "status",
                    models.CharField(
                        max_length=32,
                        choices=[
                            ("draft", "Draft"),
                            ("pending_review", "Pending Review"),
                            ("approved", "Approved"),
                            ("rejected", "Rejected"),
                        ],
                        default="draft",
                    ),
                ),
                (
                    "execution_node_type",
                    models.CharField(
                        max_length=32,
                        choices=[
                            ("http", "HTTP"),
                            ("prompt", "Prompt"),
                            ("tool", "Tool"),
                            ("transform", "Transform"),
                        ],
                    ),
                ),
                ("ui_schema", models.JSONField(blank=True, default=dict)),
                ("config_schema", models.JSONField(blank=True, default=dict)),
                ("config_defaults", models.JSONField(blank=True, default=dict)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "package",
                    models.ForeignKey(
                        on_delete=models.CASCADE,
                        related_name="releases",
                        to="orm.noderegistrypackage",
                    ),
                ),
                (
                    "reviewed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.SET_NULL,
                        related_name="reviewed_node_releases",
                        to="orm.user",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.SET_NULL,
                        related_name="node_releases",
                        to="orm.user",
                    ),
                ),
            ],
            options={
                "db_table": "node_registry_releases",
                "ordering": ["-created_at"],
                "unique_together": {("package", "version")},
            },
        ),
        migrations.AddIndex(
            model_name="noderegistryrelease",
            index=models.Index(fields=["status", "created_at"], name="node_rel_status_time_idx"),
        ),
        migrations.AddIndex(
            model_name="noderegistryrelease",
            index=models.Index(fields=["package", "status"], name="node_rel_package_status_idx"),
        ),
        migrations.CreateModel(
            name="NodePackageInstallation",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)),
                ("is_active", models.BooleanField(default=True)),
                ("install_metadata", models.JSONField(blank=True, default=dict)),
                ("installed_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=models.CASCADE,
                        related_name="installed_node_packages",
                        to="orm.organization",
                    ),
                ),
                (
                    "package",
                    models.ForeignKey(
                        on_delete=models.CASCADE,
                        related_name="installations",
                        to="orm.noderegistrypackage",
                    ),
                ),
                (
                    "release",
                    models.ForeignKey(
                        on_delete=models.PROTECT,
                        related_name="installations",
                        to="orm.noderegistryrelease",
                    ),
                ),
                (
                    "installed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.SET_NULL,
                        related_name="installed_node_packages",
                        to="orm.user",
                    ),
                ),
            ],
            options={
                "db_table": "node_package_installations",
                "unique_together": {("organization", "package")},
            },
        ),
        migrations.AddIndex(
            model_name="nodepackageinstallation",
            index=models.Index(
                fields=["organization", "is_active"], name="node_install_org_active_idx"
            ),
        ),
        migrations.RunPython(seed_marketplace_packages, migrations.RunPython.noop),
    ]
