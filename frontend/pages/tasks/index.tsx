import { useCallback, useEffect, useMemo, useReducer } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import { Play, Save, Scale, Trash2 } from "lucide-react";

import DashboardLayout from "@/components/DashboardLayout";
import {
  EmptyBlock, InspectorPanel, KeyValueGrid, Panel, SectionHeader, SelectionList, StatusBadge } from "@/components/os/operations-ui";
import { formatDateTime } from "@/components/os/operations-format";
import ProtectedRoute from "@/components/ProtectedRoute";
import { Alert, AlertDescription, Button, Spinner } from "@/components/ui";
import { operationRepository } from "@/domain/repositories";
import { translateProductError } from "@/domain/errors";
import type { TaskVM } from "@/domain/translation";
import { tasksApi, type TaskJudge } from "@/lib/api";

function splitCriteria(value: string): string[] {
  return value.split(/\r?\n/).flatMap((item) => {
    const trimmed = item.trim();
    return trimmed ? [trimmed] : [];
  });
}

function judgeSummaryFrom(judge: TaskJudge): TaskVM["judge"] {
  return {
    id: judge.id,
    title: judge.title,
    criteriaCount: judge.criteria.length,
    passThreshold: judge.pass_threshold,
    status: judge.status,
    score: judge.score,
    evaluatedAt: judge.evaluated_at,
  };
}

function judgeStatusLabel(judge: TaskJudge | TaskVM["judge"] | null | undefined): string {
  if (!judge) return "No judge";
  if (judge.status === "passed") return `Passed${judge.score == null ? "" : ` · ${judge.score}`}`;
  if (judge.status === "failed") return `Failed${judge.score == null ? "" : ` · ${judge.score}`}`;
  if (judge.status === "inconclusive") return "Inconclusive";
  return "Pending";
}

function judgeGradeLabel(judge: TaskJudge): string {
  return judge.score == null ? "Not graded" : `${judge.score}/100`;
}

function getJudgeCriteriaResults(judge: TaskJudge | null) {
  const rawCriteria = judge?.result?.criteria;
  return Array.isArray(rawCriteria)
    ? rawCriteria
        .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object"))
        .slice(0, 6)
    : [];
}

type TasksPageState = {
  tasks: TaskVM[];
  loading: boolean;
  error: string | null;
  judge: TaskJudge | null;
  judgeLoading: boolean;
  judgeSaving: boolean;
  judgeError: string | null;
  judgeTitle: string;
  judgeInstructions: string;
  judgeCriteria: string;
  judgeThreshold: number;
};

type TasksPageAction =
  | { type: "tasks-success"; tasks: TaskVM[] }
  | { type: "tasks-error"; error: string }
  | { type: "judge-empty" }
  | { type: "judge-load-start" }
  | { type: "judge-load-success"; judge: TaskJudge | null; taskTitle: string }
  | { type: "judge-load-error"; error: string }
  | { type: "judge-field"; field: "judgeTitle" | "judgeInstructions" | "judgeCriteria"; value: string }
  | { type: "judge-threshold"; value: number }
  | { type: "judge-action-start" }
  | { type: "judge-action-success"; taskId: string; judge: TaskJudge }
  | { type: "judge-delete-success"; taskId: string; taskTitle: string }
  | { type: "judge-action-error"; error: string };

const initialTasksPageState: TasksPageState = {
  tasks: [],
  loading: true,
  error: null,
  judge: null,
  judgeLoading: false,
  judgeSaving: false,
  judgeError: null,
  judgeTitle: "",
  judgeInstructions: "",
  judgeCriteria: "",
  judgeThreshold: 80,
};

function updateTaskJudge(tasks: TaskVM[], taskId: string, updatedJudge: TaskJudge | null): TaskVM[] {
  return tasks.map((task) =>
    task.id === taskId
      ? {
          ...task,
          judge: updatedJudge ? judgeSummaryFrom(updatedJudge) : null,
        }
      : task,
  );
}

function getDefaultSelectedTask(tasks: TaskVM[]): TaskVM | null {
  return tasks.find((task) => task.status === "dead_lettered" || task.deadLetter) ?? tasks[0] ?? null;
}

