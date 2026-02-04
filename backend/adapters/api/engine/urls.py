from django.urls import path

from adapters.api.engine.views import EngineCredentialDetailView

urlpatterns = [
    path(
        "credentials/<uuid:credential_id>",
        EngineCredentialDetailView.as_view(),
        name="engine-credential-detail",
    ),
]
