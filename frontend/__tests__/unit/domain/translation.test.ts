import { toOperationVM } from "@/domain/translation";
import type { RunDetail } from "@/lib/api";

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
});
