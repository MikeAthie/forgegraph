import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

import OsShell from "./shell/OsShell";

type DashboardLayoutProps = {
  children: ReactNode;
  mainClassName?: string;
  inspector?: ReactNode;
  inspectorClassName?: string;
};

export default function DashboardLayout({
  children,
  mainClassName,
  inspector,
  inspectorClassName,
}: DashboardLayoutProps) {
  return (
    <OsShell mainClassName={cn("max-w-[1680px]", mainClassName)}>
      {inspector ? (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
          <div className="min-w-0">{children}</div>
          <aside className={cn("min-w-0", inspectorClassName)}>{inspector}</aside>
        </div>
      ) : (
        children
      )}
    </OsShell>
  );
}
