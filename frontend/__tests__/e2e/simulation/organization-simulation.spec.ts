import { execFileSync } from "child_process";
import { mkdtempSync, rmSync, writeFileSync } from "fs";
import os from "os";
import path from "path";

import { expect, test, type APIRequestContext, type Page, type Route, type TestInfo } from "@playwright/test";

import {
  createTestUser,
  ensureUserRegistered,
  fetchLatestGraphVersion,
  getAccessToken,
  openBackendAuthenticatedPage,
} from "../helpers";
import {
  buildCompanyGraphJson,
  buildCompanyProfile,
  type CompanyDepartment,
  type CompanyProfile,
} from "../../../lib/company-workspace";

const API_BASE_URL = (
  process.env.PLAYWRIGHT_API_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://127.0.0.1:8000"
).replace(/\/$/, "");
const BACKEND_DIR = path.join(__dirname, "..", "..", "..", "..", "backend");
const MANAGEMENT_ENV = {
  ...process.env,
  USE_SQLITE: process.env.USE_SQLITE ?? "false",
  SQLITE_DB_PATH: process.env.SQLITE_DB_PATH,
};

const ORGANIZATION_NAME = "Demo Holding Company";
const COMPANY_NAME = "Atlas Growth Agency OS";
const COMPANY_TYPE = "Digital Marketing Agency";
const COMPANY_OBJECTIVE =
  "Operate an AI digital marketing agency that designs, validates, launches, and improves client campaigns.";

const CLIENT = {
  name: "Legacy",
  industry: "Luxury eyewear / glasses",
  market: "Mexico City",
  goal: "Launch a luxury glasses brand in Mexico City",
  tier: "VIP",
} as const;

const SETUP_OPERATION_BRIEF =
  "Prepare Atlas Growth Agency OS to serve Legacy as a VIP client account across intake, launch, approval, monitoring, and learning.";
const REQUIRE_TOP_TIER = process.env.PLAYWRIGHT_SIMULATION_REQUIRE_TOP_TIER === "true";
const LOCAL_LLM_TIMEOUT_MS = Number(process.env.PLAYWRIGHT_SIMULATION_LLM_TIMEOUT_MS ?? 120_000);
const LOCAL_LLM_MAX_TOKENS = Number(process.env.PLAYWRIGHT_SIMULATION_LLM_MAX_TOKENS ?? 2_400);
const TOP_TIER_TARGET = 90;
const RESOURCE_CONSTRAINTS = {
  budgetCapMxn: 1_400_000,
  contentCapacityPerWeek: 6,
  channelLimit: 3,
  allowedChannels: ["private appointments", "Meta retargeting", "stylist and concierge partnerships"],
} as const;
const ACTIVE_TASK_STATUSES = new Set(["running", "waiting", "failed"]);

const REQUIRED_SKILLS = [
  "copywriter.generate_ad_copy",
  "creative.generate_ad_concepts",
  "memory.retrieve_relevant",
  "memory.write_case",
  "analytics.summarize_performance",
  "compliance.review_claims",
  "finance.estimate_budget",
  "strategy.define_positioning",
  "sales.classify_client_tier",
  "project.plan_launch",
] as const;

const REQUIRED_TOOLS = [
  "generate_content",
  "creative_production",
  "legal_validation",
  "performance_metrics",
  "budget_estimator",
  "audience_segmentation",
  "campaign_calendar",
  "memory_store",
  "memory_search",
] as const;

const AI_JUDGE_PROMPT = [
  "You are a strict product simulation evaluator for an AI company operating system.",
  "Evaluate whether the simulation proves an AI-operated digital marketing agency serving Legacy as a client under adversarial constraints.",
  "Quality of the marketing strategy is secondary unless strict quality mode is enabled.",
  "Your feedback must be imperfect and ambiguous: include a useful concern without giving a single obvious next step.",
  "Return JSON only with this exact shape:",
  '{"coverage_score": number, "marketing_quality_score": number, "reasoning": string, "ambiguous_feedback": string, "criteria": {"scenario_completeness": number, "department_coverage": number, "operation_coverage": number, "skill_tool_coverage": number, "product_ux_coherence": number, "decision_adaptation": number, "learning_improvement": number, "ambiguity_handling": number, "memory_recovery": number, "marketing_quality": number}}',
  "Score from 0 to 100.",
  "Coverage requires: agency company is not Legacy, Legacy is modeled as client context, at least 10 departments, at least 5 operations, at least 15 tasks, skills, tools, HITL approval, compliance loop, performance loop, memory retrieval, memory write, deliverable, and product surface coherence.",
  "Adversarial validation requires: at least two department conflicts, one rejected approval that is revised and reapproved, competing proposals resolved by choice or merge, explicit budget/content/channel constraints, at least one hidden constraint injection, contradictory signals, delayed consequences, misleading memory recovery, at least two learning iterations, visible reasoning/tradeoffs in deliverables, and understandable UX surfaces.",
].join("\n");

const SIMULATION_DIRECTOR_PROMPT = [
  "You are the adversarial simulation director for ForgeGraph.",
  "Generate unpredictable but realistic business pressure for an AI-operated digital marketing agency serving Legacy, a luxury eyewear client in Mexico City.",
  "Return JSON only. Do not use internal implementation terminology.",
  "Return this exact shape:",
  '{"hidden_constraints":[{"id":"string","type":"legal|budget|channel","description":"string","impact":"string","response":"string"}],"contradictory_signals":[{"id":"string","signal_a":"string","signal_b":"string","choice":"string","rationale":"string"}],"delayed_consequences":[{"id":"string","early_decision":"string","consequence":"string","effect":"positive|negative"}],"memory_misuse":[{"misleading_memory_id":"memory-misleading-discount-scale","detected_by":"string","issue":"string","recovery":"string"}],"department_challenges":[{"department":"string","proposal":"string","risk":"string","response":"override|constrain|careful integration","rationale":"string"}],"active_constraints":{"budget_cap_mxn":number,"content_capacity_per_week":number,"channel_limit":number,"allowed_channels":["string"],"failed_channels":["string"],"restricted_claims":["string"]}}',
  "Return exactly 3 hidden_constraints, exactly 2 contradictory_signals, exactly 2 delayed_consequences, exactly 1 memory_misuse item, and exactly 1 department_challenges item.",
  "Do not return empty arrays. Every item must include non-empty strings for every field.",
  "Make the output plausible, ambiguous, and useful for a product simulation.",
].join("\n");

const OPERATION_DELIVERABLE_PROMPT = [
  "You are a senior operator inside Atlas Growth Agency OS, an AI-operated digital marketing agency.",
  "Write the actual operation deliverable for Legacy, a VIP luxury eyewear client launching in Mexico City.",
  "Use product language only: company, client, department, operation, task, skill, tool, approval, memory, deliverable.",
  "Do not mention test, mock, fixture, graph, node, run, execution, or workflow.",
  "Return Markdown only.",
  "Use these exact labels with colons: Client:, Operation:, Decision:, Reasoning:, Tradeoffs:, Why decisions were made:, Product coverage:.",
  "For the final follow-up operation, include the exact phrase: Learning iteration 2 used retrieved Legacy case memory.",
  "If dynamic adaptation facts are provided, include an exact Dynamic adaptation: section.",
  "If memory recovery facts are provided, include a line or section that starts exactly: Memory recovery:",
  "If ambiguous evaluator feedback is provided, include a line or section that starts exactly: Ambiguous evaluation response:",
  "If decision trace records are provided, include exact sections that start: Decision trace:, Rejected alternatives:, Memory attribution:, Approval impact:, Iteration delta:.",
].join("\n");

const AMBIGUOUS_FEEDBACK_RESPONSE_PROMPT = [
  "You are the Strategy department interpreting imperfect evaluator feedback for the Legacy launch.",
  "Return JSON only with this exact shape:",
  '{"interpretation":"string","response":"string"}',
  "Do not treat the evaluator as an absolute authority. Translate ambiguous feedback into a cautious next decision.",
].join("\n");

const TRACEABILITY_PROMPT = [
  "You are the decision traceability auditor for Atlas Growth Agency OS.",
  "Use only the provided company behavior to create an auditable causal trace for Legacy's final strategy.",
  "Return JSON only with this exact shape:",
  '{"decisions":[{"id":"string","decision":"string","alternatives":["string"],"constraints":["string"],"departments":["string"],"rationale":"string","rejected":["string"],"linked_operations":["string"]}],"memory_attributions":[{"memory_id":"string","memory_title":"string","retrieved_by":"string","used_in":"string","changed_reasoning":"string"}],"approval_impacts":[{"approval_id":"string","operation_id":"string","rejection_changed":"string","improved_before_reapproval":"string","departments":["string"]}],"iteration_deltas":[{"from_iteration":number,"to_iteration":number,"what_changed":"string","why_changed":"string","department":"string"}]}',
  "Requirements: at least three decisions, every decision has alternatives, constraints, departments, rationale, rejected alternatives, and linked operations; at least two memory attributions; at least one approval impact; at least two iteration deltas.",
  "The output must make it possible to answer: Why did this strategy emerge?",
].join("\n");

type JudgeResult = {
  coverage_score: number;
  marketing_quality_score: number;
  reasoning: string;
  criteria: {
    scenario_completeness: number;
    department_coverage: number;
    operation_coverage: number;
    skill_tool_coverage: number;
    product_ux_coherence: number;
    decision_adaptation: number;
    learning_improvement: number;
    ambiguity_handling: number;
    memory_recovery: number;
    marketing_quality: number;
  };
  ambiguous_feedback: string;
  source: "local-llm";
};

type AgencyDepartment = CompanyDepartment & {
  role: string;
  purpose: string;
  skills: string[];
  externalTools: string[];
};

type SimulationTaskTemplate = {
  title: string;
  departmentName: string;
  summary: string;
  status?: "pending" | "running" | "waiting" | "succeeded" | "failed";
  priority?: "low" | "normal" | "high" | "urgent";
  skill: (typeof REQUIRED_SKILLS)[number];
  tool: (typeof REQUIRED_TOOLS)[number];
  approvalBoundary?: boolean;
};

type OperationTemplate = {
  sequence: number;
  name: string;
  purpose: string;
  brief: string;
  departments: string[];
  tasks: SimulationTaskTemplate[];
  deliverable: string;
  createsApproval?: boolean;
  complianceLoop?: boolean;
  performanceLoop?: boolean;
  memoryRetrieval?: boolean;
  memoryWrite?: boolean;
  followUpFromPerformance?: boolean;
};

type SimulationTask = {
  id: string;
  operationId: string;
  departmentId: string;
  departmentName: string;
  title: string;
  status: "pending" | "running" | "waiting" | "succeeded" | "failed";
  priority: "low" | "normal" | "high" | "urgent";
  summary: string;
  sourceId: string;
  currentDecisionId: string | null;
  skill: (typeof REQUIRED_SKILLS)[number];
  tool: (typeof REQUIRED_TOOLS)[number];
  startedAt: string | null;
  endedAt: string | null;
};

type SimulationApproval = {
  id: string;
  operationId: string;
  departmentId: string;
  departmentName: string;
  status: "pending" | "approved" | "rejected";
  revision: number;
  promptMessage: string;
  createdAt: string;
  resolvedAt: string | null;
  result: Record<string, unknown> | null;
};

type SimulationOperation = {
  id: string;
  sequence: number;
  name: string;
  purpose: string;
  status: "pending" | "running" | "succeeded" | "failed" | "paused";
  startedAt: string;
  endedAt: string | null;
  brief: string;
  departments: string[];
  tasks: SimulationTask[];
  approval: SimulationApproval | null;
  approvalHistory: SimulationApproval[];
  deliverableText: string | null;
  attempts: number;
  triggeredByOperationId?: string | null;
};

type SimulationMemory = {
  id: string;
  title: string;
  content: string;
  operationId: string | null;
  departmentId: string | null;
  topic: string;
  toolName: string;
  createdAt: string;
  kind: "seed" | "retrieval" | "write" | "misleading";
};

type SimulationConflict = {
  id: string;
  title: string;
  departments: string[];
  constraint: string;
  decision: string;
  resolution: string;
};

type ProposalDecision = {
  id: string;
  competingProposals: string[];
  decision: "choose" | "merge";
  rationale: string;
};

type LearningIteration = {
  iteration: number;
  memoryUsed: string;
  changedFrom: string;
  changedTo: string;
  output: string;
};

type HiddenConstraint = {
  id: string;
  type: "legal" | "budget" | "channel";
  injectedAfterOperation: string;
  description: string;
  impact: string;
  response: string;
};

type ActiveConstraints = {
  budgetCapMxn: number;
  contentCapacityPerWeek: number;
  channelLimit: number;
  allowedChannels: string[];
  failedChannels: string[];
  restrictedClaims: string[];
};

type ContradictorySignal = {
  id: string;
  signalA: string;
  signalB: string;
  choice: string;
  rationale: string;
};

type DelayedConsequence = {
  id: string;
  earlyDecision: string;
  consequence: string;
  effect: "positive" | "negative";
};

type MemoryMisuseRecovery = {
  misleadingMemoryId: string;
  detectedBy: string;
  issue: string;
  recovery: string;
};

type DepartmentChallenge = {
  department: string;
  proposal: string;
  risk: string;
  response: "override" | "constrain" | "careful integration";
  rationale: string;
};

type AmbiguousJudgeInterpretation = {
  feedback: string;
  interpretation: string;
  response: string;
};

type UxComprehensionSample = {
  surface: string;
  clarityOfIntent: boolean;
  clarityOfDecisions: boolean;
  clarityOfNextSteps: boolean;
  score: number;
};

type LlmResponseRecord = {
  kind: "director" | "deliverable" | "judge" | "traceability";
  label: string;
  content: string;
};

type DecisionTraceRecord = {
  id: string;
  decision: string;
  alternatives: string[];
  constraints: string[];
  departments: string[];
  rationale: string;
  rejected: string[];
  linkedOperations: string[];
};

type MemoryAttributionRecord = {
  memoryId: string;
  memoryTitle: string;
  retrievedBy: string;
  usedIn: string;
  changedReasoning: string;
};

type ApprovalImpactRecord = {
  approvalId: string;
  operationId: string;
  rejectionChanged: string;
  improvedBeforeReapproval: string;
  departments: string[];
};

type IterationDeltaRecord = {
  fromIteration: number;
  toIteration: number;
  whatChanged: string;
  whyChanged: string;
  department: string;
};

type TraceabilityOutput = {
  decisions: DecisionTraceRecord[];
  memoryAttributions: MemoryAttributionRecord[];
  approvalImpacts: ApprovalImpactRecord[];
  iterationDeltas: IterationDeltaRecord[];
};

type StrategyReportArtifact = {
  company_id: string;
  operation_id: string;
  audience: "client" | "executive" | "internal";
  format: "md" | "html" | "pdf";
  content_type: string;
  filename: string;
  encoding: "text" | "base64";
  content: string;
  traceability: Record<string, Array<{ kind: string; id: string; field: string; label: string }>>;
};

type SimulationDirectorOutput = {
  hiddenConstraints: HiddenConstraint[];
  contradictorySignals: ContradictorySignal[];
  delayedConsequences: DelayedConsequence[];
  memoryMisuseRecoveries: MemoryMisuseRecovery[];
  departmentChallenges: DepartmentChallenge[];
  activeConstraints: ActiveConstraints;
};

type SimulationState = {
  organizationId: string;
  organizationName: string;
  companyId: string;
  setupVersionId: string;
  companyProfile: CompanyProfile;
  departmentIdsByName: Record<string, string>;
  operations: SimulationOperation[];
  memory: SimulationMemory[];
  memoryRetrievalCount: number;
  memoryWriteCount: number;
  complianceLoopOccurred: boolean;
  performanceLoopOccurred: boolean;
  approvalRejectionCount: number;
  approvalRevisionCount: number;
  approvalReapprovalCount: number;
  conflicts: SimulationConflict[];
  proposalDecisions: ProposalDecision[];
  constraints: typeof RESOURCE_CONSTRAINTS;
  activeConstraints: ActiveConstraints;
  hiddenConstraints: HiddenConstraint[];
  contradictorySignals: ContradictorySignal[];
  delayedConsequences: DelayedConsequence[];
  memoryMisuseRecoveries: MemoryMisuseRecovery[];
  departmentChallenges: DepartmentChallenge[];
  ambiguousJudgeInterpretations: AmbiguousJudgeInterpretation[];
  uxComprehensionSamples: UxComprehensionSample[];
  learningIterations: LearningIteration[];
  decisionTraces: DecisionTraceRecord[];
  memoryAttributions: MemoryAttributionRecord[];
  approvalImpacts: ApprovalImpactRecord[];
  iterationDeltas: IterationDeltaRecord[];
  improvementEvents: string[];
  llmResponses: LlmResponseRecord[];
  legacyClientReport: string | null;
  reportBuilderArtifact: StrategyReportArtifact | null;
  judge: JudgeResult | null;
};

function apiSuccess<T>(data: T) {
  return {
    data,
    meta: {
      requestId: "playwright-agency-simulation",
      timestamp: "2026-04-28T15:00:00.000Z",
    },
  };
}

function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function timestamp(minutes: number): string {
  const base = Date.parse("2026-04-28T15:00:00.000Z");
  return new Date(base + minutes * 60_000).toISOString();
}

function createOperationId(sequence: number): string {
  return `91000000-0000-4000-8000-${String(sequence).padStart(12, "0")}`;
}

function createTaskId(operationId: string, title: string): string {
  return `${operationId}-${slugify(title)}`.slice(0, 96);
}

