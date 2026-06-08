# Atlas Client Retention Product Roadmap v1

> Planning-only artifact. This roadmap focuses on the product Atlas must build to keep clients after acquisition. It intentionally ignores client acquisition/sales owned by the partner.

## 1. Product thesis

Atlas keeps clients by becoming the operating system that reliably turns a small business into a measurable customer-acquisition machine.

The retention product is not “marketing services.” It is:

> A repeatable system that diagnoses revenue opportunities, launches low-cost acquisition experiments, tracks leads/sales/commission, improves weekly, and makes the business owner feel that Atlas is creating measurable new business with minimal effort from them.

For the first market, Atlas should optimize for:

- Mexico City.
- Spanish-first client experience.
- Small businesses with low/no existing marketing spend.
- Friends/family/warm clients who trust the team.
- Commission or success-fee economics.
- Low client involvement.
- Atlas-owned execution.
- Clear proof of generated leads/sales.

## 2. Retention loops

Atlas retains clients when at least one of these loops works.

### Loop A — Revenue proof loop

1. Atlas launches a campaign.
2. Client receives qualified leads, quote requests, bookings, or sales.
3. Atlas reports attributed value.
4. Client pays commission or success fee.
5. Client wants more.

This is the primary loop.

### Loop B — Operational relief loop

1. Atlas takes annoying marketing/sales ops work off the owner.
2. Leads are followed up faster.
3. Responses, reminders, reviews, and referrals become systematic.
4. Owner feels the business is more organized without doing more work.
5. Client stays even before massive revenue proof.

### Loop C — Asset compounding loop

1. Atlas produces assets: landing pages, scripts, catalog, creatives, GBP profile, email flows.
2. Assets make future campaigns cheaper/faster.
3. Campaign performance improves over time.
4. Client sees increasing leverage.
5. Client stays.

### Loop D — Trust/reporting loop

1. Atlas sends simple weekly updates.
2. Client sees what happened, what broke, and what will change.
3. Attribution and commissions are transparent.
4. Client trusts Atlas with more execution.
5. Client stays.

## 3. North-star product outcome

A client should be able to say:

> “Atlas brings me potential customers, follows up, tells me what is working, and only gets paid meaningfully when it creates value.”

Internally, Atlas should be able to say:

> “For every client, we know the offer, channel, funnel stage, lead status, revenue, profit, commission, next action, and scale/kill decision.”

## 4. Product layers

### 4.1 Client-facing layer

What the client sees:

- Free audit package.
- 30-day action plan.
- Campaign launch plan.
- Weekly result report.
- Lead/sale attribution summary.
- Commission statement.
- Optional paid asset proposals.

Client should not need to understand ForgeGraph, whiteboards, internal task routing, or asset provenance.

### 4.2 Operator layer

What Atlas operators use:

- Intake workspace.
- Service package runner.
- Campaign readiness scorecard.
- Campaign board.
- Lead tracker.
- Asset checklist.
- Weekly review queue.
- Approval/delivery workflow.
- Commission tracker.

### 4.3 Platform layer

What ForgeGraph provides:

- Durable Company/Program/Engagement state.
- Program stages and task/card routing.
- Service deliverables and asset versions.
- Format profiles and quality gates.
- Client handoff packages.
- Campaign/lead/commission artifacts.
- Whiteboard snapshots from backend-owned state.
- Approval and delivery records.

## 5. Product roadmap overview

| Phase | Name | Goal | Client value | Internal value |
|---:|---|---|---|---|
| 0 | Foundation cleanup | Stabilize current formatter/handoff work | Reliable package output | Clean base for product work |
| 1 | Audit product | Produce excellent Spanish growth audit packages | Clear plan and trust | Repeatable client onboarding artifact |
| 2 | Campaign product | Turn audit into executable acquisition campaign | First leads/sales path | Standard campaign ops model |
| 3 | Lead/revenue tracking | Attribute leads, sales, profit, and commission | Fair success-fee model | Retention/revenue proof |
| 4 | Weekly operating cadence | Make campaign improvement visible | Confidence and accountability | Repeatable client management |
| 5 | Asset factory | Produce low-cost assets fast | Better execution without client effort | Compounding reusable assets |
| 6 | Whiteboard/operator surface | Make work visible and manageable | Indirect: faster delivery | Operational scale beyond 1–2 clients |
| 7 | Delivery/approval | Send polished client packages safely | Professional experience | Policy-gated operations |
| 8 | Scale templates | Support multiple verticals/playbooks | Better fit per business | Faster setup and lower cost |

