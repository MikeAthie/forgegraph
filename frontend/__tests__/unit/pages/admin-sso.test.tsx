import type { ReactNode } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { useRouter } from "next/router";

import { useAuth } from "@/contexts/AuthContext";
import * as api from "@/lib/api";
import AdminSsoPage from "@/pages/admin/sso";

jest.mock("@/contexts/AuthContext");
jest.mock("next/router");
jest.mock("@/components/DashboardLayout", () => ({
  __esModule: true,
  default: ({ children }: { children: ReactNode }) => <div data-testid="dashboard-layout">{children}</div>,
}));
jest.mock("@/components/ProtectedRoute", () => ({
  __esModule: true,
  default: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

const mockUseAuth = useAuth as jest.MockedFunction<typeof useAuth>;
const mockUseRouter = useRouter as jest.MockedFunction<typeof useRouter>;

describe("AdminSsoPage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseRouter.mockReturnValue({
      push: jest.fn(),
      replace: jest.fn(),
      prefetch: jest.fn(),
      pathname: "/admin/sso",
      query: {},
      asPath: "/admin/sso",
    } as any);
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

  it("renders configured and partial identity states from the API", async () => {
    jest.spyOn(api.ssoApi, "getProvider").mockResolvedValue({
      issuer_url: "https://tenant.example.com",
      client_id: "client-123",
      audience: "",
      email_domains: ["example.com"],
      default_role: "member",
      enabled: false,
      status: {
        state: "partial",
        message: "SSO configuration exists, but sign-in is currently disabled for this organization.",
      },
    });
    jest.spyOn(api.scimApi, "getTokenInfo").mockResolvedValue({
      token_last4: "abcd",
      created_at: "2026-03-01T00:00:00Z",
      last_used_at: "2026-03-02T00:00:00Z",
      rotated_at: "2026-03-03T00:00:00Z",
      status: {
        state: "configured",
        message: "SCIM provisioning token is active and has been used.",
      },
    });

    render(<AdminSsoPage />);

    await waitFor(() => {
      expect(screen.getByText(/partially configured/i)).toBeInTheDocument();
    });

    expect(screen.getAllByText(/configured/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/sign-in is currently disabled/i)).toBeInTheDocument();
    expect(screen.getByText(/provisioning token is active and has been used/i)).toBeInTheDocument();
    expect(screen.getByText(/identity stays truthful here/i)).toBeInTheDocument();
  });
});
