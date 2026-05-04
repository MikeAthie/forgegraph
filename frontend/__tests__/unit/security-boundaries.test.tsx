import fs from "fs";
import path from "path";

import { render, screen } from "@testing-library/react";
import { useRouter } from "next/router";

import ProtectedRoute from "@/components/ProtectedRoute";
import { useAuth } from "@/contexts/AuthContext";

jest.mock("@/contexts/AuthContext");
jest.mock("next/router");

const mockUseAuth = useAuth as jest.MockedFunction<typeof useAuth>;
const mockUseRouter = useRouter as jest.MockedFunction<typeof useRouter>;

const frontendRoot = path.resolve(__dirname, "../..");

function readFrontendSource(relativePath: string) {
  return fs.readFileSync(path.join(frontendRoot, relativePath), "utf8");
}

describe("security boundary enforcement", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseRouter.mockReturnValue({
      push: jest.fn(),
      replace: jest.fn(),
      prefetch: jest.fn(),
      pathname: "/approvals",
      query: {},
      asPath: "/approvals",
      isReady: true,
    } as any);
  });

  it("does not render protected children before authentication is confirmed", () => {
    mockUseAuth.mockReturnValue({
      user: null,
      loading: false,
      error: null,
      isAuthenticated: false,
      login: jest.fn(),
      register: jest.fn(),
      logout: jest.fn(),
      checkAuth: jest.fn(),
      clearError: jest.fn(),
    });

    render(
      <ProtectedRoute>
        <div>SECRET_RUN_ID=run-cross-org-1</div>
      </ProtectedRoute>,
    );

    expect(screen.getByText("Redirecting to sign in...")).toBeInTheDocument();
    expect(screen.queryByText(/SECRET_RUN_ID/)).not.toBeInTheDocument();
  });

  it("keys rendered app state by authenticated user and organization", () => {
    const source = readFrontendSource("pages/_app.tsx");

    expect(source).toContain("default_organization_id");
    expect(source).toContain("organizationScopeKey");
    expect(source).toContain("anonymous");
    expect(source).toContain("<Component key={organizationScopeKey}");
  });

  it("clears access-token state on logout and auth failure", () => {
    const authSource = readFrontendSource("contexts/AuthContext.tsx");
    const apiSource = readFrontendSource("lib/api.ts");

    expect(authSource).toContain("clearTokens()");
    expect(apiSource).toContain("export const clearTokens");
    expect(apiSource).toContain("window.sessionStorage.removeItem(E2E_ACCESS_TOKEN_KEY)");
    expect(apiSource).toContain("await api.post(API_PATHS.auth.logout");
  });

  it("submits approval decisions without client-side organization authority", () => {
    const source = readFrontendSource("domain/repositories/approvalRepository.ts");

    expect(source).toContain("operationRepository.resumeAfterApproval");
    expect(source).toContain("approval.operationId");
    expect(source).toContain("approval.departmentId");
    expect(source).not.toMatch(/\borg(anization)?_?id\b/i);
  });

  it("propagates idempotency keys for retryable run and operator commands", () => {
    const apiSource = readFrontendSource("lib/api.ts");
    const operationRepositorySource = readFrontendSource("domain/repositories/operationRepository.ts");

    expect(apiSource).toContain('"Idempotency-Key": options.idempotencyKey');
    for (const method of [
      "start:",
      "invoke:",
      "cancel:",
      "resume:",
      "replay:",
      "replayIntent:",
      "acknowledgeIntent:",
      "replayEventDeadLetter:",
      "acknowledgeEventDeadLetter:",
      "forceFailRun:",
      "forceCancelRun:",
      "forceRehydrateRun:",
    ]) {
      expect(apiSource).toContain(method);
    }

    expect(operationRepositorySource).toContain("operation.cancel:${operationId}");
    expect(operationRepositorySource).toContain("operation.resume:${operationId}:${departmentId}");
    expect(operationRepositorySource).toContain('newClientActionId("operation.launch")');
    expect(operationRepositorySource).toContain("newClientActionId(`operation.replay:${operationId}`)");
  });
});
