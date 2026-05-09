import { useCallback, useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BellRing,
  BookCopy,
  BrainCircuit,
  Building2,
  Check,
  ChevronsUpDown,
  FolderTree,
  Gauge,
  HandCoins,
  LibraryBig,
  LogOut,
  Loader2,
  Menu,
  Plus,
  ShieldCheck,
  UserCircle,
  Waypoints,
} from "lucide-react";

import { ThemeToggle } from "@/components/ui/theme-toggle";
import {
  Badge,
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  Input,
} from "@/components/ui";
import { useAuth } from "@/contexts/AuthContext";
import { useStateFeed, type StateFeedMessage } from "@/hooks/useStateFeed";
import { decisionsApi, getApiErrorMessage, organizationsApi, type OrganizationListItem } from "@/lib/api";
import { cn } from "@/lib/utils";

type OsShellProps = {
  children: ReactNode;
  mainClassName?: string;
};

type NavItem = {
  href: string;
  label: string;
  icon: typeof Gauge;
  section: "operate" | "build";
  badge?: number | null;
  adminOnly?: boolean;
};

const navItems: NavItem[] = [
  { href: "/companies", label: "Companies", icon: Building2, section: "operate" },
  { href: "/overview", label: "Command Ops", icon: Gauge, section: "operate" },
  { href: "/departments", label: "Departments", icon: BrainCircuit, section: "operate" },
  { href: "/tasks", label: "Activity", icon: Waypoints, section: "operate" },
  { href: "/approvals", label: "Approvals", icon: BellRing, section: "operate" },
  { href: "/memory", label: "Knowledge", icon: BookCopy, section: "operate" },
  { href: "/accounting", label: "Usage", icon: HandCoins, section: "operate" },
  { href: "/ops", label: "Recovery", icon: ShieldCheck, section: "operate", adminOnly: true },
  { href: "/library", label: "Assets", icon: LibraryBig, section: "build" },
  { href: "/workflows", label: "Advanced operating models", icon: FolderTree, section: "build" },
  { href: "/settings", label: "Settings", icon: ShieldCheck, section: "build" },
];

const mobilePrimaryHrefs = new Set(["/companies", "/overview", "/tasks", "/approvals", "/memory"]);

const DECISION_BADGE_FEED_EVENTS = ["decision.created", "decision.updated", "overview.updated"];

function stateFeedMessageType(message: StateFeedMessage) {
  return message.type || message.event_type || message.event?.type || message.event?.event_type || "";
}

