import http from "node:http";

const port = Number(process.env.PLAYWRIGHT_LLM_MOCK_PORT ?? "8011");

const CONSULTING_CASE_LIBRARY = {
  growth_high_acquisition_low_retention: {
    forgegraph: {
      problem_statement:
        "Growth accelerated, but lower-intent acquisition cohorts are depressing paid conversion and retention.",
      issue_tree: {
        core_question: "Why are record signups not turning into durable revenue growth?",
        branches: [
          "Acquisition channel and user mix quality",
          "Activation and time-to-value",
          "Pricing and monetization",
          "Product value narrative",
          "Expansion behavior by cohort",
          "Competitive noise",
        ],
      },
      hypotheses: [
        {
          id: "h1",
          text: "The growth push pulled in lower-intent users, so acquisition channel quality fell even though signups rose.",
        },
        {
          id: "h2",
          text: "Activation friction is causing new users to drop before they experience collaborative value.",
        },
        {
          id: "h3",
          text: "A weak product value narrative is attracting curiosity clicks instead of committed teams.",
        },
      ],
      evidence_log: [
        "Supports h1: creator and referral cohorts have much lower paid conversion than legacy organic and invite-based channels.",
        "Supports h1: many new accounts create one workspace, invite no teammates, and go inactive within two weeks.",
        "Supports h1: retained accounts that reach multi-user collaboration still show stable product satisfaction.",
        "Weakens h2: activation only dipped modestly overall, so a broken onboarding flow alone does not explain the retention collapse.",
        "Weakens h3: the problem concentrates in specific acquisition channels rather than across all traffic quality sources.",
        "Supports h1: sales-assisted high-intent product-qualified leads continue to expand at healthier rates than the high-volume cohorts.",
      ],
      reflection: {
        weak_hypotheses: ["h2", "h3"],
        missing_evidence: [
          "Retention by acquisition channel and collaboration-depth cohort.",
          "Paid conversion and expansion by referral, creator, and legacy organic sources.",
        ],
        inconsistencies: [
          "A pure onboarding diagnosis conflicts with stable satisfaction among users who reach multi-user collaboration.",
        ],
      },
      recommendation: {
        selected_hypothesis: "h1",
        selected_hypothesis_text:
          "The growth push pulled in lower-intent users, so acquisition channel quality fell even though signups rose.",
        rationale:
          "User mix quality is strongest because the retention damage is concentrated in the new high-volume cohorts while higher-intent legacy cohorts still convert and retain more normally.",
      },
      execution_plan: [
        {
          step: "Segment retention and paid conversion by acquisition channel and intent cohort.",
          owner: "Growth analytics",
          expected_outcome: "Confirm which new channels are bringing low-intent users into the funnel.",
        },
        {
          step: "Compare collaboration depth and expansion behavior between new high-volume cohorts and legacy high-intent cohorts.",
          owner: "Product operations",
          expected_outcome: "Separate shallow curiosity signups from durable multi-user adoption.",
        },
        {
          step: "Tighten or pause low-quality channels before redesigning the whole activation flow.",
          owner: "Growth lead",
          expected_outcome: "Protect retention and monetization while preserving the highest-quality demand sources.",
        },
      ],
    },
    baseline: {
      problem_statement: "Acquisition is up, but new users may not be reaching value quickly enough to retain.",
      issue_tree: {
        core_question: "Why are more signups not producing better revenue outcomes?",
        branches: [
          "Activation and time-to-value",
          "User mix quality",
          "Pricing",
          "Value narrative",
          "Expansion",
          "Competition",
        ],
      },
      hypotheses: [
        {
          id: "h1",
          text: "Activation friction is limiting time-to-value for newly acquired users.",
        },
        {
          id: "h2",
          text: "Lower-intent channels are filling the funnel with weak-fit users.",
        },
        {
          id: "h3",
          text: "The growth message may be attracting curiosity more than committed teams.",
        },
      ],
      evidence_log: [
        "Supports h1: many new accounts go inactive within two weeks.",
        "Supports h2: creator and referral cohorts convert below the historical baseline.",
        "Weakens h3: retained collaborative accounts still report solid product satisfaction.",
        "Supports h1: activation dipped modestly during the growth push.",
      ],
      reflection: {
        weak_hypotheses: ["h3"],
        missing_evidence: ["Retention by detailed acquisition cohort."],
        inconsistencies: ["Low-quality channels are plausible, but inactivity also points toward activation friction."],
      },
      recommendation: {
        selected_hypothesis: "h1",
        selected_hypothesis_text: "Activation friction is limiting time-to-value for newly acquired users.",
        rationale:
          "Activation is a strong secondary explanation because many new users drop quickly before showing deeper collaboration behavior.",
      },
      execution_plan: [
        {
          step: "Review early funnel drop-off for new cohorts.",
          owner: "Growth analytics",
          expected_outcome: "Show where users leave before they reach value.",
        },
        {
          step: "Test lighter onboarding support for low-conversion cohorts.",
          owner: "Lifecycle marketing",
          expected_outcome: "Improve time-to-value for recent signups.",
        },
        {
          step: "Interview inactive trial users from high-volume channels.",
          owner: "Research",
          expected_outcome: "Clarify whether the problem is weak fit or weak activation.",
        },
      ],
    },
  },
  feature_usage_paradox: {
    forgegraph: {
      problem_statement:
        "The new dispatch console is heavily used because it is mandatory, but frontline workflow usability regressed and renewal risk rose.",
      issue_tree: {
        core_question: "Why did feature adoption rise while customer sentiment and renewal risk worsened?",
        branches: [
          "Usability and workflow friction",
          "Training and support capacity",
          "Feature positioning and expectations",
          "Operational exception handling",
          "Admin versus frontline user needs",
          "Competitive alternatives",
        ],
      },
      hypotheses: [
        {
          id: "h1",
          text: "The new dispatch console introduced a usability regression for routine frontline work.",
        },
        {
          id: "h2",
          text: "Workflow misalignment means the console optimizes automation breadth more than dispatcher day-to-day tasks.",
        },
        {
          id: "h3",
          text: "Support and training gaps are driving most of the frustration.",
        },
      ],
      evidence_log: [
        "Supports h1: task completion time and error-correction activity rose after the console launch.",
        "Supports h1: branch coordinators report more clicks, hidden defaults, and harder exception handling in the mandatory workflow.",
        "Supports h2: admins like the automation breadth, but front-line dispatchers struggle in routine daily operations.",
        "Weakens h3: staffing noise existed, but dissatisfaction is concentrated in the new console itself rather than in generic support response patterns.",
        "Supports h1: the accounts with the heaviest day-to-day dispatcher usage show the biggest frustration increase despite high feature usage.",
        "Weakens h2: the strongest immediate signal is not just strategic workflow mismatch but concrete usability regression in the interface.",
      ],
      reflection: {
        weak_hypotheses: ["h3"],
        missing_evidence: [
          "Before-and-after session evidence on time-on-task and error recovery.",
          "Friction ranking by routine dispatch path and user role.",
        ],
        inconsistencies: [
          "Mandatory usage makes the launch look healthy in adoption metrics even while the user experience deteriorates.",
        ],
      },
      recommendation: {
        selected_hypothesis: "h1",
        selected_hypothesis_text:
          "The new dispatch console introduced a usability regression for routine frontline work.",
        rationale:
          "Usability regression is primary because the strongest evidence is higher task time, more corrections, and specific interface friction in the new mandatory workflow rather than broad support failure.",
      },
      execution_plan: [
        {
          step: "Compare task completion, error rate, and time-on-task before and after the console launch.",
          owner: "Product analytics",
          expected_outcome: "Quantify where frontline workflow efficiency regressed.",
        },
        {
          step: "Review session evidence and frontline user interviews for workflow friction in the new console.",
          owner: "UX research",
          expected_outcome: "Identify the interface elements creating the largest usability penalties.",
        },
        {
          step: "Prioritize usability fixes or a scoped rollback for high-friction dispatch paths before adding more training.",
          owner: "Product management",
          expected_outcome: "Reduce renewal risk by fixing the workflow itself rather than only explaining it better.",
        },
      ],
    },
    baseline: {
      problem_statement:
        "The dispatch launch increased usage, but support and training may not have kept pace with the workflow change.",
      issue_tree: {
        core_question: "Why did customer sentiment drop after the dispatch launch?",
        branches: ["Support capacity", "Usability", "Workflow fit", "Training", "Positioning", "Competition"],
      },
      hypotheses: [
        {
          id: "h1",
          text: "Support capacity and training gaps are making the rollout feel rougher than it should.",
        },
        {
          id: "h2",
          text: "The new console is harder for dispatchers to use in daily workflows.",
        },
        {
          id: "h3",
          text: "The launch promise may not match how frontline users actually work.",
        },
      ],
      evidence_log: [
        "Supports h1: training attendance dipped and support SLAs missed during part of the launch month.",
        "Supports h2: dispatchers complain about more clicks and hidden defaults.",
        "Weakens h3: admins still appreciate the new automation breadth.",
        "Supports h1: frustration increased during the release transition period.",
      ],
      reflection: {
        weak_hypotheses: ["h3"],
        missing_evidence: ["Role-level evidence on where users struggle most."],
        inconsistencies: ["Workflow friction exists, but rollout support also deteriorated."],
      },
      recommendation: {
        selected_hypothesis: "h1",
        selected_hypothesis_text:
          "Support capacity and training gaps are making the rollout feel rougher than it should.",
        rationale:
          "Support capacity is a plausible but weaker explanation because launch-period staffing and training noise amplified user frustration.",
      },
      execution_plan: [
        {
          step: "Review launch support load and training coverage.",
          owner: "Support operations",
          expected_outcome: "Show whether rollout enablement was under-resourced.",
        },
        {
          step: "Add dispatcher-focused training sessions.",
          owner: "Enablement lead",
          expected_outcome: "Reduce confusion in the new workflow.",
        },
        {
          step: "Collect frontline complaints by workflow step.",
          owner: "Customer success",
          expected_outcome: "Determine whether support fixes or product fixes matter most.",
        },
      ],
    },
  },
  revenue_drop_strong_metrics: {
    forgegraph: {
      problem_statement:
        "Revenue fell because pricing and segment mix shifted toward lower-realization bundles even while product engagement stayed healthy.",
      issue_tree: {
        core_question: "Why did revenue realization weaken while usage, NPS, and logo retention stayed strong?",
        branches: [
          "Pricing and segmentation shift",
          "Discount policy drift",
          "Enterprise packaging simplification",
          "Expansion attach behavior",
          "Usage versus monetization",
          "Competitive effects",
        ],
      },
      hypotheses: [
        {
          id: "h1",
          text: "Revenue is down because the packaging shift lowered price realization across the fastest-growing segments.",
        },
        {
          id: "h2",
          text: "Discount policy drift and looser commercial guardrails are eroding realized contract value.",
        },
        {
          id: "h3",
          text: "A competitor free tier is reducing willingness to pay despite stable product engagement.",
        },
      ],
      evidence_log: [
        "Supports h1: average contract value fell fastest in startup and SMB cohorts that moved onto the new bundles.",
        "Supports h1: usage grew while realized revenue per active team fell after the packaging change.",
        "Supports h2: premium add-on attach and step-up expansion weakened after enterprise packaging was simplified.",
        "Weakens h3: there is no matching churn spike or product satisfaction collapse that would suggest broad competitive displacement.",
        "Supports h1: sales reports more opportunities landing on lighter packages without obvious product dissatisfaction.",
        "Weakens h2: discount drift matters, but the larger structural shift is segment and bundle mix rather than isolated concessions.",
      ],
      reflection: {
        weak_hypotheses: ["h3"],
        missing_evidence: [
          "Revenue realization by segment, tier, and renewal cohort before and after the packaging change.",
          "Expansion and add-on attach deltas by enterprise versus startup cohorts.",
        ],
        inconsistencies: [
          "Healthy engagement can hide monetization erosion when the price architecture changes faster than product value.",
        ],
      },
      recommendation: {
        selected_hypothesis: "h1",
        selected_hypothesis_text:
          "Revenue is down because the packaging shift lowered price realization across the fastest-growing segments.",
        rationale:
          "Pricing segmentation shift is primary because revenue deterioration concentrates in cohorts moved onto lighter bundles while usage and retention remain healthy.",
      },
      execution_plan: [
        {
          step: "Analyze revenue realization by segment, tier, bundle, and renewal cohort rather than by overall usage alone.",
          owner: "Revenue analytics",
          expected_outcome: "Identify where lower-realization packaging is compressing revenue.",
        },
        {
          step: "Compare expansion and price realization before and after the packaging shift for startup, SMB, and enterprise cohorts.",
          owner: "Pricing strategy",
          expected_outcome: "Separate structural segmentation effects from one-off enterprise timing noise.",
        },
        {
          step: "Redesign segmentation or packaging guardrails before assuming the product needs major changes.",
          owner: "Revenue leadership",
          expected_outcome: "Recover revenue leverage without disrupting strong product health.",
        },
      ],
    },
    baseline: {
      problem_statement:
        "Revenue is down even though product health is strong, so discounting and commercial policy may be eroding value.",
      issue_tree: {
        core_question: "What is weakening monetization while product engagement remains strong?",
        branches: [
          "Discount policy drift",
          "Pricing and segmentation shift",
          "Expansion attach",
          "Competitive pressure",
          "Pipeline timing",
          "Usage mix",
        ],
      },
      hypotheses: [
        {
          id: "h1",
          text: "Discount policy drift is reducing realized contract value.",
        },
        {
          id: "h2",
          text: "The packaging shift moved too much growth into lower-value segments and tiers.",
        },
        {
          id: "h3",
          text: "Competitors lowered willingness to pay even though customers still like the product.",
        },
      ],
      evidence_log: [
        "Supports h1: more opportunities land on lighter packages and broader bundles.",
        "Supports h2: average contract value declined fastest in startup and SMB cohorts.",
        "Weakens h3: retention and NPS remain healthy.",
        "Supports h1: premium attach weakened after commercial simplification.",
      ],
      reflection: {
        weak_hypotheses: ["h3"],
        missing_evidence: ["Direct separation of packaging effects versus discount effects."],
        inconsistencies: [
          "Segment mix and discount policy both matter, and the primary mechanism still needs ranking.",
        ],
      },
      recommendation: {
        selected_hypothesis: "h1",
        selected_hypothesis_text: "Discount policy drift is reducing realized contract value.",
        rationale:
          "Discount policy drift is a strong secondary explanation because commercial guardrails weakened alongside the packaging changes.",
      },
      execution_plan: [
        {
          step: "Audit discounting and package concessions across recent renewals.",
          owner: "Deal desk",
          expected_outcome: "Show whether commercial guardrails materially loosened.",
        },
        {
          step: "Compare realized price by segment and tier.",
          owner: "Revenue analytics",
          expected_outcome: "Clarify where pricing leverage fell fastest.",
        },
        {
          step: "Tighten approval thresholds for new discount requests.",
          owner: "Pricing strategy",
          expected_outcome: "Stabilize price realization while the team studies bundle design.",
        },
      ],
    },
  },
  support_ticket_explosion: {
    forgegraph: {
      problem_statement:
        "Support tickets exploded because billing complexity and the new billing portal created confusion even though core product health stayed stable.",
      issue_tree: {
        core_question: "Why did ticket volume spike without a matching deterioration in core workflow reliability?",
        branches: [
          "Billing complexity",
          "Support capacity",
          "Invoice and portal UX",
          "Plan-change and proration paths",
          "Operational product bugs",
          "Customer communication",
        ],
      },
      hypotheses: [
        {
          id: "h1",
          text: "Billing complexity in the new invoicing and proration model is driving the ticket explosion.",
        },
        {
          id: "h2",
          text: "Support capacity is the main bottleneck because the queue grew faster than the team could absorb.",
        },
        {
          id: "h3",
          text: "A small set of product bugs is masking itself as a broader support issue.",
        },
      ],
      evidence_log: [
        "Supports h1: ticket spikes align with invoice delivery, plan changes, proration questions, and overage alerts.",
        "Supports h1: agents report long explanation loops about credits, thresholds, and charge mapping rather than bug reproduction.",
        "Supports h1: accounts with no plan or invoice changes generate far fewer additional tickets than accounts that changed plans mid-cycle.",
        "Weakens h2: response time worsened because volume surged, but the content of tickets points to billing confusion instead of generic staffing failure.",
        "Weakens h3: core uptime and task success remain stable, and the payout-export bug affected only a small subset of tickets.",
        "Supports h1: customers often describe the portal as broken when the underlying issue is that billing line items are hard to understand.",
      ],
      reflection: {
        weak_hypotheses: ["h2", "h3"],
        missing_evidence: [
          "Ticket classification by billing scenario and portal path.",
          "Evidence on which invoice and plan-change screens create the most confusion loops.",
        ],
        inconsistencies: [
          "A support staffing response alone would not resolve the repeated confusion around credits, proration, and overage logic.",
        ],
      },
      recommendation: {
        selected_hypothesis: "h1",
        selected_hypothesis_text:
          "Billing complexity in the new invoicing and proration model is driving the ticket explosion.",
        rationale:
          "Billing complexity is primary because the timing, content, and affected-account patterns all point to billing events rather than to broad product instability or pure support understaffing.",
      },
      execution_plan: [
        {
          step: "Classify ticket volume by billing scenario, invoice event, and plan-change path.",
          owner: "Support operations",
          expected_outcome: "Quantify exactly which billing flows are creating the ticket surge.",
        },
        {
          step: "Inspect the billing portal, invoice detail, and proration explanations that generate the longest confusion loops.",
          owner: "Billing product",
          expected_outcome: "Identify the UX and communication failures driving repeated customer questions.",
        },
        {
          step: "Simplify billing communication and billing-flow UX before defaulting to a broad support staffing response.",
          owner: "Finance systems lead",
          expected_outcome: "Reduce avoidable ticket demand at the source.",
        },
      ],
    },
    baseline: {
      problem_statement:
        "Ticket volume surged, so the support team may be under too much load during a period of customer confusion.",
      issue_tree: {
        core_question: "What explains the support queue explosion?",
        branches: [
          "Support capacity",
          "Billing complexity",
          "Portal UX",
          "Product bugs",
          "Communication",
          "Competition",
        ],
      },
      hypotheses: [
        {
          id: "h1",
          text: "Support capacity is the main bottleneck because the team cannot absorb the new ticket load.",
        },
        {
          id: "h2",
          text: "Billing complexity in the new portal is confusing customers.",
        },
        {
          id: "h3",
          text: "A few product bugs are causing disproportionate support load.",
        },
      ],
      evidence_log: [
        "Supports h1: first-response time worsened after the queue expanded.",
        "Supports h2: many tickets involve invoice delivery and plan-change questions.",
        "Weakens h3: uptime stayed broadly stable.",
        "Supports h1: the support team headcount stayed flat during a period of heavier demand.",
      ],
      reflection: {
        weak_hypotheses: ["h3"],
        missing_evidence: ["A detailed breakdown of billing versus non-billing tickets."],
        inconsistencies: ["Billing questions are common, but queue strain also makes capacity look material."],
      },
      recommendation: {
        selected_hypothesis: "h1",
        selected_hypothesis_text:
          "Support capacity is the main bottleneck because the team cannot absorb the new ticket load.",
        rationale:
          "Support capacity is a strong secondary explanation because response times worsened sharply once the queue expanded.",
      },
      execution_plan: [
        {
          step: "Review staffing coverage and queue backlog by day.",
          owner: "Support operations",
          expected_outcome: "Show whether staffing is keeping up with ticket demand.",
        },
        {
          step: "Create temporary macros for common invoice questions.",
          owner: "Support lead",
          expected_outcome: "Shorten resolution times while the root cause is investigated.",
        },
        {
          step: "Sample billing-related tickets for recurring themes.",
          owner: "Customer success",
          expected_outcome: "Clarify whether billing confusion or staffing is the larger issue.",
        },
      ],
    },
  },
  churn_after_feature_launch: {
    forgegraph: {
      problem_statement:
        "Churn rose after the feature launch because a competitor's broader bundled platform displaced accounts, not because the launch itself broke the product.",
      issue_tree: {
        core_question: "Why did churn rise after the AI feature launch period?",
        branches: [
          "External competition and bundle coverage",
          "Feature positioning and expectation gap",
          "Launch usability quality",
          "Renewal and retention timing",
          "Legacy workflow stickiness",
          "Market narrative shift",
        ],
      },
      hypotheses: [
        {
          id: "h1",
          text: "External competition is displacing accounts because a larger rival now bundles more adjacent workflows in one suite.",
        },
        {
          id: "h2",
          text: "The launch created a feature positioning gap because the AI briefing promise outpaced what the product delivered.",
        },
        {
          id: "h3",
          text: "Usability issues in the new AI feature caused most of the churn spike.",
        },
      ],
      evidence_log: [
        "Supports h1: churn increased among both feature adopters and non-adopters, which is inconsistent with a launch-quality-only explanation.",
        "Supports h1: renewal calls and loss reviews increasingly mention that the competitor now covers more workflows in one bundle.",
        "Supports h1: several departing accounts were already piloting the competitor before the feature launched.",
        "Weakens h3: some prompt-quality complaints exist, but legacy workflow usage stayed stable until formal vendor switch decisions were made.",
        "Supports h2: the launch message may have amplified scrutiny, but it does not explain why non-adopters also churned.",
        "Supports h1: win-loss notes frame the problem as a broader platform comparison rather than a single feature defect.",
      ],
      reflection: {
        weak_hypotheses: ["h3"],
        missing_evidence: [
          "Renewal losses mapped to specific competitor workflow gaps and bundle comparisons.",
          "Churn pattern split by competitor exposure, feature adoption, and sales-cycle timing.",
        ],
        inconsistencies: [
          "Blaming the feature launch alone conflicts with churn among accounts that barely touched the feature.",
        ],
      },
      recommendation: {
        selected_hypothesis: "h1",
        selected_hypothesis_text:
          "External competition is displacing accounts because a larger rival now bundles more adjacent workflows in one suite.",
        rationale:
          "External competition is primary because the churn pattern lines up with broader bundle comparisons and pre-existing competitive pilots more than with local launch-quality complaints.",
      },
      execution_plan: [
        {
          step: "Analyze churned and at-risk accounts for competitor bundle comparisons rather than only feature-usage complaints.",
          owner: "Revenue strategy",
          expected_outcome: "Confirm how often broader suite coverage drives retention risk.",
        },
        {
          step: "Map renewal losses and win-loss data to specific competitor workflow coverage gaps.",
          owner: "Product marketing",
          expected_outcome: "Identify which adjacent workflows are causing competitive displacement.",
        },
        {
          step: "Adjust retention and product response around competitive displacement before assuming the launch itself caused most churn.",
          owner: "Executive staff",
          expected_outcome: "Target the real market threat rather than only polishing a single feature.",
        },
      ],
    },
    baseline: {
      problem_statement:
        "The feature launch may have raised expectations faster than the product delivered, increasing churn pressure.",
      issue_tree: {
        core_question: "Why did churn rise after the launch period?",
        branches: [
          "Feature positioning gap",
          "Usability quality",
          "External competition",
          "Renewal timing",
          "Market narrative",
          "Workflow coverage",
        ],
      },
      hypotheses: [
        {
          id: "h1",
          text: "The launch created a feature positioning gap because the promise outpaced the delivered value.",
        },
        {
          id: "h2",
          text: "External competition is winning because the rival covers more adjacent workflows.",
        },
        {
          id: "h3",
          text: "Usability issues in the AI feature frustrated users enough to trigger churn.",
        },
      ],
      evidence_log: [
        "Supports h1: some users said the AI briefing feature felt underwhelming after a heavily marketed launch.",
        "Supports h2: renewal calls mention a competitor bundle that covers more workflows.",
        "Weakens h3: not all churned accounts used the feature deeply.",
        "Supports h1: teams repeatedly referenced the launch period when explaining dissatisfaction.",
      ],
      reflection: {
        weak_hypotheses: ["h3"],
        missing_evidence: ["Direct ranking of competitor displacement versus launch expectation effects."],
        inconsistencies: ["Competitive pressure is real, but the launch also appears to have increased scrutiny."],
      },
      recommendation: {
        selected_hypothesis: "h1",
        selected_hypothesis_text:
          "The launch created a feature positioning gap because the promise outpaced the delivered value.",
        rationale:
          "Feature positioning gap is a strong secondary explanation because the launch message intensified disappointment even if competition also mattered.",
      },
      execution_plan: [
        {
          step: "Review launch feedback and churn interviews for expectation gaps.",
          owner: "Product marketing",
          expected_outcome: "Clarify whether the message outran the actual feature value.",
        },
        {
          step: "Track competitor mentions in renewal conversations.",
          owner: "Revenue operations",
          expected_outcome: "Measure how often competitive displacement appears alongside launch complaints.",
        },
        {
          step: "Refine launch messaging while improving feature polish.",
          owner: "Product leadership",
          expected_outcome: "Reduce dissatisfaction if expectations are part of the issue.",
        },
      ],
    },
  },
};

