import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

import Header from "./Header";

type DashboardLayoutProps = {
  children: ReactNode;
  mainClassName?: string;
};

export default function DashboardLayout({ children, mainClassName }: DashboardLayoutProps) {
  return (
    <div className="min-h-screen bg-background">
      <div className="fixed inset-0 -z-10 overflow-hidden">
        <div className="absolute -top-40 left-1/3 h-96 w-96 rounded-full bg-primary/15 blur-3xl" />
        <div className="absolute top-1/4 -right-40 h-[32rem] w-[32rem] rounded-full bg-violet-500/10 blur-3xl" />
        <div className="absolute -bottom-40 left-0 h-[28rem] w-[28rem] rounded-full bg-fuchsia-500/10 blur-3xl" />

        <div
          className="absolute inset-0 opacity-[0.03]"
          style={{
            backgroundImage: `url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32' width='32' height='32' fill='none' stroke='rgb(99 102 241 / 0.35)'%3e%3cpath d='M0 .5H31.5V32'/%3e%3c/svg%3e")`,
          }}
        />
      </div>

      <Header />

      <main className={cn("max-w-7xl mx-auto py-8 px-4 sm:px-6 lg:px-8", mainClassName)}>{children}</main>
    </div>
  );
}
