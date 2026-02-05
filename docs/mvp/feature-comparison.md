# Feature Comparison: ForgeGraph vs LangChain, LangGraph, and n8n

## Purpose
ForgeGraph targets a low-code agent builder that combines graph orchestration, memory, tools, and a visual editor. This doc summarizes what each reference product does well and the MVP capabilities ForgeGraph should match.

## Reference Products (Sourced)
LangChain
- LangChain positions itself as a framework for building LLM applications with an integrations catalog spanning models, vector stores, tools, and more; their docs state "1000+ integrations." [1]

LangGraph
- LangGraph's core primitive is a StateGraph composed of nodes and edges that route between nodes; conditional edges support branching and loops. [2]
- LangGraph highlights built-in persistence (checkpointers), first-class streaming for values, updates, and events, and human-in-the-loop via interrupts. [3]

n8n
- n8n workflows are built from nodes, and integrations are delivered as nodes. [4]
- The editor supports drag-and-drop node placement on the canvas. [5]
- n8n's integrations directory currently lists 1,340 integrations (as of Feb 4, 2026). [6]
- n8n provides Gmail and Telegram nodes with trigger and action style operations (Gmail node operations plus Gmail Trigger; Telegram operations include sending messages and getting updates). [7] [8]
- Credential setup in n8n is configured in the UI, and credentials are associated with the nodes that can access them. [9]

## Implications for ForgeGraph MVP
1. Graph runtime: Directed node and edge execution with conditional routing and loops.
2. Memory and state: Persisted run state with resumability plus streaming outputs and human-in-the-loop pauses.
3. Visual editor: Drag-and-drop node canvas plus a searchable node palette.
4. Tooling: First-class "Tool" abstraction so agent nodes can call external APIs or internal functions.
5. Integrations: Launch with a small, high-demand set (Telegram, Gmail, Calendar, Tasks, HTTP, Webhooks) and a clear path to add more.

## Prioritized MVP Tasks
1. Core graph engine: Define node and edge schema, conditional edges, loops, and state passing; ship a linear and branched flow demo.
2. LLM agent node: Model selection, prompts, tool calling, and memory injection.
3. Memory persistence: Implement checkpointer-like persistence, replay or resume, and streaming outputs.
4. Visual editor: Drag-drop canvas, edge linking, node palette, and real-time run view.
5. Integrations v1: Telegram trigger and send, Gmail list and send, Google Calendar list and create, Google Tasks list and create, and HTTP node.
6. Credentials UX: Global credential objects with per-node selection and validation.
7. Observability: Run logs, error trails, and basic audit events.

## Sources
[1] https://python.langchain.com/docs/integrations
[2] https://langchain-ai.github.io/langgraph/tutorials/usaco/usaco/
[3] https://langchain-ai.github.io/langgraphjs/reference/classes/langgraph.Pregel/
[4] https://docs.n8n.io/integrations/builtin/
[5] https://docs.n8n.io/workflows/editor-ui/
[6] https://n8n.io/integrations/
[7] https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-base.gmail/
[8] https://n8n.io/integrations/telegram/
[9] https://docs.n8n.io/embed/managing-workflows/
