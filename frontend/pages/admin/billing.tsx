import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

import DashboardLayout from "../../components/DashboardLayout";
import ProtectedRoute from "../../components/ProtectedRoute";
import { useAuth } from "../../contexts/AuthContext";
import {
  analyticsApi,
  billingApi,
  type BillingPlan,
  type BillingSubscription,
  type LLMBudgetStatus,
  type LLMQuotaStatus,
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
  const [budget, setBudget] = useState<LLMBudgetStatus | null>(null);
  const [quota, setQuota] = useState<LLMQuotaStatus | null>(null);
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
        const [plansResponse, subscriptionResponse, budgetResponse, quotaResponse] = await Promise.all([
          billingApi.listPlans(),
          billingApi.getSubscription(),
          analyticsApi.getLLMBudget(),
          analyticsApi.getLLMQuota(),
        ]);
        setPlans(plansResponse);
        setSubscription(subscriptionResponse);
        setBudget(budgetResponse);
        setQuota(quotaResponse);
      } catch (err: any) {
        setError(getApiErrorMessage(err, "Failed to load billing data."));
      } finally {
        setLoading(false);
      }
    };

    void load();
  }, [canManage]);

  const activeEntitlements = useMemo(() => Object.entries(subscription?.plan?.entitlements ?? {}), [subscription]);

  const formatEntitlementLabel = (key: string) =>
    key
      .replace(/^max_/, "")
      .replace(/_/g, " ")
      .replace(/\busd\b/i, "USD")
      .replace(/\bllm\b/i, "LLM")
      .replace(/\b\w/g, (match) => match.toUpperCase());

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
      <ProtectedRoute>
        <DashboardLayout>
          <div className="mx-auto max-w-2xl p-8">
            <Alert variant="destructive">
              <AlertDescription>You do not have access to manage billing.</AlertDescription>
            </Alert>
          </div>
        </DashboardLayout>
      </ProtectedRoute>
    );
  }

  if (loading) {
    return (
      <ProtectedRoute>
        <DashboardLayout>
          <div className="flex h-[70vh] items-center justify-center">
            <Spinner size="lg" />
          </div>
        </DashboardLayout>
      </ProtectedRoute>
    );
  }

  return (
    <ProtectedRoute>
      <DashboardLayout>
        <div className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-4 py-8">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <h1 className="text-2xl font-semibold text-foreground">Usage And Billing</h1>
              <p className="text-sm text-muted-foreground">Choose a plan and manage company operating usage.</p>
            </div>
            <Button asChild variant="outline">
              <Link href="/admin/operations">View policies and retention</Link>
            </Button>
          </div>

          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          <Card>
            <CardHeader>
              <CardTitle>Current Subscription</CardTitle>
              <CardDescription>Plan status, renewal, and operating access information.</CardDescription>
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
                          Opening
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

          <div className="grid gap-4 lg:grid-cols-[1.2fr_1fr]">
            <Card>
              <CardHeader>
                <CardTitle>Plan entitlements</CardTitle>
                <CardDescription>
                  Commercial ceilings from the active plan. These are separate from tenant quota and budget settings.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {activeEntitlements.length > 0 ? (
                  activeEntitlements.map(([key, value]) => (
                    <div
                      key={key}
                      className="flex items-center justify-between rounded-xl border border-border/40 bg-muted/30 px-3 py-2 text-sm"
                    >
                      <span className="text-muted-foreground">{formatEntitlementLabel(key)}</span>
                      <span className="font-semibold">{String(value)}</span>
                    </div>
                  ))
                ) : (
                  <p className="text-sm text-muted-foreground">
                    No active plan entitlements found. Budget and quota controls can still block runs independently.
                  </p>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Operating Guardrails</CardTitle>
                <CardDescription>Use this stack when explaining why an operation was blocked.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                <div className="rounded-xl border border-border/40 bg-muted/30 p-3">
                  <p className="font-medium">1. Plan entitlement</p>
                  <p className="mt-1 text-muted-foreground">
                    Commercial ceiling from the active plan, such as max monthly operations or token volume.
                  </p>
                </div>
                <div className="rounded-xl border border-border/40 bg-muted/30 p-3">
                  <p className="font-medium">2. Tenant quota</p>
                  <p className="mt-1 text-muted-foreground">Operator-set token or cost cap for this workspace.</p>
                  <p className="mt-2 text-xs text-muted-foreground">
                    Tokens:{" "}
                    {quota?.quota?.monthly_token_limit != null
                      ? `${quota.quota.monthly_token_limit} / used ${quota.usage.month_total_tokens}`
                      : "Not set"}
                  </p>
                </div>
                <div className="rounded-xl border border-border/40 bg-muted/30 p-3">
                  <p className="font-medium">3. Budget</p>
                  <p className="mt-1 text-muted-foreground">
                    Spend threshold for this tenant. Useful for warnings and explicit cost blocking.
                  </p>
                  <p className="mt-2 text-xs text-muted-foreground">
                    {budget?.budget?.monthly_limit_usd != null
                      ? `$${budget.budget.monthly_limit_usd} / used $${budget.usage.month_cost_usd}`
                      : "Not set"}
                  </p>
                </div>
              </CardContent>
            </Card>
          </div>

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
                        Redirecting
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
      </DashboardLayout>
    </ProtectedRoute>
  );
}
