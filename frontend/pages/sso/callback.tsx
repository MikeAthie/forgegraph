import { useEffect, useState } from "react";
import { useRouter } from "next/router";

import AuthLayout from "../../components/AuthLayout";
import { authApi } from "../../lib/api";
import { useAuth } from "../../contexts/AuthContext";

export default function SsoCallbackPage() {
  const router = useRouter();
  const { checkAuth } = useAuth();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!router.isReady) {
      return;
    }

    const { code, state, error: ssoError, error_description } = router.query;

    if (ssoError) {
      setError(typeof error_description === "string" ? error_description : "SSO login failed. Please try again.");
      return;
    }

    if (typeof code !== "string" || typeof state !== "string") {
      setError("Missing SSO parameters. Please try again.");
      return;
    }

    const exchange = async () => {
      try {
        await authApi.exchangeSsoCode(code, state);
        await checkAuth();
        router.replace("/graphs");
      } catch (err: any) {
        const message = err?.response?.data?.error?.message || "SSO login failed. Please try again.";
        setError(message);
      }
    };

    void exchange();
  }, [router, checkAuth]);

  return (
    <AuthLayout>
      <div className="mx-auto w-full max-w-md text-center">
        <h1 className="text-3xl font-semibold tracking-tight text-slate-900">Signing you in</h1>
        <p className="mt-3 text-sm text-slate-600">{error ? "We ran into an issue." : "Completing SSO login..."}</p>
        {error && (
          <div className="mt-6 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
            {error}
          </div>
        )}
      </div>
    </AuthLayout>
  );
}
