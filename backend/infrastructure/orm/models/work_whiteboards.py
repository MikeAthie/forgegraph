"""Backend-owned request classification and work whiteboard models."""

from __future__ import annotations

import uuid
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from infrastructure.orm.models.auth import Organization
from infrastructure.orm.models.communications import CommunicationMessage, CommunicationThread
from infrastructure.orm.models.graphs import Graph
from infrastructure.orm.models.operating_models import ServiceEngagement


class RequestClassificationRecord(models.Model):
    """Durable classification of an incoming company-scoped request."""

    CLASS_NEW = "NEW_REQUEST"
    CLASS_EXISTING = "EXISTING_REQUEST"
    CLASS_AMBIGUOUS = "AMBIGUOUS_REQUEST"
    CLASSIFICATION_CHOICES = [
        (CLASS_NEW, "New request"),
        (CLASS_EXISTING, "Existing request"),
        (CLASS_AMBIGUOUS, "Ambiguous request"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="request_classifications",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="request_classifications",
    )
    communication_thread = models.ForeignKey(
        CommunicationThread,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="request_classifications",
    )
    communication_message = models.ForeignKey(
        CommunicationMessage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="request_classifications",
    )
    service_engagement = models.ForeignKey(
        ServiceEngagement,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="request_classifications",
    )
    classification = models.CharField(max_length=32, choices=CLASSIFICATION_CHOICES)
    confidence = models.FloatField(default=0.0)
    rationale = models.TextField(blank=True, default="")
    matched_whiteboard = models.ForeignKey(
        "WorkWhiteboard",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="matched_classifications",
    )
    matched_service_engagement = models.ForeignKey(
        ServiceEngagement,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="matched_request_classifications",
    )
    idempotency_key = models.CharField(max_length=255, blank=True, default="")
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "request_classification_records"
        indexes = [
            models.Index(
                fields=["organization", "company", "created_at"],
                name="req_class_org_comp_created_idx",
            ),
            models.Index(
                fields=["communication_message", "created_at"], name="req_class_msg_created_idx"
            ),
            models.Index(
                fields=["classification", "created_at"], name="req_class_type_created_idx"
            ),
            models.Index(fields=["matched_whiteboard"], name="req_class_whiteboard_idx"),
            models.Index(fields=["idempotency_key"], name="req_class_idem_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "idempotency_key"],
                condition=~Q(idempotency_key=""),
                name="uniq_req_class_org_idem_nonempty",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        _validate_company_scope(
            "communication_thread", self.communication_thread, self.organization_id, self.company_id
        )
        _validate_company_scope(
            "communication_message",
            self.communication_message,
            self.organization_id,
            self.company_id,
        )
        _validate_company_scope(
            "service_engagement", self.service_engagement, self.organization_id, self.company_id
        )
        _validate_company_scope(
            "matched_service_engagement",
            self.matched_service_engagement,
            self.organization_id,
            self.company_id,
        )
        if self.matched_whiteboard is not None:
            _validate_company_scope(
                "matched_whiteboard",
                self.matched_whiteboard,
                self.organization_id,
                self.company_id,
            )
        if self.confidence < 0 or self.confidence > 1:
            raise ValidationError(
                {"confidence": "Classification confidence must be between 0 and 1."}
            )


class WorkWhiteboard(models.Model):
    """Durable company-scoped context board for an active work request."""

    WORK_STATUS_DRAFT = "draft"
    WORK_STATUS_INTAKE = "intake"
    WORK_STATUS_READY_FOR_PLANNING = "ready_for_planning"
    WORK_STATUS_PLANNING = "planning"
    WORK_STATUS_IN_PROGRESS = "in_progress"
    WORK_STATUS_REVIEW = "review"
    WORK_STATUS_DELIVERY = "delivery"
    WORK_STATUS_MEASUREMENT = "measurement"
    WORK_STATUS_CLOSED = "closed"
    WORK_STATUS_CHOICES = [
        (WORK_STATUS_DRAFT, "Draft"),
        (WORK_STATUS_INTAKE, "Intake"),
        (WORK_STATUS_READY_FOR_PLANNING, "Ready for planning"),
        (WORK_STATUS_PLANNING, "Planning"),
        (WORK_STATUS_IN_PROGRESS, "In progress"),
        (WORK_STATUS_REVIEW, "Review"),
        (WORK_STATUS_DELIVERY, "Delivery"),
        (WORK_STATUS_MEASUREMENT, "Measurement"),
        (WORK_STATUS_CLOSED, "Closed"),
    ]
    STATUS_DRAFT = "draft"
    STATUS_ONBOARDING = "onboarding"
    STATUS_READY_FOR_STRATEGY = "ready_for_strategy"
    STATUS_IN_STRATEGY = "in_strategy"
    STATUS_IN_CONTENT = "in_content"
    STATUS_IN_APPROVAL = "in_approval"
    STATUS_IN_DEPLOYMENT = "in_deployment"
    STATUS_IN_OPTIMIZATION = "in_optimization"
    STATUS_CLOSED = "closed"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_ONBOARDING, "Onboarding"),
        (STATUS_READY_FOR_STRATEGY, "Ready for strategy"),
        (STATUS_IN_STRATEGY, "In strategy"),
        (STATUS_IN_CONTENT, "In content"),
        (STATUS_IN_APPROVAL, "In approval"),
        (STATUS_IN_DEPLOYMENT, "In deployment"),
        (STATUS_IN_OPTIMIZATION, "In optimization"),
        (STATUS_CLOSED, "Closed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="work_whiteboards",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="work_whiteboards",
    )
    service_engagement = models.ForeignKey(
        ServiceEngagement,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="work_whiteboards",
    )
    communication_thread = models.ForeignKey(
        CommunicationThread,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="work_whiteboards",
    )
    source_message = models.ForeignKey(
        CommunicationMessage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_work_whiteboards",
    )
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    work_status = models.CharField(
        max_length=32,
        choices=WORK_STATUS_CHOICES,
        default=WORK_STATUS_DRAFT,
    )
    request_type = models.CharField(max_length=80, blank=True, default="")
    project_name = models.CharField(max_length=255, blank=True, default="")
    client_name = models.CharField(max_length=255, blank=True, default="")
    request_summary = models.TextField(blank=True, default="")
    objective = models.TextField(blank=True, default="")
    budget_limit = models.CharField(max_length=120, blank=True, default="")
    timeline = models.CharField(max_length=255, blank=True, default="")
    constraints_json = models.JSONField(default=dict, blank=True)
    target_audience_json = models.JSONField(default=dict, blank=True)
    brand_context_json = models.JSONField(default=dict, blank=True)
    product_context_json = models.JSONField(default=dict, blank=True)
    channel_context_json = models.JSONField(default=dict, blank=True)
    stakeholder_context_json = models.JSONField(default=dict, blank=True)
    resource_context_json = models.JSONField(default=dict, blank=True)
    delivery_context_json = models.JSONField(default=dict, blank=True)
    known_facts_json = models.JSONField(default=dict, blank=True)
    assumptions_json = models.JSONField(default=list, blank=True)
    missing_fields_json = models.JSONField(default=list, blank=True)
    work_missing_fields_json = models.JSONField(default=list, blank=True)
    completion_score = models.FloatField(default=0.0)
    redis_snapshot_key = models.CharField(max_length=255, blank=True, default="")
    metadata_json = models.JSONField(default=dict, blank=True)
    idempotency_key = models.CharField(max_length=255, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_work_whiteboards",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "work_whiteboards"
        indexes = [
            models.Index(
                fields=["organization", "company", "status", "updated_at"],
                name="whiteboard_org_comp_status_idx",
            ),
            models.Index(
                fields=["company", "status", "updated_at"], name="whiteboard_comp_status_idx"
            ),
            models.Index(fields=["company", "work_status"], name="whiteboard_comp_work_stat_idx"),
            models.Index(fields=["communication_thread"], name="whiteboard_thread_idx"),
            models.Index(fields=["source_message"], name="whiteboard_source_msg_idx"),
            models.Index(fields=["service_engagement"], name="whiteboard_service_idx"),
            models.Index(fields=["idempotency_key"], name="whiteboard_idem_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "idempotency_key"],
                condition=~Q(idempotency_key=""),
                name="uniq_whiteboard_org_idem_nonempty",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        _validate_company_scope(
            "service_engagement", self.service_engagement, self.organization_id, self.company_id
        )
        _validate_company_scope(
            "communication_thread", self.communication_thread, self.organization_id, self.company_id
        )
        _validate_company_scope(
            "source_message", self.source_message, self.organization_id, self.company_id
        )
        if self.completion_score < 0 or self.completion_score > 100:
            raise ValidationError(
                {"completion_score": "Completion score must be between 0 and 100."}
            )


class ProductOperation(models.Model):
    """Durable lifecycle record for a whiteboard-scoped product action."""

    STATUS_ACCEPTED = "accepted"
    STATUS_RUNNING = "running"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_BLOCKED = "blocked"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_ACCEPTED, "Accepted"),
        (STATUS_RUNNING, "Running"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
        (STATUS_BLOCKED, "Blocked"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="product_operations",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="product_operations",
    )
    whiteboard = models.ForeignKey(
        WorkWhiteboard,
        on_delete=models.CASCADE,
        related_name="operations",
    )
    kind = models.CharField(max_length=80)
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default=STATUS_ACCEPTED)
    target_type = models.CharField(max_length=80)
    target_id = models.CharField(max_length=200, blank=True, default="")
    idempotency_key = models.CharField(max_length=255, blank=True, default="")
    contract_revision_at_accept = models.PositiveIntegerField(default=0)
    contract_revision_at_completion = models.PositiveIntegerField(default=0)
    error_code = models.CharField(max_length=120, blank=True, default="")
    error_message = models.TextField(blank=True, default="")
    metadata_json = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_product_operations",
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "product_operations"
        indexes = [
            models.Index(
                fields=["organization", "company", "whiteboard", "created_at"],
                name="prod_op_scope_created_idx",
            ),
            models.Index(
                fields=["whiteboard", "status", "created_at"], name="prod_op_wb_status_idx"
            ),
            models.Index(
                fields=["whiteboard", "target_type", "target_id"], name="prod_op_wb_target_idx"
            ),
            models.Index(fields=["idempotency_key"], name="prod_op_idem_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["whiteboard", "kind", "target_type", "target_id", "idempotency_key"],
                condition=Q(idempotency_key__gt=""),
                name="uniq_prod_op_wb_kind_target_idem",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.whiteboard is not None:
            _validate_company_scope(
                "whiteboard", self.whiteboard, self.organization_id, self.company_id
            )
        if self.contract_revision_at_completion and (
            self.contract_revision_at_completion < self.contract_revision_at_accept
        ):
            raise ValidationError(
                {
                    "contract_revision_at_completion": (
                        "Completion revision cannot be lower than acceptance revision."
                    )
                }
            )


def _validate_company_scope(
    field_name: str,
    value: Any | None,
    organization_id: Any,
    company_id: Any,
) -> None:
    if value is None:
        return
    value_organization_id = getattr(value, "organization_id", None)
    value_company_id = getattr(value, "company_id", None)
    if value_company_id is None and isinstance(value, CommunicationMessage):
        value_company_id = value.company_id
    if value_company_id is None and isinstance(value, CommunicationThread):
        value_company_id = value.company_id
    if value_organization_id != organization_id or value_company_id != company_id:
        raise ValidationError(
            {field_name: "Linked object must belong to the same organization and company."}
        )
