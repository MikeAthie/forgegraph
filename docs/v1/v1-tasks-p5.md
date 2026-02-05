# P5: Platform Ecosystem + Growth (Weeks 13-16)

## Objective
Expand the integration ecosystem and enable rapid adoption through templates and onboarding.

## Prerequisites
- P4 scale and observability tasks complete.
- P3 billing and entitlement checks enforced.

---

## Task List

### P5-T01: Node SDK + Marketplace
Effort: Medium

Why critical:
A platform needs a predictable way for teams and partners to add integrations.

Implementation steps:
1. Define a node SDK with schema, UI metadata, and execution contracts.
2. Add a registry service to publish, version, and approve nodes.
3. Add UI to discover and install approved nodes.

Recommended patterns / best practices:
- Sandbox untrusted nodes with strict egress policies.
- Version nodes with semantic versioning and changelogs.

Testing strategy:
- Unit: SDK validation for schema and config types.
- Integration: install a node and execute within a graph.

Success criteria / Definition of Done:
- [ ] A new node can be added without core engine changes.
- [ ] Registry supports versioning and review workflow.
- [ ] Installed nodes appear in the palette and execute correctly.

Dependencies:
- P2 guardrails and policies.

Risks:
- Third-party nodes can introduce security and stability risks.

---

### P5-T02: Template Library + Versioning
Effort: Small

Why critical:
Templates drive adoption and reduce time-to-value.

Implementation steps:
1. Add template versioning and change logs.
2. Enable sharing across orgs with read-only access.
3. Add template ratings and usage analytics.

Recommended patterns / best practices:
- Templates are immutable; edits create new versions.
- Keep template metadata small for fast discovery.

Testing strategy:
- Integration: clone template v2 and run without manual fixes.
- E2E: user can browse, preview, and apply template.

Success criteria / Definition of Done:
- [ ] Templates are versioned and discoverable by tags.
- [ ] Sharing is read-only by default and auditable.
- [ ] Analytics capture template adoption and success rate.

Dependencies:
- P0 onboarding flow and templates.

Risks:
- Template drift if underlying nodes change.

---

### P5-T03: Integration Expansion + OAuth Wizards
Effort: Medium

Why critical:
Popular integrations define platform stickiness and retention.

Implementation steps:
1. Add top integrations (Slack, Notion, HubSpot, Jira, Google Drive).
2. Implement OAuth wizard flows with scoped permissions.
3. Add credential health checks and reauth prompts.

Recommended patterns / best practices:
- Centralized OAuth provider config with tenant isolation.
- Least-privilege scopes and reauth reminders.

Testing strategy:
- Integration: OAuth connect and revoke per provider.
- E2E: node execution with refreshed credentials.

Success criteria / Definition of Done:
- [ ] At least 10 new integrations are usable end-to-end.
- [ ] OAuth setup is self-serve and completes in under 2 minutes.
- [ ] Credential errors are surfaced with remediation steps.

Dependencies:
- P3 org and credential model.

Risks:
- Provider API changes and quota limits.

---

### P5-T04: Onboarding + Guided Templates
Effort: Small

Why critical:
Product-led growth depends on fast, guided activation.

Implementation steps:
1. Add guided setup for the top 3 templates with inline help.
2. Add in-product checklists for onboarding milestones.
3. Add sample data mode for sandboxed demos.

Recommended patterns / best practices:
- Keep onboarding steps under 10 minutes.
- Track activation events for funnel analysis.

Testing strategy:
- E2E: new user completes guided template flow.
- Analytics: activation funnel events are emitted.

Success criteria / Definition of Done:
- [ ] New users can reach first successful run in under 10 minutes.
- [ ] Activation funnel shows drop-off points with analytics.
- [ ] Guided templates reduce support tickets.

Dependencies:
- P5-T02 template versioning.

Risks:
- Overly complex onboarding can slow adoption.