function json(response, statusCode, payload, extraHeaders = {}) {
  response.writeHead(statusCode, {
    "Content-Type": "application/json",
    ...extraHeaders,
  });
  response.end(JSON.stringify(payload));
}

function extractPrompt(messages) {
  if (!Array.isArray(messages) || messages.length === 0) return "";
  const lastMessage = messages[messages.length - 1];
  return typeof lastMessage?.content === "string" ? lastMessage.content : "";
}

function extractStage(prompt) {
  const match = prompt.match(/Stage:\s*([A-Za-z0-9_:-]+)/);
  return match ? match[1] : "";
}

function extractBalancedJsonBlock(text, startIndex) {
  let depth = 0;
  let inString = false;
  let escaping = false;

  for (let index = startIndex; index < text.length; index += 1) {
    const character = text[index];

    if (escaping) {
      escaping = false;
      continue;
    }

    if (inString && character === "\\") {
      escaping = true;
      continue;
    }

    if (character === '"') {
      inString = !inString;
      continue;
    }

    if (inString) {
      continue;
    }

    if (character === "{") {
      depth += 1;
    } else if (character === "}") {
      depth -= 1;
      if (depth === 0) {
        return text.slice(startIndex, index + 1);
      }
    }
  }

  return null;
}

function extractJsonAfterLabel(prompt, label) {
  const labelIndex = prompt.indexOf(label);
  if (labelIndex === -1) return null;
  const objectStart = prompt.indexOf("{", labelIndex + label.length);
  if (objectStart === -1) return null;
  const jsonBlock = extractBalancedJsonBlock(prompt, objectStart);
  if (!jsonBlock) return null;

  try {
    return JSON.parse(jsonBlock);
  } catch {
    return null;
  }
}

