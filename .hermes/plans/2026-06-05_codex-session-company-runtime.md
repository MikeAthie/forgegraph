# Codex Session Company Runtime Plan

## Problem

ForgeGraph/Atlas company runs currently depend on LLM connector access that consumes OpenAI API-token credits. For local testing and agency dogfooding, Mike wants to power a company through an existing Codex CLI/OAuth session instead of repeatedly buying API credits.

## Product framing

Use Codex as a **development/test agent runtime connector**, not as a production customer credential surface.

The goal is to let a ForgeGraph company/department stage ask a local Codex session to produce work product and then store the response as normal ForgeGraph artifacts: `Run`, `NodeRun`, `ServiceDeliverable`, `Asset`, `AssetVersion`, `TaskRoutingRecord`, and department pipeline lineage.

## Recommended shape

### 1. Add a third LLM access mode

Current backend supports:

- `managed`
- `byok`

Add:

- `codex_session`

Sanitized graph metadata should look like:

```json
{
  "llm_access": {
    "llm_mode": "codex_session",
    "provider": "codex",
    "api_key_present": false,
    "local_session_required": true
  }
}
```

Do **not** store Codex OAuth tokens in ForgeGraph DB.
Do **not** copy `~/.codex/auth.json` into company credentials.
Do **not** expose this mode to arbitrary production users by default.

### 2. Add a Codex execution adapter

Create a small backend-owned adapter, e.g.:

```text
backend/application/services/codex_session_runtime.py
```

Responsibilities:

- Check `codex --version`.
- Verify a Codex session exists without printing secrets.
- Run `codex exec` in a safe working directory.
- Pass a structured prompt containing:
  - company context
  - department/stage role
  - requested deliverable type
  - output contract
- Capture stdout/stderr, exit code, duration.
- Return a normalized result:

```python
@dataclass
class CodexSessionResult:
    status: Literal["succeeded", "failed"]
    output_text: str
    error_text: str
    command_summary: str
    duration_ms: int
```

### 3. Treat Codex output as evidence-backed artifact content

When used by Atlas departments:

- Strategy stage can ask Codex for strategy briefs.
- Brand stage can ask Codex for copy/message-house drafts.
- QA stage can ask Codex to review assembled deliverables.
- Approval Ops can ask Codex to package approval summaries.

Output should be persisted through normal ForgeGraph artifacts:

- `Asset`
- `AssetVersion`
- `ServiceDeliverable`
- `ProgramStageState.state_json.outputs`

### 4. Keep production honesty

Codex session runtime should render as:

```text
Local operator AI runtime: available for draft/testing work.
Production connector status: not a live customer deployment connector.
```

This prevents false claims that Atlas has production OpenAI/customer AI credentials configured.

### 5. Suggested first implementation slice

Implement a **dev-only Codex session provider** for department pipeline deliverable generation:

- Add `codex_session` to LLM access validation.
- Add settings flag:

```python
ENABLE_CODEX_SESSION_RUNTIME = env.bool("ENABLE_CODEX_SESSION_RUNTIME", default=False)
CODEX_SESSION_WORKDIR = env("CODEX_SESSION_WORKDIR", default=BASE_DIR.parent)
CODEX_SESSION_TIMEOUT_SECONDS = env.int("CODEX_SESSION_TIMEOUT_SECONDS", default=180)
```

- Add service `codex_session_runtime.py`.
- Add tests with a fake runner; do not call real Codex in unit tests.
- Add one integration-ish script/manual command for Mike's machine.
- Wire Atlas/Legacy pipeline so a stage can request `runtime_provider="codex_session"` and receive generated text deliverables.

## Acceptance criteria

- Backend validation accepts `llm_mode="codex_session", provider="codex"` when the feature flag is enabled.
- No API key or OAuth token is stored in `APIKey`, graph metadata, run input, logs, or output.
- Unit tests verify disabled mode rejects usage.
- Unit tests verify enabled mode produces sanitized runtime metadata.
- Codex adapter can be fake-run in tests and real-run manually.
- A department stage can create a deliverable from Codex output and attach normal department pipeline lineage.

## Risks / guardrails

1. Codex CLI is local/operator-scoped, so it is not suitable as a multi-tenant production customer runtime without a separate worker isolation model.
2. Codex can modify files if prompted poorly; default adapter should request text-only deliverables and run in a controlled workspace.
3. OAuth/session auth should remain outside ForgeGraph persistence.
4. Costs may still exist under the subscription/session provider, but this avoids direct per-run API-key credit burn in ForgeGraph tests.
5. This should not replace connector gap reporting for live production publishing.
