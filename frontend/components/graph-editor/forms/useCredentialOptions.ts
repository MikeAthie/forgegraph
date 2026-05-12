"use client";

import { useEffect, useReducer } from "react";

import { credentialsApi, getApiErrorMessage, type Credential } from "@/lib/api";

type CredentialOptionsState = {
  credentials: Credential[];
  loading: boolean;
  error: string | null;
};

type CredentialOptionsAction =
  | { type: "load-start" }
  | { type: "load-success"; credentials: Credential[] }
  | { type: "load-error"; error: string };

const initialCredentialOptionsState: CredentialOptionsState = {
  credentials: [],
  loading: false,
  error: null,
};

function credentialOptionsReducer(
  state: CredentialOptionsState,
  action: CredentialOptionsAction,
): CredentialOptionsState {
  switch (action.type) {
    case "load-start":
      return { ...state, loading: true, error: null };
    case "load-success":
      return { credentials: action.credentials, loading: false, error: null };
    case "load-error":
      return { ...state, loading: false, error: action.error };
    default:
      return state;
  }
}

export function useCredentialOptions() {
  const [state, dispatch] = useReducer(credentialOptionsReducer, initialCredentialOptionsState);

  useEffect(() => {
    let cancelled = false;

    const fetchCredentials = async () => {
      dispatch({ type: "load-start" });
      try {
        const credentials = await credentialsApi.list();
        if (!cancelled) {
          dispatch({ type: "load-success", credentials });
        }
      } catch (err: unknown) {
        if (!cancelled) {
          dispatch({ type: "load-error", error: getApiErrorMessage(err, "Failed to load credentials.") });
        }
      }
    };

    void fetchCredentials();

    return () => {
      cancelled = true;
    };
  }, []);

  return state;
}
