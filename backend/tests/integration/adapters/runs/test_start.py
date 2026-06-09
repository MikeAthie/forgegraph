"""Split run API integration tests."""

# ruff: noqa: F403,F405,I001

from tests.integration.adapters.runs.conftest import *  # noqa: F403


class TestRunStart:
    """Tests for POST /api/runs/start"""

    def test_start_run_requires_authentication(self, api_client, user):
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )

        response = api_client.post(
            "/api/runs/start",
            {"graph_version_id": str(version.id), "input_json": {}},
            format="json",
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_start_run_creates_run(self, authenticated_client, user):
        graph = Graph.objects.create(owner=user, name="My Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )

        response = authenticated_client.post(
            "/api/runs/start",
            {"graph_version_id": str(version.id), "input_json": {"hello": "world"}},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert "data" in response.data
        run_data = response.data["data"]
        assert run_data["graph_version_id"] == str(version.id)
        # Status is "running" after engine accepts the run
        assert run_data["status"] == "running"
        assert run_data["input_json"] == {"hello": "world"}

        created_run_id = run_data["id"]
        assert Run.objects.filter(id=created_run_id, owner=user, graph_version=version).exists()

    def test_start_run_rejects_byok_without_credential_id(self, authenticated_client, user):
        graph = Graph.objects.create(owner=user, name="BYOK Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )

        response = authenticated_client.post(
            "/api/runs/start",
            {
                "graph_version_id": str(version.id),
                "llm_mode": "byok",
                "provider": "openai",
                "input_json": {},
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"]["code"] == "VALIDATION_ERROR"
        assert any(
            detail["field"] == "credential_id" for detail in response.data["error"]["details"]
        )

    def test_start_run_rejects_raw_byok_api_key(self, authenticated_client, user):
        graph = Graph.objects.create(owner=user, name="BYOK Raw Key Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )

        response = authenticated_client.post(
            "/api/runs/start",
            {
                "graph_version_id": str(version.id),
                "llm_mode": "byok",
                "provider": "openai",
                "api_key": "sk-test-byok-123",
                "input_json": {},
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"]["code"] == "VALIDATION_ERROR"
        assert any(detail["field"] == "api_key" for detail in response.data["error"]["details"])

    def test_start_run_byok_dispatches_referenced_key_ephemerally(
        self, authenticated_client, user, mock_engine_client, settings
    ):
        settings.RUN_START_RATE_LIMIT_PER_MIN = 0
        settings.OPENAI_API_KEY = ""
        credential = APIKey.objects.create(
            organization=user.default_organization,
            user=user,
            provider="openai",
            name=f"byok-{uuid4()}",
            encrypted_key=encrypt_api_key("sk-test-byok-123"),
        )
        graph = Graph.objects.create(owner=user, name="BYOK Prompt Graph")
        version = GraphVersion.objects.create(
            graph=graph,
            version=1,
            graph_json={
                "nodes": [
                    {
                        "id": "prompt1",
                        "type": "prompt",
                        "name": "Prompt",
                        "config": {
                            "provider": "openai",
                            "prompt_template": "Hello",
                        },
                    }
                ],
                "edges": [],
            },
        )

        response = authenticated_client.post(
            "/api/runs/start",
            {
                "graph_version_id": str(version.id),
                "llm_mode": "byok",
                "provider": "openai",
                "credential_id": str(credential.id),
                "input_json": {"hello": "world"},
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED, response.data
        run_data = response.data["data"]
        assert run_data["llm_access"] == {
            "llm_mode": "byok",
            "provider": "openai",
            "credential_id": str(credential.id),
            "api_key_present": True,
            "local_session_required": False,
        }

        run = Run.objects.get(id=run_data["id"])
        assert run.input_json == {"hello": "world"}
        dispatch_graph = run.dispatch_graph_json
        assert isinstance(dispatch_graph, dict)
        metadata = dispatch_graph["metadata"]
        assert isinstance(metadata, dict)
        access = metadata["llm_access"]
        assert isinstance(access, dict)
        assert access["llm_mode"] == "byok"
        assert access["api_key_present"] is True
        assert access["credential_id"] == str(credential.id)
        assert "api_key" not in access
        assert "api_key_encrypted" not in access

        start_calls = [call for call in mock_engine_client.calls if call[0] == "start_run"]
        assert len(start_calls) == 1
        engine_input = start_calls[0][1]["input_json"]
        assert engine_input["hello"] == "world"
        assert engine_input["_forgegraph_llm_access"] == {
            "llm_mode": "byok",
            "provider": "openai",
            "credential_id": str(credential.id),
            "api_key": "sk-test-byok-123",
        }

        credential.encrypted_key = encrypt_api_key("sk-test-byok-rotated")
        credential.save(update_fields=["encrypted_key"])

        resolved_after_rotation = resolve_llm_access_for_dispatch(
            LLMAccessConfig(
                llm_mode="byok",
                provider="openai",
                credential_id=str(credential.id),
            ),
            user,
        )
        assert resolved_after_rotation.api_key == "sk-test-byok-rotated"

    def test_start_run_blocks_managed_limit_exceeded(self, authenticated_client, user, settings):
        settings.RUN_START_RATE_LIMIT_PER_MIN = 0
        settings.MANAGED_LLM_MAX_CALLS_PER_RUN = 1
        settings.OPENAI_API_KEY = "managed-key"
        graph = Graph.objects.create(owner=user, name="Managed Limit Graph")
        version = GraphVersion.objects.create(
            graph=graph,
            version=1,
            graph_json={
                "nodes": [
                    {
                        "id": "prompt1",
                        "type": "prompt",
                        "name": "Prompt 1",
                        "config": {"provider": "openai", "prompt_template": "One"},
                    },
                    {
                        "id": "prompt2",
                        "type": "prompt",
                        "name": "Prompt 2",
                        "config": {"provider": "openai", "prompt_template": "Two"},
                    },
                ],
                "edges": [],
            },
        )

        response = authenticated_client.post(
            "/api/runs/start",
            {
                "graph_version_id": str(version.id),
                "llm_mode": "managed",
                "provider": "openai",
                "input_json": {},
            },
            format="json",
        )

        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert response.data["error"]["code"] == "MANAGED_LIMIT_EXCEEDED"
        assert response.data["error"]["details"][0]["reason"] == "managed_max_llm_calls_per_run"

    def test_post_runs_alias_creates_run(self, authenticated_client, user):
        graph = Graph.objects.create(owner=user, name="My Graph Alias")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )

        response = authenticated_client.post(
            "/api/runs",
            {"graph_version_id": str(version.id), "input_json": {"hello": "alias"}},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert "data" in response.data
        run_data = response.data["data"]
        assert run_data["graph_version_id"] == str(version.id)
        assert run_data["status"] == "running"
        assert run_data["input_json"] == {"hello": "alias"}

    def test_start_run_for_other_user_graph_returns_404(self, api_client, user):
        other_user = User.objects.create_user(email="other@example.com", password="password123")
        graph = Graph.objects.create(owner=other_user, name="Other Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )

        api_client.force_authenticate(user=user)
        response = api_client.post(
            "/api/runs/start",
            {"graph_version_id": str(version.id), "input_json": {}},
            format="json",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.data["error"]["code"] == "NOT_FOUND"

    def test_start_run_rejects_invalid_input_schema(self, authenticated_client, user):
        graph = Graph.objects.create(owner=user, name="Schema Graph")
        graph_json = {
            "nodes": [],
            "edges": [],
            "metadata": {
                "input_schema": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                    "additionalProperties": False,
                }
            },
        }
        version = GraphVersion.objects.create(graph=graph, version=1, graph_json=graph_json)

        response = authenticated_client.post(
            "/api/runs/start",
            {"graph_version_id": str(version.id), "input_json": {"name": 123}},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"]["code"] == "INVALID_INPUT_SCHEMA"

    def test_start_run_sends_memory_config_to_engine(
        self, authenticated_client, user, mock_engine_client
    ):
        graph = Graph.objects.create(owner=user, name="Memory Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        MemoryConfiguration.objects.create(
            graph=graph,
            buffer_enabled=True,
            buffer_size=50,
            auto_prepend=False,
            redis_enabled=True,
            redis_summary_ttl=7200,
            redis_facts_ttl=172800,
            vector_enabled=True,
            vector_top_k=8,
            vector_threshold=0.85,
            vector_recency_weight=0.35,
            embedding_model="text-embedding-3-small",
            summarization_enabled=True,
            summarization_threshold=40,
            summarization_keep_recent=12,
            summarization_model="gpt-4",
        )

        response = authenticated_client.post(
            "/api/runs/start",
            {"graph_version_id": str(version.id), "input_json": {"hello": "world"}},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED

        start_calls = [call for call in mock_engine_client.calls if call[0] == "start_run"]
        assert len(start_calls) == 1
        call_payload = start_calls[0][1]
        assert call_payload["tenant_id"] == str(user.default_organization_id)

        memory_config = json.loads(call_payload["memory_config_json"])
        assert memory_config["tier1"]["enabled"] is True
        assert memory_config["tier1"]["buffer_size"] == 50
        assert memory_config["tier1"]["auto_prepend"] is False
        assert memory_config["tier2"]["enabled"] is True
        assert memory_config["tier2"]["summary_ttl_seconds"] == 7200
        assert memory_config["tier2"]["facts_ttl_seconds"] == 172800
        assert memory_config["tier3"]["enabled"] is True
        assert memory_config["tier3"]["top_k"] == 8
        assert memory_config["tier3"]["threshold"] == 0.85
        assert memory_config["tier3"]["recency_weight"] == 0.35
        assert memory_config["tier3"]["embedding_model"] == "text-embedding-3-small"
        assert memory_config["summarization"]["enabled"] is True
        assert memory_config["summarization"]["trigger_threshold"] == 40
        assert memory_config["summarization"]["keep_recent_count"] == 12
        assert memory_config["summarization"]["model"] == "gpt-4"

    def test_start_run_resolves_prompt_id_to_template(
        self, authenticated_client, user, mock_engine_client
    ):
        credential = _create_openai_credential(user)
        prompt = PromptTemplate.objects.create(
            owner=user,
            title="Support Prompt",
            category="other",
            content="You are a helpful support agent.",
            visibility="private",
        )
        graph = Graph.objects.create(owner=user, name="Prompt Graph")
        version = GraphVersion.objects.create(
            graph=graph,
            version=1,
            graph_json={
                "nodes": [
                    {
                        "id": "prompt1",
                        "type": "prompt",
                        "name": "Prompt",
                        "config": {
                            "prompt_id": str(prompt.id),
                            "credential_id": str(credential.id),
                        },
                    },
                    {"id": "out", "type": "output", "name": "Output", "config": {}},
                ],
                "edges": [{"id": "e1", "from": "prompt1", "to": "out"}],
            },
        )

        response = authenticated_client.post(
            "/api/runs/start",
            {"graph_version_id": str(version.id), "input_json": {"q": "hi"}},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        start_calls = [call for call in mock_engine_client.calls if call[0] == "start_run"]
        assert len(start_calls) == 1
        sent_graph = start_calls[0][1]["graph_json"]
        prompt_node = next(node for node in sent_graph["nodes"] if node["id"] == "prompt1")
        assert prompt_node["config"]["prompt_template"] == "You are a helpful support agent."

    def test_start_run_rejects_inaccessible_prompt_id(
        self, authenticated_client, user, mock_engine_client
    ):
        credential = _create_openai_credential(user)
        other_user = User.objects.create_user(email="other@example.com", password="password123")
        prompt = PromptTemplate.objects.create(
            owner=other_user,
            title="Private Prompt",
            category="other",
            content="Restricted prompt.",
            visibility="private",
        )
        graph = Graph.objects.create(owner=user, name="Prompt Access Graph")
        version = GraphVersion.objects.create(
            graph=graph,
            version=1,
            graph_json={
                "nodes": [
                    {
                        "id": "prompt1",
                        "type": "prompt",
                        "name": "Prompt",
                        "config": {
                            "prompt_id": str(prompt.id),
                            "credential_id": str(credential.id),
                        },
                    }
                ],
                "edges": [],
            },
        )

        response = authenticated_client.post(
            "/api/runs/start",
            {"graph_version_id": str(version.id), "input_json": {}},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"]["code"] == "INVALID_PROMPT_CONFIG"
        assert "not accessible" in response.data["error"]["message"]
        assert not [call for call in mock_engine_client.calls if call[0] == "start_run"]

    def test_start_run_rejects_prompt_without_template_or_prompt_id(
        self, authenticated_client, user, mock_engine_client
    ):
        credential = _create_openai_credential(user)
        graph = Graph.objects.create(owner=user, name="Prompt Validation Graph")
        version = GraphVersion.objects.create(
            graph=graph,
            version=1,
            graph_json={
                "nodes": [
                    {
                        "id": "prompt1",
                        "type": "prompt",
                        "name": "Prompt",
                        "config": {"credential_id": str(credential.id)},
                    }
                ],
                "edges": [],
            },
        )

        response = authenticated_client.post(
            "/api/runs/start",
            {"graph_version_id": str(version.id), "input_json": {}},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"]["code"] == "INVALID_PROMPT_CONFIG"
        assert "prompt_template" in response.data["error"]["message"]
        assert not [call for call in mock_engine_client.calls if call[0] == "start_run"]

    def test_start_run_blocked_when_quota_exceeded(
        self, authenticated_client, user, mock_engine_client
    ):
        graph = Graph.objects.create(owner=user, name="Quota Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )
        usage_run = Run.objects.create(owner=user, graph_version=version, status="succeeded")
        LLMQuota.objects.create(tenant_id=user.default_organization_id, monthly_token_limit=100)
        LLMUsage.objects.create(
            tenant_id=user.default_organization_id,
            run=usage_run,
            node_id="prompt-1",
            provider="openai",
            model="gpt-4",
            prompt_tokens=50,
            completion_tokens=50,
            total_tokens=100,
            cost_usd=Decimal("0.50"),
        )

        response = authenticated_client.post(
            "/api/runs/start",
            {"graph_version_id": str(version.id), "input_json": {"hello": "world"}},
            format="json",
        )

        assert response.status_code == status.HTTP_402_PAYMENT_REQUIRED
        assert response.data["error"]["code"] == "QUOTA_EXCEEDED"
        assert response.data["error"]["details"][0]["reason"] == "quota"
        assert response.data["error"]["details"][0]["scope"] == "tenant_monthly_tokens"
        assert not [call for call in mock_engine_client.calls if call[0] == "start_run"]

    def test_start_run_blocked_when_budget_exceeded(
        self, authenticated_client, user, mock_engine_client
    ):
        graph = Graph.objects.create(owner=user, name="Budget Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
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
            "/api/runs/start",
            {"graph_version_id": str(version.id), "input_json": {"hello": "budget"}},
            format="json",
        )

        assert response.status_code == status.HTTP_402_PAYMENT_REQUIRED
        assert response.data["error"]["code"] == "BUDGET_EXCEEDED"
        assert response.data["error"]["details"][0]["reason"] == "budget"
        assert response.data["error"]["details"][0]["scope"] == "tenant_monthly_spend"
        assert not [call for call in mock_engine_client.calls if call[0] == "start_run"]

    @override_settings(
        RUN_START_RATE_LIMIT_PER_MIN=1,
        RUN_RATE_LIMIT_WINDOW_SECONDS=60,
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                "LOCATION": "rate-limit-start",
            }
        },
    )
    def test_start_run_rate_limited(self, authenticated_client, user):
        graph = Graph.objects.create(owner=user, name="Rate Limit Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )

        first = authenticated_client.post(
            "/api/runs/start",
            {"graph_version_id": str(version.id), "input_json": {"hello": "world"}},
            format="json",
        )
        assert first.status_code == status.HTTP_201_CREATED

        second = authenticated_client.post(
            "/api/runs/start",
            {"graph_version_id": str(version.id), "input_json": {"hello": "world"}},
            format="json",
        )
        assert second.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert second.data["error"]["code"] == "RATE_LIMITED"
        assert second.data["error"]["details"][0]["limit"] == 1

    @override_settings(
        RUN_QUEUE_ENABLED=True,
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                "LOCATION": "run-queue-worker-unavailable",
            }
        },
    )
    def test_start_run_queues_when_enabled(
        self, authenticated_client, mock_engine_client, user, caplog
    ):
        caplog.set_level(logging.ERROR, logger="application.services.run_queue")
        graph = Graph.objects.create(owner=user, name="Queued Graph")
        version = GraphVersion.objects.create(
            graph=graph, version=1, graph_json={"nodes": [], "edges": []}
        )

        response = authenticated_client.post(
            "/api/runs/start",
            {"graph_version_id": str(version.id), "input_json": {"hello": "queue"}},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["meta"]["queued"] is True
        assert response.data["meta"]["queue_worker_active"] is False
        assert response.data["meta"]["queue_warning"] == "run_queue_worker_unavailable"
        assert "run_queue_worker_unavailable" in caplog.text
        run_data = response.data["data"]
        assert run_data["status"] == "pending"
        assert run_data["queue_status"] == "pending"
        assert run_data["queue_attempts"] == 0
        assert run_data["queue_available_at"] is not None

        run = Run.objects.get(id=run_data["id"])
        assert isinstance(run.dispatch_graph_json, dict)
        assert run.dispatch_graph_json["nodes"] == []
        assert "tool_resolution" in run.dispatch_graph_json["metadata"]
        entry = RunQueueEntry.objects.get(run=run)
        assert entry.status == "pending"
        assert not [call for call in mock_engine_client.calls if call[0] == "start_run"]

    def test_start_run_persists_backend_selected_tool_snapshot(
        self, authenticated_client, mock_engine_client, user
    ):
        package = NodeRegistryPackage.objects.create(
            slug="crm-lookup",
            name="CRM Lookup",
            summary="Lookup CRM records",
            category="crm",
        )
        release = NodeRegistryRelease.objects.create(
            package=package,
            version="1.2.0",
            status="approved",
            package_kind="runtime_tool",
            execution_node_type="tool",
            manifest_version=2,
            config_defaults={"tool": "crm_lookup"},
            runtime_manifest={
                "name": "crm_lookup",
                "version": "1.2.0",
                "category": "crm",
                "visibility": "public",
                "input_schema": {"type": "object"},
                "execution": {
                    "type": "http",
                    "timeout_seconds": 10,
                    "http": {"url": "https://example.com/crm", "method": "POST"},
                },
                "side_effects": {"type": "read", "idempotent": True},
            },
        )
        NodePackageInstallation.objects.create(
            organization=user.default_organization,
            package=package,
            release=release,
            install_metadata={},
        )

        internal_package = NodeRegistryPackage.objects.create(
            slug="crm-internal",
            name="CRM Internal",
            summary="Internal CRM helper",
            category="crm",
        )
        internal_release = NodeRegistryRelease.objects.create(
            package=internal_package,
            version="1.0.0",
            status="approved",
            package_kind="runtime_tool",
            execution_node_type="tool",
            manifest_version=2,
            config_defaults={"tool": "crm_internal"},
            runtime_manifest={
                "name": "crm_internal",
                "version": "1.0.0",
                "category": "crm",
                "visibility": "internal",
                "input_schema": {"type": "object"},
                "execution": {
                    "type": "http",
                    "timeout_seconds": 10,
                    "http": {"url": "https://example.com/internal", "method": "POST"},
                },
                "side_effects": {"type": "read", "idempotent": True},
            },
        )
        NodePackageInstallation.objects.create(
            organization=user.default_organization,
            package=internal_package,
            release=internal_release,
            install_metadata={},
        )

        graph = Graph.objects.create(owner=user, name="Backend Selected Tool Graph")
        version = GraphVersion.objects.create(
            graph=graph,
            version=1,
            graph_json={
                "nodes": [
                    {
                        "id": "agent_1",
                        "type": "agent",
                        "name": "Agent",
                        "config": {
                            "tool_selection": {"categories": ["crm"], "max_tools": 5},
                            "approval_required_tools": ["crm_lookup"],
                        },
                    },
                    {
                        "id": "tool_1",
                        "type": "tool",
                        "name": "Lookup",
                        "config": {"tool": "crm_lookup"},
                    },
                ],
                "edges": [],
            },
        )

        response = authenticated_client.post(
            "/api/runs/start",
            {"graph_version_id": str(version.id), "input_json": {"customer_id": "cust_123"}},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED, response.data
        run = Run.objects.get(id=response.data["data"]["id"])
        assert isinstance(run.dispatch_graph_json, dict)

        agent_node = next(
            node for node in run.dispatch_graph_json["nodes"] if node["id"] == "agent_1"
        )
        tool_node = next(
            node for node in run.dispatch_graph_json["nodes"] if node["id"] == "tool_1"
        )
        tool_resolution = run.dispatch_graph_json["metadata"]["tool_resolution"]

        assert agent_node["config"]["tools"] == ["crm_lookup"]
        assert agent_node["config"]["tool_versions"] == {"crm_lookup": "1.2.0"}
        assert tool_node["config"]["version"] == "1.2.0"
        assert [tool["name"] for tool in tool_resolution["pinned_tools"]] == ["crm_lookup"]
        assert tool_resolution["agent_nodes"]["agent_1"]["tools"] == ["crm_lookup"]
        assert tool_resolution["manifest_version"] == 2
        assert "backend_attempt_id" not in run.dispatch_graph_json["metadata"]
        assert "tool_execution_id" not in tool_node["config"]

        start_calls = [call for call in mock_engine_client.calls if call[0] == "start_run"]
        assert len(start_calls) == 1
        payload_graph = start_calls[0][1]["graph_json"]
        payload_tool_node = next(node for node in payload_graph["nodes"] if node["id"] == "tool_1")
        assert payload_graph["metadata"]["tool_resolution"] == tool_resolution
        assert "backend_attempt_id" in payload_graph["metadata"]
        assert payload_tool_node["config"]["tool_execution_id"]
        assert payload_tool_node["config"]["idempotency_key"]
