"""Backend-owned whiteboard operation lifecycle tracking."""

from __future__ import annotations

from typing import Any

from django.db.models import Max
from django.utils import timezone

from application.services.company_access import has_company_access
from application.services.domain_event_outbox import sanitize_outbox_payload
from application.services.rbac import has_min_role
from infrastructure.orm.models import ProductOperation, User, WorkWhiteboard

TERMINAL_OPERATION_STATUSES = {
    ProductOperation.STATUS_COMPLETED,
    ProductOperation.STATUS_FAILED,
    ProductOperation.STATUS_BLOCKED,
    ProductOperation.STATUS_CANCELLED,
}
ACTIVE_OPERATION_STATUSES = {
    ProductOperation.STATUS_ACCEPTED,
    ProductOperation.STATUS_RUNNING,
}


class ProductOperationError(ValueError):
    """Domain error for whiteboard operation lifecycle records."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.details = details or []
        super().__init__(message)


def begin_product_operation(
    *,
    user: User,
    whiteboard: WorkWhiteboard,
    kind: str,
    target_type: str,
    target_id: str,
    idempotency_key: str = "",
    metadata: dict[str, Any] | None = None,
) -> tuple[ProductOperation, bool]:
    """Create or replay a backend-owned lifecycle record for a whiteboard action."""

    _ensure_can_manage_operation(user=user, whiteboard=whiteboard)
    normalized_kind = _bounded(kind, 80)
    normalized_target_type = _bounded(target_type, 80)
    normalized_target_id = _bounded(target_id, 200)
    normalized_idempotency_key = _bounded(idempotency_key, 255)
    defaults = {
        "organization": whiteboard.organization,
        "company": whiteboard.company,
        "created_by": user,
        "status": ProductOperation.STATUS_RUNNING,
        "started_at": timezone.now(),
        "contract_revision_at_accept": _contract_revision(
            whiteboard=whiteboard,
            target_type=normalized_target_type,
            target_id=normalized_target_id,
        ),
        "metadata_json": sanitize_outbox_payload(metadata or {}),
    }
    if normalized_idempotency_key:
        operation, created = ProductOperation.objects.get_or_create(
            whiteboard=whiteboard,
            kind=normalized_kind,
            target_type=normalized_target_type,
            target_id=normalized_target_id,
            idempotency_key=normalized_idempotency_key,
            defaults=defaults,
        )
        return operation, created
    operation = ProductOperation.objects.create(
        whiteboard=whiteboard,
        kind=normalized_kind,
        target_type=normalized_target_type,
        target_id=normalized_target_id,
        idempotency_key="",
        **defaults,
    )
    return operation, True


def complete_product_operation(
    operation: ProductOperation,
    *,
    metadata: dict[str, Any] | None = None,
) -> ProductOperation:
    """Mark an operation completed and advance its backend contract revision."""

    return finish_product_operation(
        operation,
        status=ProductOperation.STATUS_COMPLETED,
        metadata=metadata,
    )


def block_product_operation(
    operation: ProductOperation,
    *,
    error_code: str,
    error_message: str,
    metadata: dict[str, Any] | None = None,
) -> ProductOperation:
    """Mark an operation blocked by explicit backend-owned readiness state."""

    return finish_product_operation(
        operation,
        status=ProductOperation.STATUS_BLOCKED,
        error_code=error_code,
        error_message=error_message,
        metadata=metadata,
    )


def fail_product_operation(
    operation: ProductOperation,
    *,
    error_code: str,
    error_message: str,
    metadata: dict[str, Any] | None = None,
) -> ProductOperation:
    """Mark an operation failed after the backend action rejects or errors."""

    return finish_product_operation(
        operation,
        status=ProductOperation.STATUS_FAILED,
        error_code=error_code,
        error_message=error_message,
        metadata=metadata,
    )


def finish_product_operation(
    operation: ProductOperation,
    *,
    status: str,
    error_code: str = "",
    error_message: str = "",
    metadata: dict[str, Any] | None = None,
) -> ProductOperation:
    """Set a terminal lifecycle state and persist revision/readiness metadata."""

    normalized_status = (
        status if status in TERMINAL_OPERATION_STATUSES else ProductOperation.STATUS_FAILED
    )
    if operation.status in TERMINAL_OPERATION_STATUSES:
        return operation
    now = timezone.now()
    operation.status = normalized_status
    operation.started_at = operation.started_at or now
    operation.completed_at = now
    if normalized_status in {ProductOperation.STATUS_FAILED, ProductOperation.STATUS_BLOCKED}:
        operation.failed_at = now
        operation.error_code = _bounded(error_code, 120)
        operation.error_message = str(error_message or "")[:2000]
    operation.contract_revision_at_completion = (
        max(
            _contract_revision(
                whiteboard=operation.whiteboard,
                target_type=operation.target_type,
                target_id=operation.target_id,
            ),
            operation.contract_revision_at_accept,
        )
        + 1
    )
    if metadata:
        merged = dict(operation.metadata_json if isinstance(operation.metadata_json, dict) else {})
        merged.update(sanitize_outbox_payload(metadata))
        operation.metadata_json = merged
    operation.save(
        update_fields=[
            "status",
            "started_at",
            "completed_at",
            "failed_at",
            "error_code",
            "error_message",
            "contract_revision_at_completion",
            "metadata_json",
            "updated_at",
        ]
    )
    return operation


def get_product_operation_for_user(
    *,
    user: User,
    whiteboard: WorkWhiteboard,
    operation_id: str,
) -> ProductOperation | None:
    """Return a scoped operation only when the user can read the whiteboard's company."""

    if not has_company_access(user, whiteboard.company, "viewer"):
        return None
    return (
        ProductOperation.objects.select_related(
            "organization", "company", "whiteboard", "created_by"
        )
        .filter(
            id=operation_id,
            organization=whiteboard.organization,
            company=whiteboard.company,
            whiteboard=whiteboard,
        )
        .first()
    )


