import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/router";

import DashboardLayout from "@/components/DashboardLayout";
import {
  EmptyBlock,
  InspectorPanel,
  KeyValueGrid,
  Panel,
  SectionHeader,
  SelectionList,
  StatusBadge,
  formatDateTime,
  formatDuration,
} from "@/components/os/operations-ui";
import ProtectedRoute from "@/components/ProtectedRoute";
import { Alert, AlertDescription, Button, Spinner } from "@/components/ui";
import { operationRepository } from "@/domain/repositories";
import { translateProductError } from "@/domain/errors";
import type { OperationVM } from "@/domain/translation";

export default function RunsPage() {
  const router = useRouter();
  const [operations, setOperations] = useState<OperationVM[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const data = await operationRepository.list();
        if (!cancelled) {
          setOperations(data);
        }
      } catch (err: unknown) {
        if (!cancelled) {
          setError(translateProductError(err, "operation"));
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

  const selectedOperationId =
    typeof router.query.operation === "string"
      ? router.query.operation
      : operations.length > 0
        ? (operations[0]?.id ?? null)
        : null;

  const selectedOperation = useMemo(
    () => operations.find((operation) => operation.id === selectedOperationId) ?? operations[0] ?? null,
    [operations, selectedOperationId],
  );

  return (
    <ProtectedRoute>
      <DashboardLayout
        inspector={
          selectedOperation ? (
            <InspectorPanel
              title="Operation summary"
              subtitle="Operations are surfaced here in company language first. Open the detail view for department activity, deliverables, and technical diagnostics."
              sections={[
                {
                  title: "Status",
                  content: <StatusBadge status={selectedOperation.status} />,
                },
                {
                  title: "Duration",
                  content: formatDuration(selectedOperation.durationMs),
                },
                {
                  title: "Started",
                  content: formatDateTime(selectedOperation.startedAt),
                },
              ]}
            />
          ) : null
        }
      >
        <div className="space-y-6">
          <SectionHeader
            eyebrow="Operations"
            title="Recent company operations"
            description="Review recent operations, understand status quickly, and open the full detail view when you need department-level diagnostics."
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
          ) : !selectedOperation ? (
            <EmptyBlock
              title="No operations available"
              description="Operation history will appear here after companies begin active work."
            />
          ) : (
            <div className="grid gap-6 xl:grid-cols-[0.76fr_1.24fr]">
              <Panel title="Operation list" description="Recent operations with summary-first metadata.">
                <SelectionList
                  items={operations}
                  selectedId={selectedOperation.id}
                  onSelect={(operation) => {
                    void router.replace({ pathname: "/runs", query: { operation: operation.id } }, undefined, {
                      shallow: true,
                    });
                  }}
                  renderTitle={(operation) => (
                    <div className="flex items-center gap-3">
                      <span>{operation.companyName}</span>
                      <StatusBadge status={operation.status} />
                    </div>
                  )}
                  renderBody={(operation) =>
                    `Saved setup ${operation.setupVersion} · started ${formatDateTime(operation.startedAt)}`
                  }
                  renderMeta={(operation) => <span className="text-xs">{formatDuration(operation.durationMs)}</span>}
                  empty={
                    <EmptyBlock
                      title="No operation history"
                      description="Once companies start operating, their operations will appear here."
                    />
                  }
                />
              </Panel>

              <div className="space-y-6">
                <Panel
                  title={selectedOperation.companyName}
                  description="Top-level summary before drilling into the full step sequence."
                  action={
                    <Button asChild className="rounded-full">
                      <Link href={`/runs/${selectedOperation.id}`}>Open operation detail</Link>
                    </Button>
                  }
                >
                  <KeyValueGrid
                    columns={2}
                    items={[
                      { label: "Status", value: <StatusBadge status={selectedOperation.status} /> },
                      { label: "Saved setup", value: `v${selectedOperation.setupVersion}` },
                      { label: "Started", value: formatDateTime(selectedOperation.startedAt) },
                      { label: "Duration", value: formatDuration(selectedOperation.durationMs) },
                    ]}
                  />
                </Panel>

                <Panel title="Operation state" description="Readout for queueing, runtime timing, and memory activity.">
                  <KeyValueGrid
                    columns={2}
                    items={[
                      { label: "Queue status", value: selectedOperation.queueStatus ?? "Not queued" },
                      { label: "Attempts", value: selectedOperation.attempts },
                      {
                        label: "Memory activity",
                        value: selectedOperation.memoryActivity?.has_activity ? "Active" : "None",
                      },
                      {
                        label: "Retrieved observations",
                        value: selectedOperation.memoryActivity?.retrieved_observation_count ?? 0,
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
