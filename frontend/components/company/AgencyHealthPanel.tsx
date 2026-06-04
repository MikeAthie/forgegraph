import { AlertTriangle, CheckCircle2, ClipboardList, PlugZap, ShieldAlert, Sparkles, Target } from "lucide-react";
import type { ReactNode } from "react";

import type { CompanyVM, OperationVM } from "@/domain/translation";
import { cn } from "@/lib/utils";

export type AgencyHealthStatus = "healthy" | "watch" | "attention" | "critical";
export type AgencyHealthAudience = "operator" | "client";
export type AgencyConnectorStatus = "ready" | "degraded" | "missing";

export type AgencyHealthDimension = {
  id: string;
  label: string;
  score: number;
  status: AgencyHealthStatus;
  summary: string;
};

export type AgencyHealthChecklistItem = {
  id: string;
  label: string;
  complete: boolean;
};

export type AgencyConnectorReadinessItem = {
  id: string;
  label: string;
  status: AgencyConnectorStatus;
  detail?: string;
  metadata?: Record<string, unknown>;
};

export type AgencyConnectorReadiness = {
  ready: number;
  degraded: number;
  missing: number;
  summary: string;
  items: AgencyConnectorReadinessItem[];
};

export type AgencyHealthAction = {
  id: string;
  label: string;
  owner?: string;
  dueLabel?: string;
  internalNote?: string;
  clientVisible?: boolean;
};

export type AgencyHealthRisk = {
  id: string;
  label: string;
  severity: "low" | "medium" | "high";
  internalNote?: string;
  clientVisible?: boolean;
};

export type AgencyHealthOpportunity = {
  id: string;
  label: string;
  impact: "low" | "medium" | "high";
  internalNote?: string;
  clientVisible?: boolean;
};

export type AgencyHealthSnapshot = {
  agencyName: string;
  healthScore: number;
  status: AgencyHealthStatus;
  statusLabel: string;
  dimensions: AgencyHealthDimension[];
  checklist: AgencyHealthChecklistItem[];
  connectors: AgencyConnectorReadiness;
  nextActions: AgencyHealthAction[];
  risks: AgencyHealthRisk[];
  opportunities: AgencyHealthOpportunity[];
  metadata?: Record<string, unknown>;
};

type AgencyHealthPanelProps = {
  snapshot: AgencyHealthSnapshot;
  audience?: AgencyHealthAudience;
  className?: string;
};

type WorkspaceHealthInput = {
  company: CompanyVM | null;
  operations: OperationVM[];
  pendingApprovalCount: number;
  displayedCompanyStatus: string;
};

const statusTone: Record<
  AgencyHealthStatus,
  {
    dot: string;
    fill: string;
    shell: string;
    text: string;
  }
> = {
  healthy: {
    dot: "bg-emerald-500",
    fill: "bg-emerald-500",
    shell:
      "border-emerald-800/15 bg-emerald-50 text-emerald-950 dark:border-emerald-200/20 dark:bg-emerald-500/10 dark:text-emerald-100",
    text: "text-emerald-800 dark:text-emerald-100",
  },
  watch: {
    dot: "bg-amber-500",
    fill: "bg-amber-500",
    shell:
      "border-amber-800/15 bg-amber-50 text-amber-950 dark:border-amber-200/20 dark:bg-amber-500/10 dark:text-amber-100",
    text: "text-amber-800 dark:text-amber-100",
  },
  attention: {
    dot: "bg-rose-500",
    fill: "bg-rose-500",
    shell: "border-rose-800/15 bg-rose-50 text-rose-950 dark:border-rose-200/20 dark:bg-rose-500/10 dark:text-rose-100",
    text: "text-rose-800 dark:text-rose-100",
  },
  critical: {
    dot: "bg-red-600",
    fill: "bg-red-600",
    shell: "border-red-800/15 bg-red-50 text-red-950 dark:border-red-200/20 dark:bg-red-500/10 dark:text-red-100",
    text: "text-red-800 dark:text-red-100",
  },
};

