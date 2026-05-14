"""Split run API integration tests."""

# ruff: noqa: F403,F405,I001

from tests.integration.adapters.runs.conftest import *  # noqa: F403


class TestRunEventStream:
    def test_stream_rejects_query_access_token_by_default(self, api_client, user):
        graph = Graph.objects.create(owner=user, name="Stream Token Guard Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="running")
        access_token = str(AccessToken.for_user(user))

        response = api_client.get(f"/api/runs/{run.id}/stream?token={access_token}")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_stream_allows_short_lived_ticket(self, api_client, user):
        graph = Graph.objects.create(owner=user, name="Stream Ticket Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="running")
        ticket, _ = issue_ws_ticket(access_token=AccessToken.for_user(user), user=user)

        response = api_client.get(f"/api/runs/{run.id}/stream?ticket={ticket}")

        assert response.status_code == status.HTTP_200_OK
        first_chunk = next(response.streaming_content).decode("utf-8")
        response.close()
        assert "event: connected" in first_chunk
        assert str(run.id) in first_chunk
