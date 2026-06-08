import { useCallback, useEffect, useMemo, useReducer, type SetStateAction } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import {
  AlertTriangle, ArrowRight, Bot, FileText, PauseCircle, PlayCircle, RotateCcw, Send, Settings2, } from "lucide-react";

import DashboardLayout from "@/components/DashboardLayout";
import { CommerceInventoryPanel } from "@/components/company/CommerceInventoryPanel";
import { OperatingModelWorkspace } from "@/components/company/OperatingModelWorkspace";
import { QuestGuide } from "@/components/company/QuestGuide";
import ProtectedRoute from "@/components/ProtectedRoute";
import {
  AgencyHealthPanel,
  agencyHealthSnapshotFromViewModel,
  type AgencyHealthSnapshot,
} from "@/components/company/AgencyHealthPanel";
import {
  EmptyBlock,
  InspectorPanel,
  MicroExplanation,
  Panel,
  SectionHeader,
  StatusBadge,
  WhyBlock,
} from "@/components/os/operations-ui";
import { formatCompactNumber, formatDateTime } from "@/components/os/operations-format";
import { Alert, AlertDescription, Button, Input, Spinner, Textarea } from "@/components/ui";
import type { InteractionEventResponse, OperatingBrief, OperatingBriefClarification } from "@/lib/api";
import { onboardingApi } from "@/lib/api";
import { companyRepository, interactionRepository } from "@/domain/repositories";
import { getOperationAiAccess } from "@/domain/repositories/operationRepository";
import { translateProductError } from "@/domain/errors";
import type { CompanyVM, DepartmentVM, OperationFailureVM, OperationVM, TaskStatusVM } from "@/domain/translation";
import {
  buildCompanyProfile,
  getDepartmentExplanation,
  type CompanyAIAccessMode,
  type CompanyAutonomyMode,
} from "@/lib/company-workspace";
import { showError, showSuccess } from "@/lib/toast";

type CompanyWorkspaceShellProps = {
  companyId: string;
  company: CompanyVM | null;
  operations: OperationVM[];
  pendingApprovalCount: number;
  loading: boolean;
  error: string | null;
  onRefresh: () => Promise<void>;
  questMode?: boolean;
};

function getProgressTone(status: TaskStatusVM | undefined) {
  switch (status) {
    case "completed":
      return { dot: "bg-emerald-500", line: "bg-emerald-300/70 dark:bg-emerald-500/30", title: "Handed off" };
    case "running":
      return { dot: "bg-sky-500 ring-4 ring-sky-500/15", line: "bg-zinc-300 dark:bg-white/15", title: "Working now" };
    case "failed":
      return {
        dot: "bg-rose-500 ring-4 ring-rose-500/15",
        line: "bg-zinc-300 dark:bg-white/15",
        title: "Needs attention",
      };
    default:
      return { dot: "bg-zinc-300 dark:bg-white/15", line: "bg-zinc-300 dark:bg-white/15", title: "Queued next" };
  }
}

function describeOperationMomentum(
  progress: Array<{ label: string; status?: TaskStatusVM }>,
  currentDepartment: string,
  userStatus: "queued" | "running" | "completed" | "failed" | "paused",
) {
  const activeStep = progress.find((step) => step.status === "running");
  const failedStep = progress.find((step) => step.status === "failed");
  const nextStep = progress.find((step) => step.status === "queued");

  if (failedStep) {
    return `${failedStep.label} needs attention before the operation can continue.`;
  }
  if (activeStep) {
    return nextStep
      ? `${activeStep.label} is working now. ${nextStep.label} is next.`
      : `${activeStep.label} is finishing the final part of this operation.`;
  }
  if (userStatus === "completed") {
    return `${currentDepartment} completed the last handoff and the deliverable is ready to review.`;
  }
  if (userStatus === "paused") {
    return `${currentDepartment} is waiting for a decision before work can continue.`;
  }
  return "The company is preparing this operation to begin.";
}

