import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import { AlertTriangle, ArrowRight, HandCoins, ShieldCheck } from "lucide-react";

import DashboardLayout from "@/components/DashboardLayout";
import {
  EmptyBlock,
  InspectorPanel,
  MetricCard,
  Panel,
  SectionHeader,
  SelectionList,
  StatusBadge,
  formatCurrency,
  formatDateTime,
} from "@/components/os/operations-ui";
import ProtectedRoute from "@/components/ProtectedRoute";
import { Alert, AlertDescription, Button, Spinner, Textarea } from "@/components/ui";
import { approvalsApi, getApiErrorMessage, runsApi, type ApprovalTask } from "@/lib/api";
import { showSuccess } from "@/lib/toast";

const estimateImpact = (approval: ApprovalTask | null) => {
  if (!approval) {
    return { cost: 0, systems: "Unavailable", risk: "low", consequence: "Unknown", blastRadius: "Unknown" };
  }

  const promptLength = approval.prompt_message?.length ?? 0;
  const requiredFields = approval.payload?.required_fields?.length ?? 0;
  const base = 0.18 + promptLength * 0.00045 + requiredFields * 0.06;
  const risk = promptLength > 240 || requiredFields > 2 ? "high" : promptLength > 120 ? "medium" : "low";

  return {
    cost: Math.round(base * 100) / 100,
    systems: approval.graph_name,
    risk,
    consequence:
      risk === "high"
        ? "This decision can materially change customer-facing or financial behavior."
        : risk === "medium"
          ? "This decision affects a meaningful workflow branch and should include operator guidance."
          : "This is a contained decision with limited downstream impact.",
    blastRadius:
      requiredFields > 0
        ? `${requiredFields} required field${requiredFields === 1 ? "" : "s"} will be carried into the resumed execution.`
        : "The execution will resume immediately after the decision is recorded.",
  };
};

