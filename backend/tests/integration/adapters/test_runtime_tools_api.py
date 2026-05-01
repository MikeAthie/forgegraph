from __future__ import annotations

from unittest.mock import Mock, patch

from django.test import override_settings

RUNTIME_TOOL_AUTH = {"HTTP_AUTHORIZATION": "Bearer runtime-tool-secret"}


@override_settings(RUNTIME_TOOL_SECRET="runtime-tool-secret")
def test_runtime_web_fetch_requires_token(client):
    response = client.post(
        "/api/runtime-tools/web-fetch",
        data={"input": {"url": "https://example.com"}},
        content_type="application/json",
    )

    assert response.status_code == 401


@override_settings(
    ENGINE_CALLBACK_SECRET="engine-callback-secret",
    RUNTIME_TOOL_SECRET="runtime-tool-secret",
)
def test_runtime_web_fetch_rejects_engine_callback_query_token(client):
    response = client.post(
        "/api/runtime-tools/web-fetch?token=engine-callback-secret",
        data={"input": {"url": "https://example.com"}},
        content_type="application/json",
    )

    assert response.status_code == 401


@override_settings(RUNTIME_TOOL_SECRET="runtime-tool-secret")
def test_runtime_web_fetch_returns_extracted_text(client):
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.url = "https://example.com/article"
    mock_response.headers = {"Content-Type": "text/html; charset=utf-8"}
    mock_response.text = """
        <html>
          <head><title>Example Article</title></head>
          <body><main><h1>Hello</h1><p>Useful content for ForgeGraph.</p></main></body>
        </html>
    """
    mock_response.raise_for_status.return_value = None

    with patch("application.services.runtime_web_tools.requests.get", return_value=mock_response):
        response = client.post(
            "/api/runtime-tools/web-fetch",
            data={"input": {"url": "https://example.com/article"}},
            content_type="application/json",
            **RUNTIME_TOOL_AUTH,
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["url"] == "https://example.com/article"
    assert payload["title"] == "Example Article"
    assert "Useful content for ForgeGraph." in payload["content"]
    assert payload["truncated"] is False


@override_settings(RUNTIME_TOOL_SECRET="runtime-tool-secret")
def test_runtime_web_fetch_blocks_localhost_targets(client):
    response = client.post(
        "/api/runtime-tools/web-fetch",
        data={"input": {"url": "http://localhost:8000/private"}},
        content_type="application/json",
        **RUNTIME_TOOL_AUTH,
    )

    assert response.status_code == 400
    assert "not allowed" in response.json()["detail"].lower()


@override_settings(RUNTIME_TOOL_SECRET="runtime-tool-secret")
def test_runtime_web_fetch_blocks_redirects_to_localhost(client):
    redirect_response = Mock()
    redirect_response.status_code = 302
    redirect_response.headers = {"Location": "http://127.0.0.1:8000/private"}
    redirect_response.close.return_value = None

    with patch(
        "application.services.runtime_web_tools.requests.get", return_value=redirect_response
    ):
        response = client.post(
            "/api/runtime-tools/web-fetch",
            data={"input": {"url": "https://example.com/redirect"}},
            content_type="application/json",
            **RUNTIME_TOOL_AUTH,
        )

    assert response.status_code == 400
    assert "private or local network" in response.json()["detail"].lower()


@override_settings(RUNTIME_TOOL_SECRET="runtime-tool-secret")
def test_runtime_web_search_returns_filtered_results(client):
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.text = """
        <html><body>
          <a class="result__a" href="https://docs.example.com/alpha">Alpha Result</a>
          <a class="result__a" href="https://blocked.example.com/beta">Blocked Result</a>
          <a class="result__a" href="https://example.com/gamma">Gamma Result</a>
        </body></html>
    """
    mock_response.raise_for_status.return_value = None

    with patch("application.services.runtime_web_tools.requests.get", return_value=mock_response):
        response = client.post(
            "/api/runtime-tools/web-search",
            data={
                "input": {
                    "query": "forgegraph runtime tools",
                    "allowed_domains": ["example.com"],
                    "blocked_domains": [],
                },
                "config": {"max_results": 5},
            },
            content_type="application/json",
            **RUNTIME_TOOL_AUTH,
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "forgegraph runtime tools"
    assert payload["count"] == 3
    assert payload["results"][0]["title"] == "Alpha Result"


@override_settings(RUNTIME_TOOL_SECRET="runtime-tool-secret")
def test_runtime_web_search_rejects_conflicting_domain_filters(client):
    response = client.post(
        "/api/runtime-tools/web-search",
        data={
            "input": {
                "query": "forgegraph",
                "allowed_domains": ["example.com"],
                "blocked_domains": ["blocked.example.com"],
            }
        },
        content_type="application/json",
        **RUNTIME_TOOL_AUTH,
    )

    assert response.status_code == 400
    assert "cannot both be provided" in response.json()["detail"]