function extractExecutionState(prompt) {
  const legacyMatch = prompt.match(/BEGIN_EXECUTION_STATE_JSON\s*([\s\S]*?)\s*END_EXECUTION_STATE_JSON/);
  if (legacyMatch) {
    try {
      return JSON.parse(legacyMatch[1]);
    } catch {
      return null;
    }
  }

  return extractJsonAfterLabel(prompt, "Current execution state JSON:");
}

function extractConsultingContext(prompt) {
  return extractJsonAfterLabel(prompt, "Context JSON:");
}

function extractBaselineInput(prompt) {
  return extractJsonAfterLabel(prompt, "Input JSON:");
}

function cloneState(state) {
  return JSON.parse(JSON.stringify(state));
}

function dedupe(values) {
  return [...new Set(values.filter(Boolean))];
}

function memoryRetrievalPatch(currentState, nodeName) {
  const current = currentState?.memory_retrieval;
  if (!current || typeof current !== "object") {
    return {
      count: 0,
      scope: "graph",
      used_by_nodes: [],
      ignored_by_nodes: [nodeName],
      memory_ids: [],
    };
  }

  return {
    count: typeof current.count === "number" ? current.count : 0,
    scope: typeof current.scope === "string" && current.scope ? current.scope : "graph",
    used_by_nodes: Array.isArray(current.used_by_nodes) ? dedupe(current.used_by_nodes) : [],
    ignored_by_nodes: dedupe([...(Array.isArray(current.ignored_by_nodes) ? current.ignored_by_nodes : []), nodeName]),
    memory_ids: Array.isArray(current.memory_ids) ? current.memory_ids : [],
  };
}