function tasksPageReducer(state: TasksPageState, action: TasksPageAction): TasksPageState {
  switch (action.type) {
    case "tasks-success":
      return { ...state, tasks: action.tasks, loading: false, error: null };
    case "tasks-error":
      return { ...state, loading: false, error: action.error };
    case "judge-empty":
      return { ...state, judge: null, judgeLoading: false };
    case "judge-load-start":
      return { ...state, judgeLoading: true, judgeError: null };
    case "judge-load-success":
      return {
        ...state,
        judge: action.judge,
        judgeLoading: false,
        judgeTitle: action.judge?.title || `Judge: ${action.taskTitle}`,
        judgeInstructions: action.judge?.instructions || "",
        judgeCriteria: action.judge?.criteria?.join("\n") || "",
        judgeThreshold: action.judge?.pass_threshold ?? 80,
      };
    case "judge-load-error":
      return { ...state, judgeLoading: false, judgeError: action.error };
    case "judge-field":
      return { ...state, [action.field]: action.value };
    case "judge-threshold":
      return { ...state, judgeThreshold: action.value };
    case "judge-action-start":
      return { ...state, judgeSaving: true, judgeError: null };
    case "judge-action-success":
      return {
        ...state,
        judge: action.judge,
        judgeSaving: false,
        tasks: updateTaskJudge(state.tasks, action.taskId, action.judge),
      };
    case "judge-delete-success":
      return {
        ...state,
        judge: null,
        judgeSaving: false,
        judgeTitle: `Judge: ${action.taskTitle}`,
        judgeInstructions: "",
        judgeCriteria: "",
        judgeThreshold: 80,
        tasks: updateTaskJudge(state.tasks, action.taskId, null),
      };
    case "judge-action-error":
      return { ...state, judgeSaving: false, judgeError: action.error };
    default:
      return state;
  }
}

