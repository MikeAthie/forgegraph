/**
 * Unit tests for ProtectedRoute component.
 *
 * Tests route protection logic and redirects for unauthenticated users.
 */

import { render, screen, waitFor } from "@testing-library/react";
import { useRouter } from "next/router";

import ProtectedRoute from "@/components/ProtectedRoute";
import { useAuth } from "@/contexts/AuthContext";

// Mock dependencies
jest.mock("@/contexts/AuthContext");
jest.mock("next/router");

const mockUseAuth = useAuth as jest.MockedFunction<typeof useAuth>;
const mockUseRouter = useRouter as jest.MockedFunction<typeof useRouter>;

describe("ProtectedRoute", () => {
  const mockPush = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
    mockUseRouter.mockReturnValue({
      push: mockPush,
      replace: jest.fn(),
      prefetch: jest.fn(),
      pathname: "/",
      query: {},
      asPath: "/",
    } as any);
  });

  describe("Loading State", () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({
        user: null,
        isAuthenticated: false,
        loading: true,
        error: null,
        login: jest.fn(),
        register: jest.fn(),
        logout: jest.fn(),
        checkAuth: jest.fn(),
        clearError: jest.fn(),
      });
    });

    it("should display loading spinner when loading is true", () => {
      render(
        <ProtectedRoute>
          <div>Protected Content</div>
        </ProtectedRoute>,
      );

      expect(screen.getByText("Loading workspace...")).toBeInTheDocument();
      expect(screen.queryByText("Protected Content")).not.toBeInTheDocument();
    });

    it("should not redirect when loading", () => {
      render(
        <ProtectedRoute>
          <div>Protected Content</div>
        </ProtectedRoute>,
      );

      expect(mockPush).not.toHaveBeenCalled();
    });

    it("should display spinner component when loading", () => {
      render(
        <ProtectedRoute>
          <div>Protected Content</div>
        </ProtectedRoute>,
      );

      expect(screen.getByRole("status", { name: /loading workspace/i })).toBeInTheDocument();
    });
  });

  describe("Unauthenticated State", () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({
        user: null,
        isAuthenticated: false,
        loading: false,
        error: null,
        login: jest.fn(),
        register: jest.fn(),
        logout: jest.fn(),
        checkAuth: jest.fn(),
        clearError: jest.fn(),
      });
    });

    it("should redirect to login when not authenticated", async () => {
      render(
        <ProtectedRoute>
          <div>Protected Content</div>
        </ProtectedRoute>,
      );

      await waitFor(() => {
        expect(mockPush).toHaveBeenCalledWith("/login");
      });
    });

    it("should display redirecting message when not authenticated", () => {
      render(
        <ProtectedRoute>
          <div>Protected Content</div>
        </ProtectedRoute>,
      );

      expect(screen.getByText("Redirecting to sign in...")).toBeInTheDocument();
      expect(screen.queryByText("Protected Content")).not.toBeInTheDocument();
    });

    it("should not render children when not authenticated", () => {
      render(
        <ProtectedRoute>
          <div>Protected Content</div>
        </ProtectedRoute>,
      );

      expect(screen.queryByText("Protected Content")).not.toBeInTheDocument();
    });
  });

  describe("Authenticated State", () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({
        user: { id: "1", email: "user@example.com" },
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

    it("should render children when authenticated", () => {
      render(
        <ProtectedRoute>
          <div>Protected Content</div>
        </ProtectedRoute>,
      );

      expect(screen.getByText("Protected Content")).toBeInTheDocument();
    });

    it("should not redirect when authenticated", () => {
      render(
        <ProtectedRoute>
          <div>Protected Content</div>
        </ProtectedRoute>,
      );

      expect(mockPush).not.toHaveBeenCalled();
    });

    it("should not display loading or redirecting message", () => {
      render(
        <ProtectedRoute>
          <div>Protected Content</div>
        </ProtectedRoute>,
      );

      expect(screen.queryByText("Loading workspace...")).not.toBeInTheDocument();
      expect(screen.queryByText("Redirecting to sign in...")).not.toBeInTheDocument();
    });

    it("should render complex children", () => {
      render(
        <ProtectedRoute>
          <div>
            <h1>Dashboard</h1>
            <p>Welcome back!</p>
            <button>Action</button>
          </div>
        </ProtectedRoute>,
      );

      expect(screen.getByRole("heading", { name: /dashboard/i })).toBeInTheDocument();
      expect(screen.getByText("Welcome back!")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /action/i })).toBeInTheDocument();
    });
  });

  describe("State Transitions", () => {
    it("should handle transition from loading to authenticated", () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isAuthenticated: false,
        loading: true,
        error: null,
        login: jest.fn(),
        register: jest.fn(),
        logout: jest.fn(),
        checkAuth: jest.fn(),
        clearError: jest.fn(),
      });

      const { rerender } = render(
        <ProtectedRoute>
          <div>Protected Content</div>
        </ProtectedRoute>,
      );

      expect(screen.getByText("Loading workspace...")).toBeInTheDocument();

      // Transition to authenticated
      mockUseAuth.mockReturnValue({
        user: { id: "1", email: "user@example.com" },
        isAuthenticated: true,
        loading: false,
        error: null,
        login: jest.fn(),
        register: jest.fn(),
        logout: jest.fn(),
        checkAuth: jest.fn(),
        clearError: jest.fn(),
      });

      rerender(
        <ProtectedRoute>
          <div>Protected Content</div>
        </ProtectedRoute>,
      );

      expect(screen.getByText("Protected Content")).toBeInTheDocument();
      expect(screen.queryByText("Loading workspace...")).not.toBeInTheDocument();
    });

    it("should handle transition from loading to unauthenticated", async () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isAuthenticated: false,
        loading: true,
        error: null,
        login: jest.fn(),
        register: jest.fn(),
        logout: jest.fn(),
        checkAuth: jest.fn(),
        clearError: jest.fn(),
      });

      const { rerender } = render(
        <ProtectedRoute>
          <div>Protected Content</div>
        </ProtectedRoute>,
      );

      expect(screen.getByText("Loading workspace...")).toBeInTheDocument();

      // Transition to unauthenticated
      mockUseAuth.mockReturnValue({
        user: null,
        isAuthenticated: false,
        loading: false,
        error: null,
        login: jest.fn(),
        register: jest.fn(),
        logout: jest.fn(),
        checkAuth: jest.fn(),
        clearError: jest.fn(),
      });

      rerender(
        <ProtectedRoute>
          <div>Protected Content</div>
        </ProtectedRoute>,
      );

      await waitFor(() => {
        expect(mockPush).toHaveBeenCalledWith("/login");
      });

      expect(screen.getByText("Redirecting to sign in...")).toBeInTheDocument();
    });
  });

  describe("Edge Cases", () => {
    it("should handle null children gracefully", () => {
      mockUseAuth.mockReturnValue({
        user: { id: "1", email: "user@example.com" },
        isAuthenticated: true,
        loading: false,
        error: null,
        login: jest.fn(),
        register: jest.fn(),
        logout: jest.fn(),
        checkAuth: jest.fn(),
        clearError: jest.fn(),
      });

      render(<ProtectedRoute>{null}</ProtectedRoute>);

      // Should not crash
      expect(screen.queryByText("Loading workspace...")).not.toBeInTheDocument();
    });

    it("should handle multiple children", () => {
      mockUseAuth.mockReturnValue({
        user: { id: "1", email: "user@example.com" },
        isAuthenticated: true,
        loading: false,
        error: null,
        login: jest.fn(),
        register: jest.fn(),
        logout: jest.fn(),
        checkAuth: jest.fn(),
        clearError: jest.fn(),
      });

      render(
        <ProtectedRoute>
          <div>Child 1</div>
          <div>Child 2</div>
          <div>Child 3</div>
        </ProtectedRoute>,
      );

      expect(screen.getByText("Child 1")).toBeInTheDocument();
      expect(screen.getByText("Child 2")).toBeInTheDocument();
      expect(screen.getByText("Child 3")).toBeInTheDocument();
    });
  });

  describe("Accessibility", () => {
    it("should have accessible loading state", () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isAuthenticated: false,
        loading: true,
        error: null,
        login: jest.fn(),
        register: jest.fn(),
        logout: jest.fn(),
        checkAuth: jest.fn(),
        clearError: jest.fn(),
      });

      render(
        <ProtectedRoute>
          <div>Protected Content</div>
        </ProtectedRoute>,
      );

      // Loading message should be visible and accessible
      expect(screen.getByText("Loading workspace...")).toBeInTheDocument();
    });

    it("should have accessible redirecting state", () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isAuthenticated: false,
        loading: false,
        error: null,
        login: jest.fn(),
        register: jest.fn(),
        logout: jest.fn(),
        checkAuth: jest.fn(),
        clearError: jest.fn(),
      });

      render(
        <ProtectedRoute>
          <div>Protected Content</div>
        </ProtectedRoute>,
      );

      // Redirecting message should be visible and accessible
      expect(screen.getByText("Redirecting to sign in...")).toBeInTheDocument();
    });
  });
});
