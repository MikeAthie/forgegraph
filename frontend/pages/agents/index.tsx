import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import { BrainCircuit, Play, Square, Wallet, Waypoints } from "lucide-react";

import DashboardLayout from "@/components/DashboardLayout";
import {
  EmptyBlock,
  InspectorPanel,
  KeyValueGrid,
  MetricCard,
  Panel,
  SectionHeader,
  SelectionList,
  StatusBadge,
  formatCurrency,
  formatDateTime,
} from "@/components/os/operations-ui";
import ProtectedRoute from "@/components/ProtectedRoute";
import { Alert, AlertDescription, Button, Spinner } from "@/components/ui";
import {
  agentsApi,
  decisionsApi,
  getApiErrorMessage,
  memoryApi,
  runsApi,
  tasksApi,
  type AgentRegistryEntry,
  type DecisionRecord,
  type MemoryObservation,
  type TaskRecord,
} from "@/lib/api";
import { showError, showSuccess } from "@/lib/toast";

const summarizePurpose = (agent: AgentRegistryEntry) => {
  const capabilities = Object.keys(agent.capabilities_json ?? {});
  if (capabilities.length > 0) {
    return `Configured around ${capabilities.slice(0, 3).join(", ")} with ${agent.default_model || "an unspecified model"}.`;
  }
  return `${agent.display_name} supervises workflow work with ${agent.default_model || "a model that has not been declared yet"}.`;
};

const deriveWhyDoingThis = (
  agent: AgentRegistryEntry,
  currentTask: TaskRecord | null,
  agentDecisions: DecisionRecord[],
  memory: MemoryObservation[],
) => {
  const memoryHeadline = memory[0]?.title || memory[0]?.topic_key || null;
  const pendingDecision = agentDecisions.find((decision) => decision.status === "pending") ?? null;
  const policyKeys = Object.keys(agent.policy_snapshot_json ?? {});

  return {
    objective:
      currentTask?.summary ??
      "No current task is projected. The agent is waiting for new work from its source workflow.",
    trigger: pendingDecision?.decision_type
      ? `The current behavior is constrained by ${pendingDecision.decision_type}.`
      : currentTask
        ? `The agent is acting because ${currentTask.title.toLowerCase()} is the current assigned unit of work.`
        : "No active execution trigger is currently visible.",
    constraints:
      policyKeys.length > 0
        ? `Policy is shaping behavior through ${policyKeys.slice(0, 3).join(", ")}.`
        : "No explicit policy snapshot has been projected for this agent yet.",
    memory: memoryHeadline
      ? `Recent memory indicates ${memoryHeadline}.`
      : "No recent memory item is currently influencing the visible behavior.",
  };
};

