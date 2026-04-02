import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/router";

import DashboardLayout from "@/components/DashboardLayout";
import { EmptyBlock, InspectorPanel, KeyValueGrid, Panel, SectionHeader, SelectionList, StatusBadge, formatDateTime, formatDuration } from "@/components/os/operations-ui";
import ProtectedRoute from "@/components/ProtectedRoute";
import { Alert, AlertDescription, Button, Spinner } from "@/components/ui";
import { getApiErrorMessage, runsApi, type RunListItem } from "@/lib/api";

export default function RunsPage() {
  const router = useRouter();
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const data = await runsApi.list();
        if (!cancelled) {
          setRuns(data.sort((a, b) => (b.started_at ?? "").localeCompare(a.started_at ?? "")));
        }
      } catch (err: unknown) {
        if (!cancelled) {
          setError(getApiErrorMessage(err, "Failed to load executions."));
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
  }, []);

  const selectedExecutionId =
    typeof router.query.execution === "string" ? router.query.execution : runs.length > 0 ? runs[0]?.id ?? null : null;

  const selectedExecution = useMemo(
    () => runs.find((run) => run.id === selectedExecutionId) ?? runs[0] ?? null,
    [runs, selectedExecutionId],
  );

  return (
    <ProtectedRoute>
      <DashboardLayout
        inspector={
          selectedExecution ? (
            <InspectorPanel
              title="Execution summary"
              subtitle="Executions are the immutable runtime backbone. Use the detail screen to inspect input, output, step sequence, and reasoning."
              sections={[
                {
                  title: "Status",
                  content: <StatusBadge status={String(selectedExecution.status)} />,
                },
                {
                  title: "Duration",
                  content: formatDuration(selectedExecution.duration_ms),
                },
                {
                  title: "Started",
                  content: formatDateTime(selectedExecution.started_at),
                },
              ]}
            />
          ) : null
        }
      >
        <div className="space-y-6">
          <SectionHeader
            eyebrow="Execution visibility"
            title="Distributed trace for humans"
            description="This screen keeps executions structured and readable. The operator can understand where a task moved, how long it took, and which run to inspect in depth."
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
          ) : !selectedExecution ? (
            <EmptyBlock title="No executions available" description="Execution history will appear here when workflows are run." />
          ) : (
            <div className="grid gap-6 xl:grid-cols-[0.76fr_1.24fr]">
              <Panel title="Execution list" description="Recent workflow executions with summary-first metadata.">
                <SelectionList
                  items={runs}
                  selectedId={selectedExecution.id}
                  onSelect={(run) => {
                    void router.replace(
                      { pathname: "/executions", query: { execution: run.id } },
                      undefined,
                      { shallow: true },
                    );
                  }}
                  renderTitle={(run) => (
                    <div className="flex items-center gap-3">
                      <span>{run.graph_name}</span>
                      <StatusBadge status={String(run.status)} />
                    </div>
                  )}
                  renderBody={(run) => `Version ${run.graph_version} · started ${formatDateTime(run.started_at)}`}
                  renderMeta={(run) => <span className="text-xs">{formatDuration(run.duration_ms)}</span>}
                  empty={<EmptyBlock title="No execution history" description="Once the runtime starts processing work, executions will appear here." />}
                />
              </Panel>

              <div className="space-y-6">
                <Panel
                  title={selectedExecution.graph_name}
                  description="Top-level summary before drilling into the full step sequence."
                  action={
                    <Button asChild className="rounded-full">
                      <Link href={`/executions/${selectedExecution.id}`}>Open execution detail</Link>
                    </Button>
                  }
                >
                  <KeyValueGrid
                    columns={2}
                    items={[
                      { label: "Status", value: <StatusBadge status={String(selectedExecution.status)} /> },
                      { label: "Workflow revision", value: `v${selectedExecution.graph_version}` },
                      { label: "Started", value: formatDateTime(selectedExecution.started_at) },
                      { label: "Duration", value: formatDuration(selectedExecution.duration_ms) },
                    ]}
                  />
                </Panel>

                <Panel title="Execution state" description="Readout for queueing, runtime timing, and memory activity.">
                  <KeyValueGrid
                    columns={2}
                    items={[
                      { label: "Queue status", value: selectedExecution.queue_status ?? "Not queued" },
                      { label: "Attempts", value: selectedExecution.queue_attempts ?? 0 },
                      { label: "Memory activity", value: selectedExecution.memory_activity?.has_activity ? "Active" : "None" },
                      {
                        label: "Retrieved observations",
                        value: selectedExecution.memory_activity?.retrieved_observation_count ?? 0,
                      },
                    ]}
                  />
                </Panel>
              </div>
            </div>
          )}
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
