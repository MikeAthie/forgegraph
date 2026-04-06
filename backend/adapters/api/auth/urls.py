"""
Auth API URLs.

Clean Architecture: Interface Adapters layer.
"""

from django.urls import include, path

from adapters.api.auth.views import (
    LoginView,
    LogoutView,
    MeView,
    RegisterView,
    TokenRefreshView,
    WSTicketView,
)

urlpatterns = [
    path("register", RegisterView.as_view(), name="auth-register"),
    path("login", LoginView.as_view(), name="auth-login"),
    path("logout", LogoutView.as_view(), name="auth-logout"),
    path("refresh", TokenRefreshView.as_view(), name="auth-refresh"),
    path("me", MeView.as_view(), name="auth-me"),
    path("ws-ticket", WSTicketView.as_view(), name="auth-ws-ticket"),
    path("sso/", include("adapters.api.sso.urls")),
]
