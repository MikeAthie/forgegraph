# ForgeGraph Frontend UI/UX Audit

Date: 2026-05-08

Scope: whole `frontend/` operator console, including shared shell, UI primitives, primary routes, compatibility routes, admin/specialist routes, analytics, credentials, prompts, company workspace, storefront, graph/workflow editor, and run/execution detail surfaces.

Standards used:

- `ui-ux-pro-max` local skill standards: accessibility, touch and interaction, performance, style consistency, responsive layout, typography and color, animation, forms and feedback, navigation, charts and data.
- Vercel Web Interface Guidelines, fetched on 2026-05-08 from <https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md>.
- ForgeGraph runtime source-of-truth contract in `docs/architecture/runtime-invariants.md`.

## Executive Summary

The frontend is directionally aligned with the current product model: it reads as a business/operator console, the primary shell is summary-first, and the main surfaces generally keep backend-owned state visible. The strongest parts are the shared shell, skip links, semantic links for navigation, backend provenance copy on core operator pages, dark-mode parity on major console surfaces, and visible empty/loading states.

The main audit risks are concentrated in shared foundations. Button, input, and select defaults are below the 44 px touch target standard, so the issue propagates across forms, dialogs, filters, graph-editor controls, and mobile layouts. The mobile primary navigation renders nearly every shell destination as a grid of pills, which consumes the first viewport and makes advanced routes compete with primary operator actions. Several stateful filters remain local-only, charts are hidden from assistive technology without textual equivalents, and internal runtime language leaks into product surfaces.

No P0 issue was observed in the sampled evidence. I did not find a UI path that makes the client, engine, events, or snapshots authoritative for durable state. I did find copy that exposes internal runtime terms and should be translated through the frontend domain language.

## Evidence

Live capture used a frontend-only Next dev server on `http://127.0.0.1:3001` with Playwright API mocks for authenticated shell state. Full backend/engine startup was not required for this visual pass. Mocked WebSocket ticketing produced expected console errors in the capture manifest; those are a live-pass limitation, not product evidence.

Screenshots:

- [login-desktop-light.png](./frontend-ui-ux-audit-2026-05-08-assets/login-desktop-light.png) - `/login`, 1440x900, light.
- [login-first-tab-focus.png](./frontend-ui-ux-audit-2026-05-08-assets/login-first-tab-focus.png) - `/login`, first Tab lands on skip link.
- [companies-desktop-light.png](./frontend-ui-ux-audit-2026-05-08-assets/companies-desktop-light.png) - `/companies`, 1440x900, light.
- [companies-mobile-light.png](./frontend-ui-ux-audit-2026-05-08-assets/companies-mobile-light.png) - `/companies`, 375x812, light.
- [companies-desktop-dark.png](./frontend-ui-ux-audit-2026-05-08-assets/companies-desktop-dark.png) - `/companies`, 1440x900, dark.
- [overview-wide-light.png](./frontend-ui-ux-audit-2026-05-08-assets/overview-wide-light.png) - `/overview`, 1920x1080, light.
- [llm-analytics-tablet-light.png](./frontend-ui-ux-audit-2026-05-08-assets/llm-analytics-tablet-light.png) - `/analytics/llm`, 768x1024, light.
- [capture-manifest.json](./frontend-ui-ux-audit-2026-05-08-assets/capture-manifest.json) - viewport, route, title, overflow, and capture diagnostics.

Verification run:

- `npm run lint` in `frontend/`: passed with no warnings or errors. The command notes `next lint` deprecation for Next.js 16.

## Route Coverage Matrix

