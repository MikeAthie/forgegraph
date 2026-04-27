import {
  buildCompanyGraphJson,
  buildCompanyProfile,
  getCompanyProfileFromGraph,
  getCurrentDepartmentLabel,
  getDepartmentProgress,
  inferCompanyPresetFromObjective,
  translateFailure,
  translateRunStatus,
} from "@/lib/company-workspace";

describe("company-workspace helpers", () => {
  it("builds a company operating model with department steps and a final deliverable", () => {
    const profile = buildCompanyProfile({
      companyName: "Northstar Growth Co.",
      companyType: "General Company",
      objective: "Launch a repeatable growth program.",
    });

    const graphJson = buildCompanyGraphJson(profile);

    expect(graphJson.metadata?.company_profile).toEqual(profile);
    expect(graphJson.nodes.some((node) => node.type === "output")).toBe(true);
    expect(graphJson.nodes.filter((node) => node.type === "agent")).toHaveLength(profile.departments.length);
    expect(graphJson.edges.some((edge) => edge.from === "START")).toBe(true);
  });

  it("reads company metadata first and falls back to graph information for legacy models", () => {
    const profile = buildCompanyProfile({
      companyName: "Atlas Ops",
      companyType: "Operations & Delivery",
      objective: "Improve follow-up quality.",
    });

    const explicit = getCompanyProfileFromGraph(
      { name: "Ignored Name", description: "Ignored objective" },
      {
        nodes: [],
        edges: [],
        metadata: {
          company_profile: profile,
        },
      },
    );

    expect(explicit.companyName).toBe("Atlas Ops");
    expect(explicit.objective).toBe("Improve follow-up quality.");

    const inferred = getCompanyProfileFromGraph(
      { name: "Legacy Workflow", description: "Legacy objective" },
      {
        nodes: [
          { id: "agent_1", type: "agent", name: "Strategy Department", config: {} },
          { id: "output_1", type: "output", name: "Final Deliverable", config: {} },
        ],
        edges: [],
      },
    );

    expect(inferred.companyName).toBe("Legacy Workflow");
    expect(inferred.objective).toBe("Legacy objective");
    expect(inferred.departments[0]?.label).toBe("Strategy Department");
  });

  it("suggests a broader company category from the objective", () => {
    expect(inferCompanyPresetFromObjective("Generate legal documents and client-ready case briefs.").label).toBe(
      "Professional Services",
    );
    expect(inferCompanyPresetFromObjective("Coordinate site operations, scheduling, and project delivery.").label).toBe(
      "Operations & Delivery",
    );
    expect(inferCompanyPresetFromObjective("")).toBeDefined();
  });

  it("translates runtime states and failures into customer-facing language", () => {
    expect(translateRunStatus("succeeded")).toBe("completed");
    expect(translateRunStatus("pending")).toBe("queued");

    const failure = translateFailure(
      {
        status: "failed",
        error_message: "LLM timeout while waiting for provider response",
        node_runs: [
          {
            id: "node-run-1",
            node_id: "dept_1",
            node_type: "agent",
            status: "failed",
            attempt: 1,
            started_at: null,
            ended_at: null,
            duration_ms: null,
            input_json: {},
            output_json: null,
            error_json: null,
          },
        ],
      },
      {
        nodes: [{ id: "dept_1", type: "agent", name: "Strategy Department", config: {} }],
        edges: [],
      },
    );

    expect(failure?.title).toBe("Intelligence provider timed out");
    expect(failure?.summary).toContain("Strategy Department");
  });

  it("derives current department and progress from node runs", () => {
    const graphJson = {
      nodes: [
        { id: "dept_1", type: "agent", name: "Strategy Department", config: {} },
        { id: "dept_2", type: "agent", name: "Analytics Department", config: {} },
        { id: "output_1", type: "output", name: "Final Deliverable", config: {} },
      ],
      edges: [],
    };

    const run = {
      node_runs: [
        {
          id: "node-run-1",
          node_id: "dept_1",
          node_type: "agent",
          status: "succeeded",
          attempt: 1,
          started_at: null,
          ended_at: null,
          duration_ms: null,
          input_json: {},
          output_json: null,
          error_json: null,
        },
        {
          id: "node-run-2",
          node_id: "dept_2",
          node_type: "agent",
          status: "running",
          attempt: 1,
          started_at: null,
          ended_at: null,
          duration_ms: null,
          input_json: {},
          output_json: null,
          error_json: null,
        },
      ],
    };

    const progress = getDepartmentProgress(run, graphJson);
    expect(progress).toEqual([
      { label: "Strategy Department", status: "completed" },
      { label: "Analytics Department", status: "running" },
    ]);
    expect(getCurrentDepartmentLabel(run, graphJson)).toBe("Analytics Department");
  });
});
