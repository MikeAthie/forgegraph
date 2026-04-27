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
  default: ({ children, inspector }: { children: ReactNode; inspector?: ReactNode }) => (
    <div data-testid="dashboard-layout">
      <div>{children}</div>
      {inspector ? <aside>{inspector}</aside> : null}
    </div>
  ),
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

    expect(screen.getByRole("heading", { name: /govern the operating environment/i })).toBeInTheDocument();
    expect(screen.getByText(/governance remains available as a legacy route/i)).toBeInTheDocument();
    expect(screen.getByText("Workspace configuration")).toBeInTheDocument();
    expect(screen.getByText("Governance controls")).toBeInTheDocument();
    expect(screen.getByText("Workspace Access")).toBeInTheDocument();
    expect(screen.getByText("Identity")).toBeInTheDocument();
    expect(screen.getByText("Billing")).toBeInTheDocument();
    expect(screen.getByText("Operations")).toBeInTheDocument();

    const hrefs = screen.getAllByRole("link", { name: "Open" }).map((link) => link.getAttribute("href"));
    expect(hrefs).toEqual(
      expect.arrayContaining([
        "/admin/organization",
        "/admin/sso",
        "/admin/billing",
        "/admin/audit-logs",
        "/admin/operations",
        "/admin/marketplace",
      ]),
    );
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

    expect(screen.getByText(/read-only on governed surfaces/i)).toBeInTheDocument();
    expect(screen.getByText(/access messaging is explicit/i)).toBeInTheDocument();
  });
});