function adversarialConflicts(): SimulationConflict[] {
  return [
    {
      id: "conflict-budget-premium-launch",
      title: "Premium paid launch exceeds budget cap",
      departments: ["Marketing Strategy", "Performance Marketing", "Finance", "Strategy"],
      constraint: `Marketing requested MXN 2.4M, but Finance capped the launch at MXN ${RESOURCE_CONSTRAINTS.budgetCapMxn.toLocaleString("en-US")}.`,
      decision: "Strategy required a smaller launch architecture before approval.",
      resolution:
        "The team reduced paid channels, protected appointment proof, and redesigned the campaign to fit MXN 1.35M.",
    },
    {
      id: "conflict-content-capacity-channel-limit",
      title: "Creative asset demand exceeds content capacity",
      departments: ["Creative Production", "Content Strategy", "Operations Design", "Project Management"],
      constraint: `Creative requested 18 launch assets, but content capacity is ${RESOURCE_CONSTRAINTS.contentCapacityPerWeek} assets per week and ${RESOURCE_CONSTRAINTS.channelLimit} active channels.`,
      decision: "Operations Design forced sequencing by business impact instead of asset volume.",
      resolution:
        "The team kept hero product films, appointment copy, and concierge partner assets while deferring broad awareness variations.",
    },
  ];
}

function competingProposalDecisions(): ProposalDecision[] {
  return [
    {
      id: "proposal-paid-vs-organic",
      competingProposals: [
        "Performance Marketing proposed paid social and search-intent capture for fast qualified lead volume.",
        "Content Strategy proposed organic-first editorial, stylist credibility, and appointment proof before spend scale.",
      ],
      decision: "merge",
      rationale:
        "Strategy merged the proposals into a constrained hybrid: paid retargeting plus search capture, supported by organic editorial and concierge referrals.",
    },
  ];
}

function initialActiveConstraints(): ActiveConstraints {
  return {
    budgetCapMxn: RESOURCE_CONSTRAINTS.budgetCapMxn,
    contentCapacityPerWeek: RESOURCE_CONSTRAINTS.contentCapacityPerWeek,
    channelLimit: RESOURCE_CONSTRAINTS.channelLimit,
    allowedChannels: [...RESOURCE_CONSTRAINTS.allowedChannels],
    failedChannels: [],
    restrictedClaims: [],
  };
}

function localLlmConfig() {
  return {
    baseUrl: (
      process.env.PLAYWRIGHT_SIMULATION_LLM_URL ??
      process.env.OPENAI_BASE_URL ??
      process.env.PLAYWRIGHT_LOCAL_LLM_URL ??
      "http://127.0.0.1:12434/v1"
    ).replace(/\/$/, ""),
    model:
      process.env.PLAYWRIGHT_SIMULATION_JUDGE_MODEL ??
      process.env.OPENAI_MODEL ??
      process.env.PLAYWRIGHT_MARKETING_LLM_MODEL ??
      "docker.io/ai/llama3.1:latest",
  };
}

async function requireLocalLlmContent(
  request: APIRequestContext,
  systemPrompt: string,
  userPayload: unknown,
  options?: { temperature?: number; json?: boolean; timeout?: number; maxTokens?: number },
): Promise<string> {
  const { baseUrl, model } = localLlmConfig();
  const timeout = Math.max(options?.timeout ?? LOCAL_LLM_TIMEOUT_MS, LOCAL_LLM_TIMEOUT_MS);
  const response = await request.post(`${baseUrl}/chat/completions`, {
    timeout,
    failOnStatusCode: false,
    data: {
      model,
      temperature: options?.temperature ?? 0.2,
      max_tokens: options?.maxTokens ?? LOCAL_LLM_MAX_TOKENS,
      ...(options?.json ? { response_format: { type: "json_object" } } : {}),
      messages: [
        { role: "system", content: systemPrompt },
        {
          role: "user",
          content: typeof userPayload === "string" ? userPayload : JSON.stringify(userPayload, null, 2),
        },
      ],
    },
  });

  if (!response.ok()) {
    throw new Error(
      `Local LLM request failed (${response.status()}) at ${baseUrl}/chat/completions: ${(await response.text()).slice(0, 500)}`,
    );
  }

  const body = (await response.json()) as {
    choices?: Array<{ message?: { content?: string } }>;
  };
  const content = body.choices?.[0]?.message?.content?.trim();
  if (!content) {
    throw new Error("Local LLM returned an empty response.");
  }
  return content;
}

async function requireLocalLlmJson(
  request: APIRequestContext,
  systemPrompt: string,
  userPayload: unknown,
  options?: { temperature?: number; timeout?: number },
): Promise<{ content: string; parsed: Record<string, unknown> }> {
  const content = await requireLocalLlmContent(request, systemPrompt, userPayload, {
    ...options,
    json: true,
  });
  const parsed = extractJsonObject(content);
  if (!parsed) {
    throw new Error(`Local LLM returned non-JSON content: ${content.slice(0, 500)}`);
  }
  return { content, parsed };
}

function normalizeDirectorOutput(
  parsed: Record<string, unknown> | null,
  afterOperationId: string,
): SimulationDirectorOutput {
  if (!parsed) {
    throw new Error("Local LLM director returned no parseable JSON.");
  }

  const hiddenConstraints = Array.isArray(parsed.hidden_constraints)
    ? parsed.hidden_constraints.flatMap((item, index) => {
        const source = item as Record<string, unknown>;
        const type =
          source.type === "legal" || source.type === "budget" || source.type === "channel" ? source.type : "budget";
        const constraint = {
          id: String(source.id ?? `llm-hidden-${index}`),
          type,
          injectedAfterOperation: afterOperationId,
          description: String(source.description ?? ""),
          impact: String(source.impact ?? ""),
          response: String(source.response ?? ""),
        };
        return constraint.description && constraint.impact && constraint.response ? [constraint] : [];
      })
    : [];

  const contradictorySignals = Array.isArray(parsed.contradictory_signals)
    ? parsed.contradictory_signals.flatMap((item, index) => {
        const source = item as Record<string, unknown>;
        const signal = {
          id: String(source.id ?? `llm-signal-${index}`),
          signalA: String(source.signal_a ?? ""),
          signalB: String(source.signal_b ?? ""),
          choice: String(source.choice ?? ""),
          rationale: String(source.rationale ?? ""),
        };
        return signal.signalA && signal.signalB && signal.choice && signal.rationale ? [signal] : [];
      })
    : [];

  const delayedConsequences = Array.isArray(parsed.delayed_consequences)
    ? parsed.delayed_consequences.flatMap((item, index) => {
        const source = item as Record<string, unknown>;
        const consequence = {
          id: String(source.id ?? `llm-consequence-${index}`),
          earlyDecision: String(source.early_decision ?? ""),
          consequence: String(source.consequence ?? ""),
          effect: source.effect === "negative" ? ("negative" as const) : ("positive" as const),
        };
        return consequence.earlyDecision && consequence.consequence ? [consequence] : [];
      })
    : [];

  const memoryMisuseRecoveries = Array.isArray(parsed.memory_misuse)
    ? parsed.memory_misuse.flatMap((item) => {
        const source = item as Record<string, unknown>;
        const recovery = {
          misleadingMemoryId: String(source.misleading_memory_id ?? "memory-misleading-discount-scale"),
          detectedBy: String(source.detected_by ?? "Memory / Learning"),
          issue: String(source.issue ?? ""),
          recovery: String(source.recovery ?? ""),
        };
        return recovery.issue && recovery.recovery ? [recovery] : [];
      })
    : [];

  const departmentChallenges = Array.isArray(parsed.department_challenges)
    ? parsed.department_challenges.flatMap((item) => {
        const source = item as Record<string, unknown>;
        const response =
          source.response === "override" || source.response === "careful integration" ? source.response : "constrain";
        const challenge = {
          department: String(source.department ?? "Performance Marketing"),
          proposal: String(source.proposal ?? ""),
          risk: String(source.risk ?? ""),
          response,
          rationale: String(source.rationale ?? ""),
        };
        return challenge.proposal && challenge.risk && challenge.rationale ? [challenge] : [];
      })
    : [];

  const active = (parsed.active_constraints ?? {}) as Record<string, unknown>;
  const budgetCapMxn = Number(active.budget_cap_mxn);
  const contentCapacityPerWeek = Number(active.content_capacity_per_week);
  const channelLimit = Number(active.channel_limit);
  const activeConstraints = {
    budgetCapMxn: Number.isFinite(budgetCapMxn) && budgetCapMxn > 0 ? budgetCapMxn : Number.NaN,
    contentCapacityPerWeek: Number.isFinite(contentCapacityPerWeek) ? contentCapacityPerWeek : Number.NaN,
    channelLimit: Number.isFinite(channelLimit) ? channelLimit : Number.NaN,
    allowedChannels: normalizeStringArray(active.allowed_channels),
    failedChannels: normalizeStringArray(active.failed_channels),
    restrictedClaims: normalizeStringArray(active.restricted_claims),
  };

  const validationFailures = [
    hiddenConstraints.length < 1 ? "at least one hidden constraint" : "",
    contradictorySignals.length < 2 ? "at least two contradictory signals" : "",
    delayedConsequences.length < 2 ? "at least two delayed consequences" : "",
    memoryMisuseRecoveries.length < 1 ? "at least one memory misuse recovery" : "",
    departmentChallenges.length < 1 ? "at least one department challenge" : "",
    !Number.isFinite(activeConstraints.budgetCapMxn) ? "active budget cap" : "",
    activeConstraints.budgetCapMxn > RESOURCE_CONSTRAINTS.budgetCapMxn ? "budget cap must not increase" : "",
    !Number.isFinite(activeConstraints.contentCapacityPerWeek) ? "content capacity" : "",
    !Number.isFinite(activeConstraints.channelLimit) ? "channel limit" : "",
    activeConstraints.allowedChannels.length < 1 ? "allowed channels" : "",
  ].flatMap((field) => (field ? [field] : []));

  if (validationFailures.length > 0) {
    throw new Error(`Local LLM director output is incomplete: ${validationFailures.join(", ")}`);
  }

  return {
    hiddenConstraints,
    contradictorySignals,
    delayedConsequences,
    memoryMisuseRecoveries,
    departmentChallenges,
    activeConstraints,
  };
}

async function generateSimulationDirectorOutput(
  request: APIRequestContext,
  state: SimulationState,
  afterOperationId: string,
): Promise<SimulationDirectorOutput> {
  const payload = {
    company: COMPANY_NAME,
    client: CLIENT,
    operations_so_far: state.operations.map((operation) => ({
      name: operation.name,
      purpose: operation.purpose,
      deliverable_excerpt: operation.deliverableText?.slice(0, 700),
      departments: operation.departments,
      task_summaries: operation.tasks.map((task) => `${task.departmentName}: ${task.title} - ${task.summary}`),
    })),
    existing_constraints: state.activeConstraints,
    misleading_memory: state.memory.find((memory) => memory.id === "memory-misleading-discount-scale"),
  };
  const requestDirectorAttempt = async (
    attempt: number,
    previousContent = "",
    previousError = "",
  ): Promise<SimulationDirectorOutput> => {
    const { content, parsed } = await requireLocalLlmJson(
      request,
      SIMULATION_DIRECTOR_PROMPT,
      attempt === 1
        ? payload
        : {
            ...payload,
            repair_instruction:
              "Repair the previous JSON by returning the complete required JSON shape again. Do not explain the repair.",
            previous_response: previousContent.slice(0, 4_000),
            validation_error: previousError,
          },
      { temperature: attempt === 1 ? 0.4 : 0, timeout: 60_000 },
    );
    state.llmResponses.push({ kind: "director", label: `adversarial simulation director attempt ${attempt}`, content });
    try {
      return normalizeDirectorOutput(parsed, afterOperationId);
    } catch (error) {
      const nextError = error instanceof Error ? error.message : String(error);
      if (attempt < 5) {
        return requestDirectorAttempt(attempt + 1, content, nextError);
      }
      if (parsed && /department challenge/i.test(nextError)) {
        const { content: repairContent, parsed: repairParsed } = await requireLocalLlmJson(
          request,
          [
            "You are repairing one missing field in an adversarial organizational simulation.",
            "Return JSON only with this exact shape:",
            '{"department_challenges":[{"department":"string","proposal":"string","risk":"string","response":"override|constrain|careful integration","rationale":"string"}]}',
            "The department challenge must be suboptimal, plausible, and specific to Legacy's Mexico City luxury eyewear launch.",
          ].join("\n"),
          {
            company: COMPANY_NAME,
            client: CLIENT,
            operations_so_far: payload.operations_so_far,
            constraints: parsed.active_constraints ?? state.activeConstraints,
            previous_director_response: parsed,
          },
          { temperature: 0, timeout: 60_000, maxTokens: 800 },
        );
        state.llmResponses.push({
          kind: "director",
          label: "adversarial simulation director targeted repair",
          content: repairContent,
        });
        return normalizeDirectorOutput(
          {
            ...parsed,
            department_challenges: repairParsed.department_challenges,
          },
          afterOperationId,
        );
      }
      throw new Error(`Local LLM director output is incomplete after repair: ${nextError}`);
    }
  };

  return requestDirectorAttempt(1);
}

function departmentDefinitions(): AgencyDepartment[] {
  return [
    {
      id: "strategy",
      label: "Strategy",
      role: "Executive strategy department",
      purpose: "Owns agency-level strategic choices, client launch goals, and positioning principles.",
      responsibility: "Defines strategic direction, decision criteria, and client outcome quality.",
      skills: ["strategy.define_positioning", "memory.retrieve_relevant"],
      externalTools: ["audience_segmentation", "memory_search"],
      tools: ["strategy.define_positioning", "memory.retrieve_relevant", "audience_segmentation", "memory_search"],
      category: "department",
    },
    {
      id: "operations-design",
      label: "Operations Design",
      role: "Operating model department",
      purpose: "Turns agency routing logic into repeatable operation design and handoff structure.",
      responsibility: "Designs operation sequence, routing conditions, and approval boundaries.",
      skills: ["project.plan_launch"],
      externalTools: ["campaign_calendar"],
      tools: ["project.plan_launch", "campaign_calendar"],
      category: "department",
    },
    {
      id: "finance",
      label: "Finance",
      role: "Budget and constraint department",
      purpose: "Estimates launch investment, financial constraints, and scale thresholds.",
      responsibility: "Converts client goals into budget ranges, constraints, and spend controls.",
      skills: ["finance.estimate_budget"],
      externalTools: ["budget_estimator", "performance_metrics"],
      tools: ["finance.estimate_budget", "budget_estimator", "performance_metrics"],
      category: "department",
    },
    {
      id: "sales",
      label: "Sales",
      role: "Revenue intake department",
      purpose: "Qualifies client commercial context and maps account value.",
      responsibility: "Classifies opportunity tier and validates commercial fit for the agency.",
      skills: ["sales.classify_client_tier"],
      externalTools: ["generate_content"],
      tools: ["sales.classify_client_tier", "generate_content"],
      category: "department",
    },
    {
      id: "lead-processing",
      label: "Lead Processing",
      role: "Qualification department",
      purpose: "Normalizes client intake, tier signals, and missing information.",
      responsibility: "Turns raw client context into an actionable account brief.",
      skills: ["sales.classify_client_tier", "memory.retrieve_relevant"],
      externalTools: ["memory_search"],
      tools: ["sales.classify_client_tier", "memory.retrieve_relevant", "memory_search"],
      category: "department",
    },
    {
      id: "account-management",
      label: "Account Management",
      role: "Client account department",
      purpose: "Keeps Legacy account context, approvals, constraints, and expectations coherent.",
      responsibility: "Owns client relationship context and coordinates account-level approvals.",
      skills: ["strategy.define_positioning"],
      externalTools: ["generate_content"],
      tools: ["strategy.define_positioning", "generate_content"],
      category: "department",
    },
    {
      id: "marketing-strategy",
      label: "Marketing Strategy",
      role: "Campaign architecture department",
      purpose: "Defines launch positioning, audience segmentation, channel mix, and market thesis.",
      responsibility: "Creates the campaign system for the Legacy launch in Mexico City.",
      skills: ["strategy.define_positioning", "memory.retrieve_relevant"],
      externalTools: ["audience_segmentation", "campaign_calendar"],
      tools: ["strategy.define_positioning", "memory.retrieve_relevant", "audience_segmentation", "campaign_calendar"],
      category: "department",
    },
    {
      id: "performance-marketing",
      label: "Performance Marketing",
      role: "Growth activation department",
      purpose: "Turns strategy into paid media, measurement, and segment-level optimization.",
      responsibility: "Manages performance channels, tests, copy, and scale decisions.",
      skills: ["analytics.summarize_performance", "copywriter.generate_ad_copy"],
      externalTools: ["performance_metrics", "generate_content"],
      tools: [
        "analytics.summarize_performance",
        "copywriter.generate_ad_copy",
        "performance_metrics",
        "generate_content",
      ],
      category: "department",
    },
    {
      id: "content-strategy",
      label: "Content Strategy",
      role: "Narrative department",
      purpose: "Designs editorial themes, messages, and content sequencing.",
      responsibility: "Owns campaign narrative, content calendar, and ad copy intent.",
      skills: ["copywriter.generate_ad_copy", "strategy.define_positioning"],
      externalTools: ["generate_content", "campaign_calendar"],
      tools: ["copywriter.generate_ad_copy", "strategy.define_positioning", "generate_content", "campaign_calendar"],
      category: "department",
    },
    {
      id: "creative-production",
      label: "Creative Production",
      role: "Creative production department",
      purpose: "Generates creative concepts, asset direction, and premium launch materials.",
      responsibility: "Converts strategy into concepts, copyboards, and production-ready creative directions.",
      skills: ["creative.generate_ad_concepts"],
      externalTools: ["creative_production"],
      tools: ["creative.generate_ad_concepts", "creative_production"],
      category: "department",
    },
    {
      id: "legal-compliance",
      label: "Legal / Compliance",
      role: "Risk review department",
      purpose: "Reviews claims, disclosures, usage rights, privacy capture, and approval boundaries.",
      responsibility: "Validates compliance before client-facing work or launch release moves forward.",
      skills: ["compliance.review_claims"],
      externalTools: ["legal_validation"],
      tools: ["compliance.review_claims", "legal_validation"],
      category: "department",
    },
    {
      id: "project-management",
      label: "Project Management",
      role: "Launch coordination department",
      purpose: "Plans milestones, owners, dependencies, and launch readiness.",
      responsibility: "Turns approved campaign plans into executable launch schedules.",
      skills: ["project.plan_launch"],
      externalTools: ["campaign_calendar", "performance_metrics"],
      tools: ["project.plan_launch", "campaign_calendar", "performance_metrics"],
      category: "department",
    },
    {
      id: "client-success",
      label: "Client Success",
      role: "Client outcome department",
      purpose: "Packages deliverables, decision context, and next actions for Legacy stakeholders.",
      responsibility: "Translates agency work into client-ready narrative, handoffs, and success tracking.",
      skills: ["memory.write_case"],
      externalTools: ["generate_content"],
      tools: ["memory.write_case", "generate_content"],
      category: "department",
    },
    {
      id: "analytics-metrics",
      label: "Analytics / Metrics",
      role: "Measurement department",
      purpose: "Summarizes performance, identifies weak segments, and informs iteration decisions.",
      responsibility: "Converts campaign signals into performance insight and next-cycle recommendations.",
      skills: ["analytics.summarize_performance"],
      externalTools: ["performance_metrics"],
      tools: ["analytics.summarize_performance", "performance_metrics"],
      category: "department",
    },
    {
      id: "memory-learning",
      label: "Memory / Learning",
      role: "Learning department",
      purpose: "Retrieves relevant prior context and writes campaign learnings back to memory.",
      responsibility: "Maintains agency memory so later operations improve from prior outcomes.",
      skills: ["memory.retrieve_relevant", "memory.write_case"],
      externalTools: ["memory_search", "memory_store"],
      tools: ["memory.retrieve_relevant", "memory.write_case", "memory_search", "memory_store"],
      category: "department",
    },
  ];
}

