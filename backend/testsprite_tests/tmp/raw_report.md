
# TestSprite AI Testing Report(MCP)

---

## 1️⃣ Document Metadata
- **Project Name:** backend
- **Date:** 2026-04-01
- **Prepared by:** TestSprite AI Team

---

## 2️⃣ Requirement Validation Summary

#### Test TC001 post api auth register user registration
- **Test Code:** [TC001_post_api_auth_register_user_registration.py](./TC001_post_api_auth_register_user_registration.py)
- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/03cde7b6-4b2f-4009-bcb1-97561b46496f/8466f3ea-57f7-40f8-b1f5-344e699f00b2
- **Status:** ✅ Passed
- **Analysis / Findings:** {{TODO:AI_ANALYSIS}}.
---

#### Test TC002 post api auth login user authentication
- **Test Code:** [TC002_post_api_auth_login_user_authentication.py](./TC002_post_api_auth_login_user_authentication.py)
- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/03cde7b6-4b2f-4009-bcb1-97561b46496f/8bb619ad-3578-4435-8f2d-0f199a64d749
- **Status:** ✅ Passed
- **Analysis / Findings:** {{TODO:AI_ANALYSIS}}.
---

#### Test TC003 post api auth logout invalidate session
- **Test Code:** [TC003_post_api_auth_logout_invalidate_session.py](./TC003_post_api_auth_logout_invalidate_session.py)
- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/03cde7b6-4b2f-4009-bcb1-97561b46496f/1d823f63-9e2c-4404-933b-966ee0cdbfca
- **Status:** ✅ Passed
- **Analysis / Findings:** {{TODO:AI_ANALYSIS}}.
---

#### Test TC004 post api auth refresh token refresh
- **Test Code:** [TC004_post_api_auth_refresh_token_refresh.py](./TC004_post_api_auth_refresh_token_refresh.py)
- **Test Error:** Traceback (most recent call last):
  File "/var/task/handler.py", line 258, in run_with_retry
    exec(code, exec_env)
  File "<string>", line 65, in <module>
  File "<string>", line 20, in test_post_api_auth_refresh_token_refresh
AssertionError: Registration failed: {"id":"98ee4462-825b-4556-85c2-3ca3ca49a7e3","email":"testuser_f890cd7b-f19f-40d0-9b87-c8b43c9b7396@example.com","created_at":"2026-04-01T09:12:16.858984Z","is_active":true,"default_organization_id":"63ce7cc9-0336-4578-bf30-479959c58518","organization_role":"owner"}

- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/03cde7b6-4b2f-4009-bcb1-97561b46496f/f3e19e02-a60b-4655-86ed-13a66ac638c5
- **Status:** ❌ Failed
- **Analysis / Findings:** {{TODO:AI_ANALYSIS}}.
---

#### Test TC005 get api auth me get authenticated user profile
- **Test Code:** [TC005_get_api_auth_me_get_authenticated_user_profile.py](./TC005_get_api_auth_me_get_authenticated_user_profile.py)
- **Test Error:** Traceback (most recent call last):
  File "/var/task/handler.py", line 258, in run_with_retry
    exec(code, exec_env)
  File "<string>", line 61, in <module>
  File "<string>", line 40, in test_tc005_get_api_auth_me_authenticated_user_profile
AssertionError: Login response missing refresh token

- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/03cde7b6-4b2f-4009-bcb1-97561b46496f/ab358ab6-cc35-4de2-bb42-9ee0a9444199
- **Status:** ❌ Failed
- **Analysis / Findings:** {{TODO:AI_ANALYSIS}}.
---

#### Test TC006 get api auth sso provider get sso metadata
- **Test Code:** [TC006_get_api_auth_sso_provider_get_sso_metadata.py](./TC006_get_api_auth_sso_provider_get_sso_metadata.py)
- **Test Error:** Traceback (most recent call last):
  File "/var/task/handler.py", line 258, in run_with_retry
    exec(code, exec_env)
  File "<string>", line 72, in <module>
  File "<string>", line 22, in test_get_api_auth_sso_provider_with_auth_and_without
AssertionError: Registration failed: {"id":"68195c2a-38b6-4c34-8a8e-613adff88445","email":"testuser_303f9903-c46c-4bba-8a55-f0265dd15aa3@example.com","created_at":"2026-04-01T09:12:10.670437Z","is_active":true,"default_organization_id":"d97cd69a-7c73-4628-81ae-829f0489f4e9","organization_role":"owner"}

- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/03cde7b6-4b2f-4009-bcb1-97561b46496f/5771d55e-b2ea-4061-80d7-e021ba79dcef
- **Status:** ❌ Failed
- **Analysis / Findings:** {{TODO:AI_ANALYSIS}}.
---

#### Test TC007 post api graphs validate graph payload validation
- **Test Code:** [TC007_post_api_graphs_validate_graph_payload_validation.py](./TC007_post_api_graphs_validate_graph_payload_validation.py)
- **Test Error:** Traceback (most recent call last):
  File "/var/task/handler.py", line 258, in run_with_retry
    exec(code, exec_env)
  File "<string>", line 95, in <module>
  File "<string>", line 39, in test_post_api_graphs_validate_graph_payload_validation
  File "<string>", line 12, in register_user
AssertionError

- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/03cde7b6-4b2f-4009-bcb1-97561b46496f/68333eab-1969-4d9f-bb58-f36bb0d600e7
- **Status:** ❌ Failed
- **Analysis / Findings:** {{TODO:AI_ANALYSIS}}.
---

#### Test TC008 post api graphs create new workflow graph
- **Test Code:** [TC008_post_api_graphs_create_new_workflow_graph.py](./TC008_post_api_graphs_create_new_workflow_graph.py)
- **Test Error:** Traceback (most recent call last):
  File "/var/task/handler.py", line 258, in run_with_retry
    exec(code, exec_env)
  File "<string>", line 106, in <module>
  File "<string>", line 23, in test_post_api_graphs_create_new_workflow_graph
AssertionError: Register failed: {"id":"fdb351c0-1fd4-48ff-83f3-19ed09c52af3","email":"testuser_ef1facec-3281-4629-bdcb-e53abe621e93@example.com","created_at":"2026-04-01T09:12:18.321424Z","is_active":true,"default_organization_id":"f31a5991-3f6f-47e9-8c23-c4b952089a44","organization_role":"owner"}

- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/03cde7b6-4b2f-4009-bcb1-97561b46496f/87483335-b2db-4194-8855-d0357d32fd34
- **Status:** ❌ Failed
- **Analysis / Findings:** {{TODO:AI_ANALYSIS}}.
---

#### Test TC009 post api runs start start graph run
- **Test Code:** [TC009_post_api_runs_start_start_graph_run.py](./TC009_post_api_runs_start_start_graph_run.py)
- **Test Error:** Traceback (most recent call last):
  File "/var/task/handler.py", line 258, in run_with_retry
    exec(code, exec_env)
  File "<string>", line 111, in <module>
  File "<string>", line 22, in test_post_api_runs_start_start_graph_run
AssertionError: Register failed: {"id":"682a76f5-c270-49e8-bd9b-4db66d9ca113","email":"testuser_7f9bb343-f5c4-45d8-95cd-88fafd474d24@example.com","created_at":"2026-04-01T09:12:20.219032Z","is_active":true,"default_organization_id":"5419ccbb-b058-4cc3-bb56-a12401716278","organization_role":"owner"}

- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/03cde7b6-4b2f-4009-bcb1-97561b46496f/d6f94f6b-0044-4c6a-abd6-a32972429f65
- **Status:** ❌ Failed
- **Analysis / Findings:** {{TODO:AI_ANALYSIS}}.
---

#### Test TC010 post api runs engine events receive engine callback
- **Test Code:** [TC010_post_api_runs_engine_events_receive_engine_callback.py](./TC010_post_api_runs_engine_events_receive_engine_callback.py)
- **Test Error:** Traceback (most recent call last):
  File "/var/task/handler.py", line 258, in run_with_retry
    exec(code, exec_env)
  File "<string>", line 68, in <module>
  File "<string>", line 40, in test_post_api_runs_engine_events_receive_engine_callback
AssertionError: Expected 200 OK for valid signature, got 401

- **Test Visualization and Result:** https://www.testsprite.com/dashboard/mcp/tests/03cde7b6-4b2f-4009-bcb1-97561b46496f/883f3640-ad44-4333-bb67-822c99c090bf
- **Status:** ❌ Failed
- **Analysis / Findings:** {{TODO:AI_ANALYSIS}}.
---


## 3️⃣ Coverage & Matching Metrics

- **30.00** of tests passed

| Requirement        | Total Tests | ✅ Passed | ❌ Failed  |
|--------------------|-------------|-----------|------------|
| ...                | ...         | ...       | ...        |
---


## 4️⃣ Key Gaps / Risks
{AI_GNERATED_KET_GAPS_AND_RISKS}
---