## 6. Detailed phase roadmap

## Phase 0 — Stabilize current foundation

### Goal

Lock in the backend foundation already built: task routing, formatter, markdown/PDF/manifest/zip package, Legacy handoff path.

### Why it matters for retention

Clients only stay if Atlas can repeatedly produce polished, reliable outputs. The current foundation is the packaging and provenance layer for everything else.

### Scope

- Review current diff.
- Ensure no accidental artifacts or credentials.
- Confirm tests pass.
- Merge or prepare PR.
- Keep current work clean before adding client product scope.

### Out of scope

- New campaign models.
- New UI.
- New provider delivery.
- Major refactors.

### Success criteria

- Formatter services are merged/clean.
- Legacy handoff uses generic formatter.
- PDF package verified.
- Tests/lint/check pass.

---

## Phase 1 — Atlas Growth Audit product

### Goal

Create the first client-facing product: a Spanish free audit plus 30-day action plan that feels valuable enough to earn permission to execute.

### Product name

Spanish client-facing candidates:

- `Diagnóstico Atlas: Plan de Clientes Nuevos en 30 Días`
- `Atlas Growth Audit + Plan de Acción de 30 Días`
- `Diagnóstico de Crecimiento Atlas`

### Client deliverables

Required:

1. Resumen ejecutivo.
2. Diagnóstico del negocio.
3. Oportunidades de crecimiento.
4. Perfil de cliente ideal.
5. Oferta inicial recomendada.
6. Canales recomendados.
7. Activos que Atlas puede producir.
8. Plan de acción de 30 días.
9. Quick wins de 7 días.
10. Propuesta de medición y comisión.

Optional but high-value:

- Sample WhatsApp script.
- Landing page outline.
- Ad copy examples.
- Prospect segment examples.

### Operator deliverables

- Intake summary.
- Missing-info list.
- Assumptions/caveats.
- Quality score.
- Recommended first campaign playbook.

### ForgeGraph implementation

Likely config/service package:

- `atlas_growth_audit_30_day_plan.v1`
- `format_profile:atlas.growth_audit_es_mx@1`

Likely backend artifacts:

- Intake snapshot.
- Audit deliverables.
- PDF/markdown/manifest/zip package.
- Quality gate results.

### Acceptance criteria

- Generates a Spanish package for Legacy.
- Package is specific, not generic.
- Includes commission/tracking proposal.
- Includes Atlas-owned execution path.
- Human operator would be comfortable showing it to a real friend/family client.

### Manual grading rubric

Grade 1–5:

- Specificity.
- Revenue clarity.
- Practicality.
- Offer quality.
- Measurement clarity.
- Asset usefulness.
- Professional Spanish.
- Trust.

Minimum to proceed:

- Average >= 4.
- No category below 3.

---

## Phase 2 — Campaign execution product

### Goal

Convert the audit recommendation into a real low-cost campaign that Atlas can execute with minimal client involvement.

### Anchor product

`Conversión Local IA`

Client-facing promise:

> Diseñamos y operamos un sistema simple para conseguir conversaciones, citas, cotizaciones o ventas medibles por WhatsApp y canales locales.

### Campaign deliverables

1. Campaign brief.
2. Offer sheet.
3. Funnel map.
4. Channel/playbook selection.
5. Trust asset plan.
6. WhatsApp/outreach scripts.
7. Follow-up sequence.
8. Tracking sheet.
9. Launch readiness score.
10. Scale/kill criteria.

### Core campaign playbooks

- WhatsApp + Meta click-to-WhatsApp.
- Google Business Profile + local SEO.
- Direct B2B outreach.
- Email/CRM reactivation.
- Referral/alliance loop.
- Google Search local.
- Marketplace growth when catalog exists.

### Product rules

- No meaningful media spend without a concrete offer.
- No campaign launch without tracking.
- No success-fee model without attribution definitions.
- Manual/direct tests before broad paid spend when possible.
- Client effort must be explicit and minimized.

### ForgeGraph implementation

Likely service package:

- `atlas_conversacion_local_ia.v1`

Likely deliverables:

