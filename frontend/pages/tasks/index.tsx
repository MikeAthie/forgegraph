import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/router";

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

export default function TasksPage() {
  const router = useRouter();
  const [tasks, setTasks] = useState<TaskVM[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
          title: "Lifecycle",
          content: (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span>Canonical state</span>
                <StatusBadge status={selectedTask.status} />
              </div>
              <div className="flex items-center justify-between">
                <span>Attempt count</span>
                <span>{selectedTask.attemptCount ?? selectedTask.attempt ?? 1}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Lifecycle ID</span>
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
            <div className="grid gap-6 xl:grid-cols-[0.78fr_1.22fr]">
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
                    <div className="flex items-center gap-3">
                      <span>{task.title}</span>
                      <StatusBadge status={task.status} />
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
                    <div className="flex items-center gap-2">
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
                        label: "Stale / late events",
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
                      <p className="text-[11px] uppercase tracking-[0.18em]">Dead-lettered</p>
                      <p className="mt-2 text-sm leading-7">
                        {selectedTask.deadLetter.reason || "Task was moved to dead letter."}
                        {selectedTask.deadLetter.last_error ? ` Last error: ${selectedTask.deadLetter.last_error}` : ""}
                      </p>
                      {selectedTask.deadLetter.recovery_options?.length ? (
                        <p className="mt-2 text-xs">
                          Recovery: {selectedTask.deadLetter.recovery_options.join(", ")}
                        </p>
                      ) : null}
                    </div>
                  ) : null}
                  {(selectedTask.staleEventCount ?? 0) > 0 || (selectedTask.lateEventCount ?? 0) > 0 ? (
                    <div className="mt-4 rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                        Rejected lifecycle events
                      </p>
                      <p className="mt-2 text-sm leading-7 text-slate-700 dark:text-slate-200">
                        Stale: {selectedTask.staleEventCount ?? 0} · Late: {selectedTask.lateEventCount ?? 0}. The
                        backend preserved these events without mutating current task state.
                      </p>
                    </div>
                  ) : null}
                </Panel>

                <div className="grid gap-6 2xl:grid-cols-2">
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
