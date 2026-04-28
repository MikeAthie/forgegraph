# Company Workspace Model

This document describes the product model the frontend rebuild should implement.

## Workspace Thesis

ForgeGraph is a company workspace, not a graph workspace.

The user creates a company with an objective, defines how that company is staffed and equipped, launches operations, and then supervises outputs, approvals, failures, and budget from one operating environment.

## Core Product Objects

- Company: the primary operating entity the user creates and manages
- Business objective: the result the company is meant to pursue
- Department: a functional part of the company responsible for a category of work
- Skill or tool: a capability assigned to a department
- Operating model: the saved structure that defines how the company performs work
- Operation: a live or historical unit of company work
- Task execution: a step performed by a department, AI worker, tool action, or approval gate
- Deliverable: the user-visible output produced by an operation
- Approval: a required human decision that can pause progress
- Budget and usage: the operating limits and spend posture for the company

## State Ownership Rule

The company workspace is backed by backend-authoritative state.

- Company status is backend-owned.
- Operation status, liveness, approvals, recovery, and history are backend-owned.
- Saved operating model versions are backend-owned records.
- The engine executes work but does not own durable company state.

This preserves the runtime invariants while allowing the frontend to present a company-level operating view.

## Primary UX Scenarios

## Scenario 1: Create A Company

User intent:

`I want to build a company that can perform a business function.`

This is a guided company builder, not a single button and not a raw graph editor.

The planning checkpoints below are required. User-facing labels should still use company language from [ux-vocabulary.md](./ux-vocabulary.md).

Recommended flow:

1. Choose company type
2. Define business objective
3. Choose departments or agents
4. Choose skills or tools
5. Choose autonomy level
6. Choose AI access mode
7. Review operating model
8. Launch first workflow

Builder implications:

- The product should explain company structure in business language first.
- Users should understand what each department does before seeing implementation details.
- Review should show how the company will operate, what approvals are required, and what budget or AI access constraints apply.

## Scenario 2: Continue Work

User intent:

`I already created a company and want to continue operating it.`

The planning checkpoints below are required. User-facing labels should still use company language from [ux-vocabulary.md](./ux-vocabulary.md).

Recommended flow:

1. Select company
2. See active workflows
3. Inspect departments or agents
4. Review latest outputs
5. Approve, retry, or modify workflow
6. Launch next operation

UX expectation:

- The user should land in a company operating context immediately.
- Recent work, pending approvals, and latest deliverables should be visible without opening a builder first.
- Modification should feel like adjusting how the company operates, not editing an abstract graph.

## Scenario 3: Command Ops

User intent:

`I want to understand what is happening and make decisions.`

The command surface should expose:

- company status
- active operations
- failed operations
- pending tasks
- objectives
- outputs
- budget and usage
- AI access mode (current LLM mode)
- approvals
- controls

This surface should feel like command operations for the company.

## Workspace Anatomy

The frontend rebuild should organize the product around these top-level surfaces:

- Company builder: create or update the company operating model
- Company command center: the default operating surface for status, activity, approvals, budget, and outputs
- Operation detail: inspect one operation, its task executions, deliverables, and decisions
- Department and capability views: understand who does what inside the company

## IA Guidance

- The primary entry point should be the company command center.
- The builder should be guided and business-facing.
- Operational status should be visible before deep technical traces.
- A raw graph editor, if retained, is a secondary expert surface and not the alpha center of gravity.
- The product should feel like one workspace with focused operating surfaces, not a collection of disconnected dashboards.

## Alpha Focus

For alpha, prioritize:

- guided company creation
- continued operation of an existing company
- clear command and approval flows
- understandable deliverables and operating status

Do not prioritize graph-editor-first navigation or heavy analytics-first design.