- `campaign_brief`
- `offer_sheet`
- `funnel_map`
- `scripts_and_followups`
- `trust_asset_plan`
- `tracking_plan`
- `readiness_scorecard`

### Acceptance criteria

- Legacy can produce a B2B acquisition campaign package.
- Campaign has one target segment, one offer, one CTA, one primary channel.
- Campaign includes no-spend/direct test option.
- Campaign includes launch/kill/scale criteria.

---

## Phase 3 — Lead, sale, profit, and commission tracking

### Goal

Make the success-fee business model operational and dispute-resistant.

### Why this is critical

If Atlas charges commission, retention depends on trust in attribution. The product must show which leads Atlas sourced, what happened to them, what revenue/profit resulted, and what commission is due.

### Core concepts

- Prospect.
- Lead.
- Qualified lead.
- Appointment/cita.
- Quote/cotización.
- Closed sale.
- Revenue.
- Estimated direct cost.
- Estimated profit.
- Commission rate.
- Commission due.
- Attribution source.
- Dispute/adjustment notes.

### Client-facing outputs

- Simple lead summary.
- New business attributed to Atlas.
- Commission statement.
- Open opportunities.
- Follow-up needed.

### Operator outputs

- Lead tracker.
- Pipeline status.
- Missing follow-ups.
- Commission calculation.
- Attribution evidence.

### Implementation approach

First slice can avoid new models if needed:

- Use structured artifacts / AssetVersions for lead tracker CSV/JSON.
- Store campaign metadata on existing program/deliverable records.
- Only introduce DB models once fields stabilize.

Likely future models:

- `Campaign`
- `LeadRecord`
- `CommissionRecord`

But avoid premature DB design until after Legacy/pilot validation.

### Acceptance criteria

- Every campaign has an attribution method.
- Every lead has a source and status.
- Commission due can be calculated from explicit assumptions.
- Client report separates leads, qualified leads, closed sales, and commission.

---

## Phase 4 — Weekly campaign operating cadence

### Goal

Create the retention rhythm: every week, Atlas shows what happened, what was learned, and what changes next.

### Client-facing weekly report

Spanish report sections:

1. Qué hicimos esta semana.
2. Qué resultados vimos.
3. Qué aprendimos.
4. Dónde se atoró el funnel.
5. Qué cambiaremos la próxima semana.
6. Leads/sales/commission summary.
7. Qué necesitamos aprobar o confirmar.

### Internal weekly report

- Channel metrics.
- Funnel conversion by stage.
- Lead quality notes.
- Follow-up SLA.
- Open blockers.
- Kill/scale recommendation.
- Next experiments.

### Product logic

Atlas should diagnose funnel failures:

- No replies: segment/message/channel problem.
- Replies but bad fit: offer/targeting problem.
- Qualified leads but no sales: sales/trust/pricing problem.
- Sales but low profit: economics problem.
- Good sales: scale.

### Acceptance criteria

- Weekly report can be generated from campaign artifacts.
- Report is readable by non-marketing owner.
- Report includes specific next action.
- Report updates trust and retention even if results are early.

---

## Phase 5 — Asset factory

### Goal

Make Atlas able to create the minimum useful assets for each campaign quickly and cheaply.

### Asset types

- Landing page.
- One-page offer PDF.
- Mini catalog.
- WhatsApp scripts.
- Email scripts.
- Instagram DM scripts.
- Ad copy variants.
- Static creatives.
- Short video scripts/storyboards.
- Google Business Profile copy.
- Review request message.
- Referral message.

### Product principle

Do not build assets for their own sake. Build only the assets needed to make the current campaign credible and measurable.

### ForgeGraph implementation

- Add asset-generation deliverable templates.
- Add format profiles for client-facing vs operator-facing assets.
- Add quality gates for Spanish copy, CTA clarity, claims, and compliance.
- Persist generated assets as AssetVersions.

### Acceptance criteria

- Given a campaign brief, Atlas can produce the first asset pack.
- Assets are tied to campaign and offer.
- Assets can be reviewed/approved independently.
- Assets include usage instructions.

---

## Phase 6 — Operator whiteboard and workflow surface

### Goal

Make Atlas operations visible and manageable without making the whiteboard the source of truth.

### Whiteboard should show

Columns:

