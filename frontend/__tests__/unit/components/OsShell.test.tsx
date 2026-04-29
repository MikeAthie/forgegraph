import { render, screen } from "@testing-library/react";
import { useRouter } from "next/router";

import OsShell from "@/components/shell/OsShell";
import { useAuth } from "@/contexts/AuthContext";

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
jest.mock("next/image", () => ({
  __esModule: true,
  default: ({ alt, priority: _priority, ...props }: any) => <img alt={alt} {...props} />,
}));
jest.mock("@/components/ui/theme-toggle", () => ({
  ThemeToggle: () => <button aria-label="Toggle theme">Theme</button>,
}));

const mockUseAuth = useAuth as jest.MockedFunction<typeof useAuth>;
const mockUseRouter = useRouter as jest.MockedFunction<typeof useRouter>;

describe("OsShell", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseAuth.mockReturnValue({
      user: {
        id: "user-1",
        email: "operator@example.com",
        default_organization_id: "org-1",
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
    mockUseRouter.mockReturnValue({
      push: jest.fn(),
      replace: jest.fn(),
      prefetch: jest.fn(),
      pathname: "/departments",
      query: {},
      asPath: "/departments",
      isReady: true,
    } as any);
  });

  it("provides a skip link and main landmark", () => {
    render(
      <OsShell>
        <h2>Department thinking surface</h2>
      </OsShell>,
    );

    expect(screen.getByRole("link", { name: /skip to main content/i })).toHaveAttribute("href", "#main-content");
    expect(screen.getByRole("main")).toHaveAttribute("id", "main-content");
    expect(screen.getByRole("heading", { name: /department thinking surface/i })).toBeInTheDocument();
  });

  it("marks active navigation links for assistive technology", () => {
    render(
      <OsShell>
        <h2>Department thinking surface</h2>
      </OsShell>,
    );

    const currentLinks = screen.getAllByRole("link", { current: "page" });
    expect(currentLinks.map((link) => link.textContent)).toEqual(expect.arrayContaining(["Departments"]));
  });

  it("uses product navigation labels in the primary shell", () => {
    render(
      <OsShell>
        <h2>Department thinking surface</h2>
      </OsShell>,
    );

    expect(screen.getAllByRole("link", { name: /departments/i }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: /approvals/i }).length).toBeGreaterThan(0);
    expect(screen.queryByRole("link", { name: /^agents$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^executions$/i })).not.toBeInTheDocument();
  });
});
