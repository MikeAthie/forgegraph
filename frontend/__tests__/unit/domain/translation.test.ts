import { toCompanyVM, toOperationVM } from "@/domain/translation";
import { buildCompanyGraphJson, buildCompanyProfile } from "@/lib/company-workspace";
import type { CompanyDTO, CompanyOperatingModelVersionDTO, RunDetail } from "@/lib/api";

describe("domain translation", () => {
  it("maps backend operation detail into product-safe deliverable and task view models", () => {
    const internalOperation = {
      id: "operation-1",
      owner_id: "owner-1",
      graph_id: "company-1",
      graph_name: "Revenue Pulse",
      graph_version_id: "setup-1",
      graph_version: 2,
      status: "succeeded",
      queue_status: "completed",
      queue_attempts: 1,
      queue_available_at: null,
      started_at: "2026-04-05T10:00:00Z",
      ended_at: "2026-04-05T10:01:00Z",
      input_json: { operation_brief: "Summarize weekly revenue" },
      output_json: { deliverable: "Revenue is up 8% with churn risk in segment B." },
      error_message: "",
      duration_ms: 60_000,
      node_runs: [
        {
          id: "task-1",
          node_id: "analysis",
          node_type: "agent",
          status: "succeeded",
          attempt: 1,
          started_at: "2026-04-05T10:00:00Z",
          ended_at: "2026-04-05T10:01:00Z",
          duration_ms: 60_000,
          input_json: {},
          output_json: { summary: "Analyzed weekly revenue." },
          error_json: null,
          agent_trace: null,
          memory_activity: null,
        },
      ],
      agent_events: [],
      memory_activity: null,
      paused_node_id: null,
      pause_payload: null,
    } satisfies RunDetail;

    const operation = toOperationVM(internalOperation);

    expect(operation.companyId).toBe("company-1");
    expect(operation.companyName).toBe("Revenue Pulse");
    expect(operation.status).toBe("completed");
    expect(operation.deliverable.ready).toBe(true);
    expect(operation.deliverable.preview).toContain("Revenue is up 8%");
    expect(operation.tasks).toHaveLength(1);
    expect(operation.tasks[0]?.status).toBe("completed");
  });

  it("maps company alias DTOs into product-safe company view models", () => {
    const profile = buildCompanyProfile({
      companyName: "Alias Company",
      companyType: "General Company",
      objective: "Operate through the company alias API.",
    });
    const company = {
      id: "company-1",
      company_id: "company-1",
      workflow_definition_id: "company-1",
      storage_model: "Graph",
      organization_id: "org-1",
      name: "Alias Company",
      description: "Operate through the company alias API.",
      created_at: "2026-05-12T00:00:00Z",
      updated_at: "2026-05-12T00:00:00Z",
      setup_version_count: 1,
      latest_setup_version: 1,
    } satisfies CompanyDTO;
    const setupVersion = {
      id: "version-1",
      company_id: "company-1",
      workflow_definition_id: "company-1",
      version: 1,
      model_json: buildCompanyGraphJson(profile),
      checksum: "checksum",
      created_at: "2026-05-12T00:00:00Z",
    } satisfies CompanyOperatingModelVersionDTO;

    const vm = toCompanyVM(company, setupVersion, [], 0);

    expect(vm.id).toBe("company-1");
    expect(vm.name).toBe("Alias Company");
    expect(vm.description).toBe("Operate through the company alias API.");
    expect(vm.setupVersion).toBe(1);
    expect(vm.setupVersionCount).toBe(1);
    expect(vm.status).toBe("Ready to launch");
    expect(vm.departments.length).toBeGreaterThan(0);
  });
});
