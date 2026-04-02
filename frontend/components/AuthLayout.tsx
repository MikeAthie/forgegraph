import Link from "next/link";
import type { ReactNode } from "react";
import { BrainCircuit } from "lucide-react";

import { Button, ThemeToggle } from "@/components/ui";

interface AuthLayoutProps {
  children: ReactNode;
}

export default function AuthLayout({ children }: AuthLayoutProps) {
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b border-slate-900/8 bg-[color-mix(in_srgb,var(--background)_80%,transparent)] backdrop-blur-2xl dark:border-white/8">
        <div className="mx-auto flex w-full max-w-[1280px] items-center justify-between px-4 py-4 sm:px-6 lg:px-8">
          <Link href="/" className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-slate-950 text-white dark:bg-slate-100 dark:text-slate-950">
              <BrainCircuit className="h-5 w-5" />
            </div>
            <div>
              <p className="text-[11px] uppercase tracking-[0.22em] text-slate-500 dark:text-slate-400">ForgeGraph</p>
              <p className="text-sm font-semibold text-slate-950 dark:text-slate-50">AI Organization OS</p>
            </div>
          </Link>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <Button variant="ghost" asChild className="rounded-full">
              <Link href="/login">Sign in</Link>
            </Button>
            <Button asChild className="rounded-full">
              <Link href="/register">Get started</Link>
            </Button>
          </div>
        </div>
      </header>

      <main className="px-4 py-12 sm:px-6 lg:px-8">
        <div className="mx-auto flex min-h-[calc(100vh-9rem)] w-full max-w-[1280px] items-center justify-center">
          <div className="grid w-full gap-10 xl:grid-cols-[0.9fr_0.7fr] xl:items-center">
            <section className="hidden xl:block">
              <p className="text-[11px] uppercase tracking-[0.22em] text-slate-500 dark:text-slate-400">Authentication</p>
              <h1
                className="mt-4 max-w-3xl text-5xl font-semibold tracking-tight text-slate-950 dark:text-slate-50"
                style={{ fontFamily: "var(--font-serif)" }}
              >
                Sign in to supervise agents, decisions, memory, and cost from one operating surface.
              </h1>
              <p className="mt-5 max-w-2xl text-base leading-8 text-slate-600 dark:text-slate-300">
                ForgeGraph opens on organizational state, not on builder chrome. Authentication should feel aligned with that product posture.
              </p>
            </section>

            <div className="flex justify-center xl:justify-end">{children}</div>
          </div>
        </div>
      </main>
    </div>
  );
}
