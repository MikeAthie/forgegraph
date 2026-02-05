from django.urls import path

from adapters.api.organizations.views import (
    OrganizationMemberDetailView,
    OrganizationMembersView,
    OrganizationMeView,
)

urlpatterns = [
    path("me", OrganizationMeView.as_view(), name="org-me"),
    path("members", OrganizationMembersView.as_view(), name="org-members"),
    path(
        "members/<uuid:user_id>", OrganizationMemberDetailView.as_view(), name="org-member-detail"
    ),
]
