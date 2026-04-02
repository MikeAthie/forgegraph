"""Accounting API URLs."""

from django.urls import path

from adapters.api.accounting.views import AccountingLedgerView, AccountingOverviewView

urlpatterns = [
    path("", AccountingOverviewView.as_view(), name="accounting-overview"),
    path("ledger", AccountingLedgerView.as_view(), name="accounting-ledger"),
]
