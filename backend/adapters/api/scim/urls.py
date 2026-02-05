from django.urls import path

from adapters.api.scim.views import (
    ScimTokenRotateView,
    ScimTokenView,
    ScimUserDetailView,
    ScimUsersView,
)

urlpatterns = [
    path("v2/Users", ScimUsersView.as_view(), name="scim-users"),
    path("v2/Users/<uuid:user_id>", ScimUserDetailView.as_view(), name="scim-user-detail"),
    path("token", ScimTokenView.as_view(), name="scim-token"),
    path("token/rotate", ScimTokenRotateView.as_view(), name="scim-token-rotate"),
]