const connectorTone: Record<AgencyConnectorStatus, string> = {
  ready:
    "border-emerald-800/15 bg-emerald-50 text-emerald-900 dark:border-emerald-200/20 dark:bg-emerald-500/10 dark:text-emerald-100",
  degraded:
    "border-amber-800/15 bg-amber-50 text-amber-900 dark:border-amber-200/20 dark:bg-amber-500/10 dark:text-amber-100",
  missing: "border-rose-800/15 bg-rose-50 text-rose-900 dark:border-rose-200/20 dark:bg-rose-500/10 dark:text-rose-100",
};

export const atlasAgencyHealthFixture: AgencyHealthSnapshot = {
  agencyName: "Atlas Agency",
  healthScore: 78,
  status: "watch",
  statusLabel: "Watch",
  dimensions: [
    {
      id: "delivery",
      label: "Delivery Quality",
      score: 84,
      status: "healthy",
      summary: "Client-ready deliverables are moving with clear review points.",
    },
    {
      id: "connectors",
      label: "Connector Readiness",
      score: 68,
      status: "watch",
      summary: "Core AI access is ready while downstream business connectors are still being mapped.",
    },
    {
      id: "approval-flow",
      label: "Approval Flow",
      score: 74,
      status: "watch",
      summary: "Human decisions are visible, but the next handoff still needs owner confirmation.",
    },
  ],
  checklist: [
    { id: "brief", label: "Operating brief accepted", complete: true },
    { id: "model", label: "Operating model saved", complete: true },
    { id: "connector", label: "Connector readiness confirmed", complete: false },
  ],
  connectors: {
    ready: 1,
    degraded: 1,
    missing: 1,
    summary: "1 ready, 1 degraded, 1 missing",
    items: [
      { id: "managed-ai", label: "Managed AI access", status: "ready" },
      { id: "approvals", label: "Approval queue", status: "degraded", detail: "Needs operator review" },
      { id: "crm", label: "CRM writeback", status: "missing", detail: "Not connected yet" },
    ],
  },
  nextActions: [
    {
      id: "confirm-owner",
      label: "Confirm owner for CRM writeback",
      owner: "Operator",
      dueLabel: "Next cycle",
      internalNote: "Internal scope hint: keep this outside client deliverables until write access is approved.",
    },
  ],
  risks: [
    {
      id: "handoff",
      label: "Handoffs may slow if approvals are not cleared before launch.",
      severity: "medium",
      internalNote: "Internal risk hint: use the approval queue before expanding scope.",
    },
  ],
  opportunities: [
    {
      id: "digest",
      label: "Package the next deliverable as a weekly client health digest.",
      impact: "high",
      internalNote: "Internal scope hint: reuse the same review checklist for the first retainer motion.",
    },
  ],
};

export async function fetchAtlasAgencyHealthSnapshot(): Promise<AgencyHealthSnapshot> {
  return atlasAgencyHealthFixture;
}

