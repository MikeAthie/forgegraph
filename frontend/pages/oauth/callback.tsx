import { useEffect, useMemo, useReducer } from "react";
import { useRouter } from "next/router";

import ProtectedRoute from "../../components/ProtectedRoute";
import DashboardLayout from "../../components/DashboardLayout";
import { credentialsApi, getApiErrorMessage } from "../../lib/api";
import { Alert, AlertDescription, Button, Card, CardContent, CardHeader, CardTitle, Spinner } from "@/components/ui";

type CallbackStatus = "loading" | "error" | "success";

type OAuthCallbackState = {
  status: CallbackStatus;
  message: string;
};

type OAuthCallbackAction =
  | { type: "failed"; message: string }
  | { type: "succeeded"; message: string };

function oauthCallbackReducer(state: OAuthCallbackState, action: OAuthCallbackAction): OAuthCallbackState {
  switch (action.type) {
    case "failed":
      return { ...state, status: "error", message: action.message };
    case "succeeded":
      return { ...state, status: "success", message: action.message };
    default:
      return state;
  }
}

export default function OAuthCallbackPage() {
  const router = useRouter();
  const { replace } = router;
  const [{ status, message }, dispatch] = useReducer(oauthCallbackReducer, {
    status: "loading",
    message: "Finalizing OAuth connection",
  });

  const callbackPayload = useMemo(() => {
    const code = router.query.code;
    const state = router.query.state;
    const error = router.query.error;
    const errorDescription = router.query.error_description;
    return {
      code: typeof code === "string" ? code : "",
      state: typeof state === "string" ? state : "",
      error: typeof error === "string" ? error : "",
      errorDescription: typeof errorDescription === "string" ? errorDescription : "",
    };
  }, [router.query.code, router.query.error, router.query.error_description, router.query.state]);

  useEffect(() => {
    if (!router.isReady) {
      return;
    }
    if (callbackPayload.error) {
      dispatch({
        type: "failed",
        message: callbackPayload.errorDescription
          ? `${callbackPayload.error}: ${callbackPayload.errorDescription}`
          : callbackPayload.error,
      });
      return;
    }
    if (!callbackPayload.code || !callbackPayload.state) {
      dispatch({ type: "failed", message: "OAuth callback is missing code or state." });
      return;
    }

    let cancelled = false;
    let redirectTimeoutId: ReturnType<typeof setTimeout> | undefined;
    const complete = async () => {
      try {
        await credentialsApi.completeOAuthCallback({
          code: callbackPayload.code,
          state: callbackPayload.state,
        });
        if (cancelled) return;
        dispatch({ type: "succeeded", message: "OAuth credential connected. Redirecting to credentials" });
        redirectTimeoutId = setTimeout(() => {
          void replace("/credentials");
        }, 900);
      } catch (err: unknown) {
        if (cancelled) return;
        dispatch({ type: "failed", message: getApiErrorMessage(err, "Failed to complete OAuth callback.") });
      }
    };
    void complete();
    return () => {
      cancelled = true;
      if (redirectTimeoutId !== undefined) {
        clearTimeout(redirectTimeoutId);
      }
    };
  }, [
    callbackPayload.code,
    callbackPayload.error,
    callbackPayload.errorDescription,
    callbackPayload.state,
    replace,
    router,
    router.isReady,
  ]);

  return (
    <ProtectedRoute>
      <DashboardLayout>
        <Card className="max-w-2xl">
          <CardHeader>
            <CardTitle>OAuth callback</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {status === "loading" && (
              <div className="flex items-center gap-2 text-muted-foreground">
                <Spinner className="size-5" />
                {message}
              </div>
            )}
            {status === "success" && (
              <Alert>
                <AlertDescription>{message}</AlertDescription>
              </Alert>
            )}
            {status === "error" && (
              <>
                <Alert variant="destructive">
                  <AlertDescription>{message}</AlertDescription>
                </Alert>
                <Button onClick={() => void replace("/credentials")}>Back to credentials</Button>
              </>
            )}
          </CardContent>
        </Card>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
