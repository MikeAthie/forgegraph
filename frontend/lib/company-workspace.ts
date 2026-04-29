import { END_NODE_ID, NODE_TYPES, START_NODE_ID, type GraphJson } from "./graph-types";
import type { GraphDetail, GraphListItem, NodeRunItem, RunDetail, RunListItem } from "./api";

export type CompanyAutonomyMode = "manual" | "assisted" | "autonomous";
export type CompanyAIAccessMode = "managed" | "byok";

export type CompanyDepartment = {
  id: string;
  label: string;
  responsibility: string;
  tools: string[];
  category: "department" | "skill";
};

export type CompanyProfile = {
  schema: "company_workspace.v1";
  companyName: string;
  companyType: string;
  objective: string;
  autonomyMode: CompanyAutonomyMode;
  aiAccessMode: CompanyAIAccessMode;
  intelligenceProvider: string;
  companyStatus?: string;
  byokCredentialId?: string | null;
  departments: CompanyDepartment[];
  skills: string[];
};

export type CompanyPreset = {
  id: string;
  label: string;
  description: string;
  starterObjective: string;
  departments: CompanyDepartment[];
  skills: string[];
};

export type CompanyFailure = {
  title: string;
  summary: string;
  nextSteps: string[];
  technicalDetails?: string | null;
  actionHint?: "retry" | "switch_ai_access_mode" | "edit_objective";
};

const departmentCatalog: CompanyDepartment[] = [
  {
    id: "strategy-department",
    label: "Strategy Department",
    responsibility: "Shapes goals, priorities, and the operating plan for the company.",
    tools: ["Planning", "Research"],
    category: "department",
  },
  {
    id: "operations-desk",
    label: "Operations Desk",
    responsibility: "Coordinates recurring work and keeps handoffs moving across the company.",
    tools: ["Coordination", "Routing"],
    category: "department",
  },
  {
    id: "delivery-management",
    label: "Delivery Management",
    responsibility: "Owns delivery plans, deadlines, and execution quality from kickoff to completion.",
    tools: ["Scheduling", "Quality control"],
    category: "department",
  },
  {
    id: "client-success",
    label: "Client Success",
    responsibility: "Packages outcomes for customers or stakeholders and tracks follow-through on commitments.",
    tools: ["Handoffs", "Follow-up"],
    category: "department",
  },
  {
    id: "research-analysis",
    label: "Research & Analysis",
    responsibility: "Investigates questions, analyzes inputs, and turns findings into recommendations.",
    tools: ["Research", "Analysis"],
    category: "department",
  },
  {
    id: "business-development",
    label: "Business Development",
    responsibility: "Finds pipeline opportunities, shapes outreach, and keeps growth opportunities moving.",
    tools: ["Outreach", "Qualification"],
    category: "department",
  },
  {
    id: "finance-admin",
    label: "Finance & Admin",
    responsibility: "Keeps budgets, approvals, and operating paperwork organized and on track.",
    tools: ["Budgeting", "Administration"],
    category: "department",
  },
  {
    id: "compliance-review",
    label: "Compliance Review",
    responsibility: "Reviews work for policy, legal, or risk-sensitive requirements before release.",
    tools: ["Review", "Risk checks"],
    category: "department",
  },
  {
    id: "document-drafting",
    label: "Document Drafting",
    responsibility: "Turns plans and findings into clear written deliverables, briefs, and updates.",
    tools: ["Drafting", "Editing"],
    category: "skill",
  },
  {
    id: "creative-production",
    label: "Creative Production",
    responsibility: "Produces presentation assets, creative materials, and polished delivery-ready outputs.",
    tools: ["Asset creation", "Packaging"],
    category: "department",
  },
];

