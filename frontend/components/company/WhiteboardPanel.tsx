import { useCallback, useEffect, useMemo, useReducer } from "react";
import { Activity, ClipboardList, GitBranch, ListChecks, RefreshCw, Rocket, Route, Target } from "lucide-react";

import { StatusBadge } from "@/components/os/operations-ui";
import { Button, Spinner } from "@/components/ui";
import { whiteboardRepository } from "@/domain/repositories";
import { translateProductError } from "@/domain/errors";
import type {
  WorkWhiteboardDTO,
  WorkWhiteboardDeploymentContractDTO,
  WorkWhiteboardPerformanceContractDTO,
  WorkWhiteboardPhaseContractDTO,
} from "@/lib/api";
import { showError } from "@/lib/toast";

type WhiteboardPanelProps = {
  companyId: string;
};

type WhiteboardPanelState = {
  whiteboards: WorkWhiteboardDTO[];
  loading: boolean;
  refreshing: boolean;
  error: string | null;
};

type WhiteboardPanelAction =
  | { type: "load-start" }
  | { type: "load-success"; whiteboards: WorkWhiteboardDTO[] }
  | { type: "load-error"; error: string }
  | { type: "refresh-start" }
  | { type: "refresh-finish" };

const initialState: WhiteboardPanelState = {
  whiteboards: [],
  loading: true,
  refreshing: false,
  error: null,
};

function reducer(state: WhiteboardPanelState, action: WhiteboardPanelAction): WhiteboardPanelState {
  switch (action.type) {
    case "load-start":
      return { ...state, loading: true, error: null };
    case "load-success":
      return { ...state, whiteboards: action.whiteboards, loading: false, error: null };
    case "load-error":
      return { ...state, loading: false, error: action.error };
    case "refresh-start":
      return { ...state, refreshing: true, error: null };
    case "refresh-finish":
      return { ...state, refreshing: false };
    default:
      return state;
  }
}

