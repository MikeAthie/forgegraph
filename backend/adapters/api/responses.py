"""
Standardized API response utilities.

Clean Architecture: Interface Adapters layer.

Implements consistent response envelopes following API architect best practices:
- Consistent structure across all endpoints
- Clear error objects with actionable messages
- Request IDs for debugging
- Metadata for pagination and timestamps
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from rest_framework.response import Response


def success_response(data: Any, status: int = 200, meta: dict[str, Any] | None = None) -> Response:
    """
    Create a standardized success response.

    Args:
        data: The response payload
        status: HTTP status code
        meta: Optional metadata (pagination, timestamps, etc.)

    Returns:
        Response with standard envelope
    """
    response_meta = {
        "requestId": str(uuid.uuid4()),
        "timestamp": datetime.now(UTC).isoformat() + "Z",
    }
    if meta:
        response_meta.update(meta)

    return Response(
        {
            "data": data,
            "meta": response_meta,
        },
        status=status,
    )


def error_response(
    code: str,
    message: str,
    status: int = 400,
    details: list[dict[str, Any]] | None = None,
    documentation_url: str | None = None,
) -> Response:
    """
    Create a standardized error response.

    Args:
        code: Error code (e.g., "VALIDATION_ERROR", "NOT_FOUND")
        message: Human-readable error message
        status: HTTP status code
        details: Optional list of detailed error information
        documentation_url: Optional link to relevant documentation

    Returns:
        Response with standard error envelope
    """
    error_obj: dict[str, Any] = {
        "code": code,
        "message": message,
    }

    if details:
        error_obj["details"] = details

    if documentation_url:
        error_obj["documentationUrl"] = documentation_url

    return Response(
        {
            "error": error_obj,
            "meta": {
                "requestId": str(uuid.uuid4()),
                "timestamp": datetime.now(UTC).isoformat() + "Z",
            },
        },
        status=status,
    )


def paginated_response(
    data: list[Any],
    page: int,
    page_size: int,
    total_count: int,
    status: int = 200,
) -> Response:
    """
    Create a standardized paginated response.

    Args:
        data: The page of data items
        page: Current page number (1-indexed)
        page_size: Items per page
        total_count: Total number of items across all pages
        status: HTTP status code

    Returns:
        Response with pagination metadata
    """
    total_pages = (total_count + page_size - 1) // page_size if page_size > 0 else 0

    meta = {
        "requestId": str(uuid.uuid4()),
        "timestamp": datetime.now(UTC).isoformat() + "Z",
        "pagination": {
            "page": page,
            "pageSize": page_size,
            "totalCount": total_count,
            "totalPages": total_pages,
            "hasNext": page < total_pages,
            "hasPrevious": page > 1,
        },
    }

    return Response(
        {
            "data": data,
            "meta": meta,
        },
        status=status,
    )
