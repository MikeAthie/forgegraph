import { useCallback, useEffect, useMemo, useReducer } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import { Blocks, BrainCircuit, Lightbulb, MessageSquareWarning, Waypoints } from "lucide-react";

import DashboardLayout from "@/components/DashboardLayout";
import { EmptyBlock, Panel, SectionHeader, StatusBadge, formatDateTime } from "@/components/os/operations-ui";
import ProtectedRoute from "@/components/ProtectedRoute";
import { Alert, AlertDescription, Button, Spinner } from "@/components/ui";
import { translateProductError } from "@/domain/errors";
import { departmentRepository } from "@/domain/repositories";
import type { DepartmentActivityVM, DepartmentVM, OperationRefVM, TaskVM } from "@/domain/translation";

function departmentName(department: DepartmentVM): string {
  return department.name ?? department.label;
}

function activityLabel(department: DepartmentVM): string {
  const status = department.activityStatus ?? "idle";
  if (status === "active") {
    return "Active";
  }
  if (status === "waiting") {
    return "Waiting";
  }
  return "Idle";
}

function taskStatusLabel(task: TaskVM): string {
  if (task.status === "paused") {
    return "waiting";
  }
  return task.status;
}

function operationStage(operation: OperationRefVM): string {
  if (operation.status === "running") {
    return operation.currentStage;
  }
  if (operation.status === "completed") {
    return "Deliverable ready";
  }
  if (operation.status === "failed") {
    return "Needs attention";
  }
  return operation.currentStage;
}

function MiniStat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-[1.1rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-3 dark:border-white/8">
      <p className="text-[10px] uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">{label}</p>
      <p className="mt-1 text-lg font-semibold text-zinc-950 dark:text-zinc-50">{value}</p>
    </div>
  );
}