export const companyPresets: CompanyPreset[] = [
  {
    id: "general-company",
    label: "General Company",
    description:
      "A broad starting point for almost any business. Use this if you want flexibility or you are not sure which category fits yet.",
    starterObjective: "Set up a reliable operating rhythm and deliver a clear first result for the business.",
    departments: [departmentCatalog[0], departmentCatalog[1], departmentCatalog[2], departmentCatalog[3]],
    skills: ["Planning", "Coordination", "Reporting", "Quality assurance"],
  },
  {
    id: "professional-services",
    label: "Professional Services",
    description:
      "A good fit for consulting agencies, legal teams, advisory firms, and service businesses that deliver client work.",
    starterObjective: "Run client delivery smoothly and produce decision-ready work with clear follow-through.",
    departments: [
      departmentCatalog[0],
      departmentCatalog[2],
      departmentCatalog[3],
      departmentCatalog[4],
      departmentCatalog[7],
    ],
    skills: ["Research synthesis", "Document drafting", "Client communication", "Quality assurance"],
  },
  {
    id: "growth-marketing",
    label: "Growth & Marketing",
    description:
      "A company pattern for growth teams, marketing groups, and outbound programs that need strategy, messaging, and campaign follow-through.",
    starterObjective: "Plan, produce, and improve a repeatable growth motion with visible outcomes.",
    departments: [
      departmentCatalog[0],
      departmentCatalog[4],
      departmentCatalog[5],
      departmentCatalog[8],
      departmentCatalog[9],
    ],
    skills: ["Campaign planning", "Messaging", "Creative review", "Performance analysis"],
  },
  {
    id: "operations-delivery",
    label: "Operations & Delivery",
    description:
      "A strong starting point for construction managers, field operations, project delivery teams, and execution-heavy businesses.",
    starterObjective: "Coordinate delivery, reduce delays, and keep work moving with fewer handoff gaps.",
    departments: [
      departmentCatalog[1],
      departmentCatalog[2],
      departmentCatalog[3],
      departmentCatalog[6],
      departmentCatalog[7],
    ],
    skills: ["Scheduling", "Estimation", "Quality assurance", "Reporting"],
  },
  {
    id: "research-advisory",
    label: "Research & Advisory",
    description: "A useful pattern for strategy teams, internal research groups, analysts, and advisory organizations.",
    starterObjective: "Investigate the right questions and produce recommendations the business can act on.",
    departments: [departmentCatalog[0], departmentCatalog[4], departmentCatalog[7], departmentCatalog[8]],
    skills: ["Research synthesis", "Recommendation writing", "Stakeholder briefing", "Document review"],
  },
];

export const companySkillCatalog = [
  "Planning",
  "Research synthesis",
  "Document drafting",
  "Client communication",
  "Scheduling",
  "Estimation",
  "Reporting",
  "Performance analysis",
  "Quality assurance",
  "Document review",
  "Tool action routing",
  "Prompt refinement",
];

const skillExplanations: Record<string, string> = {
  Planning: "Turns the goal into a clear operating plan.",
  "Research synthesis": "Pulls findings together into something usable.",
  "Document drafting": "Produces clear written deliverables and briefs.",
  "Client communication": "Packages the work for customers or stakeholders.",
  Scheduling: "Keeps timing, sequence, and handoffs on track.",
  Estimation: "Turns rough work into realistic scopes or timelines.",
  Reporting: "Summarizes progress, results, and next steps.",
  "Performance analysis": "Explains what is working and what needs to change.",
  "Quality assurance": "Checks the work before it moves forward.",
  "Document review": "Reviews written output for gaps and risks.",
  "Tool action routing": "Calls the right system or action at the right time.",
  "Prompt refinement": "Sharpens AI instructions when the task needs it.",
};

const defaultPreset = companyPresets[0];
const presetInferenceSignals: Record<string, string[]> = {
  "professional-services": [
    "consult",
    "client",
    "legal",
    "case",
    "contract",
    "brief",
    "advisory",
    "proposal",
    "document",
    "service",
  ],
  "growth-marketing": [
    "campaign",
    "marketing",
    "brand",
    "outreach",
    "content",
    "audience",
    "lead",
    "growth",
    "creative",
    "launch",
  ],
  "operations-delivery": [
    "operation",
    "delivery",
    "project",
    "construction",
    "schedule",
    "vendor",
    "field",
    "workflow",
    "handoff",
    "execution",
  ],
  "research-advisory": [
    "research",
    "analy",
    "insight",
    "recommend",
    "investigate",
    "strategy",
    "performance",
    "report",
    "assessment",
    "review",
  ],
};

function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function getDepartmentCatalogMatch(label: string): CompanyDepartment | undefined {
  return departmentCatalog.find((item) => item.label.toLowerCase() === label.toLowerCase());
}

