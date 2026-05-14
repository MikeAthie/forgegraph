"""Split run API integration tests."""

# ruff: noqa: F403,F405,I001

from tests.integration.adapters.runs.conftest import *  # noqa: F403


class TestRunCancel:
    """Tests for POST /api/runs/{run_id}/cancel"""

    def test_cancel_run_requires_authentication(self, api_client, user):
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="running")

        response = api_client.post(f"/api/runs/{run.id}/cancel", {}, format="json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_cancel_run_updates_status(self, authenticated_client, user):
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="running")

        response = authenticated_client.post(f"/api/runs/{run.id}/cancel", {}, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["id"] == str(run.id)
        assert response.data["data"]["status"] == "canceled"
        assert response.data["data"]["ended_at"] is not None

        run.refresh_from_db()
        assert run.status == "canceled"
        assert run.ended_at is not None
        assert run.error_message

    def test_cancel_completed_run_returns_invalid_state(self, authenticated_client, user):
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=user, graph_version=version, status="succeeded")

        response = authenticated_client.post(f"/api/runs/{run.id}/cancel", {}, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"]["code"] == "INVALID_STATE"

    def test_cancel_run_for_other_user_returns_404(self, api_client, user):
        other_user = User.objects.create_user(email="other@example.com", password="password123")
        graph = Graph.objects.create(owner=other_user, name="Other Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(owner=other_user, graph_version=version, status="running")

        api_client.force_authenticate(user=user)
        response = api_client.post(f"/api/runs/{run.id}/cancel", {}, format="json")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.data["error"]["code"] == "NOT_FOUND"


class TestRunResume:
    """Tests for POST /api/runs/{run_id}/resume"""

    def test_resume_requires_authentication(self, api_client, user):
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(
            owner=user, graph_version=version, status="paused", paused_node_id="gate"
        )

        response = api_client.post(
            f"/api/runs/{run.id}/resume",
            {"node_id": "gate", "input_json": {"approved": True}},
            format="json",
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_resume_rejects_non_paused_run(self, authenticated_client, mock_engine_client, user):
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(
            owner=user, graph_version=version, status="running", paused_node_id="gate"
        )

        with TestCase.captureOnCommitCallbacks(execute=True):
            response = authenticated_client.post(
                f"/api/runs/{run.id}/resume",
                {"node_id": "gate", "input_json": {"approved": True}},
                format="json",
            )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"]["code"] == "INVALID_STATE"
        assert not any(call[0] == "resume_run" for call in mock_engine_client.calls)

    def test_resume_rejects_node_mismatch(self, authenticated_client, mock_engine_client, user):
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(
            owner=user, graph_version=version, status="paused", paused_node_id="gate"
        )

        response = authenticated_client.post(
            f"/api/runs/{run.id}/resume",
            {"node_id": "other_gate", "input_json": {"approved": True}},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"]["code"] == "INVALID_NODE"
        assert not any(call[0] == "resume_run" for call in mock_engine_client.calls)

    def test_resume_calls_engine_and_marks_task_approved(
        self, authenticated_client, mock_engine_client, user
    ):
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(
            owner=user, graph_version=version, status="paused", paused_node_id="gate"
        )
        task = ApprovalTask.objects.create(
            run=run,
            node_id="gate",
            assignee=user,
            status="pending",
            payload={"prompt_message": "Please approve", "required_fields": ["ticket"]},
        )

        input_json = {"approved": True, "fields": {"ticket": "ABC-123"}, "feedback": "LGTM"}
        response = authenticated_client.post(
            f"/api/runs/{run.id}/resume",
            {"node_id": "gate", "input_json": input_json},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["resumed"] is True

        # Engine called
        resume_calls = [call for call in mock_engine_client.calls if call[0] == "resume_run"]
        assert len(resume_calls) == 1
        assert resume_calls[0][1]["run_id"] == run.id
        assert resume_calls[0][1]["node_id"] == "gate"
        assert resume_calls[0][1]["input_json"] == input_json
        assert isinstance(resume_calls[0][1]["resume_attempt_id"], str)

        run.refresh_from_db()
        assert run.status == "resume_requested"
        assert run.recovery_state == "resume_requested"
        assert run.resume_requested_at is not None
        assert run.resume_attempt_id is not None
        assert resume_calls[0][1]["resume_attempt_id"] == str(run.resume_attempt_id)

        # Task updated
        task.refresh_from_db()
        assert task.status == "approved"
        assert task.result == input_json
        assert task.resolved_at is not None

    def test_resume_updates_snapshot_attempt_before_dispatch(
        self, authenticated_client, mock_engine_client, user
    ):
        graph = Graph.objects.create(owner=user, name="Resume Snapshot Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(
            owner=user,
            graph_version=version,
            status="paused",
            paused_node_id="gate",
        )
        previous_snapshot = RunSnapshot(
            run_id=run.id,
            last_completed_node="node_1",
            next_node="gate",
            attempt_id="attempt-a",
            updated_at=timezone.now() - timedelta(minutes=1),
        )
        set_snapshot(previous_snapshot)

        response = authenticated_client.post(
            f"/api/runs/{run.id}/resume",
            {"node_id": "gate", "input_json": {"approved": True}},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        resume_calls = [call for call in mock_engine_client.calls if call[0] == "resume_run"]
        assert len(resume_calls) == 1

        run.refresh_from_db()
        snapshot = get_snapshot(run.id)
        assert snapshot is not None
        assert snapshot.last_completed_node == "node_1"
        assert snapshot.next_node == "gate"
        assert snapshot.attempt_id == str(run.resume_attempt_id)
        assert snapshot.attempt_id != previous_snapshot.attempt_id
        assert resume_calls[0][1]["resume_attempt_id"] == snapshot.attempt_id

    def test_resume_records_failed_to_resume_when_engine_rejects(
        self, authenticated_client, mock_engine_client, user
    ):
        graph = Graph.objects.create(owner=user, name="Resume Engine Reject Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(
            owner=user,
            graph_version=version,
            status="paused",
            paused_node_id="gate",
        )
        task = ApprovalTask.objects.create(
            run=run,
            node_id="gate",
            assignee=user,
            status="pending",
            payload={"prompt_message": "Please approve"},
        )
        previous_snapshot = RunSnapshot(
            run_id=run.id,
            last_completed_node="node_1",
            next_node="gate",
            attempt_id="attempt-before-resume",
            updated_at=timezone.now() - timedelta(minutes=1),
        )
        set_snapshot(previous_snapshot)
        mock_engine_client.resume_run_error = "resume_attempt_id is required in runtime intent mode"

        response = authenticated_client.post(
            f"/api/runs/{run.id}/resume",
            {"node_id": "gate", "input_json": {"approved": True}},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"]["code"] == "ENGINE_ERROR"

        resume_calls = [call for call in mock_engine_client.calls if call[0] == "resume_run"]
        assert len(resume_calls) == 1
        dispatched_attempt_id = resume_calls[0][1]["resume_attempt_id"]
        assert isinstance(dispatched_attempt_id, str)
        assert dispatched_attempt_id

        run.refresh_from_db()
        assert run.status == "resume_requested"
        assert run.recovery_state == "resume_dispatch_failed"
        assert run.recovery_reason == "engine_rejected_resume"
        assert run.resume_requested_at is not None
        assert str(run.resume_attempt_id) == dispatched_attempt_id

        snapshot = get_snapshot(run.id)
        assert snapshot is not None
        assert snapshot.attempt_id == dispatched_attempt_id
        assert snapshot.last_completed_node == previous_snapshot.last_completed_node
        assert snapshot.next_node == previous_snapshot.next_node

        task.refresh_from_db()
        assert task.status == "approved"
        assert task.result == {"approved": True}

    def test_resume_calls_engine_and_marks_task_rejected(
        self, authenticated_client, mock_engine_client, user
    ):
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(
            owner=user, graph_version=version, status="paused", paused_node_id="gate"
        )
        task = ApprovalTask.objects.create(
            run=run,
            node_id="gate",
            assignee=user,
            status="pending",
            payload={"prompt_message": "Please approve"},
        )

        input_json = {"approved": False, "feedback": "Needs changes"}
        response = authenticated_client.post(
            f"/api/runs/{run.id}/resume",
            {"node_id": "gate", "input_json": input_json},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK

        run.refresh_from_db()
        assert run.status == "resume_requested"
        assert run.resume_requested_at is not None
        assert run.resume_attempt_id is not None

        resume_calls = [call for call in mock_engine_client.calls if call[0] == "resume_run"]
        assert len(resume_calls) == 1
        assert resume_calls[0][1]["resume_attempt_id"] == str(run.resume_attempt_id)

        task.refresh_from_db()
        assert task.status == "rejected"
        assert task.result == input_json
        assert task.resolved_at is not None

    def test_resume_is_idempotent_for_duplicate_decision_payload(
        self, authenticated_client, mock_engine_client, user
    ):
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(
            owner=user, graph_version=version, status="paused", paused_node_id="gate"
        )
        ApprovalTask.objects.create(
            run=run,
            node_id="gate",
            assignee=user,
            status="pending",
            payload={"prompt_message": "Please approve"},
        )

        input_json = {"approved": True, "feedback": "Ship it"}
        first = authenticated_client.post(
            f"/api/runs/{run.id}/resume",
            {"node_id": "gate", "input_json": input_json},
            format="json",
        )
        second = authenticated_client.post(
            f"/api/runs/{run.id}/resume",
            {"node_id": "gate", "input_json": input_json},
            format="json",
        )

        assert first.status_code == status.HTTP_200_OK
        assert second.status_code == status.HTTP_200_OK
        assert second.data["data"]["duplicate"] is True

        resume_calls = [call for call in mock_engine_client.calls if call[0] == "resume_run"]
        assert len(resume_calls) == 1

    def test_resume_rejects_conflicting_duplicate_decision_payload(
        self, authenticated_client, mock_engine_client, user
    ):
        graph = Graph.objects.create(owner=user, name="Resume Conflict Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(
            owner=user, graph_version=version, status="paused", paused_node_id="gate"
        )
        ApprovalTask.objects.create(
            run=run,
            node_id="gate",
            assignee=user,
            status="approved",
            result={"approved": True, "feedback": "Ship it"},
            resolved_at=timezone.now(),
            payload={"prompt_message": "Please approve"},
        )

        response = authenticated_client.post(
            f"/api/runs/{run.id}/resume",
            {"node_id": "gate", "input_json": {"approved": False, "feedback": "Hold"}},
            format="json",
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.data["error"]["code"] == "DECISION_CONFLICT"
        assert "already been resolved differently" in response.data["error"]["message"]
        assert not [call for call in mock_engine_client.calls if call[0] == "resume_run"]

    def test_resume_rejects_when_budget_exceeded(
        self, authenticated_client, mock_engine_client, user
    ):
        graph = Graph.objects.create(owner=user, name="Budget Resume Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        run = Run.objects.create(
            owner=user, graph_version=version, status="paused", paused_node_id="gate"
        )
        ApprovalTask.objects.create(
            run=run,
            node_id="gate",
            assignee=user,
            status="pending",
            payload={"prompt_message": "Please approve"},
        )
        usage_run = Run.objects.create(owner=user, graph_version=version, status="succeeded")
        LLMBudget.objects.create(
            tenant_id=user.default_organization_id,
            monthly_limit_usd=Decimal("1.00"),
            warning_threshold_pct=Decimal("0.80"),
        )
        LLMUsage.objects.create(
            tenant_id=user.default_organization_id,
            run=usage_run,
            node_id="prompt-1",
            provider="openai",
            model="gpt-4.1-mini",
            prompt_tokens=100,
            completion_tokens=25,
            total_tokens=125,
            cost_usd=Decimal("1.00"),
        )

        response = authenticated_client.post(
            f"/api/runs/{run.id}/resume",
            {"node_id": "gate", "input_json": {"approved": True}},
            format="json",
        )

        assert response.status_code == status.HTTP_402_PAYMENT_REQUIRED
        assert response.data["error"]["code"] == "BUDGET_EXCEEDED"
        assert not any(call[0] == "resume_run" for call in mock_engine_client.calls)