export default function ApprovalsPage() {
  const router = useRouter();
  const [tasks, setTasks] = useState<ApprovalTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<"pending" | "approved" | "rejected" | "all">("pending");
  const [editNotes, setEditNotes] = useState("");

  const loadApprovals = useCallback(async () => {
    setError(null);
    try {
      const data = await approvalsApi.list(statusFilter === "all" ? undefined : statusFilter);
      setTasks(data);
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, "Failed to load inbox items."));
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    setLoading(true);
    void loadApprovals();
  }, [loadApprovals]);

  const selectedApprovalId =
    typeof router.query.item === "string" ? router.query.item : tasks.length > 0 ? (tasks[0]?.id ?? null) : null;

  const selectedApproval = useMemo(
    () => tasks.find((task) => task.id === selectedApprovalId) ?? tasks[0] ?? null,
    [selectedApprovalId, tasks],
  );

  useEffect(() => {
    setEditNotes("");
  }, [selectedApproval?.id]);

  const impact = estimateImpact(selectedApproval);
  const pendingCount = tasks.filter((task) => task.status === "pending").length;
  const highRiskCount = tasks.filter(
    (task) => estimateImpact(task).risk === "high" && task.status === "pending",
  ).length;

  const handleDecision = async (approved: boolean) => {
    if (!selectedApproval) {
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      await runsApi.resume(selectedApproval.run_id, {
        node_id: selectedApproval.node_id,
        input_json: {
          approved,
          feedback: editNotes || undefined,
        },
      });

      showSuccess(
        approved ? "Decision approved" : "Decision rejected",
        approved
          ? "Execution resumed with operator approval."
          : "Execution stayed paused after the rejection was recorded.",
      );

      const remaining = tasks.filter((task) => task.id !== selectedApproval.id);
      await loadApprovals();
      if (remaining[0]?.id) {
        void router.replace({ pathname: "/inbox", query: { item: remaining[0].id } }, undefined, { shallow: true });
      }
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, "Failed to submit the decision."));
    } finally {
      setSubmitting(false);
    }
  };

  const inspector = selectedApproval ? (
    <InspectorPanel
      title="Decision impact"
      subtitle="The operator should be able to decide from this panel without opening logs. It keeps risk, cost, and consequence visible at all times."
      sections={[
        {
          title: "Risk level",
          content: (
            <StatusBadge
              status={impact.risk === "high" ? "failed" : impact.risk === "medium" ? "paused" : "active"}
              label={impact.risk}
            />
          ),
        },
        {
          title: "Estimated cost implication",
          content: formatCurrency(impact.cost),
        },
        {
          title: "Affected system",
          content: impact.systems,
        },
        {
          title: "Required inputs",
          content: selectedApproval.payload?.required_fields?.length
            ? selectedApproval.payload.required_fields.join(", ")
            : "No additional structured fields required.",
        },
      ]}
    />
  ) : null;

  return (
    <ProtectedRoute>
      <DashboardLayout inspector={inspector}>
        <div className="space-y-6">
          <SectionHeader
            eyebrow="Human-in-the-loop inbox"
            title="Decide with context, not with logs"
            description="This is the primary review surface for consequential agent actions. The operator should understand the request, the cost, and the consequence before choosing approve or reject."
            action={
              <div className="flex flex-wrap items-center gap-2">
                {(["pending", "approved", "rejected", "all"] as const).map((status) => (
                  <Button
                    key={status}
                    variant={statusFilter === status ? "default" : "outline"}
                    className="rounded-full"
                    onClick={() => setStatusFilter(status)}
                  >
                    {status}
                  </Button>
                ))}
              </div>
            }
          />

          <Panel
            title="Inbox posture"
            description="How much human review is waiting right now, and how critical it is."
          >
            <div className="grid gap-4 lg:grid-cols-4">
              <MetricCard
                eyebrow="Pending now"
                value={String(pendingCount)}
                delta="Items waiting on an operator decision"
                icon={<ShieldCheck className="h-4 w-4" />}
                tone={pendingCount > 0 ? "amber" : "emerald"}
              />
              <MetricCard
                eyebrow="High-risk items"
                value={String(highRiskCount)}
                delta="Requests with higher blast radius or stronger consequence"
                icon={<AlertTriangle className="h-4 w-4" />}
                tone={highRiskCount > 0 ? "rose" : "slate"}
              />
              <MetricCard
                eyebrow="Current request"
                value={selectedApproval?.graph_name ?? "No item"}
                delta={selectedApproval?.node_name ?? "Select a decision to review"}
                icon={<ArrowRight className="h-4 w-4" />}
              />
              <MetricCard
                eyebrow="Cost implication"
                value={formatCurrency(impact.cost)}
                delta="Estimated additional spend if the selected run resumes"
                icon={<HandCoins className="h-4 w-4" />}
                tone="rose"
              />
            </div>
          </Panel>

          {error ? (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}

          {loading ? (
            <div className="flex min-h-[320px] items-center justify-center rounded-[1.75rem] border border-slate-900/10 bg-white/70 dark:border-white/10 dark:bg-slate-950/50">
              <Spinner size="lg" />
            </div>
          ) : !selectedApproval ? (
            <EmptyBlock title="Inbox is clear" description="No approval items match the current filter." />
          ) : (
            <div className="grid gap-6 xl:grid-cols-[0.72fr_1.28fr]">
              <Panel title="Review queue" description="Every row should be understandable before it is opened.">
                <SelectionList
                  items={tasks}
                  selectedId={selectedApproval.id}
                  onSelect={(task) => {
                    void router.replace({ pathname: "/inbox", query: { item: task.id } }, undefined, { shallow: true });
                  }}
                  renderTitle={(task) => (
                    <div className="flex items-center gap-3">
                      <span>{task.graph_name}</span>
                      <StatusBadge status={task.status} />
                    </div>
                  )}
                  renderBody={(task) => {
                    const taskImpact = estimateImpact(task);
                    return `${task.node_name} · ${taskImpact.risk} risk · ${task.prompt_message || "Approval required before execution resumes."}`;
                  }}
                  renderMeta={(task) => {
                    const taskImpact = estimateImpact(task);
                    return (
                      <div className="text-right">
                        <div className="text-xs uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
                          {taskImpact.risk}
                        </div>
                        <div className="mt-2 text-xs text-slate-500 dark:text-slate-400">
                          {formatDateTime(task.created_at)}
                        </div>
                      </div>
                    );
                  }}
                  empty={
                    <EmptyBlock
                      title="No items in this filter"
                      description="Try another inbox state to review earlier approvals."
                    />
                  }
                />
              </Panel>

              <div className="space-y-6">
                <Panel
                  title="Decision brief"
                  description="The operator context needed to decide without opening a trace view."
                  action={
                    <Button asChild variant="outline" className="rounded-full">
                      <Link href={`/executions/${selectedApproval.run_id}`}>
                        Open execution
                        <ArrowRight className="h-4 w-4" />
                      </Link>
                    </Button>
                  }
                >
                  <div className="grid gap-4 lg:grid-cols-2">
                    <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                        Decision context
                      </p>
                      <p className="mt-2 text-sm leading-7 text-slate-700 dark:text-slate-200">
                        {selectedApproval.prompt_message || "Context was not captured on this approval task."}
                      </p>
                    </div>
                    <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                        Proposed action
                      </p>
                      <p className="mt-2 text-sm leading-7 text-slate-700 dark:text-slate-200">
                        Resume <span className="font-medium">{selectedApproval.graph_name}</span> at{" "}
                        <span className="font-medium">{selectedApproval.node_name}</span> after a human decision is
                        recorded.
                      </p>
                    </div>
                    <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                        Why this needs you
                      </p>
                      <p className="mt-2 text-sm leading-7 text-slate-700 dark:text-slate-200">
                        {selectedApproval.payload?.prompt_message ??
                          "The run reached a human gate. An operator decision is required before the next step is allowed to execute."}
                      </p>
                    </div>
                    <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                        Required input
                      </p>
                      <p className="mt-2 text-sm leading-7 text-slate-700 dark:text-slate-200">
                        {selectedApproval.payload?.required_fields?.length
                          ? selectedApproval.payload.required_fields.join(", ")
                          : "No extra structured fields are required. Operator notes are optional."}
                      </p>
                    </div>
                  </div>
                </Panel>

                <Panel title="Impact and consequence" description="What changes if you approve or reject this request.">
                  <div className="grid gap-4 lg:grid-cols-3">
                    <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Risk</p>
                      <div className="mt-2">
                        <StatusBadge
                          status={impact.risk === "high" ? "failed" : impact.risk === "medium" ? "paused" : "active"}
                          label={impact.risk}
                        />
                      </div>
                      <p className="mt-3 text-sm leading-6 text-slate-700 dark:text-slate-200">{impact.consequence}</p>
                    </div>
                    <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                        Cost implication
                      </p>
                      <p className="mt-2 text-2xl font-semibold text-slate-950 dark:text-slate-50">
                        {formatCurrency(impact.cost)}
                      </p>
                      <p className="mt-3 text-sm leading-6 text-slate-700 dark:text-slate-200">
                        Estimated incremental spend if the run resumes from this point.
                      </p>
                    </div>
                    <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                        Blast radius
                      </p>
                      <p className="mt-2 text-sm leading-7 text-slate-700 dark:text-slate-200">{impact.blastRadius}</p>
                    </div>
                  </div>
                  <div className="mt-4 grid gap-4 lg:grid-cols-2">
                    <div className="rounded-[1.2rem] border border-emerald-800/12 bg-emerald-50 px-4 py-4 text-emerald-950 dark:border-emerald-200/15 dark:bg-emerald-500/10 dark:text-emerald-100">
                      <p className="text-[11px] uppercase tracking-[0.18em]">If approved</p>
                      <p className="mt-2 text-sm leading-7">
                        The execution resumes immediately at the paused node and carries any operator notes forward.
                      </p>
                    </div>
                    <div className="rounded-[1.2rem] border border-rose-800/12 bg-rose-50 px-4 py-4 text-rose-950 dark:border-rose-200/15 dark:bg-rose-500/10 dark:text-rose-100">
                      <p className="text-[11px] uppercase tracking-[0.18em]">If rejected</p>
                      <p className="mt-2 text-sm leading-7">
                        The rejection is recorded and the run remains paused so a human can choose the next intervention
                        path.
                      </p>
                    </div>
                  </div>
                </Panel>

                <Panel
                  title="Operator response"
                  description="Action should stay visible and immediate, not hidden behind logs."
                >
                  <Textarea
                    rows={6}
                    value={editNotes}
                    onChange={(event) => setEditNotes(event.target.value)}
                    placeholder="Add guidance, constraints, or corrections that should travel with this decision."
                    className="rounded-[1.25rem] border-slate-900/12 bg-white/75 dark:border-white/10 dark:bg-white/5"
                  />
                  <div className="mt-4 flex flex-wrap items-center gap-3">
                    <Button
                      className="rounded-full"
                      disabled={submitting || selectedApproval.status !== "pending"}
                      onClick={() => void handleDecision(true)}
                    >
                      {editNotes.trim() ? "Approve with notes" : "Approve"}
                    </Button>
                    <Button
                      variant="outline"
                      className="rounded-full"
                      disabled={submitting || selectedApproval.status !== "pending"}
                      onClick={() => void handleDecision(false)}
                    >
                      Reject
                    </Button>
                    {selectedApproval.status !== "pending" ? (
                      <StatusBadge status={selectedApproval.status} label="Read only" />
                    ) : null}
                    <p className="text-sm text-slate-500 dark:text-slate-400">
                      Requested {formatDateTime(selectedApproval.created_at)}
                    </p>
                  </div>
                </Panel>
              </div>
            </div>
          )}
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