function buildMarketingPatch(stage, currentState) {
  const next = cloneState(
    currentState ?? {
      goal: "Launch a replayable AI digital marketing campaign for ForgeGraph.",
      strategy: null,
      content_assets: [],
      distribution_plan: null,
      analytics: null,
      iteration: 0,
    },
  );
  const pass = Number(next.iteration ?? 0) + 1;

  switch (stage) {
    case "strategy_agent":
      return {
        strategy: {
          company: "ForgeGraph Digital Marketing Co",
          objective: next.goal,
          primary_channel: "linkedin",
          audience: "B2B operators evaluating AI workflow tooling",
          positioning: `Iteration ${pass} message focused on replayable execution and observability.`,
          content_pillars: ["reliability", "traceability", "measurable campaign loops"],
        },
      };
    case "content_copywriter_specialist":
      return {
        asset: {
          asset_id: `copy-${pass}`,
          specialist: "copywriter_specialist",
          channel: "linkedin",
          format: "post",
          headline: `Replayable growth loop v${pass}`,
          body: `Launch ForgeGraph's replayable workflow story with observable execution, resilient retries, and clear operator trust signals in pass ${pass}.`,
          iteration: pass,
          reviewed: false,
          department: "content",
          state_field: "content_assets",
        },
      };
    case "content_editor_specialist":
      return {
        asset: {
          asset_id: `editorial-${pass}`,
          specialist: "editor_specialist",
          channel: "email",
          format: "brief",
          headline: `Editorial QA pass v${pass}`,
          body: "Reviewed copy for clarity, CTA alignment, and observable execution language.",
          iteration: pass,
          reviewed: true,
          department: "content",
          state_field: "content_assets",
        },
      };
    case "distribution_agent":
      return {
        distribution_plan: {
          owner: "distribution_agent",
          channels: next.content_assets.map((asset) => asset.channel),
          asset_ids: next.content_assets.map((asset) => asset.asset_id),
          cadence: `day-${pass} morning publish window`,
        },
      };
    default:
      return next;
  }
}

