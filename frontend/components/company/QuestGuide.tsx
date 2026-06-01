import { useEffect, useMemo, useReducer } from "react";
import { ArrowRight, Sparkles, X } from "lucide-react";

import { Button } from "@/components/ui";

type QuestGuideStep = {
  id: string;
  targetId: string;
  title: string;
  description: string;
  placement?: "top" | "right" | "bottom" | "left";
};

type QuestGuideProps = {
  active: boolean;
  title: string;
  steps: QuestGuideStep[];
  onSkip: () => void;
  onComplete: () => void;
};

type RectState = {
  top: number;
  left: number;
  width: number;
  height: number;
};

type QuestGuideState = {
  stepIndex: number;
  targetRect: RectState | null;
};

type QuestGuideAction = { type: "reset" } | { type: "next" } | { type: "target"; rect: RectState | null };

const initialQuestGuideState: QuestGuideState = {
  stepIndex: 0,
  targetRect: null,
};

function questGuideReducer(state: QuestGuideState, action: QuestGuideAction): QuestGuideState {
  switch (action.type) {
    case "reset":
      return initialQuestGuideState;
    case "next":
      return { ...state, stepIndex: state.stepIndex + 1 };
    case "target":
      return { ...state, targetRect: action.rect };
    default:
      return state;
  }
}

function getBubblePosition(rect: RectState, placement: QuestGuideStep["placement"]) {
  const bubbleWidth = 320;
  const gap = 16;
  const viewportWidth = typeof window === "undefined" ? 1440 : window.innerWidth;
  const viewportHeight = typeof window === "undefined" ? 900 : window.innerHeight;

  const clampX = (value: number) => Math.min(Math.max(16, value), Math.max(16, viewportWidth - bubbleWidth - 16));
  const clampY = (value: number) => Math.min(Math.max(16, value), Math.max(16, viewportHeight - 220));

  switch (placement) {
    case "top":
      return {
        left: clampX(rect.left + rect.width / 2 - bubbleWidth / 2),
        top: clampY(rect.top - 220 - gap),
      };
    case "left":
      return {
        left: clampX(rect.left - bubbleWidth - gap),
        top: clampY(rect.top + rect.height / 2 - 110),
      };
    case "right":
      return {
        left: clampX(rect.left + rect.width + gap),
        top: clampY(rect.top + rect.height / 2 - 110),
      };
    default:
      return {
        left: clampX(rect.left + rect.width / 2 - bubbleWidth / 2),
        top: clampY(rect.top + rect.height + gap),
      };
  }
}

export function QuestGuide({ active, title, steps, onSkip, onComplete }: QuestGuideProps) {
  const [{ stepIndex, targetRect }, dispatchGuide] = useReducer(questGuideReducer, initialQuestGuideState);
  const currentStep = steps[stepIndex];

  useEffect(() => {
    if (!active) {
      dispatchGuide({ type: "reset" });
    }
  }, [active]);

  useEffect(() => {
    if (!active || !currentStep) {
      dispatchGuide({ type: "target", rect: null });
      return;
    }

    const selector = `[data-guide-id="${currentStep.targetId}"]`;
    const target = document.querySelector(selector) as HTMLElement | null;
    if (!target) {
      dispatchGuide({ type: "target", rect: null });
      return;
    }

    const update = () => {
      const rect = target.getBoundingClientRect();
      dispatchGuide({
        type: "target",
        rect: { top: rect.top, left: rect.left, width: rect.width, height: rect.height },
      });
    };

    target.scrollIntoView({ block: "center", inline: "nearest", behavior: "smooth" });
    update();

    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    return () => {
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
    };
  }, [active, currentStep]);

  const bubblePosition = useMemo(
    () => (targetRect && currentStep ? getBubblePosition(targetRect, currentStep.placement) : null),
    [currentStep, targetRect],
  );

  if (!active || !currentStep || !targetRect || !bubblePosition) {
    return null;
  }

  const isLastStep = stepIndex === steps.length - 1;

  return (
    <div data-testid="quest-guide-overlay" className="pointer-events-none fixed inset-0 z-[70]">
      <div className="absolute inset-0 bg-zinc-950/10 backdrop-blur-[1px]" />
      <div
        className="pointer-events-none fixed rounded-[1.6rem] border-2 border-sky-500/70 shadow-[0_0_0_9999px_rgba(15,23,42,0.14)] transition-[top,left,width,height,border-color,box-shadow,opacity] motion-reduce:transition-none"
        style={{
          top: Math.max(8, targetRect.top - 8),
          left: Math.max(8, targetRect.left - 8),
          width: targetRect.width + 16,
          height: targetRect.height + 16,
        }}
      />

      <div
        className="pointer-events-auto fixed w-[320px] rounded-[1.6rem] border border-zinc-900/10 bg-white p-5 shadow-[0_32px_80px_-34px_rgba(15,23,42,0.45)] dark:border-white/10 dark:bg-zinc-950"
        style={bubblePosition}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="flex size-8 items-center justify-center rounded-full bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-200">
              <Sparkles className="size-4" />
            </span>
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-500 dark:text-zinc-400">
                {title}
              </p>
              <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                Step {stepIndex + 1} of {steps.length}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onSkip}
            className="rounded-full border border-zinc-900/10 p-2 text-zinc-500 transition-colors hover:border-zinc-900 hover:text-zinc-900 dark:border-white/10 dark:text-zinc-400 dark:hover:border-white/30 dark:hover:text-white"
            aria-label="Skip guide"
          >
            <X className="size-4" />
          </button>
        </div>

        <div className="mt-4">
          <p className="text-sm font-semibold text-zinc-950 dark:text-zinc-50">{currentStep.title}</p>
          <p className="mt-2 text-sm leading-6 text-zinc-600 dark:text-zinc-300">{currentStep.description}</p>
        </div>

        <div className="mt-5 flex items-center justify-between gap-3">
          <button
            type="button"
            onClick={onSkip}
            className="text-sm font-medium text-zinc-500 transition-colors hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
          >
            Skip guide
          </button>
          <Button
            size="sm"
            className="rounded-full"
            onClick={() => {
              if (isLastStep) {
                onComplete();
                return;
              }
              dispatchGuide({ type: "next" });
            }}
          >
            {isLastStep ? "Finish" : "Next"}
            <ArrowRight className="size-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
