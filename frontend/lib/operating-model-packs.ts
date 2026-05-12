import type {
  AssertionRecordDTO,
  ArtifactRevisionDTO,
  CompanyOperatingModelDTO,
  CompanyProgramDTO,
  EvaluationRunDTO,
  ArtifactLineageDTO,
  MetricSnapshotDTO,
  OperatingModelInstallation,
  OperatingModelPack,
  PeriodicReviewDTO,
  PolicyEvaluationDTO,
  ProgramOperationDTO,
  ReportRunDTO,
  ReworkPlanDTO,
  StageOutputGenerationDTO,
  StateProjectionDTO,
  ToolExecutionReceiptDTO,
  ValidationDecisionDTO,
  ValidationPacketDTO,
  WorkArtifactDTO,
} from "@/lib/api";

export type OperatingModelPackVM = {
  id: string;
  name: string;
  version: string;
  companyTypeLabel: string;
  description: string;
  checksum: string;
  programTemplates: ProgramTemplateVM[];
  operationTemplates: OperationTemplateVM[];
  modules: CapabilityModuleVM[];
  serviceSections: ServiceSectionVM[];
  assertionKinds: AssertionKindVM[];
  assertionCategories: string[];
  artifactSchemas: ArtifactSchemaVM[];
  evaluationProfiles: EvaluationProfileOptionVM[];
  policyActions: PolicyActionOptionVM[];
  toolPackages: DepartmentToolVM[];
  departmentTools: DepartmentToolVM[];
  dashboardPanels: DashboardPanelVM[];
};

export type ServiceSectionVM = {
  id: string;
  label: string;
  description: string;
  stageIds: string[];
  operationTemplateIds: string[];
  artifactSchemaIds: string[];
  evaluationProfileIds: string[];
  items: string[];
};

export type ProgramTemplateVM = {
  id: string;
  label: string;
  titleTemplate: string;
  objectiveTemplate: string;
  defaultStageId: string;
};

export type OperationTemplateVM = {
  id: string;
  departmentId: string;
  label: string;
  description: string;
  outputs: string[];
  toolIds: string[];
  stageIds: string[];
  moduleIds: string[];
};

export type CapabilityModuleVM = {
  id: string;
  label: string;
  description: string;
  departmentId: string;
  capabilities: string[];
  operationTemplateIds: string[];
  artifactSchemaIds: string[];
  requiredToolIds: string[];
  optionalToolIds: string[];
  evaluationProfileIds: string[];
  policyRequirements: string[];
  stageIds: string[];
};

export type DepartmentToolVM = {
  id: string;
  label: string;
  departmentId: string;
  category: string;
  sideEffects: string;
  approvalRequired: boolean;
  dryRun: boolean;
  policyActionType: string;
};

export type AssertionKindVM = {
  kind: "FACT" | "OPINION" | "ASSUMPTION" | "QUESTION";
  label: string;
};

export type ArtifactSchemaVM = {
  id: string;
  label: string;
  description: string;
  producedByOperations: string[];
  requiredInputs: string[];
  optionalInputs: string[];
  evaluationProfiles: string[];
  stateProjectionBehavior: string;
};

export type EvaluationProfileOptionVM = {
  id: string;
  label: string;
  mode: string;
};

export type PeriodicReviewVM = {
  id: string;
  companyId: string;
  programId: string | null;
  label: string;
  cadence: string;
  evaluationProfileId: string;
  reportTemplateId: string;
  historyProjectionType: string;
  enabled: boolean;
};

export type MetricSnapshotVM = {
  id: string;
  companyId: string;
  programId: string | null;
  reviewDefinitionId: string | null;
  periodStart: string;
  periodEnd: string;
  metricValues: Record<string, unknown>;
  sourceType: string;
  notes: string;
};

export type ReportRunVM = {
  id: string;
  companyId: string;
  programId: string | null;
  reviewDefinitionId: string | null;
  metricSnapshotId: string | null;
  reportTemplateId: string;
  periodStart: string;
  periodEnd: string;
  evaluationRunIds: string[];
  artifact: WorkArtifactVM | null;
  generatedSections: Record<string, unknown>;
  createdAt: string;
};

export type PolicyActionOptionVM = {
  actionType: string;
  label: string;
  riskFloor: string;
};

export type DashboardPanelVM = {
  id: string;
  label: string;
};

