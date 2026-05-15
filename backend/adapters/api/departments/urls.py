"""URL configuration for department registry APIs."""

from django.urls import path

from adapters.api.departments.views import (
    DepartmentDetailView,
    DepartmentListCreateView,
    DepartmentMembershipView,
)

urlpatterns = [
    path("", DepartmentListCreateView.as_view(), name="department-list-create"),
    path("<uuid:department_id>", DepartmentDetailView.as_view(), name="department-detail"),
    path(
        "<uuid:department_id>/members",
        DepartmentMembershipView.as_view(),
        name="department-members",
    ),
]
