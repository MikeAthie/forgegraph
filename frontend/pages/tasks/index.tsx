import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import { Play, Save, Scale, Trash2 } from "lucide-react";

import DashboardLayout from "@/components/DashboardLayout";
import {
  EmptyBlock,
  InspectorPanel,
  KeyValueGrid,
  Panel,
  SectionHeader,
  SelectionList,
  StatusBadge,
  formatDateTime,
} from "@/components/os/operations-ui";
import ProtectedRoute from "@/components/ProtectedRoute";
import { Alert, AlertDescription, Button, Spinner } from "@/components/ui";
import { operationRepository } from "@/domain/repositories";
import { translateProductError } from "@/domain/errors";
import type { TaskVM } from "@/domain/translation";
import { tasksApi, type TaskJudge } from "@/lib/api";

function splitCriteria(value: string): string[] {
  return value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
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

export default function TasksPage() {
  const router = useRouter();
  const [tasks, setTasks] = useState<TaskVM[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [judge, setJudge] = useState<TaskJudge | null>(null);
  const [judgeLoading, setJudgeLoading] = useState(false);
  const [judgeSaving, setJudgeSaving] = useState(false);
  const [judgeError, setJudgeError] = useState<string | null>(null);
  const [judgeTitle, setJudgeTitle] = useState("");
  const [judgeInstructions, setJudgeInstructions] = useState("");
  const [judgeCriteria, setJudgeCriteria] = useState("");
  const [judgeThreshold, setJudgeThreshold] = useState(80);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const data = await operationRepository.listTasks();
        if (!cancelled) {
          setTasks(data);
        }
      } catch (err: unknown) {
        if (!cancelled) {
          setError(translateProductError(err, "department"));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void load();

    return () => {
      cancelled = true;
    };
  }, []);

  const selectedTaskId =
    typeof router.query.task === "string" ? router.query.task : tasks.length > 0 ? (tasks[0]?.id ?? null) : null;

  const selectedTask = useMemo(
    () => tasks.find((task) => task.id === selectedTaskId) ?? tasks[0] ?? null,
    [selectedTaskId, tasks],
  );

  useEffect(() => {
    let cancelled = false;

    const loadJudge = async () => {
      if (!selectedTask?.id) {
        setJudge(null);
        return;
      }
      setJudgeLoading(true);
      setJudgeError(null);
      try {
        const data = await tasksApi.getJudge(selectedTask.id);
        if (cancelled) return;
        setJudge(data);
        setJudgeTitle(data?.title || `Judge: ${selectedTask.title}`);
        setJudgeInstructions(data?.instructions || "");
        setJudgeCriteria(data?.criteria?.join("\n") || "");
        setJudgeThreshold(data?.pass_threshold ?? 80);
      } catch (err: unknown) {
        if (!cancelled) {
          setJudgeError(translateProductError(err, "department"));
        }
      } finally {
        if (!cancelled) {
          setJudgeLoading(false);
        }
      }
    };

    void loadJudge();

    return () => {
      cancelled = true;
    };
  }, [selectedTask?.id, selectedTask?.title]);

  const updateTaskJudgeSummary = useCallback((taskId: string, updatedJudge: TaskJudge | null) => {
    setTasks((current) =>
      current.map((task) =>
        task.id === taskId
          ? {
              ...task,
              judge: updatedJudge ? judgeSummaryFrom(updatedJudge) : null,
            }
          : task,
      ),
    );
  }, []);

  const handleSaveJudge = useCallback(async () => {
    if (!selectedTask) return;
    setJudgeSaving(true);
    setJudgeError(null);
    try {
      const savedJudge = await tasksApi.saveJudge(selectedTask.id, {
        title: judgeTitle,
        instructions: judgeInstructions,
        criteria: splitCriteria(judgeCriteria),
        pass_threshold: judgeThreshold,
      });
      setJudge(savedJudge);
      updateTaskJudgeSummary(selectedTask.id, savedJudge);
    } catch (err: unknown) {
      setJudgeError(translateProductError(err, "department"));
    } finally {
      setJudgeSaving(false);
    }
  }, [judgeCriteria, judgeInstructions, judgeThreshold, judgeTitle, selectedTask, updateTaskJudgeSummary]);

  const handleEvaluateJudge = useCallback(async () => {
    if (!selectedTask) return;
    setJudgeSaving(true);
    setJudgeError(null);
    try {
      const evaluatedJudge = await tasksApi.evaluateJudge(selectedTask.id);
      setJudge(evaluatedJudge);
      updateTaskJudgeSummary(selectedTask.id, evaluatedJudge);
    } catch (err: unknown) {
      setJudgeError(translateProductError(err, "department"));
    } finally {
      setJudgeSaving(false);
    }
  }, [selectedTask, updateTaskJudgeSummary]);

  const handleDeleteJudge = useCallback(async () => {
    if (!selectedTask) return;
    setJudgeSaving(true);
    setJudgeError(null);
    try {
      await tasksApi.deleteJudge(selectedTask.id);
      setJudge(null);
      setJudgeTitle(`Judge: ${selectedTask.title}`);
      setJudgeInstructions("");
      setJudgeCriteria("");
      setJudgeThreshold(80);
      updateTaskJudgeSummary(selectedTask.id, null);
    } catch (err: unknown) {
      setJudgeError(translateProductError(err, "department"));
    } finally {
      setJudgeSaving(false);
    }
  }, [selectedTask, updateTaskJudgeSummary]);

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

  const inspector = selectedTask ? (
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
  ) : null;

  return (
    <ProtectedRoute>
      <DashboardLayout inspector={inspector}>
        <div className="space-y-6">
          <SectionHeader
            eyebrow="Activity"
            title="Department activity at a glance"
            description="Each task summarizes what is happening now, where work is blocked, and which operation to inspect next."
          />

          {error ? (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}

          {loading ? (
            <div className="flex min-h-[320px] items-center justify-center rounded-[1.75rem] border border-slate-900/10 bg-white/70 dark:border-white/10 dark:bg-slate-950/50">
              <Spinner size="lg" />
            </div>
          ) : !selectedTask ? (
            <EmptyBlock
              title="No tasks available"
              description="Task projections will appear here when operations create operator-facing work."
            />
          ) : (
            <div className="grid gap-6 2xl:grid-cols-[0.78fr_1.22fr]">
              <Panel title="Activity queue" description="Select a task to inspect its current state and next action.">
                <div className="mb-4 grid gap-3 sm:grid-cols-3">
                  <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-3 dark:border-white/8">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                      Running
                    </p>
                    <p className="mt-2 text-2xl font-semibold text-slate-950 dark:text-slate-50">
                      {groupedCounts.running}
                    </p>
                  </div>
                  <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-3 dark:border-white/8">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                      Waiting
                    </p>
                    <p className="mt-2 text-2xl font-semibold text-slate-950 dark:text-slate-50">
                      {groupedCounts.waiting}
                    </p>
                  </div>
                  <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-3 dark:border-white/8">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Failed</p>
                    <p className="mt-2 text-2xl font-semibold text-slate-950 dark:text-slate-50">
                      {groupedCounts.failed}
                    </p>
                  </div>
                </div>
                <SelectionList
                  items={tasks}
                  selectedId={selectedTask.id}
                  onSelect={(task) => {
                    void router.replace({ pathname: "/tasks", query: { task: task.id } }, undefined, { shallow: true });
                  }}
                  renderTitle={(task) => (
                    <div className="flex min-w-0 flex-wrap items-center gap-2">
                      <span className="min-w-0 truncate">{task.title}</span>
                      <StatusBadge status={task.status} />
                      {task.judge ? (
                        <span className="inline-flex items-center gap-1 rounded-full border border-slate-900/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500 dark:border-white/10 dark:text-slate-300">
                          <Scale className="h-3 w-3" aria-hidden="true" />
                          {judgeStatusLabel(task.judge)}
                        </span>
                      ) : null}
                    </div>
                  )}
                  renderBody={(task) => (
                    <div className="space-y-1">
                      <p>{task.summary}</p>
                      {task.deadLetter?.recovery_options?.length ? (
                        <p className="text-xs">Recovery: {task.deadLetter.recovery_options.join(", ")}</p>
                      ) : null}
                    </div>
                  )}
                  renderMeta={(task) => <span className="text-xs uppercase tracking-[0.16em]">{task.priority}</span>}
                  empty={
                    <EmptyBlock
                      title="Queue is clear"
                      description="There are no projected tasks in the current time window."
                    />
                  }
                />
              </Panel>

              <div className="space-y-6">
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
                  <div className="mt-4 rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                      Summary
                    </p>
                    <p className="mt-2 text-sm leading-7 text-slate-700 dark:text-slate-200">{selectedTask.summary}</p>
                  </div>
                  {selectedTask.latestRetry ? (
                    <div className="mt-4 rounded-[1.2rem] border border-amber-900/15 bg-amber-50 px-4 py-4 text-amber-950 dark:border-amber-200/15 dark:bg-amber-500/10 dark:text-amber-100">
                      <p className="text-[11px] uppercase tracking-[0.18em]">Retry schedule</p>
                      <p className="mt-2 text-sm leading-7">
                        {selectedTask.latestRetry.retry_reason || "Retry is scheduled"} · attempt{" "}
                        {selectedTask.latestRetry.attempt_number ?? "?"} of{" "}
                        {selectedTask.latestRetry.max_attempts ?? "?"}
                        {selectedTask.latestRetry.next_scheduled_at
                          ? ` · next ${formatDateTime(selectedTask.latestRetry.next_scheduled_at)}`
                          : ""}
                      </p>
                    </div>
                  ) : null}
                  {selectedTask.deadLetter ? (
                    <div className="mt-4 rounded-[1.2rem] border border-rose-900/15 bg-rose-50 px-4 py-4 text-rose-950 dark:border-rose-200/15 dark:bg-rose-500/10 dark:text-rose-100">
                      <p className="text-[11px] uppercase tracking-[0.18em]">Needs recovery</p>
                      <p className="mt-2 text-sm leading-7">
                        {selectedTask.deadLetter.reason || "Task needs operator recovery."}
                        {selectedTask.deadLetter.last_error ? ` Last error: ${selectedTask.deadLetter.last_error}` : ""}
                      </p>
                      {selectedTask.deadLetter.recovery_options?.length ? (
                        <p className="mt-2 text-xs">Recovery: {selectedTask.deadLetter.recovery_options.join(", ")}</p>
                      ) : null}
                    </div>
                  ) : null}
                  {(selectedTask.staleEventCount ?? 0) > 0 || (selectedTask.lateEventCount ?? 0) > 0 ? (
                    <div className="mt-4 rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                        Ignored stale updates
                      </p>
                      <p className="mt-2 text-sm leading-7 text-slate-700 dark:text-slate-200">
                        Stale: {selectedTask.staleEventCount ?? 0} · Late: {selectedTask.lateEventCount ?? 0}. The saved
                        task state was not changed.
                      </p>
                    </div>
                  ) : null}
                </Panel>

                <div className="grid gap-6 2xl:grid-cols-2">
                  <Panel
                    title="Task judge"
                    description="Acceptance criteria and backend evaluation for this task."
                    action={
                      judge ? (
                        <StatusBadge
                          status={
                            judge.status === "passed"
                              ? "completed"
                              : judge.status === "failed"
                                ? "failed"
                                : judge.status === "inconclusive"
                                  ? "paused"
                                  : "queued"
                          }
                        />
                      ) : null
                    }
                  >
                    {judgeError ? (
                      <Alert variant="destructive" className="mb-4">
                        <AlertDescription>{judgeError}</AlertDescription>
                      </Alert>
                    ) : null}
                    {judgeLoading ? (
                      <div className="flex min-h-[180px] items-center justify-center">
                        <Spinner />
                      </div>
                    ) : (
                      <div className="space-y-4">
                        <div className="grid gap-3 sm:grid-cols-[1fr_120px]">
                          <label className="space-y-1 text-sm">
                            <span className="font-medium text-slate-700 dark:text-slate-200">Name</span>
                            <input
                              value={judgeTitle}
                              onChange={(event) => setJudgeTitle(event.target.value)}
                              className="w-full rounded-lg border border-slate-900/10 bg-white px-3 py-2 text-sm text-slate-950 outline-none focus:border-slate-900/30 dark:border-white/10 dark:bg-slate-950 dark:text-slate-50 dark:focus:border-white/30"
                            />
                          </label>
                          <label className="space-y-1 text-sm">
                            <span className="font-medium text-slate-700 dark:text-slate-200">Pass</span>
                            <input
                              type="number"
                              min={1}
                              max={100}
                              value={judgeThreshold}
                              onChange={(event) => setJudgeThreshold(Number(event.target.value))}
                              className="w-full rounded-lg border border-slate-900/10 bg-white px-3 py-2 text-sm text-slate-950 outline-none focus:border-slate-900/30 dark:border-white/10 dark:bg-slate-950 dark:text-slate-50 dark:focus:border-white/30"
                            />
                          </label>
                        </div>
                        <label className="space-y-1 text-sm">
                          <span className="font-medium text-slate-700 dark:text-slate-200">Criteria</span>
                          <textarea
                            value={judgeCriteria}
                            onChange={(event) => setJudgeCriteria(event.target.value)}
                            rows={5}
                            className="w-full rounded-lg border border-slate-900/10 bg-white px-3 py-2 text-sm leading-6 text-slate-950 outline-none focus:border-slate-900/30 dark:border-white/10 dark:bg-slate-950 dark:text-slate-50 dark:focus:border-white/30"
                            placeholder="One criterion per line"
                          />
                        </label>
                        <label className="space-y-1 text-sm">
                          <span className="font-medium text-slate-700 dark:text-slate-200">Rubric note</span>
                          <textarea
                            value={judgeInstructions}
                            onChange={(event) => setJudgeInstructions(event.target.value)}
                            rows={3}
                            className="w-full rounded-lg border border-slate-900/10 bg-white px-3 py-2 text-sm leading-6 text-slate-950 outline-none focus:border-slate-900/30 dark:border-white/10 dark:bg-slate-950 dark:text-slate-50 dark:focus:border-white/30"
                          />
                        </label>
                        <div className="flex flex-wrap items-center gap-2">
                          <Button onClick={handleSaveJudge} disabled={judgeSaving} className="rounded-full">
                            <Save className="mr-2 h-4 w-4" aria-hidden="true" />
                            Save judge
                          </Button>
                          <Button
                            variant="outline"
                            onClick={handleEvaluateJudge}
                            disabled={!judge || judgeSaving}
                            className="rounded-full"
                          >
                            <Play className="mr-2 h-4 w-4" aria-hidden="true" />
                            Evaluate task
                          </Button>
                          {judge ? (
                            <Button
                              variant="ghost"
                              onClick={handleDeleteJudge}
                              disabled={judgeSaving}
                              className="rounded-full"
                            >
                              <Trash2 className="mr-2 h-4 w-4" aria-hidden="true" />
                              Remove
                            </Button>
                          ) : null}
                        </div>
                        {judge ? (
                          <div className="rounded-lg border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 text-sm dark:border-white/8">
                            <div className="grid gap-3 sm:grid-cols-3">
                              <div>
                                <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
                                  Status
                                </p>
                                <p className="mt-1 font-semibold text-slate-950 dark:text-slate-50">
                                  {judgeStatusLabel(judge)}
                                </p>
                              </div>
                              <div>
                                <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
                                  Grade
                                </p>
                                <p className="mt-1 font-semibold text-slate-950 dark:text-slate-50">
                                  {judgeGradeLabel(judge)}
                                </p>
                              </div>
                              <div>
                                <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
                                  Pass mark
                                </p>
                                <p className="mt-1 font-semibold text-slate-950 dark:text-slate-50">
                                  {judge.pass_threshold}/100
                                </p>
                              </div>
                            </div>
                            <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
                              {judge.evaluated_at ? formatDateTime(judge.evaluated_at) : "Not evaluated"}
                            </p>
                            {getJudgeCriteriaResults(judge).length ? (
                              <div className="mt-3 space-y-2">
                                {getJudgeCriteriaResults(judge).map((criterion, index) => (
                                  <div key={`${String(criterion.criterion)}-${index}`} className="flex gap-3">
                                    <span
                                      className="mt-1 h-2 w-2 shrink-0 rounded-full bg-slate-400 data-[passed=true]:bg-emerald-500"
                                      data-passed={criterion.passed === true}
                                    />
                                    <p className="text-slate-700 dark:text-slate-200">
                                      {String(criterion.criterion ?? "Criterion")} · {String(criterion.score ?? 0)}
                                    </p>
                                  </div>
                                ))}
                              </div>
                            ) : null}
                          </div>
                        ) : null}
                      </div>
                    )}
                  </Panel>

                  <Panel
                    title="Operation detail"
                    description="Use the operation view when you need department-by-department detail."
                  >
                    <div className="space-y-3">
                      <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                        <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">Operation linkage</p>
                        <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">
                          This task is attached to operation{" "}
                          <span className="font-medium text-slate-900 dark:text-slate-50">
                            {selectedTask.operationId ?? "Unavailable"}
                          </span>
                          . Use the operation view to inspect department activity, tools, deliverables, and technical
                          summaries.
                        </p>
                      </div>
                      <Button asChild className="rounded-full">
                        <Link href={`/runs/${selectedTask.operationId}`}>Inspect operation detail</Link>
                      </Button>
                    </div>
                  </Panel>

                  <Panel
                    title="Operational timing"
                    description="Time awareness stays attached to every projected task."
                  >
                    <KeyValueGrid
                      columns={1}
                      items={[
                        { label: "Created", value: formatDateTime(selectedTask.createdAt) },
                        { label: "Started", value: formatDateTime(selectedTask.startedAt) },
                        { label: "Ended", value: formatDateTime(selectedTask.endedAt) },
                      ]}
                    />
                  </Panel>
                </div>
              </div>
            </div>
          )}
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
