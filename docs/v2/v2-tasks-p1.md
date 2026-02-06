# P1: Visual Builder + Wizard UX (Weeks 3-4)

## Objective
Deliver a polished low-code creation experience that enables non-technical users to build and run agents successfully.

## Prerequisites
- P0 core runtime tasks complete.
- Node schemas and validation messages stabilized.

---

## Task List

### P1-T01: Drag-and-Drop Canvas Polish
Effort: Medium

Why critical:
The visual editor is a primary differentiator versus code-first frameworks.

Implementation steps:
1. Improve drag placement accuracy and snap behavior.
2. Harden edge linking flow (handles, hover states, invalid connection feedback).
3. Add auto-routing for clearer edge paths in dense graphs.
4. Optimize pan/zoom performance for larger node counts.

Recommended patterns / best practices:
- Maintain 60fps interactions for common graph sizes.
- Separate UI interaction state from persisted graph state.

Testing strategy:
- E2E: drag, connect, pan, zoom, and delete flows.
- Manual stress test: 100-node graph interaction.

Success criteria / Definition of Done:
- [ ] User can draw and connect a workflow without interaction errors.
- [ ] Edge routing remains readable after moving nodes.
- [ ] Canvas remains responsive on expected graph sizes.

Dependencies:
- Existing GraphEditor canvas foundation.

Risks:
- Over-rendering from frequent state updates.

---

### P1-T02: Agent Wizard Completion + Presets
Effort: Medium

Why critical:
Wizard-based setup is key for first-run activation.

Implementation steps:
1. Validate end-to-end wizard flow (Start, Prompt, Tools, Memory, Output).
2. Add prebuilt presets: "Telegram bot", "Email responder", and one memory-first preset.
3. Add preflight validation with actionable fix links before wizard completion.
4. Add one-click "Create and Run Test" handoff.

Recommended patterns / best practices:
- Keep wizard steps linear with optional advanced sections.
- Save draft progress between sessions.

Testing strategy:
- E2E: complete wizard-only flow to successful run.
- Unit: wizard state transitions and validation rules.

Success criteria / Definition of Done:
- [ ] Non-technical user can build a working agent via wizard alone.
- [ ] Presets prefill common node configs and credential hints.
- [ ] Wizard blocks invalid graphs with clear remediation.

Dependencies:
- Template and node form metadata.

Risks:
- Preset drift when node schemas evolve.

---

### P1-T03: Searchable Node Palette
Effort: Small

Why critical:
Node discoverability directly impacts usability and speed.

Implementation steps:
1. Build indexed node catalog (name, type, tags, description, category).
2. Add keyboard-first search and quick add actions.
3. Display required credentials and capability badges in search results.
4. Add recently used and recommended sections.

Recommended patterns / best practices:
- Fuzzy search with deterministic ranking.
- Keep catalog metadata centralized to avoid duplicates.

Testing strategy:
- Unit: search ranking and filter behavior.
- E2E: add node by name via keyboard only.

Success criteria / Definition of Done:
- [ ] User can find any supported node by name quickly.
- [ ] Palette includes descriptions for all node types.
- [ ] Keyboard navigation is complete and reliable.

Dependencies:
- Node type registry metadata.

Risks:
- Incomplete metadata reducing result quality.

---

### P1-T04: Templates + Quick Starts
Effort: Small

Why critical:
Templates reduce time-to-value and improve conversion.

Implementation steps:
1. Add launch templates for "Personal Assistant (Telegram + Gmail)" and "WhatsApp Chatbot".
2. Prefill boilerplate node config and credential placeholders.
3. Add template preview including required credentials and expected outputs.
4. Add template versioning metadata for future updates.

Recommended patterns / best practices:
- Templates should be immutable snapshots.
- Include sample test input for every template.

Testing strategy:
- E2E: create graph from template and run with minimal edits.
- Integration: template clone preserves valid graph structure.

Success criteria / Definition of Done:
- [ ] Users can start from a template with most fields pre-filled.
- [ ] Template run succeeds after credentials are connected.
- [ ] Template metadata clearly communicates setup effort.

Dependencies:
- Credential UX and integration node readiness.

Risks:
- Broken templates if node contracts change.

---

### P1-T05: Onboarding Guide + Inline Help
Effort: Small

Why critical:
Self-serve onboarding reduces support load.

Implementation steps:
1. Add inline tips and contextual tooltips for key node settings.
2. Add "Learn more" links from node dialogs to docs.
3. Add first-run checklist with progress indicators.
4. Add contextual error explanations with fixes.

Recommended patterns / best practices:
- Tooltips should explain intent, not duplicate labels.
- Keep docs links version-aware.

Testing strategy:
- E2E: first-time user can complete core setup without docs hunting.
- UX review: tooltip clarity and placement.

Success criteria / Definition of Done:
- [ ] New users understand core features without reading full docs first.
- [ ] Help links exist on all high-friction node forms.
- [ ] First-run checklist completion is trackable.

Dependencies:
- Updated user guide sections.

Risks:
- Excessive help text can clutter forms.

---

### P1-T06: Accessibility + Shortcuts
Effort: Small

Why critical:
Keyboard productivity and accessibility are required for production use.

Implementation steps:
1. Implement and document keyboard shortcuts (`Ctrl+W`, `Ctrl+S`, etc.).
2. Ensure palette, inspector, and dialogs are fully keyboard navigable.
3. Improve focus management for modals and canvas controls.
4. Add accessibility checks for labels, contrast, and ARIA roles.

Recommended patterns / best practices:
- Use consistent shortcut scopes and conflict resolution.
- Accessibility checks in CI for critical pages.

Testing strategy:
- E2E: keyboard-only create/save/run flow.
- Automated accessibility checks on graph pages.

Success criteria / Definition of Done:
- [ ] Documented shortcuts work reliably.
- [ ] Keyboard-only workflow is usable end-to-end.
- [ ] Critical graph editor views pass accessibility checks.

Dependencies:
- Stable UI component primitives.

Risks:
- Shortcut collisions with browser defaults.
