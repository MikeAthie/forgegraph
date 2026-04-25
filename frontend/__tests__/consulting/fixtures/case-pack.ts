export type ConsultingDriver =
  | "pricing_packaging"
  | "onboarding_time_to_value"
  | "product_fit_workflow_gap"
  | "support_delivery"
  | "competitive_pressure"
  | "segment_mismatch";

export type ConsultingCaseDefinition = {
  case_id: string;
  problem_brief: string;
  evidence_pack: {
    case_type: "pricing" | "onboarding" | "product";
    company: {
      sector: string;
      product: string;
      customers: string;
      business_model: string;
    };
    recent_changes: string[];
    observed_signals: string[];
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

export const CONSULTING_CASE_PACK: ConsultingCaseDefinition[] = [
  {
    case_id: "pricing-renewal-shock",
    problem_brief:
      "A workflow automation SaaS for small service businesses saw logo churn rise from 6% to 14% in one quarter after changing pricing and packaging.",
    evidence_pack: {
      case_type: "pricing",
      company: {
        sector: "Workflow automation SaaS",
        product: "Workflow automation platform",
        customers: "Small service businesses",
        business_model: "B2B subscription",
      },
      recent_changes: [
        "The company removed its legacy starter tier and raised effective renewal prices by 18% for most accounts renewing in the last 90 days.",
        "Discount approval rules were tightened so account managers could not match prior custom pricing.",
        "No major product rewrite or onboarding process change happened during the same quarter.",
      ],
      observed_signals: [
        "Churn is concentrated in accounts that hit renewal after the packaging change rather than in newly signed accounts.",
        "Product usage among churned accounts stayed roughly flat until the renewal month, then cancellations spiked immediately after invoice delivery.",
        "Support tickets increased, but most of the increase is billing confusion and contract complaints rather than product failure reports.",
        "Call notes from churned accounts repeatedly mention that the product still works but no longer fits the budget for smaller teams.",
        "The highest churn increase is in micro-SMB accounts with fewer than 10 seats, while larger SMB cohorts moved only slightly.",
      ],
      distractors: [
        "Two brief API incidents happened during the quarter but affected less than 2% of active customers.",
        "A competitor launched new AI marketing features during the same month.",
        "Customer support CSAT remained stable despite the higher ticket volume.",
      ],
      constraints: [
        "The company needs an action plan that can be tested before the next renewal wave.",
        "Leadership wants to know whether the problem is price level, packaging, or something else before reversing the change.",
      ],
    },
    hidden_benchmark: {
      primary_driver: "pricing_packaging",
      acceptable_drivers: ["segment_mismatch"],
      wrong_paths: ["support_delivery", "product_fit_workflow_gap", "competitive_pressure"],
      expected_actions: [
        "Segment churn by renewal cohort and pricing-change exposure.",
        "Compare cancel reasons for accounts that saw the new package versus legacy pricing.",
        "Test a targeted packaging or discount pilot for the most price-sensitive micro-SMB cohort.",
      ],
    },
  },
  {
    case_id: "self-serve-onboarding-dropoff",
    problem_brief:
      "A compliance training SaaS for distributed retail teams is losing new customers in the first 60 days after switching from guided onboarding to a self-serve setup flow.",
    evidence_pack: {
      case_type: "onboarding",
      company: {
        sector: "Compliance training SaaS",
        product: "Compliance training platform",
        customers: "Distributed retail operations teams",
        business_model: "B2B subscription",
      },
      recent_changes: [
        "Implementation specialists were reallocated and the company moved most new customers to a self-serve onboarding flow two months ago.",
        "Pricing has been unchanged for the last 12 months.",
        "The product roadmap did not remove any major features during the period.",
      ],
      observed_signals: [
        "Activation fell from 68% to 41% after the onboarding change, measured by accounts launching their first mandatory training campaign.",
        "Accounts that complete employee import and launch a campaign in the first 14 days retain at normal levels.",
        "Most churn now happens in the first 45 days rather than at annual renewal.",
        "Support tickets from new customers cluster around employee import errors, location setup, and uncertainty about first-step configuration.",
        "Customer interviews say the platform looks valuable once running, but setup feels confusing without live guidance.",
      ],
      distractors: [
        "A competitor started a seasonal promotion targeting retail companies last month.",
        "The mobile app has a modest backlog of cosmetic bugs that affect existing customers more than new setup.",
        "Average first-response time from support improved slightly over the same period.",
      ],
      constraints: [
        "The team needs a recovery plan that can improve retention without rebuilding the entire product.",
        "Leadership wants to know if the main issue is onboarding execution or deeper product value problems.",
      ],
    },
    hidden_benchmark: {
      primary_driver: "onboarding_time_to_value",
      acceptable_drivers: ["support_delivery"],
      wrong_paths: ["pricing_packaging", "competitive_pressure", "product_fit_workflow_gap"],
      expected_actions: [
        "Map setup drop-off by onboarding step and time-to-first-value.",
        "Interview or review session recordings from recently churned customers who failed during implementation.",
        "Reintroduce guided onboarding or targeted setup assistance for high-risk new accounts.",
      ],
    },
  },
  {
    case_id: "reporting-workflow-gap",
    problem_brief:
      "A product analytics SaaS for mid-market software teams is seeing expansion slow and churn rise because teams stop adopting the platform beyond a few power users.",
    evidence_pack: {
      case_type: "product",
      company: {
        sector: "Product analytics SaaS",
        product: "Product analytics platform",
        customers: "Mid-market software teams",
        business_model: "B2B subscription",
      },
      recent_changes: [
        "Pricing and packaging have been unchanged for the last three quarters.",
        "The company improved onboarding documentation and launched weekly office hours six months ago.",
        "No major service outage happened during the churn window.",
      ],
      observed_signals: [
        "Renewed accounts with broad retention typically have multiple teams using shared dashboards, while churned accounts rely on one analyst exporting data manually.",
        "Churned and downsized customers repeatedly ask for easier scheduled reporting, stakeholder-friendly views, and role-based sharing.",
        "Core event tracking setup completes successfully for most accounts, but weekly active users outside the analytics team remain low.",
        "Customer success notes say teams understand the product but struggle to operationalize insights across product, marketing, and leadership workflows.",
        "Lost-deal interviews mention competitors only after prospects conclude the current product cannot support cross-functional reporting needs.",
      ],
      distractors: [
        "A newer competitor has recently increased brand awareness in the category.",
        "Support volume rose slightly after a UI refresh, but satisfaction stayed strong.",
        "A few enterprise prospects requested custom security reviews that slowed some deals.",
      ],
      constraints: [
        "Leadership needs to know whether to push sales harder, improve onboarding again, or address a product workflow gap.",
        "Recommended actions should help validate the root cause before a major roadmap commitment.",
      ],
    },
    hidden_benchmark: {
      primary_driver: "product_fit_workflow_gap",
      acceptable_drivers: ["competitive_pressure"],
      wrong_paths: ["pricing_packaging", "support_delivery", "onboarding_time_to_value"],
      expected_actions: [
        "Interview churned or downsized accounts about reporting and cross-functional workflow gaps.",
        "Correlate retention and expansion with adoption of shared dashboards or multi-team usage patterns.",
        "Prioritize or prototype reporting and sharing capabilities that remove analyst-only bottlenecks.",
      ],
    },
  },
];

export function buildConsultingExecutionInput(
  consultingCase: ConsultingCaseDefinition,
): ConsultingExecutionInput {
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
