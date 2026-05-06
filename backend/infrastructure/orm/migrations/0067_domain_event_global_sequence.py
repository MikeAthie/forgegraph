from django.db import migrations


def create_domain_event_global_sequence(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        """
        CREATE SEQUENCE IF NOT EXISTS domain_event_global_sequence
            AS bigint
            START WITH 1
            INCREMENT BY 1
            NO MINVALUE
            NO MAXVALUE
            CACHE 64
        """
    )
    schema_editor.execute(
        """
        SELECT setval(
            'domain_event_global_sequence',
            GREATEST((SELECT COALESCE(MAX(sequence), 0) FROM domain_events), 1),
            (SELECT COALESCE(MAX(sequence), 0) FROM domain_events) > 0
        )
        """
    )


def drop_domain_event_global_sequence(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("DROP SEQUENCE IF EXISTS domain_event_global_sequence")


class Migration(migrations.Migration):
    dependencies = [
        ("orm", "0066_operator_action_logs"),
    ]

    operations = [
        migrations.RunPython(
            create_domain_event_global_sequence,
            reverse_code=drop_domain_event_global_sequence,
        ),
    ]
