import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, RefreshCw, RotateCcw, ShieldAlert } from "lucide-react";

import DashboardLayout from "@/components/DashboardLayout";
import { DeadLetterTable } from "@/components/ops/DeadLetterTable";
import { EventSpoolPanel } from "@/components/ops/EventSpoolPanel";
import { ProjectionLagPanel } from "@/components/ops/ProjectionLagPanel";
import {
  InspectorPanel,
  KeyValueGrid,
  MetricCard,
  Panel,
  StatusBadge,
  formatDateTime,
} from "@/components/os/operations-ui";
import ProtectedRoute from "@/components/ProtectedRoute";
import { Alert, AlertDescription, Button, Textarea } from "@/components/ui";
import { useAuth } from "@/contexts/AuthContext";
import { newClientCommandId } from "@/lib/idempotency";
import { getApiErrorMessage, opsApi, type OpsDeadLetter } from "@/lib/api";

const OPS_QUERY_ROOT = ["ops"] as const;

function canUseOps(role: string | null | undefined) {
  return role === "owner" || role === "admin";
}

export default function OpsPage() {
  const { user, isAuthenticated } = useAuth();
  const queryClient = useQueryClient();
  const organizationId = user?.default_organization_id ?? "current";
  const enabled = isAuthenticated && canUseOps(user?.organization_role);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);

  const deadLettersQuery = useQuery({
    queryKey: [...OPS_QUERY_ROOT, "deadLetters", organizationId],
    queryFn: opsApi.getDeadLetters,
    enabled,
  });
  const projectionLagQuery = useQuery({
    queryKey: [...OPS_QUERY_ROOT, "projectionLag", organizationId],
    queryFn: opsApi.getProjectionLag,
    enabled,
  });
  const eventSpoolQuery = useQuery({
    queryKey: [...OPS_QUERY_ROOT, "eventSpool", organizationId],
    queryFn: opsApi.getEventSpool,
    enabled,
  });
  const runtimeLagQuery = useQuery({
    queryKey: [...OPS_QUERY_ROOT, "runtimeIntentLag", organizationId],
    queryFn: opsApi.getRuntimeIntentLag,
    enabled,
  });

  const items = useMemo(() => deadLettersQuery.data?.items ?? [], [deadLettersQuery.data?.items]);
  const selected = useMemo(() => items.find((item) => item.id === selectedId) ?? items[0] ?? null, [items, selectedId]);
  const selectedDetailQuery = useQuery({
    queryKey: [...OPS_QUERY_ROOT, "deadLetter", selected?.id ?? "none", organizationId],
    queryFn: () => opsApi.getDeadLetter(selected?.id ?? ""),
    enabled: enabled && Boolean(selected?.id),
  });

  const invalidateOps = () => {
    void queryClient.invalidateQueries({ queryKey: OPS_QUERY_ROOT });
  };

  const replayMutation = useMutation({
    mutationFn: (item: OpsDeadLetter) =>
      opsApi.replayDeadLetter(item.id, reason.trim(), {
        idempotencyKey: newClientCommandId(`ops.dead_letter.replay:${item.id}`),
      }),
    onSuccess: () => {
      setActionError(null);
      setReason("");
      invalidateOps();
    },
    onError: (error) => {
      setActionError(getApiErrorMessage(error, "Replay was not accepted by the backend."));
    },
  });

  const resolveMutation = useMutation({
    mutationFn: (item: OpsDeadLetter) =>
      opsApi.resolveDeadLetter(item.id, reason.trim(), {
        idempotencyKey: newClientCommandId(`ops.dead_letter.resolve:${item.id}`),
      }),
    onSuccess: () => {
      setActionError(null);
      setReason("");
      invalidateOps();
    },
    onError: (error) => {
      setActionError(getApiErrorMessage(error, "Resolve was not accepted by the backend."));
    },
  });

  const runAction = (item: OpsDeadLetter, action: "replay" | "resolve") => {
    if (!reason.trim()) {
      setActionError("Recovery actions require an operator reason.");
      return;
    }
    setSelectedId(item.id);
    setActionError(null);
    if (action === "replay") {
      replayMutation.mutate(item);
      return;
    }
    resolveMutation.mutate(item);
  };

  const activeCount = deadLettersQuery.data?.counts.active ?? 0;
  const projectionStatus = projectionLagQuery.data?.projection.status ?? "unknown";
  const degraded = activeCount > 0 || ["stale", "rebuilding", "degraded"].includes(projectionStatus);
  const actionId =
    replayMutation.variables?.id && replayMutation.isPending
      ? replayMutation.variables.id
      : resolveMutation.variables?.id && resolveMutation.isPending
        ? resolveMutation.variables.id
        : null;

  const inspector = (
    <InspectorPanel
      title="Recovery Detail"
      subtitle="Dead-letter detail, redacted payload, and backend audit trail."
      sections={[
        {
          title: "Selected failure",
          content: selectedDetailQuery.data ? (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span>Status</span>
                <StatusBadge status={selectedDetailQuery.data.status} />
              </div>
              <div className="flex items-center justify-between">
                <span>Kind</span>
                <span className="capitalize">{selectedDetailQuery.data.kind.replace(/_/g, " ")}</span>
              </div>
              <p className="text-sm leading-6 text-slate-600 dark:text-slate-300">{selectedDetailQuery.data.reason}</p>
            </div>
          ) : (
            "Select a dead letter to inspect recovery options."
          ),
        },
        {
          title: "Audit trail",
          content: selectedDetailQuery.data?.operator_actions.length ? (
            <div className="space-y-3">
              {selectedDetailQuery.data.operator_actions.slice(0, 5).map((action) => (
                <div key={action.id} className="rounded-xl border border-slate-900/8 px-3 py-3 dark:border-white/8">
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-sm font-medium">{action.action}</span>
                    <StatusBadge status={action.status} />
                  </div>
                  <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">{formatDateTime(action.created_at)}</p>
                </div>
              ))}
            </div>
          ) : (
            "No recovery actions have been recorded for this item."
          ),
        },
      ]}
    />
  );

  return (
    <ProtectedRoute>
      <DashboardLayout inspector={inspector}>
        <div className="space-y-6">
          {!enabled ? (
            <Alert variant="destructive">
              <ShieldAlert className="h-4 w-4" />
              <AlertDescription>Operator recovery is limited to organization owners and admins.</AlertDescription>
            </Alert>
          ) : null}

          <Panel
            title="Operator Recovery"
            description="Recover failed backend-owned events and inspect projection/runtime lag without treating client state as authority."
            action={
              <div className="flex flex-wrap items-center justify-end gap-2">
                <StatusBadge status={degraded ? "degraded" : "fresh"} label={degraded ? "Needs attention" : "Clear"} />
                <Button type="button" variant="outline" onClick={invalidateOps} disabled={!enabled}>
                  <RefreshCw className="h-4 w-4" />
                  Refresh
                </Button>
              </div>
            }
          >
            <div className="grid gap-4 xl:grid-cols-4">
              <MetricCard
                eyebrow="Active failures"
                value={activeCount.toLocaleString()}
                delta="Unified task, event, and runtime dead letters"
                tone={activeCount > 0 ? "rose" : "emerald"}
                icon={<AlertTriangle className="h-4 w-4" />}
              />
              <MetricCard
                eyebrow="Projection"
                value={projectionStatus}
                delta={`seq ${(projectionLagQuery.data?.projection.last_sequence ?? 0).toLocaleString()}`}
                tone={projectionStatus === "fresh" ? "emerald" : "amber"}
                icon={<CheckCircle2 className="h-4 w-4" />}
              />
              <MetricCard
                eyebrow="Runtime backlog"
                value={(runtimeLagQuery.data?.backlog ?? 0).toLocaleString()}
                delta={`${runtimeLagQuery.data?.pending ?? 0} pending · ${runtimeLagQuery.data?.lag ?? 0} lag`}
                tone={(runtimeLagQuery.data?.backlog ?? 0) > 0 ? "amber" : "slate"}
                icon={<RotateCcw className="h-4 w-4" />}
              />
              <MetricCard
                eyebrow="Event spool"
                value={(eventSpoolQuery.data?.domain_events.count ?? 0).toLocaleString()}
                delta={`state v${(eventSpoolQuery.data?.state_feed_events.latest_state_version ?? 0).toLocaleString()}`}
                tone="cyan"
              />
            </div>
          </Panel>

          {actionError ? (
            <Alert variant="destructive">
              <AlertDescription>{actionError}</AlertDescription>
            </Alert>
          ) : null}

          <div className="grid gap-6 2xl:grid-cols-[1.2fr_0.8fr]">
            <Panel
              title="Dead letters"
              description="Every row is backed by a durable backend failure record. Replay is available only when retained payloads make it safe."
            >
              <DeadLetterTable
                items={items}
                selectedId={selected?.id ?? null}
                actionId={actionId}
                onSelect={(item) => setSelectedId(item.id)}
                onReplay={(item) => runAction(item, "replay")}
                onResolve={(item) => runAction(item, "resolve")}
              />
            </Panel>

            <Panel
              title="Recovery reason"
              description="Replay and resolve actions require a reason for the audit trail."
            >
              <div className="space-y-3">
                <Textarea
                  value={reason}
                  onChange={(event) => {
                    setReason(event.target.value);
                    setActionError(null);
                  }}
                  placeholder="Describe why this recovery action is safe."
                  rows={6}
                />
                <KeyValueGrid
                  columns={1}
                  items={[
                    {
                      label: "Selected item",
                      value: selected ? `${selected.kind.replace(/_/g, " ")} · ${selected.id}` : "None",
                    },
                    {
                      label: "Last seen",
                      value: selected ? formatDateTime(selected.last_seen_at) : "Not available",
                    },
                  ]}
                />
              </div>
            </Panel>
          </div>

          <div className="grid gap-6 2xl:grid-cols-[0.95fr_1.05fr]">
            <Panel title="Projection lag" description="Cursor and lag state derived from backend projection metadata.">
              <ProjectionLagPanel data={projectionLagQuery.data} />
            </Panel>

            <Panel title="Event spool" description="Recent backend event and state-feed metadata without raw secrets.">
              <EventSpoolPanel spool={eventSpoolQuery.data} runtime={runtimeLagQuery.data} />
            </Panel>
          </div>
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
