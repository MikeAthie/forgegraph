import type { ReactNode } from "react";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useRouter } from "next/router";

import * as api from "@/lib/api";
import OperationsPage from "@/pages/runs";
import OperationDetailPage from "@/pages/runs/[runId]";
import {
  makeDepartmentActivity,
  makeOperationDetail,
  makeOperationListItem,
  operationId,
} from "../fixtures/operation-dtos";

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

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: ReactNode }) => <a href={href}>{children}</a>,
}));

jest.mock("next/router");

const mockUseRouter = useRouter as jest.MockedFunction<typeof useRouter>;
const flushPromises = async () => {
  await Promise.resolve();
  await Promise.resolve();
};

const renderOperationsPage = async () => {
  await act(async () => {
    render(<OperationsPage />);
    await flushPromises();
  });
};

const renderOperationDetailPage = async () => {
  await act(async () => {
    render(<OperationDetailPage />);
    await flushPromises();
  });
};

describe("Operations pages", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    api.clearTokens();
    mockUseRouter.mockReturnValue({
      push: jest.fn(),
      replace: jest.fn(),
      prefetch: jest.fn(),
      pathname: "/runs",
      query: {},
      asPath: "/runs",
    } as any);
  });

  describe("OperationsPage", () => {
    it("shows the loading shell while operations are still loading", () => {
      jest.spyOn(api.runsApi, "list").mockImplementation(() => new Promise(() => {}));

      render(<OperationsPage />);

      expect(screen.getByText("Recent company operations")).toBeInTheDocument();
      expect(screen.getByRole("status", { name: /loading/i })).toBeInTheDocument();
    });

    it("renders an empty state when no operations exist", async () => {
      jest.spyOn(api.runsApi, "list").mockResolvedValue([]);

      await renderOperationsPage();

      expect(screen.getByText(/no operations available/i)).toBeInTheDocument();
    });

    it("renders operations and selects the most recent one by default", async () => {
      jest.spyOn(api.runsApi, "list").mockResolvedValue([
        makeOperationListItem({
          id: "operation-old",
          companyName: "Nightly digest",
          setupVersion: 1,
          startedAt: "2026-04-05T08:00:00Z",
          status: "succeeded",
          durationMs: 62_000,
        }),
        makeOperationListItem({
          id: "operation-new",
          companyName: "Revenue triage",
          setupVersion: 4,
          startedAt: "2026-04-05T12:00:00Z",
          status: "running",
          durationMs: 90_000,
        }),
      ]);

      await renderOperationsPage();

      expect(screen.getAllByText("Revenue triage").length).toBeGreaterThan(0);
      expect(screen.getAllByText("Nightly digest").length).toBeGreaterThan(0);
      expect(screen.getAllByText(/saved setup/i).length).toBeGreaterThan(0);
      expect(screen.getByText("v4")).toBeInTheDocument();
      expect(screen.getByRole("link", { name: /open operation detail/i })).toHaveAttribute(
        "href",
        "/runs/operation-new",
      );
    });

    it("updates the selected operation through the router when the operator switches rows", async () => {
      const replace = jest.fn();
      mockUseRouter.mockReturnValue({
        push: jest.fn(),
        replace,
        prefetch: jest.fn(),
        pathname: "/runs",
        query: {},
        asPath: "/runs",
      } as any);

      jest.spyOn(api.runsApi, "list").mockResolvedValue([
        makeOperationListItem({ id: "operation-1", companyName: "Revenue triage" }),
        makeOperationListItem({
          id: "operation-2",
          companyName: "Approval sweep",
          startedAt: "2026-04-05T11:00:00Z",
        }),
      ]);

      await renderOperationsPage();
      await userEvent.click(screen.getByRole("button", { name: /approval sweep/i }));

      expect(replace).toHaveBeenCalledWith({ pathname: "/runs", query: { operation: "operation-2" } }, undefined, {
        shallow: true,
      });
    });

    it("renders a translated error banner when operations fail to load", async () => {
      jest.spyOn(api.runsApi, "list").mockRejectedValue(new Error("API Error"));

      await renderOperationsPage();

      expect(screen.getByText(/operation could not continue/i)).toBeInTheDocument();
    });
  });

  describe("OperationDetailPage", () => {
    beforeEach(() => {
      mockUseRouter.mockReturnValue({
        push: jest.fn(),
        replace: jest.fn(),
        prefetch: jest.fn(),
        pathname: `/runs/${operationId}`,
        query: { runId: operationId },
        asPath: `/runs/${operationId}`,
      } as any);
    });

    it("shows the loading shell while the operation detail request is pending", () => {
      jest.spyOn(api.runsApi, "get").mockImplementation(() => new Promise(() => {}));

      render(<OperationDetailPage />);

      expect(screen.getByText("Operation Detail")).toBeInTheDocument();
      expect(screen.getByRole("status", { name: /loading/i })).toBeInTheDocument();
    });

    it("renders the operation summary, department activity, and support identifiers", async () => {
      jest.spyOn(api.runsApi, "get").mockResolvedValue(
        makeOperationDetail({
          status: "failed",
          durationMs: 95_000,
          activities: [
            makeDepartmentActivity({
              id: "department-activity-1",
              departmentId: "fetch_customer",
              deliverable: { customer_name: "Jackie" },
            }),
            makeDepartmentActivity({
              id: "department-activity-2",
              departmentId: "draft_reply",
              departmentType: "prompt",
              status: "failed",
              durationMs: 2000,
              input: { prompt: "Draft the message" },
              deliverable: null,
              issue: { code: "MODEL_TIMEOUT", message: "Provider timed out" },
            }),
          ],
        }),
      );

      await renderOperationDetailPage();

      expect(api.runsApi.get).toHaveBeenCalledWith(operationId);
      expect(screen.getByText("Operation Detail")).toBeInTheDocument();
      expect(screen.getByText("Department activity")).toBeInTheDocument();
      expect(screen.getByText("Operation state")).toBeInTheDocument();
      expect(screen.getAllByText("Revenue triage").length).toBeGreaterThan(0);
      expect(screen.getAllByText("Analysis Skill").length).toBeGreaterThan(0);
      expect(screen.getAllByText("Tool Action").length).toBeGreaterThan(0);
      expect(screen.getAllByText(/attention point/i).length).toBeGreaterThan(0);
    });

    it("renders paused operations in the approval panel", async () => {
      jest.spyOn(api.runsApi, "get").mockResolvedValue(
        makeOperationDetail({
          status: "paused",
          pausedApproval: {
            departmentId: "approval_1",
            departmentName: "Finance approval",
            promptMessage: "Approve the outbound refund before work resumes.",
          },
        }),
      );

      await renderOperationDetailPage();

      expect(screen.getByText("Open approvals")).toBeInTheDocument();
      expect(screen.getByText(/approval is waiting/i)).toBeInTheDocument();
    });

    it("renders a translated error banner when the operation detail request fails", async () => {
      jest.spyOn(api.runsApi, "get").mockRejectedValue(new Error("API Error"));

      await renderOperationDetailPage();

      expect(screen.getByText(/operation could not continue/i)).toBeInTheDocument();
    });
  });
});
