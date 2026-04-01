"use client";

import { CheckIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { useWizard } from "@/contexts/WizardContext";

export function WizardProgress() {
  const { state, steps, goToStep } = useWizard();

  return (
    <div className="flex items-center justify-center gap-2 px-4 py-3 border-b bg-muted/30">
      {steps.map((step, index) => {
        const isActive = index === state.currentStep;
        const isCompleted = state.completedSteps.has(index);
        const isSkipped = state.skippedSteps.has(index);
        const canNavigate = isCompleted || index <= state.currentStep;

        return (
          <div key={step.id} className="flex items-center">
            {index > 0 && (
              <div
                className={cn(
                  "w-8 h-0.5 mx-1",
                  isCompleted || index <= state.currentStep ? "bg-primary" : "bg-muted-foreground/30",
                )}
              />
            )}
            <button
              type="button"
              onClick={() => canNavigate && goToStep(index)}
              disabled={!canNavigate}
              className={cn(
                "flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium transition-all",
                "focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2",
                isActive && "bg-primary text-primary-foreground",
                isCompleted && !isActive && "bg-primary/20 text-primary hover:bg-primary/30",
                isSkipped && !isActive && "bg-muted text-muted-foreground",
                !isActive && !isCompleted && !isSkipped && "bg-muted/50 text-muted-foreground",
                canNavigate && !isActive && "cursor-pointer",
                !canNavigate && "cursor-not-allowed opacity-50",
              )}
              title={step.title}
            >
              <span
                className={cn(
                  "flex items-center justify-center w-5 h-5 rounded-full text-[10px] font-bold",
                  isActive && "bg-primary-foreground/20",
                  isCompleted && !isActive && "bg-primary text-primary-foreground",
                )}
              >
                {isCompleted ? <CheckIcon className="w-3 h-3" /> : index + 1}
              </span>
              <span className="hidden sm:inline">{step.title}</span>
            </button>
          </div>
        );
      })}
    </div>
  );
}

export default WizardProgress;