export default function AgentsPage() {
  const router = useRouter();
  const [agents, setAgents] = useState<AgentRegistryEntry[]>([]);
  const [tasks, setTasks] = useState<TaskRecord[]>([]);
  const [decisions, setDecisions] = useState<DecisionRecord[]>([]);
  const [memory, setMemory] = useState<MemoryObservation[]>([]);
  const [loading, setLoading] = useState(true);
  const [memoryLoading, setMemoryLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadSupervisionData = useCallback(async () => {
    const [agentData, taskData, decisionData] = await Promise.all([
      agentsApi.list(),
      tasksApi.list(),
      decisionsApi.list(),
    ]);
    setAgents(agentData);
    setTasks(taskData);
    setDecisions(decisionData);
  }, []);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        await loadSupervisionData();
      } catch (err: unknown) {
        if (!cancelled) {
          setError(getApiErrorMessage(err, "Failed to load agent supervision data."));
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
  }, [loadSupervisionData]);

  const selectedAgentId =
    typeof router.query.agent === "string" ? router.query.agent : agents.length > 0 ? (agents[0]?.id ?? null) : null;

  const selectedAgent = useMemo(
    () => agents.find((agent) => agent.id === selectedAgentId) ?? agents[0] ?? null,
    [agents, selectedAgentId],
  );

  useEffect(() => {
    if (!selectedAgent?.id) {
      setMemory([]);
      return;
    }

    let cancelled = false;
    setMemoryLoading(true);

    const loadMemory = async () => {
      try {
        const data = await memoryApi.timeline({ agent_id: selectedAgent.id, limit: 6 });
        if (!cancelled) {
          setMemory(data);
        }
      } catch {
        if (!cancelled) {
          setMemory([]);
        }
      } finally {
        if (!cancelled) {
          setMemoryLoading(false);
        }
      }
    };

    void loadMemory();

    return () => {
      cancelled = true;
    };
  }, [selectedAgent?.id]);

  const agentTasks = useMemo(
    () =>
      tasks
        .filter((task) => task.agent_id === selectedAgent?.id)
        .sort((a, b) => (b.updated_at ?? "").localeCompare(a.updated_at ?? "")),
    [selectedAgent?.id, tasks],
  );
  const agentDecisions = useMemo(
    () =>
      decisions
        .filter((decision) => decision.agent_id === selectedAgent?.id)
        .sort((a, b) => (b.requested_at ?? b.created_at).localeCompare(a.requested_at ?? a.created_at))
        .slice(0, 6),
    [decisions, selectedAgent?.id],
  );
  const currentTask =
    agentTasks.find((task) => task.status === "running" || task.status === "waiting") ?? agentTasks[0] ?? null;
  const currentExecutionId = currentTask?.execution_id ?? selectedAgent?.last_execution_id ?? null;

  const completedTaskCount = agentTasks.filter((task) => task.status === "succeeded").length;
  const waitingTaskCount = agentTasks.filter((task) => task.status === "waiting").length;
  const failedTaskCount = agentTasks.filter((task) => task.status === "failed").length;
  const why = selectedAgent ? deriveWhyDoingThis(selectedAgent, currentTask, agentDecisions, memory) : null;

  const handleStopExecution = useCallback(async () => {
    if (!currentExecutionId) {
      return;
    }

    setActionLoading(true);
    try {
      await runsApi.cancel(currentExecutionId);
      await loadSupervisionData();
      showSuccess("Execution stopped", "The active execution was canceled from the supervision view.");
    } catch (err: unknown) {
      showError("Stop failed", getApiErrorMessage(err, "Failed to stop the active execution."));
    } finally {
      setActionLoading(false);
    }
  }, [currentExecutionId, loadSupervisionData]);

  const handleReplayExecution = useCallback(async () => {
    if (!currentExecutionId) {
      return;
    }

    setActionLoading(true);
    try {
      const replayed = await runsApi.replay(currentExecutionId);
      await loadSupervisionData();
      showSuccess("Replay started", "A replay was created from the latest execution state.");
      await router.push(`/executions/${replayed.id}`);
    } catch (err: unknown) {
      showError("Replay failed", getApiErrorMessage(err, "Failed to replay the selected execution."));
    } finally {
      setActionLoading(false);
    }
  }, [currentExecutionId, loadSupervisionData, router]);

  const inspector = selectedAgent ? (
    <InspectorPanel
      title={selectedAgent.display_name}
      subtitle="The inspector keeps durable metadata, policy scope, and registry lineage visible while the center panel focuses on what the agent is doing and why."
      sections={[
        {
          title: "Registry lineage",
          content: (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span>Workflow</span>
                <span className="truncate pl-4">{selectedAgent.source_workflow_id.slice(0, 8)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Revision</span>
                <span className="truncate pl-4">
                  {selectedAgent.source_workflow_revision_id?.slice(0, 8) ?? "Draft"}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span>Node</span>
                <span className="truncate pl-4">{selectedAgent.source_node_id}</span>
              </div>
            </div>
          ),
        },
        {
          title: "Policy snapshot",
          content: Object.keys(selectedAgent.policy_snapshot_json ?? {}).length ? (
            <div className="space-y-2">
              {Object.entries(selectedAgent.policy_snapshot_json)
                .slice(0, 5)
                .map(([key, value]) => (
                  <div key={key} className="flex items-start justify-between gap-3">
                    <span className="text-slate-500 dark:text-slate-400">{key}</span>
                    <span className="max-w-[10rem] text-right">{String(value)}</span>
                  </div>
                ))}
            </div>
          ) : (
            "No policy snapshot has been attached to this registry entry yet."
          ),
        },
        {
          title: "Capabilities",
          content: Object.keys(selectedAgent.capabilities_json ?? {}).length ? (
            <div className="flex flex-wrap gap-2">
              {Object.entries(selectedAgent.capabilities_json)
                .slice(0, 6)
                .map(([key, value]) => (
                  <StatusBadge key={key} status="pending" label={`${key}:${String(value)}`} />
                ))}
            </div>
          ) : (
            "Capability metadata has not been projected for this agent yet."
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
            eyebrow="Agent detail"
            title="Understand and control one agent at a time"
            description="The center of gravity is the selected agent: current state, recent tasks, performance posture, cost, and a direct explanation of why the agent is behaving this way."
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
          ) : !selectedAgent ? (
            <EmptyBlock title="No agents available" description="The registry has not projected any agents yet." />
          ) : (
            <>
              <div className="grid gap-6 xl:grid-cols-[0.72fr_1.28fr]">
                <Panel
                  title="Agent registry"
                  description="Select an agent to inspect its state, performance, and controls."
                >
                  <SelectionList
                    items={agents}
                    selectedId={selectedAgent.id}
                    onSelect={(agent) => {
                      void router.replace({ pathname: "/agents", query: { agent: agent.id } }, undefined, {
                        shallow: true,
                      });
                    }}
                    renderTitle={(agent) => (
                      <div className="flex items-center gap-3">
                        <span>{agent.display_name}</span>
                        <StatusBadge status={agent.status} />
                      </div>
                    )}
                    renderBody={(agent) => summarizePurpose(agent)}
                    renderMeta={(agent) => <span className="text-xs">{formatCurrency(agent.total_cost_usd)}</span>}
                    empty={
                      <EmptyBlock
                        title="No agents found"
                        description="Registry entries appear after agent nodes run in the control plane."
                      />
                    }
                  />
                </Panel>

                <div className="space-y-6">
                  <Panel
                    title={selectedAgent.display_name}
                    description="Current state and operator controls for the selected agent."
                    action={
                      <div className="flex flex-wrap items-center gap-2">
                        <StatusBadge status={selectedAgent.status} />
                        {currentExecutionId ? (
                          <Button asChild size="sm" variant="outline" className="rounded-full">
                            <Link href={`/executions/${currentExecutionId}`}>Open execution</Link>
                          </Button>
                        ) : null}
                        {selectedAgent.pending_decisions > 0 ? (
                          <Button asChild size="sm" variant="outline" className="rounded-full">
                            <Link href="/inbox">Review decisions</Link>
                          </Button>
                        ) : null}
                        <Button
                          size="sm"
                          variant="outline"
                          className="rounded-full"
                          disabled={!currentExecutionId || actionLoading}
                          onClick={() => void handleReplayExecution()}
                        >
                          <Play className="h-4 w-4" />
                          Replay
                        </Button>
                        <Button
                          size="sm"
                          className="rounded-full"
                          disabled={!currentExecutionId || actionLoading}
                          onClick={() => void handleStopExecution()}
                        >
                          <Square className="h-4 w-4" />
                          Stop execution
                        </Button>
                      </div>
                    }
                  >
                    <div className="grid gap-4 lg:grid-cols-4">
                      <MetricCard
                        eyebrow="Current state"
                        value={currentTask ? currentTask.status : selectedAgent.status}
                        delta={currentTask?.summary ?? "No active assignment is currently projected."}
                        icon={<BrainCircuit className="h-4 w-4" />}
                        tone={selectedAgent.status === "attention" ? "amber" : "slate"}
                      />
                      <MetricCard
                        eyebrow="Recent tasks"
                        value={String(agentTasks.length)}
                        delta={`${completedTaskCount} completed, ${waitingTaskCount} waiting, ${failedTaskCount} failed`}
                        icon={<Waypoints className="h-4 w-4" />}
                      />
                      <MetricCard
                        eyebrow="Performance"
                        value={
                          agentTasks.length ? `${Math.round((completedTaskCount / agentTasks.length) * 100)}%` : "N/A"
                        }
                        delta="Visible success rate for projected tasks"
                        icon={<Play className="h-4 w-4" />}
                        tone={failedTaskCount > 0 ? "amber" : "emerald"}
                      />
                      <MetricCard
                        eyebrow="Cost"
                        value={formatCurrency(selectedAgent.total_cost_usd)}
                        delta={`${selectedAgent.task_count} task${selectedAgent.task_count === 1 ? "" : "s"} in current window`}
                        tone="rose"
                        icon={<Wallet className="h-4 w-4" />}
                      />
                    </div>
                  </Panel>

                  <div className="grid gap-6 2xl:grid-cols-[0.92fr_1.08fr]">
                    <Panel
                      title="Why is it doing this?"
                      description="Readable explanation derived from task state, decisions, memory, and projected policy."
                    >
                      {why ? (
                        <div className="space-y-3">
                          <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                            <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                              Objective
                            </p>
                            <p className="mt-2 text-sm leading-7 text-slate-700 dark:text-slate-200">{why.objective}</p>
                          </div>
                          <div className="grid gap-3 lg:grid-cols-3">
                            <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                              <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                                Trigger
                              </p>
                              <p className="mt-2 text-sm leading-7 text-slate-700 dark:text-slate-200">{why.trigger}</p>
                            </div>
                            <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                              <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                                Constraints
                              </p>
                              <p className="mt-2 text-sm leading-7 text-slate-700 dark:text-slate-200">
                                {why.constraints}
                              </p>
                            </div>
                            <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                              <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                                Memory influence
                              </p>
                              <p className="mt-2 text-sm leading-7 text-slate-700 dark:text-slate-200">{why.memory}</p>
                            </div>
                          </div>
                        </div>
                      ) : (
                        <EmptyBlock
                          title="No explanation available"
                          description="Select an agent to derive a readable explanation."
                        />
                      )}
                    </Panel>

                    <Panel
                      title="Current state"
                      description="Short-term task context and recent memory relevant to the selected agent."
                    >
                      <KeyValueGrid
                        items={[
                          {
                            label: "Current task",
                            value: currentTask?.summary ?? "No active task context has been projected.",
                          },
                          {
                            label: "Latest execution",
                            value: currentExecutionId ? (
                              <Link href={`/executions/${currentExecutionId}`} className="underline underline-offset-4">
                                {currentExecutionId.slice(0, 8)}
                              </Link>
                            ) : (
                              "No recent execution linked"
                            ),
                          },
                        ]}
                      />
                      <div className="mt-4 space-y-3">
                        {memory.slice(0, 3).map((item) => (
                          <div
                            key={item.id}
                            className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8"
                          >
                            <div className="flex items-center justify-between gap-3">
                              <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">{item.title}</p>
                              <StatusBadge status="pending" label={item.scope} />
                            </div>
                            <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">{item.content}</p>
                          </div>
                        ))}
                        {!memoryLoading && memory.length === 0 ? (
                          <EmptyBlock
                            title="No memory attached"
                            description="When this agent saves or retrieves knowledge, it will surface here."
                          />
                        ) : null}
                      </div>
                    </Panel>
                  </div>

                  <div className="grid gap-6 2xl:grid-cols-[1.04fr_0.96fr]">
                    <Panel title="Recent tasks" description="Units of work recently assigned to this agent.">
                      {agentTasks.length ? (
                        <div className="space-y-3">
                          {agentTasks.map((task) => (
                            <div
                              key={task.id}
                              className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8"
                            >
                              <div className="flex items-start justify-between gap-3">
                                <div className="min-w-0">
                                  <div className="flex items-center gap-3">
                                    <p className="truncate text-sm font-semibold text-slate-950 dark:text-slate-50">
                                      {task.title}
                                    </p>
                                    <StatusBadge status={task.status} />
                                  </div>
                                  <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">
                                    {task.summary}
                                  </p>
                                </div>
                                <Link
                                  href={`/executions/${task.execution_id}`}
                                  className="shrink-0 text-sm text-slate-500 hover:text-slate-950 dark:text-slate-400 dark:hover:text-slate-50"
                                >
                                  Open
                                </Link>
                              </div>
                              <div className="mt-3 flex flex-wrap items-center gap-4 text-xs text-slate-500 dark:text-slate-400">
                                <span>Priority {task.priority}</span>
                                <span>
                                  Current step {task.current_step_id ? task.current_step_id.slice(0, 8) : "Unavailable"}
                                </span>
                                <span>Started {formatDateTime(task.started_at)}</span>
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <EmptyBlock
                          title="No active tasks"
                          description="This agent is not currently supervising any projected work."
                        />
                      )}
                    </Panel>

                    <Panel
                      title="Decision load"
                      description="Recent decisions and operator pressure tied to this agent."
                    >
                      {agentDecisions.length ? (
                        <div className="space-y-3">
                          {agentDecisions.map((decision) => (
                            <div
                              key={decision.id}
                              className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8"
                            >
                              <div className="flex flex-wrap items-center gap-2">
                                <StatusBadge status={decision.status} />
                                <StatusBadge status="pending" label={decision.decision_type} />
                                <span className="text-xs text-slate-500 dark:text-slate-400">
                                  {formatDateTime(decision.requested_at ?? decision.created_at)}
                                </span>
                              </div>
                              <p className="mt-3 text-sm leading-6 text-slate-700 dark:text-slate-200">
                                {String(
                                  decision.context_json?.summary ??
                                    decision.context_json?.prompt_message ??
                                    "Decision context was not projected for this record.",
                                )}
                              </p>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <EmptyBlock
                          title="No recent decisions"
                          description="Decision records tied to this agent will appear here when the agent reaches an approval or intervention boundary."
                        />
                      )}
                    </Panel>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
