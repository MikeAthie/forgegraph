from django.urls import path

from adapters.api.organizations.views import (
    OrganizationCurrentView,
    OrganizationListCreateView,
    OrganizationMemberDetailView,
    OrganizationMembersView,
    OrganizationMeView,
)

urlpatterns = [
    path("", OrganizationListCreateView.as_view(), name="org-list-create"),
    path("current", OrganizationCurrentView.as_view(), name="org-current"),
    path("me", OrganizationMeView.as_view(), name="org-me"),
    path("members", OrganizationMembersView.as_view(), name="org-members"),
    path(
        "members/<uuid:user_id>", OrganizationMemberDetailView.as_view(), name="org-member-detail"
    ),
]
