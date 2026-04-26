export type ConsultingDriver =
  | "user_mix_quality"
  | "usability_regression"
  | "pricing_segmentation_shift"
  | "billing_complexity"
  | "external_competition"
  | "activation_friction"
  | "workflow_misalignment"
  | "discount_policy_drift"
  | "support_capacity"
  | "feature_positioning_gap";

export type ConsultingCaseDefinition = {
  case_id: string;
  problem_brief: string;
  evidence_pack: {
    case_type: "growth" | "product" | "revenue" | "support" | "retention";
    company: {
      sector: string;
      product: string;
      customers: string;
      business_model: string;
    };
    recent_changes: string[];
    observed_signals: string[];
    conflicting_signals: string[];
    distractors: string[];
    constraints: string[];
  };
  hidden_benchmark: {
    primary_driver: ConsultingDriver;
    acceptable_drivers: ConsultingDriver[];
    wrong_paths: ConsultingDriver[];
    expected_actions: string[];
  };
};

export type ConsultingExecutionInput = {
  problem: string;
  context: {
    case_id: string;
    case_type: ConsultingCaseDefinition["evidence_pack"]["case_type"];
    product: string;
    customers: string;
    sector: string;
    business_model: string;
    evidence_pack: ConsultingCaseDefinition["evidence_pack"];
  };
};

