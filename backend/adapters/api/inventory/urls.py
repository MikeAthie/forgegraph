"""Reusable inventory URL configuration."""

from django.urls import path

from adapters.api.inventory.views import (
    InventoryOverviewView,
    ReservationCreateView,
    ReservationExpireDueView,
    ReservationExtendView,
    ReservationOrderShellView,
    ReservationReleaseView,
)

urlpatterns = [
    path("overview", InventoryOverviewView.as_view(), name="inventory-overview"),
    path("reservations", ReservationCreateView.as_view(), name="inventory-reservations"),
    path(
        "reservations/expire-due",
        ReservationExpireDueView.as_view(),
        name="inventory-reservations-expire-due",
    ),
    path(
        "reservations/<uuid:reservation_id>/release",
        ReservationReleaseView.as_view(),
        name="inventory-reservation-release",
    ),
    path(
        "reservations/<uuid:reservation_id>/extend",
        ReservationExtendView.as_view(),
        name="inventory-reservation-extend",
    ),
    path(
        "reservations/<uuid:reservation_id>/order-shell",
        ReservationOrderShellView.as_view(),
        name="inventory-reservation-order-shell",
    ),
]
