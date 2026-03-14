import type { ReactNode } from "react";
import { render, screen } from "@testing-library/react";

import AdminHelpPage from "@/pages/admin/help";

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

describe("AdminHelpPage", () => {
  it("packages the operator walkthrough into one product-facing reference", () => {
    render(<AdminHelpPage />);

    expect(screen.getByRole("heading", { name: /the short support guide for p2/i })).toBeInTheDocument();
    expect(screen.getByText(/cloud vs self-hosted/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /policies and retention/i })).toHaveAttribute("href", "/admin/operations");
    expect(screen.getByRole("link", { name: /audit trail/i })).toHaveAttribute("href", "/admin/audit-logs");
  });
});
