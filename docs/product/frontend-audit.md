# Frontend Audit

This audit records the product and UX issues found in the current frontend before the launch revamp.

## Scope Reviewed

Routes reviewed:

- `/`
- `/login`
- `/register`
- `/onboarding`
- `/overview`
- `/companies`
- `/companies/new`
- `/companies/[companyId]`
- `/graphs`
- `/graphs/[graphId]`
- `/workflows`
- `/workflows/[workflowId]`
- `/runs`
- `/runs/[runId]`
- `/executions`
- `/executions/[executionId]`
- `/agents`
- `/tasks`
- `/inbox`
- `/approvals`
- `/memory`
- `/accounting`
- `/library`
- `/prompts`
- `/credentials`
- `/settings`
- `/admin/*`
- `/analytics/*`

Core shared components reviewed:

- `components/shell/OsShell.tsx`
- `components/DashboardLayout.tsx`
- `components/AuthLayout.tsx`
- `components/os/operations-ui.tsx`
- `components/company/*`
- `components/os/ExecutionDetailView.tsx`
- `components/graph-editor/*`
- `components/os/SettingsHub.tsx`

## Audit Summary

The frontend is currently split between three competing product stories:

1. company-first surfaces
2. organization or agent-ops surfaces
3. graph and workflow builder surfaces

That split creates product confusion. A new user can still encounter `workflow`, `graph`, `execution`, `run`, `node`, `revision`, `provider`, and `credential` language before they understand that ForgeGraph is supposed to help them create and operate an AI-driven company.

## Global Findings

### 1. Product identity is inconsistent

Issues:

- Landing and auth still describe ForgeGraph as an `AI Organization OS`.
- Metadata in `_document.tsx` still markets a visual AI agent builder.
- Some pages describe the product as an operations center, others as a workflow workspace.

Impact:

- The product does not present a single mental model.
- The user is asked to reconcile company, organization, workflow, graph, run, agent, and execution concepts.

Required change:

- Standardize the product story around `AI Company Operating System`.

### 2. Internal engine concepts are still exposed in primary UI

Issues:

- `workflow`, `graph`, `revision`, `execution`, `run`, `node`, `provider`, and `credential` appear in primary page copy.
- Graph editor labels expose raw engine nouns in visible panels.
- Execution views expose raw runtime detail before user-facing interpretation.

Impact:

- The user is forced to learn the implementation model instead of the company model.

Required change:

- Translate engine terms into company terms everywhere except explicit debug or advanced mode panels.

### 3. Navigation still implies multiple primary products

Issues:

- The shell mixes `Companies`, `Dashboard`, `Agents`, `Tasks`, `Workflows`, and `Marketplace` as peers.
- `Workflows` remains a primary nav item even though it should be an advanced surface.
- `Overview` still behaves like an organization dashboard instead of a command-ops entry point for operating companies.

Impact:

- The user cannot tell what the main task is when entering the app.

Required change:

- Make company operation primary.
- Move graph and workflow authoring into advanced mode.

### 4. Visual hierarchy still reflects the old system

Issues:

- Many pages share the same panel grammar, but the layout still feels like a dashboard collection rather than a company workspace.
- Operational controls are frequently secondary to monitoring widgets.
- Some pages optimize for traces and projections instead of obvious company actions.

Impact:

- The UI reads like a control-plane explorer, not a product for operating companies.

Required change:

- Rebuild the layout around three obvious ideas:
  - company
  - operation
  - command action

## Page Review

### `/`

User goal:

- Understand what ForgeGraph is and how to start.

Issues:

- Headline centers `digital company of autonomous agents` instead of the simpler company-creation story.
- Secondary CTA sends users to workflows.
- Copy still uses `organization`, `agents`, and `workflow builder`.

Required change:

- Reframe landing around creating and operating an AI-driven company.
- Make `Create company` and `Open companies` the primary actions.

### `/login` and `/register`

User goal:

- Access the product and begin operating a company.

Issues:

- Auth hero copy centers `agents, decisions, memory, and cost`.
- Branding still says `AI Organization OS`.

Required change:

- Reframe auth around entering a company operating system.

### `/overview`

User goal:

- Understand what is happening and where attention is needed.

Issues:

- Page reads as an organization dashboard.
- Heavy use of `agent`, `task`, and `execution`.
- Good operational structure, but wrong top-level product language.

Required change:

- Convert to a company portfolio command center.
- Reframe cards and lists around companies, operations, deliverables, approvals, and attention.

### `/companies`, `/companies/new`, `/companies/[companyId]`

User goal:

- Create, continue, and operate a company.

Issues:

- These are the most aligned routes already.
- Debug and advanced links are acceptable but the surrounding shell still leaks old naming.

