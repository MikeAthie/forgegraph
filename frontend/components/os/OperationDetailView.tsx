import { useCallback, useEffect, useEffectEvent, useMemo, useReducer, type SetStateAction } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import {
  AlertTriangle,
  ArrowRight,
  ChevronDown,
  ChevronUp,
  Clock3,
  Filter,
  Inbox,
  RotateCcw,
  Square,
} from "lucide-react";

import DashboardLayout from "@/components/DashboardLayout";
import ProtectedRoute from "@/components/ProtectedRoute";
import { Alert, AlertDescription, Button, Spinner } from "@/components/ui";
import { operationRepository } from "@/domain/repositories";
import { translateProductError } from "@/domain/errors";
import type { OperationVM, TaskVM } from "@/domain/translation";
import { useRunLiveUpdates } from "@/hooks/useRunLiveUpdates";
import {
  EmptyBlock,
  InspectorPanel,
  KeyValueGrid,
  Panel,
  SectionHeader,
  StatusBadge,
  formatCurrency,
  formatDateTime,
  formatDuration,
  statusTone,
} from "./operations-ui";
import { showError, showSuccess } from "@/lib/toast";

type OperationDetailViewProps = {
  routeParam: string;
};

type OperationDetailState = {
  operation: OperationVM | null;
  selectedTaskId: string | null;
  loading: boolean;
  error: string | null;
  showAllTasks: boolean;
  actionLoading: "stop" | "retry" | null;
};

type OperationDetailAction = {
  patch: Partial<OperationDetailState> | ((state: OperationDetailState) => Partial<OperationDetailState>);
};

const initialOperationDetailState: OperationDetailState = {
  operation: null,
  selectedTaskId: null,
  loading: true,
  error: null,
  showAllTasks: false,
  actionLoading: null,
};

function operationDetailReducer(state: OperationDetailState, action: OperationDetailAction): OperationDetailState {
  const patch = typeof action.patch === "function" ? action.patch(state) : action.patch;
  return { ...state, ...patch };
}

function resolveStateAction<T>(value: SetStateAction<T>, current: T): T {
  return typeof value === "function" ? (value as (current: T) => T)(current) : value;
}

const primaryActionButtonClass =
  "rounded-full bg-white text-zinc-950 shadow-[0_18px_38px_-24px_rgba(255,255,255,0.85)] hover:bg-zinc-100 dark:bg-zinc-950 dark:text-white dark:hover:bg-zinc-800";
const secondaryActionButtonClass =
  "rounded-full border-white/25 bg-white/10 text-white hover:bg-white/18 hover:text-white dark:border-zinc-950/15 dark:bg-zinc-950/8 dark:text-zinc-950 dark:hover:bg-zinc-950/12";
const destructiveActionButtonClass =
  "rounded-full bg-rose-500 text-white shadow-[0_18px_38px_-24px_rgba(244,63,94,0.85)] hover:bg-rose-400 dark:bg-rose-600 dark:hover:bg-rose-500";

function estimateOperationCost(operation: OperationVM | null) {
  if (!operation) {
    return 0;
  }
  return Math.round((operation.tasks.length * 0.021 + (operation.durationMs ?? 0) * 0.0000004) * 100) / 100;
}

function getTaskNarrative(task: TaskVM) {
  return task.resultPreview || task.issuePreview || task.summary || "No readable activity summary is available yet.";
}

function shouldPollOperationStatus(operation: OperationVM | null) {
  return Boolean(operation && !["completed", "failed"].includes(operation.status));
}

type OperationActivityState = {
  failedTasks: TaskVM[];
  decisionTasks: TaskVM[];
  retryTasks: TaskVM[];
  bottleneckTasks: TaskVM[];
  bottleneckIds: Set<string>;
  hiddenRoutineCount: number;
  visibleTasks: TaskVM[];
};