- Intake.
- Audit.
- Campaign Design.
- Asset Production.
- Ready to Launch.
- Live.
- Follow-up Needed.
- Review/Report.
- Scale/Kill.
- Closed/Commission.

Cards:

- Program stage tasks.
- Deliverables.
- Assets.
- Leads requiring action.
- Approvals.
- Blockers.

### Source of truth

Backend remains authoritative:

- CompanyProgram.
- ProgramStageState.
- TaskRoutingRecord.
- ServiceDeliverable.
- AssetVersion.
- Campaign/lead artifacts or future models.

### Acceptance criteria

- Operator can see what each client needs next.
- Work is resumable.
- Blockers are explicit.
- Artifacts are attached to cards/tasks.
- No durable state lives only in frontend board state.

---

## Phase 7 — Approval and delivery

### Goal

Make client communication professional and safe.

### Delivery artifacts

- PDF report.
- Markdown/source.
- Manifest/provenance.
- Zip package.
- Email handoff artifact.
- Approval record.
- Delivery record.

### Approval states

- Draft.
- Needs revision.
- Approved.
- Sent.
- Failed.

### Product rules

- Do not send client-facing package unless approved.
- Do not mark sent unless provider confirms acceptance.
- Keep delivery evidence.
- Do not expose internal provenance unless useful.

### Acceptance criteria

- Operator can approve package.
- Client package can be sent through provider.
- Delivery status is recorded.
- Failed delivery is honest and recoverable.

---

## Phase 8 — Vertical templates and scale

### Goal

Reduce setup time and improve quality for repeated business types.

### Initial vertical templates

- Bars/restaurants.
- Cleaning/home services.
- Local professional services.
- Specialty retail/catalog.
- Legacy-style B2B product sales.

### Each template defines

- Intake questions.
- Common offers.
- Default channels.
- Trust assets.
- Scripts.
- Tracking metrics.
- Commission assumptions.
- Compliance caveats.
- Quality gates.

### Acceptance criteria

- New client setup time decreases.
- Output remains specific, not generic.
- Operators can override assumptions.
- Performance benchmarks accumulate by vertical.

## 7. Multi-PR implementation roadmap

| Order | Branch / PR | Objective | Boundary | Dependencies | Success criteria |
|---:|---|---|---|---|---|
| 0 | `merge/formatter-foundation` | Stabilize existing formatter/PDF/Legacy handoff work | Cleanup only | Current work | Tests pass, no secrets/artifacts, PR clean |
| 1 | `docs/atlas-product-roadmap` | Commit product specs and roadmap | Docs only | PR 0 optional | Growth audit, low-cost playbook, retention roadmap in repo |
| 2 | `feat/atlas-growth-audit-profile` | Add Spanish audit service/profile config | Backend config + tests | PR 0 | Legacy sample audit generated and graded |
| 3 | `feat/client-handoff-service` | Move script orchestration into generic handoff service | Backend service, no UI | PR 0 | Legacy and generic/fixture handoffs use same service |
| 4 | `feat/conversion-local-campaign-package` | Add campaign brief/offer/funnel/readiness deliverables | Backend config/services + tests | PR 2/3 | Legacy campaign package generated |
| 5 | `feat/lead-tracker-artifacts` | Add artifact-backed lead/revenue/commission tracking | Backend artifacts first | PR 4 | Lead tracker + commission statement generated |
| 6 | `feat/weekly-campaign-report` | Generate weekly client/operator reports | Backend formatter/reporting | PR 5 | Weekly report diagnoses funnel and next actions |
| 7 | `feat/asset-factory-v1` | Generate campaign assets from brief | Backend deliverables/assets | PR 4 | Scripts/landing outline/offer sheet created |
| 8 | `feat/approval-delivery-boundary` | Add approval state and email handoff artifact | Backend policy/service | PR 3/6 | Send blocked until approved; email artifact persisted |
| 9 | `feat/operator-whiteboard-campaigns` | Surface campaign state in whiteboard/API | Backend API + frontend if needed | PR 4/5 | Operator sees client/campaign/tasks/artifacts/leads |
| 10 | `feat/vertical-templates-v1` | Add repeatable vertical templates | Config + tests | PR 2/4/7 | Bars/restaurants, cleaning, Legacy/B2B templates work |

## 8. PR details

### PR 0 — Stabilize formatter foundation