| Group | Routes reviewed | Static coverage | Live evidence |
| --- | --- | --- | --- |
| Public/auth | `/`, `/login`, `/register`, `/oauth/callback`, `/sso/callback` | Yes | `/login` desktop and keyboard |
| Primary operator shell | `/companies`, `/overview`, `/departments`, `/tasks`, `/approvals`, `/memory`, `/accounting`, `/library`, `/workflows`, `/settings` | Yes | `/companies` desktop/mobile/dark, `/overview` wide |
| Compatibility | `/graphs`, `/runs`, `/inbox`, `/agents`, `/executions` | Yes | Indirect through shell mappings |
| Admin/specialist | `/admin/*`, `/analytics/*`, `/prompts`, `/credentials`, `/onboarding`, `/ops` | Yes | `/analytics/llm` tablet |
| Deep work surfaces | `/companies/[companyId]`, `/graphs/[graphId]`, `/workflows/[workflowId]`, `/runs/[runId]`, `/executions/[executionId]`, `/storefront/[companySlug]` | Yes | Static only |

## Highest-Risk Findings

### P1. Shared controls miss minimum touch target size

Evidence:

- `frontend/components/ui/button.tsx:22-27` defines default `h-9`, `h-8`, `h-10`, `size-9`, and `size-8`.
- `frontend/components/ui/input.tsx:21` defines `h-9`.
- `frontend/components/ui/select.tsx:34` defines default `h-9` and small `h-8`.

Standard: `ui-ux-pro-max` touch targets require at least 44x44 px. Vercel guidelines also require touch-friendly controls and clear interaction states.

Impact: This affects nearly every form, toolbar, dialog, filter row, graph-editor control, and mobile interaction. It is especially visible on dense forms and icon-only controls.

Recommended fix: Set shared default interactive height to `min-h-11`, make icon buttons `size-11` by default, keep dense `sm` variants only for non-touch desktop contexts, and audit call sites that force smaller heights.

Suggested verification: Playwright snapshot at 375x812 plus DOM measurement check for `button`, `input`, `[role=button]`, and select triggers.

### P1. Mobile navigation is overloaded

Evidence:

- `frontend/components/shell/OsShell.tsx:62-74` defines 11 nav items.
- `frontend/components/shell/OsShell.tsx:650-675` maps all visible items into the mobile primary nav.
- Screenshot: `companies-mobile-light.png`.

Standard: `ui-ux-pro-max` navigation rules require clear hierarchy, adaptive navigation, and no overloaded primary nav. Top-level mobile navigation should expose a small set of primary destinations and move secondary/advanced destinations into overflow.

Impact: On a 375 px viewport, navigation consumes most of the first screen before the user reaches page content. "Advanced operating models" truncates, and advanced/admin surfaces compete with daily operator work.

Recommended fix: Limit mobile primary nav to 4-5 core destinations, add a "More" or menu sheet for advanced/settings/admin routes, and keep badges only on the most actionable routes.

Suggested verification: 375x812 and 768x1024 screenshots confirm the first screen exposes the page title, key action, and first content block without excessive nav height.

### P1. Dialog foundations need mobile and focus hardening

Evidence:

- `frontend/components/ui/dialog.tsx:40` centers content with no max height, internal scroll, safe-area padding, or modal overscroll containment.
- `frontend/components/Modal.tsx:42-75` is a legacy custom modal with manual Escape handling, backdrop click on a `div`, no focus trap, and no `aria-labelledby` linkage.

Standard: Vercel guidelines call for semantic modal behavior, focus management, `overscroll-behavior: contain`, and safe-area-aware full-bleed/fixed surfaces. `ui-ux-pro-max` requires clear escape routes and mobile-safe modal layouts.

Impact: Long forms such as credentials, graph configuration, memory configuration, prompt authoring, and admin forms can become hard to operate on mobile or with keyboard/screen reader workflows.

Recommended fix: Retire the custom `Modal` in favor of the Radix dialog primitive, add `max-h-[calc(100dvh-2rem)] overflow-y-auto overscroll-contain`, safe-area padding where needed, and ensure every dialog has an accessible title and close path.

Suggested verification: Open each long form modal at 375x812, keyboard through it, press Escape, and check no background scroll or clipped footer actions.

### P1. Data visualizations lack accessible equivalents

