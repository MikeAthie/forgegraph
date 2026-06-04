import { render, screen, within } from "@testing-library/react";

import { AgencyHealthPanel, type AgencyHealthSnapshot } from "@/components/company/AgencyHealthPanel";

const snapshot: AgencyHealthSnapshot = {
  agencyName: "Atlas Studio",
  healthScore: 72,
  status: "watch",
  statusLabel: "Watch",
  dimensions: [
    {
      id: "delivery",
      label: "Delivery Quality",
      score: 88,
      status: "healthy",
      summary: "Recent deliverables are leaving review with minor polish only.",
    },
    {
      id: "connectors",
      label: "Connector Readiness",
      score: 61,
      status: "watch",
      summary: "Two client channels are ready; CRM writeback still needs setup.",
    },
  ],
  checklist: [
    { id: "brief", label: "Operating brief accepted", complete: true },
    { id: "channels", label: "Client channels mapped", complete: true },
    { id: "crm", label: "CRM writeback connected", complete: false },
  ],
  connectors: {
    ready: 2,
    degraded: 1,
    missing: 1,
    summary: "2 ready, 1 degraded, 1 missing",
    items: [
      { id: "email", label: "Email intake", status: "ready" },
      {
        id: "crm",
        label: "CRM writeback",
        status: "missing",
        metadata: {
          secretRef: "sk-live-raw-secret",
        },
      },
    ],
  },
  nextActions: [
    {
      id: "scope",
      label: "Confirm CRM writeback owner",
      owner: "Operator",
      dueLabel: "Today",
      internalNote: "Internal scope risk: account owner has not approved write access.",
    },
  ],
  risks: [
    {
      id: "handoff",
      label: "Client handoff depends on CRM writeback.",
      severity: "medium",
      internalNote: "Internal scope risk: staged rollout required.",
    },
  ],
  opportunities: [
    {
      id: "retainer",
      label: "Weekly delivery digest can become a retainer touchpoint.",
      impact: "high",
      internalNote: "Internal pricing hint: bundle with reporting add-on.",
    },
  ],
  metadata: {
    credentialId: "cred_123456789",
    bearerToken: "raw-token-value",
  },
};

describe("AgencyHealthPanel", () => {
  it("renders the cockpit health summary without exposing raw metadata or connector secrets", () => {
    render(<AgencyHealthPanel snapshot={snapshot} audience="operator" />);

    const panel = screen.getByRole("region", { name: /agency cockpit health/i });
    expect(within(panel).getByRole("heading", { name: /agency cockpit/i })).toBeInTheDocument();
    expect(within(panel).getByText("72")).toBeInTheDocument();
    expect(within(panel).getByText("Watch")).toBeInTheDocument();
    expect(screen.getByTestId("agency-health-status-dot")).toHaveClass("bg-amber-500");
    expect(within(panel).getByText(/lowest dimension/i)).toBeInTheDocument();
    expect(within(panel).getByText("Connector Readiness")).toBeInTheDocument();
    expect(within(panel).getByText("2/3 complete")).toBeInTheDocument();
    expect(within(panel).getByText("2 ready, 1 degraded, 1 missing")).toBeInTheDocument();
    expect(within(panel).getByText("Confirm CRM writeback owner")).toBeInTheDocument();
    expect(within(panel).getByText("Client handoff depends on CRM writeback.")).toBeInTheDocument();
    expect(within(panel).getByText("Weekly delivery digest can become a retainer touchpoint.")).toBeInTheDocument();

    expect(screen.queryByText("sk-live-raw-secret")).not.toBeInTheDocument();
    expect(screen.queryByText("cred_123456789")).not.toBeInTheDocument();
    expect(screen.queryByText("raw-token-value")).not.toBeInTheDocument();
  });

  it("shows internal risk and scope hints only in the operator view", () => {
    const { rerender } = render(<AgencyHealthPanel snapshot={snapshot} audience="operator" />);

    expect(screen.getByText("Internal scope risk: staged rollout required.")).toBeInTheDocument();
    expect(screen.getByText("Internal pricing hint: bundle with reporting add-on.")).toBeInTheDocument();

    rerender(<AgencyHealthPanel snapshot={snapshot} audience="client" />);

    expect(screen.queryByText("Internal scope risk: staged rollout required.")).not.toBeInTheDocument();
    expect(screen.queryByText("Internal pricing hint: bundle with reporting add-on.")).not.toBeInTheDocument();
    expect(screen.queryByText(/internal scope risk/i)).not.toBeInTheDocument();
  });
});