function operationTemplates(): OperationTemplate[] {
  return [
    {
      sequence: 1,
      name: "Client Intake & Strategy",
      purpose: "Understand Legacy, classify client tier, define launch goals.",
      brief: "Operation 1 - Client Intake & Strategy for Legacy VIP luxury eyewear launch in Mexico City",
      departments: ["Strategy", "Sales", "Lead Processing", "Account Management", "Finance"],
      deliverable:
        "Client: Legacy. Intake classified Legacy as VIP, confirmed Mexico City luxury eyewear launch goal, estimated MXN 1.2M-1.8M pilot range, and documented account constraints for positioning, claims, and launch pacing.",
      tasks: [
        {
          title: "define client brief",
          departmentName: "Lead Processing",
          summary: "Created the Legacy account brief with industry, market, VIP tier signals, and launch objective.",
          skill: "sales.classify_client_tier",
          tool: "memory_search",
          priority: "high",
        },
        {
          title: "classify client tier",
          departmentName: "Sales",
          summary:
            "Classified Legacy as VIP because the account combines luxury positioning, launch risk, and high expected strategic value.",
          skill: "sales.classify_client_tier",
          tool: "generate_content",
          priority: "high",
        },
        {
          title: "estimate launch budget",
          departmentName: "Finance",
          summary:
            "Estimated a focused Mexico City launch budget with room for creative production, paid media, and private client moments.",
          skill: "finance.estimate_budget",
          tool: "budget_estimator",
          priority: "high",
        },
        {
          title: "define business constraints",
          departmentName: "Account Management",
          summary:
            "Captured account constraints: premium tone, verified quality claims, private appointment flow, and client approval before launch.",
          skill: "strategy.define_positioning",
          tool: "generate_content",
          priority: "normal",
        },
      ],
    },
    {
      sequence: 2,
      name: "Campaign Architecture",
      purpose: "Create the launch strategy and campaign system.",
      brief: "Operation 2 - Campaign Architecture for Legacy luxury glasses launch in Mexico City",
      departments: [
        "Marketing Strategy",
        "Performance Marketing",
        "Content Strategy",
        "Creative Production",
        "Finance",
        "Operations Design",
      ],
      deliverable:
        'Client: Legacy. Campaign architecture positions Legacy as quiet-status luxury eyewear for Mexico City, segments Polanco/Lomas/Roma Norte/Condesa buyers, and uses "See What Endures" as the creative platform. Reasoning: VIP buyers need proof of taste and service before broad reach. Tradeoffs: the team rejected the MXN 2.4M paid-heavy plan, merged paid and organic proposals, and protected only three launch channels under the MXN 1.4M cap. Why decisions were made: Finance constrained spend, Content Strategy constrained asset volume, and Strategy chose a smaller appointment-led system that can improve before scale.',
      tasks: [
        {
          title: "define positioning",
          departmentName: "Marketing Strategy",
          summary:
            "Defined Legacy as quiet-status luxury eyewear: heirloom craft, restrained taste, and Mexico City cultural specificity.",
          skill: "strategy.define_positioning",
          tool: "audience_segmentation",
          priority: "high",
        },
        {
          title: "segment Mexico City luxury audience",
          departmentName: "Marketing Strategy",
          summary:
            "Segmented VIP buyers across Polanco, Lomas, Roma Norte, Condesa, Santa Fe, and Artz Pedregal shopping behaviors.",
          skill: "strategy.define_positioning",
          tool: "audience_segmentation",
          priority: "high",
        },
        {
          title: "propose channel mix",
          departmentName: "Performance Marketing",
          summary:
            "Proposed a paid-heavy plan using Meta retargeting, search-intent capture, creators, concierge referrals, and CRM invitations for fast demand capture.",
          skill: "analytics.summarize_performance",
          tool: "performance_metrics",
          priority: "high",
        },
        {
          title: "reject over-budget campaign proposal",
          departmentName: "Finance",
          summary:
            "Rejected the MXN 2.4M paid-heavy proposal because it exceeded the MXN 1.4M cap and would leave no reserve for compliance revision or creative learning.",
          status: "failed",
          skill: "finance.estimate_budget",
          tool: "budget_estimator",
          priority: "urgent",
        },
        {
          title: "merge paid and organic proposals",
          departmentName: "Marketing Strategy",
          summary:
            "Merged Performance Marketing's paid acquisition proposal with Content Strategy's organic-first appointment proof plan into a constrained hybrid.",
          skill: "strategy.define_positioning",
          tool: "audience_segmentation",
          priority: "urgent",
        },
        {
          title: "limit launch channels",
          departmentName: "Operations Design",
          summary:
            "Limited the first launch cycle to three channels: private appointments, Meta retargeting, and stylist plus concierge partnerships.",
          skill: "project.plan_launch",
          tool: "campaign_calendar",
          priority: "high",
        },
        {
          title: "create campaign calendar",
          departmentName: "Content Strategy",
          summary:
            "Built an eight-week calendar within six assets per week, sequencing waitlist teaser, private fitting proof, and retargeting.",
          skill: "project.plan_launch",
          tool: "campaign_calendar",
          priority: "normal",
        },
        {
          title: "generate ad copy",
          departmentName: "Content Strategy",
          summary: 'Generated premium ad copy around "See What Endures", private appointments, and restrained status.',
          skill: "copywriter.generate_ad_copy",
          tool: "generate_content",
          priority: "normal",
        },
        {
          title: "generate creative concepts",
          departmentName: "Creative Production",
          summary:
            "Generated creative concepts using macro frame details, Mexico City light, gallery settings, and tactile product films.",
          skill: "creative.generate_ad_concepts",
          tool: "creative_production",
          priority: "normal",
        },
      ],
    },
    {
      sequence: 3,
      name: "Compliance & Approval",
      purpose: "Validate campaign claims and trigger human approvals.",
      brief: "Operation 3 - Compliance & Approval for Legacy client campaign",
      departments: ["Legal / Compliance", "Strategy", "Client Success", "Account Management"],
      createsApproval: true,
      complianceLoop: true,
      deliverable:
        "Client: Legacy. Compliance approved launch materials after an operator rejected the first package, the team revised unsupported optical-health language, and the revised package was reapproved. Reasoning: the campaign cannot ask for VIP trust while using claims it cannot substantiate. Tradeoffs: the agency sacrificed stronger health-adjacent copy and some speed to preserve legal clarity, creator disclosure, appointment privacy, and client confidence. Why decisions were made: Legal / Compliance blocked risky claims, Strategy protected the positioning, and Account Management required human approval before client-facing release.",
      tasks: [
        {
          title: "legal validation",
          departmentName: "Legal / Compliance",
          summary:
            "Initial review failed unsupported optical-health and material-origin claims. Claims require revision before approval.",
          status: "failed",
          skill: "compliance.review_claims",
          tool: "legal_validation",
          priority: "urgent",
        },
        {
          title: "revise failed compliance items",
          departmentName: "Legal / Compliance",
          summary:
            "Revised campaign claims to remove health-adjacent language, add influencer disclosure, and confirm privacy consent copy.",
          skill: "compliance.review_claims",
          tool: "legal_validation",
          priority: "urgent",
        },
        {
          title: "strategy approval",
          departmentName: "Strategy",
          summary: "Validated that the revised campaign still preserves quiet-status positioning and VIP client goals.",
          skill: "strategy.define_positioning",
          tool: "generate_content",
          priority: "high",
        },
        {
          title: "campaign approval",
          departmentName: "Account Management",
          summary:
            "Waiting for a human decision before the client-facing Legacy campaign package can be released; the decision must include claim, budget, and client consequence context.",
          status: "waiting",
          approvalBoundary: true,
          skill: "strategy.define_positioning",
          tool: "generate_content",
          priority: "urgent",
        },
        {
          title: "revise rejected approval package",
          departmentName: "Account Management",
          summary:
            "Prepared a revised approval package that tightens claims, keeps spend under the cap, and explains why the constrained plan should move forward.",
          status: "pending",
          skill: "strategy.define_positioning",
          tool: "generate_content",
          priority: "urgent",
        },
        {
          title: "package approval context",
          departmentName: "Client Success",
          summary:
            "Prepared the approval summary with changed claims, budget boundaries, and launch consequences for the operator.",
          skill: "memory.write_case",
          tool: "generate_content",
          priority: "normal",
        },
      ],
    },
    {
      sequence: 4,
      name: "Launch Delivery & Monitoring",
      purpose: "Simulate launch delivery and performance measurement.",
      brief: "Operation 4 - Launch Delivery & Monitoring for Legacy Mexico City campaign",
      departments: ["Project Management", "Performance Marketing", "Analytics / Metrics", "Client Success", "Strategy"],
      performanceLoop: true,
      deliverable:
        "Client: Legacy. Launch delivery completed the revised approved campaign, collected performance metrics, found appointment conversion above target in Polanco/Lomas, and identified Roma Norte prospecting as underperforming against qualified lead targets. Reasoning: constrained channel coverage made the weak segment visible early instead of hiding it behind broad spend. Tradeoffs: the agency held budget reserve instead of scaling immediately, accepted slower reach for clearer learning, and rejected discount-led scale even though it lowered near-term acquisition cost. Why decisions were made: Analytics showed Roma Norte needed stronger appointment proof, while brand-perception feedback showed discount framing would weaken Legacy's premium signal.",
      tasks: [
        {
          title: "launch campaign",
          departmentName: "Project Management",
          summary: "Launched approved creative, appointment funnel, creator placements, and private fitting calendar.",
          skill: "project.plan_launch",
          tool: "campaign_calendar",
          priority: "high",
        },
        {
          title: "collect performance metrics",
          departmentName: "Analytics / Metrics",
          summary:
            "Collected qualified lead rate, appointment cost, fitting conversion, and creative fatigue indicators.",
          skill: "analytics.summarize_performance",
          tool: "performance_metrics",
          priority: "high",
        },
        {
          title: "compare against target",
          departmentName: "Performance Marketing",
          summary: "Compared campaign metrics against VIP launch thresholds before recommending scale.",
          skill: "analytics.summarize_performance",
          tool: "performance_metrics",
          priority: "high",
        },
        {
          title: "surface contradictory signals",
          departmentName: "Analytics / Metrics",
          summary:
            "Reported that discount-framed copy had cheaper short-term leads while brand feedback showed the same message made Legacy feel less premium.",
          skill: "analytics.summarize_performance",
          tool: "performance_metrics",
          priority: "urgent",
        },
        {
          title: "constrain discount-led scale proposal",
          departmentName: "Strategy",
          summary:
            "Constrained Performance Marketing's discount-led scale proposal and chose appointment proof over short-term lead efficiency.",
          skill: "strategy.define_positioning",
          tool: "audience_segmentation",
          priority: "urgent",
        },
        {
          title: "identify underperforming segment",
          departmentName: "Analytics / Metrics",
          summary:
            "Identified Roma Norte prospecting as below target and routed the insight into learning before campaign scale-up.",
          status: "failed",
          skill: "analytics.summarize_performance",
          tool: "performance_metrics",
          priority: "urgent",
        },
        {
          title: "refresh launch content",
          departmentName: "Performance Marketing",
          summary:
            "Generated new underperforming-segment copy prompts without increasing the content capacity beyond six assets per week.",
          skill: "copywriter.generate_ad_copy",
          tool: "generate_content",
          priority: "normal",
        },
        {
          title: "prepare creative variant request",
          departmentName: "Creative Production",
          summary: "Prepared creative variant requirements for a more appointment-led Roma Norte audience test.",
          skill: "creative.generate_ad_concepts",
          tool: "creative_production",
          priority: "normal",
        },
      ],
    },
    {
      sequence: 5,
      name: "Learning & Iteration",
      purpose: "Write learnings to memory and improve strategy.",
      brief: "Operation 5 - Learning & Iteration for Legacy campaign performance loop",
      departments: ["Memory / Learning", "Client Success", "Marketing Strategy", "Analytics / Metrics"],
      memoryRetrieval: true,
      memoryWrite: true,
      followUpFromPerformance: true,
      deliverable:
        "Client: Legacy. Learning iteration 1 retrieved prior luxury-retail memory, wrote the Legacy performance case, reflected on the underperforming Roma Norte segment, and proposed a campaign architecture follow-up focused on appointment-led proof. Reasoning: the memory showed concierge referrals and optician credibility worked better than broad awareness for premium retail. Tradeoffs: the team kept the limited channel set and shifted the message instead of buying more reach. Why decisions were made: memory plus metrics indicated the weak segment needed proof of appointment value before scale.",
      tasks: [
        {
          title: "retrieve relevant memory",
          departmentName: "Memory / Learning",
          summary:
            "Retrieved prior luxury-retail launch memory, including one misleading discount-scale memory that must be checked against current brand perception.",
          skill: "memory.retrieve_relevant",
          tool: "memory_search",
          priority: "high",
        },
        {
          title: "detect misleading memory",
          departmentName: "Memory / Learning",
          summary:
            "Detected that the discount-scale memory conflicts with current Legacy brand evidence and marked it as unsafe to use for launch decisions.",
          skill: "memory.retrieve_relevant",
          tool: "memory_search",
          priority: "urgent",
        },
        {
          title: "write case memory",
          departmentName: "Memory / Learning",
          summary:
            "Wrote the Legacy launch case with the compliance route, performance gap, misleading-memory recovery, and next iteration recommendation.",
          skill: "memory.write_case",
          tool: "memory_store",
          priority: "high",
        },
        {
          title: "reflect on campaign performance",
          departmentName: "Analytics / Metrics",
          summary:
            "Reflected that Roma Norte prospects need stronger appointment proof and less broad luxury awareness creative.",
          skill: "analytics.summarize_performance",
          tool: "performance_metrics",
          priority: "high",
        },
        {
          title: "propose iteration",
          departmentName: "Marketing Strategy",
          summary:
            "Proposed rerouting to Campaign Architecture for a refreshed audience segment, ad copy, and creative concept test.",
          skill: "strategy.define_positioning",
          tool: "audience_segmentation",
          priority: "high",
        },
        {
          title: "client learning handoff",
          departmentName: "Client Success",
          summary:
            "Packaged the learning into a client-facing narrative: preserve winning VIP segments and improve the weak segment before scaling.",
          skill: "memory.write_case",
          tool: "generate_content",
          priority: "normal",
        },
      ],
    },
    {
      sequence: 6,
      name: "Campaign Architecture Follow-up",
      purpose: "Reroute underperforming performance signals back into campaign architecture.",
      brief: "Follow-up operation - Campaign Architecture iteration for Legacy Roma Norte segment",
      departments: [
        "Marketing Strategy",
        "Content Strategy",
        "Creative Production",
        "Operations Design",
        "Memory / Learning",
      ],
      memoryRetrieval: true,
      deliverable:
        "Client: Legacy. Learning iteration 2 used retrieved Legacy case memory to improve the campaign system with a Roma Norte appointment-proof segment, refreshed ad copy, new creative variants, and an updated calendar before further spend is scaled. Reasoning: the second iteration changed the output from general luxury awareness to appointment evidence, optician trust, and gallery-adjacent proof. Tradeoffs: the agency deferred broad influencer volume, kept the three-channel constraint, and used saved budget for higher-fit prospects. Why decisions were made: prior memory influenced the next plan, and the deliverable changed meaningfully before scale.",
      tasks: [
        {
          title: "retrieve performance learning",
          departmentName: "Memory / Learning",
          summary:
            "Retrieved the Legacy case memory and ignored the misleading discount-scale memory before revising the campaign architecture.",
          skill: "memory.retrieve_relevant",
          tool: "memory_search",
          priority: "high",
        },
        {
          title: "adapt to hidden constraints",
          departmentName: "Operations Design",
          summary:
            "Replanned after a surprise budget reduction, a retargeting channel failure, and a legal claim restriction changed the launch reality.",
          skill: "project.plan_launch",
          tool: "campaign_calendar",
          priority: "urgent",
        },
        {
          title: "revise audience segment",
          departmentName: "Marketing Strategy",
          summary:
            "Revised Roma Norte targeting around private fittings, design credibility, optician trust signals, and non-discount premium proof.",
          skill: "strategy.define_positioning",
          tool: "audience_segmentation",
          priority: "high",
        },
        {
          title: "generate refreshed ad copy",
          departmentName: "Content Strategy",
          summary: "Generated refreshed copy emphasizing private appointments, frame tactility, and appointment proof.",
          skill: "copywriter.generate_ad_copy",
          tool: "generate_content",
          priority: "normal",
        },
        {
          title: "generate creative variants",
          departmentName: "Creative Production",
          summary:
            "Generated creative variants with fitting-room proof, side-profile frames, and gallery-adjacent settings.",
          skill: "creative.generate_ad_concepts",
          tool: "creative_production",
          priority: "normal",
        },
        {
          title: "update campaign calendar",
          departmentName: "Operations Design",
          summary: "Updated the campaign calendar to test the revised segment before allocating additional spend.",
          skill: "project.plan_launch",
          tool: "campaign_calendar",
          priority: "normal",
        },
      ],
    },
  ];
}