export type CompanyProgramVM = {
  id: string;
  companyId: string;
  packId: string;
  templateId: string;
  label: string;
  title: string;
  objective: string;
  status: string;
  currentStageId: string;
  stages: Array<{
    id: string;
    stageId: string;
    label: string;
    sequence: number;
    status: string;
    state: Record<string, unknown>;
    operationTemplateIds: string[];
  }>;
};

export type AssertionRecordVM = {
  id: string;
  companyId: string;
  programId: string | null;
  kind: string;
  label: string;
  category: string;
  statement: string;
  source: string;
  confidence: number;
  validationStatus: string;
};

export type WorkArtifactVM = {
  id: string;
  companyId: string;
  title: string;
  artifactType: string;
  programId: string | null;
  status: string;
  canonicalRevisionId: string | null;
  revisionCount: number;
  revisions: ArtifactRevisionVM[];
  updatedAt: string;
};

export type ArtifactRevisionVM = {
  id: string;
  artifactId: string;
  versionNumber: number;
  label: string;
  isCanonical: boolean;
  createdAt: string;
};

export type EvaluationRunVM = {
  id: string;
  companyId: string;
  profileId: string;
  status: string;
  score: number | null;
  grade: string;
  blockingFindingCount: number;
  result: Record<string, unknown>;
  findings: Array<{
    id: string;
    severity: string;
    issueType: string;
    message: string;
    suggestedFix: string;
    blocking: boolean;
  }>;
  scorecard: {
    dimensions: Record<string, unknown>;
    compositeScore: number;
    grade: string;
    metrics: ScorecardMetricVM[];
  } | null;
  recommendedOperationIds: string[];
};

export type ScorecardMetricVM = {
  metricId: string;
  label: string;
  level: string;
  levelLabel: string;
  score: number;
  value: number | null;
  unit: string;
  recommendedOperationIds: string[];
  trend: {
    movement: string;
    previousLevel: string;
    numericDelta: number | null;
  };
};

export type PolicyEvaluationVM = {
  id: string;
  companyId: string;
  actionType: string;
  riskLevel: string;
  status: string;
  approvalTaskId: string | null;
  decisionRecordId: string | null;
};

export type ReworkPlanVM = {
  id: string;
  companyId: string;
  programId: string | null;
  status: string;
  triggerSummary: string;
  estimatedEffort: Record<string, unknown>;
  impact: Record<string, unknown>;
  itemCount: number;
};

export type ValidationDecisionVM = {
  id: string;
  decision: string;
  category: string;
  assertionId: string | null;
  artifactId: string | null;
};

export type ValidationPacketVM = {
  programId: string;
  assertionCount: number;
  artifactCount: number;
  findingCount: number;
  blockingFindingCount: number;
};

export type ArtifactLineageVM = {
  artifact: WorkArtifactVM;
  dependencyCount: number;
};

export type ProgramOperationVM = {
  id: string;
  companyId: string;
  status: string;
  operationType: string;
  label: string;
  stageId: string | null;
};

export type ToolExecutionReceiptVM = {
  id: string;
  operationId: string;
  toolId: string;
  label: string;
  dryRun: boolean;
  sideEffects: string;
  status: string;
  policyStatus: string | null;
};

export type StageOutputGenerationVM = {
  workflowId: string;
  programId: string;
  stageId: string;
  status: string;
  createdArtifacts: WorkArtifactVM[];
  evaluationStatuses: string[];
  signalCount: number;
  blockers: Array<Record<string, unknown>>;
  skipped: Array<Record<string, unknown>>;
  projection: StateProjectionVM;
};

export type StateProjectionVM = {
  id: string;
  companyId: string;
  programId: string | null;
  projectionType: string;
  label: string;
  markdownSummary: string;
  state: Record<string, unknown>;
  updatedAt: string;
};

export type CompanyOperatingModelVM = {
  companyId: string;
  installedPacks: OperatingModelPackVM[];
  programs: CompanyProgramVM[];
  evaluationProfiles: EvaluationProfileOptionVM[];
  policyPacks: Array<{ id: string; label: string }>;
  signalTaxonomies: Array<{ id: string; label: string }>;
  periodicReviews: PeriodicReviewVM[];
};

