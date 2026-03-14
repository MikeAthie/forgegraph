# P1 Memory Narrative

## Why Curated Memory Exists
ForgeGraph already had operational memory layers before P1:
- buffer memory for recent conversation state
- session and summary storage for short-lived continuity
- vector chunk retrieval for semantic recall

Those layers were useful, but they were not a product concept a builder could explicitly save, browse, debug, or trust. P1 adds that missing layer: curated observations.

## What Curated Memory Is
Curated memory is a durable, explicit observation object that a workflow chooses to save and later retrieve. It is:
- scoped to tenant and then graph, run, or session
- visible in APIs, gRPC, graph nodes, the Memory Browser, and run/debugger UX
- usable as an explicit context source for prompt and agent execution

## How It Differs From Existing Memory
| Memory Type | Purpose | Builder-facing? | Durable? | Inspectable? |
| --- | --- | --- | --- | --- |
| KV / memory node | shared workflow state values | yes | depends on config | limited |
| recent buffer | immediate conversational context | mostly implicit | short-lived | no |
| summary memory | condensed prior interaction state | semi-implicit | medium-lived | limited |
| vector chunk retrieval | semantic recall over chunks | mostly backend/runtime | yes | limited |
| curated observations | explicit remembered facts, preferences, summaries, and notes | yes | yes | yes |

Curated memory is not a replacement for the other layers. It is the governed, product-visible layer that sits above them.

## Officially Supported MVP Workflows
- Memory Browser inspection: search, timeline, detail, and scope-aware review of observations.
- Explicit runtime memory flows: save, search, context, and timeline nodes in the graph editor.
- Prompt and agent curated context composition through `observation_context_paths`.
- Jackie memory workflow: recall curated context, answer, save a new observation, and inspect the influence in the run UI.

## Not Supported In MVP
- passive extraction from every run
- public MCP or external memory productization
- broad template-gallery expansion around memory
- organization-wide knowledge management features

## Product Positioning
P1 makes ForgeGraph memory-native in a way users can understand:
- builders can author memory behavior explicitly
- operators can inspect what was remembered and why
- demos can show a truthful save -> later retrieval -> influenced answer story

That is the core P1 claim: ForgeGraph does not just have hidden memory plumbing; it has explicit, inspectable curated memory.