Evidence:

- `frontend/pages/analytics/llm.tsx:74-93` renders `Sparkline` as `aria-hidden="true"` without nearby textual trend summary.
- `frontend/pages/analytics/memory.tsx:76-95` repeats the same sparkline pattern.
- `frontend/pages/analytics/llm.tsx:333-337` renders budget progress as a colored bar without semantic progress or textual range labels.

Standard: `ui-ux-pro-max` chart rules require legends, labels/tooltips, accessible colors, and not relying on color alone. Vercel guidelines require meaningful alternatives for visual data.

Impact: Screen reader users lose trend information, and low-vision users may miss progress/risk states when color is the primary signal.

Recommended fix: Give sparklines an accessible summary (`role="img"` with `aria-label`, or visible text like "Cost increased from $2 to $6 over 3 days"), add semantic progress markup for quota/budget bars, and include non-color labels for risk/threshold states.

Suggested verification: Accessibility snapshot confirms chart/progress meaning is present without relying on the SVG path.

### P1. Stateful filters are often local-only instead of URL-addressable

Evidence:

- `/companies`: `frontend/pages/companies/index.tsx:34` and `frontend/pages/companies/index.tsx:171` keep the posture filter local.
- `/memory`: `frontend/pages/memory.tsx:43-46` and `frontend/pages/memory.tsx:331-336` keep search/scope/type local.
- `/prompts`: `frontend/pages/prompts.tsx:106-152` keeps ownership/category/search local.
- `/admin/audit-logs`: `frontend/pages/admin/audit-logs.tsx:40-63` keeps filters and pagination local.
- Positive examples exist: `/tasks`, `/approvals`, `/departments`, `/library`, and `/runs` deep-link selected records.

Standard: Vercel navigation/state guidelines say URL should reflect filters, tabs, pagination, and stateful UI.

Impact: Operators cannot reliably share filtered views, browser Back does not restore review context, and audit/admin workflows are harder to reproduce.

Recommended fix: Encode meaningful filters, selection, and pagination in query params. Use shallow router updates for high-frequency filters and debounce search input.

Suggested verification: Set filters, reload, navigate away/back, and confirm state restores from URL.

### P1. Internal runtime terminology leaks into user-facing product surfaces

Evidence:

- `frontend/pages/index.tsx:245` says "Technical engine detail".
- `frontend/pages/admin/marketplace.tsx:77`, `frontend/pages/admin/marketplace.tsx:344`, and `frontend/pages/admin/marketplace.tsx:410` expose "engine" language.
- `frontend/pages/admin/marketplace.tsx:548` says "source of truth".
- `frontend/components/graph-editor/wizard/AgentWizard.tsx:252` says "engine executes".
- `frontend/components/graph-editor/NodeInspector.tsx:853` says "This is what the engine executes."
- `frontend/components/company/CompanyBuilderForm.tsx:1292` uses "Launch snapshot".

Standard: `runtime-invariants.md` states runtime terms are internal and product surfaces must translate them through canonical ontology and frontend domain ViewModels.

Impact: This does not make the engine authoritative, but it leaks implementation vocabulary into operator UX and weakens the product mental model.

Recommended fix: Add a copy pass for runtime words. Preferred replacements: "technical execution detail", "runtime service", "operating model payload", "launch summary", "backend-governed record", or domain-specific terms from `docs/product/ux-vocabulary.md`.

Suggested verification: Add a terminology check for frontend copy that flags `engine`, `snapshot`, `checkpoint`, `source of truth`, and raw event authority language outside developer/admin-only docs.

## Additional Findings

### P2. Motion system relies on `transition-all` and has limited reduced-motion coverage

Evidence:

- `frontend/components/ui/button.tsx:8`, `frontend/components/ui/theme-toggle.tsx:30-31`, `frontend/pages/overview/index.tsx:57`, `frontend/pages/companies/index.tsx:225`, `frontend/components/company/QuestGuide.tsx:122`, and multiple graph-editor files use `transition-all`.
- `frontend/styles/globals.css:231-235` only reduces smooth scrolling; component transitions remain active.

