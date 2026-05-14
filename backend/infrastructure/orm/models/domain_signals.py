"""Django ORM model group split from infrastructure.orm.models."""

from __future__ import annotations

# ruff: noqa: F401,F403,F405,I001

from infrastructure.orm.models.credentials import *  # noqa: F403
from infrastructure.orm.models.base import _make_check_constraint


@receiver(post_save, sender=User)
def ensure_default_organization(
    sender: type[User], instance: User, created: bool, **kwargs: Any
) -> None:
    if not created or instance.default_organization_id:
        return

    org_name = instance.email.split("@")[0] or "Personal"
    organization = Organization.objects.create(name=f"{org_name} Org")
    OrganizationMembership.objects.create(
        organization=organization,
        user=instance,
        role="owner",
        is_default=True,
    )
    User.objects.filter(pk=instance.pk).update(default_organization=organization)


@receiver(post_save, sender=Organization)
def ensure_organization_runtime_ledgers(
    sender: type[Organization], instance: Organization, created: bool, **kwargs: Any
) -> None:
    if kwargs.get("raw") or not created:
        return
    OrganizationDomainEventSequence.objects.get_or_create(
        organization_id=instance.id,
        defaults={"next_sequence": 1},
    )
    OrganizationStateFeedSequence.objects.get_or_create(
        organization_id=instance.id,
        defaults={"next_sequence": 1},
    )


@receiver(post_save, sender=Run)
def record_run_domain_event_signal(
    sender: type[Run], instance: Run, created: bool, **kwargs: Any
) -> None:
    if kwargs.get("raw"):
        return
    from application.services.domain_events import record_run_domain_event

    record_run_domain_event(instance, created=created)


@receiver(post_save, sender=RunEvent)
def record_run_event_domain_event_signal(
    sender: type[RunEvent], instance: RunEvent, created: bool, **kwargs: Any
) -> None:
    if kwargs.get("raw") or not created:
        return
    from application.services.domain_events import record_run_event_domain_event

    record_run_event_domain_event(instance)


@receiver(post_save, sender=NodeRun)
def record_node_run_domain_event_signal(
    sender: type[NodeRun], instance: NodeRun, created: bool, **kwargs: Any
) -> None:
    if kwargs.get("raw"):
        return
    from application.services.domain_events import record_node_run_domain_event

    record_node_run_domain_event(instance, created=created)


@receiver(post_save, sender=TaskLifecycleEvent)
def record_task_lifecycle_domain_event_signal(
    sender: type[TaskLifecycleEvent], instance: TaskLifecycleEvent, created: bool, **kwargs: Any
) -> None:
    if kwargs.get("raw") or not created:
        return
    from application.services.domain_events import record_task_lifecycle_domain_event

    record_task_lifecycle_domain_event(instance)


@receiver(post_save, sender=ApprovalTask)
def record_approval_domain_event_signal(
    sender: type[ApprovalTask], instance: ApprovalTask, created: bool, **kwargs: Any
) -> None:
    if kwargs.get("raw"):
        return
    from application.services.domain_events import record_approval_domain_event

    record_approval_domain_event(instance, created=created)


@receiver(post_save, sender=LLMUsage)
def record_llm_usage_domain_event_signal(
    sender: type[LLMUsage], instance: LLMUsage, created: bool, **kwargs: Any
) -> None:
    if kwargs.get("raw") or not created:
        return
    from application.services.domain_events import record_llm_usage_domain_event

    record_llm_usage_domain_event(instance)


@receiver(post_save, sender=MemoryUsage)
def record_memory_usage_domain_event_signal(
    sender: type[MemoryUsage], instance: MemoryUsage, created: bool, **kwargs: Any
) -> None:
    if kwargs.get("raw"):
        return
    from application.services.domain_events import record_memory_usage_domain_event

    record_memory_usage_domain_event(instance)


@receiver(post_save, sender=MemoryObservation)
def record_memory_observation_domain_event_signal(
    sender: type[MemoryObservation], instance: MemoryObservation, created: bool, **kwargs: Any
) -> None:
    if kwargs.get("raw"):
        return
    from application.services.domain_events import (
        domain_event_signals_suppressed,
        record_memory_observation_domain_event,
    )

    if domain_event_signals_suppressed():
        return

    record_memory_observation_domain_event(instance, created=created)


@receiver(post_save, sender=GraphVersion)
def record_graph_version_domain_event_signal(
    sender: type[GraphVersion], instance: GraphVersion, created: bool, **kwargs: Any
) -> None:
    if kwargs.get("raw") or not created:
        return
    from application.services.domain_events import record_graph_version_domain_event

    record_graph_version_domain_event(instance)


@receiver(post_save, sender=AuditLog)
def record_audit_review_domain_event_signal(
    sender: type[AuditLog], instance: AuditLog, created: bool, **kwargs: Any
) -> None:
    if kwargs.get("raw") or not created:
        return
    from application.services.domain_events import record_audit_review_domain_event

    record_audit_review_domain_event(instance)