const pageMeta = (pathname: string) => {
  if (pathname.startsWith("/companies/new")) {
    return {
      title: "Create Company",
      description: "Build an AI-driven company with departments, capabilities, autonomy policy, and AI access mode.",
    };
  }
  if (pathname.startsWith("/companies")) {
    return {
      title: "Company Workspace",
      description: "Operate a company, review current operations, inspect deliverables, and make command decisions.",
    };
  }
  if (pathname.startsWith("/overview")) {
    return {
      title: "Command Ops",
      description: "See company posture, active work, approvals, usage, and attention points from one command surface.",
    };
  }
  if (pathname.startsWith("/agents") || pathname.startsWith("/departments")) {
    return {
      title: "Departments",
      description: "Understand the departments currently shaping company work.",
    };
  }
  if (pathname.startsWith("/tasks")) {
    return {
      title: "Department Activity",
      description: "Track work in motion, blocked work, and the next operator action.",
    };
  }
  if (pathname.startsWith("/inbox") || pathname.startsWith("/approvals")) {
    return {
      title: "Approvals",
      description: "Review consequential company decisions with context before work resumes.",
    };
  }
  if (pathname.startsWith("/accounting")) {
    return {
      title: "Usage And Budget",
      description: "Track AI usage, spend concentration, and company operating limits.",
    };
  }
  if (pathname.startsWith("/analytics/llm")) {
    return {
      title: "LLM Analytics",
      description: "Review AI usage, cost, quota, and budget posture across the workspace.",
    };
  }
  if (pathname.startsWith("/analytics/memory")) {
    return {
      title: "Memory Analytics",
      description: "Review knowledge retention, indexing, retrieval, and memory-cost posture.",
    };
  }
  if (pathname.startsWith("/analytics")) {
    return {
      title: "Analytics",
      description: "Inspect specialist usage and operational telemetry for the workspace.",
    };
  }
  if (pathname.startsWith("/credentials")) {
    return {
      title: "AI Access Credentials",
      description: "Manage governed provider credentials and connection health for company operations.",
    };
  }
  if (pathname.startsWith("/prompts")) {
    return {
      title: "Prompt Library",
      description: "Browse reusable prompt templates and manage governed company playbooks.",
    };
  }
  if (pathname.startsWith("/onboarding")) {
    return {
      title: "Workspace Onboarding",
      description: "Complete the guided setup steps for operating companies in this organization.",
    };
  }
  if (pathname.startsWith("/storefront")) {
    return {
      title: "Storefront",
      description: "Review customer-facing commerce surfaces connected to the operating company.",
    };
  }
  if (pathname.startsWith("/admin/audit-logs")) {
    return {
      title: "Activity Log",
      description: "Search the operator trail across operations, access, credentials, retention, and knowledge.",
    };
  }
  if (pathname.startsWith("/admin/marketplace")) {
    return {
      title: "Marketplace Governance",
      description: "Review governed packages, releases, and tenant-scoped manifest previews.",
    };
  }
  if (pathname.startsWith("/admin/organization")) {
    return {
      title: "Workspace Access",
      description: "Manage organization members, roles, and access posture.",
    };
  }
  if (pathname.startsWith("/admin/sso")) {
    return {
      title: "SSO Configuration",
      description: "Configure enterprise identity settings for the workspace.",
    };
  }
  if (pathname.startsWith("/admin/billing")) {
    return {
      title: "Billing",
      description: "Manage subscription, entitlement, and workspace billing controls.",
    };
  }
  if (pathname.startsWith("/admin/help")) {
    return {
      title: "Support",
      description: "Find operational support resources and implementation references.",
    };
  }
  if (pathname.startsWith("/ops")) {
    return {
      title: "Operator Recovery",
      description: "Inspect dead letters, projection lag, event spool health, and backend recovery actions.",
    };
  }
  if (pathname.startsWith("/library") || pathname.startsWith("/prompts")) {
    return {
      title: "Assets And Playbooks",
      description: "Reusable prompts, templates, and governed building blocks for company operations.",
    };
  }
  if (pathname.startsWith("/workflows") || pathname.startsWith("/graphs")) {
    return {
      title: "Advanced Operating Model Editor",
      description: "Advanced operating-model authoring for expert users. This is not the primary company experience.",
    };
  }
  if (pathname.startsWith("/executions") || pathname.startsWith("/runs")) {
    return {
      title: "Operation Detail",
      description: "Inspect one operation, its department activity, deliverables, and decision points.",
    };
  }
  if (pathname.startsWith("/memory")) {
    return {
      title: "Company Knowledge",
      description: "Inspect retained knowledge, context, and memory quality for the operating company.",
    };
  }
  if (pathname.startsWith("/settings") || pathname.startsWith("/admin")) {
    return {
      title: "Operating Environment",
      description: "Configure identity, AI access, governance, and support controls for the workspace.",
    };
  }
  return {
    title: "ForgeGraph",
    description: "AI Company Operating System.",
  };
};

const isActivePath = (pathname: string, href: string) => {
  if (href === "/approvals" && pathname.startsWith("/inbox")) return true;
  if (href === "/workflows" && pathname.startsWith("/graphs")) return true;
  if (href === "/settings" && pathname.startsWith("/admin")) return true;
  if (href === "/overview") return pathname === "/overview";
  return pathname === href || pathname.startsWith(`${href}/`);
};

