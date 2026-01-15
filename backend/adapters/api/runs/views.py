"""
Runs API views (stub for Phase 4).

Clean Architecture: Interface Adapters layer.
"""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.runs.serializers import (
    RunResumeSerializer,
    RunStartSerializer,
)


class RunListView(APIView):
    """List runs (stub)."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        """List user's runs."""
        # Stub - will be implemented in Phase 4
        return Response([])


class RunDetailView(APIView):
    """Get run details (stub)."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, run_id) -> Response:
        """Get run details with node runs."""
        # Stub - will be implemented in Phase 4
        return Response(
            {"detail": "Run not found."},
            status=status.HTTP_404_NOT_FOUND,
        )


class RunStartView(APIView):
    """Start a run (stub)."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        """Start a new run."""
        serializer = RunStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Stub - will be implemented in Phase 4
        return Response(
            {"detail": "Run execution not yet implemented."},
            status=status.HTTP_501_NOT_IMPLEMENTED,
        )


class RunCancelView(APIView):
    """Cancel a run (stub)."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request, run_id) -> Response:
        """Cancel a running run."""
        # Stub - will be implemented in Phase 4
        return Response(
            {"detail": "Run cancellation not yet implemented."},
            status=status.HTTP_501_NOT_IMPLEMENTED,
        )


class RunResumeView(APIView):
    """Resume a paused run (stub)."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request, run_id) -> Response:
        """Resume a paused run."""
        serializer = RunResumeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Stub - will be implemented in Phase 4
        return Response(
            {"detail": "Run resume not yet implemented."},
            status=status.HTTP_501_NOT_IMPLEMENTED,
        )
