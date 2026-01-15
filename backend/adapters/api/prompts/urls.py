"""
Prompts API URLs.

Clean Architecture: Interface Adapters layer.
"""

from django.urls import path

from adapters.api.prompts.views import (
    PromptCloneView,
    PromptDetailView,
    PromptListCreateView,
    PromptPublishView,
)

urlpatterns = [
    path("", PromptListCreateView.as_view(), name="prompt-list-create"),
    path("<uuid:prompt_id>", PromptDetailView.as_view(), name="prompt-detail"),
    path("<uuid:prompt_id>/clone", PromptCloneView.as_view(), name="prompt-clone"),
    path("<uuid:prompt_id>/publish", PromptPublishView.as_view(), name="prompt-publish"),
]