Impact: This can animate layout-affecting properties, create inconsistent motion, and ignore reduced-motion preferences.

Fix: Replace `transition-all` with explicit `transition-[color,background-color,border-color,box-shadow,transform,opacity]` as appropriate. Add global or component-level `motion-reduce:transition-none motion-reduce:transform-none`.

### P2. Forms need stronger labeling, names, and mobile keyboard semantics

Evidence:

- `frontend/pages/admin/audit-logs.tsx:122-157` filter fields rely mostly on placeholders and lack `name` attributes.
- `frontend/pages/analytics/llm.tsx:351-359` budget inputs use labels without `htmlFor`/`id`, no numeric `type`, and no `inputMode`.
- `frontend/components/ui/input.tsx:7-15` defaults non-password autocomplete to `off`, which should be deliberate per field rather than implicit for all fields.

Impact: Assistive tech, browser autofill, mobile keyboards, and form analytics are less reliable.

Fix: Add `FormField`/`Label` coverage, `name`, semantic `type`, `inputMode`, and explicit autocomplete values. Keep placeholder examples as secondary hints, not labels.

### P2. Analytics route metadata falls back to generic shell title

Evidence:

- `frontend/components/shell/OsShell.tsx:82-164` has no `/analytics` branch.
- Screenshot `llm-analytics-tablet-light.png` shows shell title "ForgeGraph" above the LLM analytics content.

Impact: Operators lose orientation on specialist pages, and page titles are inconsistent with the route content.

Fix: Add `pageMeta` branches for `/analytics/llm`, `/analytics/memory`, `/credentials`, `/prompts`, `/onboarding`, and `/storefront` where needed.

### P2. Typography and density are not always operator-console aligned

Evidence:

- `frontend/styles/globals.css:144-151` applies `letter-spacing: -0.02em` globally to headings.
- Auth and company portfolio pages use large editorial serif headings; see `login-desktop-light.png` and `companies-mobile-light.png`.

Impact: The product notes call for a business-like operating console. Display-scale editorial typography makes some app screens feel more like marketing/editorial surfaces than dense operational tools.

Fix: Keep display serif treatment for public/auth hero surfaces if desired, but use tighter sans headings inside authenticated operator views. Avoid negative global letter spacing; set heading tracking explicitly by context.

### P2. Large lists render with plain `.map()` despite high page sizes

Evidence:

- `frontend/pages/admin/audit-logs.tsx:20` sets `PAGE_SIZE = 100`; `frontend/pages/admin/audit-logs.tsx:223` maps entries directly.
- `frontend/pages/prompts.tsx:505`, `frontend/components/memory/MemoryObservationList.tsx:171`, and `frontend/pages/companies/index.tsx:216` map variable-length lists directly.

Impact: Performance and input latency can degrade as tenant data grows, especially in admin audit logs and memory/prompts.

Fix: Virtualize lists over 50 items, or page aggressively with visible result counts and stable row heights. Use `content-visibility: auto` only where it does not break keyboard navigation.

### P3. Text polish issues reduce standards consistency

Evidence:

- Loading text uses three dots in several places: `frontend/components/ProtectedRoute.tsx:22`, `frontend/components/ProtectedRoute.tsx:33`, `frontend/pages/credentials.tsx:645`, `frontend/pages/graphs.tsx:243`, and `frontend/pages/prompts.tsx:494`.
- Placeholder examples use three dots: `frontend/pages/prompts.tsx:475`, `frontend/components/graph-editor/NodePalette.tsx:168`, `frontend/components/graph-editor/NodeInspector.tsx:603`, and related graph-editor forms.

Impact: Low severity, but inconsistent with the web guideline copy rules.

Fix: Use the ellipsis character for loading/copy where the project allows non-ASCII UI copy, or standardize a repo-specific ASCII exception.

