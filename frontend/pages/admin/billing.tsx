import { useEffect, useState } from "react";

import { useAuth } from "../../contexts/AuthContext";
import {
  billingApi,
  type BillingPlan,
  type BillingSubscription,
  getApiErrorMessage,
} from "../../lib/api";
import {
  Alert,
  AlertDescription,
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Spinner,
} from "@/components/ui";

export default function AdminBillingPage() {
  const { user } = useAuth();
  const [plans, setPlans] = useState<BillingPlan[]>([]);
  const [subscription, setSubscription] = useState<BillingSubscription | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const canManage = user?.organization_role === "owner" || user?.organization_role === "admin";

  useEffect(() => {
    if (!canManage) {
      return;
    }

    const load = async () => {
      try {
        const [plansResponse, subscriptionResponse] = await Promise.all([
          billingApi.listPlans(),
          billingApi.getSubscription(),
        ]);
        setPlans(plansResponse);
        setSubscription(subscriptionResponse);
      } catch (err: any) {
        setError(getApiErrorMessage(err, "Failed to load billing data."));
      } finally {
        setLoading(false);
      }
    };

    void load();
  }, [canManage]);

  const handleCheckout = async (planId: string) => {
    setError(null);
    setActionLoading(planId);
    try {
      const url = await billingApi.createCheckout(planId);
      window.location.href = url;
    } catch (err: any) {
      setError(getApiErrorMessage(err, "Failed to start checkout."));
    } finally {
      setActionLoading(null);
    }
  };

  const handlePortal = async () => {
    setError(null);
    setActionLoading("portal");
    try {
      const url = await billingApi.createPortal();
      window.location.href = url;
    } catch (err: any) {
      setError(getApiErrorMessage(err, "Failed to open billing portal."));
    } finally {
      setActionLoading(null);
    }
  };

  if (!canManage) {
    return (
      <div className="mx-auto max-w-2xl p-8">
        <Alert variant="destructive">
          <AlertDescription>You do not have access to manage billing.</AlertDescription>
        </Alert>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex h-[70vh] items-center justify-center">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-4 py-8">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">Billing</h1>
        <p className="text-sm text-muted-foreground">
          Choose a plan and manage your subscription.
        </p>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Current Subscription</CardTitle>
          <CardDescription>Plan status and renewal information.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {subscription ? (
            <>
              <div className="flex items-center gap-3">
                <Badge variant="outline">
                  {subscription.plan?.name || "No plan"} · {subscription.status}
                </Badge>
                {subscription.current_period_end && (
                  <span className="text-xs text-muted-foreground">
                    Renews {new Date(subscription.current_period_end).toLocaleDateString()}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-3">
                <Button onClick={handlePortal} disabled={actionLoading === "portal"}>
                  {actionLoading === "portal" ? (
                    <>
                      <Spinner size="xs" className="mr-2" />
                      Opening...
                    </>
                  ) : (
                    "Manage Billing"
                  )}
                </Button>
              </div>
            </>
          ) : (
            <p className="text-sm text-muted-foreground">No active subscription yet.</p>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        {plans.map((plan) => (
          <Card key={plan.id} className="flex flex-col">
            <CardHeader>
              <CardTitle>{plan.name}</CardTitle>
              <CardDescription>
                Entitlements:{" "}
                {Object.keys(plan.entitlements || {}).length > 0
                  ? Object.entries(plan.entitlements)
                      .map(([key, value]) => `${key}: ${value}`)
                      .join(", ")
                  : "Standard access"}
              </CardDescription>
            </CardHeader>
            <CardContent className="mt-auto">
              <Button
                className="w-full"
                onClick={() => handleCheckout(plan.id)}
                disabled={actionLoading === plan.id}
              >
                {actionLoading === plan.id ? (
                  <>
                    <Spinner size="xs" className="mr-2" />
                    Redirecting...
                  </>
                ) : (
                  "Choose Plan"
                )}
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
