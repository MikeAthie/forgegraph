import type { ReactNode } from "react";
import { render, screen } from "@testing-library/react";

import { useAuth } from "@/contexts/AuthContext";
import AdminIndexPage from "@/pages/admin";

jest.mock("@/contexts/AuthContext");
jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children, ...props }: any) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));
jest.mock("@/components/DashboardLayout", () => ({
  __esModule: true,
  default: ({ children }: { children: ReactNode }) => <div data-testid="dashboard-layout">{children}</div>,
}));
jest.mock("@/components/ProtectedRoute", () => ({
  __esModule: true,
  default: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

const mockUseAuth = useAuth as jest.MockedFunction<typeof useAuth>;

describe("AdminIndexPage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("groups the governance surfaces into one admin hub", () => {
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

    render(<AdminIndexPage />);

    expect(screen.getByRole("heading", { name: /one home for how the tenant is governed/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open organization/i })).toHaveAttribute("href", "/admin/organization");
    expect(screen.getByRole("link", { name: /open identity/i })).toHaveAttribute("href", "/admin/sso");
    expect(screen.getByRole("link", { name: /open billing/i })).toHaveAttribute("href", "/admin/billing");
    expect(screen.getByRole("link", { name: /open audit/i })).toHaveAttribute("href", "/admin/audit-logs");
    expect(screen.getByRole("link", { name: /open policies & operations/i })).toHaveAttribute(
      "href",
      "/admin/operations",
    );
    expect(screen.getByRole("link", { name: /open memory/i })).toHaveAttribute("href", "/memory");
  });

  it("shows the read-only governance notice for non-admin roles", () => {
    mockUseAuth.mockReturnValue({
      user: {
        id: "u2",
        email: "viewer@example.com",
        organization_role: "viewer",
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

    render(<AdminIndexPage />);

    expect(screen.getByText(/some sections stay read-only unless you have owner or admin access/i)).toBeInTheDocument();
  });
});
