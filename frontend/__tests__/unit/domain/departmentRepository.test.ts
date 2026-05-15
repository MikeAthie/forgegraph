import { departmentRepository } from "@/domain/repositories/departmentRepository";
import { departmentsApi, decisionsApi, memoryApi, routingApi, tasksApi } from "@/lib/api";

jest.mock("@/lib/api", () => ({
  agentsApi: {
    list: jest.fn(),
  },
  decisionsApi: {
    list: jest.fn(),
  },
  departmentsApi: {
    list: jest.fn(),
  },
  memoryApi: {
    timeline: jest.fn(),
  },
  routingApi: {
    listInbox: jest.fn(),
  },
  tasksApi: {
    list: jest.fn(),
  },
}));

jest.mock("@/domain/repositories/operationRepository", () => ({
  operationRepository: {
    list: jest.fn().mockResolvedValue([
      {
        id: "operation-1",
        companyId: "company-1",
        companyName: "Legacy Eyewear",
        setupVersionId: "version-1",
        setupVersion: 1,
        status: "running",
        queueStatus: null,
        attempts: 1,
        startedAt: "2026-05-14T10:00:00Z",
        endedAt: null,
        durationMs: null,
        brief: "Launch campaign",
        currentDepartmentName: "Channel Ops",
        tasks: [],
        deliverable: {
          id: "deliverable-1",
          operationId: "operation-1",
          title: "Campaign",
          preview: "",
          content: null,
          ready: false,
          createdAt: null,
        },
        failure: null,
      },
    ]),
    listTasks: () => tasksApi.list(),
  },
}));

describe("departmentRepository.listActivity", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.mocked(decisionsApi.list).mockResolvedValue([]);
    jest.mocked(memoryApi.timeline).mockResolvedValue([]);
  });

  it("uses department registry ownership and authorized routing inbox items", async () => {
    jest.mocked(departmentsApi.list).mockResolvedValue([
      {
        id: "dept-channel",
        organization_id: "org-1",
        slug: "channel-ops",
        name: "Channel Ops",
        department_type: "channel_ops",
        service_tags: ["whatsapp"],
        active: true,
        metadata: { responsibility: "Owns live channel execution." },
        role: "lead",
        can_manage: true,
        created_at: "2026-05-14T09:00:00Z",
        updated_at: "2026-05-14T09:00:00Z",
      },
    ]);
    jest.mocked(tasksApi.list).mockResolvedValue([
      {
        id: "task-1",
        organization_id: "org-1",
        execution_id: "operation-1",
        agent_id: null,
        department_id: "dept-channel",
        department_name: "Channel Ops",
        title: "Prepare WhatsApp rollout",
        status: "queued",
        priority: "normal",
        summary: "Waiting for connector readiness.",
        source_node_id: "channel",
        current_step_id: null,
        current_decision_id: null,
        lifecycle_task_id: "life-1",
        started_at: null,
        ended_at: null,
        created_at: "2026-05-14T09:05:00Z",
        updated_at: "2026-05-14T09:05:00Z",
      },
    ]);
    jest.mocked(routingApi.listInbox).mockResolvedValue([
      {
        id: "route-1",
        organization_id: "org-1",
        company_id: "company-1",
        task_lifecycle_id: "life-1",
        task_record_id: "task-1",
        run_id: "operation-1",
        from_department_id: null,
        to_department_id: "dept-channel",
        to_department_name: "Channel Ops",
        assigned_user_id: null,
        reason: "WhatsApp connector is missing.",
        status: "blocked",
        due_at: null,
        sla_breached_at: null,
        resolution: {},
        metadata: {},
        created_at: "2026-05-14T09:06:00Z",
        updated_at: "2026-05-14T09:06:00Z",
      },
    ]);

    const activities = await departmentRepository.listActivity();

    expect(departmentsApi.list).toHaveBeenCalled();
    expect(routingApi.listInbox).toHaveBeenCalled();
    expect(activities).toHaveLength(1);
    expect(activities[0].department.id).toBe("dept-channel");
    expect(activities[0].department.activityStatus).toBe("waiting");
    expect(activities[0].blockers[0].description).toBe("WhatsApp connector is missing.");
    expect(activities[0].operations[0].id).toBe("operation-1");
  });
});
