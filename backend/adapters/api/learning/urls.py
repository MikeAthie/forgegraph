"""Company learning URL configuration."""

from django.urls import path

from adapters.api.learning.views import (
    OutcomeReviewListCreateView,
    PolicyRuleListCreateView,
    PolicyRulePromoteView,
    PolicyRuleRejectView,
    PreferenceEventListView,
)

urlpatterns = [
    path("preference-events", PreferenceEventListView.as_view(), name="learning-preference-events"),
    path("outcome-reviews", OutcomeReviewListCreateView.as_view(), name="learning-outcome-reviews"),
    path("policy-rules", PolicyRuleListCreateView.as_view(), name="learning-policy-rules"),
    path(
        "policy-rules/<uuid:policy_rule_id>/promote",
        PolicyRulePromoteView.as_view(),
        name="learning-policy-promote",
    ),
    path(
        "policy-rules/<uuid:policy_rule_id>/reject",
        PolicyRuleRejectView.as_view(),
        name="learning-policy-reject",
    ),
]
