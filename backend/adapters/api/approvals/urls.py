"""
Approvals API URLs.

Clean Architecture: Interface Adapters layer.
"""

from django.urls import path

from adapters.api.approvals.views import (
    ApprovalCountView,
    ApprovalDetailView,
    ApprovalListView,
    ApprovalResolveView,
)

urlpatterns = [
    path("", ApprovalListView.as_view(), name="approval-list"),
    path("count", ApprovalCountView.as_view(), name="approval-count"),
    path("<uuid:approval_id>", ApprovalDetailView.as_view(), name="approval-detail"),
    path("<uuid:approval_id>/resolve", ApprovalResolveView.as_view(), name="approval-resolve"),
]