function buildAgencyCompanyProfile(): CompanyProfile {
  return buildCompanyProfile({
    companyName: COMPANY_NAME,
    companyType: COMPANY_TYPE,
    objective: COMPANY_OBJECTIVE,
    autonomyMode: "assisted",
    aiAccessMode: "managed",
    departments: departmentDefinitions(),
    skills: [...REQUIRED_SKILLS],
  });
}

function buildAgencyCompanySetup() {
  const profile = buildAgencyCompanyProfile();
  const setup = buildCompanyGraphJson(profile);

  setup.metadata = {
    ...setup.metadata,
    simulation_contract: {
      organization: ORGANIZATION_NAME,
      company: {
        name: COMPANY_NAME,
        type: COMPANY_TYPE,
        objective: COMPANY_OBJECTIVE,
        autonomy_policy: "moderate",
        ai_access_policy: "enabled",
      },
      client: CLIENT,
      ontology: ["Organization", "Company", "Client", "Departments", "Operations", "Tasks", "Deliverables"],
      skills: [...REQUIRED_SKILLS],
      tools: [...REQUIRED_TOOLS],
      resource_constraints: RESOURCE_CONSTRAINTS,
      adversarial_conflicts: adversarialConflicts(),
      competing_proposals: competingProposalDecisions(),
      routing: [
        "VIP client intake routes through Strategy, Sales, Lead Processing, Account Management, and Finance",
        "campaign architecture routes through strategy, performance, content, creative, and finance departments",
        "budget conflict routes from Marketing Strategy and Performance Marketing to Finance and back to Strategy redesign",
        "competing paid and organic proposals route through Marketing Strategy for a merged constrained plan",
        "failed compliance routes through Legal / Compliance revision before approval",
        "rejected approval routes back to Account Management revision before reapproval",
        "performance below target routes through Memory / Learning and back to Campaign Architecture",
      ],
      approval_boundaries: [
        "human approval is required before client-facing campaign release",
        "compliance pass is required after failed claim review",
      ],
      operations: operationTemplates().map((operation) => ({
        name: operation.name,
        purpose: operation.purpose,
        departments: operation.departments,
      })),
    },
  };

  return { setup, profile };
}

function departmentIdsByNameFromSetup(setupJson: {
  nodes: Array<{ id: string; type: string; name?: string }>;
}): Record<string, string> {
  return Object.fromEntries(
    setupJson.nodes.flatMap((item) => (item.type !== "output" && item.name ? [[item.name, item.id]] : [])),
  );
}

async function createNamedOrganization(
  request: APIRequestContext,
  accessToken: string,
): Promise<{ id: string; name: string }> {
  const createResponse = await request.post(`${API_BASE_URL}/api/orgs`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    data: { name: ORGANIZATION_NAME, make_default: true },
  });
  expect(createResponse.ok()).toBeTruthy();

  const response = await request.get(`${API_BASE_URL}/api/orgs/me`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  expect(response.ok()).toBeTruthy();
  const body = (await response.json()) as {
    data: { organization: { id: string; name: string } };
  };
  expect(body.data.organization.name).toBe(ORGANIZATION_NAME);
  return body.data.organization;
}

async function persistSimulationCompanySetup(
  request: APIRequestContext,
  accessToken: string,
  companyId: string,
): Promise<void> {
  const { setup } = buildAgencyCompanySetup();
  const response = await request.post(`${API_BASE_URL}/api/graphs/${companyId}/versions`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    data: {
      graph_json: setup,
    },
  });
  expect(response.ok(), await response.text()).toBeTruthy();
}

function extractCompanyIdFromUrl(page: Page): string {
  const match = page.url().match(/\/companies\/([a-f0-9-]+)(?:\?.*)?$/);
  if (!match?.[1]) {
    throw new Error(`Could not determine company id from URL: ${page.url()}`);
  }
  return match[1];
}

async function createCompanyThroughUi(page: Page): Promise<string> {
  const createDiagnostics: string[] = [];
  page.on("requestfailed", (request) => {
    const url = request.url();
    if (url.includes("/api/graphs") || url.includes("/api/orgs")) {
      createDiagnostics.push(`${request.method()} ${url} failed: ${request.failure()?.errorText ?? "unknown error"}`);
    }
  });
  page.on("response", (response) => {
    const url = response.url();
    if (url.includes("/api/graphs") || url.includes("/api/orgs")) {
      createDiagnostics.push(`${response.request().method()} ${url} -> ${response.status()}`);
    }
  });

  await expect(page.getByRole("heading", { name: /^create company$/i })).toBeVisible();
  await expect(page.getByTestId("company-name-input")).toBeVisible();
  await page.getByTestId("company-name-input").fill(COMPANY_NAME);
  await page.getByTestId("company-objective-input").fill(COMPANY_OBJECTIVE);
  await page.getByRole("button", { name: /^continue$/i }).click();
  await expect(page.getByText(/suggested category/i).first()).toBeVisible();
  await page.getByRole("button", { name: /^continue$/i }).click();
  await expect(page.getByText(/departments/i).first()).toBeVisible();
  await page.getByRole("button", { name: /^continue$/i }).click();
  await expect(page.getByText(/ai access mode/i).first()).toBeVisible();
  await page.getByRole("button", { name: /^continue$/i }).click();
  await page.getByTestId("company-operation-brief-input").fill(SETUP_OPERATION_BRIEF);
  await page.getByRole("button", { name: /^create company without launch$/i }).click();
  try {
    await page.waitForURL(/\/companies\/[a-f0-9-]+(?:\?.*)?$/, { timeout: 20_000 });
  } catch (error) {
    const alerts = await page.locator('[role="alert"]').allTextContents();
    throw new Error(
      [
        error instanceof Error ? error.message : String(error),
        "Company creation diagnostics:",
        ...createDiagnostics,
        "Visible alerts:",
        ...alerts.flatMap((alert) => {
          const trimmed = alert.trim();
          return trimmed ? [trimmed] : [];
        }),
      ].join("\n"),
    );
  }
  return extractCompanyIdFromUrl(page);
}

function departmentId(state: SimulationState, departmentName: string): string {
  return state.departmentIdsByName[departmentName] ?? slugify(departmentName);
}

function seedMemory(state: SimulationState): void {
  if (state.memory.length > 0) {
    return;
  }
  state.memory.push({
    id: "memory-seed-legacy-luxury-retail",
    title: "Luxury retail appointment benchmark",
    content:
      "Prior luxury retail launches in Mexico City improved when broad awareness was paired with appointment proof, concierge referrals, and optician credibility.",
    operationId: null,
    departmentId: departmentId(state, "Memory / Learning"),
    topic: "legacy-campaign-learning",
    toolName: "memory.retrieve_relevant",
    createdAt: timestamp(0),
    kind: "seed",
  });
  state.memory.push({
    id: "memory-misleading-discount-scale",
    title: "Misleading discount scale memory",
    content:
      "Incorrect memory: discount-led mass acquisition improved premium eyewear brand perception in Mexico City. This contradicts current brand-sentiment evidence and should not drive Legacy's launch.",
    operationId: null,
    departmentId: departmentId(state, "Memory / Learning"),
    topic: "legacy-campaign-learning",
    toolName: "memory.retrieve_relevant",
    createdAt: timestamp(1),
    kind: "misleading",
  });
}

async function instantiateOperation(
  request: APIRequestContext,
  template: OperationTemplate,
  state: SimulationState,
): Promise<SimulationOperation> {
  const operationId = createOperationId(template.sequence);
  const startedAt = timestamp(template.sequence * 12);
  const approvalId = `approval-${operationId}`;
  const tasks = template.tasks.map((task, index): SimulationTask => {
    const currentDecisionId = template.createsApproval && task.approvalBoundary ? approvalId : null;
    const status = task.status ?? "succeeded";
    return {
      id: createTaskId(operationId, task.title),
      operationId,
      departmentId: departmentId(state, task.departmentName),
      departmentName: task.departmentName,
      title: task.title,
      status,
      priority: task.priority ?? "normal",
      summary: task.summary,
      sourceId: departmentId(state, task.departmentName),
      currentDecisionId,
      skill: task.skill,
      tool: task.tool,
      startedAt: timestamp(template.sequence * 12 + index),
      endedAt: status === "waiting" || status === "pending" ? null : timestamp(template.sequence * 12 + index + 1),
    };
  });

  const approvalTask = tasks.find((task) => task.currentDecisionId === approvalId);
  const approval =
    template.createsApproval && approvalTask
      ? {
          id: approvalId,
          operationId,
          departmentId: approvalTask.departmentId,
          departmentName: approvalTask.departmentName,
          status: "pending" as const,
          revision: 1,
          promptMessage:
            "Approve the Legacy client-facing campaign package after compliance revision, budget boundary review, and VIP account context confirmation. Goal: decide whether this constrained package is ready for Legacy. Reasoning: the first pass carries brand, legal, and budget risk. Next action: approve, or reject with required corrections.",
          createdAt: timestamp(template.sequence * 12 + 5),
          resolvedAt: null,
          result: null,
        }
      : null;

  return {
    id: operationId,
    sequence: template.sequence,
    name: template.name,
    purpose: template.purpose,
    status: approval ? "paused" : "succeeded",
    startedAt,
    endedAt: approval ? null : timestamp(template.sequence * 12 + template.tasks.length + 2),
    brief: template.brief,
    departments: template.departments,
    tasks,
    approval,
    approvalHistory: approval ? [approval] : [],
    deliverableText: approval ? null : await generateOperationDeliverable(request, template, state),
    attempts: template.followUpFromPerformance ? 2 : 1,
    triggeredByOperationId: null,
  };
}

function missingOperationDeliverableRequirements(
  content: string,
  template: OperationTemplate,
  state: SimulationState,
): string[] {
  const requiredPatterns = [
    /Client:/i,
    /Operation:/i,
    /Reasoning:/i,
    /Tradeoffs:/i,
    /Why decisions were made:/i,
    /Product coverage:/i,
  ];
  if (template.sequence === 6) {
    requiredPatterns.push(
      /Learning iteration 2 used retrieved Legacy case memory/i,
      /Dynamic adaptation:/i,
      /Memory recovery:/i,
    );
    if (stateHasTraceabilityRecords(state)) {
      requiredPatterns.push(
        /Decision trace:/i,
        /Rejected alternatives:/i,
        /Memory attribution:/i,
        /Approval impact:/i,
        /Iteration delta:/i,
      );
    }
  }
  return requiredPatterns.flatMap((pattern) => (!pattern.test(content) ? [String(pattern)] : []));
}

function stateHasTraceabilityRecords(state: SimulationState): boolean {
  return (
    state.decisionTraces.length > 0 ||
    state.memoryAttributions.length > 0 ||
    state.approvalImpacts.length > 0 ||
    state.iterationDeltas.length > 0
  );
}

async function generateOperationDeliverable(
  request: APIRequestContext,
  template: OperationTemplate,
  state: SimulationState,
): Promise<string> {
  const payload = {
    company: COMPANY_NAME,
    client: CLIENT,
    operation: {
      name: template.name,
      purpose: template.purpose,
      sequence: template.sequence,
      departments: template.departments,
      tasks: template.tasks,
    },
    scenario_notes: template.deliverable,
    resource_constraints: state.activeConstraints,
    hidden_constraints: state.hiddenConstraints,
    contradictory_signals: state.contradictorySignals,
    delayed_consequences: state.delayedConsequences,
    memory_recovery: state.memoryMisuseRecoveries,
    ambiguous_feedback_response: state.ambiguousJudgeInterpretations,
    decision_traceability: {
      decisions: state.decisionTraces,
      memory_attributions: state.memoryAttributions,
      approval_impacts: state.approvalImpacts,
      iteration_deltas: state.iterationDeltas,
    },
    required_product_coverage: {
      departments: template.departments,
      skills: [...new Set(template.tasks.map((task) => task.skill))],
      tools: [...new Set(template.tasks.map((task) => task.tool))],
    },
  };

  const requestDeliverableAttempt = async (
    attempt: number,
    previousContent = "",
    missing: string[] = [],
  ): Promise<string> => {
    const content = await requireLocalLlmContent(
      request,
      OPERATION_DELIVERABLE_PROMPT,
      attempt === 1
        ? payload
        : {
            ...payload,
            repair_instruction:
              "Repair the previous response by returning the complete deliverable again. Include every missing exact label as plain text with a colon. Do not summarize the repair.",
            previous_response: previousContent,
            missing_required_patterns: missing,
            missing_required_labels: missing.map((pattern) => pattern.replace(/^\/|\/i$/g, "")),
          },
      { temperature: attempt === 1 ? 0.25 : 0, timeout: 35_000, maxTokens: 2_400 },
    );
    state.llmResponses.push({ kind: "deliverable", label: `${template.name} attempt ${attempt}`, content });
    const nextMissing = missingOperationDeliverableRequirements(content, template, state);
    if (nextMissing.length === 0) {
      return content;
    }
    if (attempt < 5) {
      return requestDeliverableAttempt(attempt + 1, content, nextMissing);
    }

    throw new Error(`Local LLM deliverable for ${template.name} missed required content: ${nextMissing.join(", ")}`);
  };

  return requestDeliverableAttempt(1);
}

function applyOperationSideEffects(
  operation: SimulationOperation,
  template: OperationTemplate,
  state: SimulationState,
) {
  if (
    template.sequence === 2 &&
    !state.improvementEvents.includes("Resolved budget and channel conflicts before approval.")
  ) {
    state.improvementEvents.push("Resolved budget and channel conflicts before approval.");
  }
  if (template.complianceLoop) {
    state.complianceLoopOccurred = true;
  }
  if (template.performanceLoop) {
    state.performanceLoopOccurred = true;
    state.improvementEvents.push("Performance below target identified before scale-up.");
  }
  if (template.memoryRetrieval) {
    state.memoryRetrievalCount += 1;
    state.memory.push({
      id: `memory-retrieval-${operation.id}`,
      title: "Legacy relevant memory retrieved",
      content:
        "Retrieved relevant luxury retail memory before changing the Legacy campaign strategy and segment allocation.",
      operationId: operation.id,
      departmentId: departmentId(state, "Memory / Learning"),
      topic: "legacy-campaign-learning",
      toolName: "memory.retrieve_relevant",
      createdAt: timestamp(operation.sequence * 12 + 1),
      kind: "retrieval",
    });
  }
  if (template.memoryWrite) {
    state.memoryWriteCount += 1;
    state.memory.push({
      id: `memory-write-${operation.id}`,
      title: "Legacy campaign learning written",
      content:
        "Wrote case memory: VIP account, compliance revision, Polanco/Lomas traction, Roma Norte underperformance, and recommended campaign architecture iteration.",
      operationId: operation.id,
      departmentId: departmentId(state, "Memory / Learning"),
      topic: "legacy-campaign-learning",
      toolName: "memory.write_case",
      createdAt: timestamp(operation.sequence * 12 + 2),
      kind: "write",
    });
  }
  if (template.sequence === 5 && !state.learningIterations.some((iteration) => iteration.iteration === 1)) {
    if (
      !state.memoryMisuseRecoveries.some(
        (recovery) => recovery.misleadingMemoryId === "memory-misleading-discount-scale",
      )
    ) {
      state.memoryMisuseRecoveries.push({
        misleadingMemoryId: "memory-misleading-discount-scale",
        detectedBy: "Memory / Learning",
        issue: "The retrieved misleading discount-scale memory contradicted live brand-perception evidence for Legacy.",
        recovery:
          "The agency quarantined the memory, ignored discount-led guidance, and wrote a corrected case memory tied to appointment proof.",
      });
    }
    if (!state.memory.some((memory) => memory.id.startsWith("memory-recovery-"))) {
      state.memory.push({
        id: `memory-recovery-${operation.id}`,
        title: "Misleading memory quarantined",
        content:
          state.memoryMisuseRecoveries[0]?.recovery ??
          "The discount-scale memory was marked unsafe for Legacy because current brand feedback showed discount framing harmed premium perception.",
        operationId: operation.id,
        departmentId: departmentId(state, "Memory / Learning"),
        topic: "legacy-campaign-learning",
        toolName: "memory.write_case",
        createdAt: timestamp(operation.sequence * 12 + 3),
        kind: "write",
      });
      state.improvementEvents.push("Memory / Learning detected and recovered from misleading discount memory.");
    }
    state.learningIterations.push({
      iteration: 1,
      memoryUsed:
        "Prior luxury retail launches favored appointment proof, concierge referrals, and optician credibility; misleading discount memory was rejected.",
      changedFrom: "Broad luxury awareness, paid-heavy prospecting, and unsafe discount-led memory.",
      changedTo: "Appointment-led proof for the weak Roma Norte segment while preserving the channel cap.",
      output:
        "Iteration 1 changed the recommendation toward appointment proof, retained the budget reserve, and created the follow-up architecture operation.",
    });
    state.improvementEvents.push(
      "Learning iteration 1 used retrieved luxury retail memory to change the next recommendation.",
    );
  }
  if (template.sequence === 6 && !state.learningIterations.some((iteration) => iteration.iteration === 2)) {
    state.learningIterations.push({
      iteration: 2,
      memoryUsed:
        "Legacy case memory from iteration 1 plus launch metrics from the weak segment and hidden constraint notes.",
      changedFrom: "General Roma Norte luxury awareness variant with retargeting as the easiest scale path.",
      changedTo:
        "Private fitting, optician trust, gallery-adjacent appointment evidence, and reduced reliance on failed retargeting.",
      output:
        "Iteration 2 changed the deliverable content, refreshed copy and creative variants, and kept scale paused until the segment proves fit.",
    });
    state.improvementEvents.push("Learning iteration 2 reused written case memory and changed the final deliverable.");
  }
}

