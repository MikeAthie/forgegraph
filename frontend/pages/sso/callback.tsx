import { useEffect, useMemo, useReducer } from "react";
import { useRouter } from "next/router";

import AuthLayout from "../../components/AuthLayout";
import { authApi } from "../../lib/api";
import { useAuth } from "../../contexts/AuthContext";

export default function SsoCallbackPage() {
  const router = useRouter();
  const { replace } = router;
  const { checkAuth } = useAuth();
  const [exchangeError, setExchangeError] = useReducer((_: string | null, nextError: string | null) => nextError, null);

  const ssoRequest = useMemo(() => {
    if (!router.isReady) {
      return { ready: false as const };
    }

    const { code, state, error: ssoError, error_description } = router.query;
    if (ssoError) {
      return {
        ready: true as const,
        error: typeof error_description === "string" ? error_description : "SSO login failed. Please try again.",
      };
    }

    if (typeof code !== "string" || typeof state !== "string") {
      return { ready: true as const, error: "Missing SSO parameters. Please try again." };
    }

    return { ready: true as const, code, state };
  }, [router.isReady, router.query]);

  useEffect(() => {
    if (!ssoRequest.ready || "error" in ssoRequest) {
      return;
    }

    const exchange = async () => {
      try {
        await authApi.exchangeSsoCode(ssoRequest.code, ssoRequest.state);
        await checkAuth();
        replace("/graphs");
      } catch (err: any) {
        const message = err?.response?.data?.error?.message || "SSO login failed. Please try again.";
        setExchangeError(message);
      }
    };

    void exchange();
  }, [ssoRequest, checkAuth, replace]);

  const error = ssoRequest.ready && "error" in ssoRequest ? ssoRequest.error : exchangeError;

  return (
    <AuthLayout>
      <div className="mx-auto w-full max-w-md text-center">
        <h1 className="text-3xl font-semibold tracking-tight text-zinc-900">Signing you in</h1>
        <p className="mt-3 text-sm text-zinc-600">{error ? "We ran into an issue." : "Completing SSO login"}</p>
        {error && (
          <div className="mt-6 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
            {error}
          </div>
        )}
      </div>
    </AuthLayout>
  );
}
