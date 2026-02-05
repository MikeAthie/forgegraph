from django.urls import path

from adapters.api.retention.views import (
    RetentionCleanupView,
    RetentionExportView,
    TenantRetentionPolicyView,
)

urlpatterns = [
    path("", TenantRetentionPolicyView.as_view(), name="retention-policy"),
    path("cleanup", RetentionCleanupView.as_view(), name="retention-cleanup"),
    path("export", RetentionExportView.as_view(), name="retention-export"),
]
