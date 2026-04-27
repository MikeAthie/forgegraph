import { useEffect, useMemo, useState, type ReactNode } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import {
  BellRing,
  BookCopy,
  BrainCircuit,
  Building2,
  ChevronsUpDown,
  FolderTree,
  Gauge,
  HandCoins,
  LibraryBig,
  ShieldCheck,
  Waypoints,
} from "lucide-react";

import { ThemeToggle } from "@/components/ui/theme-toggle";
import { Badge, Button } from "@/components/ui";
import { useAuth } from "@/contexts/AuthContext";
import { decisionsApi } from "@/lib/api";
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
};

const navItems: NavItem[] = [
  { href: "/companies", label: "Companies", icon: Building2, section: "operate" },
  { href: "/overview", label: "Command Ops", icon: Gauge, section: "operate" },
  { href: "/agents", label: "Departments", icon: BrainCircuit, section: "operate" },
  { href: "/tasks", label: "Activity", icon: Waypoints, section: "operate" },
  { href: "/inbox", label: "Approvals", icon: BellRing, section: "operate" },
  { href: "/memory", label: "Knowledge", icon: BookCopy, section: "operate" },
  { href: "/accounting", label: "Usage", icon: HandCoins, section: "operate" },
  { href: "/library", label: "Assets", icon: LibraryBig, section: "build" },
  { href: "/workflows", label: "Advanced", icon: FolderTree, section: "build" },
  { href: "/settings", label: "Settings", icon: ShieldCheck, section: "build" },
];

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
  if (pathname.startsWith("/agents")) {
    return {
      title: "Departments",
      description: "Understand the departments and AI workers currently shaping company work.",
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
  if (href === "/inbox" && pathname.startsWith("/approvals")) return true;
  if (href === "/workflows" && pathname.startsWith("/graphs")) return true;
  if (href === "/settings" && pathname.startsWith("/admin")) return true;
  if (href === "/overview") return pathname === "/overview";
  return pathname === href || pathname.startsWith(`${href}/`);
};

export default function OsShell({ children, mainClassName }: OsShellProps) {
  const router = useRouter();
  const { user, isAuthenticated, logout } = useAuth();
  const [pendingDecisionCount, setPendingDecisionCount] = useState<number | null>(null);
  const meta = useMemo(() => pageMeta(router.pathname), [router.pathname]);

  useEffect(() => {
    if (!isAuthenticated || process.env.NODE_ENV === "test") {
      setPendingDecisionCount(null);
      return;
    }

    let cancelled = false;

    const load = async () => {
      try {
        const data = await decisionsApi.count();
        if (!cancelled) {
          setPendingDecisionCount(data.count);
        }
      } catch {
        if (!cancelled) {
          setPendingDecisionCount(null);
        }
      }
    };

    void load();
    const intervalId = window.setInterval(() => void load(), 20_000);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [isAuthenticated]);

  const items = navItems.map((item) => ({
    ...item,
    badge: item.href === "/inbox" ? pendingDecisionCount : item.badge,
  }));

  return (
    <div className="min-h-screen text-foreground">
      <div className="fixed inset-0 -z-10 app-grid opacity-40" />
      <div className="flex min-h-screen">
        <aside className="hidden w-[18.5rem] shrink-0 border-r border-sidebar-border bg-sidebar/95 px-5 py-5 backdrop-blur-2xl lg:flex lg:flex-col">
          <Link
            href="/companies"
            className="glass-panel flex items-center gap-3 rounded-[1.5rem] border border-sidebar-border px-4 py-4"
          >
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-sidebar-primary text-sidebar-primary-foreground">
              <Building2 className="h-5 w-5" />
            </div>
            <div className="min-w-0">
              <p className="text-[11px] uppercase tracking-[0.24em] text-muted-foreground">ForgeGraph</p>
              <p className="truncate text-base font-semibold text-sidebar-foreground">AI Company OS</p>
            </div>
          </Link>

          <div className="mt-6 rounded-[1.5rem] border border-sidebar-border bg-sidebar-accent px-4 py-4">
            <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Workspace</p>
            <button
              type="button"
              className="mt-3 flex w-full items-center justify-between rounded-2xl border border-sidebar-border bg-white/80 px-3 py-2 text-left text-sm dark:bg-white/5"
            >
              <span className="truncate font-medium">
                {user?.default_organization_id ? "Company workspace" : "Personal workspace"}
              </span>
              <ChevronsUpDown className="h-4 w-4 text-muted-foreground" />
            </button>
            <p className="mt-3 text-sm leading-6 text-muted-foreground">
              Create companies, launch operations, and intervene only when the company needs you.
            </p>
          </div>

          <div className="mt-8 space-y-6">
            {(["operate", "build"] as const).map((section) => (
              <div key={section}>
                <p className="px-3 text-[11px] uppercase tracking-[0.2em] text-muted-foreground">
                  {section === "operate" ? "Operate" : "Advanced"}
                </p>
                <nav className="mt-2 space-y-1.5">
                  {items
                    .filter((item) => item.section === section)
                    .map((item) => {
                      const Icon = item.icon;
                      const active = isActivePath(router.pathname, item.href);
                      return (
                        <Link
                          key={item.href}
                          href={item.href}
                          className={cn(
                            "flex items-center justify-between rounded-2xl px-3.5 py-3 text-sm transition-colors",
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

          <div className="mt-auto rounded-[1.75rem] border border-sidebar-border bg-[linear-gradient(180deg,rgba(24,38,62,0.96),rgba(24,38,62,0.88))] px-5 py-5 text-slate-100 dark:bg-[linear-gradient(180deg,rgba(237,241,245,0.14),rgba(237,241,245,0.08))]">
            <p className="text-[11px] uppercase tracking-[0.18em] text-slate-300 dark:text-slate-400">
              Operating posture
            </p>
            <p className="mt-3 text-lg font-semibold" style={{ fontFamily: "var(--font-serif)" }}>
              Company first. Engine second.
            </p>
            <p className="mt-2 text-sm leading-6 text-slate-300 dark:text-slate-300">
              The shell should always answer four things: what the company is doing, what it produced, what is blocked,
              and what to do next.
            </p>
          </div>
        </aside>

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
                  <Badge
                    variant="outline"
                    className="rounded-full border-slate-900/10 bg-white/70 px-3 py-1 dark:border-white/10 dark:bg-white/5"
                  >
                    {user?.default_organization_id ? "Organization scope" : "Personal scope"}
                  </Badge>
                  <Badge
                    variant="outline"
                    className="rounded-full border-slate-900/10 bg-white/70 px-3 py-1 dark:border-white/10 dark:bg-white/5"
                  >
                    Last 24 hours
                  </Badge>
                  <ThemeToggle />
                  {isAuthenticated ? (
                    <Button
                      variant="outline"
                      className="rounded-full border-slate-900/10 bg-white/70 dark:border-white/10 dark:bg-white/5"
                      onClick={() => void logout()}
                    >
                      {user?.email ?? "Sign out"}
                    </Button>
                  ) : null}
                </div>
              </div>

              <div className="flex gap-2 overflow-x-auto pb-1 lg:hidden">
                {items.map((item) => {
                  const Icon = item.icon;
                  const active = isActivePath(router.pathname, item.href);
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      className={cn(
                        "inline-flex items-center gap-2 rounded-full border px-3 py-2 text-sm whitespace-nowrap",
                        active
                          ? "border-slate-950 bg-slate-950 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-950"
                          : "border-slate-900/10 bg-white/75 text-slate-700 dark:border-white/10 dark:bg-white/5 dark:text-slate-200",
                      )}
                    >
                      <Icon className="h-4 w-4" />
                      {item.label}
                      {item.badge && item.badge > 0 ? <span>{item.badge}</span> : null}
                    </Link>
                  );
                })}
              </div>
            </div>
          </header>

          <main className="px-4 py-6 sm:px-6 lg:px-8">
            <div className={cn("mx-auto w-full max-w-[1680px]", mainClassName)}>{children}</div>
          </main>
        </div>
      </div>
    </div>
  );
}
