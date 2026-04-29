/**
 * Unit tests for Header component.
 *
 * Tests navigation, authentication state display, and user menu functionality.
 */

import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useRouter } from "next/router";

import Header from "@/components/Header";
import { useAuth } from "@/contexts/AuthContext";

// Mock dependencies
jest.mock("@/contexts/AuthContext");
jest.mock("next/router");
jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children, ...props }: any) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));
jest.mock("@/components/ui/dropdown-menu", () => ({
  DropdownMenu: ({ children }: any) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: any) => <div>{children}</div>,
  DropdownMenuContent: ({ children }: any) => <div>{children}</div>,
  DropdownMenuItem: ({ children, onSelect, disabled, className }: any) => (
    <button
      type="button"
      data-slot="dropdown-menu-item"
      data-disabled={disabled ? "" : undefined}
      className={className}
      disabled={disabled}
      onClick={(event) => onSelect?.({ ...event, preventDefault: () => {} })}
    >
      {children}
    </button>
  ),
  DropdownMenuLabel: ({ children }: any) => <div>{children}</div>,
  DropdownMenuSeparator: () => <div />,
}));

const mockUseAuth = useAuth as jest.MockedFunction<typeof useAuth>;
const mockUseRouter = useRouter as jest.MockedFunction<typeof useRouter>;

const setupUser = () => {
  const user = userEvent.setup();
  return {
    ...user,
    click: (element: HTMLElement) => act(async () => user.click(element)),
  };
};