export function inferCompanyPresetFromObjective(objective: string): CompanyPreset {
  const normalized = objective.trim().toLowerCase();
  if (!normalized) {
    return defaultPreset;
  }

  let bestPreset = defaultPreset;
  let bestScore = 0;

  for (const preset of companyPresets.slice(1)) {
    const signals = presetInferenceSignals[preset.id] ?? [];
    const score = signals.reduce((total, signal) => (normalized.includes(signal) ? total + 1 : total), 0);
    if (score > bestScore) {
      bestPreset = preset;
      bestScore = score;
    }
  }

  return bestScore > 0 ? bestPreset : defaultPreset;
}

function naturalLanguageList(items: string[]): string {
  if (items.length <= 1) {
    return items[0] ?? "";
  }
  if (items.length === 2) {
    return `${items[0]} and ${items[1]}`;
  }
  return `${items.slice(0, -1).join(", ")}, and ${items[items.length - 1]}`;
}

function getObjectiveSignalMatches(objective: string, presetId: string): string[] {
  const normalized = objective.trim().toLowerCase();
  if (!normalized) {
    return [];
  }

  return (presetInferenceSignals[presetId] ?? [])
    .filter((signal) => normalized.includes(signal))
    .slice(0, 2)
    .map((signal) => signal.replace(/^analy$/, "analysis"));
}

export function getDepartmentExplanation(label: string, graphJson?: GraphJson | null): string {
  const catalogMatch = getDepartmentCatalogMatch(label);
  if (catalogMatch?.responsibility) {
    return catalogMatch.responsibility;
  }

  const graphNode = graphJson?.nodes.find((node) => node.name === label);
  const configuredDescription =
    typeof graphNode?.config?.job_description === "string" ? graphNode.config.job_description : undefined;
  if (configuredDescription?.trim()) {
    return configuredDescription.trim();
  }

  return "Handles one part of the company operation.";
}

export function getSkillExplanation(skill: string): string {
  return skillExplanations[skill] ?? "Adds one capability the company can use when needed.";
}

export function buildSuggestedSetupReasons(
  objective: string,
  preset: Pick<CompanyPreset, "id" | "label">,
  departments: CompanyDepartment[],
): string[] {
  const matches = getObjectiveSignalMatches(objective, preset.id);
  const reasons: string[] = [];

  if (matches.length) {
    reasons.push(
      `Your objective mentions ${naturalLanguageList(matches)}, so ForgeGraph started with a ${preset.label.toLowerCase()} pattern.`,
    );
  } else {
    reasons.push(
      "Your objective is still broad, so ForgeGraph started with a flexible structure you can refine quickly.",
    );
  }

  if (departments.length >= 2) {
    reasons.push(`${departments[0].label} sets direction while ${departments[1].label} keeps the work moving.`);
  }

  if (departments.length >= 3) {
    reasons.push(
      `${departments[departments.length - 1].label} helps turn the work into a deliverable you can review and use.`,
    );
  }

  if (departments.length >= 3) {
    reasons.push(
      "This first setup stays intentionally lean so you can reach a first deliverable before investing time in a more custom structure.",
    );
  }

  return reasons.slice(0, 3);
}

export function buildTeamCompositionReasons(departments: CompanyDepartment[]): string[] {
  if (!departments.length) {
    return [];
  }

  const reasons = departments.slice(0, 3).map((department, index) => {
    if (index === 0) {
      return `${department.label}: turns the business goal into a workable direction for the rest of the company.`;
    }
    if (index === departments.length - 1 || index === 2) {
      return `${department.label}: helps convert the work into something concrete you can review and act on.`;
    }
    return `${department.label}: keeps the work moving instead of letting the company stall between handoffs.`;
  });
  if (departments.length > 3) {
    reasons.push(`The remaining departments support the handoff so the company can finish the task without stalling.`);
  }
  return reasons.slice(0, 4);
}

export function buildCompanyProfile(input?: Partial<CompanyProfile>): CompanyProfile {
  return {
    schema: "company_workspace.v1",
    companyName: input?.companyName?.trim() || "Untitled Company",
    companyType: input?.companyType?.trim() || defaultPreset.label,
    objective: input?.objective?.trim() || defaultPreset.starterObjective,
    autonomyMode: input?.autonomyMode ?? "assisted",
    aiAccessMode: input?.aiAccessMode ?? "managed",
    intelligenceProvider: input?.intelligenceProvider?.trim() || "openai",
    companyStatus: input?.companyStatus ?? "Ready to launch",
    byokCredentialId: input?.byokCredentialId ?? null,
    departments:
      input?.departments !== undefined
        ? input.departments
        : defaultPreset.departments.map((department) => ({ ...department })),
    skills: input?.skills !== undefined ? input.skills : [...defaultPreset.skills],
  };
}