function useTasksPageController() {
  const router = useRouter();
  const { replace } = router;
  const [
    {
      tasks,
      loading,
      error,
      judge,
      judgeLoading,
      judgeSaving,
      judgeError,
      judgeTitle,
      judgeInstructions,
      judgeCriteria,
      judgeThreshold,
    },
    dispatchTasks,
  ] = useReducer(tasksPageReducer, initialTasksPageState);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const data = await operationRepository.listTasks();
        if (!cancelled) {
          dispatchTasks({ type: "tasks-success", tasks: data });
        }
      } catch (err: unknown) {
        if (!cancelled) {
          dispatchTasks({ type: "tasks-error", error: translateProductError(err, "department") });
        }
      }
    };

    void load();

    return () => {
      cancelled = true;
    };
  }, []);

  const defaultSelectedTask = useMemo(() => getDefaultSelectedTask(tasks), [tasks]);
  const selectedTaskId = typeof router.query.task === "string" ? router.query.task : (defaultSelectedTask?.id ?? null);

  const selectedTask = useMemo(
    () => tasks.find((task) => task.id === selectedTaskId) ?? defaultSelectedTask,
    [defaultSelectedTask, selectedTaskId, tasks],
  );

  useEffect(() => {
    let cancelled = false;

    const loadJudge = async () => {
      if (!selectedTask?.id) {
        dispatchTasks({ type: "judge-empty" });
        return;
      }
      dispatchTasks({ type: "judge-load-start" });
      try {
        const data = await tasksApi.getJudge(selectedTask.id);
        if (cancelled) return;
        dispatchTasks({ type: "judge-load-success", judge: data, taskTitle: selectedTask.title });
      } catch (err: unknown) {
        if (!cancelled) {
          dispatchTasks({ type: "judge-load-error", error: translateProductError(err, "department") });
        }
      }
    };

    void loadJudge();

    return () => {
      cancelled = true;
    };
  }, [selectedTask?.id, selectedTask?.title]);

  const handleSaveJudge = useCallback(async () => {
    if (!selectedTask) return;
    dispatchTasks({ type: "judge-action-start" });
    try {
      const savedJudge = await tasksApi.saveJudge(selectedTask.id, {
        title: judgeTitle,
        instructions: judgeInstructions,
        criteria: splitCriteria(judgeCriteria),
        pass_threshold: judgeThreshold,
      });
      dispatchTasks({ type: "judge-action-success", taskId: selectedTask.id, judge: savedJudge });
    } catch (err: unknown) {
      dispatchTasks({ type: "judge-action-error", error: translateProductError(err, "department") });
    }
  }, [judgeCriteria, judgeInstructions, judgeThreshold, judgeTitle, selectedTask]);

  const handleEvaluateJudge = useCallback(async () => {
    if (!selectedTask) return;
    dispatchTasks({ type: "judge-action-start" });
    try {
      const evaluatedJudge = await tasksApi.evaluateJudge(selectedTask.id);
      dispatchTasks({ type: "judge-action-success", taskId: selectedTask.id, judge: evaluatedJudge });
    } catch (err: unknown) {
      dispatchTasks({ type: "judge-action-error", error: translateProductError(err, "department") });
    }
  }, [selectedTask]);

  const handleDeleteJudge = useCallback(async () => {
    if (!selectedTask) return;
    dispatchTasks({ type: "judge-action-start" });
    try {
      await tasksApi.deleteJudge(selectedTask.id);
      dispatchTasks({ type: "judge-delete-success", taskId: selectedTask.id, taskTitle: selectedTask.title });
    } catch (err: unknown) {
      dispatchTasks({ type: "judge-action-error", error: translateProductError(err, "department") });
    }
  }, [selectedTask]);

  const groupedCounts = useMemo(
    () => ({
      running: tasks.filter((task) => task.status === "running" || task.status === "claimed").length,
      waiting: tasks.filter((task) =>
        ["created", "queued", "paused", "waiting_for_decision", "retry_scheduled"].includes(task.status),
      ).length,
      failed: tasks.filter((task) => ["failed", "dead_lettered", "cancelled"].includes(task.status)).length,
    }),
    [tasks],
  );

  const selectTask = useCallback(
    (task: TaskVM) => {
      void replace({ pathname: "/tasks", query: { task: task.id } }, undefined, { shallow: true });
    },
    [replace],
  );

  const updateJudgeField = useCallback((field: "judgeTitle" | "judgeInstructions" | "judgeCriteria", value: string) => {
    dispatchTasks({ type: "judge-field", field, value });
  }, []);

  const updateJudgeThreshold = useCallback((value: number) => {
    dispatchTasks({ type: "judge-threshold", value });
  }, []);

  return {
    tasks,
    loading,
    error,
    selectedTask,
    judge,
    judgeLoading,
    judgeSaving,
    judgeError,
    judgeTitle,
    judgeInstructions,
    judgeCriteria,
    judgeThreshold,
    groupedCounts,
    selectTask,
    updateJudgeField,
    updateJudgeThreshold,
    handleSaveJudge,
    handleEvaluateJudge,
    handleDeleteJudge,
  };
}

type TasksPageController = ReturnType<typeof useTasksPageController>;

