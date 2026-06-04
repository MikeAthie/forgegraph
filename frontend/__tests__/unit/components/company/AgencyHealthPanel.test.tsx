import { render, screen, within } from "@testing-library/react";

import {
  AgencyHealthPanel,
  agencyHealthSnapshotFromViewModel,
  type AgencyHealthSnapshot,
} from "@/components/company/AgencyHealthPanel";

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
  it("maps backend agency health view models into panel snapshots", () => {
    const mapped = agencyHealthSnapshotFromViewModel(
      {
        companyId: "company-1",
        generatedAt: "2026-06-04T12:00:00Z",
        health: {
          score: 72,
          status: "monitor",
          dimensions: [
            {
              slug: "connector_readiness",
              label: "Connector readiness",
              score: 45,
              status: "attention",
              weight: 20,
              ownerDepartmentSlug: "channel_execution",
              summary: "Required connector gaps are lowering account health.",
            },
          ],
        },
        onboardingItems: [
          {
            slug: "connector_setup",
            label: "Connector setup",
            status: "blocked",
            ownerDepartmentSlug: "channel_execution",
            message: "Required connectors are missing.",
          },
        ],
        connectorReadiness: {
          status: "blocked",
          summary: {
            total: 1,
            required: 1,
            ready: 0,
            missing: 1,
            degraded: 0,
            disabled: 0,
          },
          connectors: [
            {
              slug: "whatsapp",
              label: "WhatsApp",
              category: "messaging",
              required: true,
              status: "missing",
              readiness: "action_required",
              ownerDepartmentSlug: "channel_execution",
              source: "gateway_connection",
              lastSeenAt: null,
              lastHealthCheckAt: null,
              message: "WhatsApp is not connected.",
            },
          ],
        },
        risks: [
          {
            slug: "missing_required_connectors",
            label: "Required connectors missing",
            severity: "high",
            ownerDepartmentSlug: "channel_execution",
            summary: "1 required connector is not ready.",
          },
        ],
        opportunities: [],
        nextActions: [
          {
            slug: "configure_whatsapp",
            label: "Configure WhatsApp",
            priority: "high",
            ownerDepartmentSlug: "channel_execution",
            reason: "WhatsApp is not connected.",
          },
        ],
      },
      "Atlas Studio",
    );

    expect(mapped.agencyName).toBe("Atlas Studio");
    expect(mapped.status).toBe("watch");
    expect(mapped.dimensions[0]).toEqual({
      id: "connector_readiness",
      label: "Connector readiness",
      score: 45,
      status: "attention",
      summary: "Required connector gaps are lowering account health.",
    });
    expect(mapped.checklist[0]).toEqual({
      id: "connector_setup",
      label: "Connector setup",
      complete: false,
    });
    expect(mapped.connectors.items[0]).toEqual({
      id: "whatsapp",
      label: "WhatsApp",
      status: "missing",
      detail: "WhatsApp is not connected.",
    });
    expect(mapped.nextActions[0].label).toBe("Configure WhatsApp");
    expect(JSON.stringify(mapped)).not.toContain("api_key");
  });

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