function nodeTypeToDepartment(nodeType: string): CompanyDepartment {
  switch (nodeType) {
    case NODE_TYPES.AGENT:
      return {
        id: "ai-worker",
        label: "AI Worker",
        responsibility: "Performs a focused piece of company work.",
        tools: [],
        category: "skill",
      };
    case NODE_TYPES.PROMPT:
      return {
        id: "analysis-skill",
        label: "Analysis Skill",
        responsibility: "Generates a structured AI response for the next step.",
        tools: [],
        category: "skill",
      };
    case NODE_TYPES.TOOL:
    case NODE_TYPES.HTTP:
      return {
        id: "tool-action",
        label: "Tool Action",
        responsibility: "Uses an external system or capability on behalf of the company.",
        tools: [],
        category: "skill",
      };
    case NODE_TYPES.HUMAN_GATE:
      return {
        id: "approval-required",
        label: "Approval Required",
        responsibility: "Waits for a human decision before work can continue.",
        tools: [],
        category: "department",
      };
    case NODE_TYPES.TRANSFORM:
      return {
        id: "operations-desk",
        label: "Operations Desk",
        responsibility: "Packages intermediate work for the next step.",
        tools: [],
        category: "department",
      };
    default:
      return {
        id: "company-step",
        label: "Company Step",
        responsibility: "Executes one step in the operating model.",
        tools: [],
        category: "department",
      };
  }
}

export function getCompanyProfileFromGraph(
  graph: Pick<GraphListItem, "name" | "description"> | Pick<GraphDetail, "name" | "description">,
  graphJson: GraphJson | null | undefined,
): CompanyProfile {
  const rawProfile = graphJson?.metadata?.company_profile;
  if (rawProfile && typeof rawProfile === "object") {
    const metadataProfile = rawProfile as Partial<CompanyProfile>;
    return buildCompanyProfile({
      ...metadataProfile,
      companyName: metadataProfile.companyName ?? graph.name,
      objective: metadataProfile.objective ?? graph.description,
    });
  }

  const inferredDepartments =
    graphJson?.nodes
      .filter((node) => node.type !== NODE_TYPES.OUTPUT)
      .map((node, index) => {
        const catalogMatch = getDepartmentCatalogMatch(node.name);
        return {
          ...(catalogMatch ?? nodeTypeToDepartment(node.type)),
          id: `${slugify(node.name || `department-${index + 1}`)}-${index + 1}`,
          label: node.name || nodeTypeToDepartment(node.type).label,
        };
      }) ?? [];

  return buildCompanyProfile({
    companyName: graph.name,
    objective: graph.description || defaultPreset.starterObjective,
    companyType: "Custom Company",
    departments: inferredDepartments.length ? inferredDepartments : undefined,
  });
}

function buildDepartmentInstructions(profile: CompanyProfile, department: CompanyDepartment, index: number): string {
  const previousContext =
    index === 0
      ? "Start from the company objective and the current operation brief."
      : "Build on the work produced by the previous department and improve it before handing it forward.";

  const skills = department.tools.length ? `Useful capabilities: ${department.tools.join(", ")}.` : "";

  return [
    `You are the ${department.label} inside ${profile.companyName}.`,
    `Company objective: ${profile.objective}`,
    `Your responsibility: ${department.responsibility}`,
    previousContext,
    "Return concrete work product, not commentary about the workflow.",
    "Make the output operationally useful for the next department.",
    skills,
  ]
    .filter(Boolean)
    .join(" ");
}