export const toOperatingModelPackVM = (
  pack: OperatingModelPack | OperatingModelInstallation,
): OperatingModelPackVM => ({
  id: pack.pack_id,
  name: pack.display_name,
  version: pack.version,
  companyTypeLabel: pack.company_type_label ?? "Company",
  description: "description" in pack ? pack.description : "",
  checksum: pack.checksum,
  programTemplates: "files" in pack ? programTemplatesFromFiles(pack.files) : [],
  operationTemplates: "files" in pack ? operationTemplatesFromFiles(pack.files) : [],
  modules: "files" in pack ? modulesFromFiles(pack.files) : [],
  serviceSections: "files" in pack ? serviceSectionsFromFiles(pack.files) : [],
  assertionKinds: "files" in pack ? assertionKindsFromFiles(pack.files) : defaultAssertionKinds(),
  assertionCategories: "files" in pack ? stringList(readRecord(pack.files.assertions).categories) : [],
  artifactSchemas: "files" in pack ? artifactSchemasFromFiles(pack.files) : [],
  evaluationProfiles: "files" in pack ? evaluationProfilesFromFiles(pack.files) : [],
  policyActions: "files" in pack ? policyActionsFromFiles(pack.files) : [],
  toolPackages: "files" in pack ? toolsFromFiles(pack.files, "tool_packages") : [],
  departmentTools: "files" in pack ? toolsFromFiles(pack.files, "department_tools") : [],
  dashboardPanels: "files" in pack ? dashboardPanelsFromFiles(pack.files) : [],
});

export const toCompanyProgramVM = (program: CompanyProgramDTO): CompanyProgramVM => ({
  id: program.id,
  companyId: program.company_id,
  packId: program.pack_id,
  templateId: program.template_id,
  label: program.display_label,
  title: program.title,
  objective: program.objective,
  status: program.status,
  currentStageId: program.current_stage_id,
  stages: (program.stages ?? []).map((stage) => ({
    id: stage.id,
    stageId: stage.stage_id,
    label: stage.label,
    sequence: stage.sequence,
    status: stage.status,
    state: stage.state,
    operationTemplateIds: stage.operation_template_ids ?? [],
  })),
});

export const toAssertionRecordVM = (assertion: AssertionRecordDTO): AssertionRecordVM => ({
  id: assertion.id,
  companyId: assertion.company_id,
  programId: assertion.program_id,
  kind: assertion.kind,
  label: assertion.pack_label || assertion.kind,
  category: assertion.category,
  statement: assertion.statement,
  source: assertion.source,
  confidence: assertion.confidence,
  validationStatus: assertion.validation_status,
});

export const toWorkArtifactVM = (artifact: WorkArtifactDTO): WorkArtifactVM => ({
  id: artifact.id,
  companyId: artifact.company_id,
  title: artifact.title,
  artifactType: artifact.artifact_type,
  programId: artifact.program_id ?? null,
  status: artifact.status,
  canonicalRevisionId: artifact.canonical_revision_id,
  revisionCount: artifact.revisions?.length ?? 0,
  revisions: (artifact.revisions ?? []).map((revision) =>
    toArtifactRevisionVM(revision, artifact.canonical_revision_id),
  ),
  updatedAt: artifact.updated_at,
});

const toArtifactRevisionVM = (
  revision: ArtifactRevisionDTO,
  canonicalRevisionId: string | null,
): ArtifactRevisionVM => ({
  id: revision.id,
  artifactId: revision.asset_id,
  versionNumber: revision.version_number,
  label: revision.label,
  isCanonical: revision.id === canonicalRevisionId,
  createdAt: revision.created_at,
});

export const toEvaluationRunVM = (evaluation: EvaluationRunDTO): EvaluationRunVM => ({
  id: evaluation.id,
  companyId: evaluation.company_id,
  profileId: evaluation.profile_id,
  status: evaluation.status,
  score: evaluation.score,
  grade: evaluation.grade,
  blockingFindingCount: evaluation.findings.filter((finding) => finding.blocking).length,
  result: evaluation.result ?? {},
  findings: evaluation.findings.map((finding) => ({
    id: finding.id,
    severity: finding.severity,
    issueType: finding.issue_type,
    message: finding.message,
    suggestedFix: finding.suggested_fix,
    blocking: finding.blocking,
  })),
  scorecard: evaluation.scorecard
    ? {
        dimensions: evaluation.scorecard.dimensions,
        compositeScore: evaluation.scorecard.composite_score,
        grade: evaluation.scorecard.grade,
        metrics: scorecardMetricsFromDimensions(evaluation.scorecard.dimensions),
      }
    : null,
  recommendedOperationIds: stringList(readRecord(evaluation.result).recommended_operation_template_ids),
});

