"use client";

import { ChevronLeftIcon, ChevronRightIcon, XIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useWizard } from "@/contexts/WizardContext";
import { cn } from "@/lib/utils";

export interface WizardNavigationProps {
  onComplete?: () => void;
  className?: string;
}

export function WizardNavigation({ onComplete, className }: WizardNavigationProps) {
  const {
    state,
    currentStepConfig,
    nextStep,
    prevStep,
    markStepComplete,
    markStepSkipped,
    exitWizard,
    isFirstStep,
    isLastStep,
  } = useWizard();

  const handleNext = () => {
    markStepComplete();
    if (isLastStep) {
      onComplete?.();
    } else {
      nextStep();
    }
  };

  const handleSkip = () => {
    markStepSkipped();
    nextStep();
  };

  const canSkip = currentStepConfig?.canSkip ?? false;

  return (
    <div
      className={cn(
        "flex items-center justify-between px-6 py-3 border-t bg-muted/30",
        className
      )}
    >
      <div className="flex items-center gap-2">
        <Button
          variant="ghost"
          size="sm"
          onClick={exitWizard}
          className="text-muted-foreground"
        >
          <XIcon className="w-4 h-4 mr-1" />
          Exit
        </Button>
      </div>

      <div className="flex items-center gap-2">
        {!isFirstStep && (
          <Button
            variant="outline"
            size="sm"
            onClick={prevStep}
          >
            <ChevronLeftIcon className="w-4 h-4 mr-1" />
            Back
          </Button>
        )}

        {canSkip && !isLastStep && (
          <Button
            variant="ghost"
            size="sm"
            onClick={handleSkip}
            className="text-muted-foreground"
          >
            Skip
          </Button>
        )}

        <Button
          size="sm"
          onClick={handleNext}
          disabled={!state.canProceed}
        >
          {isLastStep ? (
            "Finish"
          ) : (
            <>
              Next
              <ChevronRightIcon className="w-4 h-4 ml-1" />
            </>
          )}
        </Button>
      </div>
    </div>
  );
}

export default WizardNavigation;
