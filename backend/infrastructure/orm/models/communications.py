"""Generic durable communication primitives."""

from __future__ import annotations

import uuid

from django.core.exceptions import ValidationError
from django.db import models

from infrastructure.orm.models.auth import Organization, User
from infrastructure.orm.models.company_ops import CompanySignal
from infrastructure.orm.models.decisions_assets import Asset, AssetVersion, DecisionRecord
from infrastructure.orm.models.evaluations import EvaluationRun
from infrastructure.orm.models.governance import ReportRun
from infrastructure.orm.models.graphs import Graph
from infrastructure.orm.models.operating_models import ServiceDeliverable, ServiceEngagement
from infrastructure.orm.models.run_records import AgentRegistryEntry, ApprovalTask
from infrastructure.orm.models.runtime import Run, ToolExecution


class CommunicationThread(models.Model):
    """Company-scoped durable conversation container for generic ForgeGraph work."""

    THREAD_TYPE_CHOICES = [
        ("service_engagement", "Service Engagement"),
        ("operation", "Operation"),
        ("approval", "Approval"),
        ("deliverable", "Deliverable"),
        ("support", "Support"),
        ("internal_handoff", "Internal Handoff"),
        ("agent_collaboration", "Agent Collaboration"),
        ("capability_gap", "Capability Gap"),
        ("quality_gate", "Quality Gate"),
        ("system_event", "System Event"),
    ]
    VISIBILITY_MODE_CHOICES = [
        ("customer", "Customer"),
        ("operator", "Operator"),
        ("internal", "Internal"),
        ("mixed", "Mixed"),
    ]
    STATUS_CHOICES = [
        ("open", "Open"),
        ("waiting_on_customer", "Waiting On Customer"),
        ("waiting_on_operator", "Waiting On Operator"),
        ("waiting_on_agent", "Waiting On Agent"),
        ("resolved", "Resolved"),
        ("archived", "Archived"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="communication_threads",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="communication_threads",
    )
    service_engagement = models.ForeignKey(
        ServiceEngagement,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="communication_threads",
    )
    operation = models.ForeignKey(
        Run,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="communication_threads",
    )
    approval_task = models.ForeignKey(
        ApprovalTask,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="communication_threads",
    )
    artifact = models.ForeignKey(
        Asset,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="communication_threads",
    )
    report_run = models.ForeignKey(
        ReportRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="communication_threads",
    )
    department = models.ForeignKey(
        "DepartmentRegistry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="communication_threads",
    )
    title = models.CharField(max_length=255)
    thread_type = models.CharField(
        max_length=32,
        choices=THREAD_TYPE_CHOICES,
        default="support",
    )
    visibility_mode = models.CharField(
        max_length=16,
        choices=VISIBILITY_MODE_CHOICES,
        default="mixed",
    )
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="open")
    source_key = models.CharField(max_length=255, blank=True, default="")
    created_by_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_communication_threads",
    )
    created_by_agent = models.ForeignKey(
        AgentRegistryEntry,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_communication_threads",
    )
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "communication_threads"
        ordering = ["-updated_at", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "source_key"],
                condition=models.Q(source_key__gt=""),
                name="comm_thread_company_source_uniq",
            )
        ]
        indexes = [
            models.Index(
                fields=["organization", "company", "updated_at"],
                name="comm_thread_org_comp_upd_idx",
            ),
            models.Index(
                fields=["organization", "company", "status", "updated_at"],
                name="comm_thread_org_comp_stat_idx",
            ),
            models.Index(
                fields=["company", "status", "updated_at"],
                name="comm_thread_comp_stat_idx",
            ),
            models.Index(fields=["service_engagement"], name="comm_thread_engage_idx"),
            models.Index(fields=["operation"], name="comm_thread_operation_idx"),
            models.Index(fields=["approval_task"], name="comm_thread_approval_idx"),
            models.Index(fields=["artifact"], name="comm_thread_artifact_idx"),
            models.Index(fields=["report_run"], name="comm_thread_report_idx"),
            models.Index(fields=["department", "status"], name="comm_thread_dept_status_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.company_id and self.company.organization_id != self.organization_id:
            errors["company"] = "Thread company must belong to the thread organization."
        for field_name in (
            "service_engagement",
            "operation",
            "approval_task",
            "artifact",
            "report_run",
            "department",
        ):
            linked = getattr(self, field_name, None)
            if linked is None:
                continue
            organization_id, company_id = _scope_for_object(linked)
            if organization_id and organization_id != self.organization_id:
                errors[field_name] = "Linked object belongs to a different organization."
            if self.company_id:
                if company_id and company_id != self.company_id:
                    errors[field_name] = "Linked object belongs to a different company."
            elif company_id:
                errors[field_name] = "Company-scoped linked objects require a thread company."
        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return self.title


class CommunicationMessage(models.Model):
    """Durable message inside a communication thread."""

    SENDER_KIND_CHOICES = [
        ("user", "User"),
        ("agent", "Agent"),
        ("company", "Company"),
        ("organization", "Organization"),
        ("system", "System"),
    ]
    MESSAGE_KIND_CHOICES = [
        ("note", "Note"),
        ("request", "Request"),
        ("response", "Response"),
        ("status_update", "Status Update"),
        ("approval_request", "Approval Request"),
        ("decision", "Decision"),
        ("deliverable", "Deliverable"),
        ("capability_gap", "Capability Gap"),
        ("handoff", "Handoff"),
        ("missing_info_request", "Missing Info Request"),
        ("system_event", "System Event"),
        ("agent_observation", "Agent Observation"),
        ("quality_gate_update", "Quality Gate Update"),
        ("tool_result_summary", "Tool Result Summary"),
    ]
    BODY_FORMAT_CHOICES = [
        ("plain", "Plain"),
        ("markdown", "Markdown"),
        ("structured_json", "Structured JSON"),
    ]
    VISIBILITY_CHOICES = [
        ("customer", "Customer"),
        ("operator", "Operator"),
        ("internal", "Internal"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    thread = models.ForeignKey(
        CommunicationThread,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="communication_messages",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="communication_messages",
    )
    sender_kind = models.CharField(max_length=16, choices=SENDER_KIND_CHOICES)
    sender_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="communication_messages",
    )
    sender_agent = models.ForeignKey(
        AgentRegistryEntry,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="communication_messages",
    )
    sender_company = models.ForeignKey(
        Graph,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_communication_messages",
    )
    sender_organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_communication_messages",
    )
    message_kind = models.CharField(max_length=32, choices=MESSAGE_KIND_CHOICES, default="note")
    body = models.TextField(blank=True, default="")
    body_format = models.CharField(max_length=16, choices=BODY_FORMAT_CHOICES, default="plain")
    visibility = models.CharField(max_length=16, choices=VISIBILITY_CHOICES, default="customer")
    idempotency_key = models.CharField(max_length=255, blank=True, default="")
    redacted_at = models.DateTimeField(null=True, blank=True)
    redaction_reason = models.TextField(blank=True, default="")
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "communication_messages"
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["thread", "idempotency_key"],
                condition=models.Q(idempotency_key__gt=""),
                name="comm_msg_thread_idem_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["thread", "created_at"], name="comm_msg_thread_time_idx"),
            models.Index(
                fields=["organization", "company", "created_at"],
                name="comm_msg_org_comp_time_idx",
            ),
            models.Index(
                fields=["thread", "visibility", "created_at"],
                name="comm_msg_thread_vis_time_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.thread_id:
            thread = self.thread
            if self.organization_id and self.organization_id != thread.organization_id:
                errors["organization"] = "Message organization must match the thread."
            if self.company_id != thread.company_id:
                errors["company"] = "Message company must match the thread."
        if self.sender_kind == "user" and not self.sender_user_id:
            errors["sender_user"] = "User messages require sender_user."
        if self.sender_kind == "agent" and not self.sender_agent_id:
            errors["sender_agent"] = "Agent messages require sender_agent."
        if self.sender_kind == "company" and not self.sender_company_id:
            errors["sender_company"] = "Company messages require sender_company."
        if self.sender_kind == "organization" and not self.sender_organization_id:
            errors["sender_organization"] = "Organization messages require sender_organization."
        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return f"{self.message_kind} message {self.id}"


class CommunicationAttachment(models.Model):
    """Reference from a communication message to an existing durable primitive."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message = models.ForeignKey(
        CommunicationMessage,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    artifact = models.ForeignKey(
        Asset,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="communication_attachments",
    )
    artifact_revision = models.ForeignKey(
        AssetVersion,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="communication_attachments",
    )
    report_run = models.ForeignKey(
        ReportRun,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="communication_attachments",
    )
    approval_task = models.ForeignKey(
        ApprovalTask,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="communication_attachments",
    )
    decision = models.ForeignKey(
        DecisionRecord,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="communication_attachments",
    )
    signal = models.ForeignKey(
        CompanySignal,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="communication_attachments",
    )
    service_engagement = models.ForeignKey(
        ServiceEngagement,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="communication_attachments",
    )
    operation = models.ForeignKey(
        Run,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="communication_attachments",
    )
    tool_execution = models.ForeignKey(
        ToolExecution,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="communication_attachments",
    )
    evaluation_run = models.ForeignKey(
        EvaluationRun,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="communication_attachments",
    )
    service_deliverable = models.ForeignKey(
        ServiceDeliverable,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="communication_attachments",
    )
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "communication_attachments"
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["message"], name="comm_attach_message_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        target_fields = _attachment_target_fields()
        populated = [field_name for field_name in target_fields if getattr(self, f"{field_name}_id")]
        if len(populated) != 1:
            raise ValidationError("Communication attachments require exactly one linked object.")
        if not self.message_id:
            return
        field_name = populated[0]
        linked = getattr(self, field_name)
        organization_id, company_id = _scope_for_object(linked)
        if organization_id and organization_id != self.message.organization_id:
            raise ValidationError({field_name: "Attachment target belongs to a different organization."})
        if self.message.company_id and company_id and company_id != self.message.company_id:
            raise ValidationError({field_name: "Attachment target belongs to a different company."})

    def __str__(self) -> str:
        return f"Attachment {self.id} for message {self.message_id}"


class CommunicationEventReceipt(models.Model):
    """Idempotent receipt for consumed communication Kafka metadata events."""

    STATUS_CHOICES = [
        ("handled", "Handled"),
        ("ignored", "Ignored"),
        ("failed", "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    consumer_group = models.CharField(max_length=128)
    event_id = models.CharField(max_length=255, blank=True, default="")
    idempotency_key = models.CharField(max_length=255, blank=True, default="")
    topic = models.CharField(max_length=255, blank=True, default="")
    partition = models.IntegerField(null=True, blank=True)
    offset = models.BigIntegerField(null=True, blank=True)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="communication_event_receipts",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="communication_event_receipts",
    )
    outbox_event = models.ForeignKey(
        "DomainEventOutbox",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="communication_event_receipts",
    )
    event_type = models.CharField(max_length=128, blank=True, default="")
    schema_version = models.CharField(max_length=64, blank=True, default="")
    aggregate_type = models.CharField(max_length=64, blank=True, default="")
    aggregate_id = models.CharField(max_length=64, blank=True, default="")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES)
    error_message = models.TextField(blank=True, default="")
    payload_json = models.JSONField(default=dict, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)
    handled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "communication_event_receipts"
        ordering = ["-received_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["consumer_group", "event_id"],
                condition=models.Q(event_id__gt=""),
                name="comm_evt_receipt_event_uniq",
            ),
            models.UniqueConstraint(
                fields=["consumer_group", "idempotency_key"],
                condition=models.Q(idempotency_key__gt=""),
                name="comm_evt_receipt_idem_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=["consumer_group", "status", "received_at"],
                name="comm_evt_receipt_group_idx",
            ),
            models.Index(fields=["event_type", "received_at"], name="comm_evt_receipt_type_idx"),
            models.Index(
                fields=["organization", "status", "received_at"],
                name="comm_evt_receipt_org_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.consumer_group} {self.event_type} {self.status}"


def _attachment_target_fields() -> tuple[str, ...]:
    return (
        "artifact",
        "artifact_revision",
        "report_run",
        "approval_task",
        "decision",
        "signal",
        "service_engagement",
        "operation",
        "tool_execution",
        "evaluation_run",
        "service_deliverable",
    )


def _scope_for_object(value: object) -> tuple[uuid.UUID | None, uuid.UUID | None]:
    organization_id = getattr(value, "organization_id", None)
    company_id = getattr(value, "company_id", None)
    if value.__class__.__name__ == "DepartmentRegistry":
        return organization_id, None
    if isinstance(value, AssetVersion):
        return value.asset.organization_id, value.asset.company_id
    if isinstance(value, ApprovalTask):
        return _scope_for_run(value.run)
    if isinstance(value, DecisionRecord):
        if value.execution_id:
            return _scope_for_run(value.execution)
        if value.source_approval_task_id:
            return _scope_for_run(value.source_approval_task.run)
        if value.task_id and value.task.execution_id:
            return _scope_for_run(value.task.execution)
        return value.organization_id, None
    if isinstance(value, ToolExecution):
        return _scope_for_run(value.run)
    if isinstance(value, Run):
        return _scope_for_run(value)
    return organization_id, company_id


def _scope_for_run(run: Run) -> tuple[uuid.UUID | None, uuid.UUID | None]:
    organization_id = run.organization_id or run.graph_version.graph.organization_id
    return organization_id, run.graph_version.graph_id
