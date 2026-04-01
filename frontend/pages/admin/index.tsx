import Link from "next/link";
import {
  ArrowRight,
  BrainCircuit,
  Building2,
  FileSearch,
  KeyRound,
  ReceiptText,
  Scale,
  ShieldCheck,
  Store,
} from "lucide-react";

import DashboardLayout from "../../components/DashboardLayout";
import ProtectedRoute from "../../components/ProtectedRoute";
import { useAuth } from "../../contexts/AuthContext";
import {
  Alert,
  AlertDescription,
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui";

type GovernanceArea = {
  title: string;
  description: string;
  href: string;
  accessLabel: string;
  surfaceLabel: string;
  icon: typeof Building2;
};

const GOVERNANCE_AREAS: GovernanceArea[] = [
  {
    title: "Organization",
    description: "Members, roles, and tenant ownership. This is the source of truth for who can operate the workspace.",
    href: "/admin/organization",
    accessLabel: "All signed-in users",
    surfaceLabel: "Members and roles",
    icon: Building2,
  },
  {
    title: "Identity",
    description:
      "SSO and SCIM configuration for access and provisioning. This is where identity state becomes reviewable instead of implicit.",
    href: "/admin/sso",
    accessLabel: "Owner and admin",
    surfaceLabel: "SSO and SCIM",
    icon: KeyRound,
  },
  {
    title: "Billing",
    description:
      "Plan entitlements, quota, and budget guardrails. Use this when explaining commercial limits or blocked runtime behavior.",
    href: "/admin/billing",
    accessLabel: "Owner and admin",
    surfaceLabel: "Plans and guardrails",
    icon: ReceiptText,
  },
  {
    title: "Audit",
    description:
      "Operator activity trail for support and governance. This is the current home for action history across runs, credentials, and memory work.",
    href: "/admin/audit-logs",
    accessLabel: "Owner and admin",
    surfaceLabel: "Event history",
    icon: FileSearch,
  },
  {
    title: "Policies & Operations",
    description:
      "Guardrails, retention posture, memory health, and support-safe exports now share one operator control surface.",
    href: "/admin/operations",
    accessLabel: "Owner and admin",
    surfaceLabel: "Guardrails and support",
    icon: Scale,
  },
  {
    title: "Memory",
    description:
      "Curated observations are governed tenant assets, not just runtime exhaust. Browse records and inspect operational posture from here.",
    href: "/memory",
    accessLabel: "All signed-in users",
    surfaceLabel: "Observations and analytics",
    icon: BrainCircuit,
  },
];

const ADDITIONAL_TOOLS: GovernanceArea[] = [
  {
    title: "Marketplace",
    description:
      "Package and release management stays available as an admin shortcut, but it is not part of the core governance grouping for P2-F02.",
    href: "/admin/marketplace",
    accessLabel: "Owner and admin",
    surfaceLabel: "Packaging",
    icon: Store,
  },
];

export default function AdminIndexPage() {
  const { user } = useAuth();
  const canManage = user?.organization_role === "owner" || user?.organization_role === "admin";

  return (
    <ProtectedRoute>
      <DashboardLayout>
        <div className="flex flex-col gap-6">
          <section className="relative overflow-hidden rounded-[2rem] border border-border/50 bg-card/80 p-6 shadow-lg backdrop-blur-sm sm:p-8">
            <div
              className="pointer-events-none absolute inset-0 opacity-90"
              style={{
                backgroundImage:
                  "radial-gradient(circle at 0% 0%, rgba(56, 189, 248, 0.18), transparent 38%), radial-gradient(circle at 100% 10%, rgba(34, 197, 94, 0.16), transparent 32%), linear-gradient(135deg, rgba(15, 23, 42, 0.08), rgba(255, 255, 255, 0))",
              }}
            />
            <div className="relative flex flex-col gap-4">
              <Badge variant="outline" className="w-fit border-sky-500/30 text-sky-700 dark:text-sky-300">
                Governance Hub
              </Badge>
              <div className="max-w-3xl">
                <h1 className="text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
                  One home for how the tenant is governed.
                </h1>
                <p className="mt-3 text-sm leading-7 text-muted-foreground sm:text-base">
                  Organization access, identity, billing limits, audit history, policy posture, and curated memory now
                  share a single operator entry point. This is the baseline IA for the rest of P2.
                </p>
              </div>
              {!canManage && (
                <Alert className="max-w-3xl border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-200">
                  <ShieldCheck className="h-4 w-4" />
                  <AlertDescription>
                    You can review the governance map here, but some sections stay read-only unless you have owner or
                    admin access.
                  </AlertDescription>
                </Alert>
              )}
            </div>
          </section>

          <section className="grid gap-4 xl:grid-cols-2">
            {GOVERNANCE_AREAS.map((area) => {
              const Icon = area.icon;
              return (
                <Card key={area.title} className="border-border/60 bg-card/70 backdrop-blur-sm">
                  <CardHeader className="gap-4 sm:flex-row sm:items-start sm:justify-between">
                    <div className="space-y-2">
                      <div className="flex items-center gap-3">
                        <div className="flex h-10 w-10 items-center justify-center rounded-2xl border border-border/50 bg-background/80">
                          <Icon className="h-5 w-5 text-foreground" aria-hidden="true" />
                        </div>
                        <div>
                          <CardTitle>{area.title}</CardTitle>
                          <CardDescription>{area.surfaceLabel}</CardDescription>
                        </div>
                      </div>
                    </div>
                    <Badge variant="outline">{area.accessLabel}</Badge>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <p className="text-sm leading-6 text-muted-foreground">{area.description}</p>
                    <Button asChild variant="outline" className="w-full justify-between sm:w-auto">
                      <Link href={area.href}>
                        Open {area.title}
                        <ArrowRight className="h-4 w-4" aria-hidden="true" />
                      </Link>
                    </Button>
                  </CardContent>
                </Card>
              );
            })}
          </section>

          <section className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
            <Card className="border-border/60 bg-card/70 backdrop-blur-sm">
              <CardHeader>
                <CardTitle>What this baseline changes</CardTitle>
                <CardDescription>
                  Follow-up PRs can now deepen the same structure instead of inventing new admin flows.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3 text-sm text-muted-foreground">
                <p>Audit readability will improve inside the Audit section, not in a disconnected support page.</p>
                <p>
                  Role and memory-ownership clarity will land inside Organization and Memory, where operators already
                  expect to look.
                </p>
                <p>
                  Identity status is now truthful inside Identity, and policy visibility has a dedicated home inside
                  Policies &amp; Operations.
                </p>
              </CardContent>
            </Card>

            <Card className="border-border/60 bg-card/70 backdrop-blur-sm">
              <CardHeader>
                <CardTitle>Additional admin tool</CardTitle>
                <CardDescription>Available without redefining the governance IA.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {ADDITIONAL_TOOLS.map((tool) => {
                  const Icon = tool.icon;
                  return (
                    <div key={tool.title} className="rounded-2xl border border-border/50 bg-background/70 p-4">
                      <div className="flex items-center gap-3">
                        <div className="flex h-10 w-10 items-center justify-center rounded-2xl border border-border/50 bg-card">
                          <Icon className="h-5 w-5 text-foreground" aria-hidden="true" />
                        </div>
                        <div>
                          <p className="font-medium text-foreground">{tool.title}</p>
                          <p className="text-xs text-muted-foreground">{tool.accessLabel}</p>
                        </div>
                      </div>
                      <p className="mt-3 text-sm leading-6 text-muted-foreground">{tool.description}</p>
                      <Button asChild variant="ghost" className="mt-3 px-0 text-foreground hover:bg-transparent">
                        <Link href={tool.href}>Open {tool.title}</Link>
                      </Button>
                    </div>
                  );
                })}
              </CardContent>
            </Card>
          </section>
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