**Objective:** Finish current foundation before adding product scope.

**Layer:** Platform/shared.

**Scope:**

- Review current diff.
- Verify formatter tests.
- Verify Legacy handoff PDF output.
- Remove generated outputs from git if any.
- Prepare clean PR.

**Out of scope:**

- New service packages.
- New campaign code.

**Test plan:**

- Formatter unit tests.
- Legacy pipeline tests.
- Ruff.
- Django check.

**Success criteria:**

- Clean PR.
- No accidental secrets.
- Formatter/PDF/handoff verified.

### PR 1 — Docs/product roadmap

**Objective:** Commit product strategy artifacts so implementation follows client/product needs.

**Layer:** Product-specific docs.

**Scope:**

- `docs/atlas/services/atlas-growth-audit-sprint-v1.md`
- `docs/atlas/services/atlas-low-cost-acquisition-playbook-v1.md`
- `docs/atlas/services/atlas-client-retention-product-roadmap-v1.md`

**Out of scope:**

- Runtime behavior.

**Success criteria:**

- Docs are clear enough for Codex/subagents to implement from.

### PR 2 — Atlas Growth Audit profile

**Objective:** Make ForgeGraph produce the Spanish Growth Audit package.

**Layer:** Product-specific config on shared formatter.

**Scope:**

- Add format profile `atlas.growth_audit_es_mx@1`.
- Add service/package config `atlas_growth_audit_30_day_plan.v1`.
- Add quality gates for Spanish/client-ready audit sections.
- Add Legacy sample fixture.

**Out of scope:**

- Live campaign execution.
- Leads/commission tracking beyond proposal text.
- UI.

**Test plan:**

- Profile registry tests.
- Formatting tests.
- Quality gate tests.
- Legacy sample generation test.

**Manual verification:**

- Generate Legacy Spanish PDF.
- Grade with rubric.

**Success criteria:**

- Spanish package includes all required sections.
- Commission/tracking proposal present.
- Output feels client-ready enough for manual review.

### PR 3 — Generic client handoff service

**Objective:** Replace script-specific handoff orchestration with reusable backend service.

**Layer:** Platform/shared.

**Scope:**

- Add `application/services/client_handoff.py`.
- Script becomes thin wrapper.
- Handoff service selects deliverables, calls formatter, persists/exports package.

**Out of scope:**

- Provider email send.
- UI.
- New DB models unless unavoidable.

**Test plan:**

- Service tests with Legacy and generic fixture.
- Existing script smoke test.

**Success criteria:**

- Legacy handoff still works.
- New audit/campaign packages can reuse same service.

### PR 4 — Conversión Local IA campaign package

**Objective:** Convert an approved audit into a launchable campaign plan.

**Layer:** Product-specific package + shared deliverable generation.

**Scope:**

- Campaign brief.
- Offer sheet.
- Funnel map.
- Channel/playbook selection.
- Scripts/follow-up sequence.
- Launch readiness score.
- Kill/scale criteria.

**Out of scope:**

- Actual ad platform integration.
- Automated WhatsApp sending.
- Persistent lead models.

**Test plan:**

- Legacy campaign package fixture.
- Quality gate tests for campaign readiness.

**Success criteria:**

- Legacy B2B campaign plan has clear segment, offer, CTA, channel, and follow-up.
- Readiness score blocks incomplete campaigns.

### PR 5 — Lead/revenue/commission tracker artifacts

**Objective:** Make success-fee tracking real enough for pilots.

**Layer:** Shared artifacts first; model later.

**Scope:**

- Define lead tracker schema.
- Define commission statement schema.
- Generate CSV/JSON/Markdown artifacts.
- Attach to campaign package.

**Out of scope:**

- Full CRM replacement.
- Automated provider ingestion.
- Accounting integration.

**Test plan:**

- Schema tests.
- Commission calculation tests.
- Report rendering tests.

**Success criteria:**

- Can record lead -> sale -> profit -> commission.
- Attribution assumptions explicit.

### PR 6 — Weekly campaign report

**Objective:** Create the retention communication artifact.

**Layer:** Product-specific reporting on shared formatter.

**Scope:**

- Weekly report profile.
- Funnel diagnosis logic.
- Next-action recommendation.
- Client and operator variants.

**Out of scope:**

- Live dashboard.
- Complex analytics integrations.

