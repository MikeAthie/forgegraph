from __future__ import annotations

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orm", "0063_organization_state_feed_events"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProcessedCallbackEvent",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("event_id", models.CharField(max_length=128)),
                ("idempotency_key", models.CharField(blank=True, default="", max_length=255)),
                ("event_type", models.CharField(max_length=96)),
                ("request_hash", models.CharField(max_length=64)),
                ("response_status", models.PositiveSmallIntegerField(default=200)),
                ("response_body", models.JSONField(blank=True, default=dict)),
                ("resource_type", models.CharField(blank=True, default="", max_length=64)),
                ("resource_id", models.CharField(blank=True, default="", max_length=128)),
                ("status", models.CharField(default="applied", max_length=32)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="processed_callback_events",
                        to="orm.organization",
                    ),
                ),
                (
                    "run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="processed_callback_events",
                        to="orm.run",
                    ),
                ),
            ],
            options={
                "db_table": "processed_callback_events",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="ProcessedDecisionSubmission",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("submit_id", models.CharField(max_length=255)),
                ("request_hash", models.CharField(max_length=64)),
                ("resume_attempt_id", models.UUIDField(blank=True, null=True)),
                ("dispatched_at", models.DateTimeField(blank=True, null=True)),
                ("response_status", models.PositiveSmallIntegerField(default=200)),
                ("response_body", models.JSONField(blank=True, default=dict)),
                ("status", models.CharField(default="applied", max_length=32)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "approval_task",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="processed_submissions",
                        to="orm.approvaltask",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="processed_decision_submissions",
                        to="orm.organization",
                    ),
                ),
                (
                    "run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="processed_decision_submissions",
                        to="orm.run",
                    ),
                ),
            ],
            options={
                "db_table": "processed_decision_submissions",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="ProcessedAccountingEvent",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("event_key", models.CharField(max_length=255)),
                ("event_type", models.CharField(max_length=64)),
                ("request_hash", models.CharField(blank=True, default="", max_length=64)),
                ("status", models.CharField(default="applied", max_length=32)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "cost_ledger_entry",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="processed_accounting_events",
                        to="orm.costledgerentry",
                    ),
                ),
                (
                    "llm_usage",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="processed_accounting_events",
                        to="orm.llmusage",
                    ),
                ),
                (
                    "memory_usage",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="processed_accounting_events",
                        to="orm.memoryusage",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="processed_accounting_events",
                        to="orm.organization",
                    ),
                ),
            ],
            options={
                "db_table": "processed_accounting_events",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="ProcessedMemoryEvent",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("event_id", models.CharField(max_length=128)),
                ("idempotency_key", models.CharField(blank=True, default="", max_length=255)),
                ("event_type", models.CharField(max_length=96)),
                ("request_hash", models.CharField(max_length=64)),
                ("observation_ids_json", models.JSONField(blank=True, default=list)),
                ("response_status", models.PositiveSmallIntegerField(default=200)),
                ("response_body", models.JSONField(blank=True, default=dict)),
                ("status", models.CharField(default="applied", max_length=32)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="processed_memory_events",
                        to="orm.organization",
                    ),
                ),
            ],
            options={
                "db_table": "processed_memory_events",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="processedcallbackevent",
            constraint=models.UniqueConstraint(
                fields=("run", "event_id"), name="processed_callback_run_event_uniq"
            ),
        ),
        migrations.AddConstraint(
            model_name="processedcallbackevent",
            constraint=models.UniqueConstraint(
                condition=models.Q(idempotency_key__gt=""),
                fields=("organization", "idempotency_key"),
                name="processed_callback_org_idem_uniq",
            ),
        ),
        migrations.AddIndex(
            model_name="processedcallbackevent",
            index=models.Index(
                fields=["organization", "created_at"], name="processed_cb_org_time_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="processedcallbackevent",
            index=models.Index(
                fields=["event_type", "created_at"], name="processed_cb_type_time_idx"
            ),
        ),
        migrations.AddConstraint(
            model_name="processeddecisionsubmission",
            constraint=models.UniqueConstraint(
                fields=("organization", "submit_id"), name="processed_decision_org_submit_uniq"
            ),
        ),
        migrations.AddIndex(
            model_name="processeddecisionsubmission",
            index=models.Index(fields=["run", "created_at"], name="processed_dec_run_time_idx"),
        ),
        migrations.AddIndex(
            model_name="processeddecisionsubmission",
            index=models.Index(
                fields=["approval_task", "created_at"], name="processed_dec_task_time_idx"
            ),
        ),
        migrations.AddConstraint(
            model_name="processedaccountingevent",
            constraint=models.UniqueConstraint(
                fields=("organization", "event_key"), name="processed_accounting_org_key_uniq"
            ),
        ),
        migrations.AddIndex(
            model_name="processedaccountingevent",
            index=models.Index(
                fields=["organization", "created_at"], name="processed_acct_org_time_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="processedaccountingevent",
            index=models.Index(
                fields=["event_type", "created_at"], name="processed_acct_type_time_idx"
            ),
        ),
        migrations.AddConstraint(
            model_name="processedmemoryevent",
            constraint=models.UniqueConstraint(
                fields=("organization", "event_id"), name="processed_memory_org_event_uniq"
            ),
        ),
        migrations.AddConstraint(
            model_name="processedmemoryevent",
            constraint=models.UniqueConstraint(
                condition=models.Q(idempotency_key__gt=""),
                fields=("organization", "idempotency_key"),
                name="processed_memory_org_idem_uniq",
            ),
        ),
        migrations.AddIndex(
            model_name="processedmemoryevent",
            index=models.Index(
                fields=["organization", "created_at"], name="processed_mem_org_time_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="processedmemoryevent",
            index=models.Index(
                fields=["event_type", "created_at"], name="processed_mem_type_time_idx"
            ),
        ),
    ]