export function buildCompanyGraphJson(profile: CompanyProfile): GraphJson {
  const departments = profile.departments.length ? profile.departments : defaultPreset.departments;
  const nodes = departments.map((department, index) => {
    const nodeId = `department_${index + 1}_${slugify(department.label)}`;
    return {
      id: nodeId,
      type: NODE_TYPES.AGENT,
      name: department.label,
      config: {
        role: department.label,
        job_description: department.responsibility,
        instructions: buildDepartmentInstructions(profile, department, index),
        system_prompt: `You operate as ${department.label} for ${profile.companyName}. Focus on useful business work, concise communication, and clear handoff quality.`,
        provider: profile.intelligenceProvider,
        model: "gpt-4.1-mini",
        temperature: index === 0 ? 0.45 : 0.3,
        tools: department.tools,
        max_steps: 4,
        max_tool_calls: Math.max(department.tools.length, 1),
      },
      retry_policy: {
        max_attempts: 1,
        backoff_ms: 0,
        backoff_strategy: "fixed" as const,
      },
      timeout_ms: 180_000,
    };
  });

  const lastDepartment = nodes[nodes.length - 1];
  const outputNodeId = "final_deliverable";
  const outputNode = {
    id: outputNodeId,
    type: NODE_TYPES.OUTPUT,
    name: "Final Deliverable",
    config: {
      output_mapping: {
        deliverable: lastDepartment ? `node.${lastDepartment.id}.output.final_output` : "input.operation_brief",
        company_objective: "input.objective",
      },
    },
  };

  const edges = [
    ...(nodes[0] ? [{ id: "start-entry", from: START_NODE_ID, to: nodes[0].id }] : []),
    ...nodes.slice(0, -1).map((node, index) => ({
      id: `edge-${index + 1}`,
      from: node.id,
      to: nodes[index + 1].id,
    })),
    ...(lastDepartment ? [{ id: "edge-output", from: lastDepartment.id, to: outputNodeId }] : []),
    { id: "edge-end", from: outputNodeId, to: END_NODE_ID },
  ];

  return {
    nodes: [...nodes, outputNode],
    edges,
    metadata: {
      name: profile.companyName,
      description: profile.objective,
      company_profile: profile,
    },
    editor_state: {
      viewport: { x: 0, y: 0, zoom: 1 },
      nodePositions: Object.fromEntries(
        [...nodes, outputNode].map((node, index) => [
          node.id,
          {
            x: index % 2 === 0 ? 160 : 520,
            y: 120 + index * 180,
          },
        ]),
      ),
    },
  };
}

export function buildOperationInput(profile: CompanyProfile, operationBrief: string): Record<string, unknown> {
  return {
    company_name: profile.companyName,
    company_type: profile.companyType,
    objective: profile.objective,
    autonomy_mode: profile.autonomyMode,
    ai_access_mode: profile.aiAccessMode,
    operation_brief: operationBrief.trim() || profile.objective,
    departments: profile.departments.map((department) => department.label),
  };
}

export function translateRunStatus(status: string): "queued" | "running" | "completed" | "failed" | "paused" {
  const normalized = status.toLowerCase();
  if (normalized === "succeeded" || normalized === "success" || normalized === "completed") {
    return "completed";
  }
  if (normalized === "failed" || normalized === "error" || normalized === "canceled") {
    return "failed";
  }
  if (normalized === "paused") {
    return "paused";
  }
  if (normalized === "pending" || normalized === "queued") {
    return "queued";
  }
  return "running";
}

export function getCompanyStatus(runs: Array<RunListItem | RunDetail>, pendingApprovals: number): string {
  if (pendingApprovals > 0) {
    return "Awaiting approval";
  }
  if (runs.some((run) => translateRunStatus(String(run.status)) === "failed")) {
    return "Needs attention";
  }
  if (runs.some((run) => translateRunStatus(String(run.status)) === "running")) {
    return "Operating";
  }
  if (runs.some((run) => translateRunStatus(String(run.status)) === "completed")) {
    return "Stable";
  }
  return "Ready to launch";
}

export function summarizeDeliverable(run: Pick<RunDetail, "output_json" | "node_runs">): string {
  const outputJson = run.output_json;
  if (outputJson && typeof outputJson === "object") {
    const deliverable =
      (typeof outputJson.deliverable === "string" && outputJson.deliverable) ||
      (typeof outputJson.response === "string" && outputJson.response) ||
      (typeof outputJson.summary === "string" && outputJson.summary);
    if (deliverable) {
      return deliverable;
    }
    const serialized = JSON.stringify(outputJson);
    if (serialized.length <= 180) {
      return serialized;
    }
    return `${serialized.slice(0, 177)}...`;
  }

  const lastNodeRun = [...run.node_runs].reverse().find((nodeRun) => nodeRun.output_json);
  if (!lastNodeRun?.output_json) {
    return "Deliverable will appear here when the operation finishes.";
  }

  const serialized = JSON.stringify(lastNodeRun.output_json);
  return serialized.length <= 180 ? serialized : `${serialized.slice(0, 177)}...`;
}

