# Atlas Profit Agency — final Digital Marketing Pro review

Date: 2026-06-03 19:43
Source reviewed: `https://github.com/indranilbanerjee/digital-marketing-pro`, local clone at `C:/Users/mathi/AppData/Local/Temp/forgegraph-research/digital-marketing-pro`.

## Lens
Atlas should not just generate marketing tasks. Atlas should operate like a profit-seeking agency: acquire clients, package work, onboard safely, execute with quality gates, prove outcomes, retain/expand accounts, and protect agency/client data boundaries.

## High-value borrowable capabilities

### 1. Client acquisition + sales enablement layer
Digital Marketing Pro includes proposal, ROI, sales enablement, competitor analysis, pricing/positioning, and brand setup concepts. Atlas currently has service catalog / engagement / deliverable primitives, but needs a pre-engagement commercial funnel.

Needed Atlas feats:
- Prospect/opportunity object: lead source, ICP fit, pain, budget, authority, timing, expected retainer, close probability.
- Discovery brief generator: intake notes -> pain map -> service recommendation.
- Proposal / SOW / pricing packet generator from service catalog items.
- ROI calculator embedded in proposal deliverables.
- Internal sales enablement prompts: objection handling, case study matching, pricing defense, next-step email.
- Win/loss learning: store why deals close or churn, feeding future positioning.

Priority: High for becoming a real agency.

### 2. Agency operating cockpit / portfolio health
DMP has a multi-client agency dashboard with client health score, traffic lights, lowest dimension, monthly spend, ROAS, active campaigns, next deliverable, account manager, and reporting cadence. Atlas needs this as the owner/operator view.

Needed Atlas feats:
- Portfolio dashboard across companies/accounts.
- Client health score: campaign activity, budget pacing, KPI attainment, content pipeline, engagement health.
- Profitability health: retainer value, estimated cost-to-serve, gross margin, overdue deliverables, unpaid approvals, scope creep.
- Churn risk: engagement decline, missed KPI windows, approval latency, unanswered client messages, repeated connector gaps.
- Expansion signals: KPI outperformance, unused channel opportunity, cross-sell prompts.
- Weekly account review prompt that produces action plan per amber/red client.

Priority: High.

### 3. Client onboarding as a productized workflow
DMP’s onboarding flow separates brand profile, credential profile, CRM sync, MCP validation, SOP assignment, team assignment, reporting cadence, campaign audit, and baseline metrics. Atlas already can create companies/departments/operating packs, but onboarding should become a first-class client journey.

Needed Atlas feats:
- Onboarding checklist object with owner, due date, status, blockers.
- Brand profile schema: voice, ICP, competitors, target markets, regulated industry, approved claims, channel strategy.
- Credential/connectors checklist per client, with isolation boundaries.
- Baseline campaign audit as the first mandatory deliverable before proposing new work.
- Reporting cadence and delivery channel setup.
- Team assignment and SOP package selection.

Priority: High.

### 4. Connector readiness and credential isolation
DMP is strict about connector validation and credential isolation per brand. Atlas must be equally strict before real spend/sends happen.

Needed Atlas feats:
- Per-client credential profile / connector health model.
- Connector status classes: connected, missing, expired, permission-limited, stale-data, dry-run-only, real-execution-enabled.
- Fast connector probe endpoint and evidence record.
- Hard data boundary: never use one client’s credentials/data in another client’s deliverables.
- Audit trail for profile switches, credential updates, validation runs, execution attempts.

Priority: High before any live agency operations.

### 5. Launch readiness gates and resumable execution
DMP’s launch-campaign skill is valuable because it refuses to launch without prerequisites, shows dry-run preview, executes in dependency order, checkpoints after every action, and requires human intervention on failure.

Needed Atlas feats:
- Campaign launch object distinct from campaign plan.
- Dry-run preview artifact: every platform action, cost/spend exposure, connector requirement, tracking dependency.
- Blocker gates: approved plan, approved assets, connector health, landing page 200, conversion events test-fired, UTM coverage, compliance checks, C2PA if needed.
- Resumable checkpointed launch state.
- No blind auto-retry for spend/sending actions.
- Final launch receipt deliverable.

Priority: High, especially if Atlas will activate paid/email/social channels.

### 6. QA, validation, compliance, and claim provenance
DMP has structural validators, check/eval flows, hallucination/claim verification, compliance rules, C2PA signing, spam checks, readability checks, and output validation. Atlas deliverables need not just generation; they need review gates.

Needed Atlas feats:
- Deliverable QA schema per deliverable type: required sections, placeholders, CTA consistency, source/citation needs, compliance flags, word/format rules.
- Approval risk classification: internal-only, client-review, legal-review, launch-blocker.
- Claim registry: claim text, evidence/source, jurisdiction, expiry/review date.
- Compliance posture in client profile: jurisdictions, regulated sector, disclaimers, consent requirements.
- AI asset provenance/C2PA requirement marker for EU-targeted AI assets.
- Client-safe export filter + confidential/internal appendix separation.

