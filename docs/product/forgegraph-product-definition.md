# ForgeGraph Product Definition

This document is the product source of truth for the frontend rebuild.

ForgeGraph is an AI Company Operating System.

Users do not come to ForgeGraph to create graphs. They come to ForgeGraph to create and operate AI-driven companies that execute real work against defined objectives.

## Product Definition

ForgeGraph is a system where a user creates a company, configures how that company operates, and then uses the product to launch, supervise, approve, and improve company work.

The product should feel like all of the following at once:

- an ERP for an AI-driven company
- a command operations center
- a meeting room for approvals and decisions
- a creative studio for shaping how the company works
- an AI-operated company workspace

The intended user feeling is:

`I created a company. It has departments. It can do work. I can operate it.`

## What ForgeGraph Is

- A company creation and operating system for AI-driven work
- A workspace for setting objectives, defining departments, assigning skills and tools, and launching operations
- A command layer for monitoring status, approvals, failures, outputs, and budget
- A system for operating real business functions, not just generating answers

## What ForgeGraph Is Not

- Not a chatbot
- Not a graph editor first
- Not a raw workflow runner
- Not a consulting answer generator

## Core Product Doctrine

- The company is the primary product object.
- The operating model is the primary configuration object.
- Operations are the primary unit of active work.
- Deliverables are the primary output object.
- Autonomy is an execution policy, not just a visual setting.
- AI access mode is a product choice, not a low-level provider configuration screen.
- Backend-owned state is authoritative for company status, operations, approvals, liveness, outputs, and recovery.

## Experience Rules

- The default mental model must be company-first, not graph-first.
- The default entry point should help the user create or operate a company, not edit raw topology.
- Build surfaces should explain how the company works in business language before exposing engine structure.
- Operate surfaces should summarize state, risks, outputs, and required decisions before exposing traces or logs.
- If a UI element exposes engine language directly, it must be translated into company language.

## Core User Scenarios

ForgeGraph is built around three primary scenarios:

1. Create a company
2. Continue work inside an existing company
3. Command operations across the company

Detailed flows live in [company-workspace-model.md](./company-workspace-model.md).

## Alpha Non-Goals

Alpha should not prioritize:

- complex graph editor UI
- advanced RBAC
- billing UI
- multi-page dashboards
- complex analytics
- cross-company data sharing

## Acceptance Standard

These docs are successful when:

- frontend work can treat them as product source of truth
- internal engine terms are consistently translated into company language
- the create, continue, and command-ops scenarios are explicit
- autonomy and AI access are handled as product concepts
- nothing frames ForgeGraph as starting life as a graph editor