Required change:

- Make these the primary product center of gravity.

### `/onboarding`

User goal:

- Start quickly.

Issues:

- Current route is template and graph oriented.
- Flow still exposes graph names, templates, and live run setup.

Required change:

- Replace with the company builder flow or route directly into it.

### `/graphs` and `/workflows`

User goal:

- Expert editing and advanced operating-model work.

Issues:

- Primary UI still says `workflow definitions`, `revisions`, `builder workspace`, and `new workflow`.
- These routes feel too important in current IA.

Required change:

- Rebrand as advanced mode.
- Explicitly describe them as operating-model editing tools.

### `/graphs/[graphId]` and `/workflows/[workflowId]`

User goal:

- Expert-level editing of the operating model.

Issues:

- Header says `Workflow Editor`.
- Errors, loading, and back links are workflow-first.
- Graph editor itself exposes graph and node language throughout the visible UI.

Required change:

- Relabel wrapper route as `Advanced Operating Model Editor`.
- Keep raw technical labels inside advanced mode only.

### `/runs`, `/executions`, `/executions/[executionId]`

User goal:

- Understand work in progress, recent results, and failures.

Issues:

- Primary language is `execution`, `trace`, `workflow revision`, `node`, and `human gate`.
- Operation detail is strong structurally, but the narrative is runtime-first rather than company-first.

Required change:

- Reinterpret as operations and department activity.
- Translate failures and outputs into actionable company language.

### `/agents`

User goal:

- Understand who is doing work.

Issues:

- Page is useful, but `agent` is not the best primary noun for the customer-facing surface.
- Registry lineage and workflow provenance are too prominent in visible copy.

Required change:

- Reframe as departments or AI workers within the company.

### `/tasks`

User goal:

- Track work that is moving or blocked.

Issues:

- Page is closer to acceptable, but still framed as system tasks and execution linkage.

Required change:

- Reframe as department activity or operation work queue.

### `/inbox` and `/approvals`

User goal:

- Review consequential decisions.

Issues:

- Strong structure already.
- Copy still refers to runs and executions where `operation` would be better.

Required change:

- Keep as a core command-ops surface with company-first terminology.

### `/memory`

User goal:

- Inspect retained knowledge and context.

Issues:

- Useful for advanced users, but terminology is still system-facing.

Required change:

- Reframe as company knowledge or institutional memory.

### `/accounting`

User goal:

- Understand spend and operating limits.

Issues:

- Page is readable, but still framed around organization economics instead of company operating limits.

Required change:

- Reframe as usage and budget posture for the operating company.

### `/library`, `/prompts`, `/credentials`, `/settings`, `/admin/*`, `/analytics/*`

User goal:

- Configure supporting systems and advanced capabilities.

Issues:

- These routes are not company-first.
- Several pages use developer or infra language directly.
- They feel like first-class product sections when many should be support or advanced mode.

Required change:

- Keep them available, but visually subordinate them.
- Reframe `credentials` as AI access.
- Reframe settings as operating-environment configuration.

## Misaligned Terminology

Highest-priority misalignments:

- `AI Organization OS`
- `Organization Dashboard`
- `Workflow Workspace`
- `Execution Visibility`
- `Workflow definition`
- `Workflow revision`
- `Graph`
- `Graph version`
- `Run`
- `Execution`
- `Node`
- `Provider`
- `Credential`

Required replacements:

- `Company`
- `Company operating model`
- `Saved version`
- `Operation`
- `Department`
- `Skill`
- `Department activity`
- `AI access mode`
- `Deliverable`
- `Needs attention`

## UX Friction Points

- The first-time path is still split between company creation and workflow creation.
- The main shell exposes too many peer concepts at once.
- Advanced builder tools are too close to primary navigation.
- Operation inspection is detailed, but not translated enough for business users.
- Auth and landing do not match the company doctrine.
- Metadata and marketing copy still sell a visual builder.

## Remove Or Replace

Remove from primary UX:

- workflow-first CTAs
- graph-first labels
- execution-first language
- provider-configuration framing
- organization-first product identity

Move to advanced mode:

- graph editor
- workflow definition management
- raw revisions language
- low-level runtime drill-down language

Keep only in debug or advanced surfaces:

- graph id
- version id
- run id
- node id
- raw JSON

## Revamp Priorities

1. Make company routes the primary entry and operating model.
2. Rewrite shell navigation and page metadata to support company-first thinking.
3. Rewrite landing and auth so the product promise is obvious.
4. Convert operations and failure views into customer-facing language.
5. Rebrand graph and workflow routes as advanced mode.
6. Reduce or hide graph-first and workflow-first naming from primary flows.
