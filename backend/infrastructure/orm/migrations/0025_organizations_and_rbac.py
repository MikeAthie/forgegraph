from __future__ import annotations

import uuid

from django.db import migrations, models


def seed_organizations(apps, schema_editor) -> None:
    User = apps.get_model("orm", "User")
    Organization = apps.get_model("orm", "Organization")
    OrganizationMembership = apps.get_model("orm", "OrganizationMembership")
    APIKey = apps.get_model("orm", "APIKey")
    MemoryUsage = apps.get_model("orm", "MemoryUsage")
    LLMUsage = apps.get_model("orm", "LLMUsage")
    LLMBudget = apps.get_model("orm", "LLMBudget")
    LLMQuota = apps.get_model("orm", "LLMQuota")
    AuditLog = apps.get_model("orm", "AuditLog")
    TenantPolicy = apps.get_model("orm", "TenantPolicy")
    MemoryChunk = apps.get_model("orm", "MemoryChunk")

    user_org_map: dict[uuid.UUID, uuid.UUID] = {}

    for user in User.objects.all():
        if user.default_organization_id:
            org = Organization.objects.filter(id=user.default_organization_id).first()
            if not org:
                org = Organization.objects.create(name=f"{user.email.split('@')[0]} Org")
                User.objects.filter(pk=user.pk).update(default_organization=org)
        else:
            org = Organization.objects.create(name=f"{user.email.split('@')[0]} Org")
            User.objects.filter(pk=user.pk).update(default_organization=org)

        OrganizationMembership.objects.get_or_create(
            organization=org,
            user=user,
            defaults={"role": "owner", "is_default": True},
        )
        user_org_map[user.id] = org.id

    for user_id, org_id in user_org_map.items():
        MemoryUsage.objects.filter(tenant_id=user_id).update(tenant_id=org_id)
        LLMUsage.objects.filter(tenant_id=user_id).update(tenant_id=org_id)
        LLMBudget.objects.filter(tenant_id=user_id).update(tenant_id=org_id)
        LLMQuota.objects.filter(tenant_id=user_id).update(tenant_id=org_id)
        AuditLog.objects.filter(tenant_id=user_id).update(tenant_id=org_id)
        TenantPolicy.objects.filter(tenant_id=user_id).update(tenant_id=org_id)
        MemoryChunk.objects.filter(tenant_id=user_id).update(tenant_id=org_id)

    for key in APIKey.objects.filter(organization__isnull=True):
        if key.user_id in user_org_map:
            APIKey.objects.filter(pk=key.pk).update(organization_id=user_org_map[key.user_id])


def noop_reverse(apps, schema_editor) -> None:
    return None


class Migration(migrations.Migration):
    dependencies = [
        ("orm", "0024_tenant_policy"),
    ]

    operations = [
        migrations.CreateModel(
            name="Organization",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("name", models.CharField(max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "organizations",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="OrganizationMembership",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("owner", "Owner"),
                            ("admin", "Admin"),
                            ("member", "Member"),
                            ("viewer", "Viewer"),
                        ],
                        default="member",
                        max_length=16,
                    ),
                ),
                ("is_default", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="memberships",
                        to="orm.organization",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="organization_memberships",
                        to="orm.user",
                    ),
                ),
            ],
            options={
                "db_table": "organization_memberships",
                "unique_together": {("organization", "user")},
            },
        ),
        migrations.AddField(
            model_name="user",
            name="default_organization",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name="default_users",
                to="orm.organization",
            ),
        ),
        migrations.AddField(
            model_name="apikey",
            name="organization",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.CASCADE,
                related_name="api_keys",
                to="orm.organization",
            ),
        ),
        migrations.AddIndex(
            model_name="organizationmembership",
            index=models.Index(fields=["organization", "role"], name="org_membership_role_idx"),
        ),
        migrations.AddIndex(
            model_name="organizationmembership",
            index=models.Index(fields=["user", "organization"], name="org_membership_user_idx"),
        ),
        migrations.RunPython(seed_organizations, noop_reverse),
        migrations.AlterField(
            model_name="apikey",
            name="organization",
            field=models.ForeignKey(
                on_delete=models.deletion.CASCADE,
                related_name="api_keys",
                to="orm.organization",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="apikey",
            unique_together={("organization", "provider", "name")},
        ),
        migrations.AddIndex(
            model_name="apikey",
            index=models.Index(
                fields=["organization", "provider"], name="api_keys_org_provider_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="apikey",
            index=models.Index(fields=["user"], name="api_keys_user_idx"),
        ),
        migrations.RemoveIndex(
            model_name="apikey",
            name="api_keys_user_provider_idx",
        ),
    ]