export const toPeriodicReviewVM = (review: PeriodicReviewDTO): PeriodicReviewVM => ({
  id: review.id,
  companyId: review.company_id,
  programId: review.program_id,
  label: review.display_name,
  cadence: review.cadence,
  evaluationProfileId: review.evaluation_profile_id,
  reportTemplateId: review.report_template_id,
  historyProjectionType: review.history_projection_type,
  enabled: review.enabled,
});

export const toMetricSnapshotVM = (snapshot: MetricSnapshotDTO): MetricSnapshotVM => ({
  id: snapshot.id,
  companyId: snapshot.company_id,
  programId: snapshot.program_id,
  reviewDefinitionId: snapshot.review_definition_id,
  periodStart: snapshot.period_start,
  periodEnd: snapshot.period_end,
  metricValues: snapshot.metric_values,
  sourceType: snapshot.source_type,
  notes: snapshot.notes,
});

export const toReportRunVM = (run: ReportRunDTO): ReportRunVM => ({
  id: run.id,
  companyId: run.company_id,
  programId: run.program_id,
  reviewDefinitionId: run.review_definition_id,
  metricSnapshotId: run.metric_snapshot_id,
  reportTemplateId: run.report_template_id,
  periodStart: run.period_start,
  periodEnd: run.period_end,
  evaluationRunIds: run.evaluation_run_ids,
  artifact: run.artifact ? toWorkArtifactVM(run.artifact) : null,
  generatedSections: run.generated_sections,
  createdAt: run.created_at,
});

export const toPolicyEvaluationVM = (evaluation: PolicyEvaluationDTO): PolicyEvaluationVM => ({
  id: evaluation.id,
  companyId: evaluation.company_id,
  actionType: evaluation.action_type,
  riskLevel: evaluation.risk_level,
  status: evaluation.status,
  approvalTaskId: evaluation.approval_task_id,
  decisionRecordId: evaluation.decision_record_id,
});

export const toReworkPlanVM = (plan: ReworkPlanDTO): ReworkPlanVM => ({
  id: plan.id,
  companyId: plan.company_id,
  programId: plan.program_id,
  status: plan.status,
  triggerSummary: plan.trigger_summary,
  estimatedEffort: plan.estimated_effort,
  impact: plan.impact,
  itemCount: plan.items.length,
});

export const toValidationDecisionVM = (decision: ValidationDecisionDTO): ValidationDecisionVM => ({
  id: decision.id,
  decision: decision.decision,
  category: decision.category,
  assertionId: decision.assertion_id,
  artifactId: decision.asset_id,
});

export const toValidationPacketVM = (packet: ValidationPacketDTO): ValidationPacketVM => ({
  programId: packet.program_id,
  assertionCount: packet.assertions.length,
  artifactCount: packet.artifacts.length,
  findingCount: packet.findings.length,
  blockingFindingCount: packet.findings.filter((finding) => finding.blocking).length,
});

export const toArtifactLineageVM = (lineage: ArtifactLineageDTO): ArtifactLineageVM => ({
  artifact: toWorkArtifactVM(lineage.artifact),
  dependencyCount: lineage.dependencies.length,
});

export const toProgramOperationVM = (operation: ProgramOperationDTO): ProgramOperationVM => ({
  id: operation.id,
  companyId: operation.company_id,
  status: operation.status,
  operationType: operation.operation_type,
  label: operation.operation_label || operation.operation_type,
  stageId: operation.stage_id,
});

export const toToolExecutionReceiptVM = (receipt: ToolExecutionReceiptDTO): ToolExecutionReceiptVM => ({
  id: receipt.tool_execution_id,
  operationId: receipt.operation_id,
  toolId: receipt.tool_id,
  label: receipt.label,
  dryRun: receipt.dry_run,
  sideEffects: receipt.side_effects,
  status: receipt.status,
  policyStatus: receipt.policy_evaluation?.status ?? null,
});

export const toStageOutputGenerationVM = (result: StageOutputGenerationDTO): StageOutputGenerationVM => ({
  workflowId: result.workflow_id,
  programId: result.program_id,
  stageId: result.stage_id,
  status: result.status,
  createdArtifacts: result.created_artifacts.map(toWorkArtifactVM),
  evaluationStatuses: result.evaluations.map((evaluation) => evaluation.status),
  signalCount: result.created_signals.length,
  blockers: result.blockers,
  skipped: result.skipped,
  projection: toStateProjectionVM(result.state_projection),
});

