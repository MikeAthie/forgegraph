import type { MemoryObservation } from "@/lib/api";
import { Badge, Card, CardContent, CardHeader, CardTitle, EmptyState, Separator, Spinner } from "@/components/ui";

const formatDateTime = (value: string | null) => {
  if (!value) {
    return "Not recorded";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
};

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

const MetadataRow = ({ label, value }: { label: string; value: string | null }) => (
  <div className="flex items-center justify-between gap-4 rounded-xl border border-border/50 bg-background/70 px-3 py-2">
    <span className="text-xs uppercase tracking-[0.2em] text-muted-foreground">{label}</span>
    <span className="max-w-[60%] truncate text-right text-sm text-foreground">{value || "—"}</span>
  </div>
);

interface MemoryObservationDetailPanelProps {
  error: string | null;
  loading: boolean;
  observation: MemoryObservation | null;
}

export function MemoryObservationDetailPanel({ error, loading, observation }: MemoryObservationDetailPanelProps) {
  const timelineItems = observation
    ? [
        { label: "Recorded", value: observation.created_at },
        { label: "Updated", value: observation.updated_at },
        { label: "Last seen", value: observation.last_seen_at },
        ...(observation.deleted_at ? [{ label: "Deleted", value: observation.deleted_at }] : []),
      ]
    : [];

  return (
    <Card className="border-border/50 bg-card/70 shadow-sm backdrop-blur-sm">
      <CardHeader className="gap-3">
        <Badge variant="outline" className="w-fit border-amber-500/30 text-amber-700 dark:text-amber-300">
          Detail
        </Badge>
        <CardTitle className="text-xl font-semibold tracking-tight">Observation dossier</CardTitle>
        <p className="max-w-lg text-sm text-muted-foreground">
          Inspect the full record, linked scope identifiers, and timeline of revisions that shaped this memory.
        </p>
      </CardHeader>

      <CardContent>
        {loading ? (
          <div className="flex min-h-96 items-center justify-center gap-3 rounded-2xl border border-dashed border-border/60 bg-muted/20">
            <Spinner size="md" />
            <span className="text-sm text-muted-foreground">Loading observation detail…</span>
          </div>
        ) : null}

        {!loading && error ? (
          <div className="rounded-2xl border border-rose-500/30 bg-rose-500/8 px-4 py-4 text-sm text-rose-700 dark:text-rose-300">
            {error}
          </div>
        ) : null}

        {!loading && !error && !observation ? (
          <EmptyState
            title="Pick an observation"
            description="Select any item from the ledger to inspect its content, scope, and revision timeline."
            className="min-h-96 rounded-2xl border border-dashed border-border/60 bg-muted/20"
          />
        ) : null}

        {!loading && !error && observation ? (
          <div className="space-y-5">
            <div className="rounded-3xl border border-border/50 bg-background/80 p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="space-y-2">
                  <p className="text-xs uppercase tracking-[0.28em] text-muted-foreground">
                    {toLabelCase(observation.scope)}
                  </p>
                  <h2 className="text-2xl font-semibold tracking-tight text-foreground">
                    {observation.title || "Untitled observation"}
                  </h2>
                </div>
                <div className="flex flex-wrap justify-end gap-2">
                  <Badge variant="outline">{toLabelCase(observation.type)}</Badge>
                  {observation.is_deleted ? <Badge variant="destructive">Deleted</Badge> : null}
                </div>
              </div>

              <div className="mt-4 flex flex-wrap gap-2 text-xs text-muted-foreground">
                {observation.topic_key ? (
                  <span className="rounded-full border border-border/60 px-2 py-1">Topic {observation.topic_key}</span>
                ) : null}
                {observation.tool_name ? (
                  <span className="rounded-full border border-border/60 px-2 py-1">Tool {observation.tool_name}</span>
                ) : null}
                <span className="rounded-full border border-border/60 px-2 py-1">
                  Revisions {observation.revision_count}
                </span>
                <span className="rounded-full border border-border/60 px-2 py-1">
                  Duplicates {observation.duplicate_count}
                </span>
              </div>

              <Separator className="my-5" />

              <div className="rounded-2xl border border-border/50 bg-muted/20 px-4 py-4">
                <p className="text-xs uppercase tracking-[0.24em] text-muted-foreground">Captured content</p>
                <p className="mt-3 whitespace-pre-wrap text-sm leading-7 text-foreground">{observation.content}</p>
              </div>
            </div>

            <div className="grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
              <div className="space-y-3 rounded-3xl border border-border/50 bg-background/70 p-4">
                <p className="text-xs uppercase tracking-[0.24em] text-muted-foreground">Linked scope</p>
                <MetadataRow label="Observation ID" value={observation.id} />
                <MetadataRow label="Graph" value={observation.graph_id} />
                <MetadataRow label="Run" value={observation.run_id} />
                <MetadataRow label="Session" value={observation.session_id} />
                <MetadataRow label="Agent" value={observation.agent_id} />
                <MetadataRow label="Chunk" value={observation.memory_chunk_id} />
              </div>

              <div className="space-y-3 rounded-3xl border border-border/50 bg-background/70 p-4">
                <p className="text-xs uppercase tracking-[0.24em] text-muted-foreground">Timeline</p>
                <div className="space-y-4">
                  {timelineItems.map((item, index) => (
                    <div key={`${item.label}-${item.value}`} className="flex gap-3">
                      <div className="flex flex-col items-center">
                        <span className="mt-1 h-2.5 w-2.5 rounded-full bg-sky-500" />
                        {index < timelineItems.length - 1 ? <span className="mt-2 h-full w-px bg-border" /> : null}
                      </div>
                      <div className="pb-5">
                        <p className="text-sm font-medium text-foreground">{item.label}</p>
                        <p className="text-sm text-muted-foreground">{formatDateTime(item.value)}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
