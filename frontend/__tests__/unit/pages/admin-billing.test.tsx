import { render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";

import { useAuth } from "@/contexts/AuthContext";
import * as api from "@/lib/api";
import AdminBillingPage from "@/pages/admin/billing";

jest.mock("@/contexts/AuthContext");
jest.mock("@/components/DashboardLayout", () => ({
  __esModule: true,
  default: ({ children }: { children: ReactNode }) => <div data-testid="dashboard-layout">{children}</div>,
}));
jest.mock("@/components/ProtectedRoute", () => ({
  __esModule: true,
  default: ({ children }: { children: ReactNode }) => <>{children}</>,
}));
jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children, ...props }: any) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

const mockUseAuth = useAuth as jest.MockedFunction<typeof useAuth>;

describe("AdminBillingPage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseAuth.mockReturnValue({
      user: {
        id: "u1",
        email: "owner@example.com",
        organization_role: "owner",
      },
      isAuthenticated: true,
      loading: false,
      error: null,
      login: jest.fn(),
      register: jest.fn(),
      logout: jest.fn(),
      checkAuth: jest.fn(),
      clearError: jest.fn(),
    });
  });

  it("renders plan entitlements alongside quota and budget guardrails", async () => {
    jest.spyOn(api.billingApi, "listPlans").mockResolvedValue([
      {
        id: "plan-1",
        name: "Starter",
        stripe_price_id: "price_123",
        stripe_product_id: "prod_123",
        entitlements: { max_runs_per_month: 50, max_monthly_tokens: 100000 },
      },
    ]);
    jest.spyOn(api.billingApi, "getSubscription").mockResolvedValue({
      plan: {
        id: "plan-1",
        name: "Starter",
        entitlements: { max_runs_per_month: 50, max_monthly_tokens: 100000 },
      },
      status: "active",
      current_period_end: "2026-03-31T00:00:00Z",
      cancel_at_period_end: false,
      stripe_customer_id: "cus_123",
      stripe_subscription_id: "sub_123",
    });
    jest.spyOn(api.analyticsApi, "getLLMBudget").mockResolvedValue({
      budget: { monthly_limit_usd: 200, warning_threshold_pct: 0.8 },
      usage: { month_cost_usd: 48 },
      warning_threshold_usd: 160,
      warning: false,
      over_budget: false,
    });
    jest.spyOn(api.analyticsApi, "getLLMQuota").mockResolvedValue({
      quota: { monthly_token_limit: 120000, monthly_cost_limit_usd: 250 },
      usage: { month_total_tokens: 18000, month_cost_usd: 48 },
    });

    render(<AdminBillingPage />);

    await waitFor(() => {
      expect(screen.getByText(/plan entitlements/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/operating guardrails/i)).toBeInTheDocument();
    expect(screen.getByText(/^1\. Plan entitlement$/i)).toBeInTheDocument();
    expect(screen.getByText(/^2\. Tenant quota$/i)).toBeInTheDocument();
    expect(screen.getByText(/^3\. Budget$/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /view policies and retention/i })).toHaveAttribute(
      "href",
      "/admin/operations",
    );
    expect(screen.getByText("100000")).toBeInTheDocument();
    expect(screen.getByText(/120000 \/ used 18000/i)).toBeInTheDocument();
    expect(screen.getByText(/\$200 \/ used \$48/i)).toBeInTheDocument();
  });
});