export const toStateProjectionVM = (projection: StateProjectionDTO): StateProjectionVM => ({
  id: projection.id,
  companyId: projection.company_id,
  programId: projection.program_id,
  projectionType: projection.projection_type,
  label: projection.display_label,
  markdownSummary: projection.markdown_summary,
  state: projection.json_state,
  updatedAt: projection.updated_at,
});

export const toCompanyOperatingModelVM = (model: CompanyOperatingModelDTO): CompanyOperatingModelVM => ({
  companyId: model.company_id,
  installedPacks: (model.installed_packs ?? []).map(toOperatingModelPackVM),
  programs: (model.programs ?? []).map(toCompanyProgramVM),
  evaluationProfiles: (model.evaluation_profiles ?? []).map((profile) => ({
    id: profile.profile_id,
    label: profile.display_name,
    mode: profile.mode,
  })),
  policyPacks: (model.policy_packs ?? []).map((pack) => ({
    id: pack.policy_pack_id,
    label: pack.display_name,
  })),
  signalTaxonomies: (model.signal_taxonomies ?? []).map((taxonomy) => ({
    id: taxonomy.taxonomy_id,
    label: taxonomy.display_name,
  })),
  periodicReviews: (model.periodic_reviews ?? []).map((review) => ({
    id: review.id,
    companyId: model.company_id,
    programId: null,
    label: review.display_name,
    cadence: review.cadence,
    evaluationProfileId: review.evaluation_profile_id,
    reportTemplateId: review.report_template_id,
    historyProjectionType: review.history_projection_type,
    enabled: review.enabled,
  })),
});

function readRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function readRecordList(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> =>
        Boolean(item && typeof item === "object" && !Array.isArray(item)),
      )
    : [];
}

function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.flatMap((item) => {
        const text = String(item);
        return text ? [text] : [];
      })
    : [];
}

