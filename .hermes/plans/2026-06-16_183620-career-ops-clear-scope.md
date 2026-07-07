# CareerOps ForgeGraph Clear Scope

**Primary business goal:** get at least one interview in the next week.

That means we should not try to clone the whole upstream repo first. We should build the smallest ForgeGraph-owned career operating loop that lets Mike process real job URLs quickly, produce truthful high-quality application packets, and manually submit only approved packets.

**New operating assumption:** ForgeGraph will have backend-owned cron/automation jobs. CareerOps should be designed so a daily discovery automation can run every day at **10:00 AM**, collect fresh opportunities, skip companies/jobs already applied to within a configurable cooldown window, and leave reviewed options ready for Mike when he wakes up. The default cooldown is **30 days**. The automation still cannot submit applications; it can only discover, evaluate, draft, and queue approval-ready packets.

**Base CV requirement:** Candidate onboarding must persist a canonical `cv_source` / base CV before any tailoring happens. Every tailored CV must cite this base CV plus proof-point source refs, and no generated resume can become live-ready without a base CV version.

**Native ForgeGraph contract:** See `.hermes/plans/2026-06-16_190000-career-ops-native-forgegraph-contract.md`. CareerOps features should map to `Run`/execution, `TaskRecord`, `DecisionRecord`, `MemoryObservation`, `CostAggregate`, `AssetVersion`, `ServiceDeliverable`, `CompanySignal`, `CompanyOpportunity`, and `StateProjection` instead of recreating Career-Ops as scripts plus local files.

---

## Scope decision

### Week-one MVP: build this first

The first implementation should support this workflow:

```text
candidate profile + CV + proof points
  -> paste one job URL
  -> fetch/normalize posting
  -> liveness + legitimacy check
  -> A-G evaluation
  -> tracker entry
  -> truthful ATS resume draft/PDF + cover letter draft
  -> quality gates
  -> candidate approval
  -> manual submission + status tracking
  -> story bank + interview prep update
```

**Week-one throughput target:** prepare and manually submit **8-15 high-quality applications** from **15-30 screened job URLs**, with every packet passing source-truth and PDF/ATS checks before use.

**Explicit non-goal for week one:** 45+ portal scanner coverage, TUI polish, full batch-worker orchestration, or auto-submit. Those are product-growth features; they do not help as much as a reliable URL-to-packet loop for getting one interview next week.

---

## Feature-by-feature scope matrix

| Upstream feature | Do we want it? | Week-one scope | What ForgeGraph can use now | What we need to add | Priority |
| --- | --- | --- | --- | --- | --- |
| **Auto-Pipeline** — paste URL, full evaluation + PDF + tracker entry | Yes. This is the core. | **Build now**, but as URL -> evaluation -> tracker -> draft packet -> quality gate -> approval. Manual submit only. | `Graph`, `CompanySignal`, `CompanyOpportunity`, `ServiceEngagement`, `ServiceDeliverable`, `AssetVersion`, `StateProjection`, company blueprint/pack services, generic renderers. | `career_ops_url_pipeline.py`, posting fetch/normalize, job URL idempotency, A-G evaluator, packet assembler, live-readiness command. | P0 |
| **6-Block Evaluation + Block G** | Yes. This is mandatory. | **Build now.** A-F plus G legitimacy. Keep output deterministic/schema-first; LLM can fill prose later. | Deliverables/assets can store reports; `runtime_web_tools.fetch_public_web_content` can fetch public pages; existing signal/opportunity models can hold metadata. | `career_ops_evaluation.py` with schema, scoring rubric, source refs, comp evidence field, legitimacy/liveness gate. | P0 |
| **Interview Story Bank** | Yes, but lightweight first. | Create/maintain 5-10 master STAR+Reflection stories from CV/proof points and each evaluation. Generate company prep after packet/eval. | `Asset` / `AssetVersion` and `StateProjection` can store story bank. | `career_ops_story_bank.py` or include in state/evaluation service; source-backed story extraction tests. | P1 |
| **Negotiation Scripts** | Yes, later. | Defer until interviews/offers. Include one template deliverable if an interview is scheduled. | Deliverables/assets can store scripts. | `career_ops_negotiation.py` later; comp/geography evidence integration. | P3 |
| **ATS PDF Generation** | Yes. | Build basic, safe ATS resume PDF first. Do **not** block on Space Grotesk + DM Sans visual parity. Source-backed content + extractable PDF matters more. | Generic deliverable renderer already creates PDFs; formatting/profile system exists. | CareerOps resume HTML/PDF renderer or profile, PDF text extraction/checks, placeholder checks, ATS section tests, optional Playwright/Chromium renderer later. | P0/P1 |
| **Cover Letter Generator** | Yes. | Auto-draft on evaluation, candidate-facing only after quality gate. Interactive four-angle prompt can be CLI/API fields later. PDF on demand after draft approval. | Deliverables/assets and generic renderer can persist draft/PDF. | `career_ops_cover_letter.py` or packet assembler support; angle metadata, draft approval state, quality checks. | P1 |
| **Portal Scanner** | Eventually, but not full first. | Week one: single URL intake + maybe small manual shortlist/search helper. No 45-provider clone yet. | `runtime_web_tools` can fetch public URLs; `CompanySignal` unique external key supports dedupe. | provider interface, URL parser, liveness classifier, adapters for Ashby/Greenhouse/Lever only after fake-provider tests. | P2 |
| **Batch Processing** | Yes, but controlled. | Week one: sequential or small bounded batch over manually supplied URLs. No headless `claude -p`/`opencode run` worker farm. | Run records, management commands, backend services can process batches. | `career_ops_batch.py`, idempotent per-URL status, concurrency limits, fail-closed packet quality aggregation. | P2 |
| **Dashboard TUI** | Nice, not necessary. | Defer. Use JSON read model, management command output, or existing ForgeGraph UI/API first. | Pipeline read model can derive status from DB. | Optional TUI later, likely outside backend-critical path. | P4 |
| **Human-in-the-Loop** | Yes. Non-negotiable. | Build now. Every external action requires exact packet-version approval. | Existing deliverable status/metadata and approval-style patterns; quality gates. | `career_ops_approval.py`, `career_ops_side_effects.py`, exact `asset_version_id`/packet version approval, live-send disabled by default. | P0 |
| **Pipeline Integrity** | Yes. | Build now for URL dedupe, status normalization, stale follow-ups, packet readiness, quality blockers. | `CompanySignal` unique source/external key, `CompanyOpportunity`, `StateProjection`, deliverables. | `career_ops_pipeline.py`, status map, duplicate warnings, health report. | P0/P1 |