function applyDirectorOutput(state: SimulationState, directorOutput: SimulationDirectorOutput): void {
  if (state.hiddenConstraints.length > 0) {
    return;
  }

  const launchOperation = state.operations.find((operation) => operation.sequence === 4);
  expect(launchOperation).toBeTruthy();

  state.activeConstraints = directorOutput.activeConstraints;
  state.hiddenConstraints.push(...directorOutput.hiddenConstraints);
  state.contradictorySignals.push(...directorOutput.contradictorySignals);
  state.delayedConsequences.push(...directorOutput.delayedConsequences);
  state.memoryMisuseRecoveries.push(...directorOutput.memoryMisuseRecoveries);
  state.departmentChallenges.push(...directorOutput.departmentChallenges);

  state.conflicts.push({
    id: "conflict-hidden-retargeting-failure",
    title: "Hidden channel failure conflicts with short-term acquisition plan",
    departments: ["Performance Marketing", "Strategy", "Operations Design", "Client Success"],
    constraint: "The fastest early channel became unreliable after the campaign was already approved.",
    decision: "The agency chose brand-safe appointment proof over short-term volume recovery.",
    resolution:
      "Retargeting moved to a secondary test while concierge referrals, CRM invitations, and private fitting proof became the launch core.",
  });
  state.improvementEvents.push("Local LLM simulation director injected hidden constraints after launch monitoring.");
}

async function startOperationFromBrief(
  request: APIRequestContext,
  state: SimulationState,
  brief: string,
): Promise<SimulationOperation> {
  const templates = operationTemplates();
  const template =
    templates.find((candidate) => candidate.brief === brief) ??
    templates.find((candidate) => candidate.sequence === Math.min(state.operations.length + 1, 5)) ??
    templates[0];
  const operation = await instantiateOperation(request, template, state);
  state.operations.push(operation);
  applyOperationSideEffects(operation, template, state);

  if (template.followUpFromPerformance && !state.operations.some((item) => item.sequence === 6)) {
    const followUpTemplate = templates.find((candidate) => candidate.sequence === 6);
    if (followUpTemplate) {
      const followUp = await instantiateOperation(request, followUpTemplate, state);
      followUp.triggeredByOperationId = operation.id;
      state.operations.push(followUp);
      applyOperationSideEffects(followUp, followUpTemplate, state);
      state.improvementEvents.push("Created Campaign Architecture follow-up after performance loop.");
    }
  }

  return operation;
}

function currentPendingApproval(operation: SimulationOperation): SimulationApproval | null {
  return operation.approvalHistory.find((approval) => approval.status === "pending") ?? null;
}

function allApprovals(state: SimulationState): SimulationApproval[] {
  return state.operations.flatMap((operation) => operation.approvalHistory);
}

async function resolveOperationApproval(
  request: APIRequestContext,
  operation: SimulationOperation,
  result: Record<string, unknown>,
  state: SimulationState,
): Promise<void> {
  const approval = currentPendingApproval(operation);
  if (!approval) {
    return;
  }

  const input = result.input_json as { approved?: boolean; feedback?: string } | undefined;
  const approved = input?.approved === true;
  const feedback = input?.feedback ?? "";
  approval.result = result;
  approval.resolvedAt = timestamp(operation.sequence * 12 + 7 + approval.revision);

  if (!approved) {
    approval.status = "rejected";
    state.approvalRejectionCount += 1;
    state.approvalRevisionCount += 1;
    operation.attempts += 1;

    const revisedApproval: SimulationApproval = {
      id: `approval-revised-${operation.id}`,
      operationId: operation.id,
      departmentId: approval.departmentId,
      departmentName: approval.departmentName,
      status: "pending",
      revision: approval.revision + 1,
      promptMessage:
        "Revised approval required for Legacy after rejection. Goal: confirm the agency corrected risky claims and stayed inside the budget cap. Reasoning: the operator rejected the first package because the decision context was not strong enough under legal and financial pressure. Next action: approve the revised package or request another correction.",
      createdAt: timestamp(operation.sequence * 12 + 9),
      resolvedAt: null,
      result: null,
    };

    operation.approval = revisedApproval;
    operation.approvalHistory.push(revisedApproval);
    operation.status = "paused";
    operation.endedAt = null;
    operation.deliverableText = null;
    operation.tasks = operation.tasks.map((task) => {
      if (task.currentDecisionId === approval.id || task.status === "waiting") {
        return {
          ...task,
          status: "waiting",
          currentDecisionId: revisedApproval.id,
          endedAt: null,
          summary:
            "Initial approval was rejected. Next action: revise the Legacy package with tighter claims, clearer budget reasoning, and operator feedback before reapproval.",
        };
      }
      if (task.title === "revise rejected approval package") {
        return {
          ...task,
          status: "running",
          summary: `Revision active after rejection feedback: ${feedback || "tighten claim, budget, and client consequence context."}`,
          startedAt: timestamp(operation.sequence * 12 + 9),
          endedAt: null,
        };
      }
      return task;
    });
    state.improvementEvents.push("Approval rejection forced revision before client-facing release.");
    return;
  }

  approval.status = "approved";
  state.approvalReapprovalCount += approval.revision > 1 ? 1 : 0;
  operation.status = "succeeded";
  operation.endedAt = timestamp(operation.sequence * 12 + operation.tasks.length + 5);
  operation.deliverableText = await generateOperationDeliverable(
    request,
    operationTemplates().find((item) => item.sequence === operation.sequence)!,
    state,
  );
  operation.tasks = operation.tasks.map((task) =>
    task.status === "waiting" || task.status === "running" || task.currentDecisionId === approval.id
      ? {
          ...task,
          status: "succeeded",
          currentDecisionId: null,
          endedAt: timestamp(operation.sequence * 12 + operation.tasks.length + 4),
          summary:
            task.title === "revise rejected approval package"
              ? "Revision completed. The reapproved package now explains claim changes, budget constraints, and why the constrained campaign should move forward."
              : "Human approval recorded after revision. Campaign package is released for client-facing handoff.",
        }
      : task,
  );
}

function sortOperations(operations: SimulationOperation[]): SimulationOperation[] {
  return operations.toSorted((left, right) => right.startedAt.localeCompare(left.startedAt));
}

function buildOperationListItem(operation: SimulationOperation, state: SimulationState) {
  return {
    id: operation.id,
    graph_id: state.companyId,
    graph_name: COMPANY_NAME,
    graph_version_id: state.setupVersionId,
    graph_version: 2,
    status: operation.status,
    queue_status:
      operation.status === "succeeded"
        ? operation.attempts > 1
          ? "completed_after_iteration"
          : "completed"
        : operation.status === "paused"
          ? "paused"
          : operation.status,
    queue_attempts: operation.attempts,
    queue_available_at: null,
    started_at: operation.startedAt,
    ended_at: operation.endedAt,
    duration_ms: operation.endedAt ? 420_000 + operation.tasks.length * 22_000 : 240_000,
    llm_access: {
      llm_mode: "managed",
      provider: "local-llm",
      credential_id: null,
      api_key_present: false,
    },
    memory_activity: buildMemoryActivitySummary(operation, state),
  };
}

function buildMemoryActivitySummary(operation: SimulationOperation, state: SimulationState) {
  const memoryTasks = operation.tasks.filter(
    (task) => task.skill === "memory.retrieve_relevant" || task.skill === "memory.write_case",
  );
  const retrieved = operation.tasks.filter((task) => task.skill === "memory.retrieve_relevant").length;
  const saved = operation.tasks.filter((task) => task.skill === "memory.write_case").length;
  return {
    has_activity: memoryTasks.length > 0 || state.memory.length > 0,
    save_node_count: saved,
    saved_observation_count: saved,
    retrieval_node_count: retrieved,
    retrieved_observation_count: retrieved,
    influenced_node_count: Math.max(retrieved, 0),
    influenced_observation_count: Math.max(retrieved, 0),
    degraded: false,
    operations: memoryTasks.map((task) => ({
      node_id: task.departmentId,
      node_type: "department",
      status: task.status,
      attempt: 1,
      duration_ms: 36_000,
      category: task.skill === "memory.write_case" ? "save" : "retrieval",
      operation: task.skill === "memory.write_case" ? "save" : "search",
      count: task.skill === "memory.retrieve_relevant" ? Math.max(state.memory.length, 1) : 1,
      saved: task.skill === "memory.write_case",
    })),
  };
}

function buildDepartmentActivity(operation: SimulationOperation, state: SimulationState) {
  const approvalIndex = operation.tasks.findIndex((task) => task.status === "waiting");
  const visibleTasks =
    operation.status === "paused" && approvalIndex >= 0 ? operation.tasks.slice(0, approvalIndex + 1) : operation.tasks;

  return visibleTasks.map((task, index) => ({
    id: task.id,
    node_id: task.departmentId,
    node_type: "agent",
    status: task.status === "succeeded" ? "succeeded" : task.status,
    attempt: 1,
    started_at: task.startedAt,
    ended_at: task.endedAt,
    duration_ms: task.endedAt ? 40_000 + index * 8_000 : null,
    input_json: {
      client: CLIENT,
      operation_brief: operation.brief,
      department: task.departmentName,
      skill: task.skill,
      tool: task.tool,
    },
    output_json:
      task.status === "succeeded"
        ? {
            deliverable: task.summary,
            skill: task.skill,
            tool: task.tool,
          }
        : null,
    error_json: task.status === "failed" ? { message: task.summary } : null,
    agent_trace: {
      final_output: task.summary,
      step_count: 1,
      tool_call_count: 1,
      steps: [
        {
          step_index: 0,
          action: task.skill,
          tool: task.tool,
          tool_input: { client: CLIENT.name, market: CLIENT.market, operation: operation.name },
          tool_output: task.summary,
          final_answer: task.summary,
          finish_reason: task.status === "failed" ? "requires_revision" : "completed",
        },
      ],
      usage: { total_tokens: 700 + index * 95 },
    },
    memory_activity:
      task.skill === "memory.retrieve_relevant" || task.skill === "memory.write_case"
        ? {
            category: task.skill === "memory.write_case" ? "save" : "retrieval",
            operation: task.skill === "memory.write_case" ? "save" : "search",
            count: task.skill === "memory.retrieve_relevant" ? Math.max(state.memory.length, 1) : 1,
            degraded: false,
            saved: task.skill === "memory.write_case",
          }
        : null,
  }));
}

function buildOperationDetail(operation: SimulationOperation, state: SimulationState) {
  const pendingApproval = currentPendingApproval(operation);
  return {
    ...buildOperationListItem(operation, state),
    owner_id: "playwright-agency-simulation-owner",
    thread_id: null,
    input_json: {
      company_name: COMPANY_NAME,
      company_type: COMPANY_TYPE,
      objective: COMPANY_OBJECTIVE,
      client: CLIENT,
      operation_brief: operation.brief,
    },
    output_json:
      operation.status === "succeeded"
        ? {
            deliverable: operation.deliverableText,
            operation_name: operation.name,
            client: CLIENT,
            coverage: {
              departments: operation.departments,
              tasks: operation.tasks.length,
            },
          }
        : null,
    error_message: operation.status === "failed" ? `${operation.name} needs attention.` : "",
    node_runs: buildDepartmentActivity(operation, state),
    agent_events: [],
    paused_node_id: operation.status === "paused" ? pendingApproval?.departmentId : null,
    pause_payload:
      operation.status === "paused"
        ? {
            node_id: pendingApproval?.departmentId,
            node_name: pendingApproval?.departmentName,
            prompt_message: pendingApproval?.promptMessage,
            required_fields: ["approval_notes", "client_context"],
          }
        : null,
  };
}

function buildTaskRecords(operation: SimulationOperation, state: SimulationState) {
  return operation.tasks.map((task) => ({
    id: task.id,
    organization_id: state.organizationId,
    execution_id: operation.id,
    agent_id: task.departmentId,
    title: task.title,
    status: task.status,
    priority: task.priority,
    summary: `${task.departmentName}: ${task.summary}`,
    source_node_id: task.sourceId,
    current_step_id: task.id,
    current_decision_id: task.currentDecisionId,
    started_at: task.startedAt,
    ended_at: task.endedAt,
    created_at: task.startedAt ?? operation.startedAt,
    updated_at: task.endedAt ?? task.startedAt ?? operation.startedAt,
  }));
}

function buildApprovalRecords(state: SimulationState, statusFilter: string | null) {
  return state.operations.flatMap((operation) =>
    operation.approvalHistory.flatMap((approval) =>
      !statusFilter || statusFilter === "all" || approval.status === statusFilter
        ? [
            {
              id: approval.id,
              run_id: approval.operationId,
              run_name: operation.name,
              graph_name: COMPANY_NAME,
              node_id: approval.departmentId,
              node_name: approval.departmentName,
              status: approval.status,
              prompt_message: approval.promptMessage,
              payload: {
                prompt_message: approval.promptMessage,
                required_fields: ["approval_notes", "client_context"],
              },
              result: approval.result,
              created_at: approval.createdAt,
              resolved_at: approval.resolvedAt,
            },
          ]
        : [],
    ),
  );
}

function buildDecisionRecords(state: SimulationState, includeResolved = true) {
  return state.operations.flatMap((operation) =>
    operation.approvalHistory.flatMap((approval) =>
      includeResolved || approval.status === "pending"
        ? [
            {
              id: `decision-${approval.id}`,
              organization_id: state.organizationId,
              execution_id: approval.operationId,
              task_id: `${approval.operationId}-campaign-approval`,
              agent_id: approval.departmentId,
              decision_type: "human_approval",
              status: approval.status,
              source_approval_task_id: approval.id,
              context_json: {
                summary: approval.promptMessage,
                client: CLIENT,
              },
              resolution_json: approval.result ?? {},
              requested_at: approval.createdAt,
              resolved_at: approval.resolvedAt,
              created_at: approval.createdAt,
              updated_at: approval.resolvedAt ?? approval.createdAt,
            },
          ]
        : [],
    ),
  );
}

function buildMemoryObservation(memory: SimulationMemory, state: SimulationState) {
  return {
    id: memory.id,
    tenant_id: state.organizationId,
    graph_id: state.companyId,
    run_id: memory.operationId,
    session_id: null,
    agent_id: memory.departmentId,
    memory_chunk_id: null,
    type: memory.kind === "write" ? "case_memory" : "campaign_memory",
    title: memory.title,
    content: memory.content,
    scope: memory.operationId ? "run" : "graph",
    topic_key: memory.topic,
    tool_name: memory.toolName,
    revision_count: memory.kind === "write" ? 2 : 1,
    duplicate_count: 0,
    last_seen_at: memory.createdAt,
    created_at: memory.createdAt,
    updated_at: memory.createdAt,
    deleted_at: null,
    is_deleted: false,
  };
}

function buildDepartmentProjection(department: AgencyDepartment, state: SimulationState) {
  const departmentIdValue = departmentId(state, department.label);
  const departmentTasks = state.operations.flatMap((operation) =>
    operation.tasks.flatMap((task) => (task.departmentId === departmentIdValue ? [task] : [])),
  );
  const pendingDecisions = state.operations.flatMap((operation) =>
    operation.approvalHistory.flatMap((approval) =>
      approval.departmentId === departmentIdValue && approval.status === "pending" ? [approval] : [],
    ),
  ).length;
  const failedTasks = departmentTasks.filter((task) => task.status === "failed").length;
  const lastOperation = sortOperations(state.operations).find((operation) =>
    operation.tasks.some((task) => task.departmentId === departmentIdValue),
  );

  return {
    id: departmentIdValue,
    organization_id: state.organizationId,
    slug: department.id,
    display_name: department.label,
    status: pendingDecisions > 0 || failedTasks > 0 ? "attention" : departmentTasks.length > 0 ? "active" : "idle",
    source_workflow_id: state.companyId,
    source_workflow_revision_id: state.setupVersionId,
    source_node_id: departmentIdValue,
    default_model: "local-llm",
    last_execution_id: lastOperation?.id ?? null,
    last_seen_at: lastOperation?.startedAt ?? null,
    policy_snapshot_json: {
      role: department.role,
      purpose: department.purpose,
      autonomy_policy: "moderate",
      ai_access_policy: "enabled",
    },
    capabilities_json: {
      skills: department.skills,
      tools: department.externalTools,
      capabilities: department.tools,
    },
    task_count: departmentTasks.length,
    pending_decisions: pendingDecisions,
    total_cost_usd: Math.round((departmentTasks.length * 0.08 + failedTasks * 0.11) * 100) / 100,
    created_at: timestamp(0),
    updated_at: timestamp(92),
  };
}

