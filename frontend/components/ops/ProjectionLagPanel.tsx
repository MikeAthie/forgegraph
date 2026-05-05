import { Activity } from "lucide-react";

import { KeyValueGrid, StatusBadge, formatDateTime } from "@/components/os/operations-ui";
import type { OpsProjectionLag } from "@/lib/api";

type ProjectionLagPanelProps = {
  data: OpsProjectionLag | null | undefined;
};

export function ProjectionLagPanel({ data }: ProjectionLagPanelProps) {
  const projection = data?.projection ?? null;
  const lagSeconds = typeof projection?.lag_seconds === "number" ? projection.lag_seconds : 0;

  return (
    <div className="space-y-4">
      <KeyValueGrid
        columns={3}
        items={[
          {
            label: "Projection status",
            value: <StatusBadge status={projection?.status ?? "unknown"} />,
          },
          {
            label: "Projection lag",
            value: `${Math.round(lagSeconds * 10) / 10}s`,
          },
          {
            label: "Last sequence",
            value: (projection?.last_sequence ?? 0).toLocaleString(),
          },
        ]}
      />

      <div className="space-y-2">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-950 dark:text-slate-50">
          <Activity className="h-4 w-4" />
          Projection cursors
        </div>
        <div className="space-y-2">
          {(data?.cursors ?? []).map((cursor) => (
            <div
              key={cursor.projection_name}
              className="flex items-start justify-between gap-4 rounded-[1.1rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-3 dark:border-white/8"
            >
              <div>
                <p className="text-sm font-medium text-slate-950 dark:text-slate-50">{cursor.projection_name}</p>
                <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                  seq {cursor.last_sequence.toLocaleString()} · {formatDateTime(cursor.updated_at)}
                </p>
                {cursor.last_error ? (
                  <p className="mt-2 text-xs leading-5 text-rose-700 dark:text-rose-200">{cursor.last_error}</p>
                ) : null}
              </div>
              <StatusBadge status={cursor.status} />
            </div>
          ))}
          {(data?.cursors ?? []).length === 0 ? (
            <p className="rounded-[1.1rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-4 text-sm text-slate-500 dark:border-white/8 dark:text-slate-400">
              No projection cursor has been recorded for this organization yet.
            </p>
          ) : null}
        </div>
      </div>
    </div>
  );
}
