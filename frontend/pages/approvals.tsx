import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/router";

import DashboardLayout from "@/components/DashboardLayout";
import {
  EmptyBlock,
  InspectorPanel,
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
    return { cost: 0, systems: "Unavailable", risk: "low" };
  }

  const promptLength = approval.prompt_message?.length ?? 0;
  const base = 0.14 + promptLength * 0.00045;
  const risk = promptLength > 240 ? "high" : promptLength > 120 ? "medium" : "low";
  return {
    cost: Math.round(base * 100) / 100,
    systems: approval.graph_name,
    risk,
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

      const nextItems = tasks.filter((task) => task.id !== selectedApproval.id);
      await loadApprovals();
      if (nextItems[0]?.id) {
        void router.replace({ pathname: "/inbox", query: { item: nextItems[0].id } }, undefined, { shallow: true });
      }
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, "Failed to submit the decision."));
    } finally {
      setSubmitting(false);
    }
  };

  const inspector = selectedApproval ? (
    <InspectorPanel
      title="Impact preview"
      subtitle="Approvals should expose the operational consequence before the user makes a decision."
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
          title: "Estimated cost",
          content: formatCurrency(impact.cost),
        },
        {
          title: "Affected systems",
          content: impact.systems,
        },
        {
          title: "Execution linkage",
          content: selectedApproval.run_id,
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
            title="Review consequential agent decisions"
            description="Operators should be able to see the proposed action, understand the reasoning summary, and decide with impact in view."
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
            <div className="grid gap-6 xl:grid-cols-[0.74fr_1.26fr]">
              <Panel title="Pending items" description="List of reviewable actions with risk and timestamp.">
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
                  renderBody={(task) =>
                    `${task.node_name}: ${task.prompt_message || "Approval required before execution resumes."}`
                  }
                  renderMeta={(task) => (
                    <div className="text-right">
                      <div className="text-xs uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
                        {estimateImpact(task).risk}
                      </div>
                      <div className="mt-2 text-xs text-slate-500 dark:text-slate-400">
                        {formatDateTime(task.created_at)}
                      </div>
                    </div>
                  )}
                  empty={
                    <EmptyBlock
                      title="No items in this filter"
                      description="Try another inbox state to review earlier approvals."
                    />
                  }
                />
              </Panel>

              <div className="space-y-6">
                <Panel title="Decision review" description="Context first, raw trace later.">
                  <div className="grid gap-4 lg:grid-cols-2">
                    <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                        Input
                      </p>
                      <p className="mt-2 text-sm leading-7 text-slate-700 dark:text-slate-200">
                        {selectedApproval.prompt_message || "Input context was not captured on this approval task."}
                      </p>
                    </div>
                    <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                        Proposed action
                      </p>
                      <p className="mt-2 text-sm leading-7 text-slate-700 dark:text-slate-200">
                        Resume the execution at <span className="font-medium">{selectedApproval.node_name}</span> once a
                        decision is recorded.
                      </p>
                    </div>
                    <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                        Reasoning summary
                      </p>
                      <p className="mt-2 text-sm leading-7 text-slate-700 dark:text-slate-200">
                        {selectedApproval.payload?.prompt_message ??
                          "The execution reached a human gate and paused because it needs an operator decision before it can continue."}
                      </p>
                    </div>
                    <div className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
                      <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                        Expected outcome
                      </p>
                      <p className="mt-2 text-sm leading-7 text-slate-700 dark:text-slate-200">
                        Approval resumes execution. Rejection records the decision and leaves the execution paused for
                        follow-up.
                      </p>
                    </div>
                  </div>
                </Panel>

                <Panel
                  title="Edit before approving"
                  description="Adjust operator feedback or constraints before resuming the execution."
                >
                  <Textarea
                    rows={6}
                    value={editNotes}
                    onChange={(event) => setEditNotes(event.target.value)}
                    placeholder="Add guidance, corrections, or operator feedback that should travel with the approval."
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
