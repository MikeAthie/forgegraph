# External Tool Review

This records the review of the untracked root `tools/` folder that was pasted from an external project.

Decision rule:

- Keep only tools that fit ForgeGraph's current runtime contract and execution model.
- Imported tools must be repo-native: backend-owned HTTP behavior plus engine tool manifests.
- Discard tools that are IDE shell/file editing primitives, agent-host control surfaces, or UI-specific orchestration features from the external project.

Imported tools:

| External tool | Decision | ForgeGraph target | Reason |
| --- | --- | --- | --- |
| `WebFetchTool` | Imported | `backend/adapters/api/runtime_tools/` + `engine/tool-manifests/web_research.json` | Useful runtime capability for public web retrieval; fits backend-owned HTTP execution. |
| `WebSearchTool` | Imported | `backend/adapters/api/runtime_tools/` + `engine/tool-manifests/web_research.json` | Useful runtime capability for current-information lookup; fits backend-owned HTTP execution. |

Discarded tools:

| External tool | Decision | Reason |
| --- | --- | --- |
| `AgentTool` | Discarded | External agent-host runtime and subagent UI, not a ForgeGraph manifest tool. |
| `AskUserQuestionTool` | Discarded | Interactive IDE/session prompt control, not workflow runtime behavior. |
| `BashTool` | Discarded | Shell execution primitive; incompatible with default cloud runtime and external-project specific safety model. |
| `BriefTool` | Discarded | External project briefing/upload UX, not a runtime node tool. |
| `ConfigTool` | Discarded | External host/app configuration surface, not workflow runtime behavior. |
| `EnterPlanModeTool` | Discarded | IDE mode-switch control, not a runtime tool. |
| `EnterWorktreeTool` | Discarded | IDE/worktree control surface, not a runtime tool. |
| `ExitPlanModeTool` | Discarded | IDE mode-switch control, not a runtime tool. |
| `ExitWorktreeTool` | Discarded | IDE/worktree control surface, not a runtime tool. |
| `FileEditTool` | Discarded | Filesystem editing primitive; poor fit for cloud runtime and product scope. |
| `FileReadTool` | Discarded | Local IDE filesystem read primitive, not a product/runtime integration. |
| `FileWriteTool` | Discarded | Filesystem mutation primitive; not appropriate for current runtime defaults. |
| `GlobTool` | Discarded | Repo/host file search primitive, not a ForgeGraph runtime integration. |
| `GrepTool` | Discarded | Repo/host file search primitive, not a ForgeGraph runtime integration. |
| `ListMcpResourcesTool` | Discarded | External MCP host discovery surface already handled outside runtime manifests. |
| `LSPTool` | Discarded | IDE language-server integration, not a runtime workflow tool. |
| `McpAuthTool` | Discarded | External MCP host auth UX, not runtime behavior. |
| `MCPTool` | Discarded | External MCP tool wrapper/UI, not a ForgeGraph-native runtime tool. |
| `NotebookEditTool` | Discarded | Local notebook editing primitive, not a workflow runtime integration. |
| `PowerShellTool` | Discarded | Shell execution primitive; incompatible with default cloud runtime and external safety model. |
| `ReadMcpResourceTool` | Discarded | External MCP host resource read surface, not a runtime manifest tool. |
| `RemoteTriggerTool` | Discarded | Generic external trigger helper; ForgeGraph already has native webhook/integration surfaces. |
| `REPLTool` | Discarded | External execution environment helper, not a runtime tool definition. |
| `ScheduleCronTool` | Discarded | External host scheduling UX, not a ForgeGraph runtime node tool. |
| `SendMessageTool` | Discarded | External agent-host messaging surface, not a runtime tool. |
| `SkillTool` | Discarded | External skill-loading framework, not part of ForgeGraph runtime architecture. |
| `SleepTool` | Discarded | Agent-session orchestration helper with little product/runtime value. |
| `SyntheticOutputTool` | Discarded | External testing/debugging helper, not a real runtime integration. |
| `TaskCreateTool` | Discarded | External agent-task control surface; ForgeGraph already has backend task APIs and models. |
| `TaskGetTool` | Discarded | External agent-task control surface; not a runtime manifest tool. |
| `TaskListTool` | Discarded | External agent-task control surface; not a runtime manifest tool. |
| `TaskOutputTool` | Discarded | External agent-task control surface; not a runtime manifest tool. |
| `TaskStopTool` | Discarded | External agent-task control surface; not a runtime manifest tool. |
| `TaskUpdateTool` | Discarded | External agent-task control surface; not a runtime manifest tool. |
| `TeamCreateTool` | Discarded | External agent/team control surface; not a ForgeGraph runtime integration. |
| `TeamDeleteTool` | Discarded | External agent/team control surface; not a ForgeGraph runtime integration. |
| `TodoWriteTool` | Discarded | External session planning primitive, not runtime behavior. |
| `ToolSearchTool` | Discarded | External deferred-tool discovery UI; ForgeGraph runtime manifests do not use this model. |

Discarded support artifacts removed with the folder:

- `shared/`
- `testing/`
- `utils.ts`
