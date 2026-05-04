import type { OperatingBrief, RunMemoryActivitySummary, RunLLMAccess } from "@/lib/api";
import type {
  CompanyAIAccessMode,
  CompanyAutonomyMode,
  CompanyDepartment,
  CompanyFailure,
  CompanyProfile,
} from "@/lib/company-workspace";

export type OperationStatusVM = "queued" | "running" | "completed" | "failed" | "paused";

export type TaskStatusVM =
  | "created"
  | "queued"
  | "claimed"
  | "running"
  | "paused"
  | "waiting_for_decision"
  | "retry_scheduled"
  | "completed"
  | "failed"
  | "dead_lettered"
  | "cancelled"
  | "skipped";

export type DepartmentActivityStatusVM = "active" | "waiting" | "idle";

export type DepartmentVM = CompanyDepartment & {
  status?: TaskStatusVM;
  name?: string;
  role?: string;
  purpose?: string;
  currentFocus?: string;
  activityStatus?: DepartmentActivityStatusVM;
  activeTaskCount?: number;
  pendingDecisionCount?: number;
  totalCostUsd?: number;
  defaultModel?: string | null;
  lastOperationId?: string | null;
};

export type DeliverableVM = {
  id: string;
  operationId: string;
  title: string;
  preview: string;
  content: string | null;
  ready: boolean;
  createdAt: string | null;
  sourceDepartmentName?: string | null;
};

export type TaskVM = {
  id: string;
  operationId?: string | null;
  agentId?: string | null;
  departmentId?: string | null;
  departmentName: string;
  title: string;
  status: TaskStatusVM;
  priority?: string | null;
  summary: string;
  startedAt: string | null;
  endedAt: string | null;
  createdAt?: string | null;
  updatedAt?: string | null;
  durationMs: number | null;
  attempt?: number | null;
  attemptCount?: number | null;
  currentStepId?: string | null;
  currentDecisionId?: string | null;
  lifecycleTaskId?: string | null;
  requiresApproval?: boolean;
  toolName?: string | null;
  resultPreview?: string | null;
  issuePreview?: string | null;
  retryMetadata?: Record<string, unknown> | null;
  latestRetry?: {
    operation_type?: string;
    attempt_number?: number;
    max_attempts?: number;
    retry_delay_ms?: number;
    retry_reason?: string;
    last_error?: string;
    next_scheduled_at?: string | null;
    terminal_fallback?: string;
    retry_class?: string;
    status?: string;
  } | null;
  deadLetter?: {
    reason?: string;
    attempt_count?: number;
    last_error?: string;
    recovery_options?: string[];
    status?: string;
    intent_id?: string | null;
    acknowledged_at?: string | null;
  } | null;
  staleEventCount?: number;
  lateEventCount?: number;
  recoveryOptions?: string[];
};

export type OperationFailureVM = Omit<CompanyFailure, "technicalDetails"> & {
  detailsForSupport?: string | null;
};

export type OperationVM = {
  id: string;
  companyId: string;
  companyName: string;
  setupVersionId: string;
  setupVersion: number;
  status: OperationStatusVM;
  queueStatus: string | null;
  attempts: number;
  startedAt: string | null;
  endedAt: string | null;
  durationMs: number | null;
  brief: string;
  currentDepartmentName: string;
  tasks: TaskVM[];
  deliverable: DeliverableVM;
  failure: OperationFailureVM | null;
  memoryActivity?: RunMemoryActivitySummary | null;
  aiAccess?: RunLLMAccess | null;
};

export type CompanyVM = {
  id: string;
  name: string;
  description: string;
  createdAt: string;
  updatedAt: string;
  setupVersionId: string | null;
  setupVersion: number | null;
  setupVersionCount: number;
  profile: CompanyProfile;
  departments: DepartmentVM[];
  status: string;
  pendingApprovalCount: number;
  operationCount: number;
  latestOperation: OperationVM | null;
};

export type CompanyWorkspaceVM = {
  company: CompanyVM | null;
  operations: OperationVM[];
  pendingApprovalCount: number;
};

export type ApprovalRiskVM = "low" | "medium" | "high";

export type ApprovalVM = {
  id: string;
  operationId: string;
  operationName: string;
  companyName: string;
  agentId?: string | null;
  departmentId: string;
  departmentName: string;
  status: "pending" | "approved" | "rejected";
  promptMessage: string;
  requiredFields: string[];
  result: Record<string, unknown> | null;
  createdAt: string;
  resolvedAt: string | null;
  estimatedCost: number;
  risk: ApprovalRiskVM;
  consequence: string;
  blastRadius: string;
};

export type CompanyCreateInputVM = {
  profile: CompanyProfile;
  operationBrief: string;
  launchFirstOperation: boolean;
  byokApiKey?: string;
};

export type CompanyUpdateInputVM = {
  companyId: string;
  currentProfile: CompanyProfile;
  objective: string;
  autonomyMode: CompanyAutonomyMode;
  aiAccessMode: CompanyAIAccessMode;
  paused: boolean;
};

export type OperationLaunchInputVM = {
  setupVersionId: string;
  profile: CompanyProfile;
  objective: string;
  autonomyMode: CompanyAutonomyMode;
  aiAccessMode: CompanyAIAccessMode;
  operationBrief: string;
  operatingBrief?: OperatingBrief | null;
};

export type OperationRefVM = {
  id: string;
  name: string;
  status: OperationStatusVM;
  role: string;
  currentStage: string;
  startedAt: string | null;
};

export type DepartmentProposalVM = {
  id: string;
  description: string;
  status: "awaiting approval" | "accepted" | "rejected";
  operation: OperationRefVM | null;
  createdAt: string;
};

export type DepartmentBlockerVM = {
  id: string;
  description: string;
  status: "waiting" | "failed";
  operation: OperationRefVM | null;
};

export type DepartmentFocusVM = {
  objective: string;
  reasoning: string;
};

export type DepartmentActivityVM = {
  department: DepartmentVM;
  focus: DepartmentFocusVM;
  proposals: DepartmentProposalVM[];
  tasks: TaskVM[];
  operations: OperationRefVM[];
  blockers: DepartmentBlockerVM[];
  approvals: ApprovalVM[];
};

export type CostBreakdownVM = {
  id: string;
  label: string;
  totalCostUsd: number;
  entryCount: number;
};

export type DepartmentCostVM = {
  id: string;
  displayName: string;
  status: string;
  totalCostUsd: number;
};

export type MetricProvenanceVM = {
  source: string;
  computedAt: string | null;
  freshnessMs: number | null;
  status: "available" | "not_instrumented" | "stale" | "error" | string;
  value: number | null;
};

export type AccountingLedgerEntryVM = {
  id: string;
  sourceLabel: string;
  provider: string;
  model: string;
  usageLabel: string;
  quantity: number;
  costType: string;
  totalCostUsd: number;
  occurredAt: string;
};

export type AccountingOverviewVM = {
  organizationId: string;
  totalCostUsd: number;
  generatedAt: string | null;
  metricProvenance: {
    totalCostUsd: MetricProvenanceVM;
    revenue: MetricProvenanceVM;
    profit: MetricProvenanceVM;
  };
  costByType: CostBreakdownVM[];
  topDepartments: DepartmentCostVM[];
};