function OperationsList({ operations, departments }: { operations: OperationVM[]; departments: DepartmentVM[] }) {
  if (!operations.length) {
    return (
      <EmptyBlock
        title="No operations yet"
        description="Launch the first operation to see company work move through departments, tasks, and deliverables."
      />
    );
  }

  return (
    <div className="space-y-4">
      {operations.map((operation) => {
        const tasksByDepartmentId = new Map(operation.tasks.map((task) => [task.departmentId, task]));
        const progress = departments.length
          ? departments.map((department) => ({
              ...department,
              status: tasksByDepartmentId.get(department.id)?.status ?? department.status ?? "queued",
            }))
          : operation.tasks.map((task) => ({
              id: task.departmentId ?? task.id,
              label: task.departmentName,
              responsibility: task.summary,
              tools: [],
              category: "department" as const,
              status: task.status,
            }));
        const currentDepartment = operation.currentDepartmentName || "Queued";
        const currentDepartmentExplanation =
          progress.find((department) => department.label === currentDepartment)?.responsibility ??
          getDepartmentExplanation(currentDepartment);
        const deliverablePreview = operation.deliverable.preview;
        const userStatus = operation.status;
        const momentum = describeOperationMomentum(progress, currentDepartment, userStatus);

        return (
          <div
            key={operation.id}
            className="rounded-[1.4rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-5 dark:border-white/8"
          >
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-3">
                  <p className="text-sm font-semibold text-zinc-950 dark:text-zinc-50">
                    Operation {operation.id.slice(0, 8)}
                  </p>
                  <StatusBadge status={userStatus} label={userStatus} />
                  <p className="text-xs text-zinc-500 dark:text-zinc-400">
                    Started {formatDateTime(operation.startedAt)}
                  </p>
                </div>
                <p className="mt-3 text-sm leading-6 text-zinc-600 dark:text-zinc-300">
                  Current department:{" "}
                  <span className="font-medium text-zinc-900 dark:text-zinc-100">{currentDepartment}</span>
                </p>
                <MicroExplanation className="mt-2">{currentDepartmentExplanation}</MicroExplanation>
                <p className="mt-2 text-sm leading-6 text-zinc-500 dark:text-zinc-400">{momentum}</p>
              </div>
              <div className="flex shrink-0 flex-wrap gap-2">
                <Button asChild size="sm" className="rounded-full">
                  <Link href={`/runs/${operation.id}`}>Inspect operation</Link>
                </Button>
              </div>
            </div>

            <div className="mt-4">
              <p className="text-[11px] uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">
                Progress through departments
              </p>
              <div className="mt-4 space-y-3">
                {progress.length ? (
                  progress.map((step, index) => {
                    const tone = getProgressTone(step.status);
                    return (
                      <div key={`${operation.id}-${step.label}`} className="grid grid-cols-[1rem_1fr] gap-3">
                        <div className="flex flex-col items-center pt-1">
                          <span className={`size-3 rounded-full ${tone.dot}`} />
                          {index < progress.length - 1 ? <span className={`mt-2 h-full w-px ${tone.line}`} /> : null}
                        </div>
                        <div className="rounded-[1rem] border border-zinc-900/8 bg-white/70 p-3 dark:border-white/8 dark:bg-white/5">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">{step.label}</p>
                            <p className="text-xs font-medium uppercase tracking-[0.16em] text-zinc-500 dark:text-zinc-400">
                              {tone.title}
                            </p>
                          </div>
                          <MicroExplanation className="mt-2">{step.responsibility}</MicroExplanation>
                        </div>
                      </div>
                    );
                  })
                ) : (
                  <StatusBadge status="pending" label="Preparing operation" />
                )}
              </div>
            </div>

            <div className="mt-4 rounded-[1.2rem] border border-zinc-900/8 bg-white/70 p-4 dark:border-white/8 dark:bg-white/5">
              <p className="text-[11px] uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">
                Latest deliverable preview
              </p>
              <p className="mt-3 text-sm leading-6 text-zinc-700 dark:text-zinc-200">{deliverablePreview}</p>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function FailureCard({ failure, onRetry }: { failure: OperationFailureVM; onRetry: () => Promise<void> }) {
  return (
    <div className="rounded-[1.3rem] border border-rose-800/12 bg-rose-50/80 p-4 dark:border-rose-200/15 dark:bg-rose-500/10">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <AlertTriangle className="size-4 text-rose-600 dark:text-rose-300" />
            <p className="text-sm font-semibold text-rose-900 dark:text-rose-100">{failure.title}</p>
          </div>
          <p className="mt-2 text-xs font-semibold uppercase tracking-[0.16em] text-rose-700/80 dark:text-rose-100/70">
            What happened
          </p>
          <p className="mt-2 text-sm leading-6 text-rose-900/85 dark:text-rose-100/85">{failure.summary}</p>
          <p className="mt-4 text-xs font-semibold uppercase tracking-[0.16em] text-rose-700/80 dark:text-rose-100/70">
            What you can do next
          </p>
          <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-rose-900/80 dark:text-rose-100/80">
            {failure.nextSteps.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ul>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          <Button size="sm" className="rounded-full" onClick={() => void onRetry()}>
            Retry
          </Button>
          <Button asChild size="sm" variant="outline" className="rounded-full">
            <a href="#company-controls">Switch AI access mode</a>
          </Button>
          <Button asChild size="sm" variant="outline" className="rounded-full">
            <a href="#company-controls">Edit objective</a>
          </Button>
        </div>
      </div>
      {failure.detailsForSupport ? (
        <details className="mt-4 rounded-2xl border border-rose-800/12 bg-white/80 px-4 py-3 text-sm dark:border-rose-200/15 dark:bg-white/5">
          <summary className="cursor-pointer font-medium text-rose-900 dark:text-rose-100">Support details</summary>
          <pre className="mt-3 whitespace-pre-wrap text-xs leading-6 text-rose-900/80 dark:text-rose-100/80">
            {failure.detailsForSupport}
          </pre>
        </details>
      ) : null}
    </div>
  );
}

function formatAssumptionValue(value: unknown) {
  if (typeof value === "string") {
    return value;
  }
  if (value === null || value === undefined) {
    return "Not specified";
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value);
}

function BriefList({ label, items, emptyLabel }: { label: string; items: string[]; emptyLabel: string }) {
  return (
    <div>
      <p className="text-[11px] uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">{label}</p>
      <div className="mt-2 flex flex-wrap gap-2">
        {items.length ? (
          items.map((item) => (
            <span
              key={`${label}-${item}`}
              className="rounded-full border border-zinc-900/10 bg-white/80 px-3 py-1 text-xs text-zinc-700 dark:border-white/10 dark:bg-white/6 dark:text-zinc-200"
            >
              {item}
            </span>
          ))
        ) : (
          <span className="text-sm text-zinc-500 dark:text-zinc-400">{emptyLabel}</span>
        )}
      </div>
    </div>
  );
}

function PriorityFrameView({ brief }: { brief: OperatingBrief | null }) {
  const priorities = brief?.priority_frame ?? { speed: 0.5, cost: 0.5, quality: 0.5, risk: 0.5 };
  const items = [
    { label: "Speed", value: priorities.speed },
    { label: "Cost", value: priorities.cost },
    { label: "Quality", value: priorities.quality },
    { label: "Risk", value: priorities.risk },
  ];

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {items.map((item) => (
        <div key={item.label}>
          <div className="flex items-center justify-between text-xs text-zinc-500 dark:text-zinc-400">
            <span>{item.label}</span>
            <span>{Math.round(item.value * 100)}%</span>
          </div>
          <div className="mt-2 h-2 overflow-hidden rounded-full bg-zinc-200 dark:bg-white/10">
            <div
              className="h-full rounded-full bg-zinc-950 dark:bg-zinc-100"
              style={{ width: `${Math.max(0, Math.min(item.value, 1)) * 100}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

function formatInteractionLabel(value: string) {
  return value
    .toLowerCase()
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function responseClarifications(response: InteractionEventResponse): OperatingBriefClarification[] {
  const blocking = response.plan_implications.blocking_clarifications.length
    ? response.plan_implications.blocking_clarifications
    : response.brief.clarifications.filter((item) => item.blocking);
  if (blocking.length) {
    return blocking.slice(0, 3);
  }

  const suggested: OperatingBriefClarification[] = [];
  if (!response.brief.stakeholders.length) {
    suggested.push({
      question: "Who is the target customer?",
      blocking: false,
      related_field: "stakeholders",
    });
  }
  if (!response.brief.constraints.length) {
    suggested.push({
      question: "Which channels are allowed or off-limits?",
      blocking: false,
      related_field: "constraints",
    });
  }
  if (!response.brief.success_criteria.length) {
    suggested.push({
      question: "What result should define success?",
      blocking: false,
      related_field: "success_criteria",
    });
  }
  return suggested.slice(0, 3);
}

function nextStepForResponse(response: InteractionEventResponse) {
  if (response.pm_action.action === "ASK_CLARIFICATION") {
    return "Answer the open question and I will update the brief before the company moves forward.";
  }
  if (response.pm_action.action === "EXECUTE") {
    return "The brief is ready. Launch the operation when you want the company to start acting on it.";
  }
  if (response.pm_action.action === "BLOCK") {
    return "I will hold company work until you change the brief or remove the blocking instruction.";
  }
  if (response.plan_implications.requires_plan_revision) {
    return "I recorded the change for this active operation. Future planning can use it while current work continues from the state it already had.";
  }
  return "I recorded assumptions and can start a draft plan from this brief when you launch the next operation.";
}

function ProjectManagerResponseCard({ response }: { response: InteractionEventResponse }) {
  const clarifications = responseClarifications(response);
  const affectedFields = response.interpretation.affected_fields.length
    ? response.interpretation.affected_fields.map(formatInteractionLabel).join(", ")
    : "Operating Brief";
  const confidence = Math.round(response.interpretation.confidence * 100);

  return (
    <div
      data-testid="command-ops-response-card"
      className="mt-4 rounded-[1.2rem] border border-zinc-900/10 bg-white/85 p-4 dark:border-white/10 dark:bg-zinc-950/35"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-start gap-3">
          <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full bg-zinc-950 text-white dark:bg-white dark:text-zinc-950">
            <Bot className="size-4" />
          </span>
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">
              Project Manager
            </p>
            <p className="mt-2 text-sm font-semibold text-zinc-950 dark:text-zinc-50">
              I understand the objective as: {response.brief.objective ?? "Not set yet"}
            </p>
          </div>
        </div>
        <StatusBadge status={response.pm_action.action} label={formatInteractionLabel(response.pm_action.action)} />
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-3">
        <div className="rounded-[1rem] border border-zinc-900/8 bg-zinc-50 p-3 dark:border-white/8 dark:bg-white/5">
          <p className="text-[11px] uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">Interpreted As</p>
          <p className="mt-2 text-sm text-zinc-800 dark:text-zinc-200">
            {formatInteractionLabel(response.interpretation.intent_classification)} - {confidence}%
          </p>
        </div>
        <div className="rounded-[1rem] border border-zinc-900/8 bg-zinc-50 p-3 dark:border-white/8 dark:bg-white/5">
          <p className="text-[11px] uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">Deliverable</p>
          <p className="mt-2 text-sm text-zinc-800 dark:text-zinc-200">
            {response.brief.deliverable ?? "Needs definition"}
          </p>
        </div>
        <div className="rounded-[1rem] border border-zinc-900/8 bg-zinc-50 p-3 dark:border-white/8 dark:bg-white/5">
          <p className="text-[11px] uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">Changed</p>
          <p className="mt-2 text-sm text-zinc-800 dark:text-zinc-200">{affectedFields}</p>
        </div>
      </div>

      <div className="mt-4 rounded-[1rem] border border-amber-800/12 bg-amber-50/75 p-3 dark:border-amber-200/15 dark:bg-amber-500/10">
        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-amber-900/80 dark:text-amber-100/80">
          Before I Proceed
        </p>
        {clarifications.length ? (
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm leading-6 text-amber-950 dark:text-amber-100">
            {clarifications.map((item) => (
              <li key={`${item.related_field}-${item.question}`}>{item.question}</li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-sm leading-6 text-amber-950 dark:text-amber-100">
            No blocking questions. I can proceed with the recorded assumptions.
          </p>
        )}
      </div>

      <div className="mt-4 rounded-[1rem] border border-emerald-800/12 bg-emerald-50/75 p-3 dark:border-emerald-200/15 dark:bg-emerald-500/10">
        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-emerald-900/80 dark:text-emerald-100/80">
          Next Step
        </p>
        <p
          data-testid="command-ops-response-next-step"
          className="mt-2 text-sm leading-6 text-emerald-950 dark:text-emerald-100"
        >
          {nextStepForResponse(response)}
        </p>
      </div>

      <p className="mt-4 text-sm leading-6 text-zinc-600 dark:text-zinc-300">{response.plan_implications.summary}</p>
    </div>
  );
}

function focusOperatingBriefInput() {
  if (typeof document === "undefined") {
    return false;
  }

  const input = document.querySelector<HTMLTextAreaElement>('[data-testid="operating-brief-input"]');
  if (!input) {
    return false;
  }

  input.focus({ preventScroll: true });
  return true;
}

type CompanyWorkspaceState = {
  launching: boolean;
  retrying: boolean;
  savingObjective: boolean;
  savingCompanyState: boolean;
  companyPaused: boolean;
  operationBrief: string;
  editableObjective: string;
  editableAutonomyMode: CompanyAutonomyMode;
  editableAIAccessMode: CompanyAIAccessMode;
  operatingBrief: OperatingBrief | null;
  operatingBriefInput: string;
  operatingBriefLoading: boolean;
  operatingBriefSubmitting: boolean;
  operatingBriefError: string | null;
  latestPmAction: string | null;
  latestInteractionResponse: InteractionEventResponse | null;
  agencyHealthSnapshot: AgencyHealthSnapshot | null;
  agencyHealthLoading: boolean;
  agencyHealthError: string | null;
  questMilestoneComplete: boolean;
  questPhase: "workspace" | "deliverable" | "done";
};

type CompanyWorkspaceAction = {
  patch: Partial<CompanyWorkspaceState> | ((state: CompanyWorkspaceState) => Partial<CompanyWorkspaceState>);
};

function companyWorkspaceReducer(state: CompanyWorkspaceState, action: CompanyWorkspaceAction): CompanyWorkspaceState {
  const patch = typeof action.patch === "function" ? action.patch(state) : action.patch;
  return { ...state, ...patch };
}

function resolveStateAction<T>(value: SetStateAction<T>, current: T): T {
  return typeof value === "function" ? (value as (current: T) => T)(current) : value;
}

function useCompanyWorkspaceShellController({
  companyId,
  company,
  operations,
  pendingApprovalCount,
  loading,
  error,
  onRefresh,
  questMode = false,
}: CompanyWorkspaceShellProps) {
  const router = useRouter();
  const { replace } = router;
  const profile = useMemo(() => company?.profile ?? buildCompanyProfile({ companyName: "Company" }), [company]);
  const companyStatus = company?.status ?? "Ready to launch";
  const [workspaceState, dispatchWorkspaceState] = useReducer(companyWorkspaceReducer, {
    launching: false,
    retrying: false,
    savingObjective: false,
    savingCompanyState: false,
    companyPaused: profile.companyStatus === "Paused by operator",
    operationBrief: "Start the next operating cycle and produce a useful deliverable.",
    editableObjective: profile.objective,
    editableAutonomyMode: profile.autonomyMode,
    editableAIAccessMode: profile.aiAccessMode,
    operatingBrief: null,
    operatingBriefInput: "",
    operatingBriefLoading: false,
    operatingBriefSubmitting: false,
    operatingBriefError: null,
    latestPmAction: null,
    latestInteractionResponse: null,
    agencyHealthSnapshot: null,
    agencyHealthLoading: false,
    agencyHealthError: null,
    questMilestoneComplete: false,
    questPhase: "workspace",
  } satisfies CompanyWorkspaceState);
  const {
    launching,
    retrying,
    savingObjective,
    savingCompanyState,
    companyPaused,
    operationBrief,
    editableObjective,
    editableAutonomyMode,
    editableAIAccessMode,
    operatingBrief,
    operatingBriefInput,
    operatingBriefLoading,
    operatingBriefSubmitting,
    operatingBriefError,
    latestPmAction,
    latestInteractionResponse,
    agencyHealthSnapshot,
    agencyHealthLoading,
    agencyHealthError,
    questMilestoneComplete,
    questPhase,
  } = workspaceState;
  const setWorkspaceField = useCallback(
    <K extends keyof CompanyWorkspaceState>(key: K, value: SetStateAction<CompanyWorkspaceState[K]>) => {
      dispatchWorkspaceState({
        patch: (current) => ({ [key]: resolveStateAction(value, current[key]) }) as Partial<CompanyWorkspaceState>,
      });
    },
    [],
  );
  const setLaunching = useCallback(
    (value: SetStateAction<boolean>) => setWorkspaceField("launching", value),
    [setWorkspaceField],
  );
  const setRetrying = useCallback(
    (value: SetStateAction<boolean>) => setWorkspaceField("retrying", value),
    [setWorkspaceField],
  );
  const setSavingObjective = useCallback(
    (value: SetStateAction<boolean>) => setWorkspaceField("savingObjective", value),
    [setWorkspaceField],
  );
  const setSavingCompanyState = useCallback(
    (value: SetStateAction<boolean>) => setWorkspaceField("savingCompanyState", value),
    [setWorkspaceField],
  );
  const setCompanyPaused = useCallback(
    (value: SetStateAction<boolean>) => setWorkspaceField("companyPaused", value),
    [setWorkspaceField],
  );
  const setOperationBrief = useCallback(
    (value: SetStateAction<string>) => setWorkspaceField("operationBrief", value),
    [setWorkspaceField],
  );
  const setEditableObjective = useCallback(
    (value: SetStateAction<string>) => setWorkspaceField("editableObjective", value),
    [setWorkspaceField],
  );
  const setEditableAutonomyMode = useCallback(
    (value: SetStateAction<CompanyAutonomyMode>) => setWorkspaceField("editableAutonomyMode", value),
    [setWorkspaceField],
  );
  const setEditableAIAccessMode = useCallback(
    (value: SetStateAction<CompanyAIAccessMode>) => setWorkspaceField("editableAIAccessMode", value),
    [setWorkspaceField],
  );
  const setOperatingBrief = useCallback(
    (value: SetStateAction<OperatingBrief | null>) => setWorkspaceField("operatingBrief", value),
    [setWorkspaceField],
  );
  const setOperatingBriefInput = useCallback(
    (value: SetStateAction<string>) => setWorkspaceField("operatingBriefInput", value),
    [setWorkspaceField],
  );
  const setOperatingBriefLoading = useCallback(
    (value: SetStateAction<boolean>) => setWorkspaceField("operatingBriefLoading", value),
    [setWorkspaceField],
  );
  const setOperatingBriefSubmitting = useCallback(
    (value: SetStateAction<boolean>) => setWorkspaceField("operatingBriefSubmitting", value),
    [setWorkspaceField],
  );
  const setOperatingBriefError = useCallback(
    (value: SetStateAction<string | null>) => setWorkspaceField("operatingBriefError", value),
    [setWorkspaceField],
  );
  const setLatestPmAction = useCallback(
    (value: SetStateAction<string | null>) => setWorkspaceField("latestPmAction", value),
    [setWorkspaceField],
  );
  const setLatestInteractionResponse = useCallback(
    (value: SetStateAction<InteractionEventResponse | null>) => setWorkspaceField("latestInteractionResponse", value),
    [setWorkspaceField],
  );
  const setQuestMilestoneComplete = useCallback(
    (value: SetStateAction<boolean>) => setWorkspaceField("questMilestoneComplete", value),
    [setWorkspaceField],
  );
  const setQuestPhase = useCallback(
    (value: SetStateAction<"workspace" | "deliverable" | "done">) => setWorkspaceField("questPhase", value),
    [setWorkspaceField],
  );

  useEffect(() => {
    dispatchWorkspaceState({
      patch: {
        editableObjective: profile.objective,
        editableAutonomyMode: profile.autonomyMode,
        editableAIAccessMode: profile.aiAccessMode,
        companyPaused: profile.companyStatus === "Paused by operator",
      },
    });
  }, [profile.aiAccessMode, profile.autonomyMode, profile.companyStatus, profile.objective]);

  useEffect(() => {
    if (!questMode) {
      dispatchWorkspaceState({ patch: { questMilestoneComplete: true, questPhase: "done" } });
      return;
    }

    let mounted = true;
    void onboardingApi
      .list()
      .then((milestones) => {
        if (!mounted) {
          return;
        }
        const guideMilestone = milestones.find((item) => item.key === "company_first_run_explained");
        const completed = Boolean(guideMilestone?.completed);
        if (completed) {
          dispatchWorkspaceState({ patch: { questMilestoneComplete: true, questPhase: "done" } });
          return;
        }

        let nextQuestPhase: CompanyWorkspaceState["questPhase"] = "workspace";
        if (typeof window !== "undefined") {
          const storedPhase = window.sessionStorage.getItem(`forgegraph:first-operation-quest:${companyId}`);
          if (storedPhase === "deliverable" || storedPhase === "done") {
            nextQuestPhase = storedPhase;
          }
        }
        dispatchWorkspaceState({ patch: { questMilestoneComplete: false, questPhase: nextQuestPhase } });
      })
      .catch(() => {
        if (mounted) {
          dispatchWorkspaceState({ patch: { questMilestoneComplete: true, questPhase: "done" } });
        }
      });

    return () => {
      mounted = false;
    };
  }, [companyId, questMode]);

  const displayedCompanyStatus = companyPaused ? "Paused by operator" : companyStatus;

  const latestFailedOperation = useMemo(
    () => operations.find((operation) => operation.status === "failed") ?? null,
    [operations],
  );
  const failure = latestFailedOperation?.failure ?? null;
  const latestCompletedOutputs = useMemo(
    () =>
      operations
        .filter((operation) => operation.status === "completed")
        .slice(0, 3)
        .map((operation) => ({
          id: operation.id,
          title: operation.deliverable.title,
          preview: operation.deliverable.preview,
        })),
    [operations],
  );
  const workspaceGuideActive = questMode && !questMilestoneComplete && questPhase === "workspace";
  const deliverableGuideActive =
    questMode && !questMilestoneComplete && questPhase === "deliverable" && latestCompletedOutputs.length > 0;
  const workspaceQuestSteps = useMemo(
    () => [
      {
        id: "workspace",
        targetId: "company-command-ops-panel",
        title: "Interact with your company here.",
        description:
          "Command Ops is where you update the Operating Brief, launch operations, handle approvals, and keep the company moving.",
        placement: "left" as const,
      },
    ],
    [],
  );
  const deliverableQuestSteps = useMemo(
    () => [
      {
        id: "deliverable",
        targetId: "company-latest-outputs",
        title: "This is the result your company produced.",
        description:
          "Completed operations leave readable deliverables here so you can decide whether to launch the next cycle, retry, or tighten the objective.",
        placement: "left" as const,
      },
    ],
    [],
  );
  const runningOperation = useMemo(
    () => operations.find((operation) => operation.status === "running") ?? null,
    [operations],
  );
  const activeBriefOperation = useMemo(
    () => operations.find((operation) => operation.status === "running" || operation.status === "paused") ?? null,
    [operations],
  );

  useEffect(() => {
    if (loading || typeof window === "undefined" || !router.asPath.includes("#command-ops")) {
      return;
    }

    const scrollTimer = window.setTimeout(() => {
      const target = document.getElementById("command-ops");
      target?.scrollIntoView({ block: "start", inline: "nearest", behavior: "smooth" });
      if (!focusOperatingBriefInput()) {
        target?.focus({ preventScroll: true });
      }
    }, 80);

    return () => window.clearTimeout(scrollTimer);
  }, [loading, router.asPath]);

  useEffect(() => {
    if (!company?.id) {
      dispatchWorkspaceState({ patch: { operatingBrief: null } });
      return;
    }

    let mounted = true;
    dispatchWorkspaceState({ patch: { operatingBriefLoading: true, operatingBriefError: null } });
    void interactionRepository
      .getCurrentBrief(company.id, activeBriefOperation?.id ?? null)
      .then((brief) => {
        if (!mounted) {
          return;
        }
        dispatchWorkspaceState({
          patch: {
            operatingBrief: brief,
            latestPmAction: null,
            latestInteractionResponse: null,
            operatingBriefLoading: false,
          },
        });
      })
      .catch((briefError: unknown) => {
        if (!mounted) {
          return;
        }
        dispatchWorkspaceState({
          patch: {
            operatingBriefError: translateProductError(briefError, "company"),
            operatingBriefLoading: false,
          },
        });
      });

    return () => {
      mounted = false;
    };
  }, [activeBriefOperation?.id, company?.id]);

  useEffect(() => {
    if (!company?.id) {
      dispatchWorkspaceState({
        patch: {
          agencyHealthSnapshot: null,
          agencyHealthLoading: false,
          agencyHealthError: null,
        },
      });
      return;
    }

    let mounted = true;
    dispatchWorkspaceState({
      patch: {
        agencyHealthLoading: true,
        agencyHealthError: null,
      },
    });
    void companyRepository
      .getAgencyHealth(company.id)
      .then((snapshot) => {
        if (!mounted) {
          return;
        }
        dispatchWorkspaceState({
          patch: {
            agencyHealthSnapshot: agencyHealthSnapshotFromViewModel(
              snapshot,
              company.profile.companyName || company.name,
            ),
            agencyHealthLoading: false,
          },
        });
      })
      .catch((healthError: unknown) => {
        if (!mounted) {
          return;
        }
        dispatchWorkspaceState({
          patch: {
            agencyHealthSnapshot: null,
            agencyHealthLoading: false,
            agencyHealthError: translateProductError(healthError, "company"),
          },
        });
      });

    return () => {
      mounted = false;
    };
  }, [company?.id, company?.name, company?.profile.companyName]);

  const nextAction = useMemo(() => {
    if (failure) {
      return {
        title: "Needs attention now",
        body: "A department failed. Retry the work first if the request is still valid, or tighten the objective before launching again.",
        tone: "rose" as const,
      };
    }
    if (pendingApprovalCount > 0) {
      return {
        title: "Review approvals next",
        body: `${pendingApprovalCount} operation${pendingApprovalCount === 1 ? "" : "s"} are waiting on a human decision before the company can continue.`,
        tone: "amber" as const,
      };
    }
    if (companyPaused) {
      return {
        title: "Resume the company when you are ready",
        body: "New work is paused. Resume the company to let the next operation start.",
        tone: "slate" as const,
      };
    }
    if (!operations.length) {
      return {
        title: "Launch the first operation",
        body: "The company shell is ready. Start one focused assignment to reach the first deliverable quickly.",
        tone: "emerald" as const,
      };
    }
    if (runningOperation) {
      return {
        title: "Work is already in motion",
        body: `${runningOperation.currentDepartmentName} is actively working right now. Review progress or let the company finish this cycle.`,
        tone: "sky" as const,
      };
    }
    return {
      title: "Start the next operating cycle",
      body: "The last deliverable is ready. Launch the next operation when you want the company to keep moving.",
      tone: "emerald" as const,
    };
  }, [companyPaused, failure, operations.length, pendingApprovalCount, runningOperation]);

  const finishQuest = async (reason: "skip" | "complete") => {
    setQuestMilestoneComplete(true);
    setQuestPhase("done");
    if (typeof window !== "undefined") {
      window.sessionStorage.setItem(`forgegraph:first-operation-quest:${companyId}`, "done");
    }
    try {
      await onboardingApi.complete("company_first_run_explained", {
        source: "workspace",
        reason,
        company_id: companyId,
      });
    } catch {
      // Ignore guide persistence errors to keep the workspace responsive.
    }
    if (router.query.quest) {
      void replace({ pathname: `/companies/${companyId}` }, undefined, { shallow: true });
    }
  };

  const advanceWorkspaceQuest = () => {
    setQuestPhase("deliverable");
    if (typeof window !== "undefined") {
      window.sessionStorage.setItem(`forgegraph:first-operation-quest:${companyId}`, "deliverable");
    }
  };

  const handleLaunchOperation = async () => {
    if (!company?.setupVersionId) {
      showError("Company setup is incomplete", "Finish creating the company before launching an operation.");
      return;
    }
    if (companyPaused) {
      showError("Company is paused", "Resume the company before launching another operation.");
      return;
    }

    setLaunching(true);
    try {
      await companyRepository.launchOperation({
        setupVersionId: company.setupVersionId,
        profile,
        objective: editableObjective,
        autonomyMode: editableAutonomyMode,
        aiAccessMode: editableAIAccessMode,
        operationBrief,
        operatingBrief,
      });
      showSuccess("Operation launched", "The company is now running the next operation.");
      await onRefresh();
    } catch (launchError: unknown) {
      showError("Operation failed to launch", translateProductError(launchError, "operation"));
    } finally {
      setLaunching(false);
    }
  };

  const handleRetryFailedOperation = async () => {
    if (!latestFailedOperation) {
      showError("Nothing to retry", "No failed operation is currently available.");
      return;
    }

    setRetrying(true);
    try {
      await companyRepository.retryOperation(latestFailedOperation.id, getOperationAiAccess(profile));
      showSuccess("Retry started", "The failed operation has been requeued.");
      await onRefresh();
    } catch (retryError: unknown) {
      showError("Retry failed", translateProductError(retryError, "operation"));
    } finally {
      setRetrying(false);
    }
  };

  const handleSaveObjective = async () => {
    if (!company) {
      return;
    }

    setSavingObjective(true);
    try {
      await companyRepository.saveSettings({
        companyId: company.id,
        currentProfile: profile,
        objective: editableObjective,
        autonomyMode: editableAutonomyMode,
        aiAccessMode: editableAIAccessMode,
        paused: companyPaused,
      });
      showSuccess("Company updated", "The objective and operating settings were saved.");
      await onRefresh();
    } catch (saveError: unknown) {
      showError("Update failed", translateProductError(saveError, "company"));
    } finally {
      setSavingObjective(false);
    }
  };

  const handleToggleCompanyPause = async () => {
    if (!company?.setupVersionId) {
      showError("No operating model available", "Save a company operating model before changing company state.");
      return;
    }

    const nextPaused = !companyPaused;
    setSavingCompanyState(true);
    try {
      await companyRepository.setPaused({
        companyId: company.id,
        currentProfile: profile,
        objective: editableObjective,
        autonomyMode: editableAutonomyMode,
        aiAccessMode: editableAIAccessMode,
        paused: nextPaused,
      });
      setCompanyPaused(nextPaused);
      showSuccess(
        nextPaused ? "Company paused" : "Company resumed",
        nextPaused
          ? "New operations are paused until you resume the company."
          : "The company can launch operations again.",
      );
      await onRefresh();
    } catch (saveError: unknown) {
      showError(nextPaused ? "Pause failed" : "Resume failed", translateProductError(saveError, "company"));
    } finally {
      setSavingCompanyState(false);
    }
  };

  const handleSubmitOperatingBrief = async () => {
    if (!company) {
      return;
    }

    const input = operatingBriefInput.trim();
    if (!input) {
      showError("Brief input is empty", "Add the operating change before updating the brief.");
      return;
    }

    setOperatingBriefSubmitting(true);
    setOperatingBriefError(null);
    try {
      const result = await interactionRepository.submitInput({
        companyId: company.id,
        operationId: activeBriefOperation?.id ?? null,
        briefId: operatingBrief?.id ?? null,
        text: input,
      });
      setOperatingBrief(result.brief);
      setLatestPmAction(result.pm_action.action);
      setLatestInteractionResponse(result);
      setOperatingBriefInput("");
      showSuccess("Operating brief updated", result.plan_implications.summary);
    } catch (briefError: unknown) {
      const message = translateProductError(briefError, "company");
      setOperatingBriefError(message);
      showError("Brief update failed", message);
    } finally {
      setOperatingBriefSubmitting(false);
    }
  };

  return {
    companyId,
    company,
    operations,
    pendingApprovalCount,
    loading,
    error,
    profile,
    companyStatus,
    displayedCompanyStatus,
    launching,
    retrying,
    savingObjective,
    savingCompanyState,
    companyPaused,
    operationBrief,
    editableObjective,
    editableAutonomyMode,
    editableAIAccessMode,
    operatingBrief,
    operatingBriefInput,
    operatingBriefLoading,
    operatingBriefSubmitting,
    operatingBriefError,
    latestPmAction,
    latestInteractionResponse,
    agencyHealthSnapshot,
    agencyHealthLoading,
    agencyHealthError,
    latestFailedOperation,
    failure,
    latestCompletedOutputs,
    workspaceGuideActive,
    deliverableGuideActive,
    workspaceQuestSteps,
    deliverableQuestSteps,
    runningOperation,
    activeBriefOperation,
    nextAction,
    finishQuest,
    advanceWorkspaceQuest,
    handleLaunchOperation,
    handleRetryFailedOperation,
    handleSaveObjective,
    handleToggleCompanyPause,
    handleSubmitOperatingBrief,
    setOperatingBriefInput,
    setEditableObjective,
    setEditableAutonomyMode,
    setEditableAIAccessMode,
    setOperationBrief,
  };
}

type CompanyWorkspaceController = ReturnType<typeof useCompanyWorkspaceShellController>;

function CompanyWorkspaceInspector({ controller }: { controller: CompanyWorkspaceController }) {
  const { companyId, company, operations, pendingApprovalCount, profile, displayedCompanyStatus } = controller;

  return (
    <InspectorPanel
      title={profile.companyName}
      subtitle="Debug details stay collapsed here so the main shell can stay in company language."
      sections={[
        {
          title: "Company status",
          content: (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span>Status</span>
                <StatusBadge
                  status={
                    displayedCompanyStatus === "Needs attention"
                      ? "failed"
                      : displayedCompanyStatus === "Operating"
                        ? "running"
                        : displayedCompanyStatus === "Paused by operator"
                          ? "paused"
                          : "pending"
                  }
                  label={displayedCompanyStatus}
                />
              </div>
              <div className="flex items-center justify-between">
                <span>Pending approvals</span>
                <span>{pendingApprovalCount}</span>
              </div>
            </div>
          ),
        },
        {
          title: "Debug",
          content: (
            <details className="text-sm">
              <summary className="cursor-pointer font-medium">Show support identifiers</summary>
              <div className="mt-3 space-y-2 text-xs leading-6">
                <div>Company ID: {companyId}</div>
                <div>Setup version ID: {company?.setupVersionId ?? "None"}</div>
                <div>Latest operation ID: {operations[0]?.id ?? "None"}</div>
              </div>
            </details>
          ),
        },
      ]}
    />
  );
}

function CompanyWorkspaceContent({ controller }: { controller: CompanyWorkspaceController }) {
  const { company, companyId, deliverableGuideActive, deliverableQuestSteps, error, loading, profile } = controller;

  return (
    <div className="space-y-6">
      <CompanyQuestGuides controller={controller} />
      <SectionHeader
        eyebrow="Company Workspace"
        title={profile.companyName}
        description="Operate the company from one shell: see what it is doing, what it produced, and what needs your decision next."
        action={
          <div className="flex flex-wrap gap-2">
            <Button asChild variant="outline" className="rounded-full">
              <Link href={`/graphs/${companyId}`}>Advanced mode</Link>
            </Button>
            <Button asChild className="rounded-full">
              <Link href="/companies/new">
                Create another company
                <ArrowRight className="size-4" />
              </Link>
            </Button>
          </div>
        }
      />
      {error ? (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      {loading || !company ? (
        <div className="flex min-h-[320px] items-center justify-center rounded-[1.75rem] border border-zinc-900/10 bg-white/70 dark:border-white/10 dark:bg-zinc-950/50">
          <Spinner size="lg" />
        </div>
      ) : (
        <CompanyWorkspaceLoaded controller={controller} />
      )}
      {deliverableGuideActive && deliverableQuestSteps.length === 0 ? null : null}
    </div>
  );
}

function CompanyQuestGuides({ controller }: { controller: CompanyWorkspaceController }) {
  const { deliverableGuideActive, deliverableQuestSteps, workspaceGuideActive, workspaceQuestSteps } = controller;

  return (
    <>
      <QuestGuide
        active={workspaceGuideActive}
        title="Guided first operation"
        steps={workspaceQuestSteps}
        onSkip={() => {
          void controller.finishQuest("skip");
        }}
        onComplete={controller.advanceWorkspaceQuest}
      />
      <QuestGuide
        active={deliverableGuideActive}
        title="Guided first operation"
        steps={deliverableQuestSteps}
        onSkip={() => {
          void controller.finishQuest("skip");
        }}
        onComplete={() => {
          void controller.finishQuest("complete");
        }}
      />
    </>
  );
}

function CompanyWorkspaceLoaded({ controller }: { controller: CompanyWorkspaceController }) {
  return (
    <>
      <CompanyHeaderPanel controller={controller} />
      {controller.agencyHealthSnapshot ? (
        <AgencyHealthPanel snapshot={controller.agencyHealthSnapshot} audience="operator" />
      ) : controller.agencyHealthError && !controller.agencyHealthLoading ? (
        <Alert>
          <AlertDescription>{controller.agencyHealthError}</AlertDescription>
        </Alert>
      ) : null}
      <OperatingModelWorkspace companyId={controller.companyId} companyName={controller.profile.companyName} />
      <div className="grid gap-6 2xl:grid-cols-[1.06fr_0.94fr]">
        <div data-guide-id="company-operations-panel">
          <Panel
            title="Operations"
            description="Current and recent operations shown in company language."
            className="operations-panel"
          >
            <OperationsList operations={controller.operations} departments={controller.company?.departments ?? []} />
          </Panel>
        </div>
        <CompanyCommandOpsPanel controller={controller} />
      </div>
      <CommerceInventoryPanel companyId={controller.companyId} />
    </>
  );
}

function CompanyHeaderPanel({ controller }: { controller: CompanyWorkspaceController }) {
  const { companyStatus, displayedCompanyStatus, editableAIAccessMode, editableAutonomyMode, profile } = controller;

  return (
    <Panel
      title="Company Header"
      description="Primary company information translated from the current operating model and runtime state."
      className="company-header-panel"
    >
      <div className="grid gap-6 lg:grid-cols-[1.15fr_0.85fr]">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <StatusBadge
              status={
                companyStatus === "Needs attention" ? "failed" : companyStatus === "Operating" ? "running" : "pending"
              }
              label={companyStatus}
            />
            <StatusBadge status={editableAutonomyMode} label={editableAutonomyMode} />
            <StatusBadge
              status={editableAIAccessMode === "managed" ? "active" : "paused"}
              label={editableAIAccessMode === "managed" ? "Managed" : "BYOK"}
            />
          </div>
          <p
            className="mt-4 text-3xl font-semibold tracking-tight text-zinc-950 dark:text-zinc-50"
            style={{ fontFamily: "var(--font-serif)" }}
          >
            {profile.companyName}
          </p>
          <p className="mt-3 text-sm leading-7 text-zinc-600 dark:text-zinc-300">{profile.objective}</p>
          <MicroExplanation className="mt-3">
            The objective is the company-wide result ForgeGraph is trying to produce right now.
          </MicroExplanation>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-1">
          <CompanyFact
            label="Company Category"
            value={profile.companyType}
            detail="A starting shape that tells ForgeGraph how to organize the first team."
          />
          <CompanyFact
            label="Status"
            value={displayedCompanyStatus}
            detail="Tells you whether the company is working, waiting, paused, or needs attention."
          />
          <CompanyFact
            label="Autonomy Mode"
            value={editableAutonomyMode}
            detail={
              editableAutonomyMode === "manual"
                ? "Manual waits for you before work moves forward."
                : editableAutonomyMode === "autonomous"
                  ? "Autonomous keeps the company moving until a limit or failure stops it."
                  : "Assisted keeps the company moving and pauses only when a decision matters."
            }
          />
          <CompanyFact
            label="AI Access Mode"
            value={editableAIAccessMode === "managed" ? "Managed" : "BYOK"}
            detail={
              editableAIAccessMode === "managed"
                ? "Managed means ForgeGraph handles the AI access so you can operate immediately."
                : "BYOK means the company operates on your own AI access."
            }
          />
        </div>
      </div>
    </Panel>
  );
}

function CompanyFact({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="rounded-[1.35rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
      <p className="text-[11px] uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">{label}</p>
      <p className="mt-2 text-sm font-medium text-zinc-900 dark:text-zinc-100">{value}</p>
      <MicroExplanation className="mt-2">{detail}</MicroExplanation>
    </div>
  );
}

function CompanyCommandOpsPanel({ controller }: { controller: CompanyWorkspaceController }) {
  return (
    <div
      id="command-ops"
      data-guide-id="company-command-ops-panel"
      data-testid="command-ops-panel"
      tabIndex={-1}
      className="scroll-mt-24 focus:outline-none"
    >
      <Panel
        title="Command Ops"
        description="Interact with the company here: update the Operating Brief, launch work, handle approvals, and adjust controls."
        className="command-ops-panel"
      >
        <NextActionCard controller={controller} />
        <ProjectManagerMessage />
        <OperatingBriefPanel controller={controller} />
        <OperationStatsGrid controller={controller} />
        <CompanyDecisionExplanation controller={controller} />
        {controller.failure ? (
          <div className="mt-5">
            <FailureCard failure={controller.failure} onRetry={controller.handleRetryFailedOperation} />
          </div>
        ) : null}
        <CompanyControlsPanel controller={controller} />
        <LatestOutputsPanel controller={controller} />
      </Panel>
    </div>
  );
}

function NextActionCard({ controller }: { controller: CompanyWorkspaceController }) {
  const { companyPaused, failure, launching, nextAction, pendingApprovalCount } = controller;
  const toneClass =
    nextAction.tone === "rose"
      ? "border-rose-800/12 bg-rose-50/80 dark:border-rose-200/15 dark:bg-rose-500/10"
      : nextAction.tone === "amber"
        ? "border-amber-800/12 bg-amber-50/80 dark:border-amber-200/15 dark:bg-amber-500/10"
        : nextAction.tone === "sky"
          ? "border-sky-800/12 bg-sky-50/80 dark:border-sky-200/15 dark:bg-sky-500/10"
          : "border-emerald-800/12 bg-emerald-50/80 dark:border-emerald-200/15 dark:bg-emerald-500/10";

  return (
    <div className={`rounded-[1.35rem] border p-4 ${toneClass}`}>
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-300">
        Next best action
      </p>
      <div className="mt-3 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm font-semibold text-zinc-950 dark:text-zinc-50">{nextAction.title}</p>
          <p className="mt-2 text-sm leading-6 text-zinc-700 dark:text-zinc-200">{nextAction.body}</p>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          {failure ? (
            <Button size="sm" className="rounded-full" onClick={() => void controller.handleRetryFailedOperation()}>
              Retry now
            </Button>
          ) : pendingApprovalCount > 0 ? (
            <Button asChild size="sm" className="rounded-full">
              <Link href="/approvals">Review approvals</Link>
            </Button>
          ) : companyPaused ? (
            <Button size="sm" className="rounded-full" onClick={() => void controller.handleToggleCompanyPause()}>
              Resume company
            </Button>
          ) : (
            <Button
              size="sm"
              className="rounded-full"
              onClick={() => void controller.handleLaunchOperation()}
              disabled={launching}
            >
              Launch operation
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

function ProjectManagerMessage() {
  return (
    <div
      data-testid="command-ops-system-message"
      className="mt-4 rounded-[1.2rem] border border-sky-800/12 bg-sky-50/85 p-4 dark:border-sky-200/15 dark:bg-sky-500/10"
    >
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-200">
          <Bot className="size-4" />
        </span>
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-sky-900/70 dark:text-sky-100/75">
            Project Manager
          </p>
          <p className="mt-2 text-sm leading-6 text-sky-950 dark:text-sky-50">
            I&apos;m managing this company. Tell me what you want to achieve, and I&apos;ll turn it into a plan.
          </p>
        </div>
      </div>
    </div>
  );
}

function OperatingBriefPanel({ controller }: { controller: CompanyWorkspaceController }) {
  const {
    activeBriefOperation,
    latestInteractionResponse,
    latestPmAction,
    operatingBrief,
    operatingBriefError,
    operatingBriefInput,
    operatingBriefLoading,
    operatingBriefSubmitting,
  } = controller;

  return (
    <div
      data-testid="operating-brief-panel"
      className="mt-5 rounded-[1.5rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-zinc-950 dark:text-zinc-50">
            <FileText className="size-4" />
            <p className="text-sm font-semibold">Operating Brief</p>
          </div>
          <p className="mt-2 text-sm leading-6 text-zinc-600 dark:text-zinc-300">
            {activeBriefOperation
              ? `Scoped to operation ${activeBriefOperation.id.slice(0, 8)}`
              : "Scoped to the next company operation"}
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          {operatingBriefLoading ? <StatusBadge status="pending" label="Loading" /> : null}
          {latestPmAction ? <StatusBadge status={latestPmAction} label={latestPmAction} /> : null}
          {operatingBrief?.autonomy_mode ? (
            <StatusBadge status={operatingBrief.autonomy_mode} label={operatingBrief.autonomy_mode} />
          ) : null}
        </div>
      </div>
      {operatingBriefError ? (
        <Alert variant="destructive" className="mt-4">
          <AlertDescription>{operatingBriefError}</AlertDescription>
        </Alert>
      ) : null}
      <OperatingBriefSummary brief={operatingBrief} />
      <div className="mt-4">
        <label
          htmlFor="components-company-companyworkspaceshell-1282"
          className="text-[11px] uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400"
        >
          Update Brief
        </label>
        <Textarea
          id="components-company-companyworkspaceshell-1282"
          data-testid="operating-brief-input"
          className="mt-2"
          rows={3}
          value={operatingBriefInput}
          onChange={(event) => controller.setOperatingBriefInput(event.target.value)}
          placeholder={`Start by telling me what you want this company to achieve.

Examples:
- Build a lead generation system
- Analyze my market and competitors
- Create a content strategy`}
        />
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button
          data-testid="operating-brief-submit-button"
          onClick={() => void controller.handleSubmitOperatingBrief()}
          disabled={operatingBriefSubmitting || operatingBriefLoading}
        >
          {operatingBriefSubmitting ? <Spinner size="xs" className="mr-2" /> : <Send className="size-4" />}
          Update brief
        </Button>
      </div>
      {latestInteractionResponse ? <ProjectManagerResponseCard response={latestInteractionResponse} /> : null}
    </div>
  );
}

function OperatingBriefSummary({ brief }: { brief: OperatingBrief | null }) {
  return (
    <>
      <div className="mt-4 grid gap-3 lg:grid-cols-2">
        <BriefFact label="Objective" value={brief?.objective ?? "Not set"} />
        <BriefFact label="Deliverable" value={brief?.deliverable ?? "Not set"} />
      </div>
      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <BriefList label="Constraints" items={brief?.constraints ?? []} emptyLabel="No constraints recorded" />
        <BriefList
          label="Success Criteria"
          items={brief?.success_criteria ?? []}
          emptyLabel="No success criteria recorded"
        />
        <BriefList label="Stakeholders" items={brief?.stakeholders ?? []} emptyLabel="No stakeholders recorded" />
        <BriefList label="Dependencies" items={brief?.dependencies ?? []} emptyLabel="No dependencies recorded" />
      </div>
      <div className="mt-4 rounded-[1.1rem] border border-zinc-900/8 bg-white/70 p-4 dark:border-white/8 dark:bg-white/5">
        <p className="text-[11px] uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">Priority Frame</p>
        <div className="mt-3">
          <PriorityFrameView brief={brief} />
        </div>
      </div>
      <OperatingBriefClarifications brief={brief} />
      <OperatingBriefAssumptions brief={brief} />
    </>
  );
}

function BriefFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1.1rem] border border-zinc-900/8 bg-white/70 p-4 dark:border-white/8 dark:bg-white/5">
      <p className="text-[11px] uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">{label}</p>
      <p className="mt-2 text-sm leading-6 text-zinc-800 dark:text-zinc-200">{value}</p>
    </div>
  );
}

function OperatingBriefClarifications({ brief }: { brief: OperatingBrief | null }) {
  const blockingClarifications = brief?.clarifications.filter((item) => item.blocking) ?? [];

  if (blockingClarifications.length === 0) {
    return null;
  }

  return (
    <div className="mt-4 rounded-[1.1rem] border border-amber-800/15 bg-amber-50/80 p-4 dark:border-amber-200/20 dark:bg-amber-500/10">
      <p className="text-[11px] uppercase tracking-[0.18em] text-amber-800 dark:text-amber-100/80">
        Blocking Clarifications
      </p>
      <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-amber-950 dark:text-amber-100">
        {blockingClarifications.map((item) => (
          <li key={`${item.related_field}-${item.question}`}>{item.question}</li>
        ))}
      </ul>
    </div>
  );
}

function OperatingBriefAssumptions({ brief }: { brief: OperatingBrief | null }) {
  if (!brief?.assumptions.length) {
    return null;
  }

  return (
    <div className="mt-4">
      <p className="text-[11px] uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">Assumptions</p>
      <div className="mt-2 space-y-2">
        {brief.assumptions.slice(-3).map((item, index) => (
          <div
            key={`${item.field}-${item.created_at}-${index}`}
            className="rounded-[1rem] border border-zinc-900/8 bg-white/70 p-3 text-sm dark:border-white/8 dark:bg-white/5"
          >
            <span className="font-medium text-zinc-900 dark:text-zinc-100">{item.field}: </span>
            <span className="text-zinc-600 dark:text-zinc-300">{formatAssumptionValue(item.value)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function OperationStatsGrid({ controller }: { controller: CompanyWorkspaceController }) {
  const runningCount = controller.operations.filter((operation) => operation.status === "running").length;
  const failedCount = controller.operations.filter((operation) => operation.status === "failed").length;
  const stats = [
    { label: "Active operations", value: formatCompactNumber(runningCount), detail: null },
    { label: "Failed operations", value: formatCompactNumber(failedCount), detail: null },
    { label: "Pending approvals", value: formatCompactNumber(controller.pendingApprovalCount), detail: null },
    {
      label: "AI mode and usage",
      value: controller.editableAIAccessMode === "managed" ? "Managed" : "BYOK",
      detail: `${controller.operations.length} total operation${controller.operations.length === 1 ? "" : "s"} recorded in this company workspace.`,
    },
  ];

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {stats.map((item) => (
        <div
          key={item.label}
          className="rounded-[1.2rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8"
        >
          <p className="text-[11px] uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">{item.label}</p>
          <p className="mt-2 text-2xl font-semibold text-zinc-950 dark:text-zinc-50">{item.value}</p>
          {item.detail ? <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-300">{item.detail}</p> : null}
        </div>
      ))}
    </div>
  );
}

function CompanyDecisionExplanation({ controller }: { controller: CompanyWorkspaceController }) {
  const { failure, pendingApprovalCount, runningOperation } = controller;
  const reasons = failure
    ? [
        "A department could not finish its part of the operation.",
        "Retrying is the fastest way to check whether the issue was temporary or whether the objective needs to change.",
      ]
    : pendingApprovalCount > 0
      ? [
          "The company reached a point where a human decision is required.",
          "Approvals are shown first because the operation cannot continue until you respond.",
        ]
      : runningOperation
        ? [
            `${runningOperation.currentDepartmentName} is actively working right now.`,
            "The command surface shifts toward monitoring until the operation finishes or something needs your intervention.",
          ]
        : [
            "There is no blocked work right now, so the best next move is to launch another operation.",
            "This area keeps the next decision visible instead of making you hunt through metrics.",
          ];

  return <WhyBlock title="Why you are seeing this" reasons={reasons} className="mt-5" />;
}

function CompanyControlsPanel({ controller }: { controller: CompanyWorkspaceController }) {
  return (
    <div
      id="company-controls"
      className="mt-5 rounded-[1.5rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8"
    >
      <div className="flex items-center gap-2 text-zinc-950 dark:text-zinc-50">
        <Settings2 className="size-4" />
        <p className="text-sm font-semibold">Controls</p>
      </div>
      <div className="mt-4 space-y-4">
        <CompanyObjectiveControl controller={controller} />
        <CompanyModeControls controller={controller} />
        <CompanyLaunchControl controller={controller} />
        <CompanyControlActions controller={controller} />
      </div>
    </div>
  );
}

function CompanyObjectiveControl({ controller }: { controller: CompanyWorkspaceController }) {
  return (
    <div>
      <label
        htmlFor="components-company-companyworkspaceshell-1401"
        className="text-[11px] uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400"
      >
        Objective
      </label>
      <Textarea
        id="components-company-companyworkspaceshell-1401"
        className="mt-2"
        rows={4}
        value={controller.editableObjective}
        onChange={(event) => controller.setEditableObjective(event.target.value)}
      />
    </div>
  );
}

function CompanyModeControls({ controller }: { controller: CompanyWorkspaceController }) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <ModeButtonGroup
        id="components-company-companyworkspaceshell-1414"
        label="Autonomy mode"
        modes={["manual", "assisted", "autonomous"] as CompanyAutonomyMode[]}
        value={controller.editableAutonomyMode}
        getLabel={(mode) => mode}
        onChange={controller.setEditableAutonomyMode}
        description={
          controller.editableAutonomyMode === "manual"
            ? "Nothing meaningful moves forward without you."
            : controller.editableAutonomyMode === "autonomous"
              ? "The company keeps moving on its own until a limit or failure stops it."
              : "The company works on its own and pauses only at key decision points."
        }
      />
      <ModeButtonGroup
        id="components-company-companyworkspaceshell-1443"
        label="AI access mode"
        modes={["managed", "byok"] as CompanyAIAccessMode[]}
        value={controller.editableAIAccessMode}
        getLabel={(mode) => (mode === "managed" ? "Managed" : "BYOK")}
        onChange={controller.setEditableAIAccessMode}
        description={
          controller.editableAIAccessMode === "managed"
            ? "Managed uses ForgeGraph's AI access so you can keep operating immediately."
            : "BYOK uses your own API key and is best when you want the company to operate on your AI access."
        }
      />
    </div>
  );
}

function ModeButtonGroup<TMode extends string>({
  description,
  getLabel,
  id,
  label,
  modes,
  onChange,
  value,
}: {
  description: string;
  getLabel: (mode: TMode) => string;
  id: string;
  label: string;
  modes: TMode[];
  onChange: (mode: TMode) => void;
  value: TMode;
}) {
  return (
    <div>
      <label htmlFor={id} className="text-[11px] uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">
        {label}
      </label>
      <div className="mt-2 flex flex-wrap gap-2">
        {modes.map((mode) => (
          <button
            id={id}
            key={mode}
            type="button"
            onClick={() => onChange(mode)}
            className={`rounded-full border px-3 py-2 text-sm transition-colors ${
              value === mode
                ? "border-zinc-950 bg-zinc-950 text-white dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-950"
                : "border-zinc-900/10 bg-white/80 text-zinc-700 dark:border-white/10 dark:bg-white/5 dark:text-zinc-200"
            }`}
          >
            {getLabel(mode)}
          </button>
        ))}
      </div>
      <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">{description}</p>
    </div>
  );
}

function CompanyLaunchControl({ controller }: { controller: CompanyWorkspaceController }) {
  return (
    <div>
      <label
        htmlFor="components-company-companyworkspaceshell-1471"
        className="text-[11px] uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400"
      >
        Launch operation
      </label>
      <Input
        id="components-company-companyworkspaceshell-1471"
        data-testid="company-launch-operation-input"
        className="mt-2"
        value={controller.operationBrief}
        onChange={(event) => controller.setOperationBrief(event.target.value)}
        placeholder="Start the next company operation"
      />
      <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
        Use one clear instruction. The company will turn it into work across the selected departments.
      </p>
    </div>
  );
}

function CompanyControlActions({ controller }: { controller: CompanyWorkspaceController }) {
  return (
    <div className="flex flex-wrap gap-3">
      <Button
        data-testid="company-launch-operation-button"
        onClick={() => void controller.handleLaunchOperation()}
        disabled={controller.launching || controller.companyPaused}
      >
        {controller.launching ? <Spinner size="xs" className="mr-2" /> : <PlayCircle className="size-4" />}
        Launch operation
      </Button>
      <Button
        data-testid="company-retry-operation-button"
        variant="outline"
        onClick={() => void controller.handleRetryFailedOperation()}
        disabled={controller.retrying || !controller.latestFailedOperation}
      >
        {controller.retrying ? <Spinner size="xs" className="mr-2" /> : <RotateCcw className="size-4" />}
        Retry failed operation
      </Button>
      <Button
        data-testid="company-update-objective-button"
        variant="outline"
        onClick={() => void controller.handleSaveObjective()}
        disabled={controller.savingObjective}
      >
        {controller.savingObjective ? <Spinner size="xs" className="mr-2" /> : <Bot className="size-4" />}
        Update objective
      </Button>
      <Button
        variant="outline"
        onClick={() => void controller.handleToggleCompanyPause()}
        disabled={controller.savingCompanyState}
      >
        {controller.savingCompanyState ? (
          <Spinner size="xs" className="mr-2" />
        ) : controller.companyPaused ? (
          <PlayCircle className="size-4" />
        ) : (
          <PauseCircle className="size-4" />
        )}
        {controller.companyPaused ? "Resume company" : "Pause company"}
      </Button>
    </div>
  );
}

function LatestOutputsPanel({ controller }: { controller: CompanyWorkspaceController }) {
  return (
    <div data-guide-id="company-latest-outputs" className="mt-5">
      <p className="text-[11px] uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">Latest outputs</p>
      <MicroExplanation className="mt-2">
        Completed operations leave readable deliverables here so you can quickly decide whether to launch, refine, or
        retry.
      </MicroExplanation>
      <div className="mt-3 space-y-3">
        {controller.latestCompletedOutputs.length ? (
          controller.latestCompletedOutputs.map((item) => (
            <div
              key={item.id}
              className="rounded-[1.2rem] border border-zinc-900/8 bg-white/70 p-4 dark:border-white/8 dark:bg-white/5"
            >
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm font-semibold text-zinc-950 dark:text-zinc-50">{item.title}</p>
                <Button asChild size="sm" variant="outline" className="rounded-full">
                  <Link href={`/runs/${item.id}`}>Open</Link>
                </Button>
              </div>
              <p className="mt-3 text-sm leading-6 text-zinc-600 dark:text-zinc-300">{item.preview}</p>
            </div>
          ))
        ) : (
          <EmptyBlock
            title="No deliverables yet"
            description="Completed operations will surface their latest outputs here."
          />
        )}
      </div>
    </div>
  );
}

export function CompanyWorkspaceShell(props: CompanyWorkspaceShellProps) {
  const controller = useCompanyWorkspaceShellController(props);
  const inspector = useMemo(() => <CompanyWorkspaceInspector controller={controller} />, [controller]);

  return (
    <ProtectedRoute>
      <DashboardLayout inspector={inspector}>
        <CompanyWorkspaceContent controller={controller} />
      </DashboardLayout>
    </ProtectedRoute>
  );
}
