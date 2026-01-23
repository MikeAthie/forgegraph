import { memo } from "react";
import type { NodeProps } from "@xyflow/react";
import { StickyNote } from "lucide-react";

import { cn } from "@/lib/utils";

interface NoteNodeData {
  label?: string;
  text?: string;
}

function NoteNodeComponent({ data, selected }: NodeProps) {
  const noteData = data as unknown as NoteNodeData;
  const title = noteData.label?.trim() ? noteData.label.trim() : "Note";
  const text = noteData.text?.trim() ? noteData.text : "";

  return (
    <div
      className={cn(
        "relative min-w-[180px] max-w-[260px] rounded-xl border border-border bg-card p-3 shadow-sm",
        selected && "ring-2 ring-primary ring-offset-2 ring-offset-background",
      )}
    >
      <div className="pointer-events-none absolute inset-x-0 top-0 h-1 rounded-t-xl bg-amber-500" />

      <div className="flex items-center gap-2 mb-2">
        <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/15 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-amber-800 dark:text-amber-300">
          <StickyNote aria-hidden="true" className="w-3.5 h-3.5" />
          Note
        </span>
      </div>

      <div className="text-sm font-semibold text-foreground truncate">{title}</div>

      <div className="mt-2 text-xs text-muted-foreground whitespace-pre-wrap break-words line-clamp-6">
        {text ? (
          <span className="text-foreground/90">{text}</span>
        ) : (
          <span className="italic">Add a note in the inspector…</span>
        )}
      </div>
    </div>
  );
}

export const NoteNode = memo(NoteNodeComponent);
