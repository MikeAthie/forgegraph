"""URL configuration for generic communication APIs."""

from django.urls import path

from adapters.api.communications.views import (
    CommunicationAttachmentCreateView,
    CommunicationMessageListCreateView,
    CommunicationThreadDetailView,
    CommunicationThreadListCreateView,
)

urlpatterns = [
    path(
        "communication/threads",
        CommunicationThreadListCreateView.as_view(),
        name="communication-thread-list-create",
    ),
    path(
        "communication/threads/<uuid:thread_id>",
        CommunicationThreadDetailView.as_view(),
        name="communication-thread-detail",
    ),
    path(
        "communication/threads/<uuid:thread_id>/messages",
        CommunicationMessageListCreateView.as_view(),
        name="communication-thread-messages",
    ),
    path(
        "communication/messages/<uuid:message_id>/attachments",
        CommunicationAttachmentCreateView.as_view(),
        name="communication-message-attachments",
    ),
]
