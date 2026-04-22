from django.urls import path

from adapters.api.runtime_tools.views import RuntimeWebFetchView, RuntimeWebSearchView

urlpatterns = [
    path("web-fetch", RuntimeWebFetchView.as_view(), name="runtime-web-fetch"),
    path("web-search", RuntimeWebSearchView.as_view(), name="runtime-web-search"),
]