function extractAllowedTools(prompt) {
  const marker = "Allowed tools:\n";
  const nextMarker = "\n\nCurrent workflow state:";
  const start = prompt.indexOf(marker);
  if (start === -1) return [];
  const end = prompt.indexOf(nextMarker, start);
  const block = prompt.slice(start + marker.length, end === -1 ? undefined : end);
  return block
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.startsWith("- "))
    .map((line) => line.slice(2).trim())
    .filter(Boolean);
}

function buildChatCompletion(content, model) {
  return {
    id: "chatcmpl-playwright-mock",
    object: "chat.completion",
    created: Math.floor(Date.now() / 1000),
    model,
    choices: [
      {
        index: 0,
        message: {
          role: "assistant",
          content,
        },
        finish_reason: "stop",
      },
    ],
    usage: {
      prompt_tokens: 42,
      completion_tokens: 18,
      total_tokens: 60,
    },
  };
}

function handleAgentPrompt(prompt, model) {
  const allowedTools = extractAllowedTools(prompt);
  const primaryTool = allowedTools[0] ?? "playwright_runtime_health_check";
  const hasToolOutput = prompt.includes('"tool_output"');

  if (!hasToolOutput) {
    return buildChatCompletion(
      JSON.stringify({
        action: "tool_call",
        tool: primaryTool,
        tool_input: {
          channel: "telegram",
          mode: "status_check",
        },
      }),
      model,
    );
  }

  return buildChatCompletion(
    JSON.stringify({
      action: "final_answer",
      final_answer: "Jackie checked your workspace health and everything looks good. No urgent issues found.",
    }),
    model,
  );
}

