import type { HTMLAttributes, ReactNode } from "react";
import { AlertTriangle, ArrowUpRight, CheckCircle2, Clock3, Dot, PauseCircle, Wallet } from "lucide-react";

import { Badge, Button, Card, CardContent, CardHeader, CardTitle } from "@/components/ui";
import { cn } from "@/lib/utils";

const USD_FORMATTER = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 2,
});
const USD_INTEGER_FORMATTER = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});
const COMPACT_NUMBER_FORMATTER = new Intl.NumberFormat("en-US", {
  notation: "compact",
  maximumFractionDigits: 1,
});

export const formatCurrency = (value: number) => (value >= 100 ? USD_INTEGER_FORMATTER : USD_FORMATTER).format(value);

export const formatCompactNumber = (value: number) => COMPACT_NUMBER_FORMATTER.format(value);

export const formatDateTime = (value: string | null | undefined) => {
  if (!value) {
    return "Not available";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString();
};

export const formatDuration = (value: number | null | undefined) => {
  if (value === null || value === undefined) {
    return "Pending";
  }
  if (value < 1_000) {
    return `${value}ms`;
  }

  const seconds = Math.floor(value / 1_000);
  if (seconds < 60) {
    return `${seconds}s`;
  }

  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  if (minutes < 60) {
    return `${minutes}m ${remainingSeconds}s`;
  }

  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return `${hours}h ${remainingMinutes}m`;
};

export const statusTone = (status: string) => {
  switch (status.toLowerCase()) {
    case "running":
    case "active":
    case "approved":
    case "succeeded":
    case "success":
    case "resolved":
    case "fresh":
      return "emerald";
    case "idle":
    case "created":
    case "claimed":
    case "queued":
    case "pending":
    case "waiting":
      return "slate";
    case "paused":
    case "waiting_for_decision":
    case "retry_scheduled":
    case "stale":
    case "rebuilding":
      return "amber";
    case "error":
    case "failed":
    case "dead_lettered":
    case "cancelled":
    case "rejected":
    case "attention":
    case "degraded":
      return "rose";
    default:
      return "slate";
  }
};

const toneClasses: Record<string, string> = {
  emerald:
    "border-emerald-800/15 bg-emerald-50 text-emerald-900 dark:border-emerald-200/20 dark:bg-emerald-500/12 dark:text-emerald-100",
  slate: "border-zinc-900/10 bg-white/90 text-zinc-700 dark:border-white/10 dark:bg-white/6 dark:text-zinc-200",
  amber:
    "border-amber-800/15 bg-amber-50 text-amber-900 dark:border-amber-200/20 dark:bg-amber-500/10 dark:text-amber-100",
  rose: "border-rose-800/15 bg-rose-50 text-rose-900 dark:border-rose-200/20 dark:bg-rose-500/10 dark:text-rose-100",
  cyan: "border-cyan-800/15 bg-cyan-50 text-cyan-900 dark:border-cyan-200/20 dark:bg-cyan-500/10 dark:text-cyan-100",
};

const toneDotClasses: Record<string, string> = {
  emerald: "bg-emerald-500",
  slate: "bg-zinc-400 dark:bg-zinc-500",
  amber: "bg-amber-500",
  rose: "bg-rose-500",
  cyan: "bg-cyan-500",
};

export function StatusBadge({ status, label }: { status: string; label?: string }) {
  const tone = statusTone(status);
  return (
    <Badge
      variant="outline"
      className={cn("gap-2 rounded-full px-2.5 py-1 text-[11px] font-medium", toneClasses[tone])}
    >
      <span className={cn("size-1.5 rounded-full", toneDotClasses[tone])} />
      {label ?? status}
    </Badge>
  );
}

export function MetricCard({
  eyebrow,
  value,
  delta,
  icon,
  tone = "slate",
  className,
}: {
  eyebrow: string;
  value: string;
  delta?: string;
  icon?: ReactNode;
  tone?: "slate" | "emerald" | "amber" | "rose" | "cyan";
  className?: string;
}) {
  return (
    <Card
      className={cn(
        "rounded-[1.75rem] border-zinc-900/12 bg-white/92 shadow-[0_28px_80px_-46px_rgba(15,23,42,0.35)] dark:border-white/10 dark:bg-zinc-950/72",
        className,
      )}
    >
      <CardContent className="flex items-start justify-between gap-4 p-5">
        <div>
          <p className="text-[11px] uppercase tracking-[0.24em] text-zinc-500 dark:text-zinc-400">{eyebrow}</p>
          <p className="mt-3 text-3xl font-semibold tracking-tight text-zinc-950 dark:text-zinc-50">{value}</p>
          {delta ? (
            <p className="mt-3 flex items-center gap-2 text-xs text-zinc-500 dark:text-zinc-400">
              <span className={cn("size-2 rounded-full", toneDotClasses[tone])} />
              {delta}
            </p>
          ) : null}
        </div>
        <div className={cn("flex size-11 items-center justify-center rounded-2xl border", toneClasses[tone])}>
          {icon}
        </div>
      </CardContent>
    </Card>
  );
}

export function Surface({ className, children, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <section
      className={cn(
        "rounded-[2rem] border border-zinc-900/10 bg-white/90 shadow-[0_32px_90px_-56px_rgba(15,23,42,0.32)] backdrop-blur-xl dark:border-white/10 dark:bg-zinc-950/70",
        className,
      )}
      {...props}
    >
      {children}
    </section>
  );
}

export function SectionHeader({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-4 border-b border-zinc-900/8 p-6 dark:border-white/8 lg:flex-row lg:items-end lg:justify-between">
      <div className="min-w-0">
        {eyebrow ? (
          <p className="text-[11px] uppercase tracking-[0.28em] text-zinc-500 dark:text-zinc-400">{eyebrow}</p>
        ) : null}
        <h2
          className="mt-2 text-3xl font-semibold tracking-tight text-zinc-950 dark:text-zinc-50"
          style={{ fontFamily: "var(--font-serif)" }}
        >
          {title}
        </h2>
        {description ? (
          <p className="mt-3 max-w-3xl text-sm leading-7 text-zinc-600 dark:text-zinc-300">{description}</p>
        ) : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}

export function Panel({
  title,
  description,
  action,
  children,
  className,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <Surface className={className}>
      <div className="flex items-start justify-between gap-4 border-b border-zinc-900/8 px-6 py-5 dark:border-white/8">
        <div>
          <h3 className="text-sm font-semibold uppercase tracking-[0.14em] text-zinc-950 dark:text-zinc-50">{title}</h3>
          {description ? <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">{description}</p> : null}
        </div>
        {action ? <div className="shrink-0">{action}</div> : null}
      </div>
      <div className="px-6 py-5">{children}</div>
    </Surface>
  );
}

export function KeyValueGrid({
  items,
  columns = 2,
}: {
  items: Array<{ label: string; value: ReactNode }>;
  columns?: 1 | 2 | 3;
}) {
  return (
    <div
      className={cn("grid gap-3", columns === 1 ? "grid-cols-1" : columns === 2 ? "md:grid-cols-2" : "md:grid-cols-3")}
    >
      {items.map((item) => (
        <div
          key={item.label}
          className="rounded-[1.35rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8"
        >
          <p className="text-[11px] uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">{item.label}</p>
          <div className="mt-2 text-sm font-medium text-zinc-900 dark:text-zinc-100">{item.value}</div>
        </div>
      ))}
    </div>
  );
}

export function SelectionList<T>({
  items,
  selectedId,
  onSelect,
  empty,
  children,
}: {
  items: T[];
  selectedId: string | null;
  onSelect: (item: T) => void;
  empty: ReactNode;
  children: (item: T, state: { selected: boolean }) => ReactNode;
}) {
  if (items.length === 0) {
    return <div>{empty}</div>;
  }

  return (
    <div className="space-y-3">
      {items.map((item) => {
        const id = String((item as { id: string }).id);
        const selected = id === selectedId;

        return (
          <button
            key={id}
            type="button"
            onClick={() => onSelect(item)}
            className={cn(
              "w-full rounded-[1.25rem] border p-4 text-left transition-colors",
              selected
                ? "border-zinc-950 bg-zinc-950 text-white shadow-[0_24px_48px_-34px_rgba(15,23,42,0.85)] dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-950"
                : "border-zinc-900/8 bg-white hover:bg-[var(--panel-muted)] dark:border-white/8 dark:bg-white/5 dark:hover:bg-white/8",
            )}
          >
            {children(item, { selected })}
          </button>
        );
      })}
    </div>
  );
}

export function InspectorPanel({
  title,
  subtitle,
  sections,
}: {
  title: string;
  subtitle?: string;
  sections: Array<{ title: string; content: ReactNode }>;
}) {
  return (
    <div className="sticky top-[7.5rem] z-10 max-h-[calc(100vh-8.5rem)] space-y-4 overflow-y-auto overscroll-contain pb-1">
      <Surface className="overflow-hidden">
        <div className="border-b border-zinc-900/8 p-6 dark:border-white/8">
          <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-500 dark:text-zinc-400">Inspection</p>
          <h3 className="mt-3 text-xl font-semibold text-zinc-950 dark:text-zinc-50">{title}</h3>
          {subtitle ? <p className="mt-3 text-sm leading-6 text-zinc-600 dark:text-zinc-300">{subtitle}</p> : null}
        </div>
        <div className="space-y-5 p-6">
          {sections.map((section) => (
            <div key={section.title}>
              <p className="text-[11px] uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">
                {section.title}
              </p>
              <div className="mt-2 text-sm leading-6 text-zinc-700 dark:text-zinc-200">{section.content}</div>
            </div>
          ))}
        </div>
      </Surface>
    </div>
  );
}

export function TimelineList({
  items,
}: {
  items: Array<{
    id: string;
    title: string;
    detail: string;
    time?: string;
    tone?: "emerald" | "amber" | "rose" | "slate" | "cyan";
  }>;
}) {
  if (items.length === 0) {
    return (
      <EmptyBlock
        title="No recent activity"
        description="Events will appear here once work starts moving through the system."
      />
    );
  }

  return (
    <div className="space-y-4">
      {items.map((item) => (
        <div key={item.id} className="flex gap-3">
          <div className="flex flex-col items-center">
            <span className={cn("mt-1 size-2.5 rounded-full", toneDotClasses[item.tone ?? "slate"])} />
            <span className="mt-2 h-full w-px bg-zinc-900/10 dark:bg-white/10" />
          </div>
          <div className="min-w-0 pb-4">
            <div className="flex items-start justify-between gap-3">
              <p className="text-sm font-medium text-zinc-900 dark:text-zinc-50">{item.title}</p>
              {item.time ? <p className="text-xs text-zinc-500 dark:text-zinc-400">{item.time}</p> : null}
            </div>
            <p className="mt-1 text-sm leading-6 text-zinc-600 dark:text-zinc-300">{item.detail}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

export function EmptyBlock({ title, description }: { title: string; description: string }) {
  return (
    <div className="rounded-[1.25rem] border border-dashed border-zinc-900/12 bg-[var(--panel-muted)] px-5 py-8 text-center dark:border-white/12">
      <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">{title}</p>
      <p className="mt-2 text-sm leading-6 text-zinc-500 dark:text-zinc-400">{description}</p>
    </div>
  );
}

export function MicroExplanation({ children, className }: { children: ReactNode; className?: string }) {
  return <p className={cn("text-xs leading-5 text-zinc-500 dark:text-zinc-400", className)}>{children}</p>;
}

export function WhyBlock({
  title = "Why this?",
  reasons,
  className,
}: {
  title?: string;
  reasons: string[];
  className?: string;
}) {
  if (!reasons.length) {
    return null;
  }

  return (
    <div
      className={cn(
        "rounded-[1.35rem] border border-sky-800/12 bg-sky-50/80 p-4 dark:border-sky-200/15 dark:bg-sky-500/10",
        className,
      )}
    >
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-sky-800/80 dark:text-sky-100/75">
        {title}
      </p>
      <ul className="mt-3 space-y-2">
        {reasons.map((reason) => (
          <li key={reason} className="flex gap-2 text-sm leading-6 text-sky-950/85 dark:text-sky-50/85">
            <span className="mt-2 size-1.5 shrink-0 rounded-full bg-sky-500" />
            <span>{reason}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function TrendBar({
  value,
  total,
  tone = "slate",
}: {
  value: number;
  total: number;
  tone?: "emerald" | "amber" | "rose" | "slate" | "cyan";
}) {
  const width = total > 0 ? Math.max(6, Math.round((value / total) * 100)) : 0;

  return (
    <div className="h-2 rounded-full bg-zinc-900/8 dark:bg-white/8">
      <div className={cn("h-2 rounded-full", toneDotClasses[tone])} style={{ width: `${width}%` }} />
    </div>
  );
}

export const overviewIcons = {
  stable: <CheckCircle2 className="size-4" />,
  attention: <AlertTriangle className="size-4" />,
  paused: <PauseCircle className="size-4" />,
  timing: <Clock3 className="size-4" />,
  financial: <Wallet className="size-4" />,
  external: <ArrowUpRight className="size-4" />,
  separator: <Dot className="size-4" />,
};

function SecondaryActionLink({ children, href }: { children: ReactNode; href: string }) {
  return (
    <Button
      asChild
      variant="outline"
      className="rounded-full border-zinc-900/12 bg-white/80 px-4 dark:border-white/10 dark:bg-white/5"
    >
      <a href={href}>{children}</a>
    </Button>
  );
}