function useOperationDetailController({ routeParam }: OperationDetailViewProps) {
  const router = useRouter();
  const { push } = router;
  const operationId = typeof router.query[routeParam] === "string" ? router.query[routeParam] : null;
  const [detailState, dispatchDetailState] = useReducer(operationDetailReducer, initialOperationDetailState);
  const { operation, selectedTaskId, loading, error, showAllTasks, actionLoading } = detailState;
  const setDetailField = useCallback(
    <K extends keyof OperationDetailState>(key: K, value: SetStateAction<OperationDetailState[K]>) => {
      dispatchDetailState({
        patch: (current) => ({ [key]: resolveStateAction(value, current[key]) }) as Partial<OperationDetailState>,
      });
    },
    [],
  );
  const setOperation = useCallback(
    (value: SetStateAction<OperationVM | null>) => setDetailField("operation", value),
    [setDetailField],
  );
  const setSelectedTaskId = useCallback(
    (value: SetStateAction<string | null>) => setDetailField("selectedTaskId", value),
    [setDetailField],
  );
  const setLoading = useCallback(
    (value: SetStateAction<boolean>) => setDetailField("loading", value),
    [setDetailField],
  );
  const setError = useCallback(
    (value: SetStateAction<string | null>) => setDetailField("error", value),
    [setDetailField],
  );
  const setShowAllTasks = useCallback(
    (value: SetStateAction<boolean>) => setDetailField("showAllTasks", value),
    [setDetailField],
  );
  const setActionLoading = useCallback(
    (value: SetStateAction<"stop" | "retry" | null>) => setDetailField("actionLoading", value),
    [setDetailField],
  );
  const shouldPollCurrentOperation = shouldPollOperationStatus(operation);

  const loadOperation = useCallback(
    async (options?: { showSpinner?: boolean }) => {
      if (!operationId) {
        return;
      }

      if (options?.showSpinner) {
        setLoading(true);
      }
      setError(null);
      try {
        const data = await operationRepository.get(operationId);
        setOperation(data);
        setSelectedTaskId((current) =>
          current && data.tasks.some((task) => task.id === current) ? current : (data.tasks[0]?.id ?? null),
        );
      } catch (loadError: unknown) {
        setError(translateProductError(loadError, "operation"));
      } finally {
        setLoading(false);
      }
    },
    [operationId, setError, setLoading, setOperation, setSelectedTaskId],
  );
  const refreshOperation = useEffectEvent((options?: { showSpinner?: boolean }) => {
    void loadOperation(options);
  });

  useEffect(() => {
    void loadOperation({ showSpinner: true });
  }, [loadOperation]);

  useEffect(() => {
    if (!operationId || typeof window === "undefined" || typeof document === "undefined") {
      return;
    }

    const refreshVisibleOperation = () => {
      if (document.visibilityState === "visible") {
        refreshOperation({ showSpinner: false });
      }
    };

    window.addEventListener("focus", refreshVisibleOperation);
    document.addEventListener("visibilitychange", refreshVisibleOperation);
    return () => {
      window.removeEventListener("focus", refreshVisibleOperation);
      document.removeEventListener("visibilitychange", refreshVisibleOperation);
    };
  }, [operationId, refreshOperation]);

  useEffect(() => {
    if (!operationId || !shouldPollCurrentOperation || typeof window === "undefined") {
      return;
    }

    const poller = window.setInterval(() => {
      refreshOperation({ showSpinner: false });
    }, 2000);

    return () => {
      window.clearInterval(poller);
    };
  }, [operationId, refreshOperation, shouldPollCurrentOperation]);

  useRunLiveUpdates(operationId, () => refreshOperation({ showSpinner: false }));

  const activityState = useMemo<OperationActivityState | null>(() => {
    if (!operation) {
      return null;
    }

    const timedTasks = operation.tasks.filter((task) => typeof task.durationMs === "number");
    const averageDuration =
      timedTasks.length > 0 ? timedTasks.reduce((sum, task) => sum + (task.durationMs ?? 0), 0) / timedTasks.length : 0;
    const bottleneckTasks = timedTasks
      .filter((task) => (task.durationMs ?? 0) >= Math.max(averageDuration * 1.5, 4_000))
      .toSorted((left, right) => (right.durationMs ?? 0) - (left.durationMs ?? 0))
      .slice(0, 2);
    const bottleneckIds = new Set(bottleneckTasks.map((task) => task.id));
    const decisionTasks = operation.tasks.filter(
      (task) => task.requiresApproval || task.status === "paused" || task.status === "waiting_for_decision",
    );
    const failedTasks = operation.tasks.filter((task) =>
      ["failed", "dead_lettered", "cancelled"].includes(task.status),
    );
    const retryTasks = operation.tasks.filter((task) => task.status === "retry_scheduled");
    const highlightIds = new Set([
      ...bottleneckIds,
      ...decisionTasks.map((task) => task.id),
      ...failedTasks.map((task) => task.id),
      ...retryTasks.map((task) => task.id),
    ]);
    const routineTasks = operation.tasks.filter((task) => !highlightIds.has(task.id));
    const visibleRoutineIds = new Set(routineTasks.slice(0, 3).map((task) => task.id));
    const visibleTasks = showAllTasks
      ? operation.tasks
      : operation.tasks.filter(
          (task) => highlightIds.has(task.id) || visibleRoutineIds.has(task.id) || task.id === selectedTaskId,
        );

    return {
      failedTasks,
      decisionTasks,
      retryTasks,
      bottleneckTasks,
      bottleneckIds,
      hiddenRoutineCount: Math.max(routineTasks.length - visibleRoutineIds.size, 0),
      visibleTasks,
    };
  }, [operation, selectedTaskId, showAllTasks]);

  const totalCost = estimateOperationCost(operation);
  const failedTask = activityState?.failedTasks[0] ?? null;
  const decisionTask = activityState?.decisionTasks[0] ?? null;
  const retryTask = activityState?.retryTasks[0] ?? null;
  const bottleneckTask = activityState?.bottleneckTasks[0] ?? null;
  const canStopOperation = operation ? ["queued", "running"].includes(operation.status) : false;
  const isWaitingForApproval = operation?.status === "paused" || Boolean(decisionTask);
  const canRetryOperation = Boolean(operation) && !canStopOperation && !isWaitingForApproval;
  const retryButtonLabel =
    actionLoading === "retry" ? "Retrying" : operation?.status === "completed" ? "Start again" : "Retry operation";
  const actionTitle =
    failedTask || operation?.failure
      ? "Failure needs review"
      : retryTask
        ? "Retry is scheduled"
        : isWaitingForApproval
          ? "Approval is waiting"
          : operation?.status === "running"
            ? "Operation is active"
            : operation?.status === "completed"
              ? "Deliverable is ready"
              : "Operation state";
  const actionDescription =
    failedTask || operation?.failure
      ? (operation?.failure?.summary ?? "A department could not finish its assigned work.")
      : retryTask
        ? `${retryTask.departmentName} has a bounded retry scheduled by the backend.`
        : isWaitingForApproval
          ? "A department needs a human decision before work can continue."
          : operation?.status === "running"
            ? `${operation.currentDepartmentName} is working now.`
            : operation?.status === "completed"
              ? "The operation finished cleanly. Review the deliverable or start another operation when needed."
              : "Review status, task activity, and deliverable readiness.";

  const handleStopOperation = useCallback(async () => {
    if (!operation || actionLoading) {
      return;
    }

    setActionLoading("stop");
    try {
      const updated = await operationRepository.stop(operation.id);
      setOperation(updated);
      showSuccess("Operation stopped", "The operation was canceled by the backend control plane.");
    } catch (stopError: unknown) {
      showError("Stop failed", translateProductError(stopError, "operation"));
    } finally {
      setActionLoading(null);
    }
  }, [actionLoading, operation, setActionLoading, setOperation]);

  const handleRetryOperation = useCallback(async () => {
    if (!operation || actionLoading) {
      return;
    }

    setActionLoading("retry");
    try {
      const retried = await operationRepository.retry(operation.id, {
        aiAccessMode: operation.aiAccess?.llm_mode,
        provider: operation.aiAccess?.provider,
        credentialId: operation.aiAccess?.credential_id,
      });
      showSuccess("Retry started", "A fresh operation has been queued from the saved input.");
      await push(`/runs/${retried.id}`);
    } catch (retryError: unknown) {
      showError("Retry failed", translateProductError(retryError, "operation"));
    } finally {
      setActionLoading(null);
    }
  }, [actionLoading, operation, push, setActionLoading]);

  const handleInspectTask = useCallback(
    (taskId: string) => {
      setSelectedTaskId(taskId);
      if (typeof document !== "undefined") {
        document.getElementById("department-activity")?.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    },
    [setSelectedTaskId],
  );

  return {
    operation,
    loading,
    error,
    showAllTasks,
    actionLoading,
    activityState,
    totalCost,
    failedTask,
    decisionTask,
    retryTask,
    bottleneckTask,
    canStopOperation,
    isWaitingForApproval,
    canRetryOperation,
    retryButtonLabel,
    actionTitle,
    actionDescription,
    setShowAllTasks,
    handleStopOperation,
    handleRetryOperation,
    handleInspectTask,
  };
}

type OperationDetailController = ReturnType<typeof useOperationDetailController>;

function OperationDetailInspector({ operation }: { operation: OperationVM | null }) {
  if (!operation) {
    return null;
  }

  return (
    <InspectorPanel
      title="Operation inspector"
      subtitle="Backend-owned operation state translated into company language."
      sections={[
        { title: "Status", content: <StatusBadge status={operation.status} /> },
        { title: "Current department", content: operation.currentDepartmentName },
        { title: "Deliverable", content: operation.deliverable.ready ? "Ready" : "Not ready yet" },
        {
          title: "Support",
          content: (
            <details>
              <summary className="cursor-pointer font-medium">Show identifiers</summary>
              <div className="mt-2 space-y-1 text-xs">
                <div>Operation ID: {operation.id}</div>
                <div>Company ID: {operation.companyId}</div>
                <div>Setup version ID: {operation.setupVersionId}</div>
              </div>
            </details>
          ),
        },
      ]}
    />
  );
}

function OperationActionBanner({ controller }: { controller: OperationDetailController }) {
  const { operation, failedTask } = controller;
  if (!operation) {
    return null;
  }

  return (
    <div className="overflow-hidden rounded-[1.85rem] border border-zinc-900/10 bg-zinc-950 text-white shadow-[0_32px_90px_-58px_rgba(15,23,42,0.75)] dark:border-white/10 dark:bg-zinc-100 dark:text-zinc-950">
      <div className="flex flex-col gap-5 p-6 xl:flex-row xl:items-center xl:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-[11px] uppercase tracking-[0.2em] text-white/55 dark:text-zinc-500">Operator action</p>
            <StatusBadge status={operation.status} />
          </div>
          <h3 className="mt-3 text-2xl font-semibold tracking-tight" style={{ fontFamily: "var(--font-serif)" }}>
            {controller.actionTitle}
          </h3>
          <p className="mt-2 max-w-3xl text-sm leading-7 text-white/68 dark:text-zinc-600">
            {controller.actionDescription}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2 xl:justify-end">
          {failedTask ? (
            <Button
              type="button"
              className={primaryActionButtonClass}
              onClick={() => controller.handleInspectTask(failedTask.id)}
            >
              Inspect failure
              <ArrowRight className="size-4" />
            </Button>
          ) : null}
          {controller.isWaitingForApproval ? (
            <Button asChild className={primaryActionButtonClass}>
              <Link href="/approvals">
                <Inbox className="size-4" />
                Open approvals
              </Link>
            </Button>
          ) : null}
          {controller.canStopOperation ? (
            <Button
              type="button"
              className={destructiveActionButtonClass}
              onClick={() => void controller.handleStopOperation()}
              disabled={controller.actionLoading !== null}
            >
              <Square className="size-4" />
              {controller.actionLoading === "stop" ? "Stopping" : "Stop operation"}
            </Button>
          ) : null}
          {controller.canRetryOperation ? (
            <Button
              type="button"
              className={failedTask ? secondaryActionButtonClass : primaryActionButtonClass}
              onClick={() => void controller.handleRetryOperation()}
              disabled={controller.actionLoading !== null}
            >
              <RotateCcw className="size-4" />
              {controller.retryButtonLabel}
            </Button>
          ) : null}
          <Button asChild variant="outline" className={secondaryActionButtonClass}>
            <Link href="/runs">Back to operations</Link>
          </Button>
        </div>
      </div>
    </div>
  );
}

function OperationSummaryPanel({ controller }: { controller: OperationDetailController }) {
  const { operation, failedTask, bottleneckTask } = controller;
  if (!operation) {
    return null;
  }

  return (
    <Panel
      title={operation.companyName}
      description="One-screen summary of what happened, what needs attention, and where the operation slowed down."
      action={<StatusBadge status={operation.status} />}
    >
      <div className="grid gap-4 xl:grid-cols-4">
        <OperationMetricCard label="Total duration" value={formatDuration(operation.durationMs)} />
        <OperationMetricCard label="Estimated cost" value={formatCurrency(controller.totalCost)} />
        <OperationMetricCard
          label="Attention point"
          value={failedTask ? failedTask.departmentName : "No failure detected"}
          compact
        />
        <OperationMetricCard
          label="Bottleneck"
          value={
            bottleneckTask
              ? `${bottleneckTask.departmentName} · ${formatDuration(bottleneckTask.durationMs)}`
              : "No bottleneck flagged"
          }
          compact
        />
      </div>
    </Panel>
  );
}

function OperationMetricCard({ label, value, compact }: { label: string; value: string; compact?: boolean }) {
  return (
    <div className="rounded-[1.2rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
      <p className="text-[11px] uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">{label}</p>
      <p
        className={
          compact
            ? "mt-2 text-sm font-semibold text-zinc-950 dark:text-zinc-50"
            : "mt-2 text-2xl font-semibold text-zinc-950 dark:text-zinc-50"
        }
      >
        {value}
      </p>
    </div>
  );
}

function AttentionAndPosturePanels({ controller }: { controller: OperationDetailController }) {
  if (!controller.operation || !controller.activityState) {
    return null;
  }

  return (
    <div className="grid gap-6 2xl:grid-cols-[0.92fr_1.08fr]">
      <AttentionPointsPanel controller={controller} />
      <OperationPosturePanel controller={controller} />
    </div>
  );
}

function AttentionPointsPanel({ controller }: { controller: OperationDetailController }) {
  const hasAttention =
    controller.failedTask || controller.decisionTask || controller.retryTask || controller.bottleneckTask;

  return (
    <Panel title="Attention points" description="The department activity that matters most right now.">
      {hasAttention ? (
        <div className="space-y-3">
          {controller.failedTask ? <FailureAttentionCard task={controller.failedTask} /> : null}
          {controller.decisionTask ? <DecisionAttentionCard task={controller.decisionTask} /> : null}
          {controller.retryTask ? <RetryAttentionCard task={controller.retryTask} /> : null}
          {controller.bottleneckTask ? <BottleneckAttentionCard task={controller.bottleneckTask} /> : null}
        </div>
      ) : (
        <EmptyBlock
          title="No attention point surfaced"
          description="The visible activity completed without a failure, decision boundary, or obvious bottleneck."
        />
      )}
    </Panel>
  );
}

function FailureAttentionCard({ task }: { task: TaskVM }) {
  return (
    <div className="rounded-[1.2rem] border border-rose-800/12 bg-rose-50 p-4 text-rose-950 dark:border-rose-200/15 dark:bg-rose-500/10 dark:text-rose-100">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold">Needs attention</p>
          <p className="mt-2 text-sm leading-7">
            {task.departmentName} needs attention. Inspect this activity before retrying the operation.
          </p>
        </div>
        <AlertTriangle className="size-4 shrink-0" />
      </div>
    </div>
  );
}

function DecisionAttentionCard({ task }: { task: TaskVM }) {
  return (
    <div className="rounded-[1.2rem] border border-amber-800/12 bg-amber-50 p-4 text-amber-950 dark:border-amber-200/15 dark:bg-amber-500/10 dark:text-amber-100">
      <p className="text-sm font-semibold">Decision boundary</p>
      <p className="mt-2 text-sm leading-7">
        {task.departmentName} is waiting on a human decision or approval boundary.
      </p>
    </div>
  );
}

function RetryAttentionCard({ task }: { task: TaskVM }) {
  return (
    <div className="rounded-[1.2rem] border border-amber-800/12 bg-amber-50 p-4 text-amber-950 dark:border-amber-200/15 dark:bg-amber-500/10 dark:text-amber-100">
      <p className="text-sm font-semibold">Retry scheduled</p>
      <p className="mt-2 text-sm leading-7">
        {task.latestRetry?.retry_reason || `${task.departmentName} has a bounded backend retry recorded.`}
      </p>
    </div>
  );
}

function BottleneckAttentionCard({ task }: { task: TaskVM }) {
  return (
    <div className="rounded-[1.2rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-zinc-950 dark:text-zinc-50">Bottleneck</p>
          <p className="mt-2 text-sm leading-7 text-zinc-700 dark:text-zinc-200">
            {task.departmentName} consumed {formatDuration(task.durationMs)} and is materially slower than the rest of
            the operation.
          </p>
        </div>
        <Clock3 className="size-4 shrink-0 text-zinc-500 dark:text-zinc-400" />
      </div>
    </div>
  );
}

function OperationPosturePanel({ controller }: { controller: OperationDetailController }) {
  if (!controller.operation || !controller.activityState) {
    return null;
  }

  return (
    <Panel title="Operation posture" description="Operator-oriented summary of the current operation state.">
      <KeyValueGrid
        columns={2}
        items={[
          {
            label: "Current status",
            value: <StatusBadge status={controller.operation.status} label={controller.operation.status} />,
          },
          { label: "Decision boundaries", value: controller.activityState.decisionTasks.length },
          { label: "Flagged bottlenecks", value: controller.activityState.bottleneckTasks.length },
          {
            label: "Routine tasks hidden",
            value: controller.showAllTasks ? 0 : controller.activityState.hiddenRoutineCount,
          },
        ]}
      />
    </Panel>
  );
}

function DepartmentActivityPanel({ controller }: { controller: OperationDetailController }) {
  const { operation, activityState } = controller;
  if (!operation || !activityState) {
    return null;
  }

  return (
    <div id="department-activity" className="scroll-mt-32">
      <Panel
        title="Department activity"
        description="Routine activity is collapsed by default so the operator can focus on failures, decisions, and bottlenecks first."
        action={<DepartmentActivityToggle controller={controller} />}
      >
        {operation.tasks.length ? (
          <div className="space-y-4">
            {!controller.showAllTasks && activityState.hiddenRoutineCount > 0 ? (
              <CollapsedActivityNotice hiddenRoutineCount={activityState.hiddenRoutineCount} />
            ) : null}
            {activityState.visibleTasks.map((task, index) => (
              <DepartmentActivityItem
                key={task.id}
                task={task}
                index={index}
                isBottleneck={activityState.bottleneckIds.has(task.id)}
                onSelect={() => controller.handleInspectTask(task.id)}
              />
            ))}
          </div>
        ) : (
          <EmptyBlock
            title="No activity available"
            description="This operation has not emitted any department activity yet."
          />
        )}
      </Panel>
    </div>
  );
}

function DepartmentActivityToggle({ controller }: { controller: OperationDetailController }) {
  if (!controller.operation || controller.operation.tasks.length <= 3) {
    return null;
  }

  return (
    <Button
      type="button"
      variant="outline"
      className="rounded-full"
      onClick={() => controller.setShowAllTasks((current) => !current)}
    >
      {controller.showAllTasks ? (
        <>
          Collapse routine activity
          <ChevronUp className="size-4" />
        </>
      ) : (
        <>
          Show all activity
          <ChevronDown className="size-4" />
        </>
      )}
    </Button>
  );
}

function CollapsedActivityNotice({ hiddenRoutineCount }: { hiddenRoutineCount: number }) {
  return (
    <div className="flex items-center gap-2 rounded-[1.2rem] border border-zinc-900/8 bg-[var(--panel-muted)] px-4 py-3 text-sm text-zinc-600 dark:border-white/8 dark:text-zinc-300">
      <Filter className="size-4" />
      {hiddenRoutineCount} routine activit{hiddenRoutineCount === 1 ? "y" : "ies"} collapsed.
    </div>
  );
}

function DepartmentActivityItem({
  task,
  index,
  isBottleneck,
  onSelect,
}: {
  task: TaskVM;
  index: number;
  isBottleneck: boolean;
  onSelect: () => void;
}) {
  const tone = statusTone(task.status);
  const isDecision = Boolean(task.requiresApproval);

  return (
    <button
      type="button"
      onClick={onSelect}
      className="w-full rounded-[1.3rem] border border-zinc-900/8 bg-white/75 p-5 text-left transition-colors hover:bg-[var(--panel-muted)] dark:border-white/8 dark:bg-white/4 dark:hover:bg-white/8"
    >
      <div className="grid gap-4 xl:grid-cols-[3.5rem_minmax(0,1fr)_13rem]">
        <div className="flex items-start gap-3 xl:block">
          <div className="flex size-10 items-center justify-center rounded-2xl border border-zinc-900/10 bg-[var(--panel-muted)] text-sm font-semibold dark:border-white/10">
            {index + 1}
          </div>
        </div>
        <DepartmentActivityNarrative task={task} isDecision={isDecision} isBottleneck={isBottleneck} />
        <DepartmentActivityMetrics task={task} tone={tone} />
      </div>
    </button>
  );
}

function DepartmentActivityNarrative({
  task,
  isDecision,
  isBottleneck,
}: {
  task: TaskVM;
  isDecision: boolean;
  isBottleneck: boolean;
}) {
  return (
    <div className="min-w-0">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-sm font-semibold text-zinc-950 dark:text-zinc-50">{task.departmentName}</p>
        <StatusBadge status={task.status} />
        <StatusBadge status="pending" label="department activity" />
        {isDecision ? <StatusBadge status="paused" label="decision" /> : null}
        {isBottleneck ? <StatusBadge status="pending" label="bottleneck" /> : null}
        {task.deadLetter ? <StatusBadge status="dead_lettered" label="dead letter" /> : null}
        {task.latestRetry ? <StatusBadge status="retry_scheduled" label="retry" /> : null}
      </div>
      <p className="mt-3 text-sm leading-7 text-zinc-600 dark:text-zinc-300">{getTaskNarrative(task)}</p>
      {task.toolName ? (
        <p className="mt-3 text-xs text-zinc-500 dark:text-zinc-400">Tool {task.toolName} · Completed</p>
      ) : null}
    </div>
  );
}

function DepartmentActivityMetrics({ task, tone }: { task: TaskVM; tone: string }) {
  return (
    <div className="grid gap-2 text-sm">
      <TaskMetricBox label="Duration" value={formatDuration(task.durationMs)} />
      <TaskMetricBox label="Started" value={formatDateTime(task.startedAt)} />
      {tone === "rose" ? (
        <div className="rounded-2xl border border-rose-800/15 bg-rose-50 px-3 py-2 text-rose-900 dark:border-rose-200/20 dark:bg-rose-500/10 dark:text-rose-100">
          <p className="text-[11px] uppercase tracking-[0.16em]">Failure</p>
          <p className="mt-1 text-xs">{task.deadLetter?.reason || "This activity requires intervention here."}</p>
        </div>
      ) : null}
      {task.latestRetry ? (
        <div className="rounded-2xl border border-amber-800/15 bg-amber-50 px-3 py-2 text-amber-900 dark:border-amber-200/20 dark:bg-amber-500/10 dark:text-amber-100">
          <p className="text-[11px] uppercase tracking-[0.16em]">Retry</p>
          <p className="mt-1 text-xs">
            Attempt {task.latestRetry.attempt_number ?? "?"} of {task.latestRetry.max_attempts ?? "?"}
          </p>
        </div>
      ) : null}
    </div>
  );
}

function TaskMetricBox({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-zinc-900/8 bg-[var(--panel-muted)] px-3 py-2 dark:border-white/8">
      <p className="text-[11px] uppercase tracking-[0.16em] text-zinc-500 dark:text-zinc-400">{label}</p>
      <p className="mt-1 font-medium text-zinc-900 dark:text-zinc-100">{value}</p>
    </div>
  );
}

function OperationStateAndDeliverable({ operation }: { operation: OperationVM }) {
  return (
    <div className="grid gap-6 2xl:grid-cols-2">
      <Panel title="Operation state" description="Canonical timing, queue status, and memory posture.">
        <KeyValueGrid
          columns={2}
          items={[
            { label: "Started", value: formatDateTime(operation.startedAt) },
            { label: "Ended", value: formatDateTime(operation.endedAt) },
            { label: "Queue status", value: operation.queueStatus ?? "Not queued" },
            { label: "Attempts", value: operation.attempts },
          ]}
        />
      </Panel>
      <DeliverablePanel operation={operation} />
    </div>
  );
}

function DeliverablePanel({ operation }: { operation: OperationVM }) {
  return (
    <Panel title="Deliverable" description="The latest readable result produced by this operation.">
      {operation.deliverable.ready ? (
        <div className="rounded-[1.2rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
          <p className="text-sm font-semibold text-zinc-950 dark:text-zinc-50">{operation.deliverable.title}</p>
          <p className="mt-2 text-sm leading-7 text-zinc-600 dark:text-zinc-300">
            {operation.deliverable.content ?? operation.deliverable.preview}
          </p>
        </div>
      ) : (
        <EmptyBlock
          title="Deliverable not ready"
          description="The deliverable will appear after the company finishes this operation."
        />
      )}
    </Panel>
  );
}

function OperationLoadedContent({ controller }: { controller: OperationDetailController }) {
  if (controller.loading || !controller.operation || !controller.activityState) {
    return (
      <div className="flex min-h-[320px] items-center justify-center rounded-[1.75rem] border border-zinc-900/10 bg-white/70 dark:border-white/10 dark:bg-zinc-950/50">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <>
      <OperationActionBanner controller={controller} />
      <OperationSummaryPanel controller={controller} />
      <AttentionAndPosturePanels controller={controller} />
      <DepartmentActivityPanel controller={controller} />
      <OperationStateAndDeliverable operation={controller.operation} />
    </>
  );
}

export default function OperationDetailView({ routeParam }: OperationDetailViewProps) {
  const controller = useOperationDetailController({ routeParam });

  return (
    <ProtectedRoute>
      <DashboardLayout inspector={<OperationDetailInspector operation={controller.operation} />}>
        <div className="space-y-6">
          <SectionHeader
            eyebrow="Operation Detail"
            title={controller.operation?.companyName ?? "Operation"}
            description="Inspect department activity, approvals, deliverables, and attention points without exposing technical internals."
          />

          {controller.error ? (
            <Alert variant="destructive">
              <AlertDescription>{controller.error}</AlertDescription>
            </Alert>
          ) : null}

          <OperationLoadedContent controller={controller} />
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
