import { useEffect, useRef } from "react";

import { authApi } from "@/lib/api";

type RunLiveMessage = {
  type?: string;
  event_type?: string;
  event_id?: string;
  state_version?: number;
  payload?: {
    resync_required?: boolean;
    full_resync_required?: boolean;
    replay_supported?: boolean;
    latest_state_version?: number;
  };
  event?: {
    type?: string;
    event_type?: string;
  };
  data?: {
    type?: string;
    event_type?: string;
  };
};

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

function websocketBaseUrl() {
  const apiBase = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
  const parsed = new URL(apiBase);
  parsed.protocol = parsed.protocol === "https:" ? "wss:" : "ws:";
  parsed.pathname = "";
  parsed.search = "";
  parsed.hash = "";
  return parsed.toString().replace(/\/$/, "");
}

function messageType(message: RunLiveMessage) {
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

function numericStateVersion(value: unknown): number | null {
  if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) {
    return null;
  }
  return Math.trunc(value);
}

export function useRunLiveUpdates(
  runId: string | null | undefined,
  onBackendStateInvalidated: () => void | Promise<void>,
  options?: { enabled?: boolean },
) {
  const callbackRef = useRef(onBackendStateInvalidated);

  useEffect(() => {
    callbackRef.current = onBackendStateInvalidated;
  }, [onBackendStateInvalidated]);

  useEffect(() => {
    if (!runId || options?.enabled === false || typeof window === "undefined") {
      return;
    }

    let closed = false;
    let socket: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    const lastEventIdRef = { current: "" };
    const lastStateVersionRef = { current: 0 };

    const connect = async () => {
      try {
        const ticket = await authApi.issueWsTicket();
        if (closed) {
          return;
        }

        const params = new URLSearchParams({
          ticket: ticket.ticket,
          event_level: "default",
          event_types: Array.from(RUN_INVALIDATION_MESSAGES).join(","),
        });
        if (lastEventIdRef.current) {
          params.set("last_event_id", lastEventIdRef.current);
        }
        if (lastStateVersionRef.current > 0) {
          params.set("last_seen_state_version", String(lastStateVersionRef.current));
        }

        socket = new WebSocket(`${websocketBaseUrl()}/ws/runs/${encodeURIComponent(runId)}/?${params.toString()}`);
        socket.onmessage = (event) => {
          try {
            const parsed = JSON.parse(String(event.data ?? "{}")) as RunLiveMessage;
            const parsedType = messageType(parsed);
            if (parsed.event_id) {
              lastEventIdRef.current = parsed.event_id;
            }
            const messageStateVersion =
              numericStateVersion(parsed.state_version) ?? numericStateVersion(parsed.payload?.latest_state_version);
            if (messageStateVersion !== null) {
              lastStateVersionRef.current = Math.max(lastStateVersionRef.current, messageStateVersion);
            }
            if (parsedType === "heartbeat") {
              socket?.send(
                JSON.stringify({
                  type: "pong",
                  event_id: lastEventIdRef.current,
                  last_seen_state_version: lastStateVersionRef.current,
                }),
              );
              return;
            }
            if (parsedType === "connection_established") {
              if (parsed.payload?.resync_required || parsed.payload?.full_resync_required) {
                void callbackRef.current();
              }
              return;
            }
            if (parsedType === "replay_complete") {
              return;
            }
            if (RUN_INVALIDATION_MESSAGES.has(parsedType)) {
              void callbackRef.current();
            }
          } catch {
            // Ignore malformed transport messages; the next valid backend update will refetch state.
          }
        };
        socket.onclose = () => {
          if (!closed) {
            reconnectTimer = window.setTimeout(() => void connect(), 2000);
          }
        };
      } catch {
        if (!closed) {
          reconnectTimer = window.setTimeout(() => void connect(), 2000);
        }
      }
    };

    void connect();

    return () => {
      closed = true;
      if (reconnectTimer) {
        window.clearTimeout(reconnectTimer);
      }
      socket?.close();
    };
  }, [options?.enabled, runId]);
}