def contract_operation_metadata(
    *,
    whiteboard: WorkWhiteboard,
    target_type: str,
    target_id: str,
) -> dict[str, Any]:
    """Return contract readiness metadata derived from durable operation records."""

    operations = ProductOperation.objects.filter(
        whiteboard=whiteboard,
        target_type=_bounded(target_type, 80),
        target_id=_bounded(target_id, 200),
    )
    last_operation = operations.order_by("-updated_at", "-created_at").first()
    status_counts = {
        status: operations.filter(status=status).count()
        for status in [
            ProductOperation.STATUS_ACCEPTED,
            ProductOperation.STATUS_RUNNING,
            ProductOperation.STATUS_BLOCKED,
            ProductOperation.STATUS_COMPLETED,
            ProductOperation.STATUS_FAILED,
            ProductOperation.STATUS_CANCELLED,
        ]
    }
    active_count = sum(status_counts[status] for status in ACTIVE_OPERATION_STATUSES)
    return {
        "contract_revision": _contract_revision(
            whiteboard=whiteboard,
            target_type=target_type,
            target_id=target_id,
        ),
        "last_operation_id": str(last_operation.id) if last_operation is not None else "",
        "terminal": active_count == 0,
        "pending_count": status_counts[ProductOperation.STATUS_ACCEPTED],
        "running_count": status_counts[ProductOperation.STATUS_RUNNING],
        "blocked_count": status_counts[ProductOperation.STATUS_BLOCKED],
        "completed_count": status_counts[ProductOperation.STATUS_COMPLETED],
    }


def operation_payload(operation: ProductOperation) -> dict[str, Any]:
    """Serialize a product operation for API clients."""

    payload = {
        "id": str(operation.id),
        "company_id": str(operation.company_id),
        "whiteboard_id": str(operation.whiteboard_id),
        "kind": operation.kind,
        "status": operation.status,
        "target_type": operation.target_type,
        "target_id": operation.target_id,
        "idempotency_key": operation.idempotency_key,
        "contract_revision": operation.contract_revision_at_completion
        or operation.contract_revision_at_accept,
        "contract_revision_at_accept": operation.contract_revision_at_accept,
        "contract_revision_at_completion": operation.contract_revision_at_completion,
        "terminal": operation.status in TERMINAL_OPERATION_STATUSES,
        "metadata": operation.metadata_json if isinstance(operation.metadata_json, dict) else {},
        "started_at": _iso(operation.started_at),
        "completed_at": _iso(operation.completed_at),
        "failed_at": _iso(operation.failed_at),
        "created_at": _iso(operation.created_at),
        "updated_at": _iso(operation.updated_at),
        "error": None,
    }
    if operation.error_code or operation.error_message:
        payload["error"] = {
            "code": operation.error_code,
            "message": operation.error_message,
        }
    return sanitize_outbox_payload(payload)


def _contract_revision(
    *,
    whiteboard: WorkWhiteboard,
    target_type: str,
    target_id: str,
) -> int:
    value = (
        ProductOperation.objects.filter(
            whiteboard=whiteboard,
            target_type=_bounded(target_type, 80),
            target_id=_bounded(target_id, 200),
        ).aggregate(value=Max("contract_revision_at_completion"))["value"]
        or 0
    )
    return int(value)


def _ensure_can_manage_operation(*, user: User, whiteboard: WorkWhiteboard) -> None:
    if not has_company_access(user, whiteboard.company, "member") or not has_min_role(
        user,
        "member",
        str(whiteboard.organization_id),
    ):
        raise ProductOperationError(
            "permission_denied",
            "You do not have permission to start this whiteboard operation.",
        )


def _bounded(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _iso(value: Any | None) -> str:
    if value is None:
        return ""
    return value.isoformat()
