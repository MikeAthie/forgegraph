import { useCallback, useEffect, useMemo, useState } from "react";
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

const primaryActionButtonClass =
  "rounded-full bg-white text-slate-950 shadow-[0_18px_38px_-24px_rgba(255,255,255,0.85)] hover:bg-slate-100 dark:bg-slate-950 dark:text-white dark:hover:bg-slate-800";
const secondaryActionButtonClass =
  "rounded-full border-white/25 bg-white/10 text-white hover:bg-white/18 hover:text-white dark:border-slate-950/15 dark:bg-slate-950/8 dark:text-slate-950 dark:hover:bg-slate-950/12";
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

export default function OperationDetailView({ routeParam }: OperationDetailViewProps) {
  const router = useRouter();
  const operationId = typeof router.query[routeParam] === "string" ? router.query[routeParam] : null;
  const [operation, setOperation] = useState<OperationVM | null>(null);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAllTasks, setShowAllTasks] = useState(false);
  const [actionLoading, setActionLoading] = useState<"stop" | "retry" | null>(null);

  const loadOperation = useCallback(async (options?: { showSpinner?: boolean }) => {
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
  }, [operationId]);

  useEffect(() => {
    void loadOperation({ showSpinner: true });
  }, [loadOperation]);

  useRunLiveUpdates(operationId, () => loadOperation({ showSpinner: false }));

  const selectedTask = useMemo(
    () => operation?.tasks.find((task) => task.id === selectedTaskId) ?? operation?.tasks[0] ?? null,
    [operation?.tasks, selectedTaskId],
  );

  const activityState = useMemo(() => {
    if (!operation) {
      return null;
    }

    const timedTasks = operation.tasks.filter((task) => typeof task.durationMs === "number");
    const averageDuration =
      timedTasks.length > 0 ? timedTasks.reduce((sum, task) => sum + (task.durationMs ?? 0), 0) / timedTasks.length : 0;
    const bottleneckTasks = timedTasks
      .filter((task) => (task.durationMs ?? 0) >= Math.max(averageDuration * 1.5, 4_000))
      .sort((left, right) => (right.durationMs ?? 0) - (left.durationMs ?? 0))
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
    actionLoading === "retry" ? "Retrying..." : operation?.status === "completed" ? "Start again" : "Retry operation";
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
  }, [actionLoading, operation]);

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
      await router.push(`/runs/${retried.id}`);
    } catch (retryError: unknown) {
      showError("Retry failed", translateProductError(retryError, "operation"));
    } finally {
      setActionLoading(null);
    }
  }, [actionLoading, operation, router]);

  const handleInspectTask = useCallback((taskId: string) => {
    setSelectedTaskId(taskId);
    if (typeof document !== "undefined") {
      document.getElementById("department-activity")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, []);

  return (
    <ProtectedRoute>
      <DashboardLayout
        inspector={
          operation ? (
            <InspectorPanel
              title="Operation inspector"
              subtitle="Backend-owned operation state translated into company language."
              sections={[
                {
                  title: "Status",
                  content: <StatusBadge status={operation.status} />,
                },
                {
                  title: "Current department",
                  content: operation.currentDepartmentName,
                },
                {
                  title: "Deliverable",
                  content: operation.deliverable.ready ? "Ready" : "Not ready yet",
                },
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
          ) : null
        }
      >
        <div className="space-y-6">
          <SectionHeader
            eyebrow="Operation Detail"
            title={operation?.companyName ?? "Operation"}
            description="Inspect department activity, approvals, deliverables, and attention points without exposing engine internals."
          />

          {error ? (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}

          {loading || !operation || !activityState ? (
            <div className="flex min-h-[320px] items-center justify-center rounded-[1.75rem] border border-slate-900/10 bg-white/70 dark:border-white/10 dark:bg-slate-950/50">
              <Spinner size="lg" />
            </div>
          ) : (
            <>
              <div className="overflow-hidden rounded-[1.85rem] border border-slate-900/10 bg-slate-950 text-white shadow-[0_32px_90px_-58px_rgba(15,23,42,0.75)] dark:border-white/10 dark:bg-slate-100 dark:text-slate-950">
                <div className="flex flex-col gap-5 px-6 py-6 xl:flex-row xl:items-center xl:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-[11px] uppercase tracking-[0.2em] text-white/55 dark:text-slate-500">
                        Operator action
                      </p>
                      <StatusBadge status={operation.status} />
                    </div>
                    <h3
                      className="mt-3 text-2xl font-semibold tracking-tight"
                      style={{ fontFamily: "var(--font-serif)" }}
                    >
                      {actionTitle}
                    </h3>
                    <p className="mt-2 max-w-3xl text-sm leading-7 text-white/68 dark:text-slate-600">
                      {actionDescription}
                    </p>
                  </div>

                  <div className="flex flex-wrap items-center gap-2 xl:justify-end">
                    {failedTask ? (
                      <Button
                        type="button"
                        className={primaryActionButtonClass}
                        onClick={() => handleInspectTask(failedTask.id)}
                      >
                        Inspect failure
                        <ArrowRight className="h-4 w-4" />
                      </Button>
                    ) : null}

                    {isWaitingForApproval ? (
                      <Button asChild className={primaryActionButtonClass}>
                        <Link href="/approvals">
                          <Inbox className="h-4 w-4" />
                          Open approvals
                        </Link>
                      </Button>
                    ) : null}

                    {canStopOperation ? (
                      <Button
                        type="button"
                        className={destructiveActionButtonClass}
                        onClick={() => void handleStopOperation()}
                        disabled={actionLoading !== null}
                      >
                        <Square className="h-4 w-4" />
                        {actionLoading === "stop" ? "Stopping..." : "Stop operation"}
                      </Button>
                    ) : null}

                    {canRetryOperation ? (
                      <Button
                        type="button"
                        className={failedTask ? secondaryActionButtonClass : primaryActionButtonClass}
                        onClick={() => void handleRetryOperation()}
                        disabled={actionLoading !== null}
                      >
                        <RotateCcw className="h-4 w-4" />
                        {retryButtonLabel}
                      </Button>
                    ) : null}

                    <Button asChild variant="outline" className={secondaryActionButtonClass}>
                      <Link href="/runs">Back to operations</Link>
                    </Button>
                  </div>
                </div>
              </div>

              <Panel
                title={operation.companyName}
                description="One-screen summary of what happened, what needs attention, and where the operation slowed down."
                action={<StatusBadge status={operation.status} />}
              >
                <div className="grid gap-4 xl:grid-cols-4">
                  <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                      Total duration
                    </p>
                    <p className="mt-2 text-2xl font-semibold text-slate-950 dark:text-slate-50">
                      {formatDuration(operation.durationMs)}
                    </p>
                  </div>
                  <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                      Estimated cost
                    </p>
                    <p className="mt-2 text-2xl font-semibold text-slate-950 dark:text-slate-50">
                      {formatCurrency(totalCost)}
                    </p>
                  </div>
                  <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                      Attention point
                    </p>
                    <p className="mt-2 text-sm font-semibold text-slate-950 dark:text-slate-50">
                      {failedTask ? failedTask.departmentName : "No failure detected"}
                    </p>
                  </div>
                  <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                      Bottleneck
                    </p>
                    <p className="mt-2 text-sm font-semibold text-slate-950 dark:text-slate-50">
                      {bottleneckTask
                        ? `${bottleneckTask.departmentName} · ${formatDuration(bottleneckTask.durationMs)}`
                        : "No bottleneck flagged"}
                    </p>
                  </div>
                </div>
              </Panel>

              <div className="grid gap-6 2xl:grid-cols-[0.92fr_1.08fr]">
                <Panel title="Attention points" description="The department activity that matters most right now.">
                  {failedTask || decisionTask || retryTask || bottleneckTask ? (
                    <div className="space-y-3">
                      {failedTask ? (
                        <div className="rounded-[1.2rem] border border-rose-800/12 bg-rose-50 px-4 py-4 text-rose-950 dark:border-rose-200/15 dark:bg-rose-500/10 dark:text-rose-100">
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <p className="text-sm font-semibold">Needs attention</p>
                              <p className="mt-2 text-sm leading-7">
                                {failedTask.departmentName} needs attention. Inspect this activity before retrying the
                                operation.
                              </p>
                            </div>
                            <AlertTriangle className="h-4 w-4 shrink-0" />
                          </div>
                        </div>
                      ) : null}
                      {decisionTask ? (
                        <div className="rounded-[1.2rem] border border-amber-800/12 bg-amber-50 px-4 py-4 text-amber-950 dark:border-amber-200/15 dark:bg-amber-500/10 dark:text-amber-100">
                          <p className="text-sm font-semibold">Decision boundary</p>
                          <p className="mt-2 text-sm leading-7">
                            {decisionTask.departmentName} is waiting on a human decision or approval boundary.
                          </p>
                        </div>
                      ) : null}
                      {retryTask ? (
                        <div className="rounded-[1.2rem] border border-amber-800/12 bg-amber-50 px-4 py-4 text-amber-950 dark:border-amber-200/15 dark:bg-amber-500/10 dark:text-amber-100">
                          <p className="text-sm font-semibold">Retry scheduled</p>
                          <p className="mt-2 text-sm leading-7">
                            {retryTask.latestRetry?.retry_reason ||
                              `${retryTask.departmentName} has a bounded backend retry recorded.`}
                          </p>
                        </div>
                      ) : null}
                      {bottleneckTask ? (
                        <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">Bottleneck</p>
                              <p className="mt-2 text-sm leading-7 text-slate-700 dark:text-slate-200">
                                {bottleneckTask.departmentName} consumed {formatDuration(bottleneckTask.durationMs)} and
                                is materially slower than the rest of the operation.
                              </p>
                            </div>
                            <Clock3 className="h-4 w-4 shrink-0 text-slate-500 dark:text-slate-400" />
                          </div>
                        </div>
                      ) : null}
                    </div>
                  ) : (
                    <EmptyBlock
                      title="No attention point surfaced"
                      description="The visible activity completed without a failure, decision boundary, or obvious bottleneck."
                    />
                  )}
                </Panel>

                <Panel
                  title="Operation posture"
                  description="Operator-oriented summary of the current operation state."
                >
                  <KeyValueGrid
                    columns={2}
                    items={[
                      {
                        label: "Current status",
                        value: <StatusBadge status={operation.status} label={operation.status} />,
                      },
                      { label: "Decision boundaries", value: activityState.decisionTasks.length },
                      { label: "Flagged bottlenecks", value: activityState.bottleneckTasks.length },
                      { label: "Routine tasks hidden", value: showAllTasks ? 0 : activityState.hiddenRoutineCount },
                    ]}
                  />
                </Panel>
              </div>

              <div id="department-activity" className="scroll-mt-32">
                <Panel
                  title="Department activity"
                  description="Routine activity is collapsed by default so the operator can focus on failures, decisions, and bottlenecks first."
                  action={
                    operation.tasks.length > 3 ? (
                      <Button
                        type="button"
                        variant="outline"
                        className="rounded-full"
                        onClick={() => setShowAllTasks((current) => !current)}
                      >
                        {showAllTasks ? (
                          <>
                            Collapse routine activity
                            <ChevronUp className="h-4 w-4" />
                          </>
                        ) : (
                          <>
                            Show all activity
                            <ChevronDown className="h-4 w-4" />
                          </>
                        )}
                      </Button>
                    ) : null
                  }
                >
                  {operation.tasks.length ? (
                    <div className="space-y-4">
                      {!showAllTasks && activityState.hiddenRoutineCount > 0 ? (
                        <div className="flex items-center gap-2 rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-3 text-sm text-slate-600 dark:border-white/8 dark:text-slate-300">
                          <Filter className="h-4 w-4" />
                          {activityState.hiddenRoutineCount} routine activit
                          {activityState.hiddenRoutineCount === 1 ? "y" : "ies"} collapsed.
                        </div>
                      ) : null}

                      {activityState.visibleTasks.map((task, index) => {
                        const tone = statusTone(task.status);
                        const isBottleneck = activityState.bottleneckIds.has(task.id);
                        const isDecision = Boolean(task.requiresApproval);

                        return (
                          <button
                            key={task.id}
                            type="button"
                            onClick={() => setSelectedTaskId(task.id)}
                            className="w-full rounded-[1.3rem] border border-slate-900/8 bg-white/75 px-5 py-5 text-left transition-colors hover:bg-[var(--panel-muted)] dark:border-white/8 dark:bg-white/4 dark:hover:bg-white/8"
                          >
                            <div className="grid gap-4 xl:grid-cols-[3.5rem_minmax(0,1fr)_13rem]">
                              <div className="flex items-start gap-3 xl:block">
                                <div className="flex h-10 w-10 items-center justify-center rounded-2xl border border-slate-900/10 bg-[var(--panel-muted)] text-sm font-semibold dark:border-white/10">
                                  {index + 1}
                                </div>
                              </div>
                              <div className="min-w-0">
                                <div className="flex flex-wrap items-center gap-2">
                                  <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">
                                    {task.departmentName}
                                  </p>
                                  <StatusBadge status={task.status} />
                                  <StatusBadge status="pending" label="department activity" />
                                  {isDecision ? <StatusBadge status="paused" label="decision" /> : null}
                                  {isBottleneck ? <StatusBadge status="pending" label="bottleneck" /> : null}
                                  {task.deadLetter ? <StatusBadge status="dead_lettered" label="dead letter" /> : null}
                                  {task.latestRetry ? <StatusBadge status="retry_scheduled" label="retry" /> : null}
                                </div>
                                <p className="mt-3 text-sm leading-7 text-slate-600 dark:text-slate-300">
                                  {getTaskNarrative(task)}
                                </p>
                                {task.toolName ? (
                                  <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
                                    Tool {task.toolName} · Completed
                                  </p>
                                ) : null}
                              </div>
                              <div className="grid gap-2 text-sm">
                                <div className="rounded-2xl border border-slate-900/8 bg-[var(--panel-muted)] px-3 py-2 dark:border-white/8">
                                  <p className="text-[11px] uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
                                    Duration
                                  </p>
                                  <p className="mt-1 font-medium text-slate-900 dark:text-slate-100">
                                    {formatDuration(task.durationMs)}
                                  </p>
                                </div>
                                <div className="rounded-2xl border border-slate-900/8 bg-[var(--panel-muted)] px-3 py-2 dark:border-white/8">
                                  <p className="text-[11px] uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
                                    Started
                                  </p>
                                  <p className="mt-1 font-medium text-slate-900 dark:text-slate-100">
                                    {formatDateTime(task.startedAt)}
                                  </p>
                                </div>
                                {tone === "rose" ? (
                                  <div className="rounded-2xl border border-rose-800/15 bg-rose-50 px-3 py-2 text-rose-900 dark:border-rose-200/20 dark:bg-rose-500/10 dark:text-rose-100">
                                    <p className="text-[11px] uppercase tracking-[0.16em]">Failure</p>
                                    <p className="mt-1 text-xs">
                                      {task.deadLetter?.reason || "This activity requires intervention here."}
                                    </p>
                                  </div>
                                ) : null}
                                {task.latestRetry ? (
                                  <div className="rounded-2xl border border-amber-800/15 bg-amber-50 px-3 py-2 text-amber-900 dark:border-amber-200/20 dark:bg-amber-500/10 dark:text-amber-100">
                                    <p className="text-[11px] uppercase tracking-[0.16em]">Retry</p>
                                    <p className="mt-1 text-xs">
                                      Attempt {task.latestRetry.attempt_number ?? "?"} of{" "}
                                      {task.latestRetry.max_attempts ?? "?"}
                                    </p>
                                  </div>
                                ) : null}
                              </div>
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  ) : (
                    <EmptyBlock
                      title="No activity available"
                      description="This operation has not emitted any department activity yet."
                    />
                  )}
                </Panel>
              </div>

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

                <Panel title="Deliverable" description="The latest readable result produced by this operation.">
                  {operation.deliverable.ready ? (
                    <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                      <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">
                        {operation.deliverable.title}
                      </p>
                      <p className="mt-2 text-sm leading-7 text-slate-600 dark:text-slate-300">
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
              </div>
            </>
          )}
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
