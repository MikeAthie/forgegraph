import Link from "next/link";
import { useRouter } from "next/router";
import type { ReactNode } from "react";
import { BrainCircuit } from "lucide-react";

import { Button, ThemeToggle } from "@/components/ui";

interface AuthLayoutProps {
  children: ReactNode;
}

export default function AuthLayout({ children }: AuthLayoutProps) {
  const router = useRouter();
  const isLogin = router.pathname.startsWith("/login");
  const isRegister = router.pathname.startsWith("/register");
  const heroCopy = isRegister
    ? {
        eyebrow: "New workspace",
        title: "Create your operating workspace before the first company operation.",
        description:
          "ForgeGraph starts with company work, approval gates, deliverables, and operating controls in one scoped workspace.",
      }
    : {
        eyebrow: "Authentication",
        title: "Sign in to create and operate AI-driven companies from one workspace.",
        description:
          "ForgeGraph opens on company work, approvals, deliverables, and operating controls instead of internal tooling.",
      };

  return (
    <div className="min-h-screen">
      <a
        href="#auth-main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[1000] focus:rounded-full focus:bg-slate-950 focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:text-white focus:shadow-lg focus:outline-none dark:focus:bg-slate-100 dark:focus:text-slate-950"
      >
        Skip to main content
      </a>
      <header className="sticky top-0 z-20 border-b border-slate-900/8 bg-[color-mix(in_srgb,var(--background)_80%,transparent)] backdrop-blur-2xl dark:border-white/8">
        <div className="mx-auto flex w-full max-w-[1280px] items-center justify-between px-4 py-4 sm:px-6 lg:px-8">
          <Link href="/" className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-slate-950 text-white dark:bg-slate-100 dark:text-slate-950">
              <BrainCircuit className="h-5 w-5" />
            </div>
            <div>
              <p className="text-[11px] uppercase tracking-[0.22em] text-slate-500 dark:text-slate-400">ForgeGraph</p>
              <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">AI Company OS</p>
            </div>
          </Link>
          <div className="flex flex-wrap items-center justify-end gap-2">
            <ThemeToggle />
            <Button variant={isLogin ? "secondary" : "ghost"} asChild className="min-h-11 rounded-full">
              <Link href="/login" aria-current={isLogin ? "page" : undefined}>
                Sign in
              </Link>
            </Button>
            <Button variant={isRegister ? "secondary" : "default"} asChild className="min-h-11 rounded-full">
              <Link href="/register" aria-current={isRegister ? "page" : undefined}>
                Get started
              </Link>
            </Button>
          </div>
        </div>
      </header>

      <main id="auth-main" tabIndex={-1} className="px-4 py-12 sm:px-6 lg:px-8">
        <div className="mx-auto flex min-h-[calc(100vh-9rem)] w-full max-w-[1280px] items-center justify-center">
          <div className="grid w-full gap-10 xl:grid-cols-[0.9fr_0.7fr] xl:items-center">
            <section className="hidden xl:block">
              <p className="text-[11px] uppercase tracking-[0.22em] text-slate-500 dark:text-slate-400">
                {heroCopy.eyebrow}
              </p>
              <h1
                className="mt-4 max-w-3xl text-5xl font-semibold tracking-tight text-slate-950 dark:text-slate-50"
                style={{ fontFamily: "var(--font-serif)" }}
              >
                {heroCopy.title}
              </h1>
              <p className="mt-5 max-w-2xl text-base leading-8 text-slate-600 dark:text-slate-300">
                {heroCopy.description}
              </p>
            </section>

            <div className="flex justify-center xl:justify-end">{children}</div>
          </div>
        </div>
      </main>
    </div>
  );
}
