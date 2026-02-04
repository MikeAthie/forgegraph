from django.urls import path

from adapters.api.credentials.views import CredentialsDetailView, CredentialsListCreateView

urlpatterns = [
    path("", CredentialsListCreateView.as_view(), name="credentials-list"),
    path("<uuid:credential_id>", CredentialsDetailView.as_view(), name="credentials-detail"),
]
