# Autonomy Policy

This document defines autonomy and AI access as product policies.

## Product Rule

Autonomy is not only a UI preference.

Autonomy is an operation policy that controls when work can proceed automatically, when approvals are required, and what operating limits apply.

The backend must remain authoritative for the resulting durable state, approvals, liveness, and recovery decisions.

## Autonomy Modes

## Manual

Nothing starts without explicit user approval.

Characteristics:

- every consequential step waits for user approval
- useful for setup, onboarding, regulated work, or low trust situations
- highest operator control, lowest throughput

## Assisted

Default for alpha.

The system works automatically but pauses at key points.

Characteristics:

- routine work can proceed automatically
- approvals are required at important checkpoints
- balances speed with operator confidence
- recommended default while product trust and operating policies mature

## Autonomous

The company operates continuously within budget and safety limits.

Characteristics:

- the company can continue operating without step-by-step approval
- work must remain bounded by policy, budget, tool access, and safety controls
- interventions happen when limits, failures, or policy conditions are triggered

## Policy Dimensions

Autonomy policy should govern more than a label in settings.

It should define:

- approval thresholds
- retry behavior
- escalation rules
- budget ceilings
- tool access boundaries
- time or volume limits
- allowed unattended operating windows

## UX Requirements

- Company creation must ask the user to choose an autonomy mode.
- The active autonomy mode must be visible from command surfaces.
- When the mode changes system behavior, the product should explain the consequence in business terms.
- Approval queues and pause states should reflect the selected policy.

## AI Access Mode

AI access should be framed as `AI access mode`.

It should not be framed as a low-level provider configuration concern in the primary product UX.

### Managed

The system uses a ForgeGraph-managed provider with limits.

Characteristics:

- easiest setup path
- usage is controlled by ForgeGraph-defined limits and safety posture
- best default for fast onboarding

### BYOK

The user provides their own provider key.

Characteristics:

- customer-controlled model access
- useful when the user needs their own provider relationship or budget control
- should still feel like a product operating choice, not a raw infrastructure screen

## Interaction Between Autonomy And AI Access

- Autonomy determines how independently the company operates.
- AI access mode determines how the company obtains model capability.
- These are separate product choices and should be explained separately.

## Alpha Guidance

- Default autonomy mode: Assisted
- Default AI access framing: Managed vs BYOK
- Avoid surfacing unnecessary provider-specific complexity during initial company setup
