"""Generic operating model pack API views."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from django.db.models import Q
from rest_framework import status as http_status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from adapters.api.operating_models.serializers import (
    ArtifactRevisionCreateSerializer,
    AssertionCreateSerializer,
    AssertionQuerySerializer,
    CanonicalRevisionSerializer,
    CompanyPackArchiveSerializer,
    CompanyPackInstallSerializer,
    CompanyPackPatchSerializer,
    CompanyPackUpgradeSerializer,
    EvaluationRunSerializer,
    MetricSnapshotCreateSerializer,
    MetricSnapshotQuerySerializer,
    PackCompileSerializer,
    PackInstallSerializer,
    PackToolExecutionSerializer,
    PeriodicReviewCreateSerializer,
    PeriodicReviewQuerySerializer,
    PeriodicReviewRunSerializer,
    PolicyEvaluationSerializer,
    ProgramCreateSerializer,
    ProgramPatchSerializer,
    ReportRunQuerySerializer,
    ReworkPlanCreateSerializer,
    StageAdvanceSerializer,
    StageOperationLaunchSerializer,
    StageOutputGenerationSerializer,
    StateProjectionQuerySerializer,
    ValidationDecisionCreateSerializer,
    WorkArtifactCreateSerializer,
    WorkArtifactQuerySerializer,
)
from adapters.api.responses import error_response, success_response
from application.services.assertions import assertion_payload, create_assertion
from application.services.company_access import accessible_company_queryset, has_company_access
from application.services.company_operating_models import company_operating_model_payload
from application.services.company_programs import (
    CompanyProgramError,
    advance_program_stage,
    create_program,
    launch_program_stage_operation,
    program_payload,
    update_program,
)
from application.services.evaluations import (
    SubmittedScorecardValidationError,
    evaluation_payload,
    run_evaluation,
)
from application.services.operating_model_packs import (
    OperatingModelPackError,
    archive_pack_installation,
    compile_pack,
    config_revision_payload,
    install_pack_for_company,
    installation_detail_payload,
    installation_payload,
    list_available_packs,
    load_pack_definition,
    namespace_claim_payload,
    remove_pack_from_company,
    update_pack_installation,
    upgrade_pack_for_company,
    upgrade_pack_installation,
)
from application.services.pack_tool_executions import (
    PackToolExecutionError,
    execute_pack_tool,
)
from application.services.periodic_reviews import (
    PeriodicReviewError,
    create_metric_snapshot,
    execute_periodic_review,
    metric_snapshot_payload,
    periodic_review_payload,
    report_run_payload,
    upsert_review_definition_from_template,
)
from application.services.policy_evaluations import evaluate_policy, policy_evaluation_payload
from application.services.processed_commands import (
    IdempotencyConflict,
    build_idempotency_context,
    idempotency_key_from_request,
    record_processed_command,
    replay_processed_command,
)
from application.services.program_stage_outputs import (
    ProgramStageOutputError,
    execute_stage_output_generation,
)
from application.services.rbac import has_min_role
from application.services.rework_plans import (
    create_rework_plan,
    execute_rework_plan,
    rework_plan_payload,
)
from application.services.state_projections import (
    materialize_current_truth_projection,
    projection_payload,
)
from application.services.validation_decisions import (
    ValidationDecisionError,
    create_validation_decision,
    validation_decision_payload,
    validation_packet_payload,
)
from application.services.work_artifacts import (
    artifact_payload,
    create_artifact_revision,
    create_work_artifact,
    lineage_payload,
    set_canonical_revision,
)
from infrastructure.orm.models import (
    AssertionRecord,
    Asset,
    AssetVersion,
    CompanyOperatingModelInstallation,
    CompanyProgram,
    EvaluationRun,
    Graph,
    MetricSnapshot,
    PeriodicReviewDefinition,
    ReportRun,
    ReworkPlan,
    Run,
    StateProjection,
    User,
    ValidationDecision,
)


class OperatingModelPackListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        if not has_min_role(user, "viewer"):
            return _forbidden("You do not have permission to view operating model packs.")
        return success_response({"packs": list_available_packs()})


class OperatingModelPackDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pack_id: str) -> Response:
        user = cast(User, request.user)
        if not has_min_role(user, "viewer"):
            return _forbidden("You do not have permission to view operating model packs.")
        try:
            pack = load_pack_definition(pack_id)
        except OperatingModelPackError as exc:
            return _pack_error(exc)
        return success_response({"pack": pack.as_payload()})


class OperatingModelPackCompileView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, pack_id: str) -> Response:
        user = cast(User, request.user)
        if not has_min_role(user, "viewer"):
            return _forbidden("You do not have permission to compile operating model packs.")
        serializer = PackCompileSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        try:
            result = compile_pack(pack_id=pack_id, **serializer.validated_data)
        except OperatingModelPackError as exc:
            return _pack_error(exc)
        return success_response(result.as_payload())


class CompanyOperatingModelView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, company_id: UUID) -> Response:
        company = _company_for_user(request, company_id, minimum_role="viewer")
        if isinstance(company, Response):
            return company
        return success_response({"operating_model": company_operating_model_payload(company)})


class CompanyPackListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, company_id: UUID) -> Response:
        company = _company_for_user(request, company_id, minimum_role="viewer")
        if isinstance(company, Response):
            return company
        installations = (
            CompanyOperatingModelInstallation.objects.filter(company=company)
            .select_related("pack_release")
            .order_by("role", "pack_id")
        )
        return success_response(
            {"packs": [installation_payload(installation) for installation in installations]}
        )


class CompanyPackGenericInstallView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, company_id: UUID) -> Response:
        serializer = CompanyPackInstallSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        company = _company_for_user(request, company_id, minimum_role="admin")
        if isinstance(company, Response):
            return company
        pack_id = str(serializer.validated_data["pack_id"])
        command = _prepare_command(
            request=request,
            company=company,
            action=f"company_pack.install:{pack_id}",
        )
        if isinstance(command, Response):
            return command
        context, replay = command
        if replay is not None:
            return replay
        try:
            installation = install_pack_for_company(
                company=company,
                user=cast(User, request.user),
                pack_id=pack_id,
                role=str(serializer.validated_data.get("role") or ""),
                config=serializer.validated_data.get("config") or {},
            )
        except OperatingModelPackError as exc:
            return _pack_error(exc)
        response = success_response(
            {"installation": installation_payload(installation)},
            status=http_status.HTTP_201_CREATED,
        )
        return record_processed_command(
            context=context,
            response=response,
            resource_type="pack_installation",
            resource_id=str(installation.id),
        )


class CompanyPackDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, company_id: UUID, installation_id: UUID) -> Response:
        installation = _installation_for_user(
            request,
            company_id,
            installation_id,
            minimum_role="viewer",
        )
        if isinstance(installation, Response):
            return installation
        return success_response({"installation": installation_detail_payload(installation)})

    def patch(self, request: Request, company_id: UUID, installation_id: UUID) -> Response:
        serializer = CompanyPackPatchSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        installation = _installation_for_user(
            request,
            company_id,
            installation_id,
            minimum_role="admin",
        )
        if isinstance(installation, Response):
            return installation
        command = _prepare_command(
            request=request,
            company=installation.company,
            action=f"company_pack.update:{installation_id}",
        )
        if isinstance(command, Response):
            return command
        context, replay = command
        if replay is not None:
            return replay
        try:
            installation = update_pack_installation(
                installation=installation,
                user=cast(User, request.user),
                role=serializer.validated_data.get("role"),
                status=serializer.validated_data.get("status"),
                config=serializer.validated_data.get("config")
                if "config" in serializer.validated_data
                else None,
            )
        except OperatingModelPackError as exc:
            return _pack_error(exc)
        response = success_response({"installation": installation_payload(installation)})
        return record_processed_command(
            context=context,
            response=response,
            resource_type="pack_installation",
            resource_id=str(installation.id),
        )


class CompanyPackGenericUpgradeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, company_id: UUID, installation_id: UUID) -> Response:
        serializer = CompanyPackUpgradeSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        installation = _installation_for_user(
            request,
            company_id,
            installation_id,
            minimum_role="admin",
        )
        if isinstance(installation, Response):
            return installation
        command = _prepare_command(
            request=request,
            company=installation.company,
            action=f"company_pack.upgrade:{installation_id}",
        )
        if isinstance(command, Response):
            return command
        context, replay = command
        if replay is not None:
            return replay
        config = dict(installation.public_config_json or {})
        overrides = serializer.validated_data.get("config_overrides")
        if isinstance(overrides, dict):
            config.update(overrides)
        try:
            installation = upgrade_pack_installation(
                installation=installation,
                user=cast(User, request.user),
                config=config,
            )
        except OperatingModelPackError as exc:
            return _pack_error(exc)
        response = success_response({"installation": installation_payload(installation)})
        return record_processed_command(
            context=context,
            response=response,
            resource_type="pack_installation",
            resource_id=str(installation.id),
        )


class CompanyPackGenericArchiveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, company_id: UUID, installation_id: UUID) -> Response:
        serializer = CompanyPackArchiveSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        installation = _installation_for_user(
            request,
            company_id,
            installation_id,
            minimum_role="admin",
        )
        if isinstance(installation, Response):
            return installation
        command = _prepare_command(
            request=request,
            company=installation.company,
            action=f"company_pack.archive:{installation_id}",
        )
        if isinstance(command, Response):
            return command
        context, replay = command
        if replay is not None:
            return replay
        installation = archive_pack_installation(
            installation=installation,
            user=cast(User, request.user),
            reason=str(serializer.validated_data.get("reason") or ""),
        )
        response = success_response({"installation": installation_payload(installation)})
        return record_processed_command(
            context=context,
            response=response,
            resource_type="pack_installation",
            resource_id=str(installation.id),
        )


class CompanyPackObjectsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, company_id: UUID, installation_id: UUID) -> Response:
        installation = _installation_for_user(
            request,
            company_id,
            installation_id,
            minimum_role="viewer",
        )
        if isinstance(installation, Response):
            return installation
        claims = installation.namespace_claims.order_by("object_type", "namespaced_id")
        revisions = installation.config_revisions.order_by("-version")[:20]
        return success_response(
            {
                "objects": [namespace_claim_payload(claim) for claim in claims],
                "config_revisions": [config_revision_payload(revision) for revision in revisions],
            }
        )


class CompanyPackInstallView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, company_id: UUID, pack_id: str) -> Response:
        serializer = PackInstallSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        company = _company_for_user(request, company_id, minimum_role="admin")
        if isinstance(company, Response):
            return company
        command = _prepare_command(
            request=request,
            company=company,
            action=f"operating_model_pack.install:{pack_id}",
        )
        if isinstance(command, Response):
            return command
        context, replay = command
        if replay is not None:
            return replay
        try:
            installation = install_pack_for_company(
                company=company,
                user=cast(User, request.user),
                pack_id=pack_id,
                config=serializer.validated_data.get("config") or {},
            )
        except OperatingModelPackError as exc:
            return _pack_error(exc)
        response = success_response(
            {"installation": installation_payload(installation)},
            status=http_status.HTTP_201_CREATED,
        )
        return record_processed_command(
            context=context,
            response=response,
            resource_type="operating_model_pack_installation",
            resource_id=str(installation.id),
        )


class CompanyPackUpgradeView(CompanyPackInstallView):
    def post(self, request: Request, company_id: UUID, pack_id: str) -> Response:
        serializer = PackInstallSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        company = _company_for_user(request, company_id, minimum_role="admin")
        if isinstance(company, Response):
            return company
        command = _prepare_command(
            request=request,
            company=company,
            action=f"operating_model_pack.upgrade:{pack_id}",
        )
        if isinstance(command, Response):
            return command
        context, replay = command
        if replay is not None:
            return replay
        try:
            installation = upgrade_pack_for_company(
                company=company,
                user=cast(User, request.user),
                pack_id=pack_id,
                config=serializer.validated_data.get("config") or {},
            )
        except OperatingModelPackError as exc:
            return _pack_error(exc)
        response = success_response({"installation": installation_payload(installation)})
        return record_processed_command(
            context=context,
            response=response,
            resource_type="operating_model_pack_installation",
            resource_id=str(installation.id),
        )


class CompanyPackRemoveView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request: Request, company_id: UUID, pack_id: str) -> Response:
        company = _company_for_user(request, company_id, minimum_role="admin")
        if isinstance(company, Response):
            return company
        command = _prepare_command(
            request=request,
            company=company,
            action=f"operating_model_pack.remove:{pack_id}",
        )
        if isinstance(command, Response):
            return command
        context, replay = command
        if replay is not None:
            return replay
        try:
            installation = remove_pack_from_company(
                company=company,
                user=cast(User, request.user),
                pack_id=pack_id,
            )
        except OperatingModelPackError as exc:
            return _pack_error(exc)
        response = success_response({"installation": installation_payload(installation)})
        return record_processed_command(
            context=context,
            response=response,
            resource_type="operating_model_pack_installation",
            resource_id=str(installation.id),
        )


class CompanyProgramListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, company_id: UUID) -> Response:
        company = _company_for_user(request, company_id, minimum_role="viewer")
        if isinstance(company, Response):
            return company
        programs = CompanyProgram.objects.filter(company=company).order_by("-updated_at")
        return success_response(
            {"programs": [program_payload(item, include_stages=False) for item in programs]}
        )

    def post(self, request: Request, company_id: UUID) -> Response:
        serializer = ProgramCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        company = _company_for_user(request, company_id, minimum_role="member")
        if isinstance(company, Response):
            return company
        command = _prepare_command(
            request=request, company=company, action="company_program.create"
        )
        if isinstance(command, Response):
            return command
        context, replay = command
        if replay is not None:
            return replay
        program = create_program(
            company=company, user=cast(User, request.user), **serializer.validated_data
        )
        materialize_current_truth_projection(company=company, program=program)
        response = success_response(
            {"program": program_payload(program)},
            status=http_status.HTTP_201_CREATED,
        )
        return record_processed_command(
            context=context,
            response=response,
            resource_type="company_program",
            resource_id=str(program.id),
        )


class ProgramDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, program_id: UUID) -> Response:
        program = _program_for_user(request, program_id, minimum_role="viewer")
        if isinstance(program, Response):
            return program
        return success_response({"program": program_payload(program)})

    def patch(self, request: Request, program_id: UUID) -> Response:
        serializer = ProgramPatchSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        program = _program_for_user(request, program_id, minimum_role="member")
        if isinstance(program, Response):
            return program
        command = _prepare_command(
            request=request,
            company=program.company,
            action=f"company_program.update:{program_id}",
        )
        if isinstance(command, Response):
            return command
        context, replay = command
        if replay is not None:
            return replay
        program = update_program(
            program=program, user=cast(User, request.user), **serializer.validated_data
        )
        response = success_response({"program": program_payload(program)})
        return record_processed_command(
            context=context,
            response=response,
            resource_type="company_program",
            resource_id=str(program.id),
        )


class ProgramStageAdvanceView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, program_id: UUID, stage_id: str) -> Response:
        serializer = StageAdvanceSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        program = _program_for_user(request, program_id, minimum_role="member")
        if isinstance(program, Response):
            return program
        command = _prepare_command(
            request=request,
            company=program.company,
            action=f"company_program.stage_advance:{program_id}:{stage_id}",
        )
        if isinstance(command, Response):
            return command
        context, replay = command
        if replay is not None:
            return replay
        try:
            advance_program_stage(
                program=program,
                user=cast(User, request.user),
                stage_id=stage_id,
                status=str(serializer.validated_data["status"]),
            )
        except CompanyProgramError as exc:
            return _program_error(exc)
        materialize_current_truth_projection(company=program.company, program=program)
        response = success_response({"program": program_payload(program)})
        return record_processed_command(
            context=context,
            response=response,
            resource_type="company_program",
            resource_id=str(program.id),
        )


class ProgramStageOperationLaunchView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, program_id: UUID, stage_id: str) -> Response:
        serializer = StageOperationLaunchSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        program = _program_for_user(request, program_id, minimum_role="member")
        if isinstance(program, Response):
            return program
        command = _prepare_command(
            request=request,
            company=program.company,
            action=f"company_program.operation_launch:{program_id}:{stage_id}",
        )
        if isinstance(command, Response):
            return command
        context, replay = command
        if replay is not None:
            return replay
        try:
            operation = launch_program_stage_operation(
                program=program,
                user=cast(User, request.user),
                stage_id=stage_id,
                operation_template_id=str(serializer.validated_data["operation_template_id"]),
                context_note=str(serializer.validated_data.get("context_note") or ""),
                run_goal=str(serializer.validated_data.get("run_goal") or ""),
            )
        except CompanyProgramError as exc:
            return _program_error(exc)
        materialize_current_truth_projection(company=program.company, program=program)
        response = success_response(
            {"operation": _program_operation_payload(operation)},
            status=http_status.HTTP_201_CREATED,
        )
        return record_processed_command(
            context=context,
            response=response,
            resource_type="run",
            resource_id=str(operation.id),
        )


class ProgramStageOutputGenerationView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, program_id: UUID, stage_id: str) -> Response:
        serializer = StageOutputGenerationSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        program = _program_for_user(request, program_id, minimum_role="member")
        if isinstance(program, Response):
            return program
        command = _prepare_command(
            request=request,
            company=program.company,
            action=f"program_stage.outputs:{stage_id}",
        )
        if isinstance(command, Response):
            return command
        context, replay = command
        if replay is not None:
            return replay
        try:
            result = execute_stage_output_generation(
                program=program,
                user=cast(User, request.user),
                stage_id=stage_id,
                workflow_id=str(serializer.validated_data.get("workflow_id") or ""),
                artifact_schema_ids=[
                    str(item) for item in serializer.validated_data.get("artifact_schema_ids", [])
                ],
                selected_family_ids=[
                    str(item) for item in serializer.validated_data.get("selected_family_ids", [])
                ],
                source_artifact_ids=[
                    str(item) for item in serializer.validated_data.get("source_artifact_ids", [])
                ],
                notes=str(serializer.validated_data.get("notes") or ""),
                evaluation_inputs=serializer.validated_data.get("evaluation_inputs") or {},
            )
        except ProgramStageOutputError as exc:
            return _stage_output_error(exc)
        response = success_response(
            {"stage_output": result},
            status=http_status.HTTP_201_CREATED,
        )
        return record_processed_command(
            context=context,
            response=response,
            resource_type="program_stage",
            resource_id=result["stage_id"],
        )


class ProgramValidationPacketView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, program_id: UUID) -> Response:
        program = _program_for_user(request, program_id, minimum_role="viewer")
        if isinstance(program, Response):
            return program
        return success_response(
            {
                "validation_packet": validation_packet_payload(
                    company=program.company, program=program
                )
            }
        )


class AssertionsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        serializer = AssertionQuerySerializer(data=request.query_params)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        company = _company_for_user(
            request, serializer.validated_data["company_id"], minimum_role="viewer"
        )
        if isinstance(company, Response):
            return company
        queryset = AssertionRecord.objects.filter(company=company)
        if serializer.validated_data.get("program_id"):
            queryset = queryset.filter(program_id=serializer.validated_data["program_id"])
        if serializer.validated_data.get("kind"):
            queryset = queryset.filter(kind=str(serializer.validated_data["kind"]).upper())
        if serializer.validated_data.get("validation_status"):
            queryset = queryset.filter(
                validation_status=serializer.validated_data["validation_status"]
            )
        return success_response(
            {"assertions": [assertion_payload(item) for item in queryset[:200]]}
        )

    def post(self, request: Request) -> Response:
        serializer = AssertionCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        company = _company_for_user(
            request, serializer.validated_data["company_id"], minimum_role="member"
        )
        if isinstance(company, Response):
            return company
        program = _optional_program(
            company=company, program_id=serializer.validated_data.get("program_id")
        )
        if isinstance(program, Response):
            return program
        command = _prepare_command(request=request, company=company, action="assertion.create")
        if isinstance(command, Response):
            return command
        context, replay = command
        if replay is not None:
            return replay
        assertion = create_assertion(
            company=company,
            user=cast(User, request.user),
            program=program,
            **{
                key: value
                for key, value in serializer.validated_data.items()
                if key not in {"company_id", "program_id"}
            },
        )
        if program is not None:
            materialize_current_truth_projection(company=company, program=program)
        response = success_response(
            {"assertion": assertion_payload(assertion)},
            status=http_status.HTTP_201_CREATED,
        )
        return record_processed_command(
            context=context,
            response=response,
            resource_type="assertion",
            resource_id=str(assertion.id),
        )


class ValidationDecisionsView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = ValidationDecisionCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        company = _company_for_user(
            request, serializer.validated_data["company_id"], minimum_role="member"
        )
        if isinstance(company, Response):
            return company
        program = _optional_program(
            company=company, program_id=serializer.validated_data.get("program_id")
        )
        if isinstance(program, Response):
            return program
        command = _prepare_command(
            request=request, company=company, action="validation_decision.create"
        )
        if isinstance(command, Response):
            return command
        context, replay = command
        if replay is not None:
            return replay
        try:
            decision = create_validation_decision(
                company=company,
                user=cast(User, request.user),
                program=program,
                assertion_id=serializer.validated_data.get("assertion_id"),
                asset_id=serializer.validated_data.get("asset_id"),
                asset_version_id=serializer.validated_data.get("asset_version_id"),
                decision=str(serializer.validated_data["decision"]),
                category=str(serializer.validated_data.get("category") or ""),
                rationale=str(serializer.validated_data.get("rationale") or ""),
                proposed_change=serializer.validated_data.get("proposed_change") or {},
            )
        except ValidationDecisionError as exc:
            return error_response(
                exc.code.upper(), exc.message, status=http_status.HTTP_400_BAD_REQUEST
            )
        response = success_response(
            {"validation_decision": validation_decision_payload(decision)},
            status=http_status.HTTP_201_CREATED,
        )
        return record_processed_command(
            context=context,
            response=response,
            resource_type="validation_decision",
            resource_id=str(decision.id),
        )


class WorkArtifactsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        serializer = WorkArtifactQuerySerializer(data=request.query_params)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        company_id = serializer.validated_data.get("company_id")
        if not company_id:
            return _validation_error({"company_id": ["This field is required."]})
        company = _company_for_user(request, company_id, minimum_role="viewer")
        if isinstance(company, Response):
            return company
        queryset = Asset.objects.filter(company=company).order_by("-updated_at")
        if serializer.validated_data.get("artifact_type"):
            queryset = queryset.filter(
                metadata_json__artifact_type=serializer.validated_data["artifact_type"]
            )
        if serializer.validated_data.get("status"):
            queryset = queryset.filter(status=serializer.validated_data["status"])
        return success_response({"artifacts": [artifact_payload(item) for item in queryset[:200]]})

    def post(self, request: Request) -> Response:
        serializer = WorkArtifactCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        company = _company_for_user(
            request, serializer.validated_data["company_id"], minimum_role="member"
        )
        if isinstance(company, Response):
            return company
        program = _optional_program(
            company=company, program_id=serializer.validated_data.get("program_id")
        )
        if isinstance(program, Response):
            return program
        command = _prepare_command(request=request, company=company, action="work_artifact.create")
        if isinstance(command, Response):
            return command
        context, replay = command
        if replay is not None:
            return replay
        asset, version = create_work_artifact(
            company=company,
            user=cast(User, request.user),
            program=program,
            title=str(serializer.validated_data["title"]),
            artifact_type=str(serializer.validated_data["artifact_type"]),
            content=serializer.validated_data["content"],
            metadata=serializer.validated_data.get("metadata") or {},
        )
        if program is not None:
            materialize_current_truth_projection(company=company, program=program)
        response = success_response(
            {"artifact": artifact_payload(asset), "revision": _revision_payload(version)},
            status=http_status.HTTP_201_CREATED,
        )
        return record_processed_command(
            context=context,
            response=response,
            resource_type="work_artifact",
            resource_id=str(asset.id),
        )


class WorkArtifactDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, artifact_id: UUID) -> Response:
        asset = _asset_for_user(request, artifact_id, minimum_role="viewer")
        if isinstance(asset, Response):
            return asset
        return success_response({"artifact": artifact_payload(asset, include_versions=True)})


class ArtifactRevisionCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, artifact_id: UUID) -> Response:
        serializer = ArtifactRevisionCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        asset = _asset_for_user(request, artifact_id, minimum_role="member")
        if isinstance(asset, Response):
            return asset
        command = _prepare_command(
            request=request, company=asset.company, action="artifact_revision.create"
        )
        if isinstance(command, Response):
            return command
        context, replay = command
        if replay is not None:
            return replay
        parent = None
        if serializer.validated_data.get("parent_revision_id"):
            parent = AssetVersion.objects.filter(
                asset=asset,
                id=serializer.validated_data["parent_revision_id"],
            ).first()
        version = create_artifact_revision(
            asset=asset,
            user=cast(User, request.user),
            content=serializer.validated_data["content"],
            parent_version=parent,
            label=str(serializer.validated_data.get("label") or ""),
            metadata=serializer.validated_data.get("metadata") or {},
        )
        program_id = (asset.metadata_json or {}).get("program_id")
        if program_id:
            program = CompanyProgram.objects.filter(company=asset.company, id=program_id).first()
            if program is not None:
                materialize_current_truth_projection(company=asset.company, program=program)
        response = success_response(
            {"revision": _revision_payload(version)},
            status=http_status.HTTP_201_CREATED,
        )
        return record_processed_command(
            context=context,
            response=response,
            resource_type="artifact_revision",
            resource_id=str(version.id),
        )


class ArtifactLineageView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, artifact_id: UUID) -> Response:
        asset = _asset_for_user(request, artifact_id, minimum_role="viewer")
        if isinstance(asset, Response):
            return asset
        return success_response({"lineage": lineage_payload(asset)})


class ArtifactCanonicalRevisionView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request: Request, artifact_id: UUID) -> Response:
        serializer = CanonicalRevisionSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        asset = _asset_for_user(request, artifact_id, minimum_role="member")
        if isinstance(asset, Response):
            return asset
        command = _prepare_command(
            request=request, company=asset.company, action="artifact.canonical_revision"
        )
        if isinstance(command, Response):
            return command
        context, replay = command
        if replay is not None:
            return replay
        version = AssetVersion.objects.filter(
            asset=asset, id=serializer.validated_data["revision_id"]
        ).first()
        if version is None:
            return _not_found("Artifact revision was not found.")
        set_canonical_revision(asset=asset, version=version, user=cast(User, request.user))
        program_id = (asset.metadata_json or {}).get("program_id")
        if program_id:
            program = CompanyProgram.objects.filter(company=asset.company, id=program_id).first()
            if program is not None:
                materialize_current_truth_projection(company=asset.company, program=program)
        response = success_response({"artifact": artifact_payload(asset, include_versions=True)})
        return record_processed_command(
            context=context,
            response=response,
            resource_type="work_artifact",
            resource_id=str(asset.id),
        )


class EvaluationRunView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = EvaluationRunSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        company = _company_for_user(
            request, serializer.validated_data["company_id"], minimum_role="member"
        )
        if isinstance(company, Response):
            return company
        command = _prepare_command(request=request, company=company, action="evaluation.run")
        if isinstance(command, Response):
            return command
        context, replay = command
        if replay is not None:
            return replay
        program = _optional_program(
            company=company, program_id=serializer.validated_data.get("program_id")
        )
        if isinstance(program, Response):
            return program
        asset = _optional_asset(company=company, asset_id=serializer.validated_data.get("asset_id"))
        if isinstance(asset, Response):
            return asset
        version = None
        if serializer.validated_data.get("asset_version_id") and asset is not None:
            version = AssetVersion.objects.filter(
                asset=asset,
                id=serializer.validated_data["asset_version_id"],
            ).first()
        try:
            evaluation = run_evaluation(
                company=company,
                user=cast(User, request.user),
                profile_id=str(serializer.validated_data["profile_id"]),
                content=str(serializer.validated_data.get("content") or ""),
                asset=asset,
                asset_version=version,
                program=program,
                input_refs=serializer.validated_data.get("input_refs") or [],
                inputs=serializer.validated_data.get("inputs") or {},
            )
        except SubmittedScorecardValidationError as exc:
            return _validation_error(exc.field_errors)
        response = success_response(
            {"evaluation": evaluation_payload(evaluation)},
            status=http_status.HTTP_201_CREATED,
        )
        return record_processed_command(
            context=context,
            response=response,
            resource_type="evaluation",
            resource_id=str(evaluation.id),
        )


class EvaluationDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, evaluation_id: UUID) -> Response:
        evaluation = (
            EvaluationRun.objects.select_related("company").filter(id=evaluation_id).first()
        )
        if evaluation is None:
            return _not_found("Evaluation was not found.")
        if not _can_access_company(request, evaluation.company, "viewer"):
            return _forbidden("You do not have permission to view this evaluation.")
        return success_response({"evaluation": evaluation_payload(evaluation)})


class PeriodicReviewListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        serializer = PeriodicReviewQuerySerializer(data=request.query_params)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        company = _company_for_user(
            request, serializer.validated_data["company_id"], minimum_role="viewer"
        )
        if isinstance(company, Response):
            return company
        queryset = PeriodicReviewDefinition.objects.filter(company=company)
        if serializer.validated_data.get("program_id"):
            queryset = queryset.filter(
                Q(program_id=serializer.validated_data["program_id"]) | Q(program__isnull=True)
            )
        if "enabled" in serializer.validated_data:
            queryset = queryset.filter(enabled=serializer.validated_data["enabled"])
        return success_response(
            {"periodic_reviews": [periodic_review_payload(item) for item in queryset[:100]]}
        )

    def post(self, request: Request) -> Response:
        serializer = PeriodicReviewCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        company = _company_for_user(
            request, serializer.validated_data["company_id"], minimum_role="member"
        )
        if isinstance(company, Response):
            return company
        program = _optional_program(
            company=company, program_id=serializer.validated_data.get("program_id")
        )
        if isinstance(program, Response):
            return program
        command = _prepare_command(
            request=request, company=company, action="periodic_review_definition.upsert"
        )
        if isinstance(command, Response):
            return command
        context, replay = command
        if replay is not None:
            return replay
        try:
            review = upsert_review_definition_from_template(
                company=company,
                user=cast(User, request.user),
                program=program,
                template={
                    "id": serializer.validated_data["template_id"],
                    "display_name": serializer.validated_data["display_name"],
                    "cadence": serializer.validated_data.get("cadence") or "monthly",
                    "timezone": serializer.validated_data.get("timezone") or "UTC",
                    "evaluation_profile_id": serializer.validated_data.get("evaluation_profile_id")
                    or "",
                    "report_template_id": serializer.validated_data.get("report_template_id") or "",
                    "history_projection_type": serializer.validated_data.get(
                        "history_projection_type"
                    )
                    or "",
                    "enabled": serializer.validated_data.get("enabled", True),
                    **(serializer.validated_data.get("metadata") or {}),
                },
            )
        except PeriodicReviewError as exc:
            return _periodic_review_error(exc)
        response = success_response(
            {"periodic_review": periodic_review_payload(review)},
            status=http_status.HTTP_201_CREATED,
        )
        return record_processed_command(
            context=context,
            response=response,
            resource_type="periodic_review_definition",
            resource_id=str(review.id),
        )


class MetricSnapshotListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        serializer = MetricSnapshotQuerySerializer(data=request.query_params)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        company = _company_for_user(
            request, serializer.validated_data["company_id"], minimum_role="viewer"
        )
        if isinstance(company, Response):
            return company
        queryset = MetricSnapshot.objects.filter(company=company)
        if serializer.validated_data.get("program_id"):
            queryset = queryset.filter(program_id=serializer.validated_data["program_id"])
        if serializer.validated_data.get("review_definition_id"):
            queryset = queryset.filter(
                review_definition_id=serializer.validated_data["review_definition_id"]
            )
        return success_response(
            {"metric_snapshots": [metric_snapshot_payload(item) for item in queryset[:100]]}
        )

    def post(self, request: Request) -> Response:
        serializer = MetricSnapshotCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        company = _company_for_user(
            request, serializer.validated_data["company_id"], minimum_role="member"
        )
        if isinstance(company, Response):
            return company
        program = _optional_program(
            company=company, program_id=serializer.validated_data.get("program_id")
        )
        if isinstance(program, Response):
            return program
        review = _optional_periodic_review(
            company=company,
            review_id=serializer.validated_data.get("review_definition_id"),
        )
        if isinstance(review, Response):
            return review
        command = _prepare_command(
            request=request, company=company, action="metric_snapshot.create"
        )
        if isinstance(command, Response):
            return command
        context, replay = command
        if replay is not None:
            return replay
        try:
            snapshot = create_metric_snapshot(
                company=company,
                user=cast(User, request.user),
                program=program,
                review_definition=review,
                period_start=serializer.validated_data["period_start"],
                period_end=serializer.validated_data["period_end"],
                metric_values=serializer.validated_data.get("metric_values") or {},
                metric_sources=serializer.validated_data.get("metric_sources") or {},
                source_type=str(serializer.validated_data.get("source_type") or "manual"),
                notes=str(serializer.validated_data.get("notes") or ""),
            )
        except PeriodicReviewError as exc:
            return _periodic_review_error(exc)
        response = success_response(
            {"metric_snapshot": metric_snapshot_payload(snapshot)},
            status=http_status.HTTP_201_CREATED,
        )
        return record_processed_command(
            context=context,
            response=response,
            resource_type="metric_snapshot",
            resource_id=str(snapshot.id),
        )


class PeriodicReviewRunView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, review_id: UUID) -> Response:
        serializer = PeriodicReviewRunSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        review = _periodic_review_for_user(request, review_id, minimum_role="member")
        if isinstance(review, Response):
            return review
        command = _prepare_command(
            request=request,
            company=review.company,
            action=f"periodic_review.run:{review_id}",
        )
        if isinstance(command, Response):
            return command
        context, replay = command
        if replay is not None:
            return replay
        try:
            summary = execute_periodic_review(
                review=review,
                user=cast(User, request.user),
                period_start=serializer.validated_data.get("period_start"),
                period_end=serializer.validated_data.get("period_end"),
                metric_snapshot_id=str(serializer.validated_data.get("metric_snapshot_id") or ""),
                metric_values=serializer.validated_data.get("metric_values"),
                metric_sources=serializer.validated_data.get("metric_sources") or {},
                source_type=str(serializer.validated_data.get("source_type") or "manual"),
                force=bool(serializer.validated_data.get("force", False)),
                dry_run=bool(serializer.validated_data.get("dry_run", False)),
                notes=str(serializer.validated_data.get("notes") or ""),
            )
        except PeriodicReviewError as exc:
            return _periodic_review_error(exc)
        payload: dict[str, Any] = {"periodic_review_execution": summary.as_payload()}
        if summary.evaluation_run_ids:
            evaluation = EvaluationRun.objects.filter(
                company=review.company, id=summary.evaluation_run_ids[0]
            ).first()
            if evaluation is not None:
                payload["evaluation"] = evaluation_payload(evaluation)
        if summary.report_run_id:
            report = ReportRun.objects.filter(
                company=review.company, id=summary.report_run_id
            ).first()
            if report is not None:
                payload["report_run"] = report_run_payload(report)
        response_status = (
            http_status.HTTP_201_CREATED
            if summary.status == "completed" and not summary.skipped and not summary.dry_run
            else http_status.HTTP_200_OK
        )
        response = success_response(payload, status=response_status)
        return record_processed_command(
            context=context,
            response=response,
            resource_type="periodic_review_run",
            resource_id=summary.report_run_id or str(review.id),
        )


class ReportRunListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        serializer = ReportRunQuerySerializer(data=request.query_params)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        company = _company_for_user(
            request, serializer.validated_data["company_id"], minimum_role="viewer"
        )
        if isinstance(company, Response):
            return company
        queryset = ReportRun.objects.filter(company=company)
        if serializer.validated_data.get("program_id"):
            queryset = queryset.filter(program_id=serializer.validated_data["program_id"])
        if serializer.validated_data.get("review_definition_id"):
            queryset = queryset.filter(
                review_definition_id=serializer.validated_data["review_definition_id"]
            )
        return success_response(
            {"report_runs": [report_run_payload(item) for item in queryset[:100]]}
        )


class PolicyEvaluationView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = PolicyEvaluationSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        company = _company_for_user(
            request, serializer.validated_data["company_id"], minimum_role="member"
        )
        if isinstance(company, Response):
            return company
        command = _prepare_command(
            request=request, company=company, action="policy_evaluation.create"
        )
        if isinstance(command, Response):
            return command
        context, replay = command
        if replay is not None:
            return replay
        operation = None
        if serializer.validated_data.get("operation_id"):
            operation = Run.objects.filter(
                id=serializer.validated_data["operation_id"],
                graph_version__graph=company,
            ).first()
        evaluation = evaluate_policy(
            company=company,
            user=cast(User, request.user),
            action_type=str(serializer.validated_data["action_type"]),
            inputs=serializer.validated_data.get("inputs") or {},
            policy_pack_id=str(serializer.validated_data.get("policy_pack_id") or ""),
            operation=operation,
        )
        response = success_response(
            {"policy_evaluation": policy_evaluation_payload(evaluation)},
            status=http_status.HTTP_201_CREATED,
        )
        return record_processed_command(
            context=context,
            response=response,
            resource_type="policy_evaluation",
            resource_id=str(evaluation.id),
        )


class PackToolExecutionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = PackToolExecutionSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        company = _company_for_user(
            request, serializer.validated_data["company_id"], minimum_role="member"
        )
        if isinstance(company, Response):
            return company
        operation = Run.objects.filter(
            id=serializer.validated_data["operation_id"],
            graph_version__graph=company,
        ).first()
        if operation is None:
            return _not_found("Operation was not found.")
        command = _prepare_command(request=request, company=company, action="pack_tool.execute")
        if isinstance(command, Response):
            return command
        context, replay = command
        if replay is not None:
            return replay
        try:
            receipt = execute_pack_tool(
                company=company,
                user=cast(User, request.user),
                operation=operation,
                tool_id=str(serializer.validated_data["tool_id"]),
                inputs=serializer.validated_data.get("inputs") or {},
                dry_run=bool(serializer.validated_data.get("dry_run", True)),
                policy_evaluation_id=serializer.validated_data.get("policy_evaluation_id"),
                idempotency_key=idempotency_key_from_request(request) or "",
            )
        except PackToolExecutionError as exc:
            return error_response(
                exc.code.upper(), exc.message, status=http_status.HTTP_400_BAD_REQUEST
            )
        response = success_response(
            {"tool_execution": receipt}, status=http_status.HTTP_201_CREATED
        )
        return record_processed_command(
            context=context,
            response=response,
            resource_type="tool_execution",
            resource_id=str(receipt["tool_execution_id"]),
        )


class ReworkPlanCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = ReworkPlanCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        company = _company_for_user(
            request, serializer.validated_data["company_id"], minimum_role="member"
        )
        if isinstance(company, Response):
            return company
        program = _optional_program(
            company=company, program_id=serializer.validated_data.get("program_id")
        )
        if isinstance(program, Response):
            return program
        command = _prepare_command(request=request, company=company, action="rework_plan.create")
        if isinstance(command, Response):
            return command
        context, replay = command
        if replay is not None:
            return replay
        plan = create_rework_plan(
            company=company,
            user=cast(User, request.user),
            program=program,
            validation_decision_ids=serializer.validated_data.get("validation_decision_ids") or [],
            notes=str(serializer.validated_data.get("notes") or ""),
        )
        response = success_response(
            {"rework_plan": rework_plan_payload(plan)},
            status=http_status.HTTP_201_CREATED,
        )
        return record_processed_command(
            context=context,
            response=response,
            resource_type="rework_plan",
            resource_id=str(plan.id),
        )


class ReworkPlanExecuteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, plan_id: UUID) -> Response:
        plan = ReworkPlan.objects.select_related("company", "program").filter(id=plan_id).first()
        if plan is None:
            return _not_found("Rework plan was not found.")
        if not _can_access_company(request, plan.company, "member"):
            return _forbidden("You do not have permission to execute this rework plan.")
        command = _prepare_command(
            request=request, company=plan.company, action=f"rework_plan.execute:{plan_id}"
        )
        if isinstance(command, Response):
            return command
        context, replay = command
        if replay is not None:
            return replay
        plan = execute_rework_plan(plan=plan, user=cast(User, request.user))
        response = success_response({"rework_plan": rework_plan_payload(plan)})
        return record_processed_command(
            context=context,
            response=response,
            resource_type="rework_plan",
            resource_id=str(plan.id),
        )


class StateProjectionListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        serializer = StateProjectionQuerySerializer(data=request.query_params)
        if not serializer.is_valid():
            return _validation_error(serializer.errors)
        company = _company_for_user(
            request, serializer.validated_data["company_id"], minimum_role="viewer"
        )
        if isinstance(company, Response):
            return company
        queryset = StateProjection.objects.filter(
            company=company,
            projection_type=serializer.validated_data["projection_type"],
        )
        if serializer.validated_data.get("program_id"):
            queryset = queryset.filter(program_id=serializer.validated_data["program_id"])
        return success_response(
            {"state_projections": [projection_payload(item) for item in queryset]}
        )


def _company_for_user(request: Request, company_id: UUID, *, minimum_role: str) -> Graph | Response:
    user = cast(User, request.user)
    company = accessible_company_queryset(user, minimum_role="viewer").filter(id=company_id).first()
    if company is None:
        return _not_found("Company was not found.")
    if not _can_access_company(request, company, minimum_role):
        return _forbidden("You do not have permission for this company.")
    return company


def _program_for_user(
    request: Request, program_id: UUID, *, minimum_role: str
) -> CompanyProgram | Response:
    user = cast(User, request.user)
    program = (
        CompanyProgram.objects.select_related("company")
        .filter(
            id=program_id,
            company__in=Graph.objects.for_user(user),
        )
        .first()
    )
    if program is None:
        return _not_found("Program was not found.")
    if not _can_access_company(request, program.company, minimum_role):
        return _forbidden("You do not have permission for this program.")
    return program


def _installation_for_user(
    request: Request,
    company_id: UUID,
    installation_id: UUID,
    *,
    minimum_role: str,
) -> CompanyOperatingModelInstallation | Response:
    company = _company_for_user(request, company_id, minimum_role=minimum_role)
    if isinstance(company, Response):
        return company
    installation = (
        CompanyOperatingModelInstallation.objects.select_related("company", "pack_release")
        .filter(company=company, id=installation_id)
        .first()
    )
    if installation is None:
        return _not_found("Pack installation was not found.")
    return installation


def _optional_program(
    *,
    company: Graph,
    program_id: UUID | None,
) -> CompanyProgram | None | Response:
    if not program_id:
        return None
    program = CompanyProgram.objects.filter(company=company, id=program_id).first()
    if program is None:
        return _not_found("Program was not found.")
    return program


def _asset_for_user(request: Request, asset_id: UUID, *, minimum_role: str) -> Asset | Response:
    user = cast(User, request.user)
    asset = (
        Asset.objects.select_related("company")
        .filter(
            id=asset_id,
            company__in=Graph.objects.for_user(user),
        )
        .first()
    )
    if asset is None:
        return _not_found("Artifact was not found.")
    if not _can_access_company(request, asset.company, minimum_role):
        return _forbidden("You do not have permission for this artifact.")
    return asset


def _optional_asset(*, company: Graph, asset_id: UUID | None) -> Asset | None | Response:
    if not asset_id:
        return None
    asset = Asset.objects.filter(company=company, id=asset_id).first()
    if asset is None:
        return _not_found("Artifact was not found.")
    return asset


def _periodic_review_for_user(
    request: Request, review_id: UUID, *, minimum_role: str
) -> PeriodicReviewDefinition | Response:
    user = cast(User, request.user)
    review = (
        PeriodicReviewDefinition.objects.select_related("company")
        .filter(
            id=review_id,
            company__in=Graph.objects.for_user(user),
        )
        .first()
    )
    if review is None:
        return _not_found("Periodic review was not found.")
    if not _can_access_company(request, review.company, minimum_role):
        return _forbidden("You do not have permission for this periodic review.")
    return review


def _optional_periodic_review(
    *,
    company: Graph,
    review_id: UUID | None,
) -> PeriodicReviewDefinition | None | Response:
    if not review_id:
        return None
    review = PeriodicReviewDefinition.objects.filter(company=company, id=review_id).first()
    if review is None:
        return _not_found("Periodic review was not found.")
    return review


def _can_access_company(request: Request, company: Graph, minimum_role: str) -> bool:
    user = cast(User, request.user)
    return has_company_access(user, company, minimum_role)


def _prepare_command(
    *,
    request: Request,
    company: Graph,
    action: str,
) -> tuple[Any, Response | None] | Response:
    if not idempotency_key_from_request(request):
        return error_response(
            "IDEMPOTENCY_KEY_REQUIRED",
            "Idempotency-Key is required for this operation.",
            status=http_status.HTTP_400_BAD_REQUEST,
        )
    context = build_idempotency_context(
        request=request,
        organization=company.organization,
        action=action,
        request_payload=request.data,
    )
    try:
        replay = replay_processed_command(context)
    except IdempotencyConflict as exc:
        return error_response(
            "IDEMPOTENCY_CONFLICT",
            str(exc),
            status=http_status.HTTP_409_CONFLICT,
            details=[{"action": exc.action, "idempotency_key": exc.idempotency_key}],
        )
    return context, replay


def _revision_payload(version: AssetVersion) -> dict[str, Any]:
    from application.services.work_artifacts import revision_payload

    return revision_payload(version)


def _validation_decision_payload(decision: ValidationDecision) -> dict[str, Any]:
    return validation_decision_payload(decision)


def _program_operation_payload(operation: Run) -> dict[str, Any]:
    input_json = operation.input_json if isinstance(operation.input_json, dict) else {}
    return {
        "id": str(operation.id),
        "company_id": str(operation.graph_version.graph_id),
        "status": operation.status,
        "operation_type": input_json.get("operation_type"),
        "operation_label": input_json.get("operation_label"),
        "operation_brief": input_json.get("operation_brief"),
        "program_id": input_json.get("program_id"),
        "stage_id": input_json.get("stage_id"),
        "started_at": operation.started_at.isoformat() if operation.started_at else None,
        "created_at": operation.started_at.isoformat() if operation.started_at else None,
    }


def _program_error(exc: CompanyProgramError) -> Response:
    status_code: int = (
        http_status.HTTP_404_NOT_FOUND
        if exc.code.endswith("not_found")
        else http_status.HTTP_400_BAD_REQUEST
    )
    if exc.code == "invalid_stage_transition":
        status_code = http_status.HTTP_409_CONFLICT
    return error_response(exc.code.upper(), exc.message, status=status_code)


def _stage_output_error(exc: ProgramStageOutputError) -> Response:
    status_code: int = (
        http_status.HTTP_404_NOT_FOUND
        if exc.code.endswith("not_found")
        else http_status.HTTP_400_BAD_REQUEST
    )
    return error_response(exc.code.upper(), exc.message, status=status_code)


def _validation_error(details: Any) -> Response:
    return error_response(
        "VALIDATION_ERROR",
        "Request validation failed.",
        status=http_status.HTTP_400_BAD_REQUEST,
        details=[{"field": key, "errors": value} for key, value in dict(details).items()],
    )


def _periodic_review_error(exc: PeriodicReviewError) -> Response:
    status_code = (
        http_status.HTTP_404_NOT_FOUND
        if exc.code.endswith("not_found")
        else http_status.HTTP_400_BAD_REQUEST
    )
    return error_response(exc.code.upper(), exc.message, status=status_code)


def _forbidden(message: str) -> Response:
    return error_response("FORBIDDEN", message, status=http_status.HTTP_403_FORBIDDEN)


def _not_found(message: str) -> Response:
    return error_response("NOT_FOUND", message, status=http_status.HTTP_404_NOT_FOUND)


def _pack_error(exc: OperatingModelPackError) -> Response:
    status_code: int = (
        http_status.HTTP_404_NOT_FOUND
        if exc.code.endswith("not_found")
        else http_status.HTTP_400_BAD_REQUEST
    )
    if exc.code in {
        "invalid_graph_json",
        "primary_pack_conflict",
        "pack_namespace_conflict",
        "pack_namespace_duplicate",
    }:
        status_code = http_status.HTTP_409_CONFLICT
    return error_response(exc.code.upper(), exc.message, status=status_code, details=exc.details)