function TasksInspector({ selectedTask }: { selectedTask: TaskVM | null }) {
  if (!selectedTask) {
    return null;
  }

  return (
    <InspectorPanel
      title={selectedTask.title}
      subtitle="Task records are the operator-facing projection over operation, department activity, and approval state."
      sections={[
        {
          title: "Routing",
          content: (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span>Operation</span>
                <span className="truncate pl-4">{selectedTask.operationId?.slice(0, 8) ?? "Unavailable"}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Department</span>
                <span className="truncate pl-4">{selectedTask.departmentName}</span>
              </div>
            </div>
          ),
        },
        {
          title: "Task state",
          content: (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span>Current state</span>
                <StatusBadge status={selectedTask.status} />
              </div>
              <div className="flex items-center justify-between">
                <span>Attempt count</span>
                <span>{selectedTask.attemptCount ?? selectedTask.attempt ?? 1}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Support ID</span>
                <span className="truncate pl-4">{selectedTask.lifecycleTaskId?.slice(0, 8) ?? "Unavailable"}</span>
              </div>
            </div>
          ),
        },
        {
          title: "Timing",
          content: (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span>Started</span>
                <span>{formatDateTime(selectedTask.startedAt)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Duration</span>
                <span>{selectedTask.durationMs == null ? "Pending" : `${selectedTask.durationMs}ms`}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Ended</span>
                <span>{formatDateTime(selectedTask.endedAt)}</span>
              </div>
            </div>
          ),
        },
      ]}
    />
  );
}

function TaskQueuePanel({ controller }: { controller: TasksPageController }) {
  const emptyState = useMemo(
    () => <EmptyBlock title="Queue is clear" description="There are no projected tasks in the current time window." />,
    [],
  );

  return (
    <Panel title="Activity queue" description="Select a task to inspect its current state and next action.">
      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        <TaskCountCard label="Running" value={controller.groupedCounts.running} />
        <TaskCountCard label="Waiting" value={controller.groupedCounts.waiting} />
        <TaskCountCard label="Failed" value={controller.groupedCounts.failed} />
      </div>
      <SelectionList
        items={controller.tasks}
        selectedId={controller.selectedTask?.id ?? null}
        onSelect={controller.selectTask}
        empty={emptyState}
      >
        {(task, { selected }) => <TaskQueueItem task={task} selected={selected} />}
      </SelectionList>
    </Panel>
  );
}

function TaskCountCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-[1.2rem] border border-zinc-900/8 bg-[var(--panel-muted)] px-4 py-3 dark:border-white/8">
      <p className="text-[11px] uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-zinc-950 dark:text-zinc-50">{value}</p>
    </div>
  );
}

function TaskQueueItem({ task, selected }: { task: TaskVM; selected: boolean }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <div className="min-w-0">
        <div className="flex min-w-0 flex-wrap items-center gap-2 text-sm font-semibold">
          <span className="min-w-0 truncate">{task.title}</span>
          <StatusBadge status={task.status} />
          {task.judge ? (
            <span className="inline-flex items-center gap-1 rounded-full border border-zinc-900/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-zinc-500 dark:border-white/10 dark:text-zinc-300">
              <Scale className="size-3" aria-hidden="true" />
              {judgeStatusLabel(task.judge)}
            </span>
          ) : null}
        </div>
        <div
          className={
            selected
              ? "mt-2 space-y-1 text-sm leading-6 text-white/78 dark:text-zinc-700"
              : "mt-2 space-y-1 text-sm leading-6 text-zinc-600 dark:text-zinc-300"
          }
        >
          <p>{task.summary}</p>
          {task.deadLetter?.recovery_options?.length ? (
            <p className="text-xs">Recovery: {task.deadLetter.recovery_options.join(", ")}</p>
          ) : null}
        </div>
      </div>
      <div className="shrink-0">
        <span className="text-xs uppercase tracking-[0.16em]">{task.priority}</span>
      </div>
    </div>
  );
}

function TaskDetailPanel({ selectedTask }: { selectedTask: TaskVM }) {
  return (
    <Panel
      title={selectedTask.title}
      description="Summary first, deeper operation detail one click away."
      action={
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status={selectedTask.status} />
          <Button asChild variant="outline" className="rounded-full">
            <Link href={`/runs/${selectedTask.operationId}`}>Open operation</Link>
          </Button>
        </div>
      }
    >
      <KeyValueGrid
        columns={2}
        items={[
          { label: "Priority", value: selectedTask.priority },
          { label: "Department", value: selectedTask.departmentName },
          {
            label: "Decision gate",
            value: selectedTask.requiresApproval ? "Waiting for approval" : "No active decision",
          },
          { label: "Attempts", value: selectedTask.attemptCount ?? selectedTask.attempt ?? 1 },
          {
            label: "Ignored updates",
            value: `${selectedTask.staleEventCount ?? 0} / ${selectedTask.lateEventCount ?? 0}`,
          },
          { label: "Started", value: formatDateTime(selectedTask.startedAt) },
        ]}
      />
      <div className="mt-4 rounded-[1.2rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
        <p className="text-[11px] uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">Summary</p>
        <p className="mt-2 text-sm leading-7 text-zinc-700 dark:text-zinc-200">{selectedTask.summary}</p>
      </div>
      <TaskRetryNotice selectedTask={selectedTask} />
      <TaskRecoveryNotice selectedTask={selectedTask} />
      <TaskStaleUpdatesNotice selectedTask={selectedTask} />
    </Panel>
  );
}

