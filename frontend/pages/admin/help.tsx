import Link from "next/link";
import { ArrowRight, BookOpenText, ShieldCheck } from "lucide-react";

import DashboardLayout from "../../components/DashboardLayout";
import ProtectedRoute from "../../components/ProtectedRoute";
import {
  Alert,
  AlertDescription,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui";

const GUIDE_SECTIONS = [
  {
    title: "Cloud vs self-hosted",
    description:
      "Cloud mode can deny exec-tool behavior even when a graph requests it. Self-hosted mode still follows package and tenant policy restrictions.",
  },
  {
    title: "Retention expectations",
    description:
      "Runs, logs, audit logs, and usage follow the tenant retention policy. Curated observations and indexed chunks currently require explicit operator review and cleanup.",
  },
  {
    title: "Memory triage",
    description:
      "If a memory-backed run degrades, check indexing backlog, Redis and gRPC health, then inspect the observation trail before assuming prompt quality is the issue.",
  },
  {
    title: "Support-safe exports",
    description:
      "Use the admin operations screen for tenant-scoped exports instead of raw database access. That keeps support work aligned with API redaction and access controls.",
  },
];

export default function AdminHelpPage() {
  return (
    <ProtectedRoute>
      <DashboardLayout>
        <div className="mx-auto flex max-w-5xl flex-col gap-6 py-8">
          <section className="rounded-[2rem] border border-border/50 bg-card/80 p-6 shadow-lg backdrop-blur-sm sm:p-8">
            <div className="flex flex-col gap-4">
              <div className="inline-flex w-fit items-center gap-2 rounded-full border border-border/60 px-3 py-1 text-xs uppercase tracking-[0.2em] text-muted-foreground">
                <BookOpenText className="size-4" aria-hidden="true" />
                Operator Help
              </div>
              <div className="max-w-3xl">
                <h1 className="text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
                  The short support guide for P2.
                </h1>
                <p className="mt-3 text-sm leading-7 text-muted-foreground sm:text-base">
                  This page turns the shipped P2 behavior into one operator-facing reference so admins do not need to
                  reconstruct the product model from code.
                </p>
              </div>
              <Alert className="max-w-3xl border-sky-500/30 bg-sky-500/10 text-sky-800 dark:text-sky-100">
                <ShieldCheck className="size-4" />
                <AlertDescription>
                  The deeper written references live in the repo docs under <code>docs/ops</code>. This page is the
                  product-facing version of those notes.
                </AlertDescription>
              </Alert>
            </div>
          </section>

          <section className="grid gap-4 md:grid-cols-2">
            {GUIDE_SECTIONS.map((section) => (
              <Card key={section.title} className="border-border/60 bg-card/70 backdrop-blur-sm">
                <CardHeader>
                  <CardTitle>{section.title}</CardTitle>
                  <CardDescription>{section.description}</CardDescription>
                </CardHeader>
              </Card>
            ))}
          </section>

          <Card className="border-border/60 bg-card/70 backdrop-blur-sm">
            <CardHeader>
              <CardTitle>Where to go next</CardTitle>
              <CardDescription>
                These links match the P2 operator walkthrough instead of sending admins to scattered pages.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-wrap gap-3">
              <Button asChild variant="outline">
                <Link href="/admin/operations">
                  Policies and retention
                  <ArrowRight className="ml-2 size-4" aria-hidden="true" />
                </Link>
              </Button>
              <Button asChild variant="outline">
                <Link href="/admin/billing">
                  Billing and entitlements
                  <ArrowRight className="ml-2 size-4" aria-hidden="true" />
                </Link>
              </Button>
              <Button asChild variant="outline">
                <Link href="/admin/audit-logs">
                  Audit trail
                  <ArrowRight className="ml-2 size-4" aria-hidden="true" />
                </Link>
              </Button>
            </CardContent>
          </Card>
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
