import { useMemo } from "react";
import Link from "next/link";
import { Building2, FileSearch, KeyRound, LifeBuoy, ReceiptText, Scale, ShieldCheck, Store, Vault } from "lucide-react";

import DashboardLayout from "@/components/DashboardLayout";
import { InspectorPanel, Panel, SectionHeader, StatusBadge } from "@/components/os/operations-ui";
import ProtectedRoute from "@/components/ProtectedRoute";
import { Button } from "@/components/ui";
import { useAuth } from "@/contexts/AuthContext";

type SettingsArea = {
  title: string;
  description: string;
  href: string;
  accessLabel: string;
  section: "workspace" | "governance";
  icon: typeof Building2;
};

const SETTINGS_AREAS: SettingsArea[] = [
  {
    title: "Workspace Access",
    description: "Members, roles, default ownership, and workspace structure.",
    href: "/admin/organization",
    accessLabel: "All signed-in users",
    section: "workspace",
    icon: Building2,
  },
  {
    title: "Credentials",
    description: "Manage provider credentials and OAuth connections used by company operations and departments.",
    href: "/credentials",
    accessLabel: "Workspace operators",
    section: "workspace",
    icon: Vault,
  },
  {
    title: "Identity",
    description: "SSO and SCIM configuration for workspace-wide access control.",
    href: "/admin/sso",
    accessLabel: "Owner and admin",
    section: "governance",
    icon: KeyRound,
  },
  {
    title: "Billing",
    description: "Plans, commercial limits, and spend guardrails.",
    href: "/admin/billing",
    accessLabel: "Owner and admin",
    section: "governance",
    icon: ReceiptText,
  },
  {
    title: "Audit logs",
    description: "Action trail for governance, support, and operator review.",
    href: "/admin/audit-logs",
    accessLabel: "Owner and admin",
    section: "governance",
    icon: FileSearch,
  },
  {
    title: "Operations",
    description: "Guardrails, retention posture, memory health, and support-safe exports.",
    href: "/admin/operations",
    accessLabel: "Owner and admin",
    section: "governance",
    icon: Scale,
  },
  {
    title: "Marketplace admin",
    description: "Govern package releases, review posture, and runtime distribution.",
    href: "/admin/marketplace",
    accessLabel: "Owner and admin",
    section: "governance",
    icon: Store,
  },
  {
    title: "Help",
    description: "Operational guidance, support affordances, and implementation references.",
    href: "/admin/help",
    accessLabel: "All signed-in users",
    section: "workspace",
    icon: LifeBuoy,
  },
];

type SettingsHubProps = {
  mode: "settings" | "admin";
};

export default function SettingsHub({ mode }: SettingsHubProps) {
  const { user } = useAuth();
  const canManage = user?.organization_role === "owner" || user?.organization_role === "admin";
  const inspector = useMemo(
    () => (
      <InspectorPanel
        title={mode === "settings" ? "Settings posture" : "Governance posture"}
        subtitle="This hub is the configuration counterpart to the operating shell. It keeps policy, identity, billing, and credentials grouped instead of spread across unrelated navigation."
        sections={[
          {
            title: "Access level",
            content: (
              <StatusBadge
                status={canManage ? "active" : "pending"}
                label={canManage ? "Admin-capable" : "Read-only on governed surfaces"}
              />
            ),
          },
          {
            title: "Scope",
            content: user?.default_organization_id ? "Workspace settings" : "Personal workspace settings",
          },
          {
            title: "Current role",
            content: user?.organization_role ?? "member",
          },
        ]}
      />
    ),
    [canManage, mode, user?.default_organization_id, user?.organization_role],
  );

  return (
    <ProtectedRoute>
      <DashboardLayout inspector={inspector}>
        <div className="space-y-6">
          <SectionHeader
            eyebrow={mode === "settings" ? "Settings" : "Governance"}
            title={mode === "settings" ? "Configure the operating environment" : "Govern the operating environment"}
            description={
              mode === "settings"
                ? "Settings should be a truthful home for credentials, workspace access, identity, billing, and policy controls."
                : "Governance remains available as a legacy route, but it now follows the same settings structure and language."
            }
          />

          <div className="grid gap-6 2xl:grid-cols-2">
            {(["workspace", "governance"] as const).map((section) => (
              <Panel
                key={section}
                title={section === "workspace" ? "Workspace configuration" : "Governance controls"}
                description={
                  section === "workspace"
                    ? "Day-to-day configuration used by operators."
                    : "Policy, compliance, and administrative surfaces."
                }
              >
                <div className="space-y-3">
                  {SETTINGS_AREAS.flatMap((area) => {
                    if (area.section !== section) {
                      return [];
                    }
                    const Icon = area.icon;
                    return [
                      <div
                        key={area.title}
                        className="rounded-[1.25rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8"
                      >
                        <div className="flex items-start justify-between gap-4">
                          <div className="flex min-w-0 gap-3">
                            <div className="flex size-10 shrink-0 items-center justify-center rounded-2xl border border-zinc-900/10 bg-white dark:border-white/10 dark:bg-white/5">
                              <Icon className="size-5 text-zinc-900 dark:text-zinc-100" />
                            </div>
                            <div className="min-w-0">
                              <div className="flex flex-wrap items-center gap-2">
                                <p className="text-sm font-semibold text-zinc-950 dark:text-zinc-50">{area.title}</p>
                                <StatusBadge
                                  status={area.accessLabel.includes("admin") ? "paused" : "active"}
                                  label={area.accessLabel}
                                />
                              </div>
                              <p className="mt-2 text-sm leading-6 text-zinc-600 dark:text-zinc-300">
                                {area.description}
                              </p>
                            </div>
                          </div>
                          <Button asChild variant="outline" className="shrink-0 rounded-full">
                            <Link href={area.href}>Open</Link>
                          </Button>
                        </div>
                      </div>,
                    ];
                  })}
                </div>
              </Panel>
            ))}
          </div>

          <Panel
            title="Why this exists"
            description="The product should not force operators to remember whether a control lives under admin, account, or a legacy support section."
          >
            <div className="grid gap-4 lg:grid-cols-3">
              <div className="rounded-[1.25rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
                <p className="text-sm font-semibold text-zinc-950 dark:text-zinc-50">One mental model</p>
                <p className="mt-2 text-sm leading-6 text-zinc-600 dark:text-zinc-300">
                  The operating shell owns runtime state. Settings owns persistent configuration and governance.
                </p>
              </div>
              <div className="rounded-[1.25rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
                <p className="text-sm font-semibold text-zinc-950 dark:text-zinc-50">Less route drift</p>
                <p className="mt-2 text-sm leading-6 text-zinc-600 dark:text-zinc-300">
                  Legacy admin paths remain valid, but the top-level entry point becomes truthful and predictable.
                </p>
              </div>
              <div className="rounded-[1.25rem] border border-zinc-900/8 bg-[var(--panel-muted)] p-4 dark:border-white/8">
                <p className="text-sm font-semibold text-zinc-950 dark:text-zinc-50">Operator-safe</p>
                <p className="mt-2 text-sm leading-6 text-zinc-600 dark:text-zinc-300">
                  Access messaging is explicit, so users know what is configurable versus merely inspectable.
                </p>
              </div>
            </div>
          </Panel>
        </div>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
