import { memo } from "react";
import type { NodeProps } from "@xyflow/react";
import { StickyNote } from "lucide-react";

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
      className={`
        relative min-w-[180px] max-w-[260px] rounded-lg border-2 border-yellow-300 bg-yellow-50 p-3 shadow-sm
        ${selected ? "ring-2 ring-primary ring-offset-2" : ""}
      `}
    >
      <div className="flex items-center gap-2 text-yellow-800 mb-2">
        <StickyNote aria-hidden="true" className="w-4 h-4" />
        <span className="text-[11px] font-semibold uppercase tracking-wide">Note</span>
      </div>

      <div className="text-sm font-medium text-yellow-900 truncate">{title}</div>

      <div className="mt-2 text-xs text-yellow-900 whitespace-pre-wrap break-words line-clamp-6">
        {text ? (
          text
        ) : (
          <span className="text-yellow-800/70 italic">Add a note in the inspector…</span>
        )}
      </div>
    </div>
  );
}

export const NoteNode = memo(NoteNodeComponent);

