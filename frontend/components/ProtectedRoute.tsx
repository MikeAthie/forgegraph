import { useEffect, type ReactNode } from "react";
import { useRouter } from "next/router";

import { useAuth } from "../contexts/AuthContext";
import { Spinner } from "@/components/ui";

export default function ProtectedRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated, loading } = useAuth();
  const router = useRouter();

  const { push } = router;
  useEffect(() => {
    if (!loading && !isAuthenticated) {
      push("/login");
    }
  }, [loading, isAuthenticated, push]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background" aria-live="polite">
        <div className="flex flex-col items-center gap-y-4">
          <Spinner size="lg" label="Loading workspace" />
          <p className="text-sm text-muted-foreground">Loading workspace</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background" aria-live="polite">
        <div className="flex flex-col items-center gap-y-4">
          <Spinner size="lg" label="Redirecting to sign in" />
          <p className="text-sm text-muted-foreground">Redirecting to sign in</p>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
