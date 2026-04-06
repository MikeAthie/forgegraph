import { useEffect, useState } from "react";
import Link from "next/link";

import DashboardLayout from "@/components/DashboardLayout";
import {
  EmptyBlock,
  InspectorPanel,
  Panel,
  SectionHeader,
  StatusBadge,
  formatDateTime,
} from "@/components/os/operations-ui";
import ProtectedRoute from "@/components/ProtectedRoute";
import { Alert, AlertDescription, Button, Spinner } from "@/components/ui";
import { executionsApi, getApiErrorMessage, workflowsApi, type GraphListItem, type RunListItem } from "@/lib/api";

export default function WorkflowsPage() {
  const [workflows, setWorkflows] = useState<GraphListItem[]>([]);
  const [executions, setExecutions] = useState<RunListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const [workflowData, executionData] = await Promise.all([workflowsApi.list(), executionsApi.list()]);
        if (!cancelled) {
          setWorkflows(workflowData);
          setExecutions(executionData.slice(0, 8));
        }
      } catch (err: unknown) {
        if (!cancelled) {
          setError(getApiErrorMessage(err, "Failed to load workflow workspace."));
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

  return (
    <ProtectedRoute>
      <DashboardLayout
        inspector={
          <InspectorPanel
            title="Builder workspace"
            subtitle="Workflows remain fully supported, but they are now a secondary workspace under the operating shell."
            sections={[
              {
                title: "Mental model",
                content:
                  "Definitions and revisions live here. Operations happen from dashboard, agents, tasks, inbox, and accounting.",
              },
              { title: "Compatibility", content: "Legacy graph routes remain available while the new IA settles in." },
            ]}
          />
        }
      >
        <div className="space-y-6">
          <SectionHeader
            eyebrow="Workflow workspace"
            title="Definitions, revisions, and execution visibility"
            description="Authoring stays available for builder users, but the workspace is explicitly subordinate to system state."
            action={
              <Button asChild className="rounded-full">
                <Link href="/graphs">Open editor</Link>
              </Button>
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
          ) : (
            <>
              <Panel
                title="Workflow definitions"
                description="Reusable authored definitions available to the organization."
              >
                {workflows.length ? (
                  <div className="grid gap-4 lg:grid-cols-2">
                    {workflows.map((workflow) => (
                      <div
                        key={workflow.id}
                        className="rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">{workflow.name}</p>
                            <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">
                              {workflow.description || "No description provided."}
                            </p>
                          </div>
                          <StatusBadge status="pending" label={`${workflow.version_count} rev`} />
                        </div>
                        <div className="mt-4 flex flex-wrap items-center gap-3 text-xs text-slate-500 dark:text-slate-400">
                          <span>Updated {formatDateTime(workflow.updated_at)}</span>
                          <Link
                            href={`/graphs/${workflow.id}`}
                            className="text-slate-900 hover:underline dark:text-slate-50"
                          >
                            Open definition
                          </Link>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <EmptyBlock
                    title="No workflows defined"
                    description="Create a workflow to start routing work through the builder workspace."
                  />
                )}
              </Panel>

              <Panel
                title="Recent executions"
                description="Visibility from the builder side without turning this into the primary runtime surface."
              >
                {executions.length ? (
                  <div className="space-y-3">
                    {executions.map((execution) => (
                      <Link
                        key={execution.id}
                        href={`/executions/${execution.id}`}
                        className="flex items-start justify-between gap-4 rounded-[1.2rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 transition-colors hover:bg-slate-950 hover:text-white dark:border-white/8 dark:hover:bg-white dark:hover:text-slate-950"
                      >
                        <div>
                          <p className="text-sm font-semibold">{execution.graph_name}</p>
                          <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">
                            Started {formatDateTime(execution.started_at)}
                          </p>
                        </div>
                        <StatusBadge status={String(execution.status)} />
                      </Link>
                    ))}
                  </div>
                ) : (
                  <EmptyBlock
                    title="No recent executions"
                    description="Execution history will appear here as workflows are run."
                  />
                )}
              </Panel>
            </>
          )}
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