function labelForField(value: string): string {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function jsonSummary(value: Record<string, unknown>): string {
  const entries = Object.entries(value).filter(([, item]) => item !== null && item !== "");
  if (!entries.length) {
    return "Not captured";
  }
  return entries
    .slice(0, 3)
    .map(([key, item]) => `${labelForField(key)}: ${Array.isArray(item) ? item.join(", ") : String(item)}`)
    .join(" | ");
}

function phaseScoreLabel(phase: WorkWhiteboardPhaseContractDTO): string {
  const score = phase.current_state.gate?.score;
  return typeof score === "number" ? `${Math.round(score)}%` : "Pending";
}

function deploymentStatusLabel(deployment: WorkWhiteboardDeploymentContractDTO): string {
  return deployment.status ? labelForField(deployment.status) : "Not Started";
}

function performanceStatusLabel(performance: WorkWhiteboardPerformanceContractDTO): string {
  return performance.status ? labelForField(performance.status) : "Not Started";
}

export function WhiteboardPanel({ companyId }: WhiteboardPanelProps) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const { whiteboards, loading, refreshing, error } = state;
  const activeWhiteboard = useMemo(() => whiteboards[0] ?? null, [whiteboards]);
  const activePhase = useMemo(() => activeWhiteboard?.phase_contracts?.[0] ?? null, [activeWhiteboard]);
  const activeDeployment = useMemo(() => activeWhiteboard?.deployment_contract ?? null, [activeWhiteboard]);
  const activePerformance = useMemo(() => activeWhiteboard?.performance_contract ?? null, [activeWhiteboard]);

  const loadWhiteboards = useCallback(async () => {
    dispatch({ type: "load-start" });
    try {
      const data = await whiteboardRepository.list({ companyId });
      dispatch({ type: "load-success", whiteboards: data });
    } catch (loadError: unknown) {
      dispatch({ type: "load-error", error: translateProductError(loadError, "company") });
    }
  }, [companyId]);

  useEffect(() => {
    void loadWhiteboards();
  }, [loadWhiteboards]);

  const markReady = async () => {
    if (!activeWhiteboard || refreshing) {
      return;
    }
    dispatch({ type: "refresh-start" });
    try {
      const updated = await whiteboardRepository.readyForStrategy(activeWhiteboard.id);
      dispatch({
        type: "load-success",
        whiteboards: [updated, ...whiteboards.filter((whiteboard) => whiteboard.id !== updated.id)],
      });
    } catch (updateError: unknown) {
      const message = translateProductError(updateError, "company");
      showError("Whiteboard not updated", message);
      dispatch({ type: "load-error", error: message });
    } finally {
      dispatch({ type: "refresh-finish" });
    }
  };

  const startPhase = async (phase: WorkWhiteboardPhaseContractDTO) => {
    if (!activeWhiteboard || refreshing) {
      return;
    }
    dispatch({ type: "refresh-start" });
    try {
      const result = await whiteboardRepository.startPhase(activeWhiteboard.id, phase.phase_id);
      const updated = result.whiteboard ?? {
        ...activeWhiteboard,
        phase_contracts: activeWhiteboard.phase_contracts?.map((contract) =>
          contract.phase_id === phase.phase_id ? result.whiteboard_phase_contract : contract,
        ),
      };
      dispatch({
        type: "load-success",
        whiteboards: [updated, ...whiteboards.filter((whiteboard) => whiteboard.id !== updated.id)],
      });
    } catch (updateError: unknown) {
      const message = translateProductError(updateError, "company");
      showError("Phase not started", message);
      dispatch({ type: "load-error", error: message });
    } finally {
      dispatch({ type: "refresh-finish" });
    }
  };

  const prepareDeployment = async () => {
    if (!activeWhiteboard || refreshing) {
      return;
    }
    dispatch({ type: "refresh-start" });
    try {
      const result = await whiteboardRepository.prepareDeployment(activeWhiteboard.id);
      const updated = result.whiteboard ?? {
        ...activeWhiteboard,
        deployment_contract: result.deployment_contract,
      };
      dispatch({
        type: "load-success",
        whiteboards: [updated, ...whiteboards.filter((whiteboard) => whiteboard.id !== updated.id)],
      });
    } catch (updateError: unknown) {
      const message = translateProductError(updateError, "company");
      showError("Deployment not prepared", message);
      dispatch({ type: "load-error", error: message });
    } finally {
      dispatch({ type: "refresh-finish" });
    }
  };

  const startPerformance = async () => {
    if (!activeWhiteboard || refreshing) {
      return;
    }
    dispatch({ type: "refresh-start" });
    try {
      const result = await whiteboardRepository.startPerformance(activeWhiteboard.id);
      const updated = result.whiteboard ?? {
        ...activeWhiteboard,
        performance_contract: result.performance_contract,
      };
      dispatch({
        type: "load-success",
        whiteboards: [updated, ...whiteboards.filter((whiteboard) => whiteboard.id !== updated.id)],
      });
    } catch (updateError: unknown) {
      const message = translateProductError(updateError, "company");
      showError("Performance review not started", message);
      dispatch({ type: "load-error", error: message });
    } finally {
      dispatch({ type: "refresh-finish" });
    }
  };

  return (
    <div
      data-testid="whiteboard-panel"
      className="rounded-[1.35rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-zinc-950 dark:text-zinc-50">
          <ClipboardList className="size-4" />
          <p className="text-sm font-semibold">Work Whiteboard</p>
        </div>
        {activeWhiteboard ? (
          <StatusBadge
            status={activeWhiteboard.status}
            label={`${Math.round(activeWhiteboard.completion_score)}% complete`}
          />
        ) : null}
      </div>

      {loading ? (
        <div className="mt-4 flex min-h-[112px] items-center justify-center">
          <Spinner size="sm" />
        </div>
      ) : activeWhiteboard ? (
        <div className="mt-4 space-y-4">
          <div className="grid gap-3 md:grid-cols-[1.1fr_0.9fr]">
            <div data-testid="whiteboard-summary" className="space-y-2">
              <div className="flex items-center gap-2 text-zinc-900 dark:text-zinc-100">
                <Target className="size-4" />
                <p className="text-sm font-semibold">{activeWhiteboard.request_type || "Request"}</p>
              </div>
              <p className="text-sm leading-6 text-zinc-600 dark:text-zinc-300">
                {activeWhiteboard.request_summary || activeWhiteboard.objective || "No request summary captured."}
              </p>
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs" data-testid="whiteboard-status">
              <FieldValue label="Status" value={labelForField(activeWhiteboard.status)} />
              <FieldValue
                label="Score"
                value={`${Math.round(activeWhiteboard.completion_score)}%`}
                testId="whiteboard-completion-score"
              />
              <FieldValue label="Budget" value={activeWhiteboard.budget_limit || "Not captured"} />
              <FieldValue label="Timeline" value={activeWhiteboard.timeline || "Not captured"} />
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            <section data-testid="whiteboard-known-fields">
              <div className="flex items-center gap-2 text-zinc-900 dark:text-zinc-100">
                <ListChecks className="size-4" />
                <p className="text-sm font-semibold">Known Fields</p>
              </div>
              <div className="mt-2 space-y-2 text-xs text-zinc-600 dark:text-zinc-300">
                <FieldValue label="Objective" value={activeWhiteboard.objective || "Not captured"} />
                <FieldValue label="Product" value={jsonSummary(activeWhiteboard.product_context)} />
                <FieldValue label="Channels" value={jsonSummary(activeWhiteboard.channel_context)} />
              </div>
            </section>
            <section data-testid="whiteboard-missing-fields">
              <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Missing Fields</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {activeWhiteboard.missing_fields.length ? (
                  activeWhiteboard.missing_fields.map((field) => (
                    <span
                      key={field}
                      className="rounded-full border border-zinc-900/10 bg-white/80 px-3 py-1 text-xs text-zinc-700 dark:border-white/10 dark:bg-white/6 dark:text-zinc-200"
                    >
                      {labelForField(field)}
                    </span>
                  ))
                ) : (
                  <span className="text-xs text-zinc-500 dark:text-zinc-400">Ready</span>
                )}
              </div>
            </section>
          </div>

          {activeWhiteboard.routing_records?.length ? (
            <section data-testid="whiteboard-routing-tasks">
              <div className="flex items-center gap-2 text-zinc-900 dark:text-zinc-100">
                <Route className="size-4" />
                <p className="text-sm font-semibold">Onboarding Tasks</p>
              </div>
              <div className="mt-2 grid gap-2 md:grid-cols-2">
                {activeWhiteboard.routing_records.slice(0, 6).map((record) => (
                  <div
                    key={record.id}
                    className="rounded-[1rem] border border-zinc-900/8 bg-white/70 p-3 text-xs dark:border-white/8 dark:bg-white/5"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-semibold text-zinc-900 dark:text-zinc-100">{record.department_name}</span>
                      <StatusBadge status={record.status} label={labelForField(record.status)} />
                    </div>
                    <p className="mt-2 line-clamp-2 text-zinc-500 dark:text-zinc-400">{record.reason}</p>
                  </div>
                ))}
              </div>
            </section>
          ) : null}

          {activeWhiteboard.phase_contracts?.length ? (
            <section data-testid="whiteboard-phase-section" className="border-t border-zinc-900/8 pt-4 dark:border-white/8">
              <div className="space-y-4">
                {activeWhiteboard.phase_contracts.map((phase) => (
                  <div key={phase.phase_id} data-testid={`whiteboard-phase-${phase.phase_id}`} className="space-y-3">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div className="flex items-center gap-2 text-zinc-900 dark:text-zinc-100">
                        <GitBranch className="size-4" />
                        <p className="text-sm font-semibold">{phase.phase_name || labelForField(phase.phase_id)}</p>
                      </div>
                      <div className="flex items-center gap-2">
                        <StatusBadge status={phase.current_state.status} label={labelForField(phase.current_state.status)} />
                        {phase.gate ? (
                          <StatusBadge status={phase.gate.result ?? "pending"} label={phaseScoreLabel(phase)} />
                        ) : null}
                      </div>
                    </div>
                    <div data-testid="whiteboard-phase-workstreams" className="mt-3 grid gap-2 md:grid-cols-2">
                      {phase.workstreams.length ? (
                        phase.workstreams.map((workstream) => (
                          <div
                            key={workstream.id}
                            className="flex min-w-0 items-center justify-between gap-3 border-b border-zinc-900/8 py-2 text-xs dark:border-white/8"
                          >
                            <span className="truncate font-medium text-zinc-800 dark:text-zinc-100">
                              {workstream.name || labelForField(workstream.id)}
                            </span>
                            <StatusBadge status={workstream.status} label={labelForField(workstream.status)} />
                          </div>
                        ))
                      ) : (
                        <p className="text-xs text-zinc-500 dark:text-zinc-400">No workstreams configured.</p>
                      )}
                    </div>
                    <div className="mt-3 grid gap-2 text-xs md:grid-cols-3" data-testid="whiteboard-phase-gate">
                      <FieldValue label="Gate" value={phase.gate?.result ? labelForField(phase.gate.result) : "Pending"} />
                      <FieldValue
                        label="Synthesis"
                        value={phase.current_state.synthesis ? "Captured" : "Pending"}
                      />
                      <FieldValue
                        label="Actions"
                        value={phase.allowed_actions.length ? phase.allowed_actions.map(labelForField).join(", ") : "None"}
                      />
                      {phase.current_state.applied_actions?.approval_task_id ? (
                        <FieldValue label="Approval" value="Queued" testId="whiteboard-phase-approval" />
                      ) : null}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          ) : null}

          {activeDeployment ? (
            <section
              data-testid="whiteboard-deployment-section"
              className="border-t border-zinc-900/8 pt-4 dark:border-white/8"
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-2 text-zinc-900 dark:text-zinc-100">
                  <Rocket className="size-4" />
                  <p className="text-sm font-semibold">Deployment</p>
                </div>
                <StatusBadge status={activeDeployment.status} label={deploymentStatusLabel(activeDeployment)} />
              </div>
              <div data-testid="whiteboard-deployment-channels" className="mt-3 grid gap-2 md:grid-cols-2">
                {activeDeployment.channels.length ? (
                  activeDeployment.channels.map((channel) => (
                    <div
                      key={channel.id}
                      data-testid={`whiteboard-deployment-channel-${channel.id}`}
                      className="rounded-[1rem] border border-zinc-900/8 bg-white/70 p-3 text-xs dark:border-white/8 dark:bg-white/5"
                    >
                      <div className="flex min-w-0 items-center justify-between gap-3">
                        <span className="truncate font-semibold text-zinc-900 dark:text-zinc-100">
                          {channel.display_name || labelForField(channel.id)}
                        </span>
                        <StatusBadge status={channel.status} label={labelForField(channel.status)} />
                      </div>
                      {channel.blocked_reason ? (
                        <p className="mt-2 line-clamp-2 text-zinc-500 dark:text-zinc-400">
                          {channel.blocked_reason}
                        </p>
                      ) : null}
                      <div className="mt-3 grid gap-2">
                        {channel.tool_execution_id ? (
                          <FieldValue
                            label="Receipt"
                            value={channel.tool_execution_id}
                            testId="whiteboard-deployment-receipt"
                          />
                        ) : null}
                        {channel.company_signal_id ? (
                          <FieldValue
                            label="Signal"
                            value={channel.company_signal_id}
                            testId="whiteboard-deployment-signal"
                          />
                        ) : null}
                        {channel.approval_task_id ? (
                          <FieldValue
                            label="Approval"
                            value={channel.approval_task_id}
                            testId="whiteboard-deployment-approval"
                          />
                        ) : null}
                      </div>
                    </div>
                  ))
                ) : (
                  <p className="text-xs text-zinc-500 dark:text-zinc-400">No deployment channels configured.</p>
                )}
              </div>
            </section>
          ) : null}

          {activePerformance ? (
            <section
              data-testid="whiteboard-performance-section"
              className="border-t border-zinc-900/8 pt-4 dark:border-white/8"
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-2 text-zinc-900 dark:text-zinc-100">
                  <Activity className="size-4" />
                  <p className="text-sm font-semibold">Performance Review</p>
                </div>
                <StatusBadge status={activePerformance.status} label={performanceStatusLabel(activePerformance)} />
              </div>
              <div data-testid="whiteboard-performance-sources" className="mt-3 grid gap-2 md:grid-cols-2">
                {activePerformance.sources.length ? (
                  activePerformance.sources.map((source) => (
                    <div
                      key={source.id}
                      data-testid={`whiteboard-performance-source-${source.id}`}
                      className="rounded-[1rem] border border-zinc-900/8 bg-white/70 p-3 text-xs dark:border-white/8 dark:bg-white/5"
                    >
                      <div className="flex min-w-0 items-center justify-between gap-3">
                        <span className="truncate font-semibold text-zinc-900 dark:text-zinc-100">
                          {source.display_name || labelForField(source.id)}
                        </span>
                        <StatusBadge status={source.status} label={labelForField(source.status)} />
                      </div>
                      {source.blocked_reason ? (
                        <p className="mt-2 line-clamp-2 text-zinc-500 dark:text-zinc-400">
                          {source.blocked_reason}
                        </p>
                      ) : null}
                      <div className="mt-3 grid gap-2">
                        {source.tool_execution_id ? (
                          <FieldValue
                            label="Receipt"
                            value={source.tool_execution_id}
                            testId="whiteboard-performance-receipt"
                          />
                        ) : null}
                        {source.company_signal_id ? (
                          <FieldValue
                            label="Signal"
                            value={source.company_signal_id}
                            testId="whiteboard-performance-signal"
                          />
                        ) : null}
                        {source.metrics && Object.keys(source.metrics).length ? (
                          <FieldValue
                            label="Metrics"
                            value={Object.keys(source.metrics).slice(0, 4).map(labelForField).join(", ")}
                            testId="whiteboard-performance-metrics"
                          />
                        ) : null}
                      </div>
                    </div>
                  ))
                ) : (
                  <p className="text-xs text-zinc-500 dark:text-zinc-400">No metric sources configured.</p>
                )}
              </div>
              <div className="mt-3 grid gap-2 text-xs md:grid-cols-3" data-testid="whiteboard-performance-state">
                <FieldValue
                  label="Snapshot"
                  value={activePerformance.current_state.metric_snapshot_id || "Pending"}
                  testId="whiteboard-performance-snapshot"
                />
                <FieldValue
                  label="Report"
                  value={activePerformance.current_state.report_run_id || "Pending"}
                  testId="whiteboard-performance-report"
                />
                <FieldValue
                  label="Evaluation"
                  value={activePerformance.current_state.evaluation_id || "Pending"}
                  testId="whiteboard-performance-evaluation"
                />
              </div>
            </section>
          ) : null}

          <div className="flex flex-wrap items-center justify-between gap-3">
            {error ? <p className="text-xs text-red-600 dark:text-red-300">{error}</p> : <span />}
            {activeWhiteboard.can_update ? (
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" size="sm" onClick={() => void markReady()} disabled={refreshing}>
                  {refreshing ? <Spinner size="sm" /> : <RefreshCw className="size-4" />}
                  Mark ready
                </Button>
                {activePhase?.allowed_actions.includes("start") ? (
                  <Button variant="outline" size="sm" onClick={() => void startPhase(activePhase)} disabled={refreshing}>
                    {refreshing ? <Spinner size="sm" /> : <GitBranch className="size-4" />}
                    Start phase
                  </Button>
                ) : null}
                {activeDeployment?.allowed_actions.includes("prepare") ? (
                  <Button variant="outline" size="sm" onClick={() => void prepareDeployment()} disabled={refreshing}>
                    {refreshing ? <Spinner size="sm" /> : <Rocket className="size-4" />}
                    Prepare deployment
                  </Button>
                ) : null}
                {activePerformance?.allowed_actions.includes("start") ? (
                  <Button variant="outline" size="sm" onClick={() => void startPerformance()} disabled={refreshing}>
                    {refreshing ? <Spinner size="sm" /> : <Activity className="size-4" />}
                    Start review
                  </Button>
                ) : null}
              </div>
            ) : null}
          </div>
        </div>
      ) : (
        <div className="mt-4 rounded-[1rem] border border-dashed border-zinc-900/10 p-4 text-sm text-zinc-500 dark:border-white/10 dark:text-zinc-400">
          No active whiteboard.
        </div>
      )}
    </div>
  );
}

function FieldValue({ label, value, testId }: { label: string; value: string; testId?: string }) {
  return (
    <div data-testid={testId} className="min-w-0 border-b border-zinc-900/8 py-2 dark:border-white/8">
      <p className="text-[11px] uppercase tracking-[0.16em] text-zinc-500 dark:text-zinc-400">{label}</p>
      <p className="mt-1 break-words text-xs font-medium text-zinc-800 dark:text-zinc-100">{value}</p>
    </div>
  );
}
