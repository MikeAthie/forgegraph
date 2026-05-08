import type { ReactNode } from "react";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useRouter } from "next/router";

import * as api from "@/lib/api";
import AuditLogsPage from "@/pages/admin/audit-logs";

jest.mock("@/components/DashboardLayout", () => ({
  __esModule: true,
  default: ({ children }: { children: ReactNode }) => <div data-testid="dashboard-layout">{children}</div>,
}));

jest.mock("@/components/ProtectedRoute", () => ({
  __esModule: true,
  default: ({ children }: { children: ReactNode }) => <>{children}</>,
}));
jest.mock("next/router");

const mockUseRouter = useRouter as jest.MockedFunction<typeof useRouter>;
const replaceMock = jest.fn();

const auditEntry: api.AuditLogEntry = {
  id: "audit-1",
  tenant_id: "tenant-1",
  actor_email: "owner@example.com",
  action: "memory.observation_created",
  resource_type: "memory_observation",
  resource_id: "obs-1",
  description: "Created graph fact observation 'VIP preference'.",
  metadata: { title: "VIP preference", scope: "graph", type: "fact" },
  created_at: "2026-03-13T12:00:00Z",
};

const toExpectedIso = (value: string) => new Date(value).toISOString();

const flushPromises = async () => {
  await Promise.resolve();
  await Promise.resolve();
};

const renderPage = async () => {
  await act(async () => {
    render(<AuditLogsPage />);
    await flushPromises();
  });
};

describe("AuditLogsPage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    replaceMock.mockClear();
    mockUseRouter.mockReturnValue({
      pathname: "/admin/audit-logs",
      query: {},
      asPath: "/admin/audit-logs",
      isReady: true,
      replace: replaceMock,
      push: jest.fn(),
      prefetch: jest.fn(),
    } as any);
  });

  it("renders the human-readable audit description", async () => {
    jest.spyOn(api.auditLogsApi, "list").mockResolvedValue({
      data: [auditEntry],
      meta: {
        requestId: "req-1",
        timestamp: "2026-03-13T12:00:00Z",
        pagination: {
          page: 1,
          pageSize: 50,
          totalCount: 1,
          totalPages: 1,
          hasNext: false,
          hasPrevious: false,
        },
      },
    });

    await renderPage();

    await waitFor(() => {
      expect(screen.getByText(/created graph fact observation 'vip preference'/i)).toBeInTheDocument();
    });

    expect(screen.getByText("memory.observation_created")).toBeInTheDocument();
    expect(screen.getByText("owner@example.com")).toBeInTheDocument();
  });

  it("passes actor, resource, and date-range filters to the API", async () => {
    const listSpy = jest.spyOn(api.auditLogsApi, "list").mockResolvedValue({
      data: [auditEntry],
      meta: {
        requestId: "req-1",
        timestamp: "2026-03-13T12:00:00Z",
        pagination: {
          page: 1,
          pageSize: 50,
          totalCount: 1,
          totalPages: 1,
          hasNext: false,
          hasPrevious: false,
        },
      },
    });

    const user = userEvent.setup();
    await renderPage();

    await waitFor(() => {
      expect(listSpy).toHaveBeenCalled();
    });

    await act(async () => {
      await user.clear(screen.getByLabelText(/^action$/i));
      await user.type(screen.getByLabelText(/^action$/i), "memory.observation_created");
      await user.clear(screen.getByLabelText(/resource type/i));
      await user.type(screen.getByLabelText(/resource type/i), "memory_observation");
      await user.clear(screen.getByLabelText(/resource id/i));
      await user.type(screen.getByLabelText(/resource id/i), "obs-1");
      await user.clear(screen.getByLabelText(/actor email/i));
      await user.type(screen.getByLabelText(/actor email/i), "owner@example.com");
      await user.clear(screen.getByLabelText(/created from/i));
      await user.type(screen.getByLabelText(/created from/i), "2026-03-10T08:30");
      await user.clear(screen.getByLabelText(/created to/i));
      await user.type(screen.getByLabelText(/created to/i), "2026-03-13T18:30");
      await user.click(screen.getByRole("button", { name: /apply filters/i }));
      await flushPromises();
    });

    await waitFor(() => {
      expect(listSpy).toHaveBeenLastCalledWith({
        action: "memory.observation_created",
        resource_type: "memory_observation",
        resource_id: "obs-1",
        actor_email: "owner@example.com",
        created_from: toExpectedIso("2026-03-10T08:30"),
        created_to: toExpectedIso("2026-03-13T18:30"),
        tenant_id: undefined,
        limit: 50,
        offset: 0,
      });
    });
    expect(replaceMock).toHaveBeenCalledWith(
      {
        pathname: "/admin/audit-logs",
        query: expect.objectContaining({
          action: "memory.observation_created",
          resource_type: "memory_observation",
          resource_id: "obs-1",
          actor_email: "owner@example.com",
          offset: "0",
        }),
      },
      undefined,
      { shallow: true, scroll: false },
    );
  });
});
