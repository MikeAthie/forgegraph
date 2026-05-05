import { RadioTower } from "lucide-react";

import { KeyValueGrid, StatusBadge, formatDateTime } from "@/components/os/operations-ui";
import type { OpsEventSpool, OpsRuntimeIntentLag } from "@/lib/api";

type EventSpoolPanelProps = {
  spool: OpsEventSpool | null | undefined;
  runtime: OpsRuntimeIntentLag | null | undefined;
};

export function EventSpoolPanel({ spool, runtime }: EventSpoolPanelProps) {
  return (
    <div className="space-y-4">
      <KeyValueGrid
        columns={3}
        items={[
          {
            label: "Domain events",
            value: (spool?.domain_events.count ?? 0).toLocaleString(),
          },
          {
            label: "State feed version",
            value: (spool?.state_feed_events.latest_state_version ?? 0).toLocaleString(),
          },
          {
            label: "Runtime backlog",
            value: (runtime?.backlog ?? 0).toLocaleString(),
          },
        ]}
      />

      <div className="grid gap-4 xl:grid-cols-2">
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-950 dark:text-slate-50">
            <RadioTower className="h-4 w-4" />
            Recent domain events
          </div>
          <div className="space-y-2">
            {(spool?.domain_events.recent ?? []).slice(0, 6).map((event) => (
              <div
                key={event.id}
                className="rounded-[1.1rem] border border-slate-900/8 bg-[var(--panel-muted)] px-4 py-3 dark:border-white/8"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-slate-950 dark:text-slate-50">{event.event_type}</p>
                    <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                      seq {event.sequence.toLocaleString()} · {formatDateTime(event.occurred_at)}
                    </p>
                  </div>
                  <StatusBadge status="fresh" label={event.aggregate_type} />
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="space-y-2">
          <div className="text-sm font-semibold text-slate-950 dark:text-slate-50">Runtime intent transport</div>
          <KeyValueGrid
            columns={2}
            items={[
              { label: "Pending", value: (runtime?.pending ?? 0).toLocaleString() },
              { label: "Lag", value: (runtime?.lag ?? 0).toLocaleString() },
              { label: "Dead letters", value: (runtime?.dead_letter_count ?? 0).toLocaleString() },
              { label: "Source", value: runtime?.source ?? "unavailable" },
            ]}
          />
          {runtime?.error ? (
            <p className="rounded-[1.1rem] border border-rose-800/15 bg-rose-50 px-4 py-3 text-sm text-rose-900 dark:border-rose-200/20 dark:bg-rose-500/10 dark:text-rose-100">
              {runtime.error}
            </p>
          ) : null}
        </div>
      </div>
    </div>
  );
}