export default function OsShell({ children, mainClassName }: OsShellProps) {
  const router = useRouter();
  const { user, isAuthenticated, logout, checkAuth } = useAuth();
  const [organizations, setOrganizations] = useState<OrganizationListItem[]>([]);
  const [organizationsLoading, setOrganizationsLoading] = useState(false);
  const [organizationActionId, setOrganizationActionId] = useState<string | null>(null);
  const [organizationError, setOrganizationError] = useState<string | null>(null);
  const [createOrganizationOpen, setCreateOrganizationOpen] = useState(false);
  const [newOrganizationName, setNewOrganizationName] = useState("");
  const [creatingOrganization, setCreatingOrganization] = useState(false);
  const [createOrganizationError, setCreateOrganizationError] = useState<string | null>(null);
  const meta = useMemo(() => pageMeta(router.pathname), [router.pathname]);
  const organizationId = user?.default_organization_id ?? null;
  const queryClient = useQueryClient();
  const invalidateDecisionCount = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ["decisions", "count"] });
  }, [queryClient]);
  const decisionBadgeFeed = useStateFeed({
    scope: "organization",
    organizationId,
    enabled: isAuthenticated && Boolean(organizationId) && process.env.NODE_ENV !== "test",
    eventTypes: DECISION_BADGE_FEED_EVENTS,
    onEvent: (event) => {
      if (event.requires_refetch || DECISION_BADGE_FEED_EVENTS.includes(stateFeedMessageType(event))) {
        invalidateDecisionCount();
      }
    },
    onFullResync: invalidateDecisionCount,
  });
  const pendingDecisionQuery = useQuery({
    queryKey: ["decisions", "count", organizationId ?? "current"],
    queryFn: decisionsApi.count,
    enabled: isAuthenticated && Boolean(organizationId) && process.env.NODE_ENV !== "test",
    refetchInterval: decisionBadgeFeed.status === "unavailable" ? 30_000 : false,
  });
  const pendingDecisionCount = pendingDecisionQuery.data?.count ?? null;
  const canOperate = user?.organization_role === "owner" || user?.organization_role === "admin";

  useEffect(() => {
    if (!isAuthenticated || process.env.NODE_ENV === "test") {
      setOrganizations([]);
      return;
    }

    let cancelled = false;

    const loadOrganizations = async () => {
      setOrganizationsLoading(true);
      try {
        const data = await organizationsApi.list();
        if (!cancelled) {
          setOrganizations(data);
          setOrganizationError(null);
        }
      } catch (error) {
        if (!cancelled) {
          setOrganizations([]);
          setOrganizationError(getApiErrorMessage(error, "Could not load organizations."));
        }
      } finally {
        if (!cancelled) {
          setOrganizationsLoading(false);
        }
      }
    };

    void loadOrganizations();
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated, user?.default_organization_id]);

  const currentOrganization = useMemo(
    () =>
      organizations.find((organization) => organization.id === user?.default_organization_id) ??
      organizations.find((organization) => organization.is_default) ??
      null,
    [organizations, user?.default_organization_id],
  );

  const organizationLabel =
    currentOrganization?.name ?? (user?.default_organization_id ? "Current organization" : "Personal organization");

  const refreshOrganizationContext = useCallback(async () => {
    await checkAuth();
    if (router.isReady) {
      await router.replace(router.asPath, undefined, { scroll: false });
    }
  }, [checkAuth, router]);

  const handleSwitchOrganization = useCallback(
    async (organizationId: string) => {
      if (organizationId === user?.default_organization_id || organizationActionId) {
        return;
      }

      setOrganizationActionId(organizationId);
      setOrganizationError(null);
      try {
        const selected = await organizationsApi.switchCurrent(organizationId);
        setOrganizations((current) =>
          current.map((organization) => ({
            ...organization,
            is_default: organization.id === selected.id,
          })),
        );
        await refreshOrganizationContext();
      } catch (error) {
        setOrganizationError(getApiErrorMessage(error, "Could not switch organization."));
      } finally {
        setOrganizationActionId(null);
      }
    },
    [organizationActionId, refreshOrganizationContext, user?.default_organization_id],
  );

  const resetCreateOrganization = useCallback(() => {
    setNewOrganizationName("");
    setCreatingOrganization(false);
    setCreateOrganizationError(null);
  }, []);

  const handleCreateOrganization = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      const name = newOrganizationName.trim();
      if (!name) {
        setCreateOrganizationError("Organization name is required.");
        return;
      }

      setCreatingOrganization(true);
      setCreateOrganizationError(null);
      try {
        const created = await organizationsApi.create({ name, make_default: true });
        setOrganizations((current) => [
          created,
          ...current
            .filter((organization) => organization.id !== created.id)
            .map((organization) => ({ ...organization, is_default: false })),
        ]);
        setCreateOrganizationOpen(false);
        setOrganizationError(null);
        resetCreateOrganization();
        await refreshOrganizationContext();
      } catch (error) {
        setCreateOrganizationError(getApiErrorMessage(error, "Could not create organization."));
      } finally {
        setCreatingOrganization(false);
      }
    },
    [newOrganizationName, refreshOrganizationContext, resetCreateOrganization],
  );

  const items = navItems
    .filter((item) => !item.adminOnly || canOperate)
    .map((item) => ({
      ...item,
      badge: item.href === "/approvals" ? pendingDecisionCount : item.badge,
    }));
  const mobilePrimaryItems = items.filter((item) => mobilePrimaryHrefs.has(item.href));
  const mobileOverflowItems = items.filter((item) => !mobilePrimaryHrefs.has(item.href));

  return (
    <div className="min-h-screen text-foreground">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[1000] focus:rounded-full focus:bg-slate-950 focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:text-white focus:shadow-lg focus:outline-none dark:focus:bg-slate-100 dark:focus:text-slate-950"
      >
        Skip to main content
      </a>
      <div className="fixed inset-0 -z-10 app-grid opacity-40" />
      <div className="flex min-h-screen">
        <aside className="hidden w-[18.5rem] shrink-0 border-r border-sidebar-border bg-sidebar/95 px-4 py-4 backdrop-blur-2xl lg:sticky lg:top-0 lg:flex lg:h-screen lg:flex-col lg:self-start lg:overflow-y-auto">
          <Link
            href="/companies"
            className="glass-panel flex items-center gap-3 rounded-[1.25rem] border border-sidebar-border px-3.5 py-3"
          >
            <Image
              src="/icon0.svg"
              alt=""
              width={40}
              height={40}
              priority
              className="h-10 w-10 shrink-0 rounded-xl object-cover shadow-sm"
            />
            <div className="min-w-0">
              <p className="text-[11px] uppercase tracking-[0.24em] text-muted-foreground">ForgeGraph</p>
              <p className="truncate text-base font-semibold text-sidebar-foreground">AI Company OS</p>
            </div>
          </Link>

          <div className="mt-5 rounded-[1.25rem] border border-sidebar-border bg-sidebar-accent px-3.5 py-3">
            <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Organization</p>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button
                  type="button"
                  aria-label={`Switch organization. Current organization: ${organizationLabel}`}
                  className="mt-2 flex min-h-11 w-full items-center justify-between rounded-xl border border-sidebar-border bg-white/80 px-3 py-2.5 text-left text-sm dark:bg-white/5"
                >
                  <span className="truncate font-medium">{organizationLabel}</span>
                  {organizationsLoading ? (
                    <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                  ) : (
                    <ChevronsUpDown className="h-4 w-4 text-muted-foreground" />
                  )}
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" className="w-64">
                <DropdownMenuLabel>Organizations</DropdownMenuLabel>
                {organizations.length > 0 ? (
                  organizations.map((organization) => {
                    const selected =
                      organization.id === user?.default_organization_id || organization.id === currentOrganization?.id;
                    const switching = organizationActionId === organization.id;
                    return (
                      <DropdownMenuItem
                        key={organization.id}
                        disabled={switching}
                        onSelect={() => void handleSwitchOrganization(organization.id)}
                      >
                        <span className="flex min-w-0 flex-1 items-center gap-2">
                          {switching ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <Check className={cn("h-4 w-4", selected ? "opacity-100" : "opacity-0")} />
                          )}
                          <span className="truncate">{organization.name}</span>
                        </span>
                      </DropdownMenuItem>
                    );
                  })
                ) : (
                  <DropdownMenuItem disabled>
                    {organizationsLoading ? "Loading organizations" : "No organizations found"}
                  </DropdownMenuItem>
                )}
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  onSelect={(event) => {
                    event.preventDefault();
                    setCreateOrganizationError(null);
                    setCreateOrganizationOpen(true);
                  }}
                >
                  <Plus className="h-4 w-4" />
                  Add organization
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
            <p className="mt-2 text-[13px] leading-5 text-muted-foreground">
              Companies, operations, knowledge, and usage stay separated by organization.
            </p>
            {organizationError ? <p className="mt-2 text-xs text-destructive">{organizationError}</p> : null}
          </div>

          <div className="mt-6 space-y-4">
            {(["operate", "build"] as const).map((section) => (
              <div key={section}>
                <p className="px-3 text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
                  {section === "operate" ? "Operate" : "Advanced"}
                </p>
                <nav className="mt-1.5 space-y-0.5" aria-label={`${section} navigation`}>
                  {items
                    .filter((item) => item.section === section)
                    .map((item) => {
                      const Icon = item.icon;
                      const active = isActivePath(router.pathname, item.href);
                      return (
                        <Link
                          key={item.href}
                          href={item.href}
                          aria-current={active ? "page" : undefined}
                          className={cn(
                            "flex items-center justify-between rounded-xl px-3.5 py-2.5 text-sm transition-colors",
                            active
                              ? "bg-sidebar-primary text-sidebar-primary-foreground shadow-[0_20px_40px_-30px_rgba(15,23,42,0.85)]"
                              : "text-sidebar-foreground/80 hover:bg-sidebar-accent hover:text-sidebar-foreground",
                          )}
                        >
                          <span className="flex items-center gap-3">
                            <Icon className="h-4 w-4" />
                            {item.label}
                          </span>
                          {item.badge && item.badge > 0 ? (
                            <Badge
                              variant="outline"
                              className={cn(
                                "min-w-6 justify-center rounded-full px-1.5 text-[11px]",
                                active
                                  ? "border-white/18 bg-white/12 text-white"
                                  : "border-rose-800/10 bg-rose-50 text-rose-900 dark:border-rose-200/15 dark:bg-rose-500/10 dark:text-rose-100",
                              )}
                            >
                              {item.badge}
                            </Badge>
                          ) : null}
                        </Link>
                      );
                    })}
                </nav>
              </div>
            ))}
          </div>
        </aside>

        <Dialog
          open={createOrganizationOpen}
          onOpenChange={(open) => {
            setCreateOrganizationOpen(open);
            if (!open) {
              resetCreateOrganization();
            }
          }}
        >
          <DialogContent className="sm:max-w-md">
            <form onSubmit={handleCreateOrganization} className="space-y-5">
              <DialogHeader>
                <DialogTitle>Add Organization</DialogTitle>
                <DialogDescription>
                  Create a separate operating space for companies, operations, knowledge, and usage.
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-2">
                <label htmlFor="new-organization-name" className="text-sm font-medium text-foreground">
                  Organization name
                </label>
                <Input
                  id="new-organization-name"
                  autoFocus
                  aria-describedby={createOrganizationError ? "new-organization-name-error" : undefined}
                  autoComplete="organization"
                  value={newOrganizationName}
                  onChange={(event) => {
                    setNewOrganizationName(event.target.value);
                    setCreateOrganizationError(null);
                  }}
                  placeholder="Acme Operations"
                />
                {createOrganizationError ? (
                  <p id="new-organization-name-error" role="alert" className="text-sm text-destructive">
                    {createOrganizationError}
                  </p>
                ) : null}
              </div>
              <DialogFooter>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setCreateOrganizationOpen(false)}
                  disabled={creatingOrganization}
                >
                  Cancel
                </Button>
                <Button type="submit" disabled={creatingOrganization}>
                  {creatingOrganization ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                  Add organization
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>

        <div className="min-w-0 flex-1">
          <header className="sticky top-0 z-30 border-b border-slate-900/8 bg-[color-mix(in_srgb,var(--background)_82%,transparent)] backdrop-blur-2xl dark:border-white/8">
            <div className="mx-auto flex w-full max-w-[1680px] flex-col gap-4 px-4 py-4 sm:px-6 lg:px-8">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
                <div className="min-w-0">
                  <p className="text-[11px] uppercase tracking-[0.24em] text-muted-foreground">ForgeGraph</p>
                  <h1 className="mt-2 text-2xl font-semibold tracking-tight text-foreground sm:text-[2rem]">
                    {meta.title}
                  </h1>
                  <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">{meta.description}</p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {isAuthenticated ? (
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <button
                          type="button"
                          aria-label={`Switch organization. Current organization: ${organizationLabel}`}
                          className="inline-flex min-h-11 max-w-[18rem] items-center gap-2 rounded-full border border-slate-900/10 bg-white/70 px-3 py-2.5 text-sm font-medium text-slate-900 shadow-sm transition-colors hover:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-950 focus-visible:ring-offset-2 focus-visible:ring-offset-white dark:border-white/10 dark:bg-white/5 dark:text-slate-100 dark:hover:bg-white/10 dark:focus-visible:ring-slate-100 dark:focus-visible:ring-offset-slate-950"
                        >
                          <Building2 className="h-4 w-4 shrink-0 text-muted-foreground" />
                          <span className="truncate">{organizationLabel}</span>
                          {organizationsLoading ? (
                            <Loader2 className="h-4 w-4 shrink-0 animate-spin text-muted-foreground" />
                          ) : (
                            <ChevronsUpDown className="h-4 w-4 shrink-0 text-muted-foreground" />
                          )}
                        </button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end" className="w-72">
                        <DropdownMenuLabel>Organization scope</DropdownMenuLabel>
                        {organizations.length > 0 ? (
                          organizations.map((organization) => {
                            const selected =
                              organization.id === user?.default_organization_id ||
                              organization.id === currentOrganization?.id;
                            const switching = organizationActionId === organization.id;
                            return (
                              <DropdownMenuItem
                                key={organization.id}
                                disabled={switching}
                                onSelect={() => void handleSwitchOrganization(organization.id)}
                              >
                                <span className="flex min-w-0 flex-1 items-center gap-2">
                                  {switching ? (
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                  ) : (
                                    <Check className={cn("h-4 w-4", selected ? "opacity-100" : "opacity-0")} />
                                  )}
                                  <span className="truncate">{organization.name}</span>
                                </span>
                              </DropdownMenuItem>
                            );
                          })
                        ) : (
                          <DropdownMenuItem disabled>
                            {organizationsLoading ? "Loading organizations" : "No organizations found"}
                          </DropdownMenuItem>
                        )}
                        <DropdownMenuSeparator />
                        <DropdownMenuItem
                          onSelect={(event) => {
                            event.preventDefault();
                            setCreateOrganizationError(null);
                            setCreateOrganizationOpen(true);
                          }}
                        >
                          <Plus className="h-4 w-4" />
                          Add organization
                        </DropdownMenuItem>
                        {organizationError ? (
                          <>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem disabled className="text-destructive">
                              {organizationError}
                            </DropdownMenuItem>
                          </>
                        ) : null}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  ) : null}
                  <ThemeToggle />
                  {isAuthenticated ? (
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <button
                          type="button"
                          aria-label={`Open account menu for ${user?.email ?? "account"}`}
                          className="inline-flex min-h-11 max-w-[16rem] items-center gap-2 rounded-full border border-slate-900/10 bg-white/70 px-3 py-2.5 text-sm font-medium text-slate-900 shadow-sm transition-colors hover:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-950 focus-visible:ring-offset-2 focus-visible:ring-offset-white dark:border-white/10 dark:bg-white/5 dark:text-slate-100 dark:hover:bg-white/10 dark:focus-visible:ring-slate-100 dark:focus-visible:ring-offset-slate-950"
                        >
                          <UserCircle className="h-4 w-4 shrink-0 text-muted-foreground" />
                          <span className="truncate">{user?.email ?? "Account"}</span>
                          <ChevronsUpDown className="h-4 w-4 shrink-0 text-muted-foreground" />
                        </button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end" className="w-72">
                        <DropdownMenuLabel>
                          <span className="block text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
                            Signed in as
                          </span>
                          <span className="mt-1 block truncate font-normal">{user?.email ?? "Account"}</span>
                        </DropdownMenuLabel>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem onSelect={() => void logout()}>
                          <LogOut className="h-4 w-4" />
                          Sign out
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  ) : null}
                </div>
              </div>

              <nav
                aria-label="Mobile primary navigation"
                className="grid grid-cols-2 gap-2 pb-1 sm:grid-cols-3 lg:hidden"
              >
                {mobilePrimaryItems.map((item) => {
                  const Icon = item.icon;
                  const active = isActivePath(router.pathname, item.href);
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      aria-current={active ? "page" : undefined}
                      className={cn(
                        "inline-flex min-h-11 items-center justify-center gap-2 rounded-full border px-3 py-2 text-center text-sm",
                        active
                          ? "border-slate-950 bg-slate-950 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-950"
                          : "border-slate-900/10 bg-white/75 text-slate-700 dark:border-white/10 dark:bg-white/5 dark:text-slate-200",
                      )}
                    >
                      <Icon className="h-4 w-4" />
                      <span className="min-w-0 truncate">{item.label}</span>
                      {item.badge && item.badge > 0 ? <span>{item.badge}</span> : null}
                    </Link>
                  );
                })}
                {mobileOverflowItems.length > 0 ? (
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <button
                        type="button"
                        className="inline-flex min-h-11 items-center justify-center gap-2 rounded-full border border-slate-900/10 bg-white/75 px-3 py-2 text-center text-sm text-slate-700 dark:border-white/10 dark:bg-white/5 dark:text-slate-200"
                      >
                        <Menu className="h-4 w-4" />
                        <span>More</span>
                      </button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" className="w-72 lg:hidden">
                      <DropdownMenuLabel>More destinations</DropdownMenuLabel>
                      <DropdownMenuSeparator />
                      {mobileOverflowItems.map((item) => {
                        const Icon = item.icon;
                        const active = isActivePath(router.pathname, item.href);
                        return (
                          <DropdownMenuItem key={item.href} asChild>
                            <Link href={item.href} aria-current={active ? "page" : undefined}>
                              <Icon className="h-4 w-4" />
                              <span className="min-w-0 truncate">{item.label}</span>
                              {item.badge && item.badge > 0 ? <Badge variant="secondary">{item.badge}</Badge> : null}
                            </Link>
                          </DropdownMenuItem>
                        );
                      })}
                    </DropdownMenuContent>
                  </DropdownMenu>
                ) : null}
              </nav>
            </div>
          </header>

          <main id="main-content" tabIndex={-1} className="px-4 py-6 sm:px-6 lg:px-8">
            <div className={cn("mx-auto w-full max-w-[1680px]", mainClassName)}>{children}</div>
          </main>
        </div>
      </div>
    </div>
  );
}
