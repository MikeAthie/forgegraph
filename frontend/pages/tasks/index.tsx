import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/router";

import DashboardLayout from "@/components/DashboardLayout";
import { EmptyBlock, InspectorPanel, KeyValueGrid, Panel, SectionHeader, SelectionList, StatusBadge, formatDateTime } from "@/components/os/operations-ui";
import ProtectedRoute from "@/components/ProtectedRoute";
import { Alert, AlertDescription, Button, Spinner } from "@/components/ui";
import { getApiErrorMessage, tasksApi, type TaskRecord } from "@/lib/api";

export default function TasksPage() {
  const router = useRouter();
  const [tasks, setTasks] = useState<TaskRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const data = await tasksApi.list();
        if (!cancelled) {
          setTasks(data.sort((a, b) => (b.updated_at ?? "").localeCompare(a.updated_at ?? "")));
        }
      } catch (err: unknown) {
        if (!cancelled) {
          setError(getApiErrorMessage(err, "Failed to load tasks."));
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
    typeof router.query.task === "string" ? router.query.task : tasks.length > 0 ? tasks[0]?.id ?? null : null;

  const selectedTask = useMemo(
    () => tasks.find((task) => task.id === selectedTaskId) ?? tasks[0] ?? null,
    [selectedTaskId, tasks],
  );

  const groupedCounts = useMemo(
    () => ({
      running: tasks.filter((task) => task.status === "running").length,
      waiting: tasks.filter((task) => task.status === "waiting" || task.status === "pending").length,
      failed: tasks.filter((task) => task.status === "failed").length,
    }),
    [tasks],
  );

  const inspector = selectedTask ? (
    <InspectorPanel
      title={selectedTask.title}
      subtitle="Task records are the operator-facing projection over execution, step, and decision state."
      sections={[
        {
          title: "Routing",
          content: (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span>Execution</span>
                <span className="truncate pl-4">{selectedTask.execution_id.slice(0, 8)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Current step</span>
                <span className="truncate pl-4">{selectedTask.current_step_id?.slice(0, 8) ?? "Unavailable"}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Decision</span>
                <span className="truncate pl-4">{selectedTask.current_decision_id?.slice(0, 8) ?? "None"}</span>
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
                <span>{formatDateTime(selectedTask.started_at)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Last change</span>
                <span>{formatDateTime(selectedTask.updated_at)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Ended</span>
                <span>{formatDateTime(selectedTask.ended_at)}</span>
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
            eyebrow="Task control"
            title="Queue-first supervision"
            description="Tasks are the units of work an operator can reason about. Each one summarizes what is happening now, where the execution is paused, and which execution to inspect next."
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
            <EmptyBlock title="No tasks available" description="Task projections will appear here when executions create operator-facing work." />
          ) : (
            <div className="grid gap-6 xl:grid-cols-[0.78fr_1.22fr]">
              <Panel title="Task queue" description="Select a task to inspect its current state and trace linkage.">
                <div className="mb-4 grid gap-3 sm:grid-cols-3">
                  <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-3 dark:border-white/8">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Running</p>
                    <p className="mt-2 text-2xl font-semibold text-slate-950 dark:text-slate-50">{groupedCounts.running}</p>
                  </div>
                  <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-3 dark:border-white/8">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Waiting</p>
                    <p className="mt-2 text-2xl font-semibold text-slate-950 dark:text-slate-50">{groupedCounts.waiting}</p>
                  </div>
                  <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-3 dark:border-white/8">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Failed</p>
                    <p className="mt-2 text-2xl font-semibold text-slate-950 dark:text-slate-50">{groupedCounts.failed}</p>
                  </div>
                </div>
                <SelectionList
                  items={tasks}
                  selectedId={selectedTask.id}
                  onSelect={(task) => {
                    void router.replace(
                      { pathname: "/tasks", query: { task: task.id } },
                      undefined,
                      { shallow: true },
                    );
                  }}
                  renderTitle={(task) => (
                    <div className="flex items-center gap-3">
                      <span>{task.title}</span>
                      <StatusBadge status={task.status} />
                    </div>
                  )}
                  renderBody={(task) => task.summary}
                  renderMeta={(task) => <span className="text-xs uppercase tracking-[0.16em]">{task.priority}</span>}
                  empty={<EmptyBlock title="Queue is clear" description="There are no projected tasks in the current time window." />}
                />
              </Panel>

              <div className="space-y-6">
                <Panel
                  title={selectedTask.title}
                  description="Summary first, trace detail one click away."
                  action={
                    <div className="flex items-center gap-2">
                      <StatusBadge status={selectedTask.status} />
                      <Button asChild variant="outline" className="rounded-full">
                        <Link href={`/executions/${selectedTask.execution_id}`}>Open execution</Link>
                      </Button>
                    </div>
                  }
                >
                  <KeyValueGrid
                    columns={2}
                    items={[
                      { label: "Priority", value: selectedTask.priority },
                      { label: "Current step", value: selectedTask.current_step_id?.slice(0, 8) ?? "Unavailable" },
                      { label: "Decision gate", value: selectedTask.current_decision_id?.slice(0, 8) ?? "No active decision" },
                      { label: "Started", value: formatDateTime(selectedTask.started_at) },
                    ]}
                  />
                  <div className="mt-4 rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                    <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Summary</p>
                    <p className="mt-2 text-sm leading-7 text-slate-700 dark:text-slate-200">{selectedTask.summary}</p>
                  </div>
                </Panel>

                <div className="grid gap-6 2xl:grid-cols-2">
                  <Panel title="Execution trace" description="The task is a projection; the execution remains the canonical trace backbone.">
                    <div className="space-y-3">
                      <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                        <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">Execution linkage</p>
                        <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">
                          This task is attached to execution <span className="font-medium text-slate-900 dark:text-slate-50">{selectedTask.execution_id}</span>.
                          Use the execution view to inspect step-level input, output, tools, and reasoning summaries.
                        </p>
                      </div>
                      <Button asChild className="rounded-full">
                        <Link href={`/executions/${selectedTask.execution_id}`}>Inspect distributed trace</Link>
                      </Button>
                    </div>
                  </Panel>

                  <Panel title="Operational timing" description="Time awareness stays attached to every projected task.">
                    <KeyValueGrid
                      columns={1}
                      items={[
                        { label: "Created", value: formatDateTime(selectedTask.created_at) },
                        { label: "Last updated", value: formatDateTime(selectedTask.updated_at) },
                        { label: "Ended", value: formatDateTime(selectedTask.ended_at) },
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
