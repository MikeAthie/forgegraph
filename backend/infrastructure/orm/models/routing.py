"""Organization-owned department routing and ownership primitives."""

from __future__ import annotations

import uuid

from django.core.exceptions import ValidationError
from django.db import models

from infrastructure.orm.models.auth import Organization, User
from infrastructure.orm.models.communications import CommunicationMessage, CommunicationThread
from infrastructure.orm.models.company_ops import CompanySignal
from infrastructure.orm.models.graphs import Graph
from infrastructure.orm.models.operating_models import ServiceEngagement
from infrastructure.orm.models.run_records import ApprovalTask, TaskLifecycleRecord
from infrastructure.orm.models.runtime import Run


class DepartmentRegistry(models.Model):
    """Organization-scoped work owner used for routing and department RBAC."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="departments",
    )
    slug = models.SlugField(max_length=160)
    name = models.CharField(max_length=255)
    department_type = models.CharField(max_length=64, blank=True, default="")
    lead_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lead_departments",
    )
    service_tags_json = models.JSONField(default=list, blank=True)
    active = models.BooleanField(default=True)
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "department_registry"
        ordering = ["name", "slug"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "slug"],
                name="department_registry_org_slug_uniq",
            )
        ]
        indexes = [
            models.Index(
                fields=["organization", "department_type", "active"],
                name="dept_registry_org_type_idx",
            ),
            models.Index(fields=["organization", "active"], name="dept_registry_org_active_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.slug})"


class DepartmentMembership(models.Model):
    """User role inside a department; company access is checked separately."""

    ROLE_CHOICES = [
        ("viewer", "Viewer"),
        ("member", "Member"),
        ("lead", "Lead"),
    ]
    STATUS_CHOICES = [
        ("active", "Active"),
        ("inactive", "Inactive"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="department_memberships",
    )
    department = models.ForeignKey(
        DepartmentRegistry,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="department_memberships",
    )
    role = models.CharField(max_length=16, choices=ROLE_CHOICES, default="viewer")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="active")
    expires_at = models.DateTimeField(null=True, blank=True)
    metadata_json = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_department_memberships",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "department_memberships"
        ordering = ["department", "user"]
        constraints = [
            models.UniqueConstraint(
                fields=["department", "user"],
                name="department_membership_dept_user_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "status"], name="dept_member_org_status_idx"),
            models.Index(
                fields=["department", "role", "status"],
                name="dept_member_dept_role_idx",
            ),
            models.Index(fields=["user", "status"], name="dept_member_user_status_idx"),
            models.Index(fields=["expires_at"], name="dept_member_expires_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        if self.department_id and self.organization_id != self.department.organization_id:
            raise ValidationError(
                {"department": "Department membership organization must match department."}
            )

    def __str__(self) -> str:
        return f"{self.user_id} -> {self.department_id} ({self.role}, {self.status})"


class RoutingPolicy(models.Model):
    """Backend-owned policy for selecting the department that should own work."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="routing_policies",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="routing_policies",
    )
    department = models.ForeignKey(
        DepartmentRegistry,
        on_delete=models.CASCADE,
        related_name="routing_policies",
    )
    trigger_type = models.CharField(max_length=128, blank=True, default="")
    event_type = models.CharField(max_length=128, blank=True, default="")
    service_type = models.CharField(max_length=80, blank=True, default="")
    channel = models.CharField(max_length=64, blank=True, default="")
    signal_type = models.CharField(max_length=64, blank=True, default="")
    entry_conditions_json = models.JSONField(default=dict, blank=True)
    priority_rules_json = models.JSONField(default=dict, blank=True)
    sla_json = models.JSONField(default=dict, blank=True)
    required_approval_types_json = models.JSONField(default=list, blank=True)
    fallback_department = models.ForeignKey(
        DepartmentRegistry,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fallback_routing_policies",
    )
    active = models.BooleanField(default=True)
    metadata_json = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_routing_policies",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "routing_policies"
        ordering = ["organization", "-active", "service_type", "channel"]
        indexes = [
            models.Index(
                fields=["organization", "company", "trigger_type", "active"],
                name="route_pol_org_comp_trig_idx",
            ),
            models.Index(fields=["event_type", "active"], name="routing_policy_event_idx"),
            models.Index(fields=["service_type", "active"], name="routing_policy_svc_idx"),
            models.Index(fields=["department", "active"], name="routing_policy_dept_idx"),
            models.Index(fields=["channel", "active"], name="routing_policy_channel_idx"),
            models.Index(fields=["signal_type", "active"], name="routing_policy_signal_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.company_id and self.company.organization_id != self.organization_id:
            errors["company"] = "Routing policy company must belong to the policy organization."
        if self.department_id and self.department.organization_id != self.organization_id:
            errors["department"] = "Routing policy department must belong to the policy organization."
        if (
            self.fallback_department_id
            and self.fallback_department.organization_id != self.organization_id
        ):
            errors["fallback_department"] = (
                "Routing policy fallback department must belong to the policy organization."
            )
        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        company_scope = self.company_id or "organization"
        return f"{company_scope} -> {self.department_id}"


class TaskRoutingRecord(models.Model):
    """Durable handoff history for department-owned generic work."""

    STATUS_CHOICES = [
        ("queued", "Queued"),
        ("assigned", "Assigned"),
        ("claimed", "Claimed"),
        ("in_progress", "In Progress"),
        ("blocked", "Blocked"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    ]
    PRIORITY_CHOICES = [
        ("low", "Low"),
        ("normal", "Normal"),
        ("high", "High"),
        ("urgent", "Urgent"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="task_routing_records",
    )
    company = models.ForeignKey(
        Graph,
        on_delete=models.CASCADE,
        related_name="task_routing_records",
    )
    task_lifecycle = models.ForeignKey(
        TaskLifecycleRecord,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="routing_records",
    )
    communication_thread = models.ForeignKey(
        CommunicationThread,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="routing_records",
    )
    communication_message = models.ForeignKey(
        CommunicationMessage,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="routing_records",
    )
    service_engagement = models.ForeignKey(
        ServiceEngagement,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="routing_records",
    )
    operation = models.ForeignKey(
        Run,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="routing_records",
    )
    approval_task = models.ForeignKey(
        ApprovalTask,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="routing_records",
    )
    company_signal = models.ForeignKey(
        CompanySignal,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="routing_records",
    )
    from_department = models.ForeignKey(
        DepartmentRegistry,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="outgoing_routing_records",
    )
    to_department = models.ForeignKey(
        DepartmentRegistry,
        on_delete=models.PROTECT,
        related_name="incoming_routing_records",
    )
    assigned_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_task_routing_records",
    )
    reason = models.TextField(blank=True, default="")
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="queued")
    priority = models.CharField(max_length=16, choices=PRIORITY_CHOICES, default="normal")
    due_at = models.DateTimeField(null=True, blank=True)
    sla_breached_at = models.DateTimeField(null=True, blank=True)
    resolution_json = models.JSONField(default=dict, blank=True)
    idempotency_key = models.CharField(max_length=255, blank=True, default="")
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "task_routing_records"
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["to_department", "status", "due_at"],
                name="task_routing_to_status_due_idx",
            ),
            models.Index(
                fields=["task_lifecycle", "created_at"],
                name="task_route_life_time_idx",
            ),
            models.Index(
                fields=["communication_thread", "created_at"],
                name="task_route_comm_thread_idx",
            ),
            models.Index(
                fields=["communication_message", "created_at"],
                name="task_route_comm_msg_idx",
            ),
            models.Index(fields=["status", "sla_breached_at"], name="task_routing_sla_idx"),
            models.Index(fields=["company", "status", "due_at"], name="task_routing_company_idx"),
            models.Index(
                fields=["assigned_user", "status", "due_at"],
                name="task_routing_assignee_idx",
            ),
            models.Index(fields=["idempotency_key"], name="task_routing_idem_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "idempotency_key"],
                condition=models.Q(idempotency_key__gt=""),
                name="task_routing_org_idem_uniq",
            )
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.company_id and self.company.organization_id != self.organization_id:
            errors["company"] = "Routing record company must belong to the organization."
        if self.task_lifecycle_id and self.task_lifecycle.organization_id != self.organization_id:
            errors["task_lifecycle"] = "Routing record task must belong to the organization."
        for field_name in ("from_department", "to_department"):
            department = getattr(self, field_name, None)
            if department is not None and department.organization_id != self.organization_id:
                errors[field_name] = "Routing record departments must belong to the organization."
        for field_name in (
            "communication_thread",
            "communication_message",
            "service_engagement",
            "operation",
            "approval_task",
            "company_signal",
        ):
            linked = getattr(self, field_name, None)
            if linked is None:
                continue
            organization_id, company_id = _scope_for_object(linked)
            if organization_id and organization_id != self.organization_id:
                errors[field_name] = "Routing record target belongs to a different organization."
            if company_id and company_id != self.company_id:
                errors[field_name] = "Routing record target belongs to a different company."
        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return f"{self.task_lifecycle_id} -> {self.to_department_id} ({self.status})"


def _scope_for_object(value: object) -> tuple[uuid.UUID | None, uuid.UUID | None]:
    organization_id = getattr(value, "organization_id", None)
    company_id = getattr(value, "company_id", None)
    if isinstance(value, CommunicationMessage):
        return value.organization_id, value.company_id
    if isinstance(value, CommunicationThread):
        return value.organization_id, value.company_id
    if isinstance(value, ApprovalTask):
        return _scope_for_run(value.run)
    if isinstance(value, Run):
        return _scope_for_run(value)
    return organization_id, company_id


def _scope_for_run(run: Run) -> tuple[uuid.UUID | None, uuid.UUID | None]:
    organization_id = run.organization_id or run.graph_version.graph.organization_id
    return organization_id, run.graph_version.graph_id
