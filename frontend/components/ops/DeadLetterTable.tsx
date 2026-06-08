import { CheckCircle2, RotateCcw } from "lucide-react";

import { StatusBadge } from "@/components/os/operations-ui";
import { formatDateTime } from "@/components/os/operations-format";
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
      <div className="rounded-[1.25rem] border border-zinc-900/8 bg-[var(--panel-muted)] px-5 py-8 text-sm text-zinc-500 dark:border-white/8 dark:text-zinc-400">
        No operator-visible dead letters are currently active.
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-[1.25rem] border border-zinc-900/8 dark:border-white/8">
      <div className="grid grid-cols-[1fr_8rem_9rem_13rem] gap-3 border-b border-zinc-900/8 bg-[var(--panel-muted)] px-4 py-3 text-[11px] uppercase tracking-[0.16em] text-zinc-500 dark:border-white/8 dark:text-zinc-400 max-lg:hidden">
        <span>Failure</span>
        <span>Status</span>
        <span>Kind</span>
        <span className="text-right">Actions</span>
      </div>
      <div className="divide-y divide-zinc-900/8 dark:divide-white/8">
        {items.map((item) => {
          const selected = item.id === selectedId;
          const busy = actionId === item.id;
          const canReplay = item.actions.includes("replay");
          const canResolve = item.actions.includes("resolve");
          return (
            <div
              key={item.id}
              className={cn(
                "grid grid-cols-[1fr_8rem_9rem_13rem] gap-3 p-4 text-sm max-lg:grid-cols-1",
                selected ? "bg-zinc-950 text-white dark:bg-white dark:text-zinc-950" : "bg-white/70 dark:bg-white/5",
              )}
            >
              <button type="button" onClick={() => onSelect?.(item)} className="min-w-0 text-left">
                <p className="truncate font-semibold">{item.title || item.id}</p>
                <p
                  className={cn(
                    "mt-1 line-clamp-2 text-sm leading-5",
                    selected ? "text-white/75 dark:text-zinc-700" : "text-zinc-500 dark:text-zinc-400",
                  )}
                >
                  {item.reason || item.last_error || "No failure reason was recorded."}
                </p>
                <p
                  className={cn(
                    "mt-2 text-xs",
                    selected ? "text-white/65 dark:text-zinc-600" : "text-zinc-500 dark:text-zinc-400",
                  )}
                >
                  Last seen {formatDateTime(item.last_seen_at)} · {item.id}
                </p>
              </button>
              <div className="flex items-start">
                <StatusBadge status={item.status} />
              </div>
              <div className="text-sm capitalize text-zinc-600 dark:text-zinc-300">{item.kind.replace(/_/g, " ")}</div>
              <div className="flex justify-end gap-2 max-lg:justify-start">
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={!canReplay || busy}
                  onClick={() => onReplay?.(item)}
                >
                  <RotateCcw className="size-4" />
                  Replay
                </Button>
                <Button type="button" size="sm" disabled={!canResolve || busy} onClick={() => onResolve?.(item)}>
                  <CheckCircle2 className="size-4" />
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
