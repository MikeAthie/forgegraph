import type { MemoryObservationVM } from "@/domain/repositories/memoryRepository";
import { EmptyBlock, KeyValueGrid, StatusBadge, formatDateTime } from "@/components/os/operations-ui";
import { Spinner } from "@/components/ui";

const toLabelCase = (value: string) => {
  if (!value) {
    return "Untyped";
  }
  return value
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(" ");
};

interface MemoryObservationDetailPanelProps {
  error: string | null;
  loading: boolean;
  observation: MemoryObservationVM | null;
}

export function MemoryObservationDetailPanel({ error, loading, observation }: MemoryObservationDetailPanelProps) {
  return (
    <div className="space-y-4">
      <div>
        <p className="text-[11px] uppercase tracking-[0.22em] text-slate-500 dark:text-slate-400">Inspection</p>
        <h3 className="mt-2 text-lg font-semibold text-slate-950 dark:text-slate-50">Observation detail</h3>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
          Inspect the full content, linked scope identifiers, and the timeline that shaped this memory.
        </p>
      </div>

      {loading ? (
        <div className="flex min-h-96 items-center justify-center gap-3 rounded-[1.4rem] border border-slate-900/8 bg-[var(--panel-muted)] dark:border-white/8">
          <Spinner size="md" />
          <span className="text-sm text-slate-500 dark:text-slate-400">Loading observation detail...</span>
        </div>
      ) : null}

      {!loading && error ? (
        <div className="rounded-[1.4rem] border border-rose-800/15 bg-rose-50 px-4 py-4 text-sm text-rose-900 dark:border-rose-200/20 dark:bg-rose-500/10 dark:text-rose-100">
          {error}
        </div>
      ) : null}

      {!loading && !error && !observation ? (
        <EmptyBlock
          title="Pick an observation"
          description="Select any item from the ledger to inspect its content, scope, and revision timeline."
        />
      ) : null}

      {!loading && !error && observation ? (
        <>
          <div className="rounded-[1.5rem] border border-slate-900/8 bg-white px-5 py-5 dark:border-white/8 dark:bg-white/4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-2xl font-semibold text-slate-950 dark:text-slate-50">
                    {observation.title || "Untitled observation"}
                  </h2>
                  <StatusBadge status="pending" label={toLabelCase(observation.scope)} />
                  <StatusBadge
                    status={observation.isDeleted ? "failed" : "active"}
                    label={toLabelCase(observation.type)}
                  />
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                {observation.topic ? <StatusBadge status="pending" label={`Topic ${observation.topic}`} /> : null}
                {observation.toolName ? <StatusBadge status="pending" label={`Tool ${observation.toolName}`} /> : null}
              </div>
            </div>

            <div className="mt-4 rounded-[1.25rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 dark:border-white/8">
              <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                Captured content
              </p>
              <p className="mt-3 whitespace-pre-wrap text-sm leading-7 text-slate-700 dark:text-slate-200">
                {observation.content}
              </p>
            </div>
          </div>

          <div className="grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
            <div className="rounded-[1.5rem] border border-slate-900/8 bg-white px-5 py-5 dark:border-white/8 dark:bg-white/4">
              <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Linked scope</p>
              <div className="mt-4">
                <KeyValueGrid
                  columns={1}
                  items={[
                    { label: "Observation ID", value: observation.id },
                    { label: "Company", value: observation.companyId ?? "None" },
                    { label: "Operation", value: observation.operationId ?? "None" },
                    { label: "Session", value: observation.sessionId ?? "None" },
                    { label: "Department", value: observation.departmentId ?? "None" },
                    { label: "Chunk", value: observation.chunkId ?? "None" },
                  ]}
                />
              </div>
            </div>

            <div className="rounded-[1.5rem] border border-slate-900/8 bg-white px-5 py-5 dark:border-white/8 dark:bg-white/4">
              <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Timeline</p>
              <div className="mt-4 space-y-4">
                {[
                  { label: "Recorded", value: observation.createdAt },
                  { label: "Updated", value: observation.updatedAt },
                  { label: "Last seen", value: observation.lastSeenAt },
                  ...(observation.deletedAt ? [{ label: "Deleted", value: observation.deletedAt }] : []),
                ].map((item, index, items) => (
                  <div key={`${item.label}-${item.value}`} className="flex gap-3">
                    <div className="flex flex-col items-center">
                      <span className="mt-1 h-2.5 w-2.5 rounded-full bg-slate-950 dark:bg-slate-100" />
                      {index < items.length - 1 ? (
                        <span className="mt-2 h-full w-px bg-slate-900/10 dark:bg-white/10" />
                      ) : null}
                    </div>
                    <div className="pb-5">
                      <p className="text-sm font-medium text-slate-950 dark:text-slate-50">{item.label}</p>
                      <p className="text-sm text-slate-600 dark:text-slate-300">{formatDateTime(item.value)}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}