function RosterItem({
  activity,
  selected,
  onSelect,
}: {
  activity: DepartmentActivityVM;
  selected: boolean;
  onSelect: () => void;
}) {
  const { department } = activity;

  return (
    <button
      type="button"
      onClick={onSelect}
      className={`w-full rounded-[1.25rem] border p-4 text-left transition-colors ${
        selected
          ? "border-zinc-950 bg-zinc-950 text-white shadow-[0_24px_48px_-34px_rgba(15,23,42,0.85)] dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-950"
          : "border-zinc-900/8 bg-white hover:bg-[var(--panel-muted)] dark:border-white/8 dark:bg-white/5 dark:hover:bg-white/8"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-semibold">{departmentName(department)}</p>
            <StatusBadge status={department.activityStatus ?? "idle"} label={activityLabel(department)} />
          </div>
          <p className={`mt-2 text-xs font-medium ${selected ? "text-white/75 dark:text-zinc-700" : "text-zinc-500"}`}>
            {department.role ?? "Company thinking department"}
          </p>
          <p
            className={`mt-2 text-sm leading-6 ${selected ? "text-white/78 dark:text-zinc-700" : "text-zinc-600 dark:text-zinc-300"}`}
          >
            {department.currentFocus ?? activity.focus.objective}
          </p>
        </div>
      </div>
      <div className="mt-4 flex flex-wrap gap-2 text-xs">
        <span
          className={`rounded-full border px-2.5 py-1 ${
            selected
              ? "border-white/20 text-white/80 dark:border-zinc-950/15 dark:text-zinc-700"
              : "border-zinc-900/10 text-zinc-500 dark:border-white/10"
          }`}
        >
          {department.activeTaskCount ?? activity.tasks.length} active tasks
        </span>
        <span
          className={`rounded-full border px-2.5 py-1 ${
            selected
              ? "border-white/20 text-white/80 dark:border-zinc-950/15 dark:text-zinc-700"
              : "border-zinc-900/10 text-zinc-500 dark:border-white/10"
          }`}
        >
          {department.pendingDecisionCount ?? activity.approvals.length} pending approvals
        </span>
      </div>
    </button>
  );
}

function OperationLink({ operation }: { operation: OperationRefVM }) {
  return (
    <Button asChild size="sm" variant="outline" className="rounded-full">
      <Link href={`/runs/${operation.id}`}>Open operation</Link>
    </Button>
  );
}

type DepartmentsState = {
  activities: DepartmentActivityVM[];
  loading: boolean;
  error: string | null;
};

type DepartmentsAction =
  | { type: "load-start" }
  | { type: "load-success"; activities: DepartmentActivityVM[] }
  | { type: "load-error"; error: string };

const initialDepartmentsState: DepartmentsState = {
  activities: [],
  loading: true,
  error: null,
};

function departmentsReducer(state: DepartmentsState, action: DepartmentsAction): DepartmentsState {
  switch (action.type) {
    case "load-start":
      return { ...state, loading: true, error: null };
    case "load-success":
      return { activities: action.activities, loading: false, error: null };
    case "load-error":
      return { ...state, loading: false, error: action.error };
    default:
      return state;
  }
}

export default function DepartmentsPage() {
  const router = useRouter();
  const { replace } = router;
  const [{ activities, loading, error }, dispatchDepartments] = useReducer(departmentsReducer, initialDepartmentsState);

  const loadDepartments = useCallback(async () => {
    dispatchDepartments({ type: "load-start" });
    try {
      const data = await departmentRepository.listActivity();
      dispatchDepartments({ type: "load-success", activities: data });
    } catch (err: unknown) {
      dispatchDepartments({ type: "load-error", error: translateProductError(err, "department") });
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const data = await departmentRepository.listActivity();
        if (!cancelled) {
          dispatchDepartments({ type: "load-success", activities: data });
        }
      } catch (err: unknown) {
        if (!cancelled) {
          dispatchDepartments({ type: "load-error", error: translateProductError(err, "department") });
        }
      }
    };

    void load();

    return () => {
      cancelled = true;
    };
  }, []);

  const selectedDepartmentId =
    typeof router.query.department === "string" ? router.query.department : (activities[0]?.department.id ?? null);

  const selectedActivity = useMemo(
    () => activities.find((activity) => activity.department.id === selectedDepartmentId) ?? activities[0] ?? null,
    [activities, selectedDepartmentId],
  );

  const totalActiveDepartments = activities.filter(
    (activity) => activity.department.activityStatus === "active",
  ).length;
  const totalWaitingDepartments = activities.filter(
    (activity) => activity.department.activityStatus === "waiting",
  ).length;

  return (
    <ProtectedRoute>
      <DashboardLayout>
        <div className="space-y-6">
          <SectionHeader
            eyebrow="Departments"
            title="How the company thinks"
            description="Departments are the thinking layer of the company: they hold intent, form proposals, participate in operations, and surface approvals when judgment is needed."
            action={
              <Button variant="outline" className="rounded-full" onClick={() => void loadDepartments()}>
                Refresh
              </Button>
            }
          />

          {error ? (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}

          {loading ? (
            <div className="flex min-h-[360px] items-center justify-center rounded-[1.75rem] border border-zinc-900/10 bg-white/70 dark:border-white/10 dark:bg-zinc-950/50">
              <Spinner size="lg" />
            </div>
          ) : activities.length === 0 ? (
            <EmptyBlock
              title="No departments available"
              description="Departments appear after a company has started work."
            />
          ) : (
            <div className="grid gap-6 xl:grid-cols-[0.46fr_1fr]">
              <Panel
                title="Departments"
                description="Select a department to inspect its intent, proposals, blockers, and participation."
              >
                <div className="mb-4 grid grid-cols-2 gap-3">
                  <MiniStat label="Thinking" value={totalActiveDepartments} />
                  <MiniStat label="Waiting" value={totalWaitingDepartments} />
                </div>
                <div className="space-y-3">
                  {activities.map((activity) => (
                    <RosterItem
                      key={activity.department.id}
                      activity={activity}
                      selected={activity.department.id === selectedActivity?.department.id}
                      onSelect={() => {
                        void replace(
                          { pathname: "/departments", query: { department: activity.department.id } },
                          undefined,
                          { shallow: true },
                        );
                      }}
                    />
                  ))}
                </div>
              </Panel>

              {selectedActivity ? <DepartmentDetail activity={selectedActivity} /> : null}
            </div>
          )}
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}

function DepartmentDetail({ activity }: { activity: DepartmentActivityVM }) {
  const { department, focus, proposals, tasks, operations, blockers } = activity;
  const activeTasks = tasks.filter((task) => task.status === "running" || task.status === "paused");
  const visibleTasks = tasks.slice(0, 5);

  return (
    <div className="space-y-6">
      <Panel
        title={departmentName(department)}
        description={department.purpose ?? department.responsibility}
        action={<StatusBadge status={department.activityStatus ?? "idle"} label={activityLabel(department)} />}
      >
        <div className="grid gap-3 md:grid-cols-4">
          <MiniStat label="Active tasks" value={activeTasks.length} />
          <MiniStat label="Proposals" value={proposals.length} />
          <MiniStat label="Blockers" value={blockers.length} />
          <MiniStat label="Operations" value={operations.length} />
        </div>
      </Panel>

      <Panel title="Current focus" description="What this department is trying to understand or decide right now.">
        <div className="rounded-[1.25rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-5 dark:border-white/8">
          <div className="flex items-start gap-3">
            <div className="mt-1 flex size-10 shrink-0 items-center justify-center rounded-2xl border border-cyan-800/15 bg-cyan-50 text-cyan-800 dark:border-cyan-200/20 dark:bg-cyan-500/10 dark:text-cyan-100">
              <BrainCircuit className="size-5" />
            </div>
            <div>
              <p className="text-base font-semibold leading-7 text-zinc-950 dark:text-zinc-50">{focus.objective}</p>
              <p className="mt-2 text-sm leading-7 text-zinc-600 dark:text-zinc-300">{focus.reasoning}</p>
            </div>
          </div>
        </div>
      </Panel>

      <Panel
        title="Active proposals"
        description="Recommendations this department has formed before work becomes assigned task work."
      >
        {proposals.length ? (
          <div className="space-y-3">
            {proposals.map((proposal) => (
              <div
                key={proposal.id}
                className="rounded-[1.25rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8"
              >
                <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <Lightbulb className="size-4 text-amber-500" />
                      <StatusBadge
                        status={proposal.status === "awaiting approval" ? "waiting" : proposal.status}
                        label={proposal.status}
                      />
                    </div>
                    <p className="mt-3 text-sm leading-7 text-zinc-700 dark:text-zinc-200">{proposal.description}</p>
                    <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
                      Proposed {formatDateTime(proposal.createdAt)}
                    </p>
                  </div>
                  {proposal.operation ? <OperationLink operation={proposal.operation} /> : null}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyBlock
            title="No active proposals"
            description="When this department recommends an action or reaches an approval point, the proposal appears here first."
          />
        )}
      </Panel>

      <Panel
        title="Tasks from operations"
        description="Task work is secondary here: these tasks are consequences of proposals or active operations."
      >
        {visibleTasks.length ? (
          <div className="space-y-3">
            {visibleTasks.map((task) => (
              <div
                key={task.id}
                className="rounded-[1.25rem] border border-zinc-900/8 bg-white/70 p-4 dark:border-white/8 dark:bg-white/3"
              >
                <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <Waypoints className="size-4 text-zinc-500" />
                      <p className="text-sm font-semibold text-zinc-950 dark:text-zinc-50">{task.title}</p>
                      <StatusBadge status={task.status} label={taskStatusLabel(task)} />
                    </div>
                    <p className="mt-2 text-sm leading-7 text-zinc-600 dark:text-zinc-300">{task.summary}</p>
                  </div>
                  {task.operationId ? (
                    <Button asChild size="sm" variant="outline" className="rounded-full">
                      <Link href={`/runs/${task.operationId}`}>Open operation</Link>
                    </Button>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyBlock
            title="No tasks assigned"
            description="This department is not currently doing assigned work; it can still participate by forming proposals."
          />
        )}
      </Panel>

      <Panel title="Operation participation" description="Where this department is participating across company work.">
        {operations.length ? (
          <div className="space-y-3">
            {operations.map((operation) => (
              <div
                key={operation.id}
                className="rounded-[1.25rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8"
              >
                <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <Blocks className="size-4 text-cyan-600" />
                      <p className="text-sm font-semibold text-zinc-950 dark:text-zinc-50">{operation.name}</p>
                      <StatusBadge status={operation.status} />
                    </div>
                    <p className="mt-2 text-sm leading-7 text-zinc-600 dark:text-zinc-300">{operation.role}</p>
                    <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                      Current stage: {operationStage(operation)}
                    </p>
                  </div>
                  <OperationLink operation={operation} />
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyBlock
            title="No operation participation"
            description="This department is not attached to active company work in the current view."
          />
        )}
      </Panel>

      <Panel
        title="Blockers and approvals"
        description="Decisions or failed work that prevent the department from moving forward."
      >
        {blockers.length ? (
          <div className="space-y-3">
            {blockers.map((blocker) => (
              <div
                key={blocker.id}
                className="rounded-[1.25rem] border border-amber-800/15 bg-amber-50/70 p-4 dark:border-amber-200/20 dark:bg-amber-500/10"
              >
                <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <MessageSquareWarning className="size-4 text-amber-600" />
                      <StatusBadge status={blocker.status} />
                    </div>
                    <p className="mt-3 text-sm leading-7 text-zinc-700 dark:text-zinc-200">{blocker.description}</p>
                  </div>
                  {blocker.operation ? <OperationLink operation={blocker.operation} /> : null}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyBlock
            title="No blockers"
            description="This department has no active approvals or blocked tasks in the current view."
          />
        )}
      </Panel>
    </div>
  );
}