---

## What ForgeGraph can support with current primitives

Based on the current repo shape, ForgeGraph already has the generic primitives needed for the MVP:

- **Company/workspace:** `Graph` and company blueprint services.
- **Operating model:** operating-model pack loader/compiler and pack installation pattern.
- **Programs/stages:** `CompanyProgram` and `ProgramStageState`.
- **Job leads/tracker:** `CompanySignal` and `CompanyOpportunity`, including a uniqueness constraint on `(company, source, external_key)` for dedupe.
- **Candidate/application state:** `StateProjection`.
- **CVs/reports/packets:** `Asset`, `AssetVersion`, `ServiceEngagement`, and `ServiceDeliverable`.
- **Formatting/PDF baseline:** generic deliverable format renderers and profiles exist, including PDF output, manifest, and zip packaging.
- **Quality-gate precedent:** existing agency deliverable quality gates show the pattern for customer-safe deliverables.
- **Web fetch baseline:** `runtime_web_tools.fetch_public_web_content` can safely fetch public text/HTML with URL validation and limits.

So the first slice does **not** need new core tables. It should be a CareerOps pack + CareerOps services over existing tables.

---

## What ForgeGraph needs added for this product

### Must add before real use

1. `career_ops.v1` operating-model pack.
2. CareerOps graph contract tests so stages/departments/deliverables do not drift.
3. URL intake + job posting normalizer.
4. Liveness/legitimacy gate.
5. A-G evaluation service with source refs.
6. Application tracker/read model over `CompanyOpportunity`.
7. Application packet assembler: evaluation report, tailored resume, cover letter, answers.
8. CareerOps-specific quality gates:
   - claim-source validation,
   - no-invention checks,
   - PDF/ATS checks,
   - internal leakage checks,
   - employer/opportunity isolation,
   - exact-version approval checks.
9. Side-effect guard: live external sends disabled by default.
10. Management commands for seed, run URL pipeline, and check live readiness.

### Should add shortly after MVP

1. HTML + Playwright resume/cover-letter renderer with CareerOps style profile.
2. Small provider adapter set for Ashby, Greenhouse, Lever pages.
3. Bounded batch processing over URL lists.
4. Story bank update service and interview prep generation.
5. Follow-up reminders/status normalization.

### Defer until after week-one interview push

1. 45+ preconfigured portal scanner list.
2. Dashboard TUI.
3. Full parallel CLI-worker orchestration.
4. Advanced negotiation scripts unless interview/offer appears.
5. Visual polish parity with upstream fonts/design beyond safe, parseable PDFs.

---

## Week-one operating plan

### Day 1: Foundation

- Implement `career_ops.v1` pack and graph contract.
- Seed a CareerOps company with candidate profile, CV, proof points, and one fake opportunity.
- Verify pack compile + seed tests.

### Day 2: URL-to-evaluation

- Add paste-URL intake, posting fetch/normalize, liveness/G-legitimacy check, and A-G evaluation.
- Verify with 3-5 real job URLs in dry-run mode.

### Day 3: Packet + quality gates

- Generate evaluation report, ATS resume draft/PDF, cover letter draft, and application answers.
- Add claim-source, placeholder, internal leakage, PDF/ATS, and employer-isolation tests.
- Require `check_career_ops_live_readiness` before manual submission.

### Day 4-5: Application sprint

- Process 15-30 URLs.
- Manually approve and submit only packets that pass quality gates.
- Track submitted/skipped/follow-up statuses in ForgeGraph.

### Day 6-7: Interview prep + iteration

- Generate story bank and company-specific interview prep for high-signal opportunities.
- Review pipeline health: which roles got strongest fit, which packets blocked, what to adjust.
- Follow up where appropriate.

---

## Acceptance criteria for scope lock

We can say scope is clear when all of these are agreed:

- [ ] Week-one goal is one interview, not full upstream feature parity.
- [ ] P0 scope is URL-to-evaluation-to-quality-gated-packet-to-manual-submit.
- [ ] Human approval and side-effect blocking are mandatory.
- [ ] Full portal scanner, TUI, and worker farm are deferred.
- [ ] ATS/PDF output must be safe and parseable before pretty.
- [ ] Every generated candidate-facing claim must be source-backed.
- [ ] First implementation uses existing ForgeGraph primitives before adding new core models.

---

## Recommended final scope statement

Build **CareerOps MVP v0** in ForgeGraph:

> A backend-owned CareerOps company that takes a job URL, creates a deduped tracker entry, runs liveness + A-G evaluation, generates source-backed resume/cover-letter/application-packet drafts, blocks unsafe packets through quality gates, requires exact candidate approval, and supports manual submission/status tracking — with enough throughput to submit 8-15 high-quality applications this week.

Everything else is a later expansion unless it directly increases this week's interview probability.