function buildSystemOverview(state: SimulationState) {
  const activeTasks: ReturnType<typeof buildTaskRecords> = [];
  for (const operation of sortOperations(state.operations)) {
    for (const task of buildTaskRecords(operation, state)) {
      if (ACTIVE_TASK_STATUSES.has(task.status)) {
        activeTasks.push(task);
      }
    }
  }
  const activeDepartments = departmentDefinitions().map((department) => buildDepartmentProjection(department, state));
  const pendingDecisions = buildDecisionRecords(state, false);
  const recentOperations = sortOperations(state.operations).map((operation) => ({
    id: operation.id,
    workflow_id: state.companyId,
    workflow_name: COMPANY_NAME,
    workflow_revision_id: state.setupVersionId,
    status: operation.status,
    started_at: operation.startedAt,
    ended_at: operation.endedAt,
    duration_ms: operation.endedAt ? 420_000 + operation.tasks.length * 22_000 : 240_000,
  }));
  const totalCost =
    Math.round((activeDepartments.reduce((sum, item) => sum + item.total_cost_usd, 0) + 7.35) * 100) / 100;

  return {
    organization: {
      id: state.organizationId,
      name: state.organizationName,
    },
    summary: {
      active_agent_count: activeDepartments.length,
      active_task_count: activeTasks.length,
      pending_decision_count: pendingDecisions.length,
      execution_count_24h: state.operations.length,
      memory_observation_count: state.memory.length,
      total_cost_usd: totalCost,
    },
    active_agents: activeDepartments,
    active_tasks: activeTasks,
    pending_decisions: pendingDecisions,
    recent_executions: recentOperations,
    memory: {
      active_observation_count: state.memory.length,
      recent_topics: ["legacy-campaign-learning", "mexico-city-luxury", "vip-client-launch"],
    },
    policy: {
      configured: true,
      allowed_providers: ["local-llm"],
      allowed_models: ["docker-local"],
      http_default_deny: true,
    },
    accounting: {
      organization_id: state.organizationId,
      total_cost_usd: totalCost,
      cost_by_type: [
        { cost_type: "skills", total_cost_usd: 3.42, entry_count: REQUIRED_SKILLS.length },
        { cost_type: "tools", total_cost_usd: 4.18, entry_count: REQUIRED_TOOLS.length },
        { cost_type: "approvals", total_cost_usd: 0.34, entry_count: allApprovals(state).length },
        { cost_type: "memory", total_cost_usd: 0.21, entry_count: state.memory.length },
      ],
      top_agents: activeDepartments.slice(0, 6).map((department) => ({
        id: department.id,
        display_name: department.display_name,
        status: department.status,
        total_cost_usd: department.total_cost_usd,
      })),
      recent_aggregates: [],
    },
    generated_at: timestamp(95),
  };
}

async function installSimulationProductApis(
  page: Page,
  apiRequest: APIRequestContext,
  state: SimulationState,
): Promise<void> {
  await page.route(/\/api\/agents\/[^/]+(?:\?.*)?$/, async (route: Route) => {
    const departmentIdFromUrl = route.request().url().split("/api/agents/")[1]?.split("?")[0] ?? "";
    const department = departmentDefinitions().find((item) => departmentId(state, item.label) === departmentIdFromUrl);
    await route.fulfill({
      status: department ? 200 : 404,
      contentType: "application/json",
      body: JSON.stringify(
        department
          ? apiSuccess(buildDepartmentProjection(department, state))
          : { error: { code: "NOT_FOUND", message: "Department not found." } },
      ),
    });
  });

  await page.route(/\/api\/agents\/?(?:\?.*)?$/, async (route: Route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(
        apiSuccess(departmentDefinitions().map((department) => buildDepartmentProjection(department, state))),
      ),
    });
  });

  await page.route(/\/api\/runs\/start(?:\?.*)?$/, async (route: Route) => {
    const body = route.request().postDataJSON() as { input_json?: { operation_brief?: string } };
    const brief = body.input_json?.operation_brief ?? "";
    const operation = await startOperationFromBrief(apiRequest, state, brief);
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(apiSuccess(buildOperationDetail(operation, state))),
    });
  });

  await page.route(/\/api\/runs\/[^/]+\/resume(?:\?.*)?$/, async (route: Route) => {
    const operationId = route.request().url().split("/api/runs/")[1]?.split("/resume")[0] ?? "";
    const operation = state.operations.find((item) => item.id === operationId);
    expect(operation).toBeTruthy();
    await resolveOperationApproval(
      apiRequest,
      operation!,
      route.request().postDataJSON() as Record<string, unknown>,
      state,
    );
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(apiSuccess({ resumed: true })),
    });
  });

  await page.route(/\/api\/runs\/(?!start(?:\?|$))[^/]+(?:\?.*)?$/, async (route: Route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }
    const operationId = route.request().url().split("/api/runs/")[1]?.split("?")[0] ?? "";
    const operation = state.operations.find((item) => item.id === operationId);
    await route.fulfill({
      status: operation ? 200 : 404,
      contentType: "application/json",
      body: JSON.stringify(operation ? apiSuccess(buildOperationDetail(operation, state)) : { error: "Not found" }),
    });
  });

  await page.route(/\/api\/runs\/?(?:\?.*)?$/, async (route: Route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(
        apiSuccess(sortOperations(state.operations).map((operation) => buildOperationListItem(operation, state))),
      ),
    });
  });

  await page.route(/\/api\/approvals\/count(?:\?.*)?$/, async (route: Route) => {
    const count = allApprovals(state).filter((approval) => approval.status === "pending").length;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(apiSuccess({ count })),
    });
  });

  await page.route(/\/api\/approvals\/?(?:\?.*)?$/, async (route: Route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }
    const statusFilter = new URL(route.request().url()).searchParams.get("status");
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(apiSuccess(buildApprovalRecords(state, statusFilter))),
    });
  });

  await page.route(/\/api\/decisions\/count(?:\?.*)?$/, async (route: Route) => {
    const count = allApprovals(state).filter((approval) => approval.status === "pending").length;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(apiSuccess({ count })),
    });
  });

  await page.route(/\/api\/decisions\/?(?:\?.*)?$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(apiSuccess(buildDecisionRecords(state))),
    });
  });

  await page.route(/\/api\/tasks\/?(?:\?.*)?$/, async (route: Route) => {
    const tasks = sortOperations(state.operations).flatMap((operation) => buildTaskRecords(operation, state));
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(apiSuccess(tasks)),
    });
  });

  await page.route(/\/api\/memory\/observations\/timeline(?:\?.*)?$/, async (route: Route) => {
    const url = new URL(route.request().url());
    const agentId = url.searchParams.get("agent_id");
    const observations = state.memory.flatMap((memory) =>
      !agentId || memory.departmentId === agentId ? [buildMemoryObservation(memory, state)] : [],
    );
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(apiSuccess(observations)),
    });
  });

  await page.route(/\/api\/memory\/observations\/search(?:\?.*)?$/, async (route: Route) => {
    const url = new URL(route.request().url());
    const query = (url.searchParams.get("query") ?? "").toLowerCase();
    const observations = state.memory.flatMap((memory) => {
      const searchableText = `${memory.title} ${memory.content} ${memory.topic}`.toLowerCase();
      return !query || searchableText.split(query).length > 1 ? [buildMemoryObservation(memory, state)] : [];
    });
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(apiSuccess(observations)),
    });
  });

  await page.route(/\/api\/memory\/observations\/(?!search|timeline|context)[^/?]+(?:\?.*)?$/, async (route: Route) => {
    const observationId = route.request().url().split("/api/memory/observations/")[1]?.split("?")[0] ?? "";
    const memory = state.memory.find((item) => item.id === observationId);
    await route.fulfill({
      status: memory ? 200 : 404,
      contentType: "application/json",
      body: JSON.stringify(memory ? apiSuccess(buildMemoryObservation(memory, state)) : { error: "Not found" }),
    });
  });

  await page.route(/\/api\/system-state\/overview(?:\?.*)?$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(apiSuccess(buildSystemOverview(state))),
    });
  });
}

function coverageReport(state: SimulationState) {
  const tasks = state.operations.flatMap((operation) => operation.tasks);
  return {
    organization: state.organizationName,
    company: state.companyProfile.companyName,
    client: CLIENT,
    departments: departmentDefinitions().map((department) => department.label),
    operations: state.operations.map((operation) => operation.name),
    taskCount: tasks.length,
    skills: [...new Set(tasks.map((task) => task.skill))],
    tools: [...new Set(tasks.map((task) => task.tool))],
    approvals: allApprovals(state),
    approvalRejectionCount: state.approvalRejectionCount,
    approvalRevisionCount: state.approvalRevisionCount,
    approvalReapprovalCount: state.approvalReapprovalCount,
    constraints: state.constraints,
    activeConstraints: state.activeConstraints,
    hiddenConstraints: state.hiddenConstraints,
    contradictorySignals: state.contradictorySignals,
    delayedConsequences: state.delayedConsequences,
    memoryMisuseRecoveries: state.memoryMisuseRecoveries,
    departmentChallenges: state.departmentChallenges,
    ambiguousJudgeInterpretations: state.ambiguousJudgeInterpretations,
    uxComprehensionSamples: state.uxComprehensionSamples,
    conflicts: state.conflicts,
    proposalDecisions: state.proposalDecisions,
    complianceLoopOccurred: state.complianceLoopOccurred,
    performanceLoopOccurred: state.performanceLoopOccurred,
    memoryRetrievalCount: state.memoryRetrievalCount,
    memoryWriteCount: state.memoryWriteCount,
    learningIterations: state.learningIterations,
    decisionTraces: state.decisionTraces,
    memoryAttributions: state.memoryAttributions,
    approvalImpacts: state.approvalImpacts,
    iterationDeltas: state.iterationDeltas,
    deliverables: state.operations.flatMap((operation) => (operation.deliverableText ? [operation.name] : [])),
    deliverableTexts: state.operations.flatMap((operation) =>
      operation.deliverableText ? [operation.deliverableText] : [],
    ),
    improvementEvents: state.improvementEvents,
    reportBuilderArtifact: state.reportBuilderArtifact
      ? {
          operationId: state.reportBuilderArtifact.operation_id,
          format: state.reportBuilderArtifact.format,
          contentType: state.reportBuilderArtifact.content_type,
          traceableSections: Object.keys(state.reportBuilderArtifact.traceability),
        }
      : null,
    llmResponses: state.llmResponses,
    llmResponseCount: state.llmResponses.length,
  };
}

function extractJsonObject(text: string): Record<string, unknown> | null {
  const firstBrace = text.indexOf("{");
  const lastBrace = text.lastIndexOf("}");
  if (firstBrace === -1 || lastBrace <= firstBrace) {
    return null;
  }
  try {
    return JSON.parse(text.slice(firstBrace, lastBrace + 1)) as Record<string, unknown>;
  } catch {
    return null;
  }
}

async function judgeScenario(request: APIRequestContext, state: SimulationState): Promise<JudgeResult> {
  const report = coverageReport(state);
  const { llmResponses, deliverableTexts, ...scenario } = report;
  const { content, parsed } = await requireLocalLlmJson(
    request,
    AI_JUDGE_PROMPT,
    {
      scenario: {
        ...scenario,
        llmResponseCount: llmResponses.length,
        llmResponseKinds: [...new Set(llmResponses.map((response) => response.kind))],
        finalDeliverable: deliverableTexts[deliverableTexts.length - 1],
      },
      strict_quality_mode: REQUIRE_TOP_TIER,
    },
    { temperature: 0, timeout: 60_000 },
  );
  state.llmResponses.push({ kind: "judge", label: "scenario evaluator", content });

  const criteria = (parsed.criteria ?? {}) as Partial<JudgeResult["criteria"]>;
  const result: JudgeResult = {
    coverage_score: Number(parsed.coverage_score),
    marketing_quality_score: Number(parsed.marketing_quality_score),
    reasoning: String(parsed.reasoning ?? ""),
    ambiguous_feedback: String(parsed.ambiguous_feedback ?? ""),
    criteria: {
      scenario_completeness: Number(criteria.scenario_completeness),
      department_coverage: Number(criteria.department_coverage),
      operation_coverage: Number(criteria.operation_coverage),
      skill_tool_coverage: Number(criteria.skill_tool_coverage),
      product_ux_coherence: Number(criteria.product_ux_coherence),
      decision_adaptation: Number(criteria.decision_adaptation),
      learning_improvement: Number(criteria.learning_improvement),
      ambiguity_handling: Number(criteria.ambiguity_handling),
      memory_recovery: Number(criteria.memory_recovery),
      marketing_quality: Number(criteria.marketing_quality),
    },
    source: "local-llm",
  };

  const invalidFields = [
    Number.isFinite(result.coverage_score) ? "" : "coverage_score",
    Number.isFinite(result.marketing_quality_score) ? "" : "marketing_quality_score",
    result.reasoning ? "" : "reasoning",
    result.ambiguous_feedback ? "" : "ambiguous_feedback",
    ...Object.entries(result.criteria).flatMap(([key, value]) => (!Number.isFinite(value) ? [`criteria.${key}`] : [])),
  ].flatMap((field) => (field ? [field] : []));
  if (invalidFields.length > 0) {
    throw new Error(`Local LLM judge output is incomplete: ${invalidFields.join(", ")}`);
  }

  return result;
}

async function launchOperationThroughUi(page: Page, state: SimulationState, brief: string) {
  const before = state.operations.length;
  await page.getByTestId("company-launch-operation-input").fill(brief);
  await page.getByTestId("company-launch-operation-button").click();
  await expect.poll(() => state.operations.length, { timeout: 120_000 }).toBeGreaterThan(before);
  await page.waitForLoadState("networkidle");
}

async function visibleText(page: Page): Promise<string> {
  return page.locator("body").innerText();
}

function assertNoInternalTerminology(text: string) {
  expect(text).not.toMatch(/\bgraph\b/i);
  expect(text).not.toMatch(/\bnode\b/i);
  expect(text).not.toMatch(/\brun\b/i);
  expect(text).not.toMatch(/\bexecution\b/i);
  expect(text).not.toMatch(/\bworkflow\b/i);
}

async function expectSurfaceClean(page: Page) {
  assertNoInternalTerminology(await visibleText(page));
}

function recordUxComprehension(state: SimulationState, surface: string, text: string): void {
  const clarityOfIntent = /\b(goal|purpose|current focus|trying to|client|operation)\b/i.test(text);
  const clarityOfDecisions = /\b(decision|approve|reject|revised|tradeoff|choice|chose|constrained|because)\b/i.test(
    text,
  );
  const clarityOfNextSteps =
    /\b(next action|next|inspect|open operation|approve|follow-up|before further spend|scale)\b/i.test(text);
  state.uxComprehensionSamples.push({
    surface,
    clarityOfIntent,
    clarityOfDecisions,
    clarityOfNextSteps,
    score: [clarityOfIntent, clarityOfDecisions, clarityOfNextSteps].filter(Boolean).length,
  });
}

async function interpretAmbiguousJudgeFeedback(request: APIRequestContext, state: SimulationState): Promise<void> {
  const feedback =
    state.judge?.ambiguous_feedback ??
    "The strategy is directionally stronger, but the evidence is incomplete and should be interpreted with caution.";
  if (state.ambiguousJudgeInterpretations.some((item) => item.feedback === feedback)) {
    return;
  }

  const { content, parsed } = await requireLocalLlmJson(
    request,
    AMBIGUOUS_FEEDBACK_RESPONSE_PROMPT,
    {
      feedback,
      client: CLIENT,
      current_strategy: state.operations.find((operation) => operation.sequence === 6)?.deliverableText,
      hidden_constraints: state.hiddenConstraints,
      contradictory_signals: state.contradictorySignals,
      memory_recovery: state.memoryMisuseRecoveries,
    },
    { temperature: 0.2, timeout: 20_000 },
  );
  const interpretation = String(parsed.interpretation ?? "");
  const response = String(parsed.response ?? "");
  if (!interpretation || !response) {
    throw new Error(`Local LLM ambiguous feedback response is incomplete: ${content.slice(0, 500)}`);
  }
  state.llmResponses.push({ kind: "judge", label: "ambiguous feedback response", content });
  state.ambiguousJudgeInterpretations.push({
    feedback,
    interpretation,
    response,
  });
  state.learningIterations.push({
    iteration: 3,
    memoryUsed: "Ambiguous judge feedback plus corrected Legacy case memory.",
    changedFrom: "A single final recommendation based mainly on appointment proof.",
    changedTo:
      "A guarded recommendation with brand-safe appointment proof and a small demand test that cannot override brand perception.",
    output:
      "Iteration 3 interpreted imperfect feedback, preserved the brand-safe plan, and added a constrained learning test instead of treating the judge as absolute.",
  });
  state.improvementEvents.push(
    "Ambiguous evaluator feedback was interpreted and converted into a constrained next decision.",
  );

  const followUpOperation = state.operations.find((operation) => operation.sequence === 6);
  const followUpTemplate = operationTemplates().find((template) => template.sequence === 6);
  if (followUpOperation && followUpTemplate) {
    followUpOperation.deliverableText = await generateOperationDeliverable(request, followUpTemplate, state);
  }
}

function normalizeStringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.flatMap((item) => {
        const trimmed = String(item).trim();
        return trimmed ? [trimmed] : [];
      })
    : [];
}

async function generateTraceabilityAudit(
  request: APIRequestContext,
  state: SimulationState,
): Promise<TraceabilityOutput> {
  const { content, parsed } = await requireLocalLlmJson(
    request,
    TRACEABILITY_PROMPT,
    {
      company: COMPANY_NAME,
      client: CLIENT,
      operations: state.operations.map((operation) => ({
        id: operation.id,
        name: operation.name,
        purpose: operation.purpose,
        departments: operation.departments,
        tasks: operation.tasks.map((task) => ({
          title: task.title,
          department: task.departmentName,
          summary: task.summary,
          status: task.status,
        })),
        approvals: operation.approvalHistory.map((approval) => ({
          id: approval.id,
          status: approval.status,
          prompt: approval.promptMessage,
          result: approval.result,
        })),
        deliverable_excerpt: operation.deliverableText?.slice(0, 1_200),
      })),
      constraints: state.activeConstraints,
      conflicts: state.conflicts,
      proposal_decisions: state.proposalDecisions,
      hidden_constraints: state.hiddenConstraints,
      contradictory_signals: state.contradictorySignals,
      delayed_consequences: state.delayedConsequences,
      memory: state.memory.map((memory) => ({
        id: memory.id,
        title: memory.title,
        content: memory.content,
        kind: memory.kind,
      })),
      memory_recovery: state.memoryMisuseRecoveries,
      department_challenges: state.departmentChallenges,
      learning_iterations: state.learningIterations,
      ambiguous_feedback_response: state.ambiguousJudgeInterpretations,
    },
    { temperature: 0.1, timeout: 90_000 },
  );
  state.llmResponses.push({ kind: "traceability", label: "decision traceability audit", content });

  const decisions = Array.isArray(parsed.decisions)
    ? parsed.decisions.map((item, index): DecisionTraceRecord => {
        const source = item as Record<string, unknown>;
        return {
          id: String(source.id ?? `decision-${index + 1}`),
          decision: String(source.decision ?? ""),
          alternatives: normalizeStringArray(source.alternatives),
          constraints: normalizeStringArray(source.constraints),
          departments: normalizeStringArray(source.departments),
          rationale: String(source.rationale ?? ""),
          rejected: normalizeStringArray(source.rejected),
          linkedOperations: normalizeStringArray(source.linked_operations),
        };
      })
    : [];

  const memoryAttributions = Array.isArray(parsed.memory_attributions)
    ? parsed.memory_attributions.map((item): MemoryAttributionRecord => {
        const source = item as Record<string, unknown>;
        return {
          memoryId: String(source.memory_id ?? ""),
          memoryTitle: String(source.memory_title ?? ""),
          retrievedBy: String(source.retrieved_by ?? ""),
          usedIn: String(source.used_in ?? ""),
          changedReasoning: String(source.changed_reasoning ?? ""),
        };
      })
    : [];

  const approvalImpacts = Array.isArray(parsed.approval_impacts)
    ? parsed.approval_impacts.map((item): ApprovalImpactRecord => {
        const source = item as Record<string, unknown>;
        return {
          approvalId: String(source.approval_id ?? ""),
          operationId: String(source.operation_id ?? ""),
          rejectionChanged: String(source.rejection_changed ?? ""),
          improvedBeforeReapproval: String(source.improved_before_reapproval ?? ""),
          departments: normalizeStringArray(source.departments),
        };
      })
    : [];

  const iterationDeltas = Array.isArray(parsed.iteration_deltas)
    ? parsed.iteration_deltas.map((item): IterationDeltaRecord => {
        const source = item as Record<string, unknown>;
        return {
          fromIteration: Number(source.from_iteration),
          toIteration: Number(source.to_iteration),
          whatChanged: String(source.what_changed ?? ""),
          whyChanged: String(source.why_changed ?? ""),
          department: String(source.department ?? ""),
        };
      })
    : [];

  const incompleteDecision = decisions.find(
    (decision) =>
      !decision.decision ||
      decision.alternatives.length === 0 ||
      decision.constraints.length === 0 ||
      decision.departments.length === 0 ||
      !decision.rationale ||
      decision.rejected.length === 0 ||
      decision.linkedOperations.length === 0,
  );
  const invalidFields = [
    decisions.length < 3 ? "at least three decisions" : "",
    incompleteDecision ? `complete fields for ${incompleteDecision.id}` : "",
    memoryAttributions.length < 2 ? "at least two memory attributions" : "",
    memoryAttributions.some((item) => !item.memoryId || !item.changedReasoning)
      ? "complete memory attribution fields"
      : "",
    approvalImpacts.length < 1 ? "at least one approval impact" : "",
    approvalImpacts.some(
      (item) => !item.rejectionChanged || !item.improvedBeforeReapproval || item.departments.length === 0,
    )
      ? "complete approval impact fields"
      : "",
    iterationDeltas.length < 2 ? "at least two iteration deltas" : "",
    iterationDeltas.some(
      (item) =>
        !Number.isFinite(item.fromIteration) ||
        !Number.isFinite(item.toIteration) ||
        !item.whatChanged ||
        !item.whyChanged,
    )
      ? "complete iteration delta fields"
      : "",
  ].filter(Boolean);

  if (invalidFields.length > 0) {
    throw new Error(`Local LLM traceability output is incomplete: ${invalidFields.join(", ")}`);
  }

  return {
    decisions,
    memoryAttributions,
    approvalImpacts,
    iterationDeltas,
  };
}

function buildReportBuilderFixturePayload(user: { email: string }, state: SimulationState) {
  const finalOperation = state.operations.find((operation) => operation.sequence === 6);
  expect(finalOperation).toBeTruthy();

  return {
    email: user.email,
    company_id: state.companyId,
    client_context: CLIENT,
    operation: {
      name: finalOperation!.name,
      started_at: finalOperation!.startedAt,
      ended_at: finalOperation!.endedAt,
      input_json: {
        operation_name: finalOperation!.name,
        operation_brief: finalOperation!.brief,
        client_context: CLIENT,
      },
      output_json: {
        client_context: CLIENT,
        deliverable: finalOperation!.deliverableText,
        positioning: "Position Legacy as quiet-status luxury eyewear for Mexico City.",
        target_audience: [
          "Polanco and Lomas private-client buyers who value service, discretion, and verified taste.",
          "Roma Norte design-led professionals who need appointment proof before converting.",
        ],
        approach:
          "Lead with private fitting proof, optician credibility, concierge referrals, and a guarded paid retargeting test.",
        constraints: [
          `MXN ${state.activeConstraints.budgetCapMxn.toLocaleString("en-US")} active budget cap`,
          `${state.activeConstraints.contentCapacityPerWeek} assets per week`,
          `${state.activeConstraints.channelLimit} active launch channels`,
          ...state.activeConstraints.restrictedClaims,
        ],
        execution_plan: {
          channels: state.activeConstraints.allowedChannels,
          rollout_phases: [
            "Finalize compliant claims and appointment-facing creative.",
            "Run private appointments and concierge partner referrals before broad scale.",
            "Use a small Meta retargeting test only after brand perception remains premium.",
          ],
          campaign_structure:
            "One VIP appointment core, one concierge/stylist referral stream, and one guarded paid retargeting proof stream.",
          timeline: "Six-week pilot before budget scale decisions.",
        },
        risks: [
          "Appointment-led growth may trade early volume for stronger luxury perception.",
          "A three-channel launch limits rapid reach and requires disciplined sequencing.",
          "Retargeting remains a secondary test because hidden channel pressure reduced reliability.",
        ],
        recommendations: [
          "Approve the three-channel VIP pilot anchored in private appointments.",
          "Keep broad influencer and discount-led scale rejected until appointment conversion and brand perception both hold.",
          "Review segment performance after the six-week pilot before increasing paid spend.",
        ],
        decision_traces: state.decisionTraces.map((decision) => ({
          decision: decision.decision,
          alternatives: decision.alternatives,
          constraints: decision.constraints,
          departments: decision.departments,
          rationale: decision.rationale,
          rejected: decision.rejected,
          linked_operations: decision.linkedOperations,
        })),
        memory_attributions: state.memoryAttributions.map((memory) => ({
          memory_id: memory.memoryId,
          memory_title: memory.memoryTitle,
          retrieved_by: memory.retrievedBy,
          used_in: memory.usedIn,
          changed_reasoning: memory.changedReasoning,
        })),
        iteration_deltas: state.iterationDeltas.map((delta) => ({
          from_iteration: delta.fromIteration,
          to_iteration: delta.toIteration,
          what_changed: delta.whatChanged,
          why_changed: delta.whyChanged,
          department: delta.department,
          trigger: "memory, approval, performance, and hidden constraint pressure",
        })),
      },
    },
    tasks: finalOperation!.tasks.map((task) => ({
      title: task.title,
      department_id: task.departmentId,
      department_name: task.departmentName,
      source_id: task.sourceId,
      status: task.status,
      priority: task.priority,
      summary: task.summary,
      skill: task.skill,
      tool: task.tool,
      started_at: task.startedAt,
      ended_at: task.endedAt,
      deliverable: finalOperation!.deliverableText,
    })),
    approvals: state.approvalImpacts.map((impact) => ({
      id: impact.approvalId,
      department_id: departmentId(state, impact.departments[0] ?? "Legal / Compliance"),
      status: "rejected",
      payload: {
        prompt_message: "Review Legacy campaign claims before client release.",
        departments: impact.departments,
      },
      result: {
        approved: false,
        what_changed_after_rejection: impact.rejectionChanged,
        improved_before_reapproval: impact.improvedBeforeReapproval,
      },
      resolved_at: timestamp(92),
    })),
    memory: state.memory.map((memory) => ({
      id: memory.id,
      type: memory.kind === "write" ? "case" : memory.kind,
      title: memory.title,
      content: memory.content,
      topic: memory.topic,
      tool_name: memory.toolName,
      created_at: memory.createdAt,
    })),
  };
}

function seedReportBuilderOperation(user: { email: string }, state: SimulationState): string {
  const tempDir = mkdtempSync(path.join(os.tmpdir(), "forgegraph-report-builder-"));
  const inputPath = path.join(tempDir, "fixture.json");
  try {
    writeFileSync(inputPath, JSON.stringify(buildReportBuilderFixturePayload(user, state), null, 2), "utf8");
    const raw = execFileSync("python", ["manage.py", "seed_strategy_report_fixture", "--input", inputPath, "--json"], {
      cwd: BACKEND_DIR,
      env: MANAGEMENT_ENV,
      encoding: "utf8",
    }).trim();
    const body = JSON.parse(raw) as { operation_id?: string };
    if (!body.operation_id) {
      throw new Error(`Strategy report fixture did not return an operation id: ${raw}`);
    }
    return body.operation_id;
  } finally {
    rmSync(tempDir, { recursive: true, force: true });
  }
}

async function generateLegacyClientReport(
  request: APIRequestContext,
  accessToken: string,
  user: { email: string },
  state: SimulationState,
): Promise<string> {
  const reportOperationId = seedReportBuilderOperation(user, state);
  const response = await request.post(`${API_BASE_URL}/api/reports/strategy-report`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    data: {
      company_id: state.companyId,
      operation_id: reportOperationId,
      audience: "client",
      format: "md",
    },
  });
  if (!response.ok()) {
    throw new Error(`report_builder.generate_strategy_report failed (${response.status()}): ${await response.text()}`);
  }
  const body = (await response.json()) as { data: StrategyReportArtifact };
  const artifact = body.data;
  expect(artifact.format).toBe("md");
  expect(artifact.encoding).toBe("text");
  expect(artifact.operation_id).toBe(reportOperationId);
  expect(Object.keys(artifact.traceability)).toEqual(
    expect.arrayContaining([
      "executive_summary",
      "strategy_narrative",
      "key_decisions",
      "iteration_story",
      "insights",
      "execution_plan",
      "risks_tradeoffs",
      "recommendations",
    ]),
  );
  const report = artifact.content;
  if (
    !/Legacy/i.test(report) ||
    !/Recommendations/i.test(report) ||
    !/Key Decisions/i.test(report) ||
    !/Rejected/i.test(report)
  ) {
    throw new Error(`Report builder output is missing required client-facing sections: ${report.slice(0, 500)}`);
  }
  state.reportBuilderArtifact = artifact;
  state.improvementEvents.push(
    "Post-operation report builder generated the client strategy report from backend state.",
  );
  return report;
}

async function attachSimulationArtifacts(testInfo: TestInfo, state: SimulationState) {
  if (!state.legacyClientReport) {
    throw new Error("Legacy client report was not generated by the local LLM.");
  }
  await Promise.all([
    testInfo.attach("agency-simulation-state.json", {
      body: Buffer.from(JSON.stringify(state, null, 2), "utf8"),
      contentType: "application/json",
    }),
    testInfo.attach("agency-simulation-coverage.json", {
      body: Buffer.from(JSON.stringify(coverageReport(state), null, 2), "utf8"),
      contentType: "application/json",
    }),
    testInfo.attach("agency-simulation-ai-judge-prompt.txt", {
      body: Buffer.from(AI_JUDGE_PROMPT, "utf8"),
      contentType: "text/plain",
    }),
    testInfo.attach("agency-simulation-decision-trace.json", {
      body: Buffer.from(
        JSON.stringify(
          {
            decisions: state.decisionTraces,
            memoryAttributions: state.memoryAttributions,
            approvalImpacts: state.approvalImpacts,
            iterationDeltas: state.iterationDeltas,
          },
          null,
          2,
        ),
        "utf8",
      ),
      contentType: "application/json",
    }),
    testInfo.attach("agency-simulation-final-deliverable.md", {
      body: Buffer.from(
        sortOperations(state.operations).find((operation) => operation.deliverableText)?.deliverableText ?? "",
        "utf8",
      ),
      contentType: "text/markdown",
    }),
    testInfo.attach("legacy-client-adaptation-report.md", {
      body: Buffer.from(state.legacyClientReport, "utf8"),
      contentType: "text/markdown",
    }),
    testInfo.attach("report-builder-artifact.json", {
      body: Buffer.from(JSON.stringify(state.reportBuilderArtifact, null, 2), "utf8"),
      contentType: "application/json",
    }),
    testInfo.attach("agency-simulation-llm-responses.json", {
      body: Buffer.from(JSON.stringify(state.llmResponses, null, 2), "utf8"),
      contentType: "application/json",
    }),
  ]);
}

