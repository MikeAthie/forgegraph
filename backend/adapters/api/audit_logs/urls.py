from django.urls import path

from adapters.api.audit_logs.views import AuditLogListView

urlpatterns = [
    path("", AuditLogListView.as_view(), name="audit-log-list"),
]