function TaskRetryNotice({ selectedTask }: { selectedTask: TaskVM }) {
  if (!selectedTask.latestRetry) {
    return null;
  }

  return (
    <div className="mt-4 rounded-[1.2rem] border border-amber-900/15 bg-amber-50 p-4 text-amber-950 dark:border-amber-200/15 dark:bg-amber-500/10 dark:text-amber-100">
      <p className="text-[11px] uppercase tracking-[0.18em]">Retry schedule</p>
      <p className="mt-2 text-sm leading-7">
        {selectedTask.latestRetry.retry_reason || "Retry is scheduled"} · attempt{" "}
        {selectedTask.latestRetry.attempt_number ?? "?"} of {selectedTask.latestRetry.max_attempts ?? "?"}
        {selectedTask.latestRetry.next_scheduled_at
          ? ` · next ${formatDateTime(selectedTask.latestRetry.next_scheduled_at)}`
          : ""}
      </p>
    </div>
  );
}

function TaskRecoveryNotice({ selectedTask }: { selectedTask: TaskVM }) {
  if (!selectedTask.deadLetter) {
    return null;
  }

  return (
    <div className="mt-4 rounded-[1.2rem] border border-rose-900/15 bg-rose-50 p-4 text-rose-950 dark:border-rose-200/15 dark:bg-rose-500/10 dark:text-rose-100">
      <p className="text-[11px] uppercase tracking-[0.18em]">Needs recovery</p>
      <p className="mt-2 text-sm leading-7">
        {selectedTask.deadLetter.reason || "Task needs operator recovery."}
        {selectedTask.deadLetter.last_error ? ` Last error: ${selectedTask.deadLetter.last_error}` : ""}
      </p>
      {selectedTask.deadLetter.recovery_options?.length ? (
        <p className="mt-2 text-xs">Recovery: {selectedTask.deadLetter.recovery_options.join(", ")}</p>
      ) : null}
    </div>
  );
}

function TaskStaleUpdatesNotice({ selectedTask }: { selectedTask: TaskVM }) {
  if ((selectedTask.staleEventCount ?? 0) <= 0 && (selectedTask.lateEventCount ?? 0) <= 0) {
    return null;
  }

  return (
    <div className="mt-4 rounded-[1.2rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
      <p className="text-[11px] uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">Ignored stale updates</p>
      <p className="mt-2 text-sm leading-7 text-zinc-700 dark:text-zinc-200">
        Stale: {selectedTask.staleEventCount ?? 0} · Late: {selectedTask.lateEventCount ?? 0}. The saved task state was
        not changed.
      </p>
    </div>
  );
}

function TaskJudgePanel({ controller }: { controller: TasksPageController }) {
  const judgeStatus = controller.judge?.status;

  return (
    <Panel
      title="Task judge"
      description="Acceptance criteria and backend evaluation for this task."
      action={
        controller.judge ? (
          <StatusBadge
            status={
              judgeStatus === "passed"
                ? "completed"
                : judgeStatus === "failed"
                  ? "failed"
                  : judgeStatus === "inconclusive"
                    ? "paused"
                    : "queued"
            }
          />
        ) : null
      }
    >
      {controller.judgeError ? (
        <Alert variant="destructive" className="mb-4">
          <AlertDescription>{controller.judgeError}</AlertDescription>
        </Alert>
      ) : null}
      {controller.judgeLoading ? (
        <div className="flex min-h-[180px] items-center justify-center">
          <Spinner />
        </div>
      ) : (
        <TaskJudgeEditor controller={controller} />
      )}
    </Panel>
  );
}

