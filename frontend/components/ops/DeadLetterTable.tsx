import { CheckCircle2, RotateCcw } from "lucide-react";

import { StatusBadge, formatDateTime } from "@/components/os/operations-ui";
import { Button } from "@/components/ui";
import type { OpsDeadLetter } from "@/lib/api";
import { cn } from "@/lib/utils";

type DeadLetterTableProps = {
  items: OpsDeadLetter[];
  selectedId?: string | null;
  actionId?: string | null;
  onSelect?: (item: OpsDeadLetter) => void;
  onReplay?: (item: OpsDeadLetter) => void;
  onResolve?: (item: OpsDeadLetter) => void;
};

export function DeadLetterTable({ items, selectedId, actionId, onSelect, onReplay, onResolve }: DeadLetterTableProps) {
  if (items.length === 0) {
    return (
      <div className="rounded-[1.25rem] border border-slate-900/8 bg-[var(--panel-muted)] px-5 py-8 text-sm text-slate-500 dark:border-white/8 dark:text-slate-400">
        No operator-visible dead letters are currently active.
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-[1.25rem] border border-slate-900/8 dark:border-white/8">
      <div className="grid grid-cols-[1fr_8rem_9rem_13rem] gap-3 border-b border-slate-900/8 bg-[var(--panel-muted)] px-4 py-3 text-[11px] uppercase tracking-[0.16em] text-slate-500 dark:border-white/8 dark:text-slate-400 max-lg:hidden">
        <span>Failure</span>
        <span>Status</span>
        <span>Kind</span>
        <span className="text-right">Actions</span>
      </div>
      <div className="divide-y divide-slate-900/8 dark:divide-white/8">
        {items.map((item) => {
          const selected = item.id === selectedId;
          const busy = actionId === item.id;
          const canReplay = item.actions.includes("replay");
          const canResolve = item.actions.includes("resolve");
          return (
            <div
              key={item.id}
              className={cn(
                "grid grid-cols-[1fr_8rem_9rem_13rem] gap-3 px-4 py-4 text-sm max-lg:grid-cols-1",
                selected ? "bg-slate-950 text-white dark:bg-white dark:text-slate-950" : "bg-white/70 dark:bg-white/5",
              )}
            >
              <button type="button" onClick={() => onSelect?.(item)} className="min-w-0 text-left">
                <p className="truncate font-semibold">{item.title || item.id}</p>
                <p
                  className={cn(
                    "mt-1 line-clamp-2 text-sm leading-5",
                    selected ? "text-white/75 dark:text-slate-700" : "text-slate-500 dark:text-slate-400",
                  )}
                >
                  {item.reason || item.last_error || "No failure reason was recorded."}
                </p>
                <p
                  className={cn(
                    "mt-2 text-xs",
                    selected ? "text-white/65 dark:text-slate-600" : "text-slate-500 dark:text-slate-400",
                  )}
                >
                  Last seen {formatDateTime(item.last_seen_at)} · {item.id}
                </p>
              </button>
              <div className="flex items-start">
                <StatusBadge status={item.status} />
              </div>
              <div className="text-sm capitalize text-slate-600 dark:text-slate-300">
                {item.kind.replace(/_/g, " ")}
              </div>
              <div className="flex justify-end gap-2 max-lg:justify-start">
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={!canReplay || busy}
                  onClick={() => onReplay?.(item)}
                >
                  <RotateCcw className="h-4 w-4" />
                  Replay
                </Button>
                <Button type="button" size="sm" disabled={!canResolve || busy} onClick={() => onResolve?.(item)}>
                  <CheckCircle2 className="h-4 w-4" />
                  Resolve
                </Button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
