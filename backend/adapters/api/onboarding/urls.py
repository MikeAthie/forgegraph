"""
Onboarding API routes.
"""

from django.urls import path

from adapters.api.onboarding.views import OnboardingMilestonesView

urlpatterns = [
    path("milestones", OnboardingMilestonesView.as_view(), name="onboarding-milestones"),
]
