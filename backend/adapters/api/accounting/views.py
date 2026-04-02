"""Accounting summary API views."""

from __future__ import annotations

from typing import cast

from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.responses import success_response
from application.services.os_projections import (
    accounting_overview,
    cost_ledger_summary,
    refresh_phase1_projections,
)
from infrastructure.orm.models import CostLedgerEntry, User


class AccountingOverviewView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        bundle = refresh_phase1_projections(cast(User, request.user))
        return success_response(accounting_overview(bundle.organization))


class AccountingLedgerView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        bundle = refresh_phase1_projections(cast(User, request.user))
        entries = CostLedgerEntry.objects.filter(organization=bundle.organization).select_related(
            "agent", "task", "execution", "workflow_revision"
        )
        return success_response([cost_ledger_summary(entry) for entry in entries.order_by("-occurred_at", "-created_at")[:200]])
