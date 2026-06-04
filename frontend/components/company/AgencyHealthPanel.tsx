import { AlertTriangle, CheckCircle2, ClipboardList, PlugZap, ShieldAlert, Sparkles, Target } from "lucide-react";
import type { ReactNode } from "react";

import type {
  AgencyConnectorStatusViewModel,
  AgencyHealthSnapshotViewModel,
  AgencyHealthStatusViewModel,
} from "@/domain/translation";
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

export function agencyHealthSnapshotFromViewModel(
  snapshot: AgencyHealthSnapshotViewModel,
  agencyName: string,
): AgencyHealthSnapshot {
  const healthScore = clampScore(snapshot.health.score);
  const status = panelStatus(snapshot.health.status, healthScore);
  const connectorSummary = snapshot.connectorReadiness.summary;
  return {
    agencyName: agencyName.trim() || "Atlas Agency",
    healthScore,
    status,
    statusLabel: statusLabel(status),
    dimensions: snapshot.health.dimensions.map((dimension) => ({
      id: dimension.slug,
      label: dimension.label,
      score: dimension.score,
      status: panelStatus(dimension.status, dimension.score),
      summary: dimension.summary,
    })),
    checklist: snapshot.onboardingItems.map((item) => ({
      id: item.slug,
      label: item.label,
      complete: item.status === "completed",
    })),
    connectors: {
      ready: connectorSummary.ready,
      degraded: connectorSummary.degraded,
      missing: connectorSummary.missing,
      summary: connectorSummaryText(connectorSummary.ready, connectorSummary.degraded, connectorSummary.missing),
      items: snapshot.connectorReadiness.connectors.map((connector) => ({
        id: connector.slug,
        label: connector.label,
        status: panelConnectorStatus(connector.status),
        detail: connector.message,
      })),
    },
    nextActions: snapshot.nextActions.map((action) => ({
      id: action.slug,
      label: action.label,
      owner: action.ownerDepartmentSlug ?? undefined,
      dueLabel: labelize(action.priority),
      internalNote: action.reason,
    })),
    risks: snapshot.risks.map((risk) => ({
      id: risk.slug,
      label: risk.label,
      severity: risk.severity === "unknown" ? "medium" : risk.severity,
      internalNote: risk.summary,
    })),
    opportunities: snapshot.opportunities.map((opportunity) => ({
      id: opportunity.slug,
      label: opportunity.label,
      impact: opportunity.priority === "unknown" ? "medium" : opportunity.priority,
      internalNote: opportunity.summary,
    })),
  };
}

function panelStatus(status: AgencyHealthStatusViewModel, score: number): AgencyHealthStatus {
  if (status === "healthy") {
    return "healthy";
  }
  if (status === "monitor") {
    return "watch";
  }
  if (status === "attention") {
    return "attention";
  }
  if (status === "blocked") {
    return "critical";
  }
  return healthStatusForScore(score);
}

function panelConnectorStatus(status: AgencyConnectorStatusViewModel): AgencyConnectorStatus {
  if (status === "ready" || status === "degraded" || status === "missing") {
    return status;
  }
  return status === "disabled" ? "degraded" : "missing";
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

function connectorSummaryText(ready: number, degraded: number, missing: number): string {
  return `${ready} ready, ${degraded} degraded, ${missing} missing`;
}