describe("Header", () => {
  const mockLogout = jest.fn();
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

  describe("Unauthenticated State", () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({
        user: null,
        isAuthenticated: false,
        loading: false,
        error: null,
        login: jest.fn(),
        register: jest.fn(),
        logout: mockLogout,
        checkAuth: jest.fn(),
        clearError: jest.fn(),
      });
    });

    it("should render ForgeGraph logo", () => {
      render(<Header />);

      expect(screen.getByText("ForgeGraph")).toBeInTheDocument();
    });

    it("should display Sign in and Get started buttons when not authenticated", () => {
      render(<Header />);

      expect(screen.getByRole("link", { name: /sign in/i })).toBeInTheDocument();
      expect(screen.getByRole("link", { name: /get started/i })).toBeInTheDocument();
    });

    it("should not display navigation links when not authenticated", () => {
      render(<Header />);

      expect(screen.queryByRole("link", { name: /overview/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("link", { name: /approvals/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("link", { name: /departments/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("link", { name: /activity/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("link", { name: /knowledge/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("link", { name: /operations/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("link", { name: /advanced/i })).not.toBeInTheDocument();
    });

    it("should have correct href for Sign in button", () => {
      render(<Header />);

      const signInLink = screen.getByRole("link", { name: /sign in/i });
      expect(signInLink).toHaveAttribute("href", "/login");
    });

    it("should have correct href for Get started button", () => {
      render(<Header />);

      const getStartedLink = screen.getByRole("link", { name: /get started/i });
      expect(getStartedLink).toHaveAttribute("href", "/register");
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
        logout: mockLogout,
        checkAuth: jest.fn(),
        clearError: jest.fn(),
      });
    });

    it("should display navigation links when authenticated", () => {
      render(<Header />);

      expect(screen.getByRole("link", { name: /^overview$/i })).toBeInTheDocument();
      expect(screen.getByRole("link", { name: /^approvals$/i })).toBeInTheDocument();
      expect(screen.getByRole("link", { name: /^departments$/i })).toBeInTheDocument();
      expect(screen.getByRole("link", { name: /^activity$/i })).toBeInTheDocument();
      expect(screen.getByRole("link", { name: /^knowledge$/i })).toBeInTheDocument();
      expect(screen.getByRole("link", { name: /^operations$/i })).toBeInTheDocument();
      expect(screen.getByRole("link", { name: /^advanced operating models$/i })).toBeInTheDocument();
    });

    it("should not display Sign in/Get started buttons when authenticated", () => {
      render(<Header />);

      expect(screen.queryByRole("link", { name: /sign in/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("link", { name: /get started/i })).not.toBeInTheDocument();
    });

    it("should display user email in dropdown trigger", () => {
      render(<Header />);

      expect(screen.getAllByText("user@example.com").length).toBeGreaterThan(0);
    });

    it("should display user menu with dropdown button", () => {
      render(<Header />);

      const dropdownTrigger = screen.getByRole("button", { name: /user@example.com/i });
      expect(dropdownTrigger).toBeInTheDocument();
    });

    it("should have correct hrefs for navigation links", () => {
      render(<Header />);

      expect(screen.getByRole("link", { name: /^overview$/i })).toHaveAttribute("href", "/overview");
      expect(screen.getByRole("link", { name: /^approvals$/i })).toHaveAttribute("href", "/approvals");
      expect(screen.getByRole("link", { name: /^departments$/i })).toHaveAttribute("href", "/departments");
      expect(screen.getByRole("link", { name: /^activity$/i })).toHaveAttribute("href", "/tasks");
      expect(screen.getByRole("link", { name: /^knowledge$/i })).toHaveAttribute("href", "/memory");
      expect(screen.getByRole("link", { name: /^operations$/i })).toHaveAttribute("href", "/runs");
      expect(screen.getByRole("link", { name: /^advanced operating models$/i })).toHaveAttribute("href", "/workflows");
    });
  });

  describe("User Menu Interactions", () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({
        user: { id: "1", email: "user@example.com" },
        isAuthenticated: true,
        loading: false,
        error: null,
        login: jest.fn(),
        register: jest.fn(),
        logout: mockLogout,
        checkAuth: jest.fn(),
        clearError: jest.fn(),
      });
    });

    it("should open dropdown menu on click", async () => {
      const user = setupUser();
      render(<Header />);

      const dropdownTrigger = screen.getByRole("button", { name: /user@example.com/i });
      await user.click(dropdownTrigger);

      await waitFor(() => {
        expect(screen.getByText("Account")).toBeInTheDocument();
        expect(screen.getByText("Settings & Governance")).toBeInTheDocument();
        expect(screen.getByText("Sign out")).toBeInTheDocument();
      });
    });

    it("should route to the admin hub from the user menu", async () => {
      const user = setupUser();
      render(<Header />);

      const dropdownTrigger = screen.getByRole("button", { name: /user@example.com/i });
      await user.click(dropdownTrigger);

      await waitFor(() => {
        expect(screen.getByText("Settings & Governance")).toBeInTheDocument();
      });

      await user.click(screen.getByText("Settings & Governance"));

      await waitFor(() => {
        expect(mockPush).toHaveBeenCalledWith("/admin");
      });
    });

    it("should call logout when Sign out is clicked", async () => {
      const user = setupUser();
      render(<Header />);

      // Open dropdown
      const dropdownTrigger = screen.getByRole("button", { name: /user@example.com/i });
      await user.click(dropdownTrigger);

      // Click sign out
      await waitFor(() => {
        expect(screen.getByText("Sign out")).toBeInTheDocument();
      });

      const signOutButton = screen.getByText("Sign out");
      await user.click(signOutButton);

      await waitFor(() => {
        expect(mockLogout).toHaveBeenCalledTimes(1);
      });
    });

    it("should show loading state while logging out", async () => {
      const user = setupUser();

      // Mock logout to simulate delay
      mockLogout.mockImplementation(() => new Promise((resolve) => setTimeout(resolve, 100)));

      render(<Header />);

      // Open dropdown
      const dropdownTrigger = screen.getByRole("button", { name: /user@example.com/i });
      await user.click(dropdownTrigger);

      // Click sign out
      await waitFor(() => {
        expect(screen.getByText("Sign out")).toBeInTheDocument();
      });

      const signOutButton = screen.getByText("Sign out");
      await user.click(signOutButton);

      // Should show loading state
      await waitFor(() => {
        expect(screen.getByText("Signing out...")).toBeInTheDocument();
      });
    });

    it("should disable Sign out button while logging out", async () => {
      const user = setupUser();

      // Mock logout to simulate delay
      mockLogout.mockImplementation(() => new Promise((resolve) => setTimeout(resolve, 100)));

      render(<Header />);

      // Open dropdown
      const dropdownTrigger = screen.getByRole("button", { name: /user@example.com/i });
      await user.click(dropdownTrigger);

      await waitFor(() => {
        expect(screen.getByText("Sign out")).toBeInTheDocument();
      });

      const signOutButton = screen.getByRole("button", { name: /sign out/i });
      await user.click(signOutButton);

      // Button should be disabled
      await waitFor(() => {
        const signingOutButton = screen.getByText("Signing out...").closest("button");
        expect(signingOutButton).toBeDisabled();
      });
    });
  });

  describe("Logo Link", () => {
    it("should link to home page", () => {
      mockUseAuth.mockReturnValue({
        user: null,
        isAuthenticated: false,
        loading: false,
        error: null,
        login: jest.fn(),
        register: jest.fn(),
        logout: mockLogout,
        checkAuth: jest.fn(),
        clearError: jest.fn(),
      });

      render(<Header />);

      const logoLink = screen.getByRole("link", { name: /forgegraph/i });
      expect(logoLink).toHaveAttribute("href", "/");
    });
  });

  describe("Email Truncation", () => {
    it("should handle long email addresses", () => {
      mockUseAuth.mockReturnValue({
        user: { id: "1", email: "verylongemailaddress@exampledomain.com" },
        isAuthenticated: true,
        loading: false,
        error: null,
        login: jest.fn(),
        register: jest.fn(),
        logout: mockLogout,
        checkAuth: jest.fn(),
        clearError: jest.fn(),
      });

      render(<Header />);

      // Email should be rendered (even if truncated visually with CSS)
      expect(screen.getAllByText("verylongemailaddress@exampledomain.com").length).toBeGreaterThan(0);
    });
  });

  describe("Accessibility", () => {
    it("should have accessible navigation structure", () => {
      mockUseAuth.mockReturnValue({
        user: { id: "1", email: "user@example.com" },
        isAuthenticated: true,
        loading: false,
        error: null,
        login: jest.fn(),
        register: jest.fn(),
        logout: mockLogout,
        checkAuth: jest.fn(),
        clearError: jest.fn(),
      });

      render(<Header />);

      expect(screen.getByRole("banner")).toBeInTheDocument();
      expect(screen.getByRole("navigation")).toBeInTheDocument();
    });

    it("should have accessible button for dropdown", () => {
      mockUseAuth.mockReturnValue({
        user: { id: "1", email: "user@example.com" },
        isAuthenticated: true,
        loading: false,
        error: null,
        login: jest.fn(),
        register: jest.fn(),
        logout: mockLogout,
        checkAuth: jest.fn(),
        clearError: jest.fn(),
      });

      render(<Header />);

      const dropdownTrigger = screen.getByRole("button", { name: /user@example.com/i });
      expect(dropdownTrigger).toBeInTheDocument();
    });

    it("should expose the active page in navigation", () => {
      mockUseRouter.mockReturnValue({
        push: mockPush,
        replace: jest.fn(),
        prefetch: jest.fn(),
        pathname: "/departments",
        query: {},
        asPath: "/departments",
      } as any);
      mockUseAuth.mockReturnValue({
        user: { id: "1", email: "user@example.com" },
        isAuthenticated: true,
        loading: false,
        error: null,
        login: jest.fn(),
        register: jest.fn(),
        logout: mockLogout,
        checkAuth: jest.fn(),
        clearError: jest.fn(),
      });

      render(<Header />);

      expect(screen.getByRole("link", { name: /^departments$/i, current: "page" })).toBeInTheDocument();
    });
  });
});