function TaskJudgeEditor({ controller }: { controller: TasksPageController }) {
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-[1fr_120px]">
        <JudgeTextInput
          label="Name"
          value={controller.judgeTitle}
          onChange={(value) => controller.updateJudgeField("judgeTitle", value)}
        />
        <label className="space-y-1 text-sm">
          <span className="font-medium text-zinc-700 dark:text-zinc-200">Pass</span>
          <input
            type="number"
            min={1}
            max={100}
            value={controller.judgeThreshold}
            onChange={(event) => controller.updateJudgeThreshold(Number(event.target.value))}
            className="w-full rounded-lg border border-zinc-900/10 bg-white px-3 py-2 text-sm text-zinc-950 outline-none focus:border-zinc-900/30 dark:border-white/10 dark:bg-zinc-950 dark:text-zinc-50 dark:focus:border-white/30"
          />
        </label>
      </div>
      <JudgeTextarea
        label="Criteria"
        value={controller.judgeCriteria}
        rows={5}
        placeholder="One criterion per line"
        onChange={(value) => controller.updateJudgeField("judgeCriteria", value)}
      />
      <JudgeTextarea
        label="Rubric note"
        value={controller.judgeInstructions}
        rows={3}
        onChange={(value) => controller.updateJudgeField("judgeInstructions", value)}
      />
      <TaskJudgeActions controller={controller} />
      {controller.judge ? <TaskJudgeResult judge={controller.judge} /> : null}
    </div>
  );
}

function JudgeTextInput({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="space-y-1 text-sm">
      <span className="font-medium text-zinc-700 dark:text-zinc-200">{label}</span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-lg border border-zinc-900/10 bg-white px-3 py-2 text-sm text-zinc-950 outline-none focus:border-zinc-900/30 dark:border-white/10 dark:bg-zinc-950 dark:text-zinc-50 dark:focus:border-white/30"
      />
    </label>
  );
}

function JudgeTextarea({
  label,
  value,
  rows,
  placeholder,
  onChange,
}: {
  label: string;
  value: string;
  rows: number;
  placeholder?: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="space-y-1 text-sm">
      <span className="font-medium text-zinc-700 dark:text-zinc-200">{label}</span>
      <textarea
        value={value}
        onChange={(event) => onChange(event.target.value)}
        rows={rows}
        className="w-full rounded-lg border border-zinc-900/10 bg-white px-3 py-2 text-sm leading-6 text-zinc-950 outline-none focus:border-zinc-900/30 dark:border-white/10 dark:bg-zinc-950 dark:text-zinc-50 dark:focus:border-white/30"
        placeholder={placeholder}
      />
    </label>
  );
}

function TaskJudgeActions({ controller }: { controller: TasksPageController }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button onClick={controller.handleSaveJudge} disabled={controller.judgeSaving} className="rounded-full">
        <Save className="mr-2 size-4" aria-hidden="true" />
        Save judge
      </Button>
      <Button
        variant="outline"
        onClick={controller.handleEvaluateJudge}
        disabled={!controller.judge || controller.judgeSaving}
        className="rounded-full"
      >
        <Play className="mr-2 size-4" aria-hidden="true" />
        Evaluate task
      </Button>
      {controller.judge ? (
        <Button
          variant="ghost"
          onClick={controller.handleDeleteJudge}
          disabled={controller.judgeSaving}
          className="rounded-full"
        >
          <Trash2 className="mr-2 size-4" aria-hidden="true" />
          Remove
        </Button>
      ) : null}
    </div>
  );
}

