import { operatingModelsApi } from "@/lib/api";
import { newClientCommandId, stableClientCommandId } from "@/lib/idempotency";
import {
  toAssertionRecordVM,
  toCompanyProgramVM,
  toEvaluationRunVM,
  toMetricSnapshotVM,
  toArtifactLineageVM,
  toOperatingModelPackVM,
  toPeriodicReviewVM,
  toPolicyEvaluationVM,
  toProgramOperationVM,
  toReportRunVM,
  toReworkPlanVM,
  toStageOutputGenerationVM,
  toStateProjectionVM,
  toToolExecutionReceiptVM,
  toWorkArtifactVM,
  toCompanyOperatingModelVM,
  toValidationDecisionVM,
  toValidationPacketVM,
  type ArtifactLineageVM,
  type AssertionRecordVM,
  type CompanyOperatingModelVM,
  type CompanyProgramVM,
  type EvaluationRunVM,
  type MetricSnapshotVM,
  type OperatingModelPackVM,
  type PeriodicReviewVM,
  type PolicyEvaluationVM,
  type ProgramOperationVM,
  type ReportRunVM,
  type ReworkPlanVM,
  type StageOutputGenerationVM,
  type StateProjectionVM,
  type ToolExecutionReceiptVM,
  type ValidationDecisionVM,
  type ValidationPacketVM,
  type WorkArtifactVM,
} from "@/lib/operating-model-packs";

