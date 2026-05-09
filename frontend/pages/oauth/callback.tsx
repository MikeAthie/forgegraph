import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/router";

import ProtectedRoute from "../../components/ProtectedRoute";
import DashboardLayout from "../../components/DashboardLayout";
import { credentialsApi, getApiErrorMessage } from "../../lib/api";
import { Alert, AlertDescription, Button, Card, CardContent, CardHeader, CardTitle, Spinner } from "@/components/ui";

type CallbackStatus = "loading" | "error" | "success";

export default function OAuthCallbackPage() {
  const router = useRouter();
  const [status, setStatus] = useState<CallbackStatus>("loading");
  const [message, setMessage] = useState("Finalizing OAuth connection");

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
      setStatus("error");
      setMessage(
        callbackPayload.errorDescription
          ? `${callbackPayload.error}: ${callbackPayload.errorDescription}`
          : callbackPayload.error,
      );
      return;
    }
    if (!callbackPayload.code || !callbackPayload.state) {
      setStatus("error");
      setMessage("OAuth callback is missing code or state.");
      return;
    }

    let cancelled = false;
    const complete = async () => {
      try {
        await credentialsApi.completeOAuthCallback({
          code: callbackPayload.code,
          state: callbackPayload.state,
        });
        if (cancelled) return;
        setStatus("success");
        setMessage("OAuth credential connected. Redirecting to credentials");
        setTimeout(() => {
          void router.replace("/credentials");
        }, 900);
      } catch (err: unknown) {
        if (cancelled) return;
        setStatus("error");
        setMessage(getApiErrorMessage(err, "Failed to complete OAuth callback."));
      }
    };
    void complete();
    return () => {
      cancelled = true;
    };
  }, [
    callbackPayload.code,
    callbackPayload.error,
    callbackPayload.errorDescription,
    callbackPayload.state,
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
                <Spinner className="h-5 w-5" />
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
                <Button onClick={() => void router.replace("/credentials")}>Back to credentials</Button>
              </>
            )}
          </CardContent>
        </Card>
      </DashboardLayout>
    </ProtectedRoute>
  );
}