function handleMarketingPrompt(prompt, model) {
  const stage = extractStage(prompt);
  const currentState = extractExecutionState(prompt);
  const patch = buildMarketingPatch(stage, currentState);
  return buildChatCompletion(JSON.stringify(patch, null, 2), model);
}

function resolveConsultingCase(contextOrInput) {
  const caseId = contextOrInput?.context?.case_id ?? contextOrInput?.case_id;
  if (caseId && CONSULTING_CASE_LIBRARY[caseId]) {
    return CONSULTING_CASE_LIBRARY[caseId];
  }
  return null;
}

function handleConsultingStagePrompt(prompt, model) {
  const stage = extractStage(prompt);
  const currentState = extractExecutionState(prompt) ?? {};
  const context = extractConsultingContext(prompt) ?? {};
  const caseLibrary = resolveConsultingCase(context);

  if (!caseLibrary) {
    return buildChatCompletion(
      JSON.stringify({
        state_patch: {
          problem_statement: "Unknown consulting case.",
          issue_tree: null,
          hypotheses: [],
          evidence_log: [],
          reflection: null,
          memory_retrieval: null,
          recommendation: null,
          execution_plan: [],
        },
      }),
      model,
    );
  }

  const artifact = caseLibrary.forgegraph;
  let payload;

  switch (stage) {
    case "intake":
      payload = {
        state_patch: {
          problem_statement: artifact.problem_statement,
          issue_tree: null,
          hypotheses: [],
          evidence_log: [],
          reflection: null,
          memory_retrieval: null,
          recommendation: null,
          execution_plan: [],
        },
      };
      break;
    case "structuring":
      payload = {
        state_patch: {
          problem_statement: artifact.problem_statement,
          issue_tree: artifact.issue_tree,
        },
      };
      break;
    case "hypothesis":
      payload = {
        state_patch: {
          hypotheses: artifact.hypotheses,
          memory_retrieval: memoryRetrievalPatch(currentState, "hypothesis"),
        },
      };
      break;
    case "analysis":
      payload = {
        state_patch: {
          evidence_log: artifact.evidence_log,
        },
      };
      break;
    case "reflection":
      payload = {
        state_patch: {
          reflection: artifact.reflection,
          memory_retrieval: memoryRetrievalPatch(currentState, "reflection"),
        },
      };
      break;
    case "recommendation":
      payload = {
        state_patch: {
          recommendation: artifact.recommendation,
        },
      };
      break;
    case "planner":
      payload = {
        state_patch: {
          execution_plan: artifact.execution_plan,
        },
      };
      break;
    default:
      payload = { state_patch: {} };
      break;
  }

  return buildChatCompletion(JSON.stringify(payload, null, 2), model);
}