function TaskJudgeResult({ judge }: { judge: TaskJudge }) {
  const criteriaResults = getJudgeCriteriaResults(judge);

  return (
    <div className="rounded-lg border border-zinc-900/8 bg-[var(--panel-muted)] p-4 text-sm dark:border-white/8">
      <div className="grid gap-3 sm:grid-cols-3">
        <JudgeResultMetric label="Status" value={judgeStatusLabel(judge)} />
        <JudgeResultMetric label="Grade" value={judgeGradeLabel(judge)} />
        <JudgeResultMetric label="Pass mark" value={`${judge.pass_threshold}/100`} />
      </div>
      <p className="mt-3 text-xs text-zinc-500 dark:text-zinc-400">
        {judge.evaluated_at ? formatDateTime(judge.evaluated_at) : "Not evaluated"}
      </p>
      {criteriaResults.length ? (
        <div className="mt-3 space-y-2">
          {criteriaResults.map((criterion) => (
            <div key={String(criterion.criterion)} className="flex gap-3">
              <span
                className="mt-1 size-2 shrink-0 rounded-full bg-zinc-400 data-[passed=true]:bg-emerald-500"
                data-passed={criterion.passed === true}
              />
              <p className="text-zinc-700 dark:text-zinc-200">
                {String(criterion.criterion ?? "Criterion")} · {String(criterion.score ?? 0)}
              </p>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function JudgeResultMetric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-zinc-500 dark:text-zinc-400">{label}</p>
      <p className="mt-1 font-semibold text-zinc-950 dark:text-zinc-50">{value}</p>
    </div>
  );
}

function OperationLinkPanel({ selectedTask }: { selectedTask: TaskVM }) {
  return (
    <Panel title="Operation detail" description="Use the operation view when you need department-by-department detail.">
      <div className="space-y-3">
        <div className="rounded-[1.2rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
          <p className="text-sm font-semibold text-zinc-950 dark:text-zinc-50">Operation linkage</p>
          <p className="mt-2 text-sm leading-6 text-zinc-600 dark:text-zinc-300">
            This task is attached to operation{" "}
            <span className="font-medium text-zinc-900 dark:text-zinc-50">
              {selectedTask.operationId ?? "Unavailable"}
            </span>
            . Use the operation view to inspect department activity, tools, deliverables, and technical summaries.
          </p>
        </div>
        <Button asChild className="rounded-full">
          <Link href={`/runs/${selectedTask.operationId}`}>Inspect operation detail</Link>
        </Button>
      </div>
    </Panel>
  );
}

function TaskTimingPanel({ selectedTask }: { selectedTask: TaskVM }) {
  return (
    <Panel title="Operational timing" description="Time awareness stays attached to every projected task.">
      <KeyValueGrid
        columns={1}
        items={[
          { label: "Created", value: formatDateTime(selectedTask.createdAt) },
          { label: "Started", value: formatDateTime(selectedTask.startedAt) },
          { label: "Ended", value: formatDateTime(selectedTask.endedAt) },
        ]}
      />
    </Panel>
  );
}

function TasksLoadedContent({ controller }: { controller: TasksPageController }) {
  if (controller.loading) {
    return (
      <div className="flex min-h-[320px] items-center justify-center rounded-[1.75rem] border border-zinc-900/10 bg-white/70 dark:border-white/10 dark:bg-zinc-950/50">
        <Spinner size="lg" />
      </div>
    );
  }

  if (!controller.selectedTask) {
    return (
      <EmptyBlock
        title="No tasks available"
        description="Task projections will appear here when operations create operator-facing work."
      />
    );
  }

  return (
    <div className="grid gap-6 2xl:grid-cols-[0.78fr_1.22fr]">
      <TaskQueuePanel controller={controller} />
      <div className="space-y-6">
        <TaskDetailPanel selectedTask={controller.selectedTask} />
        <div className="grid gap-6 2xl:grid-cols-2">
          <TaskJudgePanel controller={controller} />
          <OperationLinkPanel selectedTask={controller.selectedTask} />
          <TaskTimingPanel selectedTask={controller.selectedTask} />
        </div>
      </div>
    </div>
  );
}

export default function TasksPage() {
  const controller = useTasksPageController();
  const inspector = useMemo(() => <TasksInspector selectedTask={controller.selectedTask} />, [controller.selectedTask]);

  return (
    <ProtectedRoute>
      <DashboardLayout inspector={inspector}>
        <div className="space-y-6">
          <SectionHeader
            eyebrow="Activity"
            title="Department activity at a glance"
            description="Each task summarizes what is happening now, where work is blocked, and which operation to inspect next."
          />

          {controller.error ? (
            <Alert variant="destructive">
              <AlertDescription>{controller.error}</AlertDescription>
            </Alert>
          ) : null}

          <TasksLoadedContent controller={controller} />
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
