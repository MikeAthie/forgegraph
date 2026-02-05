from django.urls import path

from adapters.api.sso.views import Auth0CallbackView, Auth0LoginView, OIDCProviderView

urlpatterns = [
    path("provider", OIDCProviderView.as_view(), name="sso-provider"),
    path("auth0/login", Auth0LoginView.as_view(), name="sso-auth0-login"),
    path("auth0/callback", Auth0CallbackView.as_view(), name="sso-auth0-callback"),
]
