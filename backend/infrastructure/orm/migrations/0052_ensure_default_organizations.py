from django.db import migrations


def ensure_default_organizations(apps, schema_editor):
    user_model = apps.get_model("orm", "User")
    organization_model = apps.get_model("orm", "Organization")
    membership_model = apps.get_model("orm", "OrganizationMembership")

    for user in user_model.objects.all().iterator():
        default_org_id = getattr(user, "default_organization_id", None)
        default_membership = None

        if default_org_id:
            default_membership = membership_model.objects.filter(
                user_id=user.pk,
                organization_id=default_org_id,
            ).first()
            if default_membership is None:
                default_membership = membership_model.objects.create(
                    user_id=user.pk,
                    organization_id=default_org_id,
                    role="owner",
                    is_default=True,
                )
        else:
            default_membership = (
                membership_model.objects.filter(user_id=user.pk, is_default=True)
                .order_by("created_at")
                .first()
            )
            if default_membership is None:
                default_membership = (
                    membership_model.objects.filter(user_id=user.pk)
                    .order_by("created_at")
                    .first()
                )
            if default_membership is None:
                email = getattr(user, "email", "") or "Organization"
                local_name = email.split("@", 1)[0] or "Organization"
                organization = organization_model.objects.create(
                    name=f"{local_name}'s Organization",
                )
                default_membership = membership_model.objects.create(
                    user_id=user.pk,
                    organization=organization,
                    role="owner",
                    is_default=True,
                )

            user_model.objects.filter(pk=user.pk).update(
                default_organization_id=default_membership.organization_id,
            )

        membership_model.objects.filter(user_id=user.pk, is_default=True).exclude(
            pk=default_membership.pk,
        ).update(is_default=False)
        if not default_membership.is_default:
            membership_model.objects.filter(pk=default_membership.pk).update(is_default=True)


class Migration(migrations.Migration):

    dependencies = [
        ("orm", "0051_organization_scoped_runtime_objects"),
    ]

    operations = [
        migrations.RunPython(ensure_default_organizations, migrations.RunPython.noop),
    ]