export const operatingModelRepository = {
  listPacks: async (): Promise<OperatingModelPackVM[]> => {
    const packs = await operatingModelsApi.listPacks();
    return packs.map(toOperatingModelPackVM);
  },

  getCompanyOperatingModel: async (companyId: string): Promise<CompanyOperatingModelVM> => {
    const model = await operatingModelsApi.getCompanyOperatingModel(companyId);
    return toCompanyOperatingModelVM(model);
  },

  listPrograms: async (companyId: string): Promise<CompanyProgramVM[]> => {
    const programs = await operatingModelsApi.listPrograms(companyId);
    return programs.map(toCompanyProgramVM);
  },

  getProgram: async (programId: string): Promise<CompanyProgramVM> => {
    const program = await operatingModelsApi.getProgram(programId);
    return toCompanyProgramVM(program);
  },

  installPack: async (companyId: string, packId: string): Promise<OperatingModelPackVM> => {
    const installation = await operatingModelsApi.installPack(
      companyId,
      packId,
      {},
      { idempotencyKey: stableClientCommandId("operating-model-pack.install", companyId, packId) },
    );
    return toOperatingModelPackVM(installation);
  },

  createProgram: async (input: {
    companyId: string;
    templateId: string;
    packId?: string;
    title?: string;
    objective?: string;
  }): Promise<CompanyProgramVM> => {
    const program = await operatingModelsApi.createProgram(
      input.companyId,
      {
        template_id: input.templateId,
        pack_id: input.packId,
        title: input.title,
        objective: input.objective,
      },
      { idempotencyKey: newClientCommandId("company-program.create") },
    );
    return toCompanyProgramVM(program);
  },

  advanceStage: async (input: { programId: string; stageId: string; status: string }): Promise<CompanyProgramVM> => {
    const program = await operatingModelsApi.advanceStage(
      input.programId,
      input.stageId,
      { status: input.status },
      { idempotencyKey: newClientCommandId("program-stage.advance") },
    );
    return toCompanyProgramVM(program);
  },

  launchStageOperation: async (input: {
    programId: string;
    stageId: string;
    operationTemplateId: string;
    contextNote?: string;
  }): Promise<ProgramOperationVM> => {
    const operation = await operatingModelsApi.launchStageOperation(
      input.programId,
      input.stageId,
      {
        operation_template_id: input.operationTemplateId,
        context_note: input.contextNote,
      },
      { idempotencyKey: newClientCommandId("program-stage.operation-launch") },
    );
    return toProgramOperationVM(operation);
  },

  generateStageOutputs: async (input: {
    programId: string;
    stageId: string;
    workflowId?: string;
    artifactSchemaIds?: string[];
    selectedFamilyIds?: string[];
    sourceArtifactIds?: string[];
    notes?: string;
    evaluationInputs?: Record<string, unknown>;
  }): Promise<StageOutputGenerationVM> => {
    const result = await operatingModelsApi.generateStageOutputs(
      input.programId,
      input.stageId,
      {
        workflow_id: input.workflowId,
        artifact_schema_ids: input.artifactSchemaIds ?? [],
        selected_family_ids: input.selectedFamilyIds ?? [],
        source_artifact_ids: input.sourceArtifactIds ?? [],
        notes: input.notes,
        evaluation_inputs: input.evaluationInputs ?? {},
      },
      { idempotencyKey: newClientCommandId("program-stage.outputs-generate") },
    );
    return toStageOutputGenerationVM(result);
  },

  getValidationPacket: async (programId: string): Promise<ValidationPacketVM> => {
    const packet = await operatingModelsApi.getValidationPacket(programId);
    return toValidationPacketVM(packet);
  },

  createAssertion: async (input: {
    companyId: string;
    programId?: string;
    kind: "FACT" | "OPINION" | "ASSUMPTION" | "QUESTION";
    statement: string;
    category?: string;
    source?: string;
    confidence?: number;
    packLabel?: string;
  }): Promise<AssertionRecordVM> => {
    const assertion = await operatingModelsApi.createAssertion(
      {
        company_id: input.companyId,
        program_id: input.programId,
        kind: input.kind,
        statement: input.statement,
        category: input.category,
        source: input.source,
        confidence: input.confidence,
        pack_label: input.packLabel,
      },
      { idempotencyKey: newClientCommandId("assertion.create") },
    );
    return toAssertionRecordVM(assertion);
  },

  listAssertions: async (input: {
    companyId: string;
    programId?: string;
    kind?: string;
  }): Promise<AssertionRecordVM[]> => {
    const assertions = await operatingModelsApi.listAssertions({
      company_id: input.companyId,
      program_id: input.programId,
      kind: input.kind,
    });
    return assertions.map(toAssertionRecordVM);
  },

  createValidationDecision: async (input: {
    companyId: string;
    programId?: string;
    assertionId?: string;
    artifactId?: string;
    artifactVersionId?: string;
    decision: "ACCEPT" | "REJECT" | "EDIT" | "DEFER" | "NEEDS_RESEARCH";
    category?: string;
    rationale?: string;
    proposedChange?: Record<string, unknown>;
  }): Promise<ValidationDecisionVM> => {
    const decision = await operatingModelsApi.createValidationDecision(
      {
        company_id: input.companyId,
        program_id: input.programId,
        assertion_id: input.assertionId,
        asset_id: input.artifactId,
        asset_version_id: input.artifactVersionId,
        decision: input.decision,
        category: input.category,
        rationale: input.rationale,
        proposed_change: input.proposedChange ?? {},
      },
      { idempotencyKey: newClientCommandId("validation-decision.create") },
    );
    return toValidationDecisionVM(decision);
  },

  listArtifacts: async (input: { companyId: string; artifactType?: string }): Promise<WorkArtifactVM[]> => {
    const artifacts = await operatingModelsApi.listArtifacts({
      company_id: input.companyId,
      artifact_type: input.artifactType,
    });
    return artifacts.map(toWorkArtifactVM);
  },

  createArtifact: async (input: {
    companyId: string;
    programId?: string;
    title: string;
    artifactType: string;
    content: unknown;
  }): Promise<WorkArtifactVM> => {
    const result = await operatingModelsApi.createArtifact(
      {
        company_id: input.companyId,
        program_id: input.programId,
        title: input.title,
        artifact_type: input.artifactType,
        content: input.content,
      },
      { idempotencyKey: newClientCommandId("work-artifact.create") },
    );
    return toWorkArtifactVM(result.artifact);
  },

  getArtifact: async (artifactId: string): Promise<WorkArtifactVM> => {
    const artifact = await operatingModelsApi.getArtifact(artifactId);
    return toWorkArtifactVM(artifact);
  },

  createArtifactRevision: async (input: {
    artifactId: string;
    content: unknown;
    parentRevisionId?: string | null;
    label?: string;
  }): Promise<void> => {
    await operatingModelsApi.createArtifactRevision(
      input.artifactId,
      {
        content: input.content,
        parent_revision_id: input.parentRevisionId,
        label: input.label,
      },
      { idempotencyKey: newClientCommandId("artifact-revision.create") },
    );
  },

  getArtifactLineage: async (artifactId: string): Promise<ArtifactLineageVM> => {
    const lineage = await operatingModelsApi.getArtifactLineage(artifactId);
    return toArtifactLineageVM(lineage);
  },

  setCanonicalRevision: async (artifactId: string, revisionId: string): Promise<WorkArtifactVM> => {
    const artifact = await operatingModelsApi.setCanonicalRevision(artifactId, revisionId, {
      idempotencyKey: newClientCommandId("artifact.canonical-revision"),
    });
    return toWorkArtifactVM(artifact);
  },

  runEvaluation: async (input: {
    companyId: string;
    profileId: string;
    content?: string;
    inputs?: Record<string, unknown>;
    programId?: string;
    artifactId?: string;
    artifactVersionId?: string;
  }): Promise<EvaluationRunVM> => {
    const evaluation = await operatingModelsApi.runEvaluation(
      {
        company_id: input.companyId,
        profile_id: input.profileId,
        content: input.content,
        inputs: input.inputs ?? {},
        program_id: input.programId,
        asset_id: input.artifactId,
        asset_version_id: input.artifactVersionId,
      },
      { idempotencyKey: newClientCommandId("evaluation.run") },
    );
    return toEvaluationRunVM(evaluation);
  },

  listPeriodicReviews: async (input: { companyId: string; programId?: string }): Promise<PeriodicReviewVM[]> => {
    const reviews = await operatingModelsApi.listPeriodicReviews({
      company_id: input.companyId,
      program_id: input.programId,
    });
    return reviews.map(toPeriodicReviewVM);
  },

  createMetricSnapshot: async (input: {
    companyId: string;
    programId?: string;
    reviewDefinitionId?: string;
    periodStart: string;
    periodEnd: string;
    metricValues: Record<string, unknown>;
    metricSources?: Record<string, unknown>;
    sourceType?: string;
    notes?: string;
  }): Promise<MetricSnapshotVM> => {
    const snapshot = await operatingModelsApi.createMetricSnapshot(
      {
        company_id: input.companyId,
        program_id: input.programId,
        review_definition_id: input.reviewDefinitionId,
        period_start: input.periodStart,
        period_end: input.periodEnd,
        metric_values: input.metricValues,
        metric_sources: input.metricSources ?? {},
        source_type: input.sourceType ?? "manual",
        notes: input.notes ?? "",
      },
      { idempotencyKey: newClientCommandId("metric-snapshot.create") },
    );
    return toMetricSnapshotVM(snapshot);
  },

  listMetricSnapshots: async (input: {
    companyId: string;
    programId?: string;
    reviewDefinitionId?: string;
  }): Promise<MetricSnapshotVM[]> => {
    const snapshots = await operatingModelsApi.listMetricSnapshots({
      company_id: input.companyId,
      program_id: input.programId,
      review_definition_id: input.reviewDefinitionId,
    });
    return snapshots.map(toMetricSnapshotVM);
  },

  runPeriodicReview: async (input: {
    reviewId: string;
    metricSnapshotId: string;
    notes?: string;
  }): Promise<{ evaluation: EvaluationRunVM; reportRun: ReportRunVM }> => {
    const result = await operatingModelsApi.runPeriodicReview(
      input.reviewId,
      {
        metric_snapshot_id: input.metricSnapshotId,
        notes: input.notes ?? "",
      },
      { idempotencyKey: newClientCommandId("periodic-review.run") },
    );
    return {
      evaluation: toEvaluationRunVM(result.evaluation),
      reportRun: toReportRunVM(result.report_run),
    };
  },

  listReportRuns: async (input: {
    companyId: string;
    programId?: string;
    reviewDefinitionId?: string;
  }): Promise<ReportRunVM[]> => {
    const runs = await operatingModelsApi.listReportRuns({
      company_id: input.companyId,
      program_id: input.programId,
      review_definition_id: input.reviewDefinitionId,
    });
    return runs.map(toReportRunVM);
  },

  evaluatePolicy: async (input: {
    companyId: string;
    actionType: string;
    inputs?: Record<string, unknown>;
  }): Promise<PolicyEvaluationVM> => {
    const evaluation = await operatingModelsApi.evaluatePolicy(
      {
        company_id: input.companyId,
        action_type: input.actionType,
        inputs: input.inputs ?? {},
      },
      { idempotencyKey: newClientCommandId("policy-evaluation.create") },
    );
    return toPolicyEvaluationVM(evaluation);
  },

  createReworkPlan: async (input: {
    companyId: string;
    programId?: string;
    validationDecisionIds?: string[];
  }): Promise<ReworkPlanVM> => {
    const plan = await operatingModelsApi.createReworkPlan(
      {
        company_id: input.companyId,
        program_id: input.programId,
        validation_decision_ids: input.validationDecisionIds ?? [],
      },
      { idempotencyKey: newClientCommandId("rework-plan.create") },
    );
    return toReworkPlanVM(plan);
  },

  executeReworkPlan: async (planId: string): Promise<ReworkPlanVM> => {
    const plan = await operatingModelsApi.executeReworkPlan(planId, {
      idempotencyKey: newClientCommandId("rework-plan.execute"),
    });
    return toReworkPlanVM(plan);
  },

  executeTool: async (input: {
    companyId: string;
    operationId: string;
    toolId: string;
    dryRun?: boolean;
    inputs?: Record<string, unknown>;
  }): Promise<ToolExecutionReceiptVM> => {
    const receipt = await operatingModelsApi.executeTool(
      {
        company_id: input.companyId,
        operation_id: input.operationId,
        tool_id: input.toolId,
        dry_run: input.dryRun ?? true,
        inputs: input.inputs ?? {},
      },
      { idempotencyKey: newClientCommandId("pack-tool.execute") },
    );
    return toToolExecutionReceiptVM(receipt);
  },

  listStateProjections: async (
    companyId: string,
    programId?: string,
    projectionType = "currently_true_state",
  ): Promise<StateProjectionVM[]> => {
    const projections = await operatingModelsApi.listStateProjections({
      company_id: companyId,
      program_id: programId,
      projection_type: projectionType,
    });
    return projections.map(toStateProjectionVM);
  },
};

type OperatingModelRepository = typeof operatingModelRepository;