export function getDepartmentTaskLabel(
  nodeRun: Pick<NodeRunItem, "node_id" | "node_type">,
  graphJson: GraphJson | null,
): string {
  const graphNode = graphJson?.nodes.find((node) => node.id === nodeRun.node_id);
  if (graphNode?.name) {
    return graphNode.name;
  }
  return nodeTypeToDepartment(String(nodeRun.node_type)).label;
}

export function translateFailure(
  run: Pick<RunDetail, "error_message" | "node_runs" | "status">,
  graphJson: GraphJson | null,
): CompanyFailure | null {
  if (translateRunStatus(String(run.status)) !== "failed") {
    return null;
  }

  const rawError = run.error_message || "";
  const failedNode = [...run.node_runs].reverse().find((nodeRun) => String(nodeRun.status).toLowerCase() === "failed");
  const failedDepartment = failedNode ? getDepartmentTaskLabel(failedNode, graphJson) : "Department";
  const normalized = rawError.toLowerCase();

  if (normalized.includes("timeout")) {
    return {
      title: "Intelligence provider timed out",
      summary: `${failedDepartment} stopped because the intelligence provider did not answer in time.`,
      nextSteps: [
        "Retry the operation.",
        "Switch AI access mode if the issue persists.",
        "Reduce the scope of the objective.",
      ],
      technicalDetails: rawError,
      actionHint: "switch_ai_access_mode",
    };
  }

  if (normalized.includes("unavailable") || normalized.includes("connection") || normalized.includes("refused")) {
    return {
      title: "Intelligence provider unavailable",
      summary: `${failedDepartment} could not reach the intelligence provider for this operation.`,
      nextSteps: ["Retry the operation.", "Switch AI access mode.", "Review provider or network availability."],
      technicalDetails: rawError,
      actionHint: "switch_ai_access_mode",
    };
  }

  if (
    normalized.includes("limit") ||
    normalized.includes("quota") ||
    normalized.includes("budget") ||
    normalized.includes("rate limit")
  ) {
    return {
      title: "Managed usage limit reached",
      summary: `${failedDepartment} could not continue because the current AI access mode hit a usage limit.`,
      nextSteps: ["Retry later.", "Switch AI access mode.", "Narrow the current objective before rerunning."],
      technicalDetails: rawError,
      actionHint: "switch_ai_access_mode",
    };
  }

  return {
    title: `${failedDepartment} needs attention`,
    summary: `${failedDepartment} could not finish its part of the operation, so the company paused before the deliverable was ready.`,
    nextSteps: [
      "Retry the operation.",
      "Edit the company objective if the request needs to be narrowed.",
      "Open technical details if deeper debugging is needed.",
    ],
    technicalDetails: rawError || null,
    actionHint: "retry",
  };
}

export function getDepartmentProgress(
  run: Pick<RunDetail, "node_runs">,
  graphJson: GraphJson | null,
): Array<{ label: string; status: "pending" | "running" | "completed" | "failed" }> {
  const plannedDepartments =
    graphJson?.nodes
      .filter((node) => node.type !== NODE_TYPES.OUTPUT)
      .map((node) => ({
        nodeId: node.id,
        label: node.name,
      })) ?? [];

  return plannedDepartments.map((department) => {
    const matchingNodeRun = run.node_runs.find((nodeRun) => nodeRun.node_id === department.nodeId);
    if (!matchingNodeRun) {
      return { label: department.label, status: "pending" as const };
    }

    const status = String(matchingNodeRun.status).toLowerCase();
    if (status === "succeeded" || status === "success") {
      return { label: department.label, status: "completed" as const };
    }
    if (status === "failed") {
      return { label: department.label, status: "failed" as const };
    }
    if (status === "running") {
      return { label: department.label, status: "running" as const };
    }
    return { label: department.label, status: "pending" as const };
  });
}

export function getCurrentDepartmentLabel(run: Pick<RunDetail, "node_runs">, graphJson: GraphJson | null): string {
  const activeNode =
    run.node_runs.find((nodeRun) => String(nodeRun.status).toLowerCase() === "running") ??
    [...run.node_runs].reverse()[0];

  if (!activeNode) {
    return "Waiting to begin";
  }

  return getDepartmentTaskLabel(activeNode, graphJson);
}
