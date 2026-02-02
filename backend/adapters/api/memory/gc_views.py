"""
Memory garbage collection admin endpoints.

Provides admin-only access to trigger and preview memory cleanup.
"""

from rest_framework.permissions import IsAdminUser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.responses import error_response, success_response
from application.services.memory_gc import MemoryGCService


class MemoryGCView(APIView):
    """
    Admin endpoint for memory garbage collection.

    GET: Preview what would be deleted (dry run)
    POST: Execute garbage collection
    """

    permission_classes = [IsAdminUser]

    def get(self, request: Request) -> Response:
        """Preview what would be deleted (dry run)."""
        gc = MemoryGCService()
        result = gc.run_full_gc(dry_run=True)
        return success_response(result)

    def post(self, request: Request) -> Response:
        """Execute garbage collection."""
        dry_run = request.data.get("dry_run", False)

        # Validate retention parameters
        chunk_retention = request.data.get("chunk_retention_days", 90)
        entry_retention = request.data.get("entry_retention_days", 30)

        if not isinstance(chunk_retention, int) or chunk_retention < 1:
            return error_response(
                code="VALIDATION_ERROR",
                message="chunk_retention_days must be a positive integer",
                status=400,
            )

        if not isinstance(entry_retention, int) or entry_retention < 1:
            return error_response(
                code="VALIDATION_ERROR",
                message="entry_retention_days must be a positive integer",
                status=400,
            )

        gc = MemoryGCService(
            chunk_retention_days=chunk_retention,
            entry_retention_days=entry_retention,
        )

        result = gc.run_full_gc(dry_run=dry_run)

        # Return 207 Multi-Status if there were errors (partial success)
        status = 207 if result.get("errors") else 200
        return success_response(result, status=status)
