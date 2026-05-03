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
import { approvalRepository, operationRepository } from "@/domain/repositories";
import { translateProductError } from "@/domain/errors";
import type { ApprovalVM } from "@/domain/translation";
import { useRunLiveUpdates } from "@/hooks/useRunLiveUpdates";
import { showSuccess } from "@/lib/toast";

const estimateImpact = (approval: ApprovalVM | null) => {
  if (!approval) {
    return { cost: 0, systems: "Unavailable", risk: "low", consequence: "Unknown", blastRadius: "Unknown" };
  }

  return {
    cost: approval.estimatedCost,
    systems: approval.companyName,
    risk: approval.risk,
    consequence: approval.consequence,
    blastRadius: approval.blastRadius,
  };
};

type DecisionState = "pending" | "submitting" | "accepted" | "rejected" | "failed_to_resume" | "resumed" | null;

const decisionStateLabel = (state: DecisionState) => {
  switch (state) {
    case "submitting":
      return "Submitting";
    case "accepted":
      return "Accepted by backend";
    case "rejected":
      return "Rejected by backend";
    case "failed_to_resume":
      return "Failed to resume";
    case "resumed":
      return "Operation resumed";
    case "pending":
      return "Pending";
    default:
      return "Pending";
  }
};

const decisionStateStatus = (state: DecisionState) => {
  if (state === "failed_to_resume" || state === "rejected") {
    return "failed";
  }
  if (state === "accepted" || state === "resumed") {
    return "active";
  }
  return "paused";
};

const approvalStatusToDecisionState = (status?: ApprovalVM["status"] | null): DecisionState => {
  if (status === "approved") {
    return "accepted";
  }
  if (status === "rejected") {
    return "rejected";
  }
  return status === "pending" ? "pending" : null;
};