Priority: High.

### 7. Reporting cadence + proof of value
DMP defines weekly pulse, monthly review, QBR, annual planning; report delivery checklists; concrete KPI/anomaly/action item requirements. Atlas’s current deliverables should expand into recurring value proof.

Needed Atlas feats:
- Recurring report schedule per engagement.
- Weekly Pulse deliverable: KPIs, wins, flags, next actions.
- Monthly Review deck/document: channel breakdown, budget reconciliation, next-month plan.
- QBR package: strategic review, results vs goals, learnings, budget/channel recommendations.
- Performance narrative generator: numbers -> business explanation -> decision.
- Report delivery status and client acknowledgement.

Priority: High for retention.

### 8. Commercial agency metrics
DMP has some ROI and revenue tools; Atlas should add true agency P&L mechanics.

Needed Atlas feats:
- Retainer/package model: included deliverables, SLA, revision limits, reporting cadence.
- Work estimate / actuals / margin fields per deliverable and engagement.
- Scope creep detector: requested work not in package, extra revisions, off-cadence requests.
- Expansion recommendation engine: when to upsell SEO, CRM lifecycle, paid media, analytics, creative refresh, compliance audit.
- Revenue forecast: pipeline + active retainers + churn risk + expansion opportunities.

Priority: Medium-high; essential for profit agency, but can follow operational foundation.

### 9. Knowledge memory and cross-client intelligence with guardrails
DMP allows anonymized benchmarks and shared learnings only with consent and aggregation thresholds. Atlas should turn cross-client learning into a competitive moat while preserving boundaries.

Needed Atlas feats:
- Insight object: client-specific vs portfolio-anonymized, consent scope, source evidence.
- Benchmark generation only with minimum client count / opt-in rules.
- Safe reusable playbooks from wins/losses without exposing client data.
- Agency SOP versioning and quarterly review.

Priority: Medium.

### 10. Prompt / skill catalog as product primitives
DMP’s most useful prompts are not individual copywriting tricks; they are operating workflows: brand setup, campaign audit, campaign plan, launch campaign, performance check, validate output, status, output-folder. Atlas should represent these as reusable playbook templates and agent briefs.

Needed Atlas prompts/playbooks:
- `agency.discovery_to_proposal`
- `agency.client_onboarding`
- `agency.campaign_audit`
- `agency.campaign_plan`
- `agency.launch_readiness_review`
- `agency.launch_execution_preview`
- `agency.weekly_pulse`
- `agency.monthly_review`
- `agency.qbr`
- `agency.deliverable_qa`
- `agency.churn_risk_review`
- `agency.expansion_opportunity_review`
- `agency.scope_creep_review`
- `agency.connector_gap_explainer`

Priority: High, because they can power UI workflows and backend deliverable assembly.

## Recommended Atlas roadmap

### Phase A — Profit agency foundation
1. Client onboarding checklist + brand profile + connector readiness.
2. Portfolio/account health dashboard.
3. Proposal/SOW/ROI packet generation.
4. Baseline audit before campaign recommendations.

### Phase B — Execution safety and proof
1. Launch readiness gates and launch receipt.
2. Deliverable QA schemas + claim provenance.
3. Recurring weekly/monthly/QBR report cadence.
4. Client approval/delivery lifecycle.

### Phase C — Profit optimization
1. Margin/scope/SLA tracking.
2. Churn and expansion signals.
3. Cross-client benchmark engine with consent/aggregation guardrails.
4. SOP/playbook versioning and team capacity.

## Do not over-copy from DMP
- Do not model Atlas as local dotfolder files; Atlas should use tenant-scoped backend models and audit logs.
- Do not make every command a one-off skill; use typed playbook templates tied to engagements/deliverables.
- Do not block all work on missing connectors; degrade gracefully in audits and planning, but hard-block launch/spend/send actions.
- Do not expose internal agency reasoning in client deliverables; always split internal notes vs client-facing artifacts.

## Immediate next implementation candidates
1. `ClientAccountHealthSnapshot` service + API: aggregates deliverable status, approval latency, connector gaps, report recency, campaign activity, KPI state, and margin placeholders.
2. `AgencyPlaybookTemplate` catalog seeded with DMP-inspired prompts above.
3. `ClientOnboardingChecklist` assembled when `digital_marketing_pro.v1` pack installs.
4. `DeliverableQualityGate` service that validates Atlas deliverables for placeholders, required sections, evidence, client-safe language, and compliance flags.
5. `CampaignLaunchReadiness` dry-run endpoint: uses current whiteboard/deployment state and connector policy to produce blocker/warning/action list before any live execution.