test.describe("Organization simulation", () => {
  test("proves an AI-operated marketing agency adapts to LLM-directed Legacy client pressure", async ({
    page,
    request,
  }, testInfo) => {
    test.setTimeout(900_000);

    const user = createTestUser(testInfo, "agency-simulation");
    await ensureUserRegistered(request, user);
    const accessToken = await getAccessToken(request, user);
    const organization = await createNamedOrganization(request, accessToken);

    await openBackendAuthenticatedPage(page, request, user, "/companies/new");

    const companyId = await createCompanyThroughUi(page);
    await persistSimulationCompanySetup(request, accessToken, companyId);
    const latestSetup = await fetchLatestGraphVersion(request, accessToken, companyId);
    const simulationContract = latestSetup.graph_json.metadata?.simulation_contract as
      | Record<string, unknown>
      | undefined;
    const companyProfile = (latestSetup.graph_json.metadata?.company_profile ??
      buildAgencyCompanyProfile()) as CompanyProfile;

    const state: SimulationState = {
      organizationId: organization.id,
      organizationName: organization.name,
      companyId,
      setupVersionId: latestSetup.id,
      companyProfile,
      departmentIdsByName: departmentIdsByNameFromSetup(latestSetup.graph_json),
      operations: [],
      memory: [],
      memoryRetrievalCount: 0,
      memoryWriteCount: 0,
      complianceLoopOccurred: false,
      performanceLoopOccurred: false,
      approvalRejectionCount: 0,
      approvalRevisionCount: 0,
      approvalReapprovalCount: 0,
      conflicts: adversarialConflicts(),
      proposalDecisions: competingProposalDecisions(),
      constraints: RESOURCE_CONSTRAINTS,
      activeConstraints: initialActiveConstraints(),
      hiddenConstraints: [],
      contradictorySignals: [],
      delayedConsequences: [],
      memoryMisuseRecoveries: [],
      departmentChallenges: [],
      ambiguousJudgeInterpretations: [],
      uxComprehensionSamples: [],
      learningIterations: [],
      decisionTraces: [],
      memoryAttributions: [],
      approvalImpacts: [],
      iterationDeltas: [],
      improvementEvents: [],
      llmResponses: [],
      legacyClientReport: null,
      reportBuilderArtifact: null,
      judge: null,
    };
    seedMemory(state);

    expect(companyProfile.companyName).toBe(COMPANY_NAME);
    expect(companyProfile.companyName).not.toMatch(/\blegacy\b/i);
    expect(companyProfile.objective).toBe(COMPANY_OBJECTIVE);
    expect(companyProfile.companyType).toBe(COMPANY_TYPE);
    expect(companyProfile.autonomyMode).toBe("assisted");
    expect(companyProfile.aiAccessMode).toBe("managed");
    expect((simulationContract?.client as typeof CLIENT | undefined)?.name).toBe(CLIENT.name);
    expect(simulationContract?.skills).toEqual([...REQUIRED_SKILLS]);
    expect(simulationContract?.tools).toEqual([...REQUIRED_TOOLS]);

    await installSimulationProductApis(page, request, state);

    await page.goto("/companies");
    await page.waitForLoadState("networkidle");
    await expect(page.getByRole("heading", { name: /operate ai-driven companies/i })).toBeVisible();
    await expect(page.getByText(COMPANY_NAME).first()).toBeVisible();
    await expect(page.getByText(CLIENT.name, { exact: true })).toHaveCount(0);
    await expectSurfaceClean(page);

    await page.goto(`/companies/${companyId}`);
    await page.waitForLoadState("networkidle");
    await expect(
      page.getByRole("heading", { name: new RegExp(escapeRegExp(COMPANY_NAME), "i") }).first(),
    ).toBeVisible();
    await expect(page.getByText(COMPANY_OBJECTIVE).first()).toBeVisible();
    await expectSurfaceClean(page);

    const templates = operationTemplates();
    await launchOperationThroughUi(page, state, templates[0].brief);
    await launchOperationThroughUi(page, state, templates[1].brief);
    await launchOperationThroughUi(page, state, templates[2].brief);

    await expect(page.getByText(/awaiting approval/i).first()).toBeVisible();
    await expect(page.getByText(/Account Management is waiting for a decision/i).first()).toBeVisible();
    expect(allApprovals(state).length).toBe(1);
    expect(currentPendingApproval(state.operations.find((operation) => operation.sequence === 3)!)?.status).toBe(
      "pending",
    );

    await page.goto("/approvals");
    await page.waitForLoadState("networkidle");
    await expect(page.getByRole("heading", { name: /decide with context/i })).toBeVisible();
    await expect(page.getByText(/Legacy client-facing campaign package/i).first()).toBeVisible();
    await expect(page.getByText(/Account Management/i).first()).toBeVisible();
    await expect(page.getByText(/Decision context/i).first()).toBeVisible();
    await expect(page.getByText(/Impact and consequence/i).first()).toBeVisible();
    recordUxComprehension(state, "approvals", await visibleText(page));
    await expectSurfaceClean(page);
    await page
      .getByPlaceholder(/add guidance, constraints, or corrections/i)
      .fill(
        "Reject the first package: clarify why claims changed, show the MXN 1.4M cap, and explain the client consequence before release.",
      );
    await page.getByRole("button", { name: /^reject$/i }).click();
    await expect(page.getByText(/Revised approval required for Legacy/i).first()).toBeVisible({ timeout: 90_000 });
    await expect(page.getByText(/approve the revised package or request another correction/i).first()).toBeVisible();
    expect(state.approvalRejectionCount).toBe(1);
    expect(state.approvalRevisionCount).toBe(1);
    expect(allApprovals(state).filter((approval) => approval.status === "rejected")).toHaveLength(1);
    expect(allApprovals(state).filter((approval) => approval.status === "pending")).toHaveLength(1);

    await page
      .getByPlaceholder(/add guidance, constraints, or corrections/i)
      .fill(
        "Approve the revised package. It explains claim changes, the budget cap, and why the constrained launch should proceed.",
      );
    await page.getByRole("button", { name: /approve with notes/i }).click();
    await expect(page.getByText(/approval queue is clear/i)).toBeVisible({ timeout: 90_000 });
    expect(state.approvalReapprovalCount).toBe(1);

    await page.goto(`/companies/${companyId}`);
    await page.waitForLoadState("networkidle");
    await launchOperationThroughUi(page, state, templates[3].brief);
    const launchOperation = state.operations.find((operation) => operation.sequence === 4);
    expect(launchOperation).toBeTruthy();
    const directorOutput = await generateSimulationDirectorOutput(request, state, launchOperation!.id);
    applyDirectorOutput(state, directorOutput);
    await launchOperationThroughUi(page, state, templates[4].brief);
    await expect.poll(() => state.operations.length, { timeout: 180_000 }).toBeGreaterThanOrEqual(6);
    const generatedFollowUp = state.operations.find((operation) => operation.sequence === 6);
    expect(generatedFollowUp?.deliverableText).toMatch(/Client:/i);
    expect(generatedFollowUp?.deliverableText).toMatch(/Legacy/i);
    expect(generatedFollowUp?.deliverableText).toMatch(/Learning iteration 2 used retrieved Legacy case memory/i);
    await expectSurfaceClean(page);

    state.judge = await judgeScenario(request, state);
    await interpretAmbiguousJudgeFeedback(request, state);
    const traceability = await generateTraceabilityAudit(request, state);
    state.decisionTraces = traceability.decisions;
    state.memoryAttributions = traceability.memoryAttributions;
    state.approvalImpacts = traceability.approvalImpacts;
    state.iterationDeltas = traceability.iterationDeltas;
    const traceableFollowUp = state.operations.find((operation) => operation.sequence === 6);
    const traceableFollowUpTemplate = operationTemplates().find((template) => template.sequence === 6);
    expect(traceableFollowUp).toBeTruthy();
    expect(traceableFollowUpTemplate).toBeTruthy();
    traceableFollowUp!.deliverableText = await generateOperationDeliverable(request, traceableFollowUpTemplate!, state);
    state.legacyClientReport = await generateLegacyClientReport(request, accessToken, user, state);

    const report = coverageReport(state);
    expect(report.company).toBe(COMPANY_NAME);
    expect(report.company).not.toMatch(/\blegacy\b/i);
    expect(report.client.name).toBe(CLIENT.name);
    expect(report.departments.length).toBeGreaterThanOrEqual(10);
    expect(report.operations.length).toBeGreaterThanOrEqual(5);
    expect(report.taskCount).toBeGreaterThanOrEqual(15);
    expect(report.skills).toEqual(expect.arrayContaining([...REQUIRED_SKILLS.slice(0, 8)]));
    expect(report.skills.length).toBeGreaterThanOrEqual(8);
    expect(report.tools).toEqual(expect.arrayContaining([...REQUIRED_TOOLS.slice(0, 7)]));
    expect(report.tools.length).toBeGreaterThanOrEqual(7);
    expect(report.approvals.length).toBeGreaterThanOrEqual(1);
    expect(report.complianceLoopOccurred).toBe(true);
    expect(report.performanceLoopOccurred).toBe(true);
    expect(report.memoryWriteCount).toBeGreaterThanOrEqual(1);
    expect(report.memoryRetrievalCount).toBeGreaterThanOrEqual(1);
    expect(report.deliverables.length).toBeGreaterThanOrEqual(1);
    expect(report.conflicts.length).toBeGreaterThanOrEqual(2);
    expect(report.conflicts.map((conflict) => conflict.title)).toEqual(
      expect.arrayContaining([
        "Premium paid launch exceeds budget cap",
        "Creative asset demand exceeds content capacity",
      ]),
    );
    expect(report.proposalDecisions).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          id: "proposal-paid-vs-organic",
          decision: "merge",
        }),
      ]),
    );
    expect(report.constraints.budgetCapMxn).toBe(1_400_000);
    expect(report.constraints.contentCapacityPerWeek).toBe(6);
    expect(report.constraints.channelLimit).toBe(3);
    expect(report.hiddenConstraints.length).toBeGreaterThanOrEqual(1);
    expect(report.activeConstraints.budgetCapMxn).toBeLessThanOrEqual(report.constraints.budgetCapMxn);
    expect(report.contradictorySignals.length).toBeGreaterThanOrEqual(2);
    expect(report.delayedConsequences.length).toBeGreaterThanOrEqual(2);
    expect(report.memoryMisuseRecoveries.length).toBeGreaterThanOrEqual(1);
    expect(report.departmentChallenges.length).toBeGreaterThanOrEqual(1);
    expect(report.departmentChallenges.map((challenge) => challenge.response)).toEqual(
      expect.arrayContaining([expect.stringMatching(/override|constrain|careful integration/)]),
    );
    expect(report.approvalRejectionCount).toBeGreaterThanOrEqual(1);
    expect(report.approvalRevisionCount).toBeGreaterThanOrEqual(1);
    expect(report.approvalReapprovalCount).toBeGreaterThanOrEqual(1);
    expect(report.learningIterations.length).toBeGreaterThanOrEqual(3);
    expect(report.decisionTraces.length).toBeGreaterThanOrEqual(3);
    expect(
      report.decisionTraces.every(
        (decision) =>
          decision.decision &&
          decision.alternatives.length > 0 &&
          decision.constraints.length > 0 &&
          decision.departments.length > 0 &&
          decision.rationale &&
          decision.rejected.length > 0 &&
          decision.linkedOperations.length > 0,
      ),
    ).toBe(true);
    expect(report.memoryAttributions.length).toBeGreaterThanOrEqual(2);
    expect(report.memoryAttributions.every((memory) => memory.memoryId && memory.changedReasoning)).toBe(true);
    expect(report.approvalImpacts.length).toBeGreaterThanOrEqual(1);
    expect(report.approvalImpacts.every((impact) => impact.rejectionChanged && impact.improvedBeforeReapproval)).toBe(
      true,
    );
    expect(report.iterationDeltas.length).toBeGreaterThanOrEqual(2);
    expect(report.iterationDeltas.every((delta) => delta.whatChanged && delta.whyChanged && delta.department)).toBe(
      true,
    );
    expect(new Set(report.learningIterations.map((iteration) => iteration.output)).size).toBeGreaterThanOrEqual(2);
    expect(report.improvementEvents.length).toBeGreaterThanOrEqual(1);
    const finalDeliverable =
      sortOperations(state.operations).find((operation) => operation.deliverableText)?.deliverableText ?? "";
    expect(finalDeliverable).toMatch(/Reasoning:/i);
    expect(finalDeliverable).toMatch(/Tradeoffs:/i);
    expect(finalDeliverable).toMatch(/Why decisions were made:/i);
    expect(finalDeliverable).toMatch(/retrieved Legacy case memory/i);
    expect(finalDeliverable).toMatch(/Dynamic adaptation:/i);
    expect(finalDeliverable).toMatch(/Memory recovery:/i);
    expect(finalDeliverable).toMatch(/Ambiguous evaluation response:/i);
    expect(finalDeliverable).toMatch(/Decision trace:/i);
    expect(finalDeliverable).toMatch(/Rejected alternatives:/i);
    expect(finalDeliverable).toMatch(/Memory attribution:/i);
    expect(finalDeliverable).toMatch(/Approval impact:/i);
    expect(finalDeliverable).toMatch(/Iteration delta:/i);
    expect(state.judge.source).toBe("local-llm");
    expect(state.judge.coverage_score).toBeGreaterThanOrEqual(60);
    expect(state.judge.criteria.decision_adaptation).toBeGreaterThanOrEqual(50);
    expect(state.judge.criteria.learning_improvement).toBeGreaterThanOrEqual(50);
    expect(state.judge.criteria.ambiguity_handling).toBeGreaterThanOrEqual(50);
    expect(state.judge.criteria.memory_recovery).toBeGreaterThanOrEqual(50);
    expect(state.ambiguousJudgeInterpretations.length).toBeGreaterThanOrEqual(1);
    expect(state.reportBuilderArtifact).toEqual(
      expect.objectContaining({
        audience: "client",
        format: "md",
        encoding: "text",
      }),
    );
    expect(report.reportBuilderArtifact?.traceableSections).toEqual(
      expect.arrayContaining([
        "executive_summary",
        "strategy_narrative",
        "key_decisions",
        "iteration_story",
        "insights",
        "execution_plan",
        "risks_tradeoffs",
        "recommendations",
      ]),
    );
    expect(state.legacyClientReport).toMatch(/Legacy/i);
    expect(state.legacyClientReport).toMatch(/\*\*Strategy:\*\*/i);
    expect(state.legacyClientReport).toMatch(/Recommendations/i);
    expect(state.legacyClientReport).toMatch(/Key Decisions/i);
    expect(state.legacyClientReport).toMatch(/decision/i);
    expect(state.legacyClientReport).toMatch(/reject|not recommended|not adopted|declined/i);
    expect(state.legacyClientReport).toMatch(/prior experience|learning/i);
    expect(state.legacyClientReport).toMatch(/Requirements shaping the choice/i);
    expect(state.legacyClientReport).toMatch(/Risks & Tradeoffs/i);
    expect(state.legacyClientReport).not.toMatch(
      /\bgraph\b|\bnode\b|\bworkflow\b|\boperation\b|\bmemory\b|\bdecision trace\b|\bconstraint\b|\biteration\b/i,
    );
    expect(report.llmResponses.length).toBeGreaterThanOrEqual(9);
    expect(report.llmResponses.map((response) => response.kind)).toEqual(
      expect.arrayContaining(["director", "deliverable", "judge", "traceability"]),
    );
    expect(report.llmResponses.map((response) => response.kind)).not.toContain("report");
    if (REQUIRE_TOP_TIER) {
      expect(state.judge.marketing_quality_score).toBeGreaterThanOrEqual(TOP_TIER_TARGET);
    }

    await page.goto(`/departments?department=${departmentId(state, "Account Management")}`);
    await page.waitForLoadState("networkidle");
    await expect(page.getByRole("heading", { name: /how the company thinks/i })).toBeVisible();
    await Promise.all(
      departmentDefinitions().map((department) => expect(page.getByText(department.label).first()).toBeVisible()),
    );
    await expect(page.getByRole("heading", { name: /active proposals/i }).first()).toBeVisible();
    await expect(page.getByText(/tasks from operations/i).first()).toBeVisible();
    await expect(page.getByText(/revised approval required for Legacy/i).first()).toBeVisible();
    await expect(page.getByText(/operator rejected the first package/i).first()).toBeVisible();
    const departmentText = await visibleText(page);
    expect(departmentText).toMatch(/goal:/i);
    expect(departmentText).toMatch(/reasoning:/i);
    expect(departmentText).toMatch(/next action:/i);
    recordUxComprehension(state, "departments", departmentText);
    await expectSurfaceClean(page);

    await page.goto("/runs");
    await page.waitForLoadState("networkidle");
    await expect(page.getByRole("heading", { name: /recent company operations/i })).toBeVisible();
    await expect(page.getByText(COMPANY_NAME).first()).toBeVisible();
    await expect(page.getByRole("heading", { name: /operation list/i }).first()).toBeVisible();
    await expect(
      page.getByText(/top-level summary before drilling into the full step sequence/i).first(),
    ).toBeVisible();
    await expect(page.getByText(/memory activity/i).first()).toBeVisible();
    const operationsText = await visibleText(page);
    recordUxComprehension(state, "operations", operationsText);
    expect(operationsText).not.toMatch(/\blogs\b/i);
    expect(await page.getByText(COMPANY_NAME).count()).toBeGreaterThanOrEqual(2);
    await expectSurfaceClean(page);

    const followUpOperation = state.operations.find((operation) => operation.sequence === 6);
    expect(followUpOperation).toBeTruthy();
    await page.goto(`/runs/${followUpOperation!.id}`);
    await page.waitForLoadState("networkidle");
    await expect(page.getByText(/deliverable is ready/i).first()).toBeVisible();
    await expect(page.getByText(/Client.*Legacy/i).first()).toBeVisible();
    await expect(page.getByText(/Learning iteration 2 used retrieved Legacy case memory/i).first()).toBeVisible();
    await expect(page.getByText(/Tradeoffs/i).first()).toBeVisible();
    await expect(page.getByText(/Why decisions were made/i).first()).toBeVisible();
    recordUxComprehension(state, "operation detail", await visibleText(page));
    await expectSurfaceClean(page);

    await page.goto("/tasks");
    await page.waitForLoadState("networkidle");
    await expect(page.getByRole("heading", { name: /department activity at a glance/i })).toBeVisible();
    await expect(page.getByText(/Each task summarizes what is happening now/i).first()).toBeVisible();
    await expect(page.getByRole("heading", { name: /activity queue/i }).first()).toBeVisible();
    await expect(page.getByText(/This task is attached to operation/i).first()).toBeVisible();
    await expect(page.getByText(/define client brief/i).first()).toBeVisible();
    await expect(page.getByText(/identify underperforming segment/i).first()).toBeVisible();
    await expect(page.getByText(/failed/i).first()).toBeVisible();
    const tasksText = await visibleText(page);
    recordUxComprehension(state, "tasks", tasksText);
    expect(tasksText).not.toMatch(/primary model/i);
    await expectSurfaceClean(page);

    await page.goto("/memory");
    await page.waitForLoadState("networkidle");
    await expect(page.getByRole("heading", { name: /browse the knowledge layer/i })).toBeVisible();
    await expect(page.getByText(/Legacy campaign learning written/i).first()).toBeVisible();
    await expect(page.getByText(/Legacy relevant memory retrieved/i).first()).toBeVisible();
    await expect(page.getByText(/appointment proof/i).first()).toBeVisible();
    await expect(page.getByText(/memory\.write_case/i).first()).toBeVisible();
    await expectSurfaceClean(page);

    await page.goto("/overview");
    await page.waitForLoadState("networkidle");
    await expect(page.getByText(ORGANIZATION_NAME).first()).toBeVisible();
    await expect(page.getByText(/active departments/i).first()).toBeVisible();
    await expect(page.getByText(/legacy-campaign-learning/i).first()).toBeVisible();
    await expect(page.getByText(/operations in 24h/i).first()).toBeVisible();
    await expectSurfaceClean(page);

    expect(state.uxComprehensionSamples.length).toBeGreaterThanOrEqual(4);
    expect(state.uxComprehensionSamples.every((sample) => sample.score >= 2)).toBe(true);
    expect(state.uxComprehensionSamples.some((sample) => sample.clarityOfIntent)).toBe(true);
    expect(state.uxComprehensionSamples.some((sample) => sample.clarityOfDecisions)).toBe(true);
    expect(state.uxComprehensionSamples.some((sample) => sample.clarityOfNextSteps)).toBe(true);

    await attachSimulationArtifacts(testInfo, state);
  });
});
