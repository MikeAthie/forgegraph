import type { ReactNode } from "react";
import { render, screen, waitFor } from "@testing-library/react";

import { useAuth } from "@/contexts/AuthContext";
import * as api from "@/lib/api";
import OrganizationPage from "@/pages/admin/organization";

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

describe("OrganizationPage", () => {
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

  it("renders the role matrix from the governance contract", async () => {
    jest.spyOn(api.organizationsApi, "me").mockResolvedValue({
      organization: {
        id: "org-1",
        name: "ForgeGraph",
        created_at: "2026-03-01T00:00:00Z",
        updated_at: "2026-03-02T00:00:00Z",
      },
      role: "owner",
      governance: {
        current_role_capabilities: {
          can_view_observations: true,
          can_delete_observations: true,
          can_manage_retention: true,
          can_export_memory_data: true,
          can_manage_members: true,
        },
        role_capabilities: {
          owner: {
            can_view_observations: true,
            can_delete_observations: true,
            can_manage_retention: true,
            can_export_memory_data: true,
            can_manage_members: true,
          },
          admin: {
            can_view_observations: true,
            can_delete_observations: true,
            can_manage_retention: true,
            can_export_memory_data: true,
            can_manage_members: true,
          },
          member: {
            can_view_observations: true,
            can_delete_observations: true,
            can_manage_retention: false,
            can_export_memory_data: false,
            can_manage_members: false,
          },
          viewer: {
            can_view_observations: true,
            can_delete_observations: false,
            can_manage_retention: false,
            can_export_memory_data: false,
            can_manage_members: false,
          },
        },
      },
    });
    jest.spyOn(api.organizationsApi, "listMembers").mockResolvedValue([]);

    render(<OrganizationPage />);

    await waitFor(() => {
      expect(screen.getByText(/memory governance by role/i)).toBeInTheDocument();
    });

    expect(screen.getAllByText(/view observations/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/delete observations/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/manage retention/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/export memory data/i).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: /review policies and retention/i })).toHaveAttribute(
      "href",
      "/admin/operations",
    );
  });
});
