"use client";

import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface WizardStepProps {
  title: string;
  description?: string;
  children: ReactNode;
  className?: string;
}

export function WizardStep({ title, description, children, className }: WizardStepProps) {
  return (
    <div className={cn("flex flex-col h-full", className)}>
      <div className="px-6 py-4 border-b">
        <h2 className="text-lg font-semibold">{title}</h2>
        {description && <p className="text-sm text-muted-foreground mt-1">{description}</p>}
      </div>
      <div className="flex-1 overflow-auto px-6 py-4">{children}</div>
    </div>
  );
}

export default WizardStep;