## Standards Checklist

| Category | Status | Notes |
| --- | --- | --- |
| Accessibility | Mixed | Skip links and semantic links are good; chart alternatives, form labels, modal focus, and touch targets need work. |
| Touch and interaction | Needs work | Shared control defaults are below 44 px. |
| Performance | Mixed | `content-visibility-auto` exists, but direct maps and `transition-all` remain. |
| Style selection | Mixed | Strong operator-console direction, but editorial typography and internal runtime copy weaken consistency. |
| Layout and responsive | Mixed | No horizontal overflow in sampled screenshots, but mobile nav consumes too much first-viewport space. |
| Typography and color | Mixed | Light/dark surfaces are coherent; global negative heading tracking and raw per-page color classes need consolidation. |
| Animation | Needs work | Reduced-motion coverage is incomplete and `transition-all` is widespread. |
| Forms and feedback | Mixed | Inline errors and loading states exist; labels, names, autocomplete, and numeric keyboard semantics need hardening. |
| Navigation and state | Mixed | Record selections deep-link in several routes; filters/pagination often do not. |
| Charts and data | Needs work | Data is visible, but chart semantics and non-color encodings need improvement. |
| Runtime invariants | Pass with copy debt | No durable authority violation observed; internal terminology leaks should be cleaned up. |

## Prioritized Backlog

| Priority | Work item | Affected surfaces | Acceptance criteria |
| --- | --- | --- | --- |
| P1 | Raise shared touch targets | UI primitives, forms, graph editor, shell | Default controls meet 44x44 px on touch viewports; dense variants are opt-in and documented. |
| P1 | Redesign mobile shell navigation | `OsShell`, primary routes | Mobile first viewport shows page identity and first action/content; primary nav exposes no more than 5 top-level items plus overflow. |
| P1 | Harden dialog/modal foundation | `Dialog`, legacy `Modal`, long forms | Radix dialog used consistently; long modals scroll internally; Escape/close/focus trap verified at 375x812. |
| P1 | Add accessible chart/progress summaries | Analytics, overview cost bars | Sparklines and progress bars have screen-reader summaries and do not rely on color alone. |
| P1 | URL-sync high-value filters | Companies, memory, prompts, admin audit logs, analytics | Filter/search/pagination state survives reload and Back/Forward navigation. |
| P1 | Remove internal runtime terms from product UI | Admin marketplace, graph editor, public copy, company builder | User-facing copy uses product ontology; terminology check protects future changes. |
| P2 | Replace `transition-all` and expand reduced-motion handling | Shared UI, overview, companies, graph editor | Static scan has no `transition-all`; reduced-motion screenshots show no transform/opacity motion. |
| P2 | Improve form semantics | Admin audit logs, analytics budget, credentials, graph forms | Inputs have labels, names, correct types/input modes, and deliberate autocomplete. |
| P2 | Add missing shell metadata branches | Analytics, credentials, prompts, onboarding, storefront | Header title/description match route content on all specialist routes. |
| P2 | Normalize operator-console typography | Auth, companies, shell content, globals | Auth can retain hero treatment; authenticated app screens use task-focused heading scale and no global negative tracking. |
| P2 | Virtualize or paginate large lists | Audit logs, memory, prompts, companies | Lists over 50 rows remain responsive and keyboard navigable. |
| P3 | Copy polish pass | Loading text and placeholders | Loading and placeholder copy follows the project text standard consistently. |

## Implementation Notes

- Keep runtime ownership intact: all UI fixes must continue to treat backend-materialized state as authoritative.
- Prefer shared primitive fixes first. The touch-target, motion, and form semantics issues compound through the app.
- Do mobile shell redesign before individual mobile page polish; otherwise route-level fixes will be hidden by the current nav density.
- For copy remediation, use `docs/product/ux-vocabulary.md` and frontend ViewModels rather than replacing internal terms ad hoc per component.