export const CONSULTING_CASE_PACK_V2: ConsultingCaseDefinition[] = [
  {
    case_id: "growth_high_acquisition_low_retention",
    problem_brief:
      "A PLG collaboration SaaS doubled new-user acquisition in 10 weeks, but paid conversion and 90-day retention fell enough that net revenue growth slowed despite record signups.",
    evidence_pack: {
      case_type: "growth",
      company: {
        sector: "Collaboration SaaS",
        product: "Collaborative planning workspace",
        customers: "SMB and mid-market teams",
        business_model: "Product-led subscription",
      },
      recent_changes: [
        "Growth added creator partnerships, referrals, and template marketplaces.",
        "Onboarding and pricing pages were mostly unchanged.",
        "Sales-assisted expansion still comes from higher-intent product-qualified leads.",
      ],
      observed_signals: [
        "Creator and referral cohorts convert to paid well below the historical baseline.",
        "Legacy organic and invite cohorts retain near prior benchmarks.",
        "Many new accounts create one board, invite no teammates, and go inactive within two weeks.",
        "Accounts that reach multi-user collaboration still report stable satisfaction.",
      ],
      conflicting_signals: [
        "Overall activation dipped only modestly, which makes onboarding look plausible.",
        "Some referral cohorts show strong week-one engagement before collapsing later.",
      ],
      distractors: [
        "A competitor ran a brand campaign in the same quarter.",
        "A minor editor visual refresh shipped before the spike.",
      ],
      constraints: [
        "Leadership must decide whether to keep scaling the new channels.",
        "The diagnosis must separate user quality from generic onboarding concerns.",
      ],
    },
    hidden_benchmark: {
      primary_driver: "user_mix_quality",
      acceptable_drivers: ["discount_policy_drift", "feature_positioning_gap"],
      wrong_paths: ["billing_complexity", "external_competition", "usability_regression"],
      expected_actions: [
        "Segment retention and paid conversion by acquisition channel and intent cohort.",
        "Compare collaboration depth and expansion behavior between new high-volume cohorts and legacy high-intent cohorts.",
        "Tighten or pause low-quality channels before redesigning the whole activation flow.",
      ],
    },
  },
  {
    case_id: "feature_usage_paradox",
    problem_brief:
      "A vertical SaaS launched a new dispatch console that quickly became the most-used workflow in the product, but renewal risk rose and account-level satisfaction fell even as daily feature usage increased.",
    evidence_pack: {
      case_type: "product",
      company: {
        sector: "Field service SaaS",
        product: "Dispatch and technician scheduling platform",
        customers: "Regional field service operators",
        business_model: "B2B subscription",
      },
      recent_changes: [
        "The old dispatch workflow was replaced by a denser new console.",
        "Training was updated, but customers had to move because the old flow was removed.",
        "Pricing and billing did not change during the release window.",
      ],
      observed_signals: [
        "Usage is up because nearly all dispatch tasks now go through the new console.",
        "Task time and error-correction activity rose after launch.",
        "Coordinators report confusion around bulk edits, hidden defaults, and exception handling.",
        "Admins like the new automation breadth, but front-line users say routine work takes more clicks.",
      ],
      conflicting_signals: [
        "Usage metrics make the launch look successful because the feature is mandatory.",
        "A few strategic customers expanded seats because they liked the automation options.",
      ],
      distractors: [
        "A short mobile outage hit one week after launch.",
        "Support missed SLAs for two days during a staffing transition.",
      ],
      constraints: [
        "Leadership must choose between enablement, rollback, or iteration.",
        "The diagnosis must separate forced usage from real value.",
      ],
    },
    hidden_benchmark: {
      primary_driver: "usability_regression",
      acceptable_drivers: ["support_capacity", "feature_positioning_gap"],
      wrong_paths: ["billing_complexity", "pricing_segmentation_shift", "user_mix_quality"],
      expected_actions: [
        "Compare task completion, error rate, and time-on-task before and after the console launch.",
        "Review session evidence and frontline user interviews for workflow friction in the new console.",
        "Prioritize usability fixes or a scoped rollback for high-friction dispatch paths before adding more training.",
      ],
    },
  },
  {
    case_id: "revenue_drop_strong_metrics",
    problem_brief:
      "A developer tools SaaS reports stable product engagement, healthy logo retention, and strong NPS, yet quarterly revenue fell and expansion slowed much more than pipeline or usage trends would suggest.",
    evidence_pack: {
      case_type: "revenue",
      company: {
        sector: "Developer tools SaaS",
        product: "Observability and debugging platform",
        customers: "Software teams from startup to enterprise",
        business_model: "Hybrid self-serve and sales-led subscription",
      },
      recent_changes: [
        "Lower tiers got more bundled usage and a stronger self-serve annual offer.",
        "Enterprise packaging was simplified and several add-ons were bundled.",
        "There was no major reliability incident or churn spike.",
      ],
      observed_signals: [
        "Logo retention stayed near plan, but contract value fell fastest in startup and SMB cohorts.",
        "Usage grew, yet revenue per active team fell in cohorts moved onto the new bundles.",
        "Enterprise renewals still closed, but add-on attach weakened after simplification.",
        "Engagement and satisfaction remain strong across retained accounts.",
      ],
      conflicting_signals: [
        "Healthy engagement makes the revenue decline look counterintuitive.",
        "A few large enterprise expansions slipped one month, which makes timing look relevant.",
      ],
      distractors: ["A competitor released a free community edition.", "Paid-search conversion softened slightly."],
      constraints: [
        "Leadership needs a revenue diagnosis, not a product-health diagnosis.",
        "The answer must explain how monetization fell while usage stayed healthy.",
      ],
    },
    hidden_benchmark: {
      primary_driver: "pricing_segmentation_shift",
      acceptable_drivers: ["user_mix_quality", "external_competition"],
      wrong_paths: ["billing_complexity", "usability_regression", "support_capacity"],
      expected_actions: [
        "Analyze revenue realization by segment, tier, bundle, and renewal cohort rather than by overall usage alone.",
        "Compare expansion and price realization before and after the packaging shift for startup, SMB, and enterprise cohorts.",
        "Redesign segmentation or packaging guardrails before assuming the product needs major changes.",
      ],
    },
  },
  {
    case_id: "support_ticket_explosion",
    problem_brief:
      "A fintech operations SaaS saw support tickets nearly triple in six weeks, but core product uptime and task success metrics stayed broadly stable.",
    evidence_pack: {
      case_type: "support",
      company: {
        sector: "Fintech operations SaaS",
        product: "Back-office reconciliation and payouts platform",
        customers: "Mid-market finance and operations teams",
        business_model: "B2B subscription with usage-based overages",
      },
      recent_changes: [
        "The company launched a new invoicing model with tiers, credits, and proration.",
        "Plan changes and invoice detail moved into a new billing portal.",
        "Support headcount stayed flat during the rollout.",
      ],
      observed_signals: [
        "Ticket spikes cluster around invoice delivery, plan changes, proration, and overage alerts.",
        "Core uptime and workflow success rates remain near normal.",
        "Many tickets ask how credits, thresholds, and charges map to activity.",
        "Accounts with no billing changes create far fewer extra tickets.",
      ],
      conflicting_signals: [
        "First-response time worsened once the queue grew, which makes staffing look relevant.",
        "Some customers say the portal is broken when the real issue is confusing charges.",
      ],
      distractors: [
        "A new support manager started in the same quarter.",
        "The help center taxonomy changed two weeks before the spike.",
      ],
      constraints: [
        "Leadership wants to cut ticket load without defaulting to headcount growth.",
        "The diagnosis must explain why confusion rose while product health stayed stable.",
      ],
    },
    hidden_benchmark: {
      primary_driver: "billing_complexity",
      acceptable_drivers: ["support_capacity", "pricing_segmentation_shift"],
      wrong_paths: ["external_competition", "usability_regression", "user_mix_quality"],
      expected_actions: [
        "Classify ticket volume by billing scenario, invoice event, and plan-change path.",
        "Inspect the billing portal, invoice detail, and proration explanations that generate the longest confusion loops.",
        "Simplify billing communication and billing-flow UX before defaulting to a broad support staffing response.",
      ],
    },
  },
  {
    case_id: "churn_after_feature_launch",
    problem_brief:
      "A sales enablement SaaS launched a highly requested AI briefing feature, but churn rose in the following quarter and several customers cited the launch period when explaining why they left.",
    evidence_pack: {
      case_type: "retention",
      company: {
        sector: "Sales enablement SaaS",
        product: "Seller coaching and account briefing platform",
        customers: "Mid-market and enterprise revenue teams",
        business_model: "B2B subscription",
      },
      recent_changes: [
        "The company launched an AI briefing feature and marketed it heavily.",
        "A larger competitor launched a broader bundled suite two months earlier.",
        "The new feature had minor quality issues but no severe outage.",
      ],
      observed_signals: [
        "Churn increased across both adopters and non-adopters of the new feature.",
        "Loss reviews increasingly mention that the competitor covers more workflows in one bundle.",
        "Some users found the feature underwhelming, but many departing accounts were already piloting the competitor.",
        "Legacy workflow usage stayed stable until accounts formally switched vendors.",
      ],
      conflicting_signals: [
        "Because churn rose after launch, teams are tempted to blame launch quality.",
        "Some users did report prompt-quality frustrations.",
      ],
      distractors: [
        "One billing-report export bug affected three enterprise accounts for a week.",
        "A small subgroup asked for more admin controls around the feature.",
      ],
      constraints: [
        "Leadership must choose between more feature fixes and a broader market response.",
        "The diagnosis should separate feature complaints from competitive displacement.",
      ],
    },
    hidden_benchmark: {
      primary_driver: "external_competition",
      acceptable_drivers: ["usability_regression", "feature_positioning_gap"],
      wrong_paths: ["billing_complexity", "user_mix_quality", "pricing_segmentation_shift"],
      expected_actions: [
        "Analyze churned and at-risk accounts for competitor bundle comparisons rather than only feature-usage complaints.",
        "Map renewal losses and win-loss data to specific competitor workflow coverage gaps.",
        "Adjust retention and product response around competitive displacement before assuming the launch itself caused most churn.",
      ],
    },
  },
];

export function buildConsultingExecutionInput(consultingCase: ConsultingCaseDefinition): ConsultingExecutionInput {
  return {
    problem: consultingCase.problem_brief,
    context: {
      case_id: consultingCase.case_id,
      case_type: consultingCase.evidence_pack.case_type,
      product: consultingCase.evidence_pack.company.product,
      customers: consultingCase.evidence_pack.company.customers,
      sector: consultingCase.evidence_pack.company.sector,
      business_model: consultingCase.evidence_pack.company.business_model,
      evidence_pack: consultingCase.evidence_pack,
    },
  };
}
