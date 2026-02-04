from django.urls import path

from adapters.api.policies.views import TenantPolicyView

urlpatterns = [
    path("guardrails", TenantPolicyView.as_view(), name="tenant-policy"),
]
