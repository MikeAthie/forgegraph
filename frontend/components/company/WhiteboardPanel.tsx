import { useCallback, useEffect, useMemo, useReducer } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ClipboardList,
  GitBranch,
  ListChecks,
  Plus,
  RefreshCw,
  Rocket,
  Route,
  Target,
} from "lucide-react";

import { StatusBadge } from "@/components/os/operations-ui";
import { Button, Spinner } from "@/components/ui";
import { whiteboardRepository } from "@/domain/repositories";
import { translateProductError } from "@/domain/errors";
import type {
  WorkWhiteboardDTO,
  WorkWhiteboardBoardCardDTO,
  WorkWhiteboardBoardSnapshotDTO,
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
  board: WorkWhiteboardBoardSnapshotDTO | null;
  boardLoading: boolean;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
};

type WhiteboardPanelAction =
  | { type: "load-start" }
  | { type: "load-success"; whiteboards: WorkWhiteboardDTO[] }
  | { type: "load-error"; error: string }
  | { type: "board-load-start" }
  | { type: "board-load-success"; board: WorkWhiteboardBoardSnapshotDTO | null }
  | { type: "board-load-error"; error: string }
  | { type: "refresh-start" }
  | { type: "refresh-finish" };

const initialState: WhiteboardPanelState = {
  whiteboards: [],
  board: null,
  boardLoading: false,
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
    case "board-load-start":
      return { ...state, boardLoading: true, error: null };
    case "board-load-success":
      return { ...state, board: action.board, boardLoading: false, error: null };
    case "board-load-error":
      return { ...state, board: null, boardLoading: false, error: action.error };
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

function workStatus(whiteboard: WorkWhiteboardDTO): string {
  return whiteboard.work_status || whiteboard.status || "draft";
}

function projectName(whiteboard: WorkWhiteboardDTO): string {
  return whiteboard.project_name || whiteboard.client_name || whiteboard.request_type || "Project";
}

function stakeholderContext(whiteboard: WorkWhiteboardDTO): Record<string, unknown> {
  return Object.keys(whiteboard.stakeholder_context ?? {}).length
    ? whiteboard.stakeholder_context
    : whiteboard.target_audience;
}

function resourceContext(whiteboard: WorkWhiteboardDTO): Record<string, unknown> {
  return Object.keys(whiteboard.resource_context ?? {}).length ? whiteboard.resource_context : whiteboard.product_context;
}

function deliveryContext(whiteboard: WorkWhiteboardDTO): Record<string, unknown> {
  return Object.keys(whiteboard.delivery_context ?? {}).length ? whiteboard.delivery_context : whiteboard.channel_context;
}

function openContextFields(whiteboard: WorkWhiteboardDTO): string[] {
  return whiteboard.work_missing_fields?.length ? whiteboard.work_missing_fields : whiteboard.missing_fields;
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

function firstLinkLabel(card: WorkWhiteboardBoardCardDTO): string {
  const [firstKey] = Object.keys(card.links ?? {});
  return firstKey ? labelForField(firstKey) : "No linked evidence";
}

function reviewLabel(card: WorkWhiteboardBoardCardDTO): string | null {
  if (!card.review_kind) {
    return null;
  }
  if (card.review?.label) {
    return card.review.label;
  }
  if (card.review_kind === "human_approval") {
    return "Human approval required";
  }
  if (card.review_kind === "automated_gate") {
    return "Automated evaluation required";
  }
  return "Department review required";
}

export function WhiteboardPanel({ companyId }: WhiteboardPanelProps) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const { whiteboards, board, boardLoading, loading, refreshing, error } = state;
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

  const loadBoard = useCallback(async () => {
    if (!activeWhiteboard) {
      dispatch({ type: "board-load-success", board: null });
      return;
    }
    dispatch({ type: "board-load-start" });
    try {
      const nextBoard = await whiteboardRepository.getBoard(activeWhiteboard.id);
      dispatch({ type: "board-load-success", board: nextBoard });
    } catch (loadError: unknown) {
      dispatch({ type: "board-load-error", error: translateProductError(loadError, "company") });
    }
  }, [activeWhiteboard]);

  useEffect(() => {
    void loadBoard();
  }, [loadBoard]);

  useEffect(() => {
    const handleWhiteboardsChanged = (event: Event) => {
      const detail = (event as CustomEvent<{ companyId?: string }>).detail;
      if (!detail?.companyId || detail.companyId === companyId) {
        void loadWhiteboards();
      }
    };
    window.addEventListener("forgegraph:whiteboards:changed", handleWhiteboardsChanged);
    return () => window.removeEventListener("forgegraph:whiteboards:changed", handleWhiteboardsChanged);
  }, [companyId, loadWhiteboards]);

  const markReady = async () => {
    if (!activeWhiteboard || refreshing) {
      return;
    }
    dispatch({ type: "refresh-start" });
    try {
      const updated = await whiteboardRepository.readyForPlanning(activeWhiteboard.id);
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

  const refreshBoard = async () => {
    if (!activeWhiteboard || refreshing) {
      return;
    }
    dispatch({ type: "refresh-start" });
    try {
      const nextBoard = await whiteboardRepository.getBoard(activeWhiteboard.id);
      dispatch({ type: "board-load-success", board: nextBoard });
    } catch (updateError: unknown) {
      const message = translateProductError(updateError, "company");
      showError("Board not refreshed", message);
      dispatch({ type: "board-load-error", error: message });
    } finally {
      dispatch({ type: "refresh-finish" });
    }
  };

  const createBoardCard = async () => {
    if (!activeWhiteboard || !board || refreshing) {
      return;
    }
    const department =
      board.departments.find((item) => !item.is_routing_department && item.active) ??
      board.departments.find((item) => item.active);
    if (!department) {
      return;
    }
    dispatch({ type: "refresh-start" });
    try {
      const nextBoard = await whiteboardRepository.createBoardCard(activeWhiteboard.id, {
        department_id: department.department_id,
        title: "New board task",
        reason: "Created from board control.",
        priority: "normal",
        idempotency_key: `ui-create-${activeWhiteboard.id}-${Date.now()}`,
      });
      dispatch({ type: "board-load-success", board: nextBoard });
    } catch (updateError: unknown) {
      const message = translateProductError(updateError, "company");
      showError("Card not created", message);
      dispatch({ type: "load-error", error: message });
    } finally {
      dispatch({ type: "refresh-finish" });
    }
  };

  const patchBoardCard = async (
    card: WorkWhiteboardBoardCardDTO,
    input: Parameters<typeof whiteboardRepository.patchBoardCard>[2],
  ) => {
    if (!activeWhiteboard || refreshing) {
      return;
    }
    dispatch({ type: "refresh-start" });
    try {
      const nextBoard = await whiteboardRepository.patchBoardCard(activeWhiteboard.id, card.id, {
        ...input,
        expected_updated_at: card.updated_at,
        idempotency_key: `ui-card-${card.id}-${Date.now()}`,
      });
      dispatch({ type: "board-load-success", board: nextBoard });
    } catch (updateError: unknown) {
      const message = translateProductError(updateError, "company");
      showError("Card not updated", message);
      dispatch({ type: "load-error", error: message });
    } finally {
      dispatch({ type: "refresh-finish" });
    }
  };

  const attachEvidence = async (card: WorkWhiteboardBoardCardDTO) => {
    if (!activeWhiteboard || refreshing) {
      return;
    }
    dispatch({ type: "refresh-start" });
    try {
      const nextBoard = await whiteboardRepository.attachBoardCardEvidence(activeWhiteboard.id, card.id, {
        evidence_type: "note",
        summary: "Updated from board control.",
        idempotency_key: `ui-evidence-${card.id}-${Date.now()}`,
      });
      dispatch({ type: "board-load-success", board: nextBoard });
    } catch (updateError: unknown) {
      const message = translateProductError(updateError, "company");
      showError("Evidence not attached", message);
      dispatch({ type: "load-error", error: message });
    } finally {
      dispatch({ type: "refresh-finish" });
    }
  };

  const reassignCard = async (card: WorkWhiteboardBoardCardDTO) => {
    if (!board) {
      return;
    }
    const target =
      board.departments.find((department) => department.active && department.department_id !== card.department_id) ??
      null;
    if (!target) {
      return;
    }
    await patchBoardCard(card, { department_id: target.department_id });
  };

  const cyclePriority = async (card: WorkWhiteboardBoardCardDTO) => {
    const order = ["low", "normal", "high", "urgent"];
    const index = order.indexOf(card.priority);
    await patchBoardCard(card, { priority: order[(index + 1) % order.length] ?? "normal" });
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
            status={workStatus(activeWhiteboard)}
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
                <p className="text-sm font-semibold">{projectName(activeWhiteboard)}</p>
              </div>
              <p className="text-sm leading-6 text-zinc-600 dark:text-zinc-300">
                {activeWhiteboard.request_summary || activeWhiteboard.objective || "No request summary captured."}
              </p>
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs" data-testid="whiteboard-status">
              <FieldValue label="Work Status" value={labelForField(workStatus(activeWhiteboard))} />
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
                <p className="text-sm font-semibold">Work Context</p>
              </div>
              <div className="mt-2 space-y-2 text-xs text-zinc-600 dark:text-zinc-300">
                <FieldValue label="Objective" value={activeWhiteboard.objective || "Not captured"} />
                <FieldValue label="Stakeholders" value={jsonSummary(stakeholderContext(activeWhiteboard))} />
                <FieldValue label="Resources" value={jsonSummary(resourceContext(activeWhiteboard))} />
                <FieldValue label="Delivery" value={jsonSummary(deliveryContext(activeWhiteboard))} />
              </div>
            </section>
            <section data-testid="whiteboard-missing-fields">
              <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Open Context</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {openContextFields(activeWhiteboard).length ? (
                  openContextFields(activeWhiteboard).map((field) => (
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
                <p className="text-sm font-semibold">Intake Tasks</p>
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

          <section data-testid="whiteboard-board" className="border-t border-zinc-900/8 pt-4 dark:border-white/8">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2 text-zinc-900 dark:text-zinc-100">
                <Route className="size-4" />
                <p className="text-sm font-semibold">Project Board</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  data-testid="whiteboard-board-refresh"
                  variant="outline"
                  size="sm"
                  onClick={() => void refreshBoard()}
                  disabled={refreshing || boardLoading}
                >
                  {refreshing || boardLoading ? <Spinner size="sm" /> : <RefreshCw className="size-4" />}
                  Refresh
                </Button>
                {board?.allowed_actions.can_modify_structure ? (
                  <Button
                    data-testid="whiteboard-routing-create-card"
                    variant="outline"
                    size="sm"
                    onClick={() => void createBoardCard()}
                    disabled={refreshing || boardLoading}
                  >
                    <Plus className="size-4" />
                    Add card
                  </Button>
                ) : null}
              </div>
            </div>

            {boardLoading ? (
              <div className="mt-4 flex min-h-[96px] items-center justify-center">
                <Spinner size="sm" />
              </div>
            ) : board ? (
              <div className="mt-3 space-y-3">
                <div className="grid gap-2 text-xs md:grid-cols-3">
                  <FieldValue
                    label="Goal"
                    value={board.project.ultimate_goal || board.project.title || "Not captured"}
                  />
                  <FieldValue label="Work Status" value={labelForField(board.project.work_status || board.project.status)} />
                  <FieldValue
                    label="Risk"
                    value={board.project.risk_blocker_summary || "No active blockers recorded."}
                  />
                </div>
                {board.lanes.length ? (
                  <div className="grid gap-3 xl:grid-cols-3">
                    {board.lanes.map((lane) => (
                      <div
                        key={lane.department_id}
                        data-testid={`whiteboard-board-lane-${lane.department_slug}`}
                        className="min-w-0 rounded-[0.75rem] border border-zinc-900/8 bg-white/65 p-3 dark:border-white/8 dark:bg-white/5"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <p className="truncate text-xs font-semibold uppercase tracking-[0.12em] text-zinc-600 dark:text-zinc-300">
                            {lane.department_name}
                          </p>
                          <span className="text-[11px] font-medium text-zinc-500 dark:text-zinc-400">
                            {lane.cards.length}
                          </span>
                        </div>
                        <div className="mt-3 space-y-2">
                          {lane.cards.map((card) => (
                            <article
                              key={card.id}
                              data-testid={`whiteboard-board-card-${card.id}`}
                              className="rounded-[0.75rem] border border-zinc-900/8 bg-white p-3 text-xs shadow-sm shadow-zinc-900/4 dark:border-white/8 dark:bg-zinc-950/60"
                            >
                              <div className="flex min-w-0 items-start justify-between gap-2">
                                <p className="min-w-0 break-words font-semibold text-zinc-900 dark:text-zinc-50">
                                  {card.title}
                                </p>
                                {card.sla_state === "breached" || card.status === "blocked" ? (
                                  <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-600 dark:text-amber-300" />
                                ) : null}
                              </div>
                              <div className="mt-2 flex flex-wrap gap-2">
                                <StatusBadge status={card.status} label={labelForField(card.status)} />
                                <span
                                  data-testid={`whiteboard-card-priority-${card.id}`}
                                  className="rounded-full border border-zinc-900/10 px-2 py-1 text-[11px] font-medium text-zinc-600 dark:border-white/10 dark:text-zinc-300"
                                >
                                  {labelForField(card.priority)}
                                </span>
                                <span
                                  data-testid={`whiteboard-card-assignee-${card.id}`}
                                  className="rounded-full border border-zinc-900/10 px-2 py-1 text-[11px] text-zinc-500 dark:border-white/10 dark:text-zinc-400"
                                >
                                  {card.assigned_user_id ? "Assigned" : lane.department_name}
                                </span>
                                {reviewLabel(card) ? (
                                  <span
                                    data-testid={`whiteboard-card-review-${card.id}`}
                                    className="rounded-full border border-blue-600/20 bg-blue-50 px-2 py-1 text-[11px] font-medium text-blue-700 dark:border-blue-300/20 dark:bg-blue-300/10 dark:text-blue-200"
                                  >
                                    {reviewLabel(card)}
                                  </span>
                                ) : null}
                              </div>
                              <p data-testid={`whiteboard-card-status-${card.id}`} className="sr-only">
                                {card.status}
                              </p>
                              {card.blocker_reason ? (
                                <p
                                  data-testid={`whiteboard-card-blocker-${card.id}`}
                                  className="mt-2 line-clamp-2 text-amber-700 dark:text-amber-200"
                                >
                                  {card.blocker_reason}
                                </p>
                              ) : null}
                              <div
                                data-testid={`whiteboard-card-evidence-${card.id}`}
                                className="mt-2 text-[11px] text-zinc-500 dark:text-zinc-400"
                              >
                                {card.evidence?.length ? `${card.evidence.length} evidence refs` : firstLinkLabel(card)}
                              </div>
                              <div className="mt-3 flex flex-wrap gap-2">
                                {card.allowed_actions.includes("start") ? (
                                  <Button
                                    data-testid={`whiteboard-card-start-${card.id}`}
                                    variant="outline"
                                    size="sm"
                                    onClick={() => void patchBoardCard(card, { status: "in_progress" })}
                                    disabled={refreshing}
                                  >
                                    <GitBranch className="size-4" />
                                    Start
                                  </Button>
                                ) : null}
                                {card.allowed_actions.includes("block") ? (
                                  <Button
                                    data-testid={`whiteboard-card-block-${card.id}`}
                                    variant="outline"
                                    size="sm"
                                    onClick={() =>
                                      void patchBoardCard(card, {
                                        status: "blocked",
                                        blocker_reason: "Blocked from board control.",
                                      })
                                    }
                                    disabled={refreshing}
                                  >
                                    <AlertTriangle className="size-4" />
                                    Block
                                  </Button>
                                ) : null}
                                {card.allowed_actions.includes("ready_for_review") ? (
                                  <Button
                                    data-testid={`whiteboard-card-ready-${card.id}`}
                                    variant="outline"
                                    size="sm"
                                    onClick={() => void patchBoardCard(card, { status: "ready_for_review" })}
                                    disabled={refreshing}
                                  >
                                    <ListChecks className="size-4" />
                                    Review
                                  </Button>
                                ) : null}
                                {card.allowed_actions.includes("complete") ? (
                                  <Button
                                    data-testid={`whiteboard-card-complete-${card.id}`}
                                    variant="outline"
                                    size="sm"
                                    onClick={() => void patchBoardCard(card, { status: "completed" })}
                                    disabled={refreshing}
                                  >
                                    <CheckCircle2 className="size-4" />
                                    Complete
                                  </Button>
                                ) : null}
                                {card.allowed_actions.includes("evidence") ? (
                                  <Button
                                    data-testid={`whiteboard-card-evidence-button-${card.id}`}
                                    variant="outline"
                                    size="sm"
                                    onClick={() => void attachEvidence(card)}
                                    disabled={refreshing}
                                  >
                                    <ClipboardList className="size-4" />
                                    Evidence
                                  </Button>
                                ) : null}
                                {card.allowed_actions.includes("reassign") ? (
                                  <Button
                                    data-testid={`whiteboard-card-reassign-${card.id}`}
                                    variant="outline"
                                    size="sm"
                                    onClick={() => void reassignCard(card)}
                                    disabled={refreshing}
                                  >
                                    <Route className="size-4" />
                                    Reassign
                                  </Button>
                                ) : null}
                                {card.allowed_actions.includes("priority") ? (
                                  <Button
                                    data-testid={`whiteboard-card-priority-action-${card.id}`}
                                    variant="outline"
                                    size="sm"
                                    onClick={() => void cyclePriority(card)}
                                    disabled={refreshing}
                                  >
                                    <RefreshCw className="size-4" />
                                    Priority
                                  </Button>
                                ) : null}
                              </div>
                            </article>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="rounded-[0.75rem] border border-dashed border-zinc-900/10 p-4 text-sm text-zinc-500 dark:border-white/10 dark:text-zinc-400">
                    No board cards.
                  </div>
                )}
              </div>
            ) : (
              <div className="mt-3 rounded-[0.75rem] border border-dashed border-zinc-900/10 p-4 text-sm text-zinc-500 dark:border-white/10 dark:text-zinc-400">
                Board unavailable.
              </div>
            )}
          </section>

          {activeWhiteboard.phase_contracts?.length ? (
            <section
              data-testid="whiteboard-phase-section"
              className="border-t border-zinc-900/8 pt-4 dark:border-white/8"
            >
              <div className="space-y-4">
                {activeWhiteboard.phase_contracts.map((phase) => (
                  <div key={phase.phase_id} data-testid={`whiteboard-phase-${phase.phase_id}`} className="space-y-3">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div className="flex items-center gap-2 text-zinc-900 dark:text-zinc-100">
                        <GitBranch className="size-4" />
                        <p className="text-sm font-semibold">{phase.phase_name || labelForField(phase.phase_id)}</p>
                      </div>
                      <div className="flex items-center gap-2">
                        <StatusBadge
                          status={phase.current_state.status}
                          label={labelForField(phase.current_state.status)}
                        />
                        {phase.gate ? (
                          <StatusBadge status={phase.gate.result ?? "pending"} label={phaseScoreLabel(phase)} />
                        ) : null}
                        {activeWhiteboard.can_update && phase.allowed_actions.includes("start") ? (
                          <Button
                            data-testid={`whiteboard-phase-start-${phase.phase_id}`}
                            variant="outline"
                            size="sm"
                            onClick={() => void startPhase(phase)}
                            disabled={refreshing}
                          >
                            {refreshing ? <Spinner size="sm" /> : <GitBranch className="size-4" />}
                            Start phase
                          </Button>
                        ) : null}
                      </div>
                    </div>
                    <div data-testid="whiteboard-phase-workstreams" className="mt-3 grid gap-2 md:grid-cols-2">
                      {phase.workstreams.length ? (
                        phase.workstreams.map((workstream) => (
                          <div
                            key={workstream.id}
                            className="flex min-w-0 items-start justify-between gap-3 border-b border-zinc-900/8 py-2 text-xs dark:border-white/8"
                          >
                            <div className="min-w-0">
                              <span className="block truncate font-medium text-zinc-800 dark:text-zinc-100">
                                {workstream.name || labelForField(workstream.id)}
                              </span>
                              {workstream.dependency_state?.status === "blocked" ? (
                                <span
                                  data-testid={`whiteboard-phase-workstream-${workstream.id}-dependency-state`}
                                  className="mt-1 block truncate text-zinc-500 dark:text-zinc-400"
                                >
                                  {workstream.dependency_state.blocker_reason || "Waiting for dependencies."}
                                </span>
                              ) : workstream.dependency_state?.status === "provisional" ? (
                                <span
                                  data-testid={`whiteboard-phase-workstream-${workstream.id}-dependency-state`}
                                  className="mt-1 block truncate text-zinc-500 dark:text-zinc-400"
                                >
                                  Provisional
                                </span>
                              ) : null}
                            </div>
                            <div className="flex shrink-0 flex-wrap justify-end gap-1">
                              {workstream.dependencies?.length ? (
                                <StatusBadge
                                  status={workstream.dependency_state?.status ?? "ready"}
                                  label={`${workstream.dependencies.length} deps`}
                                />
                              ) : null}
                              <StatusBadge status={workstream.status} label={labelForField(workstream.status)} />
                            </div>
                          </div>
                        ))
                      ) : (
                        <p className="text-xs text-zinc-500 dark:text-zinc-400">No workstreams configured.</p>
                      )}
                    </div>
                    <div className="mt-3 grid gap-2 text-xs md:grid-cols-3" data-testid="whiteboard-phase-gate">
                      <FieldValue
                        label="Gate"
                        value={phase.gate?.result ? labelForField(phase.gate.result) : "Pending"}
                      />
                      <FieldValue label="Synthesis" value={phase.current_state.synthesis ? "Captured" : "Pending"} />
                      <FieldValue
                        label="Actions"
                        value={
                          phase.allowed_actions.length ? phase.allowed_actions.map(labelForField).join(", ") : "None"
                        }
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
                        <p className="mt-2 line-clamp-2 text-zinc-500 dark:text-zinc-400">{channel.blocked_reason}</p>
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
                        <p className="mt-2 line-clamp-2 text-zinc-500 dark:text-zinc-400">{source.blocked_reason}</p>
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
                  label="Metrics Record"
                  value={activePerformance.current_state.metric_snapshot_id || "Pending"}
                  testId="whiteboard-performance-metrics-record"
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
                <Button
                  data-testid="whiteboard-mark-ready-button"
                  variant="outline"
                  size="sm"
                  onClick={() => void markReady()}
                  disabled={refreshing}
                >
                  {refreshing ? <Spinner size="sm" /> : <RefreshCw className="size-4" />}
                  Ready for planning
                </Button>
                {activePhase?.allowed_actions.includes("start") ? (
                  <Button
                    data-testid={`whiteboard-active-phase-start-${activePhase.phase_id}`}
                    variant="outline"
                    size="sm"
                    onClick={() => void startPhase(activePhase)}
                    disabled={refreshing}
                  >
                    {refreshing ? <Spinner size="sm" /> : <GitBranch className="size-4" />}
                    Start phase
                  </Button>
                ) : null}
                {activeDeployment?.allowed_actions.includes("prepare") ? (
                  <Button
                    data-testid="whiteboard-prepare-deployment-button"
                    variant="outline"
                    size="sm"
                    onClick={() => void prepareDeployment()}
                    disabled={refreshing}
                  >
                    {refreshing ? <Spinner size="sm" /> : <Rocket className="size-4" />}
                    Prepare deployment
                  </Button>
                ) : null}
                {activePerformance?.allowed_actions.includes("start") ? (
                  <Button
                    data-testid="whiteboard-start-performance-button"
                    variant="outline"
                    size="sm"
                    onClick={() => void startPerformance()}
                    disabled={refreshing}
                  >
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
