import {
  toEvaluationRunVM,
  toMetricSnapshotVM,
  toOperatingModelPackVM,
  toReportRunVM,
  toStageOutputGenerationVM,
} from "@/lib/operating-model-packs";
import type { OperatingModelPack } from "@/lib/api";

describe("operating model pack ViewModels", () => {
  it("uses pack metadata for labels instead of vertical-specific frontend constants", () => {
    const pack: OperatingModelPack = {
      pack_id: "legal_ops_demo.v1",
      base_pack_id: "legal_ops_demo",
      version: "1.0.0",
      display_name: "Legal Ops Demo",
      description: "A legal operations pack.",
      company_type_label: "Legal Operations Team",
      checksum: "demo",
      manifest: {},
      files: {
        programs: {
          program_templates: [
            {
              id: "legal.matter",
              display_label: "Matter",
              title_template: "{{ company_name }} Matter",
              objective_template: "Run matter intake and review.",
              default_current_stage_id: "intake",
            },
          ],
        },
        operations: {
          operation_templates: [
            {
              id: "legal.conflict_review",
              department_id: "risk",
              label: "Conflict Review",
              description: "Check client and matter conflicts.",
              outputs: ["conflict_summary"],
              tool_ids: ["conflict_checker"],
              module_ids: ["legal_risk"],
            },
          ],
        },
        modules: {
          modules: [
            {
              id: "legal_risk",
              label: "Legal Risk",
              description: "Risk review module.",
              department_id: "risk",
              capabilities: ["conflict review"],
              operation_template_ids: ["legal.conflict_review"],
              artifact_schema_ids: ["memo"],
              required_tool_ids: ["conflict_checker"],
              optional_tool_ids: [],
              evaluation_profile_ids: ["legal.privilege_check"],
              policy_requirements: ["send_to_client"],
              stage_ids: ["intake"],
            },
          ],
        },
        service_model: {
          service_sections: [
            {
              id: "legal_service_history",
              label: "Service History",
              description: "Preserve client service records.",
              stage_ids: ["intake"],
              operation_template_ids: ["legal.conflict_review"],
              artifact_schema_ids: ["memo"],
              operations: ["Preserve file"],
            },
          ],
        },
        assertions: {
          assertion_labels: {
            FACT: "Established Fact",
            OPINION: "Counsel View",
            ASSUMPTION: "Working Assumption",
            QUESTION: "Open Question",
          },
          categories: ["client", "jurisdiction"],
        },
        artifacts: {
          artifact_schemas: [{ id: "memo", label: "Legal Memo" }],
        },
        evaluations: {
          profiles: [{ id: "legal.privilege_check", label: "Privilege Check", mode: "compliance" }],
        },
        policies: {
          policy_packs: [
            {
              rules: [{ action_type: "send_to_client", risk_floor: "HIGH" }],
            },
          ],
        },
        dashboards: {
          panels: [{ id: "legal.matter_center", label: "Matter Center" }],
        },
        tools: {
          tool_packages: [
            {
              id: "legal.document_export",
              label: "Document Export",
              category: "document",
              side_effects: "write",
              approval_required: true,
              dry_run: true,
              policy_action_type: "export_document",
            },
          ],
          department_tools: [
            {
              id: "conflict_checker",
              label: "Conflict Checker",
              department_id: "risk",
              category: "risk",
              side_effects: "none",
              approval_required: false,
            },
          ],
        },
      },
    };

    const viewModel = toOperatingModelPackVM(pack);

    expect(viewModel.companyTypeLabel).toBe("Legal Operations Team");
    expect(viewModel.programTemplates[0]).toMatchObject({ id: "legal.matter", label: "Matter" });
    expect(viewModel.operationTemplates[0]).toMatchObject({
      id: "legal.conflict_review",
      label: "Conflict Review",
      outputs: ["conflict_summary"],
      moduleIds: ["legal_risk"],
    });
    expect(viewModel.modules[0]).toMatchObject({
      id: "legal_risk",
      label: "Legal Risk",
      operationTemplateIds: ["legal.conflict_review"],
    });
    expect(viewModel.serviceSections[0]).toMatchObject({
      id: "legal_service_history",
      label: "Service History",
      operationTemplateIds: ["legal.conflict_review"],
    });
    expect(viewModel.assertionKinds.map((kind) => kind.label)).toEqual([
      "Established Fact",
      "Counsel View",
      "Working Assumption",
      "Open Question",
    ]);
    expect(viewModel.assertionCategories).toEqual(["client", "jurisdiction"]);
    expect(viewModel.artifactSchemas[0]).toMatchObject({ id: "memo", label: "Legal Memo" });
    expect(viewModel.evaluationProfiles[0]).toMatchObject({ id: "legal.privilege_check", label: "Privilege Check" });
    expect(viewModel.policyActions[0]).toMatchObject({ actionType: "send_to_client", riskFloor: "HIGH" });
    expect(viewModel.toolPackages[0]).toMatchObject({
      id: "legal.document_export",
      approvalRequired: true,
      policyActionType: "export_document",
    });
    expect(viewModel.departmentTools[0]).toMatchObject({ id: "conflict_checker", departmentId: "risk" });
    expect(viewModel.dashboardPanels[0]).toMatchObject({ label: "Matter Center" });
  });

  it("maps stage output generation results without vertical-specific fields", () => {
    const output = toStageOutputGenerationVM({
      workflow_id: "intake.outputs",
      program_id: "program-1",
      stage_id: "intake",
      status: "awaiting_validation",
      created_artifacts: [
        {
          id: "artifact-1",
          company_id: "company-1",
          title: "Intake Memo",
          artifact_type: "memo",
          program_id: "program-1",
          status: "active",
          metadata: {},
          canonical_revision_id: "revision-1",
          revisions: [
            {
              id: "revision-1",
              asset_id: "artifact-1",
              version_number: 1,
              label: "v1",
              content_uri: "forgegraph://assets/revision-1/inline",
              content_hash: "hash",
              mime_type: "application/json",
              metadata: {},
              created_at: "2026-05-12T00:00:00Z",
            },
          ],
          created_at: "2026-05-12T00:00:00Z",
          updated_at: "2026-05-12T00:00:00Z",
        },
      ],
      evaluations: [],
      created_signals: [],
      blockers: [],
      skipped: [],
      state_projection: {
        id: "projection-1",
        company_id: "company-1",
        program_id: "program-1",
        projection_type: "currently_true_state",
        display_label: "Current State",
        source_refs: [],
        json_state: {},
        markdown_summary: "Current state",
        generated_by: "system",
        created_at: "2026-05-12T00:00:00Z",
        updated_at: "2026-05-12T00:00:00Z",
      },
    });

    expect(output.createdArtifacts[0]).toMatchObject({ artifactType: "memo", revisionCount: 1 });
    expect(output.projection.label).toBe("Current State");
  });

  it("maps generic scorecard evaluation data without KPI-specific models", () => {
    const evaluation = toEvaluationRunVM({
      id: "evaluation-1",
      company_id: "company-1",
      program_id: "program-1",
      asset_id: null,
      asset_version_id: null,
      profile_id: "atlas_monthly_kpi_scorecard.v1",
      status: "WARN",
      score: 65,
      grade: "C",
      input_refs: [],
      result: {
        recommended_operation_template_ids: ["atlas.hook_creation"],
      },
      findings: [
        {
          id: "finding-1",
          severity: "CRITICAL",
          issue_type: "scorecard_bad_or_risky",
          message: "Engagement is low.",
          evidence_refs: [],
          suggested_fix: "Review hooks.",
          blocking: false,
          created_at: "2026-05-12T00:00:00Z",
        },
      ],
      scorecard: {
        composite_score: 65,
        grade: "C",
        dimensions: {
          metrics: [
            {
              metric_id: "social_engagement_rate",
              label: "Engagement Rate redes sociales",
              level: "bad_or_risky",
              level_label: "Malo / Riesgoso",
              score: 25,
              value: 0.7,
              unit: "percentage",
              recommended_operation_template_ids: ["atlas.hook_creation"],
              trend: {
                movement: "recovered",
                previous_level: "bad_or_risky",
                numeric_delta: 1.5,
              },
            },
          ],
        },
      },
      created_at: "2026-05-12T00:00:00Z",
      evaluated_at: "2026-05-12T00:00:00Z",
    });

    expect(evaluation.scorecard?.metrics[0]).toMatchObject({
      metricId: "social_engagement_rate",
      level: "bad_or_risky",
      recommendedOperationIds: ["atlas.hook_creation"],
      trend: { movement: "recovered", previousLevel: "bad_or_risky", numericDelta: 1.5 },
    });
    expect(evaluation.recommendedOperationIds).toEqual(["atlas.hook_creation"]);
    expect(evaluation.blockingFindingCount).toBe(0);
  });

  it("maps generic periodic metric snapshots and report runs", () => {
    const snapshot = toMetricSnapshotVM({
      id: "snapshot-1",
      company_id: "company-1",
      program_id: "program-1",
      review_definition_id: "review-1",
      period_start: "2026-04-01",
      period_end: "2026-04-30",
      metric_values: { roas: 2.5 },
      metric_sources: {},
      source_type: "manual",
      notes: "Manual period close.",
      created_at: "2026-05-01T00:00:00Z",
    });
    const report = toReportRunVM({
      id: "report-run-1",
      company_id: "company-1",
      program_id: "program-1",
      review_definition_id: "review-1",
      metric_snapshot_id: "snapshot-1",
      report_template_id: "monthly_business_review.v1",
      period_start: "2026-04-01",
      period_end: "2026-04-30",
      evaluation_run_ids: ["evaluation-1"],
      artifact: null,
      artifact_revision_id: null,
      generated_sections: { summary: { score: 75 } },
      source_refs: [],
      created_at: "2026-05-01T00:00:00Z",
    });

    expect(snapshot).toMatchObject({
      id: "snapshot-1",
      reviewDefinitionId: "review-1",
      metricValues: { roas: 2.5 },
    });
    expect(report).toMatchObject({
      id: "report-run-1",
      metricSnapshotId: "snapshot-1",
      evaluationRunIds: ["evaluation-1"],
    });
  });
});
