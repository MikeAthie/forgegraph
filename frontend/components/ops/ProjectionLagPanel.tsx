import { Activity } from "lucide-react";

import { KeyValueGrid, StatusBadge } from "@/components/os/operations-ui";
import { formatDateTime } from "@/components/os/operations-format";
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
        <div className="flex items-center gap-2 text-sm font-semibold text-zinc-950 dark:text-zinc-50">
          <Activity className="size-4" />
          Projection cursors
        </div>
        <div className="space-y-2">
          {(data?.cursors ?? []).map((cursor) => (
            <div
              key={cursor.projection_name}
              className="flex items-start justify-between gap-4 rounded-[1.1rem] border border-zinc-900/8 bg-[var(--panel-muted)] px-4 py-3 dark:border-white/8"
            >
              <div>
                <p className="text-sm font-medium text-zinc-950 dark:text-zinc-50">{cursor.projection_name}</p>
                <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
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
            <p className="rounded-[1.1rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 text-sm text-zinc-500 dark:border-white/8 dark:text-zinc-400">
              No projection cursor has been recorded for this organization yet.
            </p>
          ) : null}
        </div>
      </div>
    </div>
  );
}