function handleConsultingBaselinePrompt(prompt, model) {
  const input = extractBaselineInput(prompt) ?? {};
  const caseLibrary = resolveConsultingCase(input);

  if (!caseLibrary) {
    return buildChatCompletion(
      JSON.stringify(
        {
          problem_statement: "Unknown consulting case.",
          issue_tree: { core_question: "Unknown", branches: [] },
          hypotheses: [],
          evidence_log: [],
          reflection: { weak_hypotheses: [], missing_evidence: [], inconsistencies: [] },
          memory_retrieval: null,
          recommendation: {
            selected_hypothesis: "h1",
            selected_hypothesis_text: "Unknown",
            rationale: "Unknown",
          },
          execution_plan: [],
        },
        null,
        2,
      ),
      model,
    );
  }

  return buildChatCompletion(JSON.stringify({ ...caseLibrary.baseline, memory_retrieval: null }, null, 2), model);
}

const server = http.createServer(async (request, response) => {
  if (!request.url) {
    json(response, 404, { error: "missing URL" });
    return;
  }

  if (request.method === "GET" && request.url === "/health") {
    json(response, 200, { status: "ok" });
    return;
  }

  if (request.method === "GET" && request.url === "/v1/models") {
    json(response, 200, {
      data: [{ id: "playwright-consulting-mock" }],
    });
    return;
  }

  if (request.method === "OPTIONS" && request.url === "/v1/chat/completions") {
    response.writeHead(204);
    response.end();
    return;
  }

  if (request.method === "POST" && request.url === "/v1/chat/completions") {
    let body = "";
    request.setEncoding("utf8");
    for await (const chunk of request) {
      body += chunk;
    }

    const payload = body ? JSON.parse(body) : {};
    const prompt = extractPrompt(payload.messages);
    const model = typeof payload.model === "string" && payload.model ? payload.model : "gpt-4.1-mini";

    if (prompt.includes("You are executing inside a ForgeGraph agent node.")) {
      json(response, 200, handleAgentPrompt(prompt, model));
      return;
    }

    if (prompt.includes("BEGIN_EXECUTION_STATE_JSON") && prompt.includes("END_EXECUTION_STATE_JSON")) {
      json(response, 200, handleMarketingPrompt(prompt, model));
      return;
    }

    if (prompt.includes("Solve this business problem in one response.") && prompt.includes("Input JSON:")) {
      json(response, 200, handleConsultingBaselinePrompt(prompt, model));
      return;
    }

    if (
      prompt.includes("Current execution state JSON:") &&
      prompt.includes("Context JSON:") &&
      prompt.includes("Stage:")
    ) {
      json(response, 200, handleConsultingStagePrompt(prompt, model));
      return;
    }

    json(response, 200, buildChatCompletion("Mock response from the Playwright OpenAI server.", model));
    return;
  }

  json(response, 404, { error: "not found", path: request.url });
});

server.listen(port, "127.0.0.1", () => {
  // eslint-disable-next-line no-console
  console.log(`Playwright OpenAI mock listening on http://127.0.0.1:${port}`);
});
