import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orm", "0087_departmentmembership_departmentregistry_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="CommunicationEventReceipt",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("consumer_group", models.CharField(max_length=128)),
                ("event_id", models.CharField(blank=True, default="", max_length=255)),
                ("idempotency_key", models.CharField(blank=True, default="", max_length=255)),
                ("topic", models.CharField(blank=True, default="", max_length=255)),
                ("partition", models.IntegerField(blank=True, null=True)),
                ("offset", models.BigIntegerField(blank=True, null=True)),
                ("event_type", models.CharField(blank=True, default="", max_length=128)),
                ("schema_version", models.CharField(blank=True, default="", max_length=64)),
                ("aggregate_type", models.CharField(blank=True, default="", max_length=64)),
                ("aggregate_id", models.CharField(blank=True, default="", max_length=64)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("handled", "Handled"),
                            ("ignored", "Ignored"),
                            ("failed", "Failed"),
                        ],
                        max_length=16,
                    ),
                ),
                ("error_message", models.TextField(blank=True, default="")),
                ("payload_json", models.JSONField(blank=True, default=dict)),
                ("received_at", models.DateTimeField(auto_now_add=True)),
                ("handled_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "company",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="communication_event_receipts",
                        to="orm.graph",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="communication_event_receipts",
                        to="orm.organization",
                    ),
                ),
                (
                    "outbox_event",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="communication_event_receipts",
                        to="orm.domaineventoutbox",
                    ),
                ),
            ],
            options={
                "db_table": "communication_event_receipts",
                "ordering": ["-received_at"],
                "indexes": [
                    models.Index(
                        fields=["consumer_group", "status", "received_at"],
                        name="comm_evt_receipt_group_idx",
                    ),
                    models.Index(
                        fields=["event_type", "received_at"],
                        name="comm_evt_receipt_type_idx",
                    ),
                    models.Index(
                        fields=["organization", "status", "received_at"],
                        name="comm_evt_receipt_org_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(("event_id__gt", "")),
                        fields=("consumer_group", "event_id"),
                        name="comm_evt_receipt_event_uniq",
                    ),
                    models.UniqueConstraint(
                        condition=models.Q(("idempotency_key__gt", "")),
                        fields=("consumer_group", "idempotency_key"),
                        name="comm_evt_receipt_idem_uniq",
                    ),
                ],
            },
        ),
    ]
