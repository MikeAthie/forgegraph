import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import { Menu } from "lucide-react";

import { useAuth } from "../contexts/AuthContext";
import { approvalsApi } from "../lib/api";
import {
  Badge,
  Button,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  Spinner,
  ThemeToggle,
} from "@/components/ui";

const NAV_ITEMS = [
  { href: "/companies", label: "Companies" },
  { href: "/overview", label: "Command Center" },
  { href: "/approvals", label: "Approvals" },
  { href: "/departments", label: "Departments" },
  { href: "/tasks", label: "Activity" },
  { href: "/memory", label: "Knowledge" },
  { href: "/runs", label: "Operations" },
] as const;

export default function Header() {
  const router = useRouter();
  const { push } = router;
  const { user, isAuthenticated, logout } = useAuth();
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [pendingApprovalsCount, setPendingApprovalsCount] = useState<number | null>(null);

  const canManageOrg = user?.organization_role === "owner" || user?.organization_role === "admin";
  const canViewAuditLogs = canManageOrg;

  const activeHref = (() => {
    if (router.pathname.startsWith("/overview")) return "/overview";
    if (router.pathname.startsWith("/companies")) return "/companies";
    if (router.pathname.startsWith("/inbox") || router.pathname.startsWith("/approvals")) return "/approvals";
    if (router.pathname.startsWith("/agents") || router.pathname.startsWith("/departments")) return "/departments";
    if (router.pathname.startsWith("/tasks")) return "/tasks";
    if (router.pathname.startsWith("/memory")) return "/memory";
    if (router.pathname.startsWith("/runs") || router.pathname.startsWith("/executions")) return "/runs";
    return null;
  })();

  const refreshPendingApprovals = async () => {
    try {
      const data = await approvalsApi.count();
      setPendingApprovalsCount(data.count);
    } catch {
      // Non-blocking: ignore errors (e.g., transient auth/network issues).
      setPendingApprovalsCount(null);
    }
  };

  const handleLogout = async () => {
    setIsLoggingOut(true);
    try {
      await logout();
    } finally {
      setIsLoggingOut(false);
    }
  };

  // Operation and approval changes are projected server-side; this catches changes across tabs.
  useEffect(() => {
    if (!isAuthenticated) {
      setPendingApprovalsCount(null);
      return;
    }

    if (process.env.NODE_ENV === "test") {
      // Avoid noisy act() warnings in unit tests; the badge is non-critical UI.
      setPendingApprovalsCount(null);
      return;
    }

    let cancelled = false;

    const tick = async () => {
      if (cancelled) return;
      await refreshPendingApprovals();
    };

    void tick();
    const intervalId = window.setInterval(() => void tick(), 15_000);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [isAuthenticated]);

  return (
    <header className="sticky top-0 z-50 bg-background/80 backdrop-blur-lg border-b border-border supports-[backdrop-filter]:bg-background/60">
      <nav aria-label="Primary navigation" className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between h-16">
          <div className="flex items-center gap-2">
            {isAuthenticated && (
              <div className="sm:hidden">
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="icon" aria-label="Open navigation">
                      <Menu aria-hidden="true" className="size-5" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="start" className="w-44">
                    {NAV_ITEMS.map((item) => (
                      <DropdownMenuItem
                        key={item.href}
                        onSelect={(event) => {
                          event.preventDefault();
                          void push(item.href);
                        }}
                        className={activeHref === item.href ? "bg-accent cursor-pointer" : "cursor-pointer"}
                        aria-current={activeHref === item.href ? "page" : undefined}
                      >
                        <div className="flex w-full items-center justify-between gap-3">
                          <span>{item.label}</span>
                          {item.href === "/approvals" && (pendingApprovalsCount ?? 0) > 0 && (
                            <Badge
                              variant="destructive"
                              className="h-5 min-w-5 px-1.5"
                              aria-label={`${pendingApprovalsCount} pending approvals`}
                            >
                              {pendingApprovalsCount}
                            </Badge>
                          )}
                        </div>
                      </DropdownMenuItem>
                    ))}
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            )}

            <Link href="/" className="flex-shrink-0 flex items-center">
              <span className="text-xl font-bold text-foreground">ForgeGraph</span>
            </Link>

            {isAuthenticated && (
              <div className="hidden sm:ml-8 sm:flex sm:gap-x-1">
                {NAV_ITEMS.map((item) => (
                  <Button key={item.href} variant={activeHref === item.href ? "secondary" : "ghost"} asChild>
                    <Link
                      href={item.href}
                      aria-current={activeHref === item.href ? "page" : undefined}
                      className="flex items-center gap-2"
                    >
                      <span>{item.label}</span>
                      {item.href === "/approvals" && (pendingApprovalsCount ?? 0) > 0 && (
                        <Badge
                          variant="destructive"
                          className="h-5 min-w-5 px-1.5"
                          aria-label={`${pendingApprovalsCount} pending approvals`}
                        >
                          {pendingApprovalsCount}
                        </Badge>
                      )}
                    </Link>
                  </Button>
                ))}
              </div>
            )}
          </div>

          <div className="flex items-center gap-2">
            <ThemeToggle />
            {isAuthenticated ? (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="outline"
                    className="min-h-11 gap-2"
                    aria-label={`Open account menu for ${user?.email ?? "account"}`}
                  >
                    <span className="hidden sm:inline max-w-[150px] truncate">{user?.email}</span>
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      width="16"
                      height="16"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <path d="m6 9 6 6 6-6" />
                    </svg>
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-56">
                  <DropdownMenuLabel className="font-normal">
                    <div className="flex flex-col gap-y-1">
                      <p className="text-sm font-medium">Account</p>
                      <p className="text-xs text-muted-foreground truncate">{user?.email}</p>
                      {user?.organization_role && (
                        <p className="text-xs text-muted-foreground capitalize">{user.organization_role} access</p>
                      )}
                    </div>
                  </DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    onSelect={(event) => {
                      event.preventDefault();
                      void push("/admin");
                    }}
                    className="cursor-pointer"
                  >
                    Settings & Governance
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    onSelect={(event) => {
                      event.preventDefault();
                      void push("/workflows");
                    }}
                    className="cursor-pointer"
                  >
                    Advanced operating models
                  </DropdownMenuItem>
                  {canManageOrg && (
                    <DropdownMenuItem
                      onSelect={(event) => {
                        event.preventDefault();
                        void push("/admin/marketplace");
                      }}
                      className="cursor-pointer"
                    >
                      Marketplace
                    </DropdownMenuItem>
                  )}
                  {canManageOrg && (
                    <DropdownMenuItem
                      onSelect={(event) => {
                        event.preventDefault();
                        void push("/admin/sso");
                      }}
                      className="cursor-pointer"
                    >
                      SSO & SCIM
                    </DropdownMenuItem>
                  )}
                  {canManageOrg && (
                    <DropdownMenuItem
                      onSelect={(event) => {
                        event.preventDefault();
                        void push("/admin/billing");
                      }}
                      className="cursor-pointer"
                    >
                      Billing
                    </DropdownMenuItem>
                  )}
                  {canViewAuditLogs && (
                    <DropdownMenuItem
                      onSelect={(event) => {
                        event.preventDefault();
                        void push("/admin/audit-logs");
                      }}
                      className="cursor-pointer"
                    >
                      Activity log
                    </DropdownMenuItem>
                  )}
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    onSelect={(event) => {
                      event.preventDefault();
                      if (isLoggingOut) return;
                      void handleLogout();
                    }}
                    disabled={isLoggingOut}
                    className="cursor-pointer"
                  >
                    {isLoggingOut ? (
                      <>
                        <Spinner size="xs" className="mr-2" />
                        Signing out
                      </>
                    ) : (
                      "Sign out"
                    )}
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            ) : (
              <div className="flex items-center gap-x-2">
                <Button variant="ghost" asChild>
                  <Link href="/login">Sign in</Link>
                </Button>
                <Button asChild>
                  <Link href="/register">Get started</Link>
                </Button>
              </div>
            )}
          </div>
        </div>
      </nav>
    </header>
  );
}