**Test plan:**

- Synthetic campaign data tests.
- Funnel diagnosis tests.
- Spanish formatting tests.

**Success criteria:**

- Report says what happened, what broke, what changes next.

### PR 7 — Asset factory v1

**Objective:** Produce useful campaign assets quickly.

**Layer:** Product-specific generation templates + shared assets.

**Scope:**

- Landing page outline.
- Offer one-pager.
- WhatsApp scripts.
- Email/DM scripts.
- Ad copy variants.
- Review/referral requests.

**Out of scope:**

- Full website builder.
- Automated ad publishing.
- Arbitrary design editor.

**Test plan:**

- Asset generation tests from campaign brief.
- Quality gates for CTA, Spanish, claims, and placeholders.

**Success criteria:**

- Legacy campaign asset pack is usable with minimal edits.

### PR 8 — Approval and delivery boundary

**Objective:** Make package delivery safe and professional.

**Layer:** Shared policy/service.

**Scope:**

- Approval status.
- Email handoff artifact.
- Delivery provider boundary.
- Send guardrails.

**Out of scope:**

- Complex client portal.
- Multi-provider UI.

**Test plan:**

- Sending blocked until approved.
- Provider acceptance records sent status.
- Failure does not mark sent.

**Success criteria:**

- Operator can safely send approved packages.

### PR 9 — Operator whiteboard campaign surface

**Objective:** Make operations manageable as clients grow.

**Layer:** Backend API + UI as needed.

**Scope:**

- Campaign/task/card snapshot.
- Lead follow-up cards.
- Approval/blocker cards.
- Artifact links.

**Out of scope:**

- Frontend as source of truth.
- Drag/drop mutations unless backend-owned.

**Test plan:**

- API snapshot tests.
- UI smoke tests if frontend touched.

**Success criteria:**

- Operator can see what needs action today.

### PR 10 — Vertical templates v1

**Objective:** Speed setup and improve quality by vertical.

**Layer:** Product-specific config.

**Scope:**

- Bars/restaurants template.
- Cleaning/home services template.
- Legacy/B2B product sales template.
- Common offers/scripts/channels/gates.

**Out of scope:**

- Dozens of verticals.
- Hardcoded renderer logic.

**Test plan:**

- Each template generates audit + campaign package.
- Generic services remain domain-agnostic.

**Success criteria:**

- New similar client can be configured faster without generic output.

## 9. Implementation priorities

### Immediate next work

1. Clean current formatter/PDF work.
2. Commit product docs.
3. Generate a Legacy Spanish Growth Audit sample.
4. Manually grade it.
5. Build `Conversión Local IA` campaign package from the audit.

### Do not prioritize yet

- Fancy frontend.
- Full CRM build.
- Automated ad publishing.
- TikTok/marketplace integrations.
- Multi-tenant client portal.
- Complex financial/accounting system.

## 10. Key risks

### Risk: product becomes system-first again

Mitigation:

- Every PR must name the client-facing deliverable or operator retention loop it improves.

### Risk: commission attribution disputes

Mitigation:

- Define attribution before launch.
- Track source/status/profit/commission from day one.

### Risk: clients do not participate

Mitigation:

- Product assumes low client involvement.
- Atlas-owned execution paths are required.

### Risk: pretty reports but no revenue

Mitigation:

- Campaign scorecard and weekly reports focus on leads/sales/profit.

### Risk: too much custom work per client

Mitigation:

- Vertical templates and asset factory after first pilots.

## 11. Product success metrics

### Client retention metrics

- Clients with active campaign after audit.
- Week-4 retention.
- Month-2 retention.
- Month-3 retention.
- Number of clients with attributed leads/sales.
- Commission collected.
- Paid service upsells.

### Operational metrics

- Time from intake to audit package.
- Time from audit approval to campaign launch.
- Time from campaign launch to first signal.
- Number of manual operator hours per client/week.
- Number of generated assets reused/adapted.

### Campaign metrics

- Conversations.
- Qualified leads.
- Quote/cita requests.
- Closed sales.
- Revenue/profit attributed.
- Commission due/collected.
- CAC or cost per qualified lead.

## 12. Product mantra

Atlas should repeatedly ask:

> What is the cheapest next action that can produce measurable customer demand for this business?

And:

> What proof can we show the owner this week that Atlas is creating value?
