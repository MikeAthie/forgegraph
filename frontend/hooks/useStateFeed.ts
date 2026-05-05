import { useEffect, useMemo, useRef, useState } from "react";

import { authApi } from "@/lib/api";

export type StateFeedStatus = "idle" | "connecting" | "connected" | "unavailable";

export type StateFeedMessage = {
  type?: string;
  event_type?: string;
  event_id?: string;
  organization_id?: string;
  run_id?: string;
  state_version?: number;
  requires_refetch?: boolean;
  reason?: string;
  resource?: {
    type?: string;
    id?: string;
  };
  payload?: {
    resync_required?: boolean;
    full_resync_required?: boolean;
    replay_supported?: boolean;
    latest_state_version?: number;
    reason?: string;
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

type StateFeedOptions =
  | {
      scope: "run";
      runId: string | null | undefined;
      organizationId?: never;
      eventLevel?: string;
      eventTypes?: string[];
      enabled?: boolean;
      lastSeenStateVersion?: number | null;
      onEvent: (event: StateFeedMessage) => void | Promise<void>;
      onFullResync?: (event: StateFeedMessage) => void | Promise<void>;
    }
  | {
      scope: "organization";
      organizationId: string | null | undefined;
      runId?: never;
      eventLevel?: never;
      eventTypes?: string[];
      enabled?: boolean;
      lastSeenStateVersion?: number | null;
      onEvent: (event: StateFeedMessage) => void | Promise<void>;
      onFullResync?: (event: StateFeedMessage) => void | Promise<void>;
    };

function websocketBaseUrl() {
  const apiBase = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
  const parsed = new URL(apiBase);
  parsed.protocol = parsed.protocol === "https:" ? "wss:" : "ws:";
  parsed.pathname = "";
  parsed.search = "";
  parsed.hash = "";
  return parsed.toString().replace(/\/$/, "");
}

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

function numericStateVersion(value: unknown): number | null {
  if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) {
    return null;
  }
  return Math.trunc(value);
}

function targetPath(options: StateFeedOptions) {
  if (options.scope === "run") {
    return options.runId ? `/ws/runs/${encodeURIComponent(options.runId)}/` : null;
  }
  return options.organizationId ? `/ws/organizations/${encodeURIComponent(options.organizationId)}/state/` : null;
}

export function useStateFeed(options: StateFeedOptions) {
  const [status, setStatus] = useState<StateFeedStatus>("idle");
  const eventTypesKey = useMemo(() => (options.eventTypes ?? []).join(","), [options.eventTypes]);
  const onEventRef = useRef(options.onEvent);
  const onFullResyncRef = useRef(options.onFullResync);

  useEffect(() => {
    onEventRef.current = options.onEvent;
    onFullResyncRef.current = options.onFullResync;
  }, [options.onEvent, options.onFullResync]);

  useEffect(() => {
    const path = targetPath(options);
    if (!path || options.enabled === false || typeof window === "undefined") {
      setStatus("idle");
      return;
    }

    let closed = false;
    let socket: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    const lastEventIdRef = { current: "" };
    const lastStateVersionRef = {
      current: Math.max(Math.trunc(options.lastSeenStateVersion ?? 0), 0),
    };
    const eventTypes = eventTypesKey
      .split(",")
      .map((eventType) => eventType.trim())
      .filter(Boolean);

    const connect = async () => {
      setStatus("connecting");
      try {
        const ticket = await authApi.issueWsTicket();
        if (closed) {
          return;
        }

        const params = new URLSearchParams({
          ticket: ticket.ticket,
        });
        if (options.scope === "run") {
          params.set("event_level", options.eventLevel ?? "default");
        }
        if (eventTypes.length > 0) {
          params.set("event_types", eventTypes.join(","));
        }
        if (lastEventIdRef.current) {
          params.set("last_event_id", lastEventIdRef.current);
        }
        if (lastStateVersionRef.current > 0) {
          params.set("last_seen_state_version", String(lastStateVersionRef.current));
        }

        socket = new WebSocket(`${websocketBaseUrl()}${path}?${params.toString()}`);
        socket.onopen = () => {
          setStatus("connected");
          if (lastStateVersionRef.current > 0) {
            socket?.send(
              JSON.stringify({
                type: "resume",
                event_id: lastEventIdRef.current,
                last_seen_state_version: lastStateVersionRef.current,
              }),
            );
          }
        };
        socket.onmessage = (event) => {
          try {
            const parsed = JSON.parse(String(event.data ?? "{}")) as StateFeedMessage;
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
                void onFullResyncRef.current?.(parsed);
              }
              return;
            }
            if (parsedType === "replay_complete") {
              return;
            }
            if (parsedType === "full_resync_required") {
              void onFullResyncRef.current?.(parsed);
              return;
            }
            void onEventRef.current(parsed);
          } catch {
            // Malformed transport messages are ignored; backend API refetch remains the source of truth.
          }
        };
        socket.onclose = () => {
          if (!closed) {
            setStatus("unavailable");
            reconnectTimer = window.setTimeout(() => void connect(), 2000);
          }
        };
      } catch {
        if (!closed) {
          setStatus("unavailable");
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
  }, [
    eventTypesKey,
    options.enabled,
    options.eventLevel,
    options.lastSeenStateVersion,
    options.organizationId,
    options.runId,
    options.scope,
  ]);

  return { status };
}

export const stateFeedInternalsForTest = {
  messageType,
  numericStateVersion,
  websocketBaseUrl,
};