export function AgencyHealthPanel({ snapshot, audience = "operator", className }: AgencyHealthPanelProps) {
  const healthScore = clampScore(snapshot.healthScore);
  const tone = statusTone[snapshot.status];
  const lowestDimension = getLowestDimension(snapshot.dimensions);
  const completedChecklist = snapshot.checklist.filter((item) => item.complete).length;
  const checklistTotal = snapshot.checklist.length;
  const checklistProgress = checklistTotal ? Math.round((completedChecklist / checklistTotal) * 100) : 0;
  const actions = visibleItems(snapshot.nextActions, audience);
  const risks = visibleItems(snapshot.risks, audience);
  const opportunities = visibleItems(snapshot.opportunities, audience);

  return (
    <section
      aria-label="Agency cockpit health"
      className={cn(
        "rounded-[1.75rem] border border-zinc-900/10 bg-white/92 shadow-[0_30px_90px_-58px_rgba(15,23,42,0.38)] dark:border-white/10 dark:bg-zinc-950/72",
        className,
      )}
    >
      <div className="flex flex-col gap-5 border-b border-zinc-900/8 p-6 dark:border-white/8 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-zinc-500 dark:text-zinc-400">
            Company workspace
          </p>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight text-zinc-950 dark:text-zinc-50">Agency cockpit</h2>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-zinc-600 dark:text-zinc-300">
            {snapshot.agencyName} health across delivery quality, connector readiness, and the next agency moves.
          </p>
        </div>
        <div className={cn("shrink-0 rounded-[1.15rem] border px-4 py-3", tone.shell)}>
          <div className="flex items-center gap-2">
            <span data-testid="agency-health-status-dot" className={cn("size-2.5 rounded-full", tone.dot)} />
            <span className="text-sm font-semibold">{snapshot.statusLabel}</span>
          </div>
          <div className="mt-2 flex items-end gap-1">
            <span className="text-4xl font-semibold leading-none">{healthScore}</span>
            <span className="pb-1 text-sm opacity-75">/100</span>
          </div>
        </div>
      </div>

      <div className="grid gap-4 p-6 xl:grid-cols-[0.85fr_1.15fr]">
        <div className="space-y-4">
          <div className="rounded-[1.15rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <Target className={cn("size-4", tone.text)} />
                <p className="text-sm font-semibold text-zinc-950 dark:text-zinc-50">Health score</p>
              </div>
              <p className={cn("text-xs font-semibold uppercase tracking-[0.14em]", tone.text)}>Agency score</p>
            </div>
            <div
              aria-label="Agency health score"
              aria-valuemax={100}
              aria-valuemin={0}
              aria-valuenow={healthScore}
              role="progressbar"
              className="mt-4 h-2 rounded-full bg-zinc-900/8 dark:bg-white/10"
            >
              <div className={cn("h-2 rounded-full", tone.fill)} style={{ width: `${healthScore}%` }} />
            </div>
          </div>

          {lowestDimension ? (
            <div className="rounded-[1.15rem] border border-zinc-900/8 bg-white/80 p-4 dark:border-white/8 dark:bg-white/5">
              <div className="flex items-center gap-2">
                <ShieldAlert className={cn("size-4", statusTone[lowestDimension.status].text)} />
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">
                  Lowest dimension
                </p>
              </div>
              <div className="mt-3 flex items-start justify-between gap-4">
                <div>
                  <p className="text-sm font-semibold text-zinc-950 dark:text-zinc-50">{lowestDimension.label}</p>
                  <p className="mt-2 text-sm leading-6 text-zinc-600 dark:text-zinc-300">{lowestDimension.summary}</p>
                </div>
                <span
                  className={cn(
                    "rounded-full border px-2.5 py-1 text-xs font-semibold",
                    statusTone[lowestDimension.status].shell,
                  )}
                >
                  {clampScore(lowestDimension.score)}
                </span>
              </div>
            </div>
          ) : null}

          <div className="rounded-[1.15rem] border border-zinc-900/8 bg-white/80 p-4 dark:border-white/8 dark:bg-white/5">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <ClipboardList className="size-4 text-sky-700 dark:text-sky-200" />
                <p className="text-sm font-semibold text-zinc-950 dark:text-zinc-50">Checklist progress</p>
              </div>
              <p className="text-sm font-semibold text-zinc-950 dark:text-zinc-50">
                {completedChecklist}/{checklistTotal} complete
              </p>
            </div>
            <div className="mt-3 h-2 rounded-full bg-zinc-900/8 dark:bg-white/10">
              <div className="h-2 rounded-full bg-sky-600 dark:bg-sky-300" style={{ width: `${checklistProgress}%` }} />
            </div>
            <ul className="mt-4 space-y-2">
              {snapshot.checklist.map((item) => (
                <li key={item.id} className="flex items-center gap-2 text-sm text-zinc-600 dark:text-zinc-300">
                  <CheckCircle2
                    className={cn(
                      "size-4 shrink-0",
                      item.complete ? "text-emerald-600 dark:text-emerald-300" : "text-zinc-300 dark:text-zinc-600",
                    )}
                  />
                  <span>{item.label}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>

        <div className="space-y-4">
          <div className="rounded-[1.15rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <PlugZap className="size-4 text-cyan-700 dark:text-cyan-200" />
                  <p className="text-sm font-semibold text-zinc-950 dark:text-zinc-50">Connectors</p>
                </div>
                <p className="mt-2 text-sm leading-6 text-zinc-600 dark:text-zinc-300">{snapshot.connectors.summary}</p>
              </div>
              <div className="flex shrink-0 flex-wrap gap-2">
                <ConnectorCount label="Ready" value={snapshot.connectors.ready} status="ready" />
                <ConnectorCount label="Degraded" value={snapshot.connectors.degraded} status="degraded" />
                <ConnectorCount label="Missing" value={snapshot.connectors.missing} status="missing" />
              </div>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              {snapshot.connectors.items.map((item) => (
                <span key={item.id} className={cn("rounded-full border px-3 py-1 text-xs", connectorTone[item.status])}>
                  {item.label}: {labelize(item.status)}
                </span>
              ))}
            </div>
          </div>

          <PanelList
            emptyLabel="No immediate actions queued."
            icon={<Target className="size-4 text-zinc-600 dark:text-zinc-300" />}
            items={actions}
            renderItem={(item) => <ActionRow action={item} showInternalNotes={audience === "operator"} />}
            title="Next actions"
          />

          <div className="grid gap-4 lg:grid-cols-2">
            <PanelList
              emptyLabel="No material risks recorded."
              icon={<AlertTriangle className="size-4 text-rose-600 dark:text-rose-300" />}
              items={risks}
              renderItem={(item) => (
                <SignalRow
                  badgeLabel={labelize(item.severity)}
                  label={item.label}
                  note={audience === "operator" ? item.internalNote : undefined}
                />
              )}
              title="Risks"
            />
            <PanelList
              emptyLabel="No new opportunities recorded."
              icon={<Sparkles className="size-4 text-emerald-600 dark:text-emerald-300" />}
              items={opportunities}
              renderItem={(item) => (
                <SignalRow
                  badgeLabel={labelize(item.impact)}
                  label={item.label}
                  note={audience === "operator" ? item.internalNote : undefined}
                />
              )}
              title="Opportunities"
            />
          </div>
        </div>
      </div>
    </section>
  );
}

export function buildAgencyHealthSnapshotFromWorkspace({
  company,
  displayedCompanyStatus,
  operations,
  pendingApprovalCount,
}: WorkspaceHealthInput): AgencyHealthSnapshot {
  const profile = company?.profile;
  const agencyName = profile?.companyName ?? company?.name ?? "Atlas Agency";
  const failedCount = operations.filter((operation) => operation.status === "failed").length;
  const runningCount = operations.filter((operation) => operation.status === "running").length;
  const completedCount = operations.filter((operation) => operation.status === "completed").length;
  const hasSetup = Boolean(company?.setupVersionId);
  const hasDepartments = Boolean(company?.departments.length);
  const connectorReady = profile?.aiAccessMode !== "byok" || Boolean(profile.byokCredentialId);
  const connectorMissing = profile?.aiAccessMode === "byok" && !profile.byokCredentialId;
  const connectorReadyCount = Number(hasSetup) + Number(connectorReady);
  const connectorDegradedCount = pendingApprovalCount > 0 ? 1 : 0;
  const connectorMissingCount = Number(!hasSetup) + Number(connectorMissing);
  const deliveryScore = failedCount > 0 ? 42 : runningCount > 0 ? 78 : completedCount > 0 ? 88 : 72;
  const approvalScore = pendingApprovalCount > 0 ? 64 : 90;
  const connectorScore = connectorMissingCount > 0 ? 58 : connectorDegradedCount > 0 ? 70 : 86;
  const readinessScore = hasSetup && hasDepartments ? 84 : hasSetup ? 68 : 52;
  const dimensions: AgencyHealthDimension[] = [
    {
      id: "delivery",
      label: "Delivery Quality",
      score: deliveryScore,
      status: healthStatusForScore(deliveryScore),
      summary:
        failedCount > 0
          ? "A failed operation is blocking the clean delivery path."
          : completedCount > 0
            ? "Recent deliverables are available for review and follow-through."
            : "No completed deliverable is available yet; launch a scoped first operation.",
    },
    {
      id: "approval-flow",
      label: "Approval Flow",
      score: approvalScore,
      status: healthStatusForScore(approvalScore),
      summary:
        pendingApprovalCount > 0
          ? `${pendingApprovalCount} approval${pendingApprovalCount === 1 ? "" : "s"} need a decision before the agency can move cleanly.`
          : "No approval queue is currently blocking the next agency move.",
    },
    {
      id: "connectors",
      label: "Connector Readiness",
      score: connectorScore,
      status: healthStatusForScore(connectorScore),
      summary: connectorMissing
        ? "BYOK mode is selected, but the credential connection is not confirmed."
        : "Core agency access is ready for the next operation.",
    },
    {
      id: "readiness",
      label: "Workspace Readiness",
      score: readinessScore,
      status: healthStatusForScore(readinessScore),
      summary: hasDepartments
        ? "The company workspace has a saved operating model and department map."
        : "The workspace still needs a saved operating model before health can stabilize.",
    },
  ];
  const healthScore = Math.round(
    dimensions.reduce((total, dimension) => total + dimension.score, 0) / dimensions.length,
  );
  const status = displayedCompanyStatus === "Needs attention" ? "attention" : healthStatusForScore(healthScore);

  return {
    agencyName,
    healthScore,
    status,
    statusLabel: statusLabel(status),
    dimensions,
    checklist: [
      { id: "setup", label: "Operating model saved", complete: hasSetup },
      { id: "departments", label: "Departments mapped", complete: hasDepartments },
      { id: "operation", label: "First operation launched", complete: operations.length > 0 },
      { id: "connectors", label: "Connector access confirmed", complete: connectorReady && !connectorMissingCount },
      { id: "approvals", label: "Approval queue clear", complete: pendingApprovalCount === 0 },
    ],
    connectors: {
      ready: connectorReadyCount,
      degraded: connectorDegradedCount,
      missing: connectorMissingCount,
      summary: connectorSummary(connectorReadyCount, connectorDegradedCount, connectorMissingCount),
      items: [
        {
          id: "operating-model",
          label: "Operating model",
          status: hasSetup ? "ready" : "missing",
        },
        {
          id: "ai-access",
          label: profile?.aiAccessMode === "byok" ? "BYOK AI access" : "Managed AI access",
          status: connectorMissing ? "missing" : "ready",
          detail: connectorMissing ? "Credential not confirmed" : undefined,
        },
        {
          id: "approval-queue",
          label: "Approval queue",
          status: pendingApprovalCount > 0 ? "degraded" : "ready",
        },
      ],
    },
    nextActions: nextActionsForWorkspace({
      connectorMissing,
      failedCount,
      operations,
      pendingApprovalCount,
      runningCount,
    }),
    risks: risksForWorkspace({
      connectorMissing,
      failedCount,
      pendingApprovalCount,
      objective: profile?.objective ?? company?.description ?? "",
    }),
    opportunities: opportunitiesForWorkspace({ completedCount, operations, runningCount }),
  };
}

function PanelList<T>({
  emptyLabel,
  icon,
  items,
  renderItem,
  title,
}: {
  emptyLabel: string;
  icon: ReactNode;
  items: T[];
  renderItem: (item: T) => ReactNode;
  title: string;
}) {
  return (
    <div className="rounded-[1.15rem] border border-zinc-900/8 bg-white/80 p-4 dark:border-white/8 dark:bg-white/5">
      <div className="flex items-center gap-2">
        {icon}
        <p className="text-sm font-semibold text-zinc-950 dark:text-zinc-50">{title}</p>
      </div>
      {items.length ? (
        <ul className="mt-3 space-y-3">
          {items.map((item, index) => (
            <li key={String((item as { id?: string }).id ?? index)}>{renderItem(item)}</li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-sm leading-6 text-zinc-500 dark:text-zinc-400">{emptyLabel}</p>
      )}
    </div>
  );
}

function ActionRow({ action, showInternalNotes }: { action: AgencyHealthAction; showInternalNotes: boolean }) {
  return (
    <div className="rounded-xl border border-zinc-900/8 bg-[var(--panel-muted)] p-3 dark:border-white/8">
      <p className="text-sm font-medium text-zinc-950 dark:text-zinc-50">{action.label}</p>
      {action.owner || action.dueLabel ? (
        <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
          {[action.owner, action.dueLabel].filter(Boolean).join(" | ")}
        </p>
      ) : null}
      {showInternalNotes && action.internalNote ? <InternalNote>{action.internalNote}</InternalNote> : null}
    </div>
  );
}

function SignalRow({ badgeLabel, label, note }: { badgeLabel: string; label: string; note?: string }) {
  return (
    <div className="rounded-xl border border-zinc-900/8 bg-[var(--panel-muted)] p-3 dark:border-white/8">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="text-sm leading-6 text-zinc-700 dark:text-zinc-200">{label}</p>
        <span className="rounded-full border border-zinc-900/10 bg-white/80 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-zinc-500 dark:border-white/10 dark:bg-white/6 dark:text-zinc-300">
          {badgeLabel}
        </span>
      </div>
      {note ? <InternalNote>{note}</InternalNote> : null}
    </div>
  );
}

function InternalNote({ children }: { children: string }) {
  return (
    <p className="mt-2 rounded-lg border border-amber-800/15 bg-amber-50/75 px-3 py-2 text-xs leading-5 text-amber-950 dark:border-amber-200/15 dark:bg-amber-500/10 dark:text-amber-100">
      {children}
    </p>
  );
}

function ConnectorCount({ label, status, value }: { label: string; status: AgencyConnectorStatus; value: number }) {
  return (
    <span className={cn("rounded-full border px-3 py-1 text-xs font-medium", connectorTone[status])}>
      {value} {label}
    </span>
  );
}

function visibleItems<T extends { clientVisible?: boolean }>(items: T[], audience: AgencyHealthAudience): T[] {
  if (audience === "operator") {
    return items;
  }
  return items.filter((item) => item.clientVisible !== false);
}

function getLowestDimension(dimensions: AgencyHealthDimension[]): AgencyHealthDimension | null {
  if (!dimensions.length) {
    return null;
  }
  return dimensions.reduce((lowest, dimension) => (dimension.score < lowest.score ? dimension : lowest), dimensions[0]);
}

function clampScore(value: number): number {
  return Math.max(0, Math.min(100, Math.round(value)));
}

function healthStatusForScore(score: number): AgencyHealthStatus {
  if (score >= 82) {
    return "healthy";
  }
  if (score >= 64) {
    return "watch";
  }
  if (score >= 45) {
    return "attention";
  }
  return "critical";
}

function statusLabel(status: AgencyHealthStatus): string {
  switch (status) {
    case "healthy":
      return "Healthy";
    case "watch":
      return "Watch";
    case "attention":
      return "Needs attention";
    case "critical":
      return "Critical";
    default:
      return "Watch";
  }
}

function labelize(value: string): string {
  return value
    .replaceAll("_", " ")
    .split(" ")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function connectorSummary(ready: number, degraded: number, missing: number): string {
  return `${ready} ready, ${degraded} degraded, ${missing} missing`;
}

function nextActionsForWorkspace({
  connectorMissing,
  failedCount,
  operations,
  pendingApprovalCount,
  runningCount,
}: {
  connectorMissing: boolean;
  failedCount: number;
  operations: OperationVM[];
  pendingApprovalCount: number;
  runningCount: number;
}): AgencyHealthAction[] {
  if (failedCount > 0) {
    return [
      {
        id: "retry-failed-operation",
        label: "Retry or rescope the latest failed operation",
        owner: "Operator",
        dueLabel: "Now",
        internalNote: "Internal risk hint: inspect the failure before exposing a delivery date.",
      },
    ];
  }
  if (pendingApprovalCount > 0) {
    return [
      {
        id: "clear-approvals",
        label: `Review ${pendingApprovalCount} pending approval${pendingApprovalCount === 1 ? "" : "s"}`,
        owner: "Operator",
        dueLabel: "Today",
        internalNote: "Internal scope hint: approval delay is the current delivery bottleneck.",
      },
    ];
  }
  if (connectorMissing) {
    return [
      {
        id: "confirm-connector",
        label: "Confirm AI access before launching the next agency cycle",
        owner: "Operator",
        dueLabel: "Before launch",
        internalNote: "Internal risk hint: avoid promising autonomous delivery until access is connected.",
      },
    ];
  }
  if (!operations.length) {
    return [
      {
        id: "launch-first-operation",
        label: "Launch the first scoped agency operation",
        owner: "Operator",
        dueLabel: "Next",
      },
    ];
  }
  if (runningCount > 0) {
    return [
      {
        id: "monitor-active-operation",
        label: "Monitor the active operation until the deliverable is ready",
        owner: "Operator",
        dueLabel: "In progress",
      },
    ];
  }
  return [
    {
      id: "launch-next-cycle",
      label: "Launch the next operating cycle from the latest deliverable",
      owner: "Operator",
      dueLabel: "Next",
    },
  ];
}

function risksForWorkspace({
  connectorMissing,
  failedCount,
  objective,
  pendingApprovalCount,
}: {
  connectorMissing: boolean;
  failedCount: number;
  objective: string;
  pendingApprovalCount: number;
}): AgencyHealthRisk[] {
  const risks: AgencyHealthRisk[] = [];
  if (failedCount > 0) {
    risks.push({
      id: "failed-operation",
      label: "A failed operation is reducing confidence in the next client-ready handoff.",
      severity: "high",
      internalNote: "Internal risk hint: retry with tighter scope before presenting a new timeline.",
    });
  }
  if (pendingApprovalCount > 0) {
    risks.push({
      id: "approval-delay",
      label: "Pending approvals may delay delivery follow-through.",
      severity: "medium",
      internalNote: "Internal scope hint: approvals are backend-owned decisions and should be cleared before launch.",
    });
  }
  if (connectorMissing) {
    risks.push({
      id: "connector-access",
      label: "Connector access is not fully ready for autonomous follow-through.",
      severity: "medium",
      internalNote: "Internal risk hint: keep the client-facing commitment limited until access is confirmed.",
    });
  }
  if (objective.length > 160) {
    risks.push({
      id: "broad-objective",
      label: "The current objective may be broad for one agency cycle.",
      severity: "low",
      internalNote: "Internal scope hint: split the objective into a first deliverable and a follow-up cycle.",
    });
  }
  return risks.length
    ? risks
    : [
        {
          id: "baseline-risk",
          label: "No material delivery risks are visible in the current workspace snapshot.",
          severity: "low",
        },
      ];
}

function opportunitiesForWorkspace({
  completedCount,
  operations,
  runningCount,
}: {
  completedCount: number;
  operations: OperationVM[];
  runningCount: number;
}): AgencyHealthOpportunity[] {
  if (completedCount > 0) {
    return [
      {
        id: "delivery-digest",
        label: "Turn the latest deliverable into a recurring client update.",
        impact: "high",
        internalNote: "Internal pricing hint: use the digest as the first retainer expansion path.",
      },
    ];
  }
  if (runningCount > 0) {
    return [
      {
        id: "live-quality-loop",
        label: "Use the active operation as a live quality calibration point.",
        impact: "medium",
      },
    ];
  }
  if (!operations.length) {
    return [
      {
        id: "first-cycle",
        label: "Start with one narrow assignment to build a useful health baseline.",
        impact: "medium",
      },
    ];
  }
  return [
    {
      id: "next-cycle",
      label: "Use the current workspace rhythm to launch the next scoped agency cycle.",
      impact: "medium",
    },
  ];
}
