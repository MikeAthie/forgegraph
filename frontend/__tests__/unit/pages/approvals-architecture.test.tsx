import type { ReactNode } from "react";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { approvalRepository, operationRepository } from "@/domain/repositories";
import type { ApprovalVM } from "@/domain/translation";
import { useRunLiveUpdates } from "@/hooks/useRunLiveUpdates";
import ApprovalsPage from "@/pages/approvals";

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

jest.mock("@/domain/repositories", () => ({
  approvalRepository: {
    list: jest.fn(),
    decide: jest.fn(),
  },
  operationRepository: {
    getBackendState: jest.fn(),
  },
}));

jest.mock("@/hooks/useRunLiveUpdates", () => ({
  useRunLiveUpdates: jest.fn(),
}));

jest.mock("@/lib/toast", () => ({
  showSuccess: jest.fn(),
}));

const mockApprovalRepository = approvalRepository as jest.Mocked<typeof approvalRepository>;
const mockOperationRepository = operationRepository as jest.Mocked<typeof operationRepository>;
const mockUseRunLiveUpdates = useRunLiveUpdates as jest.MockedFunction<typeof useRunLiveUpdates>;

function makeApproval(overrides: Partial<ApprovalVM> = {}): ApprovalVM {
  return {
    id: "approval-1",
    operationId: "run-1",
    operationName: "Revenue review",
    companyName: "Acme Operations",
    agentId: "agent-1",
    departmentId: "human_gate_1",
    departmentName: "Finance",
    status: "pending",
    promptMessage: "Approve the finance action.",
    requiredFields: [],
    result: null,
    createdAt: "2026-05-01T12:00:00Z",
    resolvedAt: null,
    estimatedCost: 2.25,
    risk: "medium",
    consequence: "Budget-affecting action",
    blastRadius: "Finance department",
    ...overrides,
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });
  return { promise, resolve, reject };
}

describe("Approvals architecture behavior", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseRunLiveUpdates.mockImplementation(() => undefined);
    mockApprovalRepository.list.mockResolvedValue([makeApproval()]);
  });

  it("does not show approved state until the backend decision request confirms", async () => {
    const user = userEvent.setup();
    const decision = deferred<{ resumed: boolean; run_id: string; resume_attempt_id: string }>();
    mockApprovalRepository.decide.mockReturnValue(decision.promise);

    render(<ApprovalsPage />);

    await screen.findAllByText("Acme Operations");
    await user.click(screen.getByRole("button", { name: /^approve$/i }));

    expect(mockApprovalRepository.decide).toHaveBeenCalledWith(
      expect.objectContaining({ id: "approval-1" }),
      true,
      undefined,
    );
    expect(screen.getByText("Submitting")).toBeInTheDocument();
    expect(screen.queryByText("Accepted by backend")).not.toBeInTheDocument();
    for (const button of screen.getAllByRole("button", { name: /submitting/i })) {
      expect(button).toBeDisabled();
    }

    await act(async () => {
      decision.resolve({
        resumed: true,
        run_id: "run-1",
        resume_attempt_id: "resume-attempt-1",
      });
      await decision.promise;
    });

    await waitFor(() => expect(screen.getByText("Accepted by backend")).toBeInTheDocument());
  });

  it("reconciles websocket decision updates through backend run state", async () => {
    let invalidateFromWebSocket: (() => void | Promise<void>) | undefined;
    mockUseRunLiveUpdates.mockImplementation((_runId, onInvalidated) => {
      invalidateFromWebSocket = onInvalidated;
    });
    mockOperationRepository.getBackendState.mockResolvedValue({
      status: "resume_requested",
      recoveryState: "resume_dispatch_failed",
    });

    render(<ApprovalsPage />);

    await screen.findAllByText("Acme Operations");

    await act(async () => {
      await invalidateFromWebSocket?.();
    });

    expect(mockOperationRepository.getBackendState).toHaveBeenCalledWith("run-1");
    await waitFor(() => expect(screen.getByText("Failed to resume")).toBeInTheDocument());
  });

  it("treats backend authorization and conflict errors as backend-final approval state", async () => {
    const user = userEvent.setup();
    mockApprovalRepository.decide.mockRejectedValue({
      response: {
        status: 409,
        data: {
          error: {
            code: "DECISION_CONFLICT",
            message: "Approval task has already resolved with a different decision.",
          },
        },
      },
    });

    render(<ApprovalsPage />);

    await screen.findAllByText("Acme Operations");
    await user.click(screen.getByRole("button", { name: /^approve$/i }));

    await waitFor(() =>
      expect(
        screen.getByText("The backend has already recorded a different decision for this approval."),
      ).toBeInTheDocument(),
    );
    expect(screen.queryByText("Accepted by backend")).not.toBeInTheDocument();
  });
});
