from __future__ import annotations

import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


def _node_type(node: dict) -> str:
    data = node.get("data") if isinstance(node.get("data"), dict) else {}
    return str(node.get("type") or data.get("type") or data.get("node_type") or "").strip()


def _node_label(node: dict) -> str:
    data = node.get("data") if isinstance(node.get("data"), dict) else {}
    return str(node.get("name") or data.get("label") or data.get("name") or node.get("id") or "Task").strip()


def _is_executable_node(node: dict) -> bool:
    return _node_type(node).lower() not in {"input", "output", "trigger", "note", "comment"}


def backfill_task_lifecycle(apps, schema_editor) -> None:
    Run = apps.get_model("orm", "Run")
    NodeRun = apps.get_model("orm", "NodeRun")
    TaskLifecycleRecord = apps.get_model("orm", "TaskLifecycleRecord")
    TaskAttemptRecord = apps.get_model("orm", "TaskAttemptRecord")
    TaskLifecycleEvent = apps.get_model("orm", "TaskLifecycleEvent")
    TaskRecord = apps.get_model("orm", "TaskRecord")
    ApprovalTask = apps.get_model("orm", "ApprovalTask")
    DecisionRecord = apps.get_model("orm", "DecisionRecord")

    node_status_map = {
        "pending": "queued",
        "running": "running",
        "waiting": "waiting_for_decision",
        "succeeded": "completed",
        "failed": "failed",
        "skipped": "cancelled",
    }
    for run in Run.objects.select_related("owner", "organization", "graph_version__graph").iterator():
        organization_id = run.organization_id or run.graph_version.graph.organization_id or run.owner.default_organization_id
        if not organization_id:
            continue

        graph_json = run.dispatch_graph_json if isinstance(run.dispatch_graph_json, dict) else None
        if not isinstance(graph_json, dict):
            graph_json = run.graph_version.graph_json if isinstance(run.graph_version.graph_json, dict) else {}

        nodes_by_id = {
            str(node.get("id") or ""): node
            for node in graph_json.get("nodes", [])
            if isinstance(node, dict) and str(node.get("id") or "")
        }
        executable_ids = {
            node_id for node_id, node in nodes_by_id.items() if _is_executable_node(node)
        }
        node_runs = list(NodeRun.objects.filter(run=run).order_by("started_at", "attempt", "id"))
        executable_ids.update(node_run.node_id for node_run in node_runs)

        for node_id in executable_ids:
            node = nodes_by_id.get(node_id, {})
            node_type = _node_type(node)
            latest = next((node_run for node_run in reversed(node_runs) if node_run.node_id == node_id), None)
            status = node_status_map.get(latest.status, "created") if latest else "created"
            if run.status == "failed" and status not in {"completed", "failed", "dead_lettered", "cancelled"}:
                status = "failed"
            if run.status == "canceled" and status not in {"completed", "failed", "dead_lettered", "cancelled"}:
                status = "cancelled"
            task, _ = TaskLifecycleRecord.objects.get_or_create(
                organization_id=organization_id,
                external_key=f"{run.id}:{node_id}",
                defaults={
                    "run_id": run.id,
                    "source_node_id": node_id,
                    "node_type": node_type or (latest.node_type if latest else ""),
                    "title": f"{_node_label(node)} task",
                    "status": status,
                    "priority": "urgent" if status in {"failed", "dead_lettered"} else "high" if status in {"waiting_for_decision", "paused", "retry_scheduled"} else "normal",
                    "summary": f"{node_id} is {status.replace('_', ' ')}.",
                    "current_attempt": latest.attempt if latest else 1,
                    "current_node_run_id": latest.id if latest else None,
                    "started_at": latest.started_at if latest else run.started_at,
                    "ended_at": latest.ended_at if latest else run.ended_at if status in {"completed", "failed", "cancelled"} else None,
                    "last_transition_at": latest.ended_at or latest.started_at if latest else run.started_at,
                    "recovery_options": ["inspect_run"] if status in {"failed", "dead_lettered"} else [],
                },
            )
            attempt_number = latest.attempt if latest else 1
            TaskAttemptRecord.objects.get_or_create(
                lifecycle_task_id=task.id,
                attempt_number=attempt_number,
                defaults={
                    "run_id": run.id,
                    "node_run_id": latest.id if latest else None,
                    "owner_component": "backfill",
                    "status": "completed" if status == "completed" else "failed" if status == "failed" else "running" if status in {"running", "waiting_for_decision", "paused"} else "created",
                    "started_at": latest.started_at if latest else run.started_at,
                    "ended_at": latest.ended_at if latest else run.ended_at if status in {"completed", "failed", "cancelled"} else None,
                },
            )
            try:
                TaskLifecycleEvent.objects.get_or_create(
                    organization_id=organization_id,
                    idempotency_key=f"backfill:{run.id}:{node_id}:{attempt_number}:{status}",
                    defaults={
                        "run_id": run.id,
                        "lifecycle_task_id": task.id,
                        "source": "backfill",
                        "event_type": "task_lifecycle.backfill",
                        "from_status": "",
                        "to_status": status,
                        "attempt_number": attempt_number,
                        "outcome": "accepted",
                        "reason": "Backfilled from existing runtime rows.",
                        "payload": {},
                        "occurred_at": task.last_transition_at or django.utils.timezone.now(),
                    },
                )
            except Exception:
                pass
            TaskRecord.objects.filter(organization_id=organization_id, external_key=f"{run.id}:{node_id}").update(lifecycle_task_id=task.id)
            ApprovalTask.objects.filter(run_id=run.id, node_id=node_id, task_lifecycle_id__isnull=True).update(task_lifecycle_id=task.id)
            DecisionRecord.objects.filter(organization_id=organization_id, execution_id=run.id, task_lifecycle_id__isnull=True).update(task_lifecycle_id=task.id)


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("orm", "0056_runtime_intent_outcomes"),
    ]

    operations = [
        migrations.AddField(
            model_name="runtimeintentoutcome",
            name="acknowledged_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="runtimeintentoutcome",
            name="acknowledgement_reason",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="runtimeintentoutcome",
            name="acknowledged_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="acknowledged_runtime_intent_outcomes",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.CreateModel(
            name="TaskLifecycleRecord",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("source_node_id", models.CharField(max_length=255)),
                ("node_type", models.CharField(blank=True, default="", max_length=64)),
                ("external_key", models.CharField(max_length=255)),
                ("title", models.CharField(max_length=255)),
                ("status", models.CharField(choices=[("created", "Created"), ("queued", "Queued"), ("claimed", "Claimed"), ("running", "Running"), ("paused", "Paused"), ("waiting_for_decision", "Waiting For Decision"), ("retry_scheduled", "Retry Scheduled"), ("completed", "Completed"), ("failed", "Failed"), ("dead_lettered", "Dead Lettered"), ("cancelled", "Cancelled")], default="created", max_length=32)),
                ("priority", models.CharField(choices=[("low", "Low"), ("normal", "Normal"), ("high", "High"), ("urgent", "Urgent")], default="normal", max_length=16)),
                ("summary", models.TextField(blank=True, default="")),
                ("current_attempt", models.PositiveIntegerField(default=1)),
                ("retry_metadata", models.JSONField(blank=True, default=dict)),
                ("recovery_options", models.JSONField(blank=True, default=list)),
                ("unresolved_error", models.TextField(blank=True, default="")),
                ("stale_event_count", models.PositiveIntegerField(default=0)),
                ("late_event_count", models.PositiveIntegerField(default=0)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("ended_at", models.DateTimeField(blank=True, null=True)),
                ("last_transition_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("current_node_run", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="lifecycle_tasks", to="orm.noderun")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="task_lifecycle_records", to="orm.organization")),
                ("run", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="task_lifecycle_records", to="orm.run")),
            ],
            options={
                "db_table": "task_lifecycle_records",
                "ordering": ["-updated_at", "-created_at"],
            },
        ),
        migrations.CreateModel(
            name="TaskAttemptRecord",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("attempt_number", models.PositiveIntegerField(default=1)),
                ("idempotency_key", models.CharField(blank=True, default="", max_length=255)),
                ("owner_component", models.CharField(blank=True, default="", max_length=64)),
                ("status", models.CharField(choices=[("created", "Created"), ("running", "Running"), ("completed", "Completed"), ("failed", "Failed"), ("retry_scheduled", "Retry Scheduled"), ("dead_lettered", "Dead Lettered"), ("cancelled", "Cancelled")], default="created", max_length=32)),
                ("retry_reason", models.TextField(blank=True, default="")),
                ("last_error", models.TextField(blank=True, default="")),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("ended_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("lifecycle_task", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="attempts", to="orm.tasklifecyclerecord")),
                ("node_run", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="task_attempts", to="orm.noderun")),
                ("parent_attempt", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="retry_attempts", to="orm.taskattemptrecord")),
                ("run", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="task_attempts", to="orm.run")),
            ],
            options={
                "db_table": "task_attempt_records",
                "ordering": ["attempt_number", "created_at"],
            },
        ),
        migrations.CreateModel(
            name="TaskLifecycleEvent",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("idempotency_key", models.CharField(max_length=255)),
                ("source", models.CharField(blank=True, default="", max_length=64)),
                ("event_type", models.CharField(max_length=64)),
                ("from_status", models.CharField(blank=True, default="", max_length=32)),
                ("to_status", models.CharField(blank=True, default="", max_length=32)),
                ("attempt_number", models.PositiveIntegerField(default=1)),
                ("outcome", models.CharField(choices=[("accepted", "Accepted"), ("duplicate", "Duplicate"), ("invalid", "Invalid"), ("stale", "Stale"), ("late", "Late"), ("out_of_order", "Out Of Order")], max_length=32)),
                ("reason", models.TextField(blank=True, default="")),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("occurred_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("lifecycle_task", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="events", to="orm.tasklifecyclerecord")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="task_lifecycle_events", to="orm.organization")),
                ("run", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="task_lifecycle_events", to="orm.run")),
            ],
            options={
                "db_table": "task_lifecycle_events",
                "ordering": ["occurred_at", "created_at"],
            },
        ),
        migrations.CreateModel(
            name="TaskDeadLetterRecord",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("intent_id", models.UUIDField(blank=True, null=True)),
                ("stream_message_id", models.CharField(blank=True, default="", max_length=64)),
                ("reason", models.TextField()),
                ("attempt_count", models.PositiveIntegerField(default=0)),
                ("last_error", models.TextField(blank=True, default="")),
                ("recovery_options", models.JSONField(blank=True, default=list)),
                ("status", models.CharField(choices=[("active", "Active"), ("acknowledged", "Acknowledged"), ("recovered", "Recovered")], default="active", max_length=32)),
                ("acknowledged_at", models.DateTimeField(blank=True, null=True)),
                ("acknowledgement_reason", models.TextField(blank=True, default="")),
                ("recovered_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("acknowledged_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="acknowledged_task_dead_letters", to=settings.AUTH_USER_MODEL)),
                ("lifecycle_task", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="dead_letters", to="orm.tasklifecyclerecord")),
                ("recovered_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="recovered_task_dead_letters", to=settings.AUTH_USER_MODEL)),
                ("run", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="task_dead_letters", to="orm.run")),
                ("runtime_intent_outcome", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="task_dead_letters", to="orm.runtimeintentoutcome")),
            ],
            options={
                "db_table": "task_dead_letter_records",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="RetryOperation",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("operation_type", models.CharField(max_length=64)),
                ("idempotency_key", models.CharField(max_length=255)),
                ("attempt_number", models.PositiveIntegerField(default=1)),
                ("max_attempts", models.PositiveIntegerField(default=1)),
                ("retry_delay_ms", models.PositiveIntegerField(default=0)),
                ("retry_reason", models.TextField(blank=True, default="")),
                ("last_error", models.TextField(blank=True, default="")),
                ("owning_component", models.CharField(max_length=64)),
                ("next_scheduled_at", models.DateTimeField(blank=True, null=True)),
                ("terminal_fallback", models.CharField(blank=True, default="", max_length=64)),
                ("retry_class", models.CharField(choices=[("transport", "Transport"), ("backend_rejection", "Backend Rejection"), ("llm_backpressure", "LLM Backpressure"), ("human_pending", "Human Pending"), ("poison_message", "Poison Message"), ("duplicate_intent", "Duplicate Intent")], max_length=32)),
                ("status", models.CharField(choices=[("scheduled", "Scheduled"), ("running", "Running"), ("succeeded", "Succeeded"), ("failed", "Failed"), ("exhausted", "Exhausted"), ("dead_lettered", "Dead Lettered"), ("cancelled", "Cancelled")], default="scheduled", max_length=32)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("attempt", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="retry_operations", to="orm.taskattemptrecord")),
                ("lifecycle_task", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="retry_operations", to="orm.tasklifecyclerecord")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="retry_operations", to="orm.organization")),
                ("run", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="retry_operations", to="orm.run")),
            ],
            options={
                "db_table": "retry_operations",
                "ordering": ["-updated_at", "-created_at"],
            },
        ),
        migrations.AddField(
            model_name="approvaltask",
            name="task_lifecycle",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="approval_tasks", to="orm.tasklifecyclerecord"),
        ),
        migrations.AddField(
            model_name="decisionrecord",
            name="task_lifecycle",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="decision_records", to="orm.tasklifecyclerecord"),
        ),
        migrations.AddField(
            model_name="taskrecord",
            name="lifecycle_task",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="task_records", to="orm.tasklifecyclerecord"),
        ),
        migrations.AlterField(
            model_name="taskrecord",
            name="status",
            field=models.CharField(choices=[("created", "Created"), ("queued", "Queued"), ("claimed", "Claimed"), ("paused", "Paused"), ("waiting_for_decision", "Waiting For Decision"), ("retry_scheduled", "Retry Scheduled"), ("completed", "Completed"), ("dead_lettered", "Dead Lettered"), ("cancelled", "Cancelled"), ("pending", "Pending"), ("running", "Running"), ("waiting", "Waiting"), ("succeeded", "Succeeded"), ("failed", "Failed"), ("canceled", "Canceled")], default="created", max_length=32),
        ),
        migrations.AddField(
            model_name="tasklifecyclerecord",
            name="current_decision",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="lifecycle_tasks", to="orm.decisionrecord"),
        ),
        migrations.AddConstraint(
            model_name="tasklifecyclerecord",
            constraint=models.UniqueConstraint(fields=("organization", "external_key"), name="task_lifecycle_org_external_uniq"),
        ),
        migrations.AddConstraint(
            model_name="taskattemptrecord",
            constraint=models.UniqueConstraint(fields=("lifecycle_task", "attempt_number"), name="task_attempt_lifecycle_number_uniq"),
        ),
        migrations.AddConstraint(
            model_name="tasklifecycleevent",
            constraint=models.UniqueConstraint(fields=("organization", "idempotency_key"), name="task_lifecycle_event_org_idem_uniq"),
        ),
        migrations.AddConstraint(
            model_name="retryoperation",
            constraint=models.UniqueConstraint(fields=("organization", "idempotency_key"), name="retry_operations_org_idem_uniq"),
        ),
        migrations.AddIndex("tasklifecyclerecord", models.Index(fields=["organization", "status"], name="task_life_org_status_idx")),
        migrations.AddIndex("tasklifecyclerecord", models.Index(fields=["run", "status"], name="task_life_run_status_idx")),
        migrations.AddIndex("tasklifecyclerecord", models.Index(fields=["run", "source_node_id"], name="task_life_run_node_idx")),
        migrations.AddIndex("tasklifecyclerecord", models.Index(fields=["last_transition_at"], name="task_life_transition_idx")),
        migrations.AddIndex("taskattemptrecord", models.Index(fields=["run", "attempt_number"], name="task_attempt_run_number_idx")),
        migrations.AddIndex("taskattemptrecord", models.Index(fields=["status", "updated_at"], name="task_attempt_status_idx")),
        migrations.AddIndex("taskattemptrecord", models.Index(fields=["idempotency_key"], name="task_attempt_idem_idx")),
        migrations.AddIndex("tasklifecycleevent", models.Index(fields=["run", "occurred_at"], name="task_life_evt_run_time_idx")),
        migrations.AddIndex("tasklifecycleevent", models.Index(fields=["lifecycle_task", "occurred_at"], name="task_life_evt_task_time_idx")),
        migrations.AddIndex("tasklifecycleevent", models.Index(fields=["outcome", "occurred_at"], name="task_life_evt_outcome_idx")),
        migrations.AddIndex("taskdeadletterrecord", models.Index(fields=["run", "status"], name="task_dl_run_status_idx")),
        migrations.AddIndex("taskdeadletterrecord", models.Index(fields=["status", "created_at"], name="task_dl_status_time_idx")),
        migrations.AddIndex("taskdeadletterrecord", models.Index(fields=["intent_id"], name="task_dl_intent_idx")),
        migrations.AddIndex("retryoperation", models.Index(fields=["run", "status"], name="retry_ops_run_status_idx")),
        migrations.AddIndex("retryoperation", models.Index(fields=["retry_class", "status"], name="retry_ops_class_status_idx")),
        migrations.AddIndex("retryoperation", models.Index(fields=["next_scheduled_at"], name="retry_ops_next_sched_idx")),
        migrations.RunPython(backfill_task_lifecycle, migrations.RunPython.noop),
    ]
