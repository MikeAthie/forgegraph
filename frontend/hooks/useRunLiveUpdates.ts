import { useCallback } from "react";

import { useStateFeed, type StateFeedMessage } from "@/hooks/useStateFeed";

const RUN_INVALIDATION_MESSAGES = new Set([
  "connection_established",
  "resync_required",
  "full_resync_required",
  "run_started",
  "run_updated",
  "run_paused",
  "run_resumed",
  "run_completed",
  "run_failed",
  "run_canceled",
  "node_started",
  "node_completed",
  "node_failed",
  "node_updated",
  "decision_required",
  "decision_resolved",
  "cost_update",
  "cost_updated",
]);

function messageType(message: StateFeedMessage) {
  return (
    message.type ||
    message.event_type ||
    message.event?.type ||
    message.event?.event_type ||
    message.data?.type ||
    message.data?.event_type ||
    ""
  );
}

export function useRunLiveUpdates(
  runId: string | null | undefined,
  onBackendStateInvalidated: () => void | Promise<void>,
  options?: { enabled?: boolean },
) {
  const handleEvent = useCallback(
    (event: StateFeedMessage) => {
      if (RUN_INVALIDATION_MESSAGES.has(messageType(event))) {
        void onBackendStateInvalidated();
      }
    },
    [onBackendStateInvalidated],
  );

  return useStateFeed({
    scope: "run",
    runId,
    enabled: options?.enabled,
    eventLevel: "default",
    eventTypes: Array.from(RUN_INVALIDATION_MESSAGES),
    onEvent: handleEvent,
    onFullResync: onBackendStateInvalidated,
  });
}
