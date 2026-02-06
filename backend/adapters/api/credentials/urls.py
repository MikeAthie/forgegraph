from django.urls import path

from adapters.api.credentials.views import (
    CredentialOAuthCallbackView,
    CredentialOAuthProviderConfigView,
    CredentialOAuthProvidersView,
    CredentialOAuthStartView,
    CredentialsDetailView,
    CredentialsListCreateView,
)

urlpatterns = [
    path(
        "oauth/providers",
        CredentialOAuthProvidersView.as_view(),
        name="credentials-oauth-providers",
    ),
    path(
        "oauth/providers/<str:provider>",
        CredentialOAuthProviderConfigView.as_view(),
        name="credentials-oauth-provider-config",
    ),
    path("oauth/start", CredentialOAuthStartView.as_view(), name="credentials-oauth-start"),
    path(
        "oauth/callback", CredentialOAuthCallbackView.as_view(), name="credentials-oauth-callback"
    ),
    path("", CredentialsListCreateView.as_view(), name="credentials-list"),
    path("<uuid:credential_id>", CredentialsDetailView.as_view(), name="credentials-detail"),
]
