import { useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import { ArrowRight, BellRing, BrainCircuit, Building2, HandCoins, ShieldCheck, Waypoints } from "lucide-react";

import { Button, Badge } from "@/components/ui";
import { useAuth } from "@/contexts/AuthContext";

const surfaces = [
  {
    icon: BrainCircuit,
    title: "Company operations",
    description:
      "Operate AI-driven companies with clear objectives, departments, and operating controls from one shell.",
  },
  {
    icon: Waypoints,
    title: "Operation visibility",
    description:
      "Follow live company work across departments and skills with summaries first and technical detail on demand.",
  },
  {
    icon: BellRing,
    title: "Approvals and decisions",
    description: "Review consequential decisions with context, expected impact, and edit-before-approve controls.",
  },
  {
    icon: HandCoins,
    title: "Usage and budget",
    description:
      "Track operating usage, spend, and financial posture like a real company system instead of a chat product.",
  },
];

const systemRows = [
  {
    label: "Companies operating",
    value: "14",
    note: "3 need attention",
  },
  {
    label: "Operations in progress",
    value: "38",
    note: "6 blocked on approval",
  },
  {
    label: "Spend today",
    value: "$482",
    note: "12% above baseline",
  },
  {
    label: "Memory topics",
    value: "27",
    note: "retrieval healthy",
  },
];

export default function Home() {
  const router = useRouter();
  const { replace } = router;
  const { isAuthenticated } = useAuth();

  useEffect(() => {
    if (!isAuthenticated) {
      return;
    }
    void replace("/companies");
  }, [isAuthenticated, replace]);

  if (isAuthenticated) {
    return (
      <div className="flex min-h-screen items-center justify-center px-4">
        <div className="rounded-[1.7rem] border border-zinc-900/10 bg-white/80 p-8 text-center shadow-[0_30px_90px_-50px_rgba(15,23,42,0.45)] backdrop-blur-xl dark:border-white/10 dark:bg-zinc-950/60">
          <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-500 dark:text-zinc-400">ForgeGraph</p>
          <h1
            className="mt-3 text-3xl font-semibold tracking-tight text-zinc-950 dark:text-zinc-50"
            style={{ fontFamily: "var(--font-serif)" }}
          >
            Opening the company workspace
          </h1>
          <p className="mt-3 text-sm leading-7 text-zinc-600 dark:text-zinc-300">
            ForgeGraph opens on the company workspace first. Advanced operating-model editing stays available
            separately.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b border-zinc-900/8 bg-[color-mix(in_srgb,var(--background)_80%,transparent)] backdrop-blur-2xl dark:border-white/8">
        <div className="mx-auto flex w-full max-w-[1380px] items-center justify-between p-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-3">
            <div className="flex size-10 items-center justify-center rounded-2xl bg-zinc-950 text-white dark:bg-zinc-100 dark:text-zinc-950">
              <BrainCircuit className="size-5" />
            </div>
            <div>
              <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-500 dark:text-zinc-400">ForgeGraph</p>
              <p className="text-sm font-semibold text-zinc-950 dark:text-zinc-50">AI Company OS</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {isAuthenticated ? (
              <Button asChild className="rounded-full">
                <Link href="/companies">Open companies</Link>
              </Button>
            ) : (
              <>
                <Button asChild variant="ghost" className="rounded-full">
                  <Link href="/login">Sign in</Link>
                </Button>
                <Button asChild className="rounded-full">
                  <Link href="/register">Start operating</Link>
                </Button>
              </>
            )}
          </div>
        </div>
      </header>

      <main>
        <section className="px-4 pb-16 pt-16 sm:px-6 lg:px-8 lg:pb-24 lg:pt-24">
          <div className="mx-auto grid w-full max-w-[1380px] gap-12 xl:grid-cols-[1.05fr_0.95fr] xl:items-center">
            <div>
              <Badge
                variant="outline"
                className="rounded-full border-zinc-900/10 bg-white/70 px-4 py-1.5 text-[11px] uppercase tracking-[0.2em] dark:border-white/10 dark:bg-white/5"
              >
                AI company operating system
              </Badge>
              <h1
                className="mt-6 max-w-4xl text-5xl font-semibold tracking-tight text-zinc-950 sm:text-6xl lg:text-7xl dark:text-zinc-50"
                style={{ fontFamily: "var(--font-serif)" }}
              >
                Create and operate AI-driven companies that do real work.
              </h1>
              <p className="mt-6 max-w-2xl text-lg leading-8 text-zinc-600 dark:text-zinc-300">
                ForgeGraph is not a chatbot and not an advanced editor first. It is a company workspace for objectives,
                departments, operations, approvals, deliverables, and operating controls.
              </p>
              <div className="mt-8 flex flex-col gap-3 sm:flex-row">
                <Button asChild size="lg" className="rounded-full px-7">
                  <Link href={isAuthenticated ? "/companies" : "/register"}>
                    {isAuthenticated ? "Open companies" : "Create a company"}
                    <ArrowRight className="size-4" />
                  </Link>
                </Button>
                <Button asChild size="lg" variant="outline" className="rounded-full px-7">
                  <Link href="/companies/new">
                    Open company builder
                    <Building2 className="size-4" />
                  </Link>
                </Button>
              </div>
            </div>

            <div className="rounded-[2rem] border border-zinc-900/10 bg-white/80 p-5 shadow-[0_40px_120px_-60px_rgba(15,23,42,0.45)] backdrop-blur-xl dark:border-white/10 dark:bg-zinc-950/60">
              <div className="grid gap-4 md:grid-cols-2">
                {systemRows.map((row) => (
                  <div
                    key={row.label}
                    className="rounded-[1.4rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8"
                  >
                    <p className="text-[11px] uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">
                      {row.label}
                    </p>
                    <p className="mt-3 text-3xl font-semibold tracking-tight text-zinc-950 dark:text-zinc-50">
                      {row.value}
                    </p>
                    <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-300">{row.note}</p>
                  </div>
                ))}
              </div>

              <div className="mt-5 rounded-[1.6rem] border border-zinc-900/8 bg-zinc-950 p-5 text-zinc-100 dark:border-white/8 dark:bg-white/8">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="text-[11px] uppercase tracking-[0.18em] text-zinc-400">Pending decisions</p>
                    <p className="mt-2 text-xl font-semibold">6 approvals require human review</p>
                    <p className="mt-2 text-sm leading-6 text-zinc-300">
                      Client Success wants to issue 14 enterprise refunds. Finance policy requires operator approval.
                    </p>
                  </div>
                  <ShieldCheck className="mt-1 size-5 text-zinc-300" />
                </div>
                <div className="mt-4 flex flex-wrap gap-2">
                  <Button size="sm" className="rounded-full bg-white text-zinc-950 hover:bg-zinc-200">
                    Approve
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className="rounded-full border-white/15 bg-transparent text-white hover:bg-white/10"
                  >
                    Reject
                  </Button>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="px-4 pb-16 sm:px-6 lg:px-8 lg:pb-24">
          <div className="mx-auto w-full max-w-[1380px]">
            <div className="max-w-3xl">
              <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-500 dark:text-zinc-400">Core surfaces</p>
              <h2
                className="mt-3 text-4xl font-semibold tracking-tight text-zinc-950 dark:text-zinc-50"
                style={{ fontFamily: "var(--font-serif)" }}
              >
                A clear command center for operating AI-driven companies.
              </h2>
            </div>
            <div className="mt-8 grid gap-4 lg:grid-cols-4">
              {surfaces.map((surface) => {
                const Icon = surface.icon;
                return (
                  <div
                    key={surface.title}
                    className="rounded-[1.7rem] border border-zinc-900/10 bg-white/78 p-5 shadow-[0_24px_80px_-60px_rgba(15,23,42,0.4)] dark:border-white/10 dark:bg-zinc-950/55"
                  >
                    <div className="flex size-11 items-center justify-center rounded-2xl border border-zinc-900/10 bg-[var(--panel-muted)] dark:border-white/10">
                      <Icon className="size-5 text-zinc-900 dark:text-zinc-100" />
                    </div>
                    <h3 className="mt-4 text-lg font-semibold text-zinc-950 dark:text-zinc-50">{surface.title}</h3>
                    <p className="mt-3 text-sm leading-7 text-zinc-600 dark:text-zinc-300">{surface.description}</p>
                  </div>
                );
              })}
            </div>
          </div>
        </section>

        <section className="px-4 pb-20 sm:px-6 lg:px-8">
          <div className="mx-auto grid w-full max-w-[1380px] gap-6 xl:grid-cols-[0.95fr_1.05fr]">
            <div className="rounded-[1.9rem] border border-zinc-900/10 bg-white/78 p-6 dark:border-white/10 dark:bg-zinc-950/55">
              <p className="text-[11px] uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">
                Company-first design
              </p>
              <ul className="mt-4 space-y-4 text-sm leading-7 text-zinc-700 dark:text-zinc-200">
                <li>Companies are primary. Operating models are secondary.</li>
                <li>Operations, approvals, deliverables, and controls are visible without reading logs.</li>
                <li>Technical detail remains available, but only when the user chooses advanced mode.</li>
                <li>Time, status, and history stay visible across every company surface.</li>
              </ul>
            </div>

            <div className="rounded-[1.9rem] border border-zinc-900/10 bg-zinc-950 p-6 text-zinc-100 dark:border-white/10 dark:bg-white/8">
              <p className="text-[11px] uppercase tracking-[0.18em] text-zinc-400">Advanced mode</p>
              <h3 className="mt-4 text-2xl font-semibold" style={{ fontFamily: "var(--font-serif)" }}>
                Operating models still exist, but they no longer define the product.
              </h3>
              <p className="mt-4 max-w-2xl text-sm leading-7 text-zinc-300">
                Advanced editing remains available for authoring and revisions. The default product surface is the
                company workspace, followed by command ops, approvals, knowledge, and usage.
              </p>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