function labelFromId(value: string): string {
  return value
    .replace(/^[^.]+\./, "")
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function defaultAssertionKinds(): AssertionKindVM[] {
  return [
    { kind: "FACT", label: "Fact" },
    { kind: "OPINION", label: "Opinion" },
    { kind: "ASSUMPTION", label: "Assumption" },
    { kind: "QUESTION", label: "Question" },
  ];
}

function programTemplatesFromFiles(files: Record<string, unknown>): ProgramTemplateVM[] {
  return readRecordList(readRecord(files.programs).program_templates).map((template) => {
    const id = String(template.id ?? "");
    return {
      id,
      label: String(template.display_label ?? labelFromId(id || "program")),
      titleTemplate: String(template.title_template ?? ""),
      objectiveTemplate: String(template.objective_template ?? ""),
      defaultStageId: String(template.default_current_stage_id ?? ""),
    };
  });
}

function operationTemplatesFromFiles(files: Record<string, unknown>): OperationTemplateVM[] {
  return readRecordList(readRecord(files.operations).operation_templates).map((template) => {
    const id = String(template.id ?? "");
    return {
      id,
      departmentId: String(template.department_id ?? ""),
      label: String(template.label ?? labelFromId(id || "operation")),
      description: String(template.description ?? ""),
      outputs: stringList(template.outputs),
      toolIds: stringList(template.tool_ids),
      stageIds: stringList(template.stage_ids),
      moduleIds: stringList(template.module_ids),
    };
  });
}

function modulesFromFiles(files: Record<string, unknown>): CapabilityModuleVM[] {
  return readRecordList(readRecord(files.modules).modules).map((module) => {
    const id = String(module.id ?? "");
    return {
      id,
      label: String(module.label ?? labelFromId(id || "module")),
      description: String(module.description ?? ""),
      departmentId: String(module.department_id ?? ""),
      capabilities: stringList(module.capabilities),
      operationTemplateIds: stringList(module.operation_template_ids),
      artifactSchemaIds: stringList(module.artifact_schema_ids),
      requiredToolIds: stringList(module.required_tool_ids),
      optionalToolIds: stringList(module.optional_tool_ids),
      evaluationProfileIds: stringList(module.evaluation_profile_ids),
      policyRequirements: stringList(module.policy_requirements),
      stageIds: stringList(module.stage_ids),
    };
  });
}

function serviceSectionsFromFiles(files: Record<string, unknown>): ServiceSectionVM[] {
  return readRecordList(readRecord(files.service_model).service_sections).map((section) => {
    const id = String(section.id ?? "");
    const submodules = readRecordList(section.submodules);
    const submoduleItems = submodules.flatMap((submodule) => stringList(submodule.items));
    return {
      id,
      label: String(section.label ?? labelFromId(id || "service section")),
      description: String(section.description ?? ""),
      stageIds: stringList(section.stage_ids),
      operationTemplateIds: stringList(section.operation_template_ids),
      artifactSchemaIds: stringList(section.artifact_schema_ids),
      evaluationProfileIds: stringList(section.evaluation_profile_ids),
      items: [...stringList(section.operations), ...stringList(section.calendar_fields), ...submoduleItems],
    };
  });
}

function assertionKindsFromFiles(files: Record<string, unknown>): AssertionKindVM[] {
  const labels = readRecord(readRecord(files.assertions).assertion_labels);
  return defaultAssertionKinds().map((option) => ({
    ...option,
    label: String(labels[option.kind] ?? option.label),
  }));
}

function artifactSchemasFromFiles(files: Record<string, unknown>): ArtifactSchemaVM[] {
  return readRecordList(readRecord(files.artifacts).artifact_schemas).map((schema) => {
    const id = String(schema.id ?? "");
    return {
      id,
      label: String(schema.label ?? labelFromId(id || "artifact")),
      description: String(schema.description ?? ""),
      producedByOperations: stringList(schema.produced_by_operations),
      requiredInputs: stringList(schema.required_inputs),
      optionalInputs: stringList(schema.optional_inputs),
      evaluationProfiles: stringList(schema.evaluation_profiles),
      stateProjectionBehavior: String(schema.state_projection_behavior ?? ""),
    };
  });
}

function toolsFromFiles(files: Record<string, unknown>, key: string): DepartmentToolVM[] {
  return readRecordList(readRecord(files.tools)[key]).map((tool) => {
    const id = String(tool.id ?? "");
    return {
      id,
      label: String(tool.label ?? tool.name ?? labelFromId(id || "tool")),
      departmentId: String(tool.department_id ?? ""),
      category: String(tool.category ?? ""),
      sideEffects: String(tool.side_effects ?? "none"),
      approvalRequired: Boolean(tool.approval_required),
      dryRun: tool.dry_run !== false,
      policyActionType: String(tool.policy_action_type ?? ""),
    };
  });
}

function evaluationProfilesFromFiles(files: Record<string, unknown>): EvaluationProfileOptionVM[] {
  return readRecordList(readRecord(files.evaluations).profiles).map((profile) => {
    const id = String(profile.id ?? "");
    return {
      id,
      label: String(profile.label ?? labelFromId(id || "evaluation")),
      mode: String(profile.mode ?? ""),
    };
  });
}

function policyActionsFromFiles(files: Record<string, unknown>): PolicyActionOptionVM[] {
  const packs = readRecordList(readRecord(files.policies).policy_packs);
  return packs.flatMap((pack) =>
    readRecordList(pack.rules).map((rule) => {
      const actionType = String(rule.action_type ?? "");
      return {
        actionType,
        label: labelFromId(actionType || "action"),
        riskFloor: String(rule.risk_floor ?? "LOW"),
      };
    }),
  );
}

function dashboardPanelsFromFiles(files: Record<string, unknown>): DashboardPanelVM[] {
  return readRecordList(readRecord(files.dashboards).panels).map((panel) => {
    const id = String(panel.id ?? "");
    return {
      id,
      label: String(panel.label ?? labelFromId(id || "panel")),
    };
  });
}

function scorecardMetricsFromDimensions(dimensions: Record<string, unknown>): ScorecardMetricVM[] {
  return readRecordList(dimensions.metrics).map((metric) => {
    const trend = readRecord(metric.trend);
    return {
      metricId: String(metric.metric_id ?? ""),
      label: String(metric.label ?? labelFromId(String(metric.metric_id ?? "metric"))),
      level: String(metric.level ?? ""),
      levelLabel: String(metric.level_label ?? labelFromId(String(metric.level ?? ""))),
      score: Number(metric.score ?? 0),
      value: metric.value == null ? null : Number(metric.value),
      unit: String(metric.unit ?? ""),
      recommendedOperationIds: stringList(metric.recommended_operation_template_ids),
      trend: {
        movement: String(trend.movement ?? "new"),
        previousLevel: String(trend.previous_level ?? ""),
        numericDelta: trend.numeric_delta == null ? null : Number(trend.numeric_delta),
      },
    };
  });
}