export default function ApprovalsPage() {
  const router = useRouter();
  const [approvals, setApprovals] = useState<ApprovalVM[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<"pending" | "approved" | "rejected" | "all">("pending");
  const [editNotes, setEditNotes] = useState("");
  const [decisionState, setDecisionState] = useState<DecisionState>(null);

  const loadApprovals = useCallback(async () => {
    setError(null);
    try {
      const data = await approvalRepository.list(statusFilter === "all" ? undefined : statusFilter);
      setApprovals(data);
    } catch (err: unknown) {
      setError(translateProductError(err, "approval"));
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    setLoading(true);
    void loadApprovals();
  }, [loadApprovals]);

  const selectedApprovalId =
    typeof router.query.item === "string"
      ? router.query.item
      : approvals.length > 0
        ? (approvals[0]?.id ?? null)
        : null;

  const selectedApproval = useMemo(
    () => approvals.find((approval) => approval.id === selectedApprovalId) ?? approvals[0] ?? null,
    [approvals, selectedApprovalId],
  );

  useEffect(() => {
    setEditNotes("");
    setDecisionState(approvalStatusToDecisionState(selectedApproval?.status));
  }, [selectedApproval?.id]);

  useRunLiveUpdates(selectedApproval?.operationId, async () => {
    if (!selectedApproval) {
      return;
    }
    const operationState = await operationRepository.getBackendState(selectedApproval.operationId);
    if (operationState.status === "resume_requested" && operationState.recoveryState === "resume_dispatch_failed") {
      setDecisionState("failed_to_resume");
    } else if (["running", "succeeded"].includes(operationState.status)) {
      setDecisionState("resumed");
    }
    await loadApprovals();
  });

  const impact = estimateImpact(selectedApproval);
  const pendingCount = approvals.filter((approval) => approval.status === "pending").length;
  const highRiskCount = approvals.filter(
    (approval) => estimateImpact(approval).risk === "high" && approval.status === "pending",
  ).length;

  const handleDecision = async (approved: boolean) => {
    if (!selectedApproval) {
      return;
    }

    setSubmitting(true);
    setDecisionState("submitting");
    setError(null);

    try {
      const result = await approvalRepository.decide(selectedApproval, approved, editNotes || undefined);
      setDecisionState(approved ? "accepted" : "rejected");

      showSuccess(
        approved ? "Decision approved" : "Decision rejected",
        result.duplicate
          ? "The backend returned the already-recorded decision."
          : "The backend recorded the decision and will drive the next operation state.",
      );

      await loadApprovals();
    } catch (err: unknown) {
      setError(translateProductError(err, "approval"));
      setDecisionState("pending");
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
          content: selectedApproval.requiredFields.length
            ? selectedApproval.requiredFields.join(", ")
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
            eyebrow="Approvals"
            title="Decide with context, not with logs"
            description="This is the primary review surface for consequential company actions. The operator should understand the request, the cost, and the consequence before choosing approve or reject."
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
            title="Approval posture"
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
                value={selectedApproval?.companyName ?? "No item"}
                delta={selectedApproval?.departmentName ?? "Select a decision to review"}
                icon={<ArrowRight className="h-4 w-4" />}
              />
              <MetricCard
                eyebrow="Cost implication"
                value={formatCurrency(impact.cost)}
                delta="Estimated additional spend if the selected operation resumes"
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
            <EmptyBlock title="Approval queue is clear" description="No approval items match the current filter." />
          ) : (
            <div className="grid gap-6 xl:grid-cols-[0.72fr_1.28fr]">
              <Panel title="Review queue" description="Every row should be understandable before it is opened.">
                <SelectionList
                  items={approvals}
                  selectedId={selectedApproval.id}
                  onSelect={(approval) => {
                    void router.replace({ pathname: "/approvals", query: { item: approval.id } }, undefined, {
                      shallow: true,
                    });
                  }}
                  renderTitle={(approval) => (
                    <div className="flex items-center gap-3">
                      <span>{approval.companyName}</span>
                      <StatusBadge status={approval.status} />
                    </div>
                  )}
                  renderBody={(approval) => {
                    const approvalImpact = estimateImpact(approval);
                    return `${approval.departmentName} · ${approvalImpact.risk} risk · ${approval.promptMessage || "Approval required before the operation resumes."}`;
                  }}
                  renderMeta={(approval) => {
                    const approvalImpact = estimateImpact(approval);
                    return (
                      <div className="text-right">
                        <div className="text-xs uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
                          {approvalImpact.risk}
                        </div>
                        <div className="mt-2 text-xs text-slate-500 dark:text-slate-400">
                          {formatDateTime(approval.createdAt)}
                        </div>
                      </div>
                    );
                  }}
                  empty={
                    <EmptyBlock
                      title="No items in this filter"
                      description="Try another approval state to review earlier approvals."
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
                      <Link href={`/runs/${selectedApproval.operationId}`}>
                        Open operation detail
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
                        {selectedApproval.promptMessage || "Context was not captured on this approval task."}
                      </p>
                    </div>
                    <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                        Proposed action
                      </p>
                      <p className="mt-2 text-sm leading-7 text-slate-700 dark:text-slate-200">
                        Resume <span className="font-medium">{selectedApproval.companyName}</span> with{" "}
                        <span className="font-medium">{selectedApproval.departmentName}</span> after a human decision is
                        recorded.
                      </p>
                    </div>
                    <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                        Why this needs you
                      </p>
                      <p className="mt-2 text-sm leading-7 text-slate-700 dark:text-slate-200">
                        {selectedApproval.promptMessage ??
                          "The operation reached an approval gate. An operator decision is required before the next department can continue."}
                      </p>
                    </div>
                    <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                        Required input
                      </p>
                      <p className="mt-2 text-sm leading-7 text-slate-700 dark:text-slate-200">
                        {selectedApproval.requiredFields.length
                          ? selectedApproval.requiredFields.join(", ")
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
                        Estimated incremental spend if the operation resumes from this point.
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
                        The operation resumes immediately at the paused department activity and carries any operator
                        notes forward.
                      </p>
                    </div>
                    <div className="rounded-[1.2rem] border border-rose-800/12 bg-rose-50 px-4 py-4 text-rose-950 dark:border-rose-200/15 dark:bg-rose-500/10 dark:text-rose-100">
                      <p className="text-[11px] uppercase tracking-[0.18em]">If rejected</p>
                      <p className="mt-2 text-sm leading-7">
                        The rejection is recorded and the operation remains paused so a human can choose the next
                        intervention path.
                      </p>
                    </div>
                  </div>
                </Panel>

                <Panel
                  title="Operator response"
                  description="Action should stay visible and immediate, not hidden behind logs."
                >
                  <div className="mb-4 flex flex-wrap items-center gap-3">
                    <StatusBadge
                      status={decisionStateStatus(decisionState)}
                      label={decisionStateLabel(decisionState)}
                    />
                    {decisionState === "accepted" ? (
                      <span className="text-sm text-slate-500 dark:text-slate-400">
                        Waiting for the backend-owned resume acknowledgement.
                      </span>
                    ) : null}
                  </div>
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
                      {submitting ? "Submitting..." : editNotes.trim() ? "Approve with notes" : "Approve"}
                    </Button>
                    <Button
                      variant="outline"
                      className="rounded-full"
                      disabled={submitting || selectedApproval.status !== "pending"}
                      onClick={() => void handleDecision(false)}
                    >
                      {submitting ? "Submitting..." : "Reject"}
                    </Button>
                    {selectedApproval.status !== "pending" ? (
                      <StatusBadge status={selectedApproval.status} label="Read only" />
                    ) : null}
                    <p className="text-sm text-slate-500 dark:text-slate-400">
                      Requested {formatDateTime(selectedApproval.createdAt)}
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
