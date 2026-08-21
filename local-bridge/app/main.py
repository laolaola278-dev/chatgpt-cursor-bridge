"""ChatGPT Cursor Bridge - Local Bridge Service (Phase 1 MVP).

Only local file bridging capabilities are exposed. Shell execution, git
automation and browser/agent logic belong to later phases.
"""

from __future__ import annotations

from typing import Any, Callable

from fastapi import Depends, FastAPI, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from functools import lru_cache

from app.agent import AgentManager, AgentStorage
from app.collaboration import AgentCoordinator, CollaborationCommunication, CollaborationStorage, ConflictManager
from app.memory.intelligence.context_router import ContextRouter
from app.metrics import MetricsManager
from app.audit.logger import AuditLogger, get_audit_logger
from app.event import EventBus, EventStorage, EventType
from app.quality import MultiAgentQualityEvaluator, QualityEvaluator
from app.quality.gate4 import QualityGate4Evaluator
from app.quality.gate5 import QualityGate5Evaluator
from app.quality.gate6 import QualityGate6Evaluator
from app.quality.gate7 import QualityGate7Evaluator
from app.quality.gate8 import QualityGate8Evaluator
from app.intelligence import IntelligenceManager, IntelligenceStorage, DecisionManager
from app.simulation import SimulationManager, SimulationStorage
from app.execution import ExecutionManager, ExecutionStorage
from app.execution_dag import ExecutionDagManager, ExecutionDagStorage
from app.execution_loop import ExecutionLoopOrchestrator, ExecutionLoopRecovery, ExecutionLoopStorage, LoopContextBuilder
from app.benchmark import BenchmarkManager, BenchmarkStorage
from app.validation import ValidationManager, ValidationStorage
from app.reporting import EngineeringReportGenerator
from app.hardening.readiness import ProductionReadiness
from app.demo import DemoScenarioManager
from app.replay import EngineeringReplay, ReplayStorage
from app.export import ArtifactExporter
from app.agent_profile import AgentProfileManager, AgentProfileStorage
from app.model_router.provider import ProviderCapabilityRegistry
from app.engineering_graph import EngineeringGraphManager, EngineeringGraphStorage
from app.governance import ArchitectureDriftDetector, DebtManager, EngineeringHealthManager, GovernanceStorage, PolicyEngine
from app.memory.governance import GovernanceMemory
from app.quality.gate9 import QualityGate9Evaluator
from app.governance.routes import register_governance_routes
from app.organization import OrganizationGraphManager, OrganizationStorage
from app.organization.patterns import EngineeringPatternLibrary
from app.organization.routes import register_organization_routes
from app.organization_graph import GraphSnapshotManager, OrganizationGraphStorage
from app.organization_graph.routes import register_organization_graph_routes
from app.organization_strategy import OrganizationStrategyManager
from app.organization_strategy.routes import register_organization_strategy_routes
from app.intelligence.routes import register_intelligence_evolution_routes
from app.failure_intelligence import FailureIntelligenceAnalyzer
from app.memory.evolution import EvolutionTimeline
from app.metrics import AgentCapabilityMetrics
from app.metrics.engineering import EngineeringMetricsManager
from app.memory.execution import ExecutionMemory
from app.memory.intelligence.context_builder import ContextBuilder
from app.code_intelligence import CodeIndex, CodeScanner
from app.project_intelligence import ProjectProfileService
from app.knowledge_graph import KnowledgeGraph
from app.impact import ImpactAnalyzer
from app.memory.project import ProjectMemory
from app.memory.intelligence import ProjectIntelligenceMemory, IntelligenceMemory
from app.intelligence.observation import Observation, ObservationStore
from app.intelligence.pattern_intelligence import PatternIntelligence, PatternStore
from app.intelligence.risk_prediction import PredictionEngine, PredictionStore
from app.intelligence.outcome import OutcomeStore
from app.intelligence.evidence import EvidenceBundle, EvidenceStore, DecisionEvidenceManager
from app.memory.planning import PlanningMemory
from app.memory.query_engine import ContextQueryEngine
from app.runtime import RuntimeRecovery, RuntimeScheduler, RuntimeStateStore
from app.task import TaskDependencyGraph, TaskManager, TaskStatus, TaskStorage
from app.config import Settings, get_settings
from app.model_router import ModelRouter
from app.context.intelligence import ContextIndex
from app.context.service import ProjectContextService
from app.dashboard import DASHBOARD_HTML
from app.hardening.maintenance import MaintenanceService
from app.git.manager import GitManager
from app.git.policy import validate_binding as validate_git_binding
from app.memory.manager import MemoryManager
from app.memory.models import DecisionInput
from app.models.request import (
    ApprovalDecisionRequest,
    ApprovalReconfirmRequest,
    ApprovalRejectRequest,
    AgentCreateRequest,
    AgentMessageRequest,
    AgentTransitionRequest,
    FileCreateRequest,
    FileWriteRequest,
    GitCommitRequest,
    MemoryAppendRequest,
    MemoryDecisionRequest,
    MemoryInitRequest,
    PatchApplyRequest,
    TestRunRequest,
    WorkflowActionAttachRequest,
    WorkflowAgentAttachRequest,
    WorkflowCancelRequest,
    WorkflowCreateRequest,
    WorkflowRollbackRequest,
    WorkflowStageApprovalRequest,
    WorkflowStageReportRequest,
    WorkflowStageStartRequest,
    WorkflowQualityGateRequest,
    RuntimeCreateRequest,
    TaskCreateRequest,
    TaskTransitionRequest,
    TeamCreateRequest,
    CodeIndexRequest,
    ProjectMemoryProposalRequest,
    IntelligenceAnalyzeRequest,
    IntelligenceDecisionCreateRequest,
    SimulationCreateRequest,
    SimulationAnalyzeRequest,
    SimulationPlanRequest,
    ExecutionCreateRequest,
    ExecutionProposalRequest,
    ExecutionExecuteRequest,
    ExecutionLoopCreateRequest,
    ExecutionLoopActionRequest,
    ExecutionDagCreateRequest,
    ExecutionDagActionRequest,
    EngineeringGraphBuildRequest,
    EvolutionAppendRequest,
    BenchmarkCreateRequest,
    BenchmarkTransitionRequest,
    ValidationCreateRequest,
    ValidationTransitionRequest,
    ValidationRunRequest,
    DemoScenarioCreateRequest,
    ReplayCreateRequest,
    ExportCreateRequest,
    GovernanceDebtCreateRequest,
    GovernanceDebtTransitionRequest,
    GovernancePolicyEvaluateRequest,
    GovernanceTimelineAppendRequest,
    SessionCreateRequest,
    SessionTransitionRequest,
)
from app.models.response import (
    ApprovalPendingResponse,
    AuditLogResponse,
    FileReadResponse,
    HealthResponse,
    MemoryListResponse,
    MemoryReadResponse,
    MemoryStatusResponse,
    OperationResultResponse,
    PendingApprovalsResponse,
    ProjectTreeResponse,
    WorkflowListResponse,
    WorkflowStageAwaitingResponse,
    WorkflowStageView,
    WorkflowView,
    WorkspaceListResponse,
)
from app.patch.patch_service import PatchService
from app.security.permissions import (
    ApprovalRequest,
    ApprovalStore,
    PermissionLevel,
    evaluate,
    get_approval_store,
    level_for_action,
)
from app.security.sandbox import relative_display
from app.security.validator import ApprovalError, BridgeError, ResourceNotFound, ValidationFailed, ensure_request_id
from app.session import SessionManager, SessionStorage
from app.test_runner.runner import TestRunner
from app.workflow.executor import stage_execution_summary, workflow_memory_agent
from app.workflow.manager import WorkflowManager
from app.workflow.quality_gate import build_quality_gate
from app.workflow.rollback import RollbackManager
from app.workflow.storage import WorkflowStorage
from app.workspace.file_service import FileService
from app.workspace.manager import WorkspaceManager

SERVICE_NAME = "chatgpt-cursor-bridge-local"
SERVICE_VERSION = "0.9.0"
# Kept for compatibility with the existing /health contract. Phase 7 details
# are exposed by /system/health and the dashboard.
SERVICE_PHASE = "phase-6-engineering-toolchain"
SYSTEM_PHASE = "phase-7-developer-experience-production-hardening"

ALLOWED_ORIGINS = [
    "https://chatgpt.com",
    "https://chat.openai.com",
]


def settings_dependency() -> Settings:
    return get_settings()


def audit_dependency() -> AuditLogger:
    return get_audit_logger()


def approvals_dependency() -> ApprovalStore:
    return get_approval_store()


@lru_cache(maxsize=1)
def _get_session_storage_cached(root: str) -> SessionStorage:
    from pathlib import Path

    return SessionStorage(Path(root))


@lru_cache(maxsize=1)
def _get_workflow_storage_cached(root: str) -> WorkflowStorage:
    from pathlib import Path

    return WorkflowStorage(Path(root))


@lru_cache(maxsize=1)
def _get_agent_storage_cached(root: str) -> AgentStorage:
    from pathlib import Path

    return AgentStorage(Path(root))


def agent_storage_dependency(
    settings: Settings = Depends(settings_dependency),
) -> AgentStorage:
    return _get_agent_storage_cached(str(settings.agent_root))


def agent_manager_dependency(
    storage: AgentStorage = Depends(agent_storage_dependency),
    audit: AuditLogger = Depends(audit_dependency),
) -> AgentManager:
    return AgentManager(storage=storage, audit=audit)


def workflow_storage_dependency(
    settings: Settings = Depends(settings_dependency),
) -> WorkflowStorage:
    return _get_workflow_storage_cached(str(settings.workflow_root))


def workflow_manager_dependency(
    settings: Settings = Depends(settings_dependency),
    storage: WorkflowStorage = Depends(workflow_storage_dependency),
    approvals: ApprovalStore = Depends(approvals_dependency),
    audit: AuditLogger = Depends(audit_dependency),
) -> WorkflowManager:
    return WorkflowManager(
        settings=settings, storage=storage, approvals=approvals, audit=audit
    )


def session_storage_dependency(
    settings: Settings = Depends(settings_dependency),
) -> SessionStorage:
    return _get_session_storage_cached(str(settings.session_root))


def session_manager_dependency(
    storage: SessionStorage = Depends(session_storage_dependency),
    workflow_manager: WorkflowManager = Depends(workflow_manager_dependency),
    approvals: ApprovalStore = Depends(approvals_dependency),
    audit: AuditLogger = Depends(audit_dependency),
) -> SessionManager:
    return SessionManager(
        storage=storage,
        workflows=workflow_manager,
        approvals=approvals,
        audit=audit,
    )


def reset_workflow_storage_cache() -> None:
    _get_workflow_storage_cached.cache_clear()
    _get_session_storage_cached.cache_clear()
    _get_agent_storage_cached.cache_clear()


def event_bus_dependency(
    settings: Settings = Depends(settings_dependency),
    audit: AuditLogger = Depends(audit_dependency),
) -> EventBus:
    return EventBus(EventStorage(settings.event_root), audit)


def task_manager_dependency(
    settings: Settings = Depends(settings_dependency),
    audit: AuditLogger = Depends(audit_dependency),
    events: EventBus = Depends(event_bus_dependency),
) -> TaskManager:
    return TaskManager(TaskStorage(settings.task_db_path), audit, events)


def runtime_scheduler_dependency(
    settings: Settings = Depends(settings_dependency),
    audit: AuditLogger = Depends(audit_dependency),
    events: EventBus = Depends(event_bus_dependency),
    tasks: TaskManager = Depends(task_manager_dependency),
) -> RuntimeScheduler:
    return RuntimeScheduler(store=RuntimeStateStore(settings.runtime_root), tasks=tasks, audit=audit, events=events)


def _execute_action(
    request: ApprovalRequest,
    settings: Settings,
    *,
    approvals: ApprovalStore,
    workflow_manager: WorkflowManager,
) -> dict[str, Any]:
    files = FileService(settings)
    patches = PatchService(settings)
    memory = MemoryManager(settings)
    payload = request.payload

    # Phase 25/26/27 records are metadata-only and deliberately do not create a
    # source rollback snapshot. Existing file/memory/execution actions retain
    # their established rollback behavior.
    phase25_actions = {
        "intelligence_observation_record", "intelligence_pattern_analyze",
        "intelligence_prediction_analyze", "intelligence_outcome_record",
        "intelligence_knowledge_append", "intelligence_evidence_bundle",
        "intelligence_evaluation_record", "intelligence_benchmark_run",
        "intelligence_knowledge_improvement",
        "intelligence_governance_evaluate", "intelligence_governance_review",
        "context_patch_proposal",
        "llm_conversation_create", "llm_message_append", "llm_tool_proposal",
        "assistant_provider_config", "assistant_provider_forget", "assistant_settings_update",
    }
    if request.action not in phase25_actions:
        RollbackManager(settings).capture(request)

    if request.action == "intelligence_observation_record":
        raw = payload["observation"]
        observation = Observation.build(
            project_id=request.project,
            observation_id=raw.get("id"),
            timestamp=raw.get("timestamp"),
            type=raw["type"],
            source=raw["source"],
            summary=raw["summary"],
            metadata=raw.get("metadata", {}),
            risk_level=raw.get("risk_level", raw.get("riskLevel", "low")),
        )
        saved = ObservationStore(settings.intelligence_db_path, get_audit_logger()).save(observation)
        return {"observation": saved.as_dict(), "readOnlyAnalysis": True}
    if request.action in {"intelligence_pattern_analyze", "intelligence_prediction_analyze"}:
        limit = int(payload.get("limit", 500))
        observations = ObservationStore(settings.intelligence_db_path).list(request.project, limit=limit)
        pattern_store = PatternStore(settings.intelligence_db_path)
        patterns = PatternIntelligence(pattern_store).detect(request.project, observations)
        pattern_store.save_many(patterns)
        if request.action == "intelligence_pattern_analyze":
            return {"project": request.project, "patterns": [item.as_dict() for item in patterns], "readOnlyAnalysis": True}
        prediction_store = PredictionStore(settings.intelligence_db_path)
        predictions = PredictionEngine(prediction_store).predict(request.project, patterns, observations)
        prediction_store.save_many(predictions)
        return {"project": request.project, "patterns": [item.as_dict() for item in patterns], "predictions": [item.as_dict() for item in predictions], "readOnlyAnalysis": True}
    if request.action == "intelligence_outcome_record":
        outcome = OutcomeStore(settings.intelligence_db_path).record(**payload)
        return {"outcome": outcome.as_dict(), "readOnlyAnalysis": True}
    if request.action == "intelligence_knowledge_append":
        return IntelligenceMemory(settings).append_after_approval(
            request.project, payload["category"], payload["content"],
            source=payload.get("source", ""), evidence=payload.get("evidence", []),
            confidence=payload.get("confidence", 0.0), metadata=payload.get("metadata", {}),
        )
    if request.action == "intelligence_evidence_bundle":
        values = dict(payload)
        values.pop("reason", None)
        bundle = EvidenceBundle.build(**values)
        EvidenceStore(settings.intelligence_db_path).save(bundle)
        return {"evidence": bundle.as_dict(), "readOnlyAnalysis": True}
    if request.action == "intelligence_evaluation_record":
        from app.intelligence.validation import ValidationStore
        from app.intelligence.validation.models import EvaluationRecord

        raw = payload["evaluation"]
        record = EvaluationRecord(
            evaluation_id="", project_id=request.project, prediction_id=raw["prediction_id"],
            evaluation_kind=raw["evaluation_kind"], input_context=raw.get("input_context", ""),
            prediction_result=raw["prediction_result"], expected_outcome=raw["expected_outcome"],
            actual_outcome=raw["actual_outcome"], evaluation_result=raw["evaluation_result"],
            confidence=raw.get("confidence", 0.5), agent_id=raw.get("agent_id", ""),
            model_id=raw.get("model_id", ""), decision_id=raw.get("decision_id"),
            recommendation_id=raw.get("recommendation_id"), evidence=raw.get("evidence", []),
        )
        ValidationStore(settings.intelligence_db_path).save_evaluation(record)
        return {"evaluation": record.as_dict(), "readOnlyAnalysis": True}
    if request.action == "intelligence_benchmark_run":
        from app.intelligence.validation import BenchmarkRunner, ValidationStore, find_builtin_dataset

        dataset = find_builtin_dataset(payload["dataset_id"], request.project)
        if dataset is None:
            raise ApprovalError(f"Unknown benchmark dataset: {payload['dataset_id']}")
        run = BenchmarkRunner().run(
            dataset, model_id=payload.get("model_id", "deterministic"),
            predictions=payload.get("predictions", []),
        )
        ValidationStore(settings.intelligence_db_path).save_benchmark(run)
        return {"benchmark": run.as_dict(), "readOnlyAnalysis": True}
    if request.action == "intelligence_knowledge_improvement":
        from app.intelligence.validation import KnowledgeImprovementEngine, ValidationStore

        improvement = KnowledgeImprovementEngine().apply_after_approval(
            project_id=request.project, evaluation_id=payload["evaluation_id"],
            prediction_id=payload["prediction_id"], category=payload["category"],
            content=payload["content"], source=payload.get("source", "evaluation_feedback"),
            evidence=payload.get("evidence", []), confidence=payload.get("confidence", 0.0),
            approval_request_id=request.request_id,
        )
        ValidationStore(settings.intelligence_db_path).save_improvement(improvement)
        return {"improvement": improvement.as_dict(), "readOnlyAnalysis": True}
    if request.action == "intelligence_governance_evaluate":
        from app.intelligence.governance import (
            GovernanceStore,
            GovernanceReviewEngine,
            IntelligenceRiskAnalyzer,
        )
        from app.intelligence.governance.models import GovernanceRecord, PolicyViolation
        from app.intelligence.governance.rules import GovernanceRuleEngine, list_policies

        store = GovernanceStore(settings.intelligence_db_path)
        raw = payload
        metrics = payload.get("metrics", {}) or {}
        risk_analysis = IntelligenceRiskAnalyzer().analyze(
            project=request.project,
            source_kind=raw["source_kind"],
            source_id=raw["source_id"],
            confidence=raw.get("confidence", 0.5),
            evaluation_result=raw.get("evaluation_result", ""),
            source_risk_level=raw.get("risk_level", "LOW"),
            source_risk_score=raw.get("risk_score", 0.0),
            prior_accuracy=metrics.get("accuracy"),
            similar_history=raw.get("similar_history", []),
            model_reliability=metrics.get("model_reliability"),
            regression=bool(metrics.get("regression_rate") or 0) > 0.2,
            context=raw.get("context", ""),
            agent_id=raw.get("agent_id", ""),
            model_id=raw.get("model_id", ""),
        )
        rule_evaluation = GovernanceRuleEngine().evaluate(
            project=request.project,
            source_kind=raw["source_kind"],
            source_id=raw["source_id"],
            confidence=raw.get("confidence", 0.5),
            risk_level=risk_analysis.finding.risk_level,
            risk_score=risk_analysis.finding.risk_score,
            accuracy=metrics.get("accuracy"),
            failure_rate=metrics.get("failure_rate"),
            regression_rate=metrics.get("regression_rate"),
            rejection_rate=metrics.get("rejection_rate"),
            model_reliability=metrics.get("model_reliability"),
            context=raw.get("context", ""),
        )
        record = GovernanceRecord(
            governance_id="", project_id=request.project,
            source_kind=raw["source_kind"], source_id=raw["source_id"],
            agent_id=raw.get("agent_id", ""), model_id=raw.get("model_id", ""),
            policy_ids=rule_evaluation.matched_policies,
            risk_level=risk_analysis.finding.risk_level,
            risk_score=risk_analysis.finding.risk_score,
            confidence=risk_analysis.finding.confidence,
            evaluation_result=raw.get("evaluation_result", ""),
            governance_result=rule_evaluation.governance_result,
            reason=risk_analysis.finding.reason,
            evidence=raw.get("evidence", []),
            audit_request_id=request.request_id,
        )
        store.save_record(record)
        store.save_risk(risk_analysis.finding)
        violations = [
            PolicyViolation(
                violation_id="", policy_id=outcome.policy_id, project_id=request.project,
                source_id=raw["source_id"], source_kind=raw["source_kind"],
                severity=outcome.severity, reason=outcome.reason,
                confidence=record.confidence,
            )
            for outcome in rule_evaluation.outcomes
            if outcome.severity in ("warning", "blocking")
        ]
        store.save_violations(violations)
        proposed = False
        if rule_evaluation.requires_review or rule_evaluation.blocking:
            draft = GovernanceReviewEngine().build_proposal(
                project_id=request.project, source_id=raw["source_id"],
                source_kind=raw["source_kind"], risk_level=record.risk_level,
                reason=f"Governance result {rule_evaluation.governance_result}: {record.reason}",
                recommended_action="Human governance review of the intelligence claim before any downstream use",
                confidence=record.confidence, evidence=raw.get("evidence", []),
            )
            proposal = store.save_proposal(GovernanceReviewEngine().create_record(draft))
            proposed = True
        return {
            "governance": record.as_dict(),
            "risk": risk_analysis.finding.as_dict(),
            "rules": rule_evaluation.as_dict(),
            "violations": [item.as_dict() for item in violations],
            "reviewProposalCreated": proposed,
            "readOnlyAnalysis": True,
        }
    if request.action == "context_patch_proposal":
        from app.context.dev.intelligence import PatchProposalGenerator, PatchProposalStore
        from app.models.request import ContextPatchProposalRequest

        proposal = PatchProposalGenerator().build(
            project=request.project,
            target_file=payload["targetFile"],
            target_symbol=payload.get("targetSymbol", ""),
            proposed_change=payload["proposedChange"],
            reason=payload["reason"],
            expected_impact=payload.get("expectedImpact", ""),
            risk=payload.get("risk", "medium"),
            agent=payload.get("agent", "ASSISTANT"),
        )
        store = PatchProposalStore(settings.workspace_root.parent / "context_dev" / "proposals.db")
        store.save(proposal, approval_request_id=request.request_id)
        return {"proposal": proposal.as_dict(), "applied": False, "readOnlyAnalysis": True}
    if request.action == "llm_conversation_create":
        from app.llm_gateway import LLMGateway, default_llm_db_path

        gateway = LLMGateway(llm_db_path=default_llm_db_path())
        conversation = gateway.create_conversation(
            project=request.project,
            provider=payload.get("provider", "local"),
            model=payload.get("model", "local/simulator-v1"),
            title=payload.get("title", "Untitled"),
            agent=payload.get("agent", ""),
            approval_request_id=request.request_id,
        )
        return {"conversation": conversation.as_dict(), "readOnlyAnalysis": True}
    if request.action == "llm_message_append":
        from app.llm_gateway import LLMGateway, MessageRole, default_llm_db_path

        gateway = LLMGateway(llm_db_path=default_llm_db_path())
        message = gateway.append_message(
            conversation_id=payload["conversation_id"],
            project=request.project,
            role=MessageRole.USER,
            content=payload["content"],
            approval_request_id=request.request_id,
        )
        return {"message": message.as_dict(), "readOnlyAnalysis": True}
    if request.action == "llm_tool_proposal":
        from app.llm_gateway import LLMGateway, default_llm_db_path

        gateway = LLMGateway(llm_db_path=default_llm_db_path())
        proposal = gateway.record_tool_proposal(
            conversation_id=payload["conversation_id"],
            project=request.project,
            message_id=payload.get("message_id", ""),
            tool_name=payload["tool_name"],
            arguments=payload.get("arguments", "{}"),
            reason=payload.get("reason", "Tool call requested by model"),
            approval_request_id=request.request_id,
        )
        return {"proposal": proposal.as_dict(), "executed": False, "readOnlyAnalysis": True}
    if request.action == "assistant_provider_config":
        # Phase 32: promote the already-encrypted staged credential. The key was
        # encrypted when it arrived, so nothing sensitive is read from the
        # approval payload here.
        from app.assistant.service import AssistantService

        result = AssistantService().activate_provider_config(
            payload["credential_id"], approval_request_id=request.request_id
        )
        return {"provider": result, "readOnlyAnalysis": True}
    if request.action == "assistant_provider_forget":
        from app.assistant.service import AssistantService

        return {
            "provider": AssistantService().forget_provider(payload["provider"]),
            "readOnlyAnalysis": True,
        }
    if request.action == "assistant_settings_update":
        from app.assistant.service import AssistantService

        return {
            "settings": AssistantService().update_preferences(payload.get("preferences", {})),
            "readOnlyAnalysis": True,
        }
    if request.action == "intelligence_governance_review":
        # Aliased so the module-level GovernanceMemory (Phase 21 timeline)
        # stays visible to the other branches of this function.
        from app.intelligence.governance import GovernanceMemory as IntelligenceGovernanceMemory
        from app.intelligence.governance import GovernanceReviewEngine, GovernanceStore

        store = GovernanceStore(settings.intelligence_db_path)
        existing = store.get_proposal(payload["proposal_id"], request.project)
        if existing is None:
            raise ApprovalError(f"Governance proposal '{payload['proposal_id']}' was not found for this project")
        proposal = GovernanceReviewEngine().apply_review(
            proposal_id=existing.proposal_id, project_id=request.project,
            source_id=existing.source_id, source_kind=existing.source_kind,
            risk_level=existing.risk_level, reason=existing.reason,
            recommended_action=existing.recommended_action,
            confidence=existing.confidence, evidence=existing.evidence,
            decision=payload["decision"], reviewer_note=payload.get("reviewer_note", ""),
            approval_request_id=request.request_id,
        )
        store.save_proposal(proposal)
        memory = IntelligenceGovernanceMemory().apply_after_approval(
            project_id=request.project, category="review",
            content=f"Governance review for {existing.source_kind} {existing.source_id}: {payload['decision']} - {payload.get('reviewer_note', '')}",
            source="governance_review", evidence=[existing.proposal_id],
            confidence=existing.confidence, approval_request_id=request.request_id,
        )
        store.save_memory(memory)
        return {"review": proposal.as_dict(), "memory": memory.as_dict(), "readOnlyAnalysis": True}

    if request.action == "file_create":
        return files.create_file(request.project, request.path, payload["content"])
    if request.action == "file_write":
        return files.write_file(request.project, request.path, payload["content"])
    if request.action == "patch_apply":
        return patches.apply(request.project, request.path, payload["patch"])
    if request.action == "memory_init":
        return memory.initialise(request.project)
    if request.action == "memory_append":
        return memory.append(request.project, payload["document"], payload["content"])
    if request.action == "memory_decision":
        return memory.append_decision(
            request.project,
            DecisionInput.build(
                title=payload["title"],
                context=payload["context"],
                decision=payload["decision"],
                consequence=payload["consequence"],
            ),
        )
    if request.action == "git_commit":
        return GitManager(settings).commit(request.project, payload["message"]).as_dict()
    if request.action == "test_run":
        result = TestRunner(settings).execute(request.project, payload["command"])
        workflow_manager.record_test_result(
            request.workflow_id or "",
            request.stage_id or "",
            command=result.command,
            passed=result.passed,
            timed_out=result.timed_out,
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
        )
        return result.as_dict()
    if request.action == "workflow_rollback":
        return RollbackManager(settings).restore(
            payload["workflow_id"], payload["stage_id"]
        )
    if request.action == "session_create":
        session = SessionManager(
            storage=SessionStorage(settings.session_root),
            workflows=workflow_manager,
            approvals=approvals,
            audit=get_audit_logger(),
        ).create(
            project=request.project,
            workflow_id=payload.get("workflow_id"),
            stage_id=payload.get("stage_id"),
            approval_id=payload.get("approval_id"),
        )
        return session.as_dict()
    if request.action == "session_transition":
        session = SessionManager(
            storage=SessionStorage(settings.session_root),
            workflows=workflow_manager,
            approvals=approvals,
            audit=get_audit_logger(),
        ).transition(payload["session_id"], payload["status"])
        return session.as_dict()
    if request.action == "agent_create":
        agent = AgentManager(
            storage=AgentStorage(settings.agent_root),
            audit=get_audit_logger(),
            router=ModelRouter(),
        ).create(
            project=request.project,
            session_id=payload["session_id"],
            role=payload["role"],
            memory_scope=payload["memory_scope"],
            model_id=payload.get("model_id"),
            permissions=payload.get("permissions"),
            workflow_id=payload.get("workflow_id"),
            stage_id=payload.get("stage_id"),
        )
        return agent.as_dict()
    if request.action == "agent_transition":
        agent = AgentManager(
            storage=AgentStorage(settings.agent_root),
            audit=get_audit_logger(),
        ).transition(payload["agent_id"], payload["status"])
        return agent.as_dict()
    if request.action == "agent_message":
        message = AgentManager(
            storage=AgentStorage(settings.agent_root),
            audit=get_audit_logger(),
        ).send_message(
            from_agent=payload["from_agent"],
            to_agent=payload["to_agent"],
            task=payload["task"],
            context_reference=payload.get("context_reference", ""),
        )
        return message.as_dict()
    if request.action == "workflow_agent_attach":
        stage = workflow_manager.attach_agent(
            workflow_id=payload["workflow_id"],
            stage_id=payload["stage_id"],
            agent_id=payload["agent_id"],
        )
        return stage.as_dict()
    if request.action == "quality_gate_submit":
        stage = workflow_manager.attach_quality_gate(
            payload["workflow_id"], payload["stage_id"], payload["quality_gate"]
        )
        return stage.as_dict()
    if request.action == "runtime_create":
        events = EventBus(EventStorage(settings.event_root), get_audit_logger())
        tasks = TaskManager(TaskStorage(settings.task_db_path), get_audit_logger(), events)
        scheduler = RuntimeScheduler(store=RuntimeStateStore(settings.runtime_root), tasks=tasks, audit=get_audit_logger(), events=events)
        return scheduler.create(
            agent_id=payload["agent_id"], session_id=payload["session_id"],
            workflow_id=payload["workflow_id"], stage_id=payload["stage_id"],
        ).as_dict()
    if request.action == "task_create":
        events = EventBus(EventStorage(settings.event_root), get_audit_logger())
        manager = TaskManager(TaskStorage(settings.task_db_path), get_audit_logger(), events)
        return manager.create_task(
            workflow_id=payload["workflow_id"], stage_id=payload["stage_id"],
            agent_id=payload["agent_id"], priority=payload.get("priority", 0),
            context=payload.get("context", {}),
        ).as_dict()
    if request.action == "task_transition":
        events = EventBus(EventStorage(settings.event_root), get_audit_logger())
        manager = TaskManager(TaskStorage(settings.task_db_path), get_audit_logger(), events)
        return manager.transition(payload["task_id"], payload["status"]).as_dict()
    if request.action == "team_create":
        storage = CollaborationStorage(settings.workspace_root.parent / "collaboration")
        coordinator = AgentCoordinator(storage, get_audit_logger(), EventBus(EventStorage(settings.event_root), get_audit_logger()))
        return coordinator.create_team(workflow_id=payload["workflow_id"], members=payload["members"], leader=payload["leader"]).as_dict()
    if request.action == "code_index":
        scanner = CodeScanner(settings)
        index = CodeIndex(settings.code_index_db_path, scanner)
        summary = index.index_project(request.project)
        graph = KnowledgeGraph(settings.knowledge_graph_db_path, index).build(request.project)
        return {**summary.as_dict(), "graphNodes": len(graph["nodes"]), "graphEdges": len(graph["edges"]), "readOnlyAnalysis": True}
    if request.action == "project_memory_append":
        return ProjectMemory(settings).append_after_approval(
            request.project, payload["category"], payload["content"]
        )
    if request.action == "intelligence_memory_append":
        return ProjectIntelligenceMemory(settings).append_after_approval(
            request.project, payload["category"], payload["content"]
        )
    if request.action == "planning_memory_append":
        return PlanningMemory(settings).append_after_approval(
            request.project, payload["category"], payload["content"]
        )
    if request.action == "execution_memory_append":
        return ExecutionMemory(settings).append_after_approval(
            request.project, payload["category"], payload["content"]
        )
    if request.action == "execution_create":
        manager = ExecutionManager(ExecutionStorage(settings.execution_db_path), settings, approvals=approvals, workflow_manager=workflow_manager)
        plan = SimulationStorage(settings.simulation_db_path).get_plan(payload["plan_id"])
        if plan is None:
            raise ValidationFailed(f"Engineering plan '{payload['plan_id']}' was not found")
        tasks = manager.create_from_plan(
            plan_id=plan.id,
            project=request.project,
            workflow_id=payload.get("workflow_id"),
            plan_content=plan.content,
        )
        return {"planId": plan.id, "tasks": [task.as_dict() for task in tasks], "readOnlyAnalysis": True}
    if request.action == "execution_proposal":
        manager = ExecutionManager(ExecutionStorage(settings.execution_db_path), settings, approvals=approvals, workflow_manager=workflow_manager)
        return manager.generate_proposal(payload["task_id"]).as_dict()
    if request.action == "execution_execute":
        manager = ExecutionManager(ExecutionStorage(settings.execution_db_path), settings, approvals=approvals, workflow_manager=workflow_manager)
        result = manager.execute(payload["proposal_id"], approval_id=request.request_id)
        task = manager.get_task(result.task_id)
        orchestrator = ExecutionLoopOrchestrator(ExecutionLoopStorage(settings.execution_loop_db_path), settings, approvals=approvals, audit=get_audit_logger())
        loop = orchestrator.find_loop_for_task(task.id)
        output = result.as_dict()
        if loop is not None:
            # Loop-bound execution: the loop owns learning memory (queued at
            # verification); no separate Phase 15 implementation proposal.
            loop = orchestrator.on_executed(loop.id, result)
            output["executionLoop"] = loop.as_dict()
            return output
        # Non-loop execution: queue the Phase 15 implementation memory proposal,
        # which still requires an independent human approval.
        content = f"## Implementation: {task.title}\n\n- Result: {result.verification.get('status')}\n- Files: {', '.join(result.files_changed)}\n- Verification: {', '.join(result.verification.get('checks', []))}\n"
        memory_request = approvals.create(
            action="execution_memory_append",
            project=request.project,
            path="memory/execution/implementation-history.md",
            payload={"category": "implementation", "content": content},
            reason=f"Record approved execution result {result.id}",
            preview=f"[execution memory proposal/implementation]\\n\\n{content[:1200]}",
            workflow_id=task.workflow_id,
        )
        get_audit_logger().record(action="execution_memory_append", path=f"{request.project}:memory/execution/implementation-history.md", permission="LEVEL_1", approved=False, result="pending_approval", detail="Execution memory proposal queued; separate approval required", request_id=memory_request.request_id)
        output["memoryProposal"] = memory_request.as_dict()
        return output
    if request.action == "execution_loop_create":
        orchestrator = ExecutionLoopOrchestrator(ExecutionLoopStorage(settings.execution_loop_db_path), settings, approvals=approvals, audit=get_audit_logger())
        loop = orchestrator.create(project=request.project, plan_id=payload["plan_id"], workflow_id=payload.get("workflow_id"), approval_id=request.request_id)
        return loop.as_dict()
    if request.action == "execution_loop_prepare":
        orchestrator = ExecutionLoopOrchestrator(ExecutionLoopStorage(settings.execution_loop_db_path), settings, approvals=approvals, audit=get_audit_logger())
        return orchestrator.prepare(payload["loop_id"], approval_id=request.request_id).as_dict()
    if request.action == "execution_loop_verify":
        orchestrator = ExecutionLoopOrchestrator(ExecutionLoopStorage(settings.execution_loop_db_path), settings, approvals=approvals, audit=get_audit_logger())
        return orchestrator.verify(payload["loop_id"], approval_id=request.request_id, quality_score=payload.get("quality_score"), risk_score=payload.get("risk_score"), test_passed=payload.get("test_passed")).as_dict()
    if request.action == "execution_loop_rollback":
        orchestrator = ExecutionLoopOrchestrator(ExecutionLoopStorage(settings.execution_loop_db_path), settings, approvals=approvals, audit=get_audit_logger())
        return orchestrator.rollback(payload["loop_id"], approval_id=request.request_id).as_dict()
    if request.action == "execution_loop_recover":
        orchestrator = ExecutionLoopOrchestrator(ExecutionLoopStorage(settings.execution_loop_db_path), settings, approvals=approvals, audit=get_audit_logger())
        return orchestrator.recover(payload["loop_id"], approval_id=request.request_id).as_dict()
    if request.action == "execution_dag_create":
        orchestrator = ExecutionLoopOrchestrator(ExecutionLoopStorage(settings.execution_loop_db_path), settings, approvals=approvals, audit=get_audit_logger())
        manager = ExecutionDagManager(ExecutionDagStorage(settings.execution_dag_db_path), orchestrator, audit=get_audit_logger())
        dag = manager.create(project=request.project, loop_ids=payload["loop_ids"], edges=payload.get("edges", []))
        for loop_id in dag.loop_ids:
            manager.on_loop_completed(dag.id, loop_id)
        return dag.as_dict()
    if request.action == "execution_dag_advance":
        orchestrator = ExecutionLoopOrchestrator(ExecutionLoopStorage(settings.execution_loop_db_path), settings, approvals=approvals, audit=get_audit_logger())
        manager = ExecutionDagManager(ExecutionDagStorage(settings.execution_dag_db_path), orchestrator, audit=get_audit_logger())
        return manager.advance(payload["dag_id"])
    if request.action == "engineering_graph_rebuild":
        loop_storage = ExecutionLoopStorage(settings.execution_loop_db_path)
        loops = [loop.as_dict() for loop in loop_storage.list_loops(project=request.project)]
        execution = ExecutionManager(ExecutionStorage(settings.execution_db_path), settings, approvals=approvals, workflow_manager=workflow_manager)
        tasks = [task.as_dict() for task in execution.list_tasks(project=request.project)]
        results = [result.as_dict() for result in execution.list_results(project=request.project)]
        decisions = [decision.as_dict() for decision in IntelligenceStorage(settings.intelligence_db_path).list_decisions(project=request.project)]
        timeline = EvolutionTimeline(settings.memory_root / "evolution")
        memories = timeline.list(request.project)
        graph = EngineeringGraphManager(EngineeringGraphStorage(settings.workspace_root.parent / "engineering_graph" / "engineering_graph.db"), get_audit_logger()).rebuild(
            request.project, tasks=tasks, decisions=decisions, loops=loops, memories=memories, verifications=results,
        )
        return graph.as_dict()
    if request.action == "evolution_timeline_append":
        return EvolutionTimeline(settings.memory_root / "evolution").append_after_approval(
            request.project, payload["kind"], payload["title"], payload["content"], payload.get("source_id"),
        )
    if request.action == "benchmark_create":
        manager = BenchmarkManager(BenchmarkStorage(settings.workspace_root.parent / "benchmarks" / "benchmark.db"), get_audit_logger())
        return manager.create(request.project, payload["repository"], payload.get("cases", [])).as_dict()
    if request.action == "benchmark_transition":
        manager = BenchmarkManager(BenchmarkStorage(settings.workspace_root.parent / "benchmarks" / "benchmark.db"), get_audit_logger())
        return manager.transition(payload["benchmark_id"], payload["status"]).as_dict()
    if request.action == "validation_create":
        manager = ValidationManager(ValidationStorage(settings.workspace_root.parent / "validation" / "validation.db"), get_audit_logger())
        return manager.create(request.project, payload["repository"], payload.get("language", "unknown"), payload.get("framework", "unknown"), payload.get("scenarios", [])).as_dict()
    if request.action == "validation_transition":
        manager = ValidationManager(ValidationStorage(settings.workspace_root.parent / "validation" / "validation.db"), get_audit_logger())
        return manager.transition(payload["validation_id"], payload["status"]).as_dict()
    if request.action == "validation_run_record":
        manager = ValidationManager(ValidationStorage(settings.workspace_root.parent / "validation" / "validation.db"), get_audit_logger())
        return manager.record_run(payload["scenario_id"], workflow_id=payload.get("workflow_id"), execution_loop_id=payload.get("execution_loop_id"), agents=payload.get("agents", []), result=payload.get("result", "RECORDED"), human_rating=payload.get("human_rating")).as_dict()
    if request.action == "demo_scenario_create":
        return DemoScenarioManager(get_audit_logger()).create(payload["name"], payload["issue"]).as_dict()
    if request.action == "replay_create":
        audit = get_audit_logger()
        events = EventBus(EventStorage(settings.event_root), audit).list_events(limit=500)
        audit_entries = audit.read_entries(limit=500)
        runs = ValidationStorage(settings.workspace_root.parent / "validation" / "validation.db")
        run_records: list[Any] = []
        for project_record in runs.list(request.project):
            for scenario in runs.scenarios(project_record.id):
                run_records.extend(runs.runs(scenario.id))
        return EngineeringReplay(ReplayStorage(settings.workspace_root.parent / "replay" / "replay.db"), audit).build(request.project, payload["title"], events=events, audit_entries=audit_entries, runs=run_records)
    if request.action == "artifact_export":
        return ArtifactExporter(settings.workspace_root.parent / "artifacts", get_audit_logger()).export(payload["kind"], request.project, payload.get("payload", {}), payload.get("markdown", ""))
    if request.action == "governance_debt_create":
        manager = DebtManager(GovernanceStorage(settings.governance_db_path))
        return manager.create(
            request.project, category=payload["category"], severity=payload["severity"],
            source=payload["source"], affected_components=payload.get("affected_components", []),
            estimated_cost=payload.get("estimated_cost", 0), risk=payload.get("risk", "low"),
        ).as_dict()
    if request.action == "governance_debt_transition":
        manager = DebtManager(GovernanceStorage(settings.governance_db_path))
        return manager.transition(payload["debt_id"], payload["status"]).as_dict()
    if request.action == "governance_policy_evaluate":
        engine = PolicyEngine()
        evaluations = engine.evaluate_and_record(
            request.project, payload.get("signal", {}), GovernanceStorage(settings.governance_db_path)
        )
        return {"project": request.project, "evaluations": [evaluation.as_dict() for evaluation in evaluations], "readOnly": True}
    if request.action == "governance_memory_append":
        return GovernanceMemory(settings).append_after_approval(

            request.project, payload["category"], payload["content"]
        )
    if request.action == "organization_entity_register":
        manager = OrganizationGraphManager(OrganizationStorage(settings.organization_db_path))
        return manager.register(
            payload["type"], payload["name"], payload.get("parent_id"), payload.get("metadata", {})
        ).as_dict()
    if request.action == "organization_incident_create":
        from app.organization.models import OrgIncident

        incident = OrgIncident(
            project=payload["project"], title=payload["title"], summary=payload["summary"],
            severity=payload.get("severity", "medium"), service=payload.get("service", ""),
            signature=payload.get("signature", ""),
        )
        OrganizationStorage(settings.organization_db_path).save_incident(incident)
        return incident.as_dict()
    if request.action == "organization_decision_create":
        from app.organization.models import OrgDecision

        decision = OrgDecision(
            project=payload["project"], title=payload["title"], context=payload["context"],
            decision=payload["decision"], consequence=payload["consequence"],
        )
        OrganizationStorage(settings.organization_db_path).save_decision(decision)
        return decision.as_dict()
    if request.action == "organization_pattern_create":
        library = EngineeringPatternLibrary(OrganizationStorage(settings.organization_db_path))
        return library.record(
            payload["category"], payload["name"], payload["summary"],
            payload["project"], payload.get("tags", []),
        ).as_dict()
    if request.action == "organization_graph_sync":
        from app.organization.storage import OrganizationStorage as Phase22OrgStorage

        graph_storage = OrganizationGraphStorage(settings.organization_graph_db_path)
        entities = [entity.as_dict() for entity in Phase22OrgStorage(settings.organization_db_path).list_entities()]
        synced = graph_storage.sync_from_entities(entities)
        return {"synced": synced, "nodes": len(graph_storage.list_nodes()), "readOnly": True}
    if request.action == "organization_graph_snapshot_create":
        return GraphSnapshotManager(OrganizationGraphStorage(settings.organization_graph_db_path)).create().as_dict()
    if request.action == "organization_graph_snapshot_restore":
        return GraphSnapshotManager(OrganizationGraphStorage(settings.organization_graph_db_path)).restore(payload["snapshot_id"])
    if request.action == "organization_strategy_create":
        return OrganizationStrategyManager(settings, get_audit_logger()).create_strategy(payload)
    if request.action == "organization_strategy_evaluate":
        return OrganizationStrategyManager(settings, get_audit_logger()).evaluate_strategies(payload.get("strategy_ids", []))
    if request.action == "organization_strategy_decision_create":
        return OrganizationStrategyManager(settings, get_audit_logger()).create_decision(payload)
    if request.action == "organization_strategy_decision_transition":
        return OrganizationStrategyManager(settings, get_audit_logger()).transition_decision(payload["decision_id"], payload["status"])
    if request.action == "organization_memory_append":
        return OrganizationStrategyManager(settings, get_audit_logger()).append_memory(
            payload["organization"], payload["category"], payload["content"]
        )
    if request.action == "organization_learning_scan":
        from app.failure_intelligence import FailureIntelligenceAnalyzer
        from app.organization.learning import CrossProjectLearner
        from app.organization.models import OrgFailurePattern

        storage = OrganizationStorage(settings.organization_db_path)
        loops = [loop.as_dict() for loop in ExecutionLoopStorage(settings.execution_loop_db_path).list_loops(project=request.project)]
        execution = ExecutionManager(ExecutionStorage(settings.execution_db_path), settings, approvals=approvals, workflow_manager=workflow_manager)
        results = [result.as_dict() for result in execution.list_results(project=request.project)]
        analyzed = FailureIntelligenceAnalyzer().analyze(request.project, loops=loops, results=results)
        patterns = [
            OrgFailurePattern(
                project=pattern.project, category=pattern.category, signature=pattern.signature,
                occurrences=pattern.occurrences, severity=pattern.severity,
            )
            for pattern in analyzed
        ]
        storage.replace_failure_patterns(request.project, patterns)
        library = [pattern.as_dict() for pattern in storage.list_failure_patterns()]
        matches = CrossProjectLearner().analyze(
            request.project, [pattern.as_dict() for pattern in patterns], library
        )
        return {
            "project": request.project,
            "patterns": [pattern.as_dict() for pattern in patterns],
            "matches": [match.as_dict() for match in matches],
            "readOnly": True,
        }
    if request.action == "simulation_create":
        manager = SimulationManager(SimulationStorage(settings.simulation_db_path), CodeIndex(settings.code_index_db_path))
        return manager.create(project=request.project, problem=payload["problem"]).as_dict()
    if request.action == "simulation_analyze":
        manager = SimulationManager(SimulationStorage(settings.simulation_db_path), CodeIndex(settings.code_index_db_path))
        proposal = None
        if payload.get("proposal_id"):
            proposal = IntelligenceStorage(settings.intelligence_db_path).get_proposal(payload["proposal_id"])
        return manager.analyze(payload["simulation_id"], proposal=proposal, test_coverage=payload.get("test_coverage"))
    if request.action == "simulation_plan":
        manager = SimulationManager(SimulationStorage(settings.simulation_db_path), CodeIndex(settings.code_index_db_path))
        plan = manager.plan(payload["simulation_id"], payload["scenario_id"])
        memory_request = approvals.create(action="planning_memory_append", project=request.project, path="memory/planning/engineering-plans.md", payload={"category": "plans", "content": plan.content}, reason=f"Record approved engineering plan {plan.id}", preview=f"[planning memory proposal/plans]\\n\\n{plan.content[:1200]}")
        get_audit_logger().record(action="planning_memory_append", path=f"{request.project}:memory/planning/engineering-plans.md", permission="LEVEL_1", approved=False, result="pending_approval", detail="Engineering plan memory proposal queued; separate approval required", request_id=memory_request.request_id)
        result = plan.as_dict(); result["memoryProposal"] = memory_request.as_dict(); return result
    if request.action == "intelligence_analyze":
        manager = IntelligenceManager(
            IntelligenceStorage(settings.intelligence_db_path),
            CodeIndex(settings.code_index_db_path),
        )
        return manager.analyze(
            request.project,
            changed_files=payload.get("changed_files", []),
            test_coverage=payload.get("test_coverage"),
            security_sensitive=payload.get("security_sensitive", False),
        )
    if request.action == "intelligence_decision_create":
        manager = IntelligenceManager(
            IntelligenceStorage(settings.intelligence_db_path),
            CodeIndex(settings.code_index_db_path),
        )
        decision = manager.create_decision(
            project=request.project,
            proposal_id=payload["proposal_id"],
            title=payload["title"],
            context=payload["context"],
            options=payload["options"],
            recommendation=payload["recommendation"],
            simulation_id=payload.get("simulation_id"),
            selected_scenario=payload.get("selected_scenario"),
            confidence=payload.get("confidence"),
            alternatives=payload.get("alternatives", []),
            implementation_plan_id=payload.get("implementation_plan_id"),
            execution_status=payload.get("execution_status"),
        )
        # Approval creates only the decision metadata. Memory is still a
        # separate proposal and must be approved independently.
        memory_request = approvals.create(
            action="intelligence_memory_append",
            project=request.project,
            path="memory/project/intelligence/engineering-decisions.md",
            payload={"category": "decisions", "content": DecisionManager.memory_content(decision)},
            reason=f"Record approved engineering decision proposal: {decision.title}",
            preview=f"[intelligence memory proposal/decisions]\\n\\n{DecisionManager.memory_content(decision)[:1200]}",
        )
        audit = get_audit_logger()
        audit.record(action="intelligence_memory_append", path=f"{request.project}:memory/project/intelligence/engineering-decisions.md", permission="LEVEL_1", approved=False, result="pending_approval", detail="Decision memory proposal queued; separate approval required", request_id=memory_request.request_id)
        result = decision.as_dict()
        result["memoryProposal"] = memory_request.as_dict()
        return result
    if request.action == "workflow_stage_approval":
        workflow, stage, approved_actions = workflow_manager.resolve_stage_approval(
            request.request_id, approved=True
        )
        executed: list[str] = []
        for bound_id in approved_actions:
            bound = approvals.get(bound_id)
            try:
                bound_result = _execute_action(
                    bound,
                    settings,
                    approvals=approvals,
                    workflow_manager=workflow_manager,
                )
            except BridgeError as exc:
                approvals.mark_failed(bound_id, exc.message)
                continue
            approvals.mark_executed(bound_id, bound_result)
            executed.append(bound_id)
        summary = stage_execution_summary(workflow, stage, True, approved_actions)
        summary["executedActions"] = executed
        return summary
    raise ApprovalError(f"Action '{request.action}' cannot be executed")


def _result_summary(action: str, result: dict[str, Any]) -> str:
    """Short, action-aware audit detail."""
    if action == "memory_decision":
        return f"ADR {result.get('id')} recorded"
    if action == "memory_append":
        return f"{result.get('appendedBytes', 0)} bytes appended to {result.get('document')}"
    if action == "memory_init":
        created = result.get("created") or []
        return f"{len(created)} document(s) created"
    if action == "workflow_stage_approval":
        return (
            f"Stage {result.get('stageType')} approved, "
            f"{result.get('size', 0)} bound action(s) auto-approved"
        )
    if action == "git_commit":
        return f"Committed {result.get('commit')} on {result.get('branch')}"
    if action == "test_run":
        return f"{result.get('command')}: {'passed' if result.get('passed') else 'failed'}"
    if action == "workflow_rollback":
        return f"Restored {result.get('count', 0)} action(s)"
    return f"{result.get('size', 0)} bytes written"


def _register_pending(
    *,
    action: str,
    project: str,
    path: str,
    payload: dict[str, Any],
    reason: str,
    preview_factory: Callable[[], str],
    settings: Settings,
    audit: AuditLogger,
    approvals: ApprovalStore,
    workflow_id: str | None = None,
    stage_id: str | None = None,
    session_id: str | None = None,
) -> JSONResponse:
    """Validate the request, create an approval entry and return 202."""
    level = level_for_action(action)
    display = relative_display(project, path)

    try:
        preview = preview_factory()
    except BridgeError as exc:
        audit.record(
            action=action,
            path=display,
            permission=level.value,
            approved=False,
            result="rejected",
            detail=exc.message,
        )
        raise

    decision = evaluate(action)
    request = approvals.create(
        action=action,
        project=project,
        path=path,
        payload=payload,
        reason=reason or decision.reason,
        preview=preview,
        workflow_id=workflow_id,
        stage_id=stage_id,
        session_id=session_id,
    )

    audit.record(
        action=action,
        path=display,
        permission=level.value,
        approved=False,
        result="pending_approval",
        detail=request.reason,
        request_id=request.request_id,
    )

    body = ApprovalPendingResponse(
        permissionLevel=level.value,
        risk=request.risk,
        reason=request.reason,
        status=request.status.value,
        requestId=request.request_id,
        action=action,
        project=project,
        path=path,
        preview=preview,
        createdAt=request.created_at,
        workflowId=request.workflow_id,
        stageId=request.stage_id,
    )
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=body.model_dump())


def create_app() -> FastAPI:
    app = FastAPI(
        title="ChatGPT Cursor Bridge - Local Bridge",
        version=SERVICE_VERSION,
        description="Secure local bridge with memory, workflow, Git, approved tests and rollback.",
    )

    # Phase 21: Engineering Governance Layer. Read-only health / drift / debt /
    # policy / timeline endpoints plus approval-gated governance writes and
    # Quality Gate 9.0. Nothing here executes actions.
    register_governance_routes(app)

    # Phase 27: Engineering Intelligence Validation Layer. Read-only accuracy /
    # effectiveness / decision outcomes / benchmarks / knowledge improvements
    # endpoints plus approval-gated measurement writes and Quality Gate 13.0.
    from app.intelligence.validation.routes import register_intelligence_validation_routes
    register_intelligence_validation_routes(app)

    # Phase 28: Engineering Intelligence Governance Layer. Read-only risk /
    # trends / policies / violations / reviews / quality-gate / graph endpoints
    # plus approval-gated governance evaluation and review writes and Quality
    # Gate 14.0. Nothing here executes, approves, or mutates governance rules.
    from app.intelligence.governance.routes import register_intelligence_governance_routes
    register_intelligence_governance_routes(app)

    # Phase 29: Advanced Developer Context & Read-only Code Intelligence.
    # Read-only project / file / symbol / dependency / git / test context
    # bundles with explicit budgets and security filtering. No execution,
    # no source mutation, no approval-gated writes.
    from app.context.dev.routes import register_dev_context_routes
    register_dev_context_routes(app)

    # Phase 30: Context Intelligence & Developer Workflow Preparation.
    # Read-only relevance ranking, budget 2.0, dedup, relationship / error /
    # test-failure / git-diff / code-review analysis and prompt-injection
    # protection. The only POST enqueues a record-only patch proposal.
    from app.context.dev.intelligence.routes import register_context_intelligence_routes
    register_context_intelligence_routes(app)
    from app.llm_gateway.routes import register_llm_gateway_routes
    register_llm_gateway_routes(app)

    # Phase 32: AI Assistant Productization. User/Developer mode surfaces,
    # encrypted provider credentials (AES-256-GCM, staged then human-approved),
    # explicit-consent web context and a read-only assistant chat. No execution,
    # no source modification, no auto-approval.
    from app.assistant.routes import register_assistant_routes
    register_assistant_routes(app)

    # Phase 22: Organization Engineering Intelligence. Read-only org graph /
    # cross-project learning / pattern library / command center endpoints plus
    # approval-gated org writes and Quality Gate 10.0.
    register_organization_routes(app)

    # Phase 23: Organization Graph Reasoning. Read-only ancestors / descendants /
    # owner / impact / context endpoints plus approval-gated graph sync and
    # checksummed snapshot create/restore.
    register_organization_graph_routes(app)

    # Phase 24: Organization Engineering Strategy. Read-only impact / risk /
    # strategy / decision / simulation / recommendations / context endpoints
    # plus approval-gated strategy, decision and memory writes.
    register_organization_strategy_routes(app)

    # Phase 25: Engineering Intelligence Evolution. All GET routes are
    # project-scoped/read-only; persistent intelligence writes are queued in
    # the same ApprovalStore used by existing execution paths.
    register_intelligence_evolution_routes(app)

    maintenance = MaintenanceService(
        get_settings(), get_approval_store(), get_audit_logger()
    )

    @app.middleware("http")
    async def maintenance_middleware(request: Request, call_next):
        maintenance.on_request()
        return await call_next(request)

    @app.on_event("startup")
    async def startup_maintenance() -> None:
        maintenance.startup()
        # Recovery only marks interrupted metadata as RECOVERED. It never
        # starts a task, approves a proposal, or invokes an executor.
        settings = get_settings()
        audit = get_audit_logger()
        events = EventBus(EventStorage(settings.event_root), audit)
        tasks = TaskManager(TaskStorage(settings.task_db_path), audit, events)
        scheduler = RuntimeScheduler(store=RuntimeStateStore(settings.runtime_root), tasks=tasks, audit=audit, events=events)
        RuntimeRecovery(scheduler, audit, events).recover()
        get_approval_store().recover_pending(audit)
        # Runtime Recovery 2.0: loops interrupted by a restart are marked
        # RECOVERED. No automatic continuation or approval.
        loop_orchestrator = ExecutionLoopOrchestrator(
            ExecutionLoopStorage(settings.execution_loop_db_path),
            settings,
            approvals=get_approval_store(),
            audit=audit,
        )
        ExecutionLoopRecovery(loop_orchestrator, audit).recover()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_origin_regex=r"^chrome-extension://[a-p]+$",
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.exception_handler(BridgeError)
    async def bridge_error_handler(_: Request, exc: BridgeError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.code, "message": exc.message},
        )

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    def health(settings: Settings = Depends(settings_dependency)) -> HealthResponse:
        return HealthResponse(
            service=SERVICE_NAME,
            version=SERVICE_VERSION,
            phase=SERVICE_PHASE,
            workspaceRoot=str(settings.workspace_root),
            logPath=str(settings.log_path),
            memoryRoot=str(settings.memory_root),
            workflowRoot=str(settings.workflow_root),
        )

    @app.get("/system/health", tags=["system"])
    def system_health() -> dict[str, Any]:
        payload = maintenance.health()
        payload["service"] = SERVICE_NAME
        payload["version"] = SERVICE_VERSION
        payload["phase"] = SYSTEM_PHASE
        payload["runtimePhase"] = "phase-8-persistent-agent-runtime"
        return payload

    @app.get("/dashboard", response_class=HTMLResponse, include_in_schema=True, tags=["dashboard"])
    def dashboard() -> HTMLResponse:
        return HTMLResponse(DASHBOARD_HTML)

    @app.get("/agent-profile/ranking", tags=["agent-profile"])
    def agent_profile_ranking(settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency)) -> dict[str, Any]:
        records = MetricsManager(settings.agent_root, audit).list(); manager = AgentProfileManager(AgentProfileStorage(settings.agent_profile_db_path))
        profiles = [manager.derive(record) for record in records]; profiles.sort(key=lambda profile: (profile.success_rate, profile.average_quality, -profile.rollback_rate), reverse=True)
        audit.record(action="agent_profile_ranking_read", path="agent-profile/ranking", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(profiles)} profile(s)")
        return {"profiles": [profile.as_dict() for profile in profiles], "readOnly": True}

    @app.get("/agent-profile/{agent_id}", tags=["agent-profile"])
    def agent_profile(agent_id: str, settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency)) -> dict[str, Any]:
        storage = AgentProfileStorage(settings.agent_profile_db_path); profile = storage.get(agent_id)
        if profile is None: profile = AgentProfileManager(storage).derive(MetricsManager(settings.agent_root, audit).get(agent_id))
        audit.record(action="agent_profile_read", path=f"agent-profile/{agent_id}", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success")
        return profile.as_dict()

    @app.get("/agent-profile/{agent_id}/history", tags=["agent-profile"])
    def agent_profile_history(agent_id: str, settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency)) -> dict[str, Any]:
        history = AgentProfileStorage(settings.agent_profile_db_path).history(agent_id)
        if not history: history = [agent_profile(agent_id, settings, audit)]
        return {"agentId": agent_id, "history": history, "readOnly": True}

    @app.get("/demo/catalog", tags=["demo"])
    def demo_catalog(audit: AuditLogger = Depends(audit_dependency)) -> dict[str, Any]:
        catalog = DemoScenarioManager(audit).catalog()
        audit.record(action="demo_catalog_read", path="demo/catalog", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(catalog)} scenario(s)")
        return {"scenarios": catalog, "readOnly": True}

    @app.get("/demo/flow", tags=["demo"])
    def demo_flow(audit: AuditLogger = Depends(audit_dependency)) -> dict[str, Any]:
        from app.demo import DEMO_FLOW
        audit.record(action="demo_flow_read", path="demo/flow", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(DEMO_FLOW)} stage(s)")
        return {"flow": DEMO_FLOW, "readOnly": True}

    @app.post("/demo/scenario", status_code=status.HTTP_202_ACCEPTED, tags=["demo"])
    def demo_scenario_create(body: DemoScenarioCreateRequest, settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency), approvals: ApprovalStore = Depends(approvals_dependency)) -> JSONResponse:
        return _register_pending(action="demo_scenario_create", project="demo", path="demo/scenario", payload={"name": body.name, "issue": body.issue}, reason=body.reason, preview_factory=lambda: f"CREATE record-only demo scenario '{body.name}'; no execution", settings=settings, audit=audit, approvals=approvals)

    @app.post("/replay/create", status_code=status.HTTP_202_ACCEPTED, tags=["replay"])
    def replay_create(body: ReplayCreateRequest, settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency), approvals: ApprovalStore = Depends(approvals_dependency)) -> JSONResponse:
        return _register_pending(action="replay_create", project=body.project, path="replay", payload={"title": body.title}, reason=body.reason, preview_factory=lambda: f"BUILD engineering replay for {body.project} from audit/events/validation records; no execution", settings=settings, audit=audit, approvals=approvals)

    @app.get("/replay/list", tags=["replay"])
    def replay_list(project: str | None = Query(default=None, max_length=100), settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency)) -> dict[str, Any]:
        records = ReplayStorage(settings.workspace_root.parent / "replay" / "replay.db").list(project)
        audit.record(action="replay_list_read", path=project or "*", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(records)} replay(s)")
        return {"replays": records, "readOnly": True}

    @app.get("/replay/{replay_id}", tags=["replay"])
    def replay_detail(replay_id: str, settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency)) -> dict[str, Any]:
        record = ReplayStorage(settings.workspace_root.parent / "replay" / "replay.db").get(replay_id)
        if record is None: raise ResourceNotFound(f"Replay '{replay_id}' was not found")
        audit.record(action="replay_read", path=f"replay/{replay_id}", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(record['steps'])} step(s)")
        return record

    @app.post("/artifacts/export", status_code=status.HTTP_202_ACCEPTED, tags=["artifacts"])
    def artifact_export(body: ExportCreateRequest, settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency), approvals: ApprovalStore = Depends(approvals_dependency)) -> JSONResponse:
        return _register_pending(action="artifact_export", project=body.project, path="artifacts", payload={"kind": body.kind, "payload": body.payload, "markdown": body.markdown}, reason=body.reason, preview_factory=lambda: f"EXPORT read-only {body.kind} artifact for {body.project}", settings=settings, audit=audit, approvals=approvals)

    @app.get("/artifacts", tags=["artifacts"])
    def artifact_list(project: str | None = Query(default=None, max_length=100), settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency)) -> dict[str, Any]:
        records = ArtifactExporter(settings.workspace_root.parent / "artifacts", audit).list(project)
        audit.record(action="artifact_list_read", path=project or "*", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(records)} artifact(s)")
        return {"artifacts": records, "readOnly": True}

    @app.get("/models", tags=["models"])
    def models(audit: AuditLogger = Depends(audit_dependency)) -> dict[str, Any]:
        local_models = ModelRouter().descriptors(); adapters = ProviderCapabilityRegistry().all()
        audit.record(action="models_read", path="models", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(local_models) + len(adapters)} model(s)")
        return {"models": local_models + adapters, "readOnly": True}

    @app.get("/models/capabilities", tags=["models"])
    def model_capabilities(model: str | None = Query(default=None, max_length=200), audit: AuditLogger = Depends(audit_dependency)) -> dict[str, Any]:
        result = ProviderCapabilityRegistry().capabilities(model)
        audit.record(action="model_capabilities_read", path="models/capabilities", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(result)} model(s)")
        return {"capabilities": result, "readOnly": True}

    @app.get("/context/project", tags=["context"])
    def project_context(
        project: str = Query(..., min_length=1, max_length=100),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
        workflow_manager: WorkflowManager = Depends(workflow_manager_dependency),
    ) -> dict[str, Any]:
        payload = ProjectContextService(
            settings=settings,
            workflow_manager=workflow_manager,
            approvals=approvals,
            audit=audit,
        ).build(project)
        audit.record(
            action="context_project",
            path=f"{project}:context",
            permission=PermissionLevel.LEVEL_0.value,
            approved=True,
            result="success",
            detail="Project context read and snapshot refreshed",
        )
        return payload

    @app.get("/context/search", tags=["context"])
    def context_search(
        q: str = Query(default="", max_length=300),
        project: str | None = Query(default=None, min_length=1, max_length=100),
        date_from: str | None = Query(default=None, alias="from", max_length=40),
        date_to: str | None = Query(default=None, alias="to", max_length=40),
        limit: int = Query(default=50, ge=1, le=200),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        results = ContextIndex(settings.context_index_db_path).search(
            q, project=project, date_from=date_from, date_to=date_to, limit=limit
        )
        audit.record(
            action="context_search",
            path=project or "*",
            permission=PermissionLevel.LEVEL_0.value,
            approved=True,
            result="success",
            detail=f"{len(results)} indexed result(s)",
        )
        return {
            "query": q,
            "project": project,
            "from": date_from,
            "to": date_to,
            "results": [result.as_dict() for result in results],
        }

    @app.get("/model-router/capabilities", tags=["model-router"])
    def model_capabilities(
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        router = ModelRouter()
        models = router.descriptors()
        audit.record(
            action="model_route",
            path="model-router/capabilities",
            permission=PermissionLevel.LEVEL_0.value,
            approved=True,
            result="success",
            detail=f"{len(models)} registered model(s)",
        )
        return {"models": models}

    @app.get("/model-router/route", tags=["model-router"])
    def model_route(
        task: str = Query(..., min_length=1, max_length=4000),
        task_type: str | None = Query(default=None, max_length=32),
        preferred_model: str | None = Query(default=None, max_length=100),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        route = ModelRouter().route(task, task_type=task_type, preferred_model=preferred_model)
        audit.record(
            action="model_route",
            path="model-router/route",
            permission=PermissionLevel.LEVEL_0.value,
            approved=True,
            result="success",
            detail=f"{route.classification.task_type.value} -> {route.model.id}",
        )
        return route.as_dict()

    @app.get("/agent/status", tags=["agent"])
    def agent_status(
        project: str | None = Query(default=None, min_length=1, max_length=100),
        task: str | None = Query(default=None, max_length=4000),
        manager: AgentManager = Depends(agent_manager_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        agents = [agent.as_dict() for agent in manager.list(project)]
        route = ModelRouter().route(task or "coding task") if task else None
        audit.record(
            action="agent_status",
            path=project or "*",
            permission=PermissionLevel.LEVEL_0.value,
            approved=True,
            result="success",
            detail=f"{len(agents)} agent(s)",
        )
        return {
            "agents": agents,
            "messages": manager.messages(project=project, limit=50),
            "models": manager.router.descriptors(),
            "selectedModel": route.as_dict() if route else None,
        }

    # ---- Phase 10 runtime, events and task queue -----------------------

    @app.get("/runtime/status", tags=["runtime"])
    def runtime_status(
        scheduler: RuntimeScheduler = Depends(runtime_scheduler_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        runtimes = [runtime.as_dict() for runtime in scheduler.list()]
        proposals = [proposal.as_dict() for runtime in scheduler.list() for proposal in scheduler.proposals(runtime.id)]
        audit.record(action="runtime_status", path="runtime", permission="LEVEL_0", approved=True, result="success", detail=f"{len(runtimes)} runtime(s), {len(proposals)} proposal(s)")
        return {"runtimes": runtimes, "proposals": proposals, "states": [state.value for state in __import__("app.runtime.models", fromlist=["RuntimeState"]).RuntimeState]}

    @app.get("/runtime/events", tags=["runtime"])
    def runtime_events(
        limit: int = Query(default=100, ge=1, le=500),
        events: EventBus = Depends(event_bus_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        records = [event.as_dict() for event in events.list_events(limit)]
        audit.record(action="runtime_events", path="events", permission="LEVEL_0", approved=True, result="success", detail=f"{len(records)} event(s)")
        return {"events": records}

    @app.post("/runtime/create", status_code=status.HTTP_202_ACCEPTED, tags=["runtime"])
    def runtime_create(
        body: RuntimeCreateRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
    ) -> JSONResponse:
        return _register_pending(
            action="runtime_create", project="runtime", path=f"runtime/{body.agent_id}",
            payload={"agent_id": body.agent_id, "session_id": body.session_id, "workflow_id": body.workflow_id, "stage_id": body.stage_id},
            reason=body.reason, preview_factory=lambda: "CREATE runtime metadata; scheduler remains proposal-only",
            settings=settings, audit=audit, approvals=approvals,
            workflow_id=body.workflow_id, stage_id=body.stage_id, session_id=body.session_id,
        )

    @app.get("/agent/runtime", tags=["agent"])
    def agent_runtime(
        scheduler: RuntimeScheduler = Depends(runtime_scheduler_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        records = [runtime.as_dict() for runtime in scheduler.list()]
        audit.record(action="agent_runtime_status", path="agent/runtime", permission="LEVEL_0", approved=True, result="success", detail=f"{len(records)} runtime(s)")
        return {"runtimes": records}

    @app.get("/agent/{agent_id}/state", tags=["agent"])
    def agent_runtime_state(
        agent_id: str,
        scheduler: RuntimeScheduler = Depends(runtime_scheduler_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        records = [runtime.as_dict() for runtime in scheduler.list() if runtime.agent_id == agent_id]
        audit.record(action="agent_runtime_state", path=f"agent/{agent_id}", permission="LEVEL_0", approved=True, result="success", detail=f"{len(records)} runtime(s)")
        return {"agentId": agent_id, "runtimes": records}

    @app.get("/task/list", tags=["task"])
    def task_list(
        task_status: str | None = Query(default=None, alias="status", max_length=32),
        limit: int = Query(default=100, ge=1, le=500),
        manager: TaskManager = Depends(task_manager_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        try:
            parsed = TaskStatus(task_status.upper()) if task_status else None
        except ValueError as exc:
            raise ValidationFailed("Unknown task status") from exc
        tasks = [task.as_dict() for task in manager.list_tasks(status=parsed, limit=limit)]
        audit.record(action="task_list", path="tasks", permission="LEVEL_0", approved=True, result="success", detail=f"{len(tasks)} task(s)")
        return {"tasks": tasks}

    @app.post("/task/create", status_code=status.HTTP_202_ACCEPTED, tags=["task"])
    def task_create(
        body: TaskCreateRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
    ) -> JSONResponse:
        return _register_pending(
            action="task_create", project="task", path=f"workflow/{body.workflow_id}#{body.stage_id}",
            payload={"workflow_id": body.workflow_id, "stage_id": body.stage_id, "agent_id": body.agent_id, "priority": body.priority, "context": body.context},
            reason=body.reason, preview_factory=lambda: "CREATE PENDING task metadata; no agent execution",
            settings=settings, audit=audit, approvals=approvals, workflow_id=body.workflow_id, stage_id=body.stage_id,
        )

    @app.post("/task/{task_id}/transition", status_code=status.HTTP_202_ACCEPTED, tags=["task"])
    def task_transition(
        task_id: str,
        body: TaskTransitionRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
        manager: TaskManager = Depends(task_manager_dependency),
    ) -> JSONResponse:
        task = manager.get_task(task_id)
        return _register_pending(
            action="task_transition", project="task", path=f"task/{task_id}",
            payload={"task_id": task_id, "status": body.status},
            reason=body.reason, preview_factory=lambda: f"{task.status.value} → {body.status.upper()} (metadata only)",
            settings=settings, audit=audit, approvals=approvals,
            workflow_id=task.workflow_id, stage_id=task.stage_id,
        )

    @app.get("/task/{task_id}/dependencies", tags=["task"])
    def task_dependencies(task_id: str, settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency)) -> dict[str, Any]:
        graph = TaskDependencyGraph(settings.workspace_root.parent / "tasks" / "dependencies.jsonl", audit)
        payload = graph.as_dict(task_id)
        audit.record(action="task_dependencies_read", path=f"task/{task_id}/dependencies", permission="LEVEL_0", approved=True, result="success", detail=f"{len(payload['dependencies'])} edge(s)")
        return payload

    @app.get("/task/{task_id}", tags=["task"])
    def task_detail(task_id: str, manager: TaskManager = Depends(task_manager_dependency), audit: AuditLogger = Depends(audit_dependency)) -> dict[str, Any]:
        task = manager.get_task(task_id)
        audit.record(action="task_read", path=f"task/{task_id}", permission="LEVEL_0", approved=True, result="success")
        return task.as_dict()

    @app.get("/quality/{workflow_id}", tags=["quality"])
    def quality_report(workflow_id: str, audit: AuditLogger = Depends(audit_dependency)) -> dict[str, Any]:
        report = QualityEvaluator().evaluate()
        multi = MultiAgentQualityEvaluator().evaluate()
        intelligence = QualityGate4Evaluator().evaluate()
        audit.record(action="quality_read", path=f"quality/{workflow_id}", permission="LEVEL_0", approved=True, result="success", detail=f"score={report.quality_score}")
        return {"workflowId": workflow_id, **report.as_dict(), **multi.as_dict(), **intelligence}

    @app.post("/team/create", status_code=status.HTTP_202_ACCEPTED, tags=["team"])
    def team_create(body: TeamCreateRequest, settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency), approvals: ApprovalStore = Depends(approvals_dependency)) -> JSONResponse:
        members = list(dict.fromkeys(member.strip() for member in body.members))
        if any(not member.startswith("ag_") for member in members) or body.leader not in members:
            raise ValidationFailed("Team members and leader must be valid agent ids")
        return _register_pending(action="team_create", project="collaboration", path=f"workflow/{body.workflow_id}/team", payload={"workflow_id": body.workflow_id, "members": members, "leader": body.leader}, reason=body.reason, preview_factory=lambda: f"CREATE team for workflow {body.workflow_id} with {len(members)} scoped agents; no execution", settings=settings, audit=audit, approvals=approvals, workflow_id=body.workflow_id)

    @app.get("/team/list", tags=["team"])
    def team_list(workflow_id: str | None = Query(default=None, max_length=64), settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency)) -> dict[str, Any]:
        teams = AgentCoordinator(CollaborationStorage(settings.workspace_root.parent / "collaboration"), audit).list(workflow_id)
        audit.record(action="team_list", path="team", permission="LEVEL_0", approved=True, result="success", detail=f"{len(teams)} team(s)")
        return {"teams": [team.as_dict() for team in teams]}

    @app.get("/team/{team_id}", tags=["team"])
    def team_detail(team_id: str, settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency)) -> dict[str, Any]:
        team = AgentCoordinator(CollaborationStorage(settings.workspace_root.parent / "collaboration"), audit).get(team_id)
        audit.record(action="team_read", path=f"team/{team_id}", permission="LEVEL_0", approved=True, result="success")
        return team.as_dict()

    @app.get("/collaboration/events", tags=["collaboration"])
    def collaboration_events(limit: int = Query(default=100, ge=1, le=500), settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency)) -> dict[str, Any]:
        storage = CollaborationStorage(settings.workspace_root.parent / "collaboration")
        records = CollaborationCommunication(storage, audit).list(limit)
        audit.record(action="collaboration_events_read", path="collaboration/events", permission="LEVEL_0", approved=True, result="success", detail=f"{len(records)} event(s)")
        return {"events": records}

    @app.get("/conflict/{conflict_id}", tags=["collaboration"])
    def conflict_detail(conflict_id: str, settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency)) -> dict[str, Any]:
        conflict = ConflictManager(CollaborationStorage(settings.workspace_root.parent / "collaboration"), audit).get(conflict_id)
        audit.record(action="conflict_read", path=f"conflict/{conflict_id}", permission="LEVEL_0", approved=True, result="success")
        return conflict.as_dict()

    @app.get("/agent/{agent_id}/metrics", tags=["metrics"])
    def agent_metrics(agent_id: str, settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency)) -> dict[str, Any]:
        metrics = MetricsManager(settings.workspace_root.parent / "metrics", audit).get(agent_id)
        audit.record(action="agent_metrics_read", path=f"agent/{agent_id}/metrics", permission="LEVEL_0", approved=True, result="success")
        return metrics.as_dict()

    @app.get("/context/bundle", tags=["context"])
    def context_bundle(
        project: str = Query(..., min_length=1, max_length=100),
        agent_role: str = Query(default="CODER", max_length=32),
        task: str = Query(default="", max_length=4000),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        bundle = ContextRouter(settings).route(project=project, agent_role=agent_role, current_task=task)
        audit.record(action="context_bundle", path=f"{project}:context", permission="LEVEL_0", approved=True, result="success", detail="Read-only agent context bundle")
        return bundle

    # ---- Engineering Decision Intelligence (Phase 13) -----------------

    @app.get("/intelligence/insights", tags=["intelligence"])
    def intelligence_insights(
        project: str | None = Query(default=None, max_length=100),
        insight_type: str | None = Query(default=None, max_length=40),
        limit: int = Query(default=100, ge=1, le=500),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        records = IntelligenceStorage(settings.intelligence_db_path).list_insights(project, insight_type, limit)
        audit.record(action="intelligence_insights_read", path=project or "*", permission="LEVEL_0", approved=True, result="success", detail=f"{len(records)} insight(s)")
        return {"project": project, "insights": [item.as_dict() for item in records], "readOnly": True}

    @app.post("/intelligence/analyze", status_code=status.HTTP_202_ACCEPTED, tags=["intelligence"])
    def intelligence_analyze(
        body: IntelligenceAnalyzeRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
    ) -> JSONResponse:
        stats = CodeIndex(settings.code_index_db_path).stats(body.project)
        return _register_pending(
            action="intelligence_analyze",
            project=body.project,
            path="intelligence/insights",
            payload={"changed_files": body.changed_files, "test_coverage": body.test_coverage, "security_sensitive": body.security_sensitive},
            reason=body.reason,
            preview_factory=lambda: f"Analyze {stats['files']} indexed files and {stats['dependencies']} dependencies; persist insights/proposals only",
            settings=settings, audit=audit, approvals=approvals,
        )

    @app.get("/intelligence/proposals", tags=["intelligence"])
    def intelligence_proposals(
        project: str | None = Query(default=None, max_length=100),
        proposal_status: str | None = Query(default=None, alias="status", max_length=20),
        limit: int = Query(default=100, ge=1, le=500),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        records = IntelligenceStorage(settings.intelligence_db_path).list_proposals(project, proposal_status, limit)
        audit.record(action="intelligence_proposals_read", path=project or "*", permission="LEVEL_0", approved=True, result="success", detail=f"{len(records)} proposal(s)")
        return {"project": project, "proposals": [item.as_dict() for item in records], "readOnly": True}

    @app.get("/intelligence/decisions", tags=["intelligence"])
    def intelligence_decisions(
        project: str | None = Query(default=None, max_length=100),
        decision_status: str | None = Query(default=None, alias="status", max_length=20),
        limit: int = Query(default=100, ge=1, le=500),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        records = IntelligenceStorage(settings.intelligence_db_path).list_decisions(project, decision_status, limit)
        audit.record(action="intelligence_decisions_read", path=project or "*", permission="LEVEL_0", approved=True, result="success", detail=f"{len(records)} decision(s)")
        return {"project": project, "decisions": [item.as_dict() for item in records], "readOnly": True}

    @app.get("/intelligence/decision/{decision_id}", tags=["intelligence"])
    def intelligence_decision(decision_id: str, settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency)) -> dict[str, Any]:
        decision = IntelligenceStorage(settings.intelligence_db_path).get_decision(decision_id)
        if decision is None:
            from app.security.validator import ResourceNotFound
            raise ResourceNotFound(f"Decision '{decision_id}' was not found")
        audit.record(action="intelligence_decision_read", path=f"intelligence/decision/{decision_id}", permission="LEVEL_0", approved=True, result="success")
        return {**decision.as_dict(), "readOnly": True}

    @app.post("/intelligence/decision/create", status_code=status.HTTP_202_ACCEPTED, tags=["intelligence"])
    def intelligence_decision_create(
        body: IntelligenceDecisionCreateRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
    ) -> JSONResponse:
        storage = IntelligenceStorage(settings.intelligence_db_path)
        proposal = storage.get_proposal(body.proposal_id)
        if proposal is None or proposal.project != body.project:
            raise ValidationFailed("Proposal was not found for this project")
        return _register_pending(
            action="intelligence_decision_create",
            project=body.project,
            path=f"intelligence/decision/{body.proposal_id}",
            payload={"proposal_id": body.proposal_id, "title": body.title, "context": body.context, "options": body.options, "recommendation": body.recommendation, "simulation_id": body.simulation_id, "selected_scenario": body.selected_scenario, "confidence": body.confidence, "alternatives": body.alternatives, "implementation_plan_id": body.implementation_plan_id, "execution_status": body.execution_status},
            reason=body.reason,
            preview_factory=lambda: f"CREATE decision metadata for proposal {body.proposal_id}; no code or memory write",
            settings=settings, audit=audit, approvals=approvals,
        )

    @app.get("/quality/v5/{workflow_id}", tags=["quality"])
    def quality_gate_v5(
        workflow_id: str,
        architecture_score: int = Query(default=100, ge=0, le=100),
        maintainability_score: int = Query(default=100, ge=0, le=100),
        risk_score: int = Query(default=0, ge=0, le=100),
        decision_confidence: int = Query(default=100, ge=0, le=100),
        technical_debt: int = Query(default=0, ge=0, le=100),
        technical_debt_items: int = Query(default=0, ge=0, le=10000),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        report = QualityGate5Evaluator().evaluate(architecture_score=architecture_score, maintainability_score=maintainability_score, risk_score=risk_score, decision_confidence=decision_confidence, technical_debt=technical_debt, technical_debt_items=technical_debt_items)
        audit.record(action="quality_gate_v5_read", path=f"quality/v5/{workflow_id}", permission="LEVEL_0", approved=True, result="success", detail=f"quality={report['quality']}")
        return {"workflowId": workflow_id, **report}

    # ---- Engineering Simulation and Planning (Phase 14) ----------------

    @app.post("/simulation/create", status_code=status.HTTP_202_ACCEPTED, tags=["simulation"])
    def simulation_create(body: SimulationCreateRequest, settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency), approvals: ApprovalStore = Depends(approvals_dependency)) -> JSONResponse:
        return _register_pending(action="simulation_create", project=body.project, path="simulation", payload={"problem": body.problem}, reason=body.reason, preview_factory=lambda: f"CREATE simulation metadata for {body.project}; no source modification", settings=settings, audit=audit, approvals=approvals)

    @app.post("/simulation/{simulation_id}/analyze", status_code=status.HTTP_202_ACCEPTED, tags=["simulation"])
    def simulation_analyze(simulation_id: str, body: SimulationAnalyzeRequest, settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency), approvals: ApprovalStore = Depends(approvals_dependency)) -> JSONResponse:
        simulation = SimulationStorage(settings.simulation_db_path).get_simulation(simulation_id)
        if simulation is None: raise ResourceNotFound(f"Simulation '{simulation_id}' was not found")
        return _register_pending(action="simulation_analyze", project=simulation.project, path=f"simulation/{simulation_id}/scenarios", payload={"simulation_id": simulation_id, "test_coverage": body.test_coverage, "proposal_id": body.proposal_id}, reason=body.reason, preview_factory=lambda: "GENERATE candidate scenarios and impact metadata; no source modification", settings=settings, audit=audit, approvals=approvals)

    @app.get("/simulation/{simulation_id}", tags=["simulation"])
    def simulation_detail(simulation_id: str, settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency)) -> dict[str, Any]:
        storage = SimulationStorage(settings.simulation_db_path); simulation = storage.get_simulation(simulation_id)
        if simulation is None: raise ResourceNotFound(f"Simulation '{simulation_id}' was not found")
        audit.record(action="simulation_read", path=f"simulation/{simulation_id}", permission="LEVEL_0", approved=True, result="success")
        return {**simulation.as_dict(), "plans": [item.as_dict() for item in storage.list_plans(simulation_id)]}

    @app.get("/simulation/{simulation_id}/scenarios", tags=["simulation"])
    def simulation_scenarios(simulation_id: str, settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency)) -> dict[str, Any]:
        storage = SimulationStorage(settings.simulation_db_path)
        if storage.get_simulation(simulation_id) is None: raise ResourceNotFound(f"Simulation '{simulation_id}' was not found")
        scenarios = storage.list_scenarios(simulation_id)
        audit.record(action="simulation_scenarios_read", path=f"simulation/{simulation_id}/scenarios", permission="LEVEL_0", approved=True, result="success", detail=f"{len(scenarios)} scenario(s)")
        return {"simulationId": simulation_id, "scenarios": [item.as_dict() for item in scenarios], "readOnly": True}

    @app.get("/simulation/{simulation_id}/evaluation", tags=["simulation"])
    def simulation_evaluation(simulation_id: str, settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency)) -> dict[str, Any]:
        storage = SimulationStorage(settings.simulation_db_path)
        if storage.get_simulation(simulation_id) is None: raise ResourceNotFound(f"Simulation '{simulation_id}' was not found")
        evaluations = [evaluation.as_dict() for scenario in storage.list_scenarios(simulation_id) if (evaluation := storage.get_evaluation(scenario.id))]
        audit.record(action="simulation_evaluation_read", path=f"simulation/{simulation_id}/evaluation", permission="LEVEL_0", approved=True, result="success", detail=f"{len(evaluations)} evaluation(s)")
        return {"simulationId": simulation_id, "evaluations": evaluations, "readOnly": True}

    @app.post("/simulation/{simulation_id}/plan", status_code=status.HTTP_202_ACCEPTED, tags=["simulation"])
    def simulation_plan(simulation_id: str, body: SimulationPlanRequest, settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency), approvals: ApprovalStore = Depends(approvals_dependency)) -> JSONResponse:
        storage = SimulationStorage(settings.simulation_db_path); simulation = storage.get_simulation(simulation_id); scenario = storage.get_scenario(body.scenario_id)
        if simulation is None: raise ResourceNotFound(f"Simulation '{simulation_id}' was not found")
        if scenario is None: raise ResourceNotFound(f"Scenario '{body.scenario_id}' was not found")
        if scenario.simulation_id != simulation_id: raise ValidationFailed("Scenario does not belong to simulation")
        return _register_pending(action="simulation_plan", project=simulation.project, path=f"simulation/{simulation_id}/plan", payload={"simulation_id": simulation_id, "scenario_id": body.scenario_id}, reason=body.reason, preview_factory=lambda: f"GENERATE plan for {scenario.name}; plan remains metadata and memory proposal", settings=settings, audit=audit, approvals=approvals)

    @app.get("/quality/v6/{workflow_id}", tags=["quality"])
    def quality_gate_v6(workflow_id: str, simulation_confidence: float = Query(default=0.0, ge=0, le=1), alternative_coverage: int = Query(default=0, ge=0, le=100), risk_prediction_accuracy: int = Query(default=0, ge=0, le=100), plan_completeness: int = Query(default=0, ge=0, le=100), missing_information: list[str] = Query(default=[], max_length=50), audit: AuditLogger = Depends(audit_dependency)) -> dict[str, Any]:
        report = QualityGate6Evaluator().evaluate(simulation_confidence=simulation_confidence, alternative_coverage=alternative_coverage, risk_prediction_accuracy=risk_prediction_accuracy, plan_completeness=plan_completeness, missing_information=missing_information)
        audit.record(action="quality_gate_v6_read", path=f"quality/v6/{workflow_id}", permission="LEVEL_0", approved=True, result="success", detail=f"quality={report['quality']}")
        return {"workflowId": workflow_id, **report}

    # ---- Autonomous Engineering Loop (Phase 16) ------------------------

    def execution_loop_manager_dependency(
        settings: Settings = Depends(settings_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> ExecutionLoopOrchestrator:
        return ExecutionLoopOrchestrator(
            ExecutionLoopStorage(settings.execution_loop_db_path),
            settings,
            approvals=approvals,
            audit=audit,
        )

    def execution_dag_manager_dependency(
        settings: Settings = Depends(settings_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> ExecutionDagManager:
        orchestrator = ExecutionLoopOrchestrator(
            ExecutionLoopStorage(settings.execution_loop_db_path),
            settings,
            approvals=approvals,
            audit=audit,
        )
        return ExecutionDagManager(
            ExecutionDagStorage(settings.execution_dag_db_path),
            orchestrator,
            audit=audit,
        )

    @app.post("/validation/create", status_code=status.HTTP_202_ACCEPTED, tags=["validation"])
    def validation_create(body: ValidationCreateRequest, settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency), approvals: ApprovalStore = Depends(approvals_dependency)) -> JSONResponse:
        return _register_pending(
            action="validation_create", project=body.project, path="validation",
            payload={"repository": body.repository, "language": body.language, "framework": body.framework, "scenarios": body.scenarios}, reason=body.reason,
            preview_factory=lambda: f"CREATE record-only validation for {body.project} with {len(body.scenarios)} scenario(s); no task execution",
            settings=settings, audit=audit, approvals=approvals,
        )

    @app.get("/validation/reference", tags=["validation"])
    def validation_reference(settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency)) -> dict[str, Any]:
        flows = ValidationManager(ValidationStorage(settings.workspace_root.parent / "validation" / "validation.db"), audit).reference_flows()
        audit.record(action="validation_reference_read", path="validation/reference", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(flows['cases'])} case(s)")
        return flows

    @app.get("/validation/list", tags=["validation"])
    def validation_list(project: str | None = Query(default=None, max_length=100), settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency)) -> dict[str, Any]:
        records = ValidationStorage(settings.workspace_root.parent / "validation" / "validation.db").list(project)
        audit.record(action="validation_list_read", path=project or "*", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(records)} validation(s)")
        return {"validations": [record.as_dict() for record in records], "readOnly": True}

    @app.get("/validation/{validation_id}", tags=["validation"])
    def validation_detail(validation_id: str, settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency)) -> dict[str, Any]:
        storage = ValidationStorage(settings.workspace_root.parent / "validation" / "validation.db"); record = storage.get(validation_id)
        if record is None: raise ResourceNotFound(f"Validation '{validation_id}' was not found")
        payload = record.as_dict(); payload["scenarios"] = [scenario.as_dict() for scenario in storage.scenarios(validation_id)]; payload["runs"] = [run.as_dict() for scenario in storage.scenarios(validation_id) for run in storage.runs(scenario.id)]
        audit.record(action="validation_read", path=f"validation/{validation_id}", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success")
        return payload

    @app.post("/validation/{validation_id}/transition", status_code=status.HTTP_202_ACCEPTED, tags=["validation"])
    def validation_transition(validation_id: str, body: ValidationTransitionRequest, settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency), approvals: ApprovalStore = Depends(approvals_dependency)) -> JSONResponse:
        storage = ValidationStorage(settings.workspace_root.parent / "validation" / "validation.db"); record = storage.get(validation_id)
        if record is None: raise ResourceNotFound(f"Validation '{validation_id}' was not found")
        return _register_pending(action="validation_transition", project=record.project, path=f"validation/{validation_id}", payload={"validation_id": validation_id, "status": body.status}, reason=body.reason, preview_factory=lambda: f"UPDATE validation metadata {validation_id}: {record.status.value} -> {body.status}; no task execution", settings=settings, audit=audit, approvals=approvals)

    @app.post("/validation/run", status_code=status.HTTP_202_ACCEPTED, tags=["validation"])
    def validation_run(body: ValidationRunRequest, settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency), approvals: ApprovalStore = Depends(approvals_dependency)) -> JSONResponse:
        return _register_pending(action="validation_run_record", project="validation", path=f"validation/run/{body.scenario_id}", payload={"scenario_id": body.scenario_id, "workflow_id": body.workflow_id, "execution_loop_id": body.execution_loop_id, "agents": body.agents, "result": body.result, "human_rating": body.human_rating}, reason=body.reason, preview_factory=lambda: f"RECORD validation run metadata for scenario {body.scenario_id}; no task execution", settings=settings, audit=audit, approvals=approvals)

    @app.get("/reporting/generate", tags=["reporting"])
    def reporting_generate(project: str = Query(..., min_length=1, max_length=100), settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency), approvals: ApprovalStore = Depends(approvals_dependency), workflow_manager: WorkflowManager = Depends(workflow_manager_dependency)) -> dict[str, Any]:
        insights = IntelligenceStorage(settings.intelligence_db_path).list_insights(project)
        proposals = IntelligenceStorage(settings.intelligence_db_path).list_proposals(project)
        decisions = IntelligenceStorage(settings.intelligence_db_path).list_decisions(project)
        loops = ExecutionLoopStorage(settings.execution_loop_db_path).list_loops(project=project)
        results = ExecutionManager(ExecutionStorage(settings.execution_db_path), settings, approvals=approvals, workflow_manager=workflow_manager).list_results(project=project)
        failures = FailureIntelligenceAnalyzer().analyze(project, loops=[loop.as_dict() for loop in loops], results=[result.as_dict() for result in results])
        learning = EvolutionTimeline(settings.memory_root / "evolution").list(project)
        report = EngineeringReportGenerator().generate(project, insights=insights, proposals=proposals, decisions=decisions, loops=[loop.as_dict() for loop in loops], verifications=[result.as_dict() for result in results], failures=[pattern.as_dict() for pattern in failures], learning=learning)
        audit.record(action="reporting_generate_read", path=f"{project}:reporting", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail="Engineering report generated (read-only)")
        return report.as_dict()

    @app.get("/production/readiness", tags=["system"])
    def production_readiness(settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency)) -> dict[str, Any]:
        payload = ProductionReadiness(settings).summary()
        audit.record(action="production_readiness", path="production/readiness", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail="Read-only production readiness check")
        return payload

    @app.post("/benchmark/create", status_code=status.HTTP_202_ACCEPTED, tags=["benchmark"])
    def benchmark_create(body: BenchmarkCreateRequest, settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency), approvals: ApprovalStore = Depends(approvals_dependency)) -> JSONResponse:
        return _register_pending(
            action="benchmark_create", project=body.project, path="benchmark",
            payload={"repository": body.repository, "cases": body.cases}, reason=body.reason,
            preview_factory=lambda: f"CREATE record-only benchmark for {body.project} with {len(body.cases)} case(s); no task execution",
            settings=settings, audit=audit, approvals=approvals,
        )

    @app.get("/benchmark/list", tags=["benchmark"])
    def benchmark_list(project: str | None = Query(default=None, max_length=100), settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency)) -> dict[str, Any]:
        records = BenchmarkStorage(settings.workspace_root.parent / "benchmarks" / "benchmark.db").list(project)
        audit.record(action="benchmark_list_read", path=project or "*", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(records)} benchmark(s)")
        return {"benchmarks": [record.as_dict() for record in records], "readOnly": True}

    @app.get("/benchmark/{benchmark_id}/results", tags=["benchmark"])
    def benchmark_results(benchmark_id: str, settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency)) -> dict[str, Any]:
        storage = BenchmarkStorage(settings.workspace_root.parent / "benchmarks" / "benchmark.db")
        if storage.get(benchmark_id) is None: raise ResourceNotFound(f"Benchmark '{benchmark_id}' was not found")
        results = storage.results(benchmark_id)
        audit.record(action="benchmark_results_read", path=f"benchmark/{benchmark_id}/results", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(results)} result(s)")
        return {"benchmarkId": benchmark_id, "results": [result.as_dict() for result in results], "readOnly": True}

    @app.get("/benchmark/{benchmark_id}", tags=["benchmark"])
    def benchmark_detail(benchmark_id: str, settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency)) -> dict[str, Any]:
        storage = BenchmarkStorage(settings.workspace_root.parent / "benchmarks" / "benchmark.db"); record = storage.get(benchmark_id)
        if record is None: raise ResourceNotFound(f"Benchmark '{benchmark_id}' was not found")
        payload = record.as_dict(); payload["cases"] = [case.as_dict() for case in storage.cases(benchmark_id)]
        audit.record(action="benchmark_read", path=f"benchmark/{benchmark_id}", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success")
        return payload

    @app.post("/benchmark/{benchmark_id}/transition", status_code=status.HTTP_202_ACCEPTED, tags=["benchmark"])
    def benchmark_transition(benchmark_id: str, body: BenchmarkTransitionRequest, settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency), approvals: ApprovalStore = Depends(approvals_dependency)) -> JSONResponse:
        storage = BenchmarkStorage(settings.workspace_root.parent / "benchmarks" / "benchmark.db"); record = storage.get(benchmark_id)
        if record is None: raise ResourceNotFound(f"Benchmark '{benchmark_id}' was not found")
        return _register_pending(action="benchmark_transition", project=record.project, path=f"benchmark/{benchmark_id}", payload={"benchmark_id": benchmark_id, "status": body.status}, reason=body.reason, preview_factory=lambda: f"UPDATE benchmark metadata {benchmark_id}: {record.status.value} -> {body.status}; no task execution", settings=settings, audit=audit, approvals=approvals)

    @app.post("/engineering-graph/rebuild", status_code=status.HTTP_202_ACCEPTED, tags=["engineering-graph"])
    def engineering_graph_rebuild(body: EngineeringGraphBuildRequest, settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency), approvals: ApprovalStore = Depends(approvals_dependency)) -> JSONResponse:
        return _register_pending(
            action="engineering_graph_rebuild", project=body.project, path="engineering-graph",
            payload={"project": body.project}, reason=body.reason,
            preview_factory=lambda: f"REBUILD read-only engineering graph for {body.project}; no source modification",
            settings=settings, audit=audit, approvals=approvals,
        )

    @app.get("/engineering-graph", tags=["engineering-graph"])
    def engineering_graph_root(project: str | None = Query(default=None, min_length=1, max_length=100), settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency)) -> dict[str, Any]:
        selected = project or "*"
        graph = EngineeringGraphManager(EngineeringGraphStorage(settings.workspace_root.parent / "engineering_graph" / "engineering_graph.db"), audit).get(selected) if project else {"project": "*", "nodes": [], "edges": [], "readOnly": True}
        payload = graph.as_dict() if hasattr(graph, "as_dict") else graph
        audit.record(action="engineering_graph_read", path=selected, permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(payload.get('nodes', []))} node(s)")
        return payload

    @app.get("/engineering-graph/query", tags=["engineering-graph"])
    def engineering_graph_query(q: str = Query(..., min_length=1, max_length=300), project: str = Query(..., min_length=1, max_length=100), settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency)) -> dict[str, Any]:
        result = EngineeringGraphManager(EngineeringGraphStorage(settings.workspace_root.parent / "engineering_graph" / "engineering_graph.db"), audit).query(project, q)
        audit.record(action="engineering_graph_query", path=f"{project}:engineering-graph", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"query={q}")
        return result

    @app.get("/engineering-graph/{project}", tags=["engineering-graph"])
    def engineering_graph_project(project: str, settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency)) -> dict[str, Any]:
        graph = EngineeringGraphManager(EngineeringGraphStorage(settings.workspace_root.parent / "engineering_graph" / "engineering_graph.db"), audit).get(project)
        payload = graph.as_dict()
        audit.record(action="engineering_graph_read", path=project, permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(graph.nodes)} node(s), {len(graph.edges)} edge(s)")
        return payload

    @app.get("/failure-intelligence/patterns", tags=["failure-intelligence"])
    def failure_intelligence_patterns(project: str = Query(..., min_length=1, max_length=100), settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency), approvals: ApprovalStore = Depends(approvals_dependency), workflow_manager: WorkflowManager = Depends(workflow_manager_dependency)) -> dict[str, Any]:
        loops = [loop.as_dict() for loop in ExecutionLoopStorage(settings.execution_loop_db_path).list_loops(project=project)]
        execution = ExecutionManager(ExecutionStorage(settings.execution_db_path), settings, approvals=approvals, workflow_manager=workflow_manager)
        tasks = [task.as_dict() for task in execution.list_tasks(project=project)]
        results = [result.as_dict() for result in execution.list_results(project=project)]
        patterns = FailureIntelligenceAnalyzer().analyze(project, loops=loops, tasks=tasks, results=results)
        audit.record(action="failure_intelligence_read", path=project, permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(patterns)} pattern(s)")
        return {"project": project, "patterns": [pattern.as_dict() for pattern in patterns], "readOnly": True}

    @app.get("/memory/evolution/history", tags=["evolution"])
    def evolution_history(project: str = Query(..., min_length=1, max_length=100), settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency), approvals: ApprovalStore = Depends(approvals_dependency)) -> dict[str, Any]:
        timeline = EvolutionTimeline(settings.memory_root / "evolution")
        decisions = [decision.as_dict() for decision in IntelligenceStorage(settings.intelligence_db_path).list_decisions(project=project)]
        loops = [loop.as_dict() for loop in ExecutionLoopStorage(settings.execution_loop_db_path).list_loops(project=project)]
        stored = timeline.list(project)
        derived = timeline.derive(project, decisions=decisions, loops=loops)
        combined = {entry["id"]: entry for entry in stored + derived}
        result = list(combined.values())
        result.sort(key=lambda item: item.get("createdAt", ""), reverse=True)
        audit.record(action="evolution_timeline_read", path=project, permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(result)} event(s)")
        return {"project": project, "timeline": result[:200], "readOnly": True}

    @app.post("/memory/evolution/append", status_code=status.HTTP_202_ACCEPTED, tags=["evolution"])
    def evolution_append(body: EvolutionAppendRequest, settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency), approvals: ApprovalStore = Depends(approvals_dependency)) -> JSONResponse:
        return _register_pending(
            action="evolution_timeline_append", project=body.project, path="memory/evolution/evolution.jsonl",
            payload={"kind": body.kind, "title": body.title, "content": body.content, "source_id": body.source_id},
            reason=body.reason, preview_factory=lambda: f"[evolution memory proposal/{body.kind}]\\n\\n{body.title}\\n{body.content[:1200]}",
            settings=settings, audit=audit, approvals=approvals,
        )

    @app.get("/agent/{agent_id}/capability-metrics", tags=["metrics"])
    def agent_capability_metrics(agent_id: str, settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency)) -> dict[str, Any]:
        record = MetricsManager(settings.agent_root, audit).get(agent_id)
        result = AgentCapabilityMetrics().compute(agent_id, metrics=record)
        audit.record(action="agent_capability_metrics_read", path=f"agent/{agent_id}/capability-metrics", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success")
        return result

    @app.get("/engineering/agent-metrics", tags=["metrics"])
    def engineering_agent_metrics(settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency)) -> dict[str, Any]:
        records = MetricsManager(settings.agent_root, audit).list()
        result = AgentCapabilityMetrics().aggregate(records)
        audit.record(action="engineering_agent_metrics_read", path="engineering/agent-metrics", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(result)} agent(s)")
        return {"metrics": result, "readOnly": True}

    @app.post("/execution-dag/create", status_code=status.HTTP_202_ACCEPTED, tags=["execution-dag"])
    def execution_dag_create(body: ExecutionDagCreateRequest, settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency), approvals: ApprovalStore = Depends(approvals_dependency), manager: ExecutionDagManager = Depends(execution_dag_manager_dependency)) -> JSONResponse:
        for loop_id in body.loop_ids:
            manager.orchestrator.get(loop_id)
        return _register_pending(
            action="execution_dag_create", project=body.project, path="execution-dag",
            payload={"loop_ids": body.loop_ids, "edges": body.edges},
            reason=body.reason, preview_factory=lambda: f"CREATE execution DAG for {len(body.loop_ids)} loop(s) with {len(body.edges)} edge(s); no execution",
            settings=settings, audit=audit, approvals=approvals,
        )

    @app.get("/execution-dag/list", tags=["execution-dag"])
    def execution_dag_list(
        project: str | None = Query(default=None, max_length=100),
        limit: int = Query(default=100, ge=1, le=500),
        manager: ExecutionDagManager = Depends(execution_dag_manager_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        dags = manager.list_dags(project=project, limit=limit)
        audit.record(action="execution_dag_list_read", path=project or "*", permission="LEVEL_0", approved=True, result="success", detail=f"{len(dags)} DAG(s)")
        return {"dags": [{**dag.as_dict(), "loopStatuses": manager.loop_statuses(dag.id)} for dag in dags], "readOnly": True}

    @app.get("/execution-dag/{dag_id}", tags=["execution-dag"])
    def execution_dag_detail(dag_id: str, manager: ExecutionDagManager = Depends(execution_dag_manager_dependency), audit: AuditLogger = Depends(audit_dependency)) -> dict[str, Any]:
        dag = manager.get(dag_id)
        audit.record(action="execution_dag_read", path=f"execution-dag/{dag_id}", permission="LEVEL_0", approved=True, result="success", detail=f"{len(dag.loop_ids)} loop(s)")
        return {**dag.as_dict(), "loopStatuses": manager.loop_statuses(dag_id), "readOnly": True}

    @app.get("/execution-dag/{dag_id}/ready", tags=["execution-dag"])
    def execution_dag_ready(dag_id: str, manager: ExecutionDagManager = Depends(execution_dag_manager_dependency), audit: AuditLogger = Depends(audit_dependency)) -> dict[str, Any]:
        ready = manager.ready_loops(dag_id)
        audit.record(action="execution_dag_ready_read", path=f"execution-dag/{dag_id}/ready", permission="LEVEL_0", approved=True, result="success", detail=f"{len(ready)} ready loop(s)")
        return {"dagId": dag_id, "readyLoops": ready, "loopStatuses": manager.loop_statuses(dag_id), "readOnly": True}

    @app.post("/execution-dag/{dag_id}/advance", status_code=status.HTTP_202_ACCEPTED, tags=["execution-dag"])
    def execution_dag_advance(dag_id: str, body: ExecutionDagActionRequest, settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency), approvals: ApprovalStore = Depends(approvals_dependency), manager: ExecutionDagManager = Depends(execution_dag_manager_dependency)) -> JSONResponse:
        manager.get(dag_id)
        return _register_pending(
            action="execution_dag_advance", project="execution", path=f"execution-dag/{dag_id}/advance",
            payload={"dag_id": dag_id},
            reason=body.reason, preview_factory=lambda: f"PREPARE proposal for next ready loop in DAG {dag_id}; proposal remains metadata",
            settings=settings, audit=audit, approvals=approvals,
        )

    @app.get("/execution-loop/{loop_id}/context", tags=["execution-loop"])
    def execution_loop_context(loop_id: str, settings: Settings = Depends(settings_dependency), approvals: ApprovalStore = Depends(approvals_dependency), audit: AuditLogger = Depends(audit_dependency)) -> dict[str, Any]:
        orchestrator = ExecutionLoopOrchestrator(ExecutionLoopStorage(settings.execution_loop_db_path), settings, approvals=approvals, audit=audit)
        dag_manager = ExecutionDagManager(ExecutionDagStorage(settings.execution_dag_db_path), orchestrator, audit=audit)
        bundle = LoopContextBuilder(orchestrator, dag_manager).build(loop_id)
        audit.record(action="execution_loop_context_read", path=f"execution-loop/{loop_id}/context", permission="LEVEL_0", approved=True, result="success", detail=f"{len(bundle['tasks'])} task(s)")
        return bundle

    @app.get("/engineering/metrics", tags=["metrics"])
    def engineering_metrics(
        project: str | None = Query(default=None, max_length=100),
        settings: Settings = Depends(settings_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        orchestrator = ExecutionLoopOrchestrator(ExecutionLoopStorage(settings.execution_loop_db_path), settings, approvals=approvals, audit=audit)
        report = EngineeringMetricsManager(orchestrator, audit).compute(project=project)
        audit.record(action="engineering_metrics_read", path=project or "*", permission="LEVEL_0", approved=True, result="success", detail=f"{report['totalLoops']} loop(s)")
        return report

    @app.post("/execution-loop/{loop_id}/recover", status_code=status.HTTP_202_ACCEPTED, tags=["execution-loop"])
    def execution_loop_recover(loop_id: str, body: ExecutionLoopActionRequest, settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency), approvals: ApprovalStore = Depends(approvals_dependency)) -> JSONResponse:
        loop = ExecutionLoopOrchestrator(ExecutionLoopStorage(settings.execution_loop_db_path), settings, approvals=approvals, audit=audit).get(loop_id)
        return _register_pending(
            action="execution_loop_recover", project=loop.project, path=f"execution-loop/{loop_id}/recover",
            payload={"loop_id": loop_id},
            reason=body.reason, preview_factory=lambda: f"MARK loop {loop_id} as RECOVERED; no automatic continuation, explicit user confirmation required",
            settings=settings, audit=audit, approvals=approvals, workflow_id=loop.workflow_id,
        )

    @app.post("/execution-loop/create", status_code=status.HTTP_202_ACCEPTED, tags=["execution-loop"])
    def execution_loop_create(body: ExecutionLoopCreateRequest, settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency), approvals: ApprovalStore = Depends(approvals_dependency)) -> JSONResponse:
        plan = SimulationStorage(settings.simulation_db_path).get_plan(body.plan_id)
        if plan is None:
            raise ResourceNotFound(f"Engineering plan '{body.plan_id}' was not found")
        return _register_pending(
            action="execution_loop_create", project=body.project, path=f"execution-loop/{body.plan_id}",
            payload={"plan_id": body.plan_id, "workflow_id": body.workflow_id},
            reason=body.reason, preview_factory=lambda: f"CREATE execution loop metadata for plan {body.plan_id}; proposal/execution remain approval-gated",
            settings=settings, audit=audit, approvals=approvals, workflow_id=body.workflow_id,
        )

    @app.get("/execution-loop/list", tags=["execution-loop"])
    def execution_loop_list(
        project: str | None = Query(default=None, max_length=100),
        limit: int = Query(default=100, ge=1, le=500),
        orchestrator: ExecutionLoopOrchestrator = Depends(execution_loop_manager_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        loops = orchestrator.list_loops(project=project, limit=limit)
        audit.record(action="execution_loop_list_read", path=project or "*", permission="LEVEL_0", approved=True, result="success", detail=f"{len(loops)} loop(s)")
        return {"loops": [loop.as_dict() for loop in loops], "readOnly": True}

    @app.get("/execution-loop/{loop_id}", tags=["execution-loop"])
    def execution_loop_detail(loop_id: str, orchestrator: ExecutionLoopOrchestrator = Depends(execution_loop_manager_dependency), audit: AuditLogger = Depends(audit_dependency)) -> dict[str, Any]:
        loop = orchestrator.get(loop_id)
        audit.record(action="execution_loop_read", path=f"execution-loop/{loop_id}", permission="LEVEL_0", approved=True, result="success", detail=f"state={loop.status.value}")
        return {**loop.as_dict(), "readOnly": True}

    @app.post("/execution-loop/{loop_id}/prepare", status_code=status.HTTP_202_ACCEPTED, tags=["execution-loop"])
    def execution_loop_prepare(loop_id: str, body: ExecutionLoopActionRequest, settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency), approvals: ApprovalStore = Depends(approvals_dependency)) -> JSONResponse:
        loop = ExecutionLoopOrchestrator(ExecutionLoopStorage(settings.execution_loop_db_path), settings, approvals=approvals, audit=audit).get(loop_id)
        return _register_pending(
            action="execution_loop_prepare", project=loop.project, path=f"execution-loop/{loop_id}/prepare",
            payload={"loop_id": loop_id},
            reason=body.reason, preview_factory=lambda: f"GENERATE execution proposals for loop {loop_id}; proposals remain metadata",
            settings=settings, audit=audit, approvals=approvals, workflow_id=loop.workflow_id,
        )

    @app.post("/execution-loop/{loop_id}/verify", status_code=status.HTTP_202_ACCEPTED, tags=["execution-loop"])
    def execution_loop_verify(loop_id: str, body: ExecutionLoopActionRequest, settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency), approvals: ApprovalStore = Depends(approvals_dependency)) -> JSONResponse:
        loop = ExecutionLoopOrchestrator(ExecutionLoopStorage(settings.execution_loop_db_path), settings, approvals=approvals, audit=audit).get(loop_id)
        return _register_pending(
            action="execution_loop_verify", project=loop.project, path=f"execution-loop/{loop_id}/verify",
            payload={"loop_id": loop_id, "quality_score": body.quality_score, "risk_score": body.risk_score, "test_passed": body.test_passed},
            reason=body.reason, preview_factory=lambda: f"VERIFY loop {loop_id}: generate verification report and queue learning memory proposal",
            settings=settings, audit=audit, approvals=approvals, workflow_id=loop.workflow_id,
        )

    @app.post("/execution-loop/{loop_id}/rollback", status_code=status.HTTP_202_ACCEPTED, tags=["execution-loop"])
    def execution_loop_rollback(loop_id: str, body: ExecutionLoopActionRequest, settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency), approvals: ApprovalStore = Depends(approvals_dependency)) -> JSONResponse:
        loop = ExecutionLoopOrchestrator(ExecutionLoopStorage(settings.execution_loop_db_path), settings, approvals=approvals, audit=audit).get(loop_id)
        return _register_pending(
            action="execution_loop_rollback", project=loop.project, path=f"execution-loop/{loop_id}/rollback",
            payload={"loop_id": loop_id},
            reason=body.reason, preview_factory=lambda: f"GENERATE rollback proposal for loop {loop_id}; snapshot restore requires separate approval",
            settings=settings, audit=audit, approvals=approvals, workflow_id=loop.workflow_id,
        )

    @app.get("/execution-loop/{loop_id}/timeline", tags=["execution-loop"])
    def execution_loop_timeline(loop_id: str, orchestrator: ExecutionLoopOrchestrator = Depends(execution_loop_manager_dependency), audit: AuditLogger = Depends(audit_dependency)) -> dict[str, Any]:
        timeline = orchestrator.timeline(loop_id)
        audit.record(action="execution_loop_timeline_read", path=f"execution-loop/{loop_id}/timeline", permission="LEVEL_0", approved=True, result="success", detail=f"{len(timeline)} event(s)")
        return {"loopId": loop_id, "timeline": timeline, "readOnly": True}

    @app.get("/quality/v8/{workflow_id}", tags=["quality"])
    def quality_gate_v8(
        workflow_id: str,
        approval_present: bool = Query(default=False, alias="approval_present"),
        snapshot_present: bool = Query(default=False, alias="snapshot_present"),
        verification_status: str = Query(default=None, max_length=10),
        risk_level: str = Query(default="low", max_length=10),
        rollback_capability: bool = Query(default=False, alias="rollback_capability"),
        test_result: str = Query(default=None, max_length=16),
        confidence: int = Query(default=0, ge=0, le=100),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        report = QualityGate8Evaluator().evaluate(
            approval_present=approval_present,
            snapshot_present=snapshot_present,
            verification_status=verification_status,
            risk_level=risk_level,
            rollback_capability=rollback_capability,
            test_result=test_result,
            confidence=confidence,
        )
        audit.record(action="quality_gate_v8_read", path=f"quality/v8/{workflow_id}", permission="LEVEL_0", approved=True, result="success", detail=f"quality={report['quality']}, ready={report['executionReady']}")
        return {"workflowId": workflow_id, **report}

    @app.get("/memory/planning/history", tags=["memory"])
    def planning_memory_history(project: str = Query(..., min_length=1, max_length=100), settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency)) -> dict[str, Any]:
        history = PlanningMemory(settings).history(project)
        audit.record(action="planning_memory_history", path=f"{project}:planning-memory", permission="LEVEL_0", approved=True, result="success", detail=f"{len(history)} record(s)")
        return {"project": project, "history": history, "readOnly": True}

    # ---- Controlled Engineering Execution (Phase 15) -----------------

    def execution_manager_dependency(
        settings: Settings = Depends(settings_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
        workflow_manager: WorkflowManager = Depends(workflow_manager_dependency),
    ) -> ExecutionManager:
        return ExecutionManager(
            ExecutionStorage(settings.execution_db_path),
            settings,
            approvals=approvals,
            workflow_manager=workflow_manager,
        )

    @app.post("/execution/create", status_code=status.HTTP_202_ACCEPTED, tags=["execution"])
    def execution_create(body: ExecutionCreateRequest, settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency), approvals: ApprovalStore = Depends(approvals_dependency)) -> JSONResponse:
        plan = SimulationStorage(settings.simulation_db_path).get_plan(body.plan_id)
        if plan is None:
            raise ResourceNotFound(f"Engineering plan '{body.plan_id}' was not found")
        return _register_pending(
            action="execution_create", project=body.project, path=f"execution/plan/{body.plan_id}",
            payload={"plan_id": body.plan_id, "workflow_id": body.workflow_id},
            reason=body.reason, preview_factory=lambda: f"CREATE implementation task metadata from approved plan {body.plan_id}; no source modification",
            settings=settings, audit=audit, approvals=approvals, workflow_id=body.workflow_id,
        )

    @app.get("/execution/tasks", tags=["execution"])
    def execution_tasks(
        project: str | None = Query(default=None, max_length=100),
        task_status: str | None = Query(default=None, alias="status", max_length=32),
        limit: int = Query(default=100, ge=1, le=500),
        manager: ExecutionManager = Depends(execution_manager_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        tasks = manager.list_tasks(project=project, status=task_status, limit=limit)
        audit.record(action="execution_tasks_read", path=project or "*", permission="LEVEL_0", approved=True, result="success", detail=f"{len(tasks)} task(s)")
        return {"tasks": [task.as_dict() for task in tasks], "readOnly": True}

    @app.get("/execution/task/{task_id}", tags=["execution"])
    def execution_task(task_id: str, manager: ExecutionManager = Depends(execution_manager_dependency), audit: AuditLogger = Depends(audit_dependency)) -> dict[str, Any]:
        task = manager.get_task(task_id)
        proposals = [item.as_dict() for item in manager.list_proposals(project=task.project) if item.task_id == task_id]
        audit.record(action="execution_task_read", path=f"execution/task/{task_id}", permission="LEVEL_0", approved=True, result="success")
        return {**task.as_dict(), "proposals": proposals}

    @app.post("/execution/{task_id}/proposal", status_code=status.HTTP_202_ACCEPTED, tags=["execution"])
    def execution_proposal(task_id: str, body: ExecutionProposalRequest, settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency), approvals: ApprovalStore = Depends(approvals_dependency), manager: ExecutionManager = Depends(execution_manager_dependency)) -> JSONResponse:
        task = manager.get_task(task_id)
        return _register_pending(
            action="execution_proposal", project=task.project, path=f"execution/task/{task_id}/proposal",
            payload={"task_id": task_id},
            reason=body.reason, preview_factory=lambda: f"GENERATE execution proposal for task {task_id} ({task.files} file(s)); proposal remains metadata",
            settings=settings, audit=audit, approvals=approvals, workflow_id=task.workflow_id,
        )

    @app.get("/execution/proposals", tags=["execution"])
    def execution_proposals(
        project: str | None = Query(default=None, max_length=100),
        proposal_status: str | None = Query(default=None, alias="status", max_length=32),
        limit: int = Query(default=100, ge=1, le=500),
        manager: ExecutionManager = Depends(execution_manager_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        proposals = manager.list_proposals(project=project, status=proposal_status, limit=limit)
        audit.record(action="execution_proposals_read", path=project or "*", permission="LEVEL_0", approved=True, result="success", detail=f"{len(proposals)} proposal(s)")
        return {"proposals": [item.as_dict() for item in proposals], "readOnly": True}

    @app.get("/execution/proposal/{proposal_id}", tags=["execution"])
    def execution_proposal_detail(proposal_id: str, manager: ExecutionManager = Depends(execution_manager_dependency), audit: AuditLogger = Depends(audit_dependency)) -> dict[str, Any]:
        proposal = manager.get_proposal(proposal_id)
        audit.record(action="execution_proposal_read", path=f"execution/proposal/{proposal_id}", permission="LEVEL_0", approved=True, result="success")
        return proposal.as_dict()

    @app.post("/execution/{proposal_id}/execute", status_code=status.HTTP_202_ACCEPTED, tags=["execution"])
    def execution_execute(proposal_id: str, body: ExecutionExecuteRequest, settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency), approvals: ApprovalStore = Depends(approvals_dependency), manager: ExecutionManager = Depends(execution_manager_dependency)) -> JSONResponse:
        proposal = manager.get_proposal(proposal_id)
        task = manager.get_task(proposal.task_id)
        return _register_pending(
            action="execution_execute", project=proposal.project, path=f"execution/proposal/{proposal_id}",
            payload={"proposal_id": proposal_id},
            reason=body.reason, preview_factory=lambda: f"EXECUTE approved proposal {proposal_id}: {len(proposal.operations)} operation(s), risk {proposal.risk_score}/100; snapshot + result metadata only, no source write",
            settings=settings, audit=audit, approvals=approvals, workflow_id=task.workflow_id,
        )

    @app.get("/execution/results", tags=["execution"])
    def execution_results(
        project: str | None = Query(default=None, max_length=100),
        limit: int = Query(default=100, ge=1, le=500),
        manager: ExecutionManager = Depends(execution_manager_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        results = manager.list_results(project=project, limit=limit)
        audit.record(action="execution_results_read", path=project or "*", permission="LEVEL_0", approved=True, result="success", detail=f"{len(results)} result(s)")
        return {"results": [item.as_dict() for item in results], "readOnly": True}

    @app.get("/execution/{execution_id}/verify", tags=["execution"])
    def execution_verify(execution_id: str, manager: ExecutionManager = Depends(execution_manager_dependency), audit: AuditLogger = Depends(audit_dependency)) -> dict[str, Any]:
        verification = manager.verification(execution_id)
        audit.record(action="execution_verify_read", path=f"execution/{execution_id}/verify", permission="LEVEL_0", approved=True, result="success", detail=f"status={verification.get('status')}")
        return {"executionId": execution_id, **verification, "readOnly": True}

    @app.get("/quality/v7/{workflow_id}", tags=["quality"])
    def quality_gate_v7(
        workflow_id: str,
        implementation_confidence: int = Query(default=100, ge=0, le=100),
        execution_risk: int = Query(default=0, ge=0, le=100),
        rollback_readiness: int = Query(default=100, ge=0, le=100),
        verification_confidence: int = Query(default=100, ge=0, le=100),
        blocking_issue: list[str] = Query(default=[], alias="blocking_issue", max_length=50),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        report = QualityGate7Evaluator().evaluate(implementation_confidence=implementation_confidence, execution_risk=execution_risk, rollback_readiness=rollback_readiness, verification_confidence=verification_confidence, blocking_issues=blocking_issue)
        audit.record(action="quality_gate_v7_read", path=f"quality/v7/{workflow_id}", permission="LEVEL_0", approved=True, result="success", detail=f"quality={report['quality']}")
        return {"workflowId": workflow_id, **report}

    @app.get("/memory/execution/history", tags=["memory"])
    def execution_memory_history(project: str = Query(..., min_length=1, max_length=100), settings: Settings = Depends(settings_dependency), audit: AuditLogger = Depends(audit_dependency)) -> dict[str, Any]:
        history = ExecutionMemory(settings).history(project)
        audit.record(action="execution_memory_history", path=f"{project}:execution-memory", permission="LEVEL_0", approved=True, result="success", detail=f"{len(history)} record(s)")
        return {"project": project, "history": history, "readOnly": True}

    # ---- Project Intelligence (Phase 12) -------------------------------

    @app.post("/code/index", status_code=status.HTTP_202_ACCEPTED, tags=["code-intelligence"])
    def code_index(
        body: CodeIndexRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
    ) -> JSONResponse:
        scanner = CodeScanner(settings)
        return _register_pending(
            action="code_index",
            project=body.project,
            path="code/code_index.db",
            payload={"project": body.project},
            reason=body.reason,
            preview_factory=lambda: f"SCAN {len(scanner.scan(body.project))} source file(s); update symbol/dependency indexes only",
            settings=settings,
            audit=audit,
            approvals=approvals,
        )

    @app.get("/code/search", tags=["code-intelligence"])
    def code_search(
        project: str = Query(..., min_length=1, max_length=100),
        q: str = Query(default="", max_length=300),
        limit: int = Query(default=100, ge=1, le=500),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        index = CodeIndex(settings.code_index_db_path)
        results = index.search(project, q, limit)
        audit.record(action="code_search", path=f"{project}:code", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(results)} symbol(s)")
        return {"project": project, "query": q, "results": results, "stats": index.stats(project), "readOnly": True}

    @app.get("/code/symbol/{name}", tags=["code-intelligence"])
    def code_symbol(
        name: str,
        project: str = Query(..., min_length=1, max_length=100),
        limit: int = Query(default=100, ge=1, le=500),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        index = CodeIndex(settings.code_index_db_path)
        results = index.symbol(project, name, limit)
        audit.record(action="code_symbol_read", path=f"{project}:symbol/{name}", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(results)} definition(s)")
        return {"project": project, "name": name, "definitions": results, "readOnly": True}

    @app.get("/project/profile", tags=["project-intelligence"])
    def project_profile(
        project: str = Query(..., min_length=1, max_length=100),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        profile = ProjectProfileService(CodeIndex(settings.code_index_db_path)).build(project).as_dict()
        audit.record(action="project_profile_read", path=f"{project}:profile", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success")
        return profile

    @app.get("/project/graph", tags=["project-intelligence"])
    def project_graph(
        project: str = Query(..., min_length=1, max_length=100),
        q: str = Query(default="", max_length=300),
        limit: int = Query(default=200, ge=1, le=1000),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        graph = KnowledgeGraph(settings.knowledge_graph_db_path, CodeIndex(settings.code_index_db_path)).query(project, q, limit)
        audit.record(action="project_graph_read", path=f"{project}:graph", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(graph['nodes'])} node(s)")
        return graph

    @app.get("/impact/analyze", tags=["project-intelligence"])
    def impact_analyze(
        project: str = Query(..., min_length=1, max_length=100),
        changed_file: list[str] = Query(default=[], alias="changed_file", max_length=100),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        report = ImpactAnalyzer(CodeIndex(settings.code_index_db_path)).analyze(project, changed_file)
        audit.record(action="impact_analyze", path=f"{project}:impact", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(report['affectedModules'])} affected module(s)")
        return report

    @app.get("/context/query", tags=["context"])
    def context_query(
        project: str = Query(..., min_length=1, max_length=100),
        q: str = Query(default="", max_length=4000),
        agent_role: str = Query(default="CODER", max_length=32),
        changed_file: list[str] = Query(default=[], alias="changed_file", max_length=100),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        engine = ContextQueryEngine(CodeIndex(settings.code_index_db_path), ProjectMemory(settings))
        result = engine.query(project, agent_role, q, changed_file)
        audit.record(action="context_query", path=f"{project}:context-query", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(result['files'])} code result(s)")
        return result

    @app.post("/memory/project/propose", status_code=status.HTTP_202_ACCEPTED, tags=["memory"])
    def project_memory_propose(
        body: ProjectMemoryProposalRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
    ) -> JSONResponse:
        memory = ProjectMemory(settings)
        return _register_pending(
            action="project_memory_append",
            project=body.project,
            path=f"memory/project/{body.category}",
            payload={"category": body.category, "content": body.content},
            reason=body.reason,
            preview_factory=lambda: memory.preview(body.project, body.category, body.content),
            settings=settings,
            audit=audit,
            approvals=approvals,
        )

    @app.get("/memory/project/history", tags=["memory"])
    def project_memory_history(
        project: str = Query(..., min_length=1, max_length=100),
        limit: int = Query(default=100, ge=1, le=500),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        history = ProjectMemory(settings).history(project, limit)
        intelligence_history = ProjectIntelligenceMemory(settings).history(project, limit)
        combined = sorted([*history, *intelligence_history], key=lambda item: item["updatedAt"], reverse=True)[:limit]
        audit.record(action="project_memory_history", path=f"{project}:project-memory", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"{len(combined)} record(s)")
        return {"project": project, "history": combined, "readOnly": True}

    @app.get("/quality/v4/{workflow_id}", tags=["quality"])
    def quality_gate_v4(
        workflow_id: str,
        architecture_impact: int = Query(default=0, ge=0, le=100),
        change_risk: str = Query(default="low", max_length=16),
        regression_risk: str = Query(default="low", max_length=16),
        historical_stability: int = Query(default=100, ge=0, le=100),
        affected_module: list[str] = Query(default=[], alias="affected_module", max_length=200),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        report = QualityGate4Evaluator().evaluate(architecture_impact=architecture_impact, change_risk=change_risk, regression_risk=regression_risk, historical_stability=historical_stability, affected_modules=affected_module)
        audit.record(action="quality_gate_v4_read", path=f"quality/v4/{workflow_id}", permission=PermissionLevel.LEVEL_0.value, approved=True, result="success", detail=f"score={report['score']}")
        return {"workflowId": workflow_id, **report}

    @app.get("/workspace/list", response_model=WorkspaceListResponse, tags=["workspace"])
    def workspace_list(
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> WorkspaceListResponse:
        manager = WorkspaceManager(settings)
        projects = manager.list_projects()
        audit.record(
            action="workspace_list",
            path=str(settings.workspace_root),
            permission=PermissionLevel.LEVEL_0.value,
            approved=True,
            result="success",
            detail=f"{len(projects)} project(s)",
        )
        return WorkspaceListResponse(projects=projects)  # type: ignore[arg-type]

    @app.get("/project/tree", response_model=ProjectTreeResponse, tags=["workspace"])
    def project_tree(
        project_name: str = Query(..., min_length=1, max_length=100),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> ProjectTreeResponse:
        manager = WorkspaceManager(settings)
        try:
            tree = manager.build_tree(project_name)
        except BridgeError as exc:
            audit.record(
                action="project_tree",
                path=project_name,
                permission=PermissionLevel.LEVEL_0.value,
                approved=True,
                result="rejected",
                detail=exc.message,
            )
            raise
        audit.record(
            action="project_tree",
            path=project_name,
            permission=PermissionLevel.LEVEL_0.value,
            approved=True,
            result="success",
        )
        return ProjectTreeResponse(
            project=project_name,
            maxDepth=settings.max_tree_depth,
            ignored=list(settings.ignored_names),
            tree=tree,  # type: ignore[arg-type]
        )

    @app.get("/file/read", response_model=FileReadResponse, tags=["files"])
    def file_read(
        project: str = Query(..., min_length=1, max_length=100),
        path: str = Query(..., min_length=1, max_length=1024),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> FileReadResponse:
        service = FileService(settings)
        display = relative_display(project, path)
        try:
            payload = service.read_file(project, path)
        except BridgeError as exc:
            audit.record(
                action="file_read",
                path=display,
                permission=PermissionLevel.LEVEL_0.value,
                approved=True,
                result="rejected",
                detail=exc.message,
            )
            raise
        audit.record(
            action="file_read",
            path=display,
            permission=PermissionLevel.LEVEL_0.value,
            approved=True,
            result="success",
            detail=f"{payload['size']} bytes",
        )
        return FileReadResponse(**payload)

    @app.post("/file/create", status_code=status.HTTP_202_ACCEPTED, tags=["files"])
    def file_create(
        body: FileCreateRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
    ) -> JSONResponse:
        service = FileService(settings)
        return _register_pending(
            action="file_create",
            project=body.project,
            path=body.path,
            payload={"content": body.content},
            reason=body.reason,
            preview_factory=lambda: service.preview_create(body.project, body.path, body.content),
            settings=settings,
            audit=audit,
            approvals=approvals,
        )

    @app.post("/file/write", status_code=status.HTTP_202_ACCEPTED, tags=["files"])
    def file_write(
        body: FileWriteRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
    ) -> JSONResponse:
        service = FileService(settings)
        return _register_pending(
            action="file_write",
            project=body.project,
            path=body.path,
            payload={"content": body.content},
            reason=body.reason,
            preview_factory=lambda: service.preview_write(body.project, body.path, body.content),
            settings=settings,
            audit=audit,
            approvals=approvals,
        )

    @app.post("/patch/apply", status_code=status.HTTP_202_ACCEPTED, tags=["patch"])
    def patch_apply(
        body: PatchApplyRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
    ) -> JSONResponse:
        service = PatchService(settings)
        return _register_pending(
            action="patch_apply",
            project=body.project,
            path=body.path,
            payload={"patch": body.patch},
            reason=body.reason,
            preview_factory=lambda: service.preview(body.project, body.path, body.patch),
            settings=settings,
            audit=audit,
            approvals=approvals,
        )

    # ---- Memory: read side (LEVEL_0) --------------------------------

    @app.get("/memory/list", response_model=MemoryListResponse, tags=["memory"])
    def memory_list(
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> MemoryListResponse:
        projects = MemoryManager(settings).list_projects()
        audit.record(
            action="memory_list",
            path=str(settings.memory_root),
            permission=PermissionLevel.LEVEL_0.value,
            approved=True,
            result="success",
            detail=f"{len(projects)} project(s)",
        )
        return MemoryListResponse(projects=projects)  # type: ignore[arg-type]

    @app.get("/memory/status", response_model=MemoryStatusResponse, tags=["memory"])
    def memory_status(
        project: str = Query(..., min_length=1, max_length=100),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> MemoryStatusResponse:
        manager = MemoryManager(settings)
        try:
            payload = manager.status(project)
        except BridgeError as exc:
            audit.record(
                action="memory_read",
                path=f"{project}:status",
                permission=PermissionLevel.LEVEL_0.value,
                approved=True,
                result="rejected",
                detail=exc.message,
            )
            raise
        audit.record(
            action="memory_read",
            path=f"{project}:status",
            permission=PermissionLevel.LEVEL_0.value,
            approved=True,
            result="success",
        )
        return MemoryStatusResponse(**payload)

    @app.get("/memory/read", response_model=MemoryReadResponse, tags=["memory"])
    def memory_read(
        project: str = Query(..., min_length=1, max_length=100),
        document: str = Query(..., min_length=1, max_length=64),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> MemoryReadResponse:
        manager = MemoryManager(settings)
        display = f"{project}:memory/{document}"
        try:
            payload = manager.read(project, document)
        except BridgeError as exc:
            audit.record(
                action="memory_read",
                path=display,
                permission=PermissionLevel.LEVEL_0.value,
                approved=True,
                result="rejected",
                detail=exc.message,
            )
            raise
        audit.record(
            action="memory_read",
            path=display,
            permission=PermissionLevel.LEVEL_0.value,
            approved=True,
            result="success",
            detail=f"{payload['size']} bytes",
        )
        return MemoryReadResponse(**payload)

    # ---- Memory: write side (LEVEL_1, approval gated) ----------------

    @app.post("/memory/init", status_code=status.HTTP_202_ACCEPTED, tags=["memory"])
    def memory_init(
        body: MemoryInitRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
    ) -> JSONResponse:
        return _register_pending(
            action="memory_init",
            project=body.project,
            path="memory/",
            payload={},
            reason=body.reason or "Initialise project memory documents",
            preview_factory=lambda: "[init] project.md, architecture.md, decisions.md, "
            "tasks.md, changelog.md, memory.db",
            settings=settings,
            audit=audit,
            approvals=approvals,
        )

    @app.post("/memory/append", status_code=status.HTTP_202_ACCEPTED, tags=["memory"])
    def memory_append(
        body: MemoryAppendRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
    ) -> JSONResponse:
        manager = MemoryManager(settings)
        return _register_pending(
            action="memory_append",
            project=body.project,
            path=f"memory/{body.document}",
            payload={"document": body.document, "content": body.content},
            reason=body.reason or f"Append to {body.document}",
            preview_factory=lambda: manager.preview_append(
                body.project, body.document, body.content
            ),
            settings=settings,
            audit=audit,
            approvals=approvals,
        )

    @app.post("/memory/decision", status_code=status.HTTP_202_ACCEPTED, tags=["memory"])
    def memory_decision(
        body: MemoryDecisionRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
    ) -> JSONResponse:
        manager = MemoryManager(settings)
        payload = DecisionInput.build(
            title=body.title,
            context=body.context,
            decision=body.decision,
            consequence=body.consequence,
        )
        return _register_pending(
            action="memory_decision",
            project=body.project,
            path="memory/decisions.md",
            payload={
                "title": payload.title,
                "context": payload.context,
                "decision": payload.decision,
                "consequence": payload.consequence,
            },
            reason=body.reason or f"Record ADR: {payload.title}",
            preview_factory=lambda: manager.preview_decision(body.project, payload),
            settings=settings,
            audit=audit,
            approvals=approvals,
        )

    @app.get("/permission/pending", response_model=PendingApprovalsResponse, tags=["permission"])
    def permission_pending(
        approvals: ApprovalStore = Depends(approvals_dependency),
    ) -> PendingApprovalsResponse:
        return PendingApprovalsResponse(pending=[req.as_dict() for req in approvals.list_pending()])

    @app.post("/permission/reconfirm", tags=["permission"])
    def permission_reconfirm(
        body: ApprovalReconfirmRequest,
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
    ) -> dict[str, Any]:
        request_id = ensure_request_id(body.request_id)
        request = approvals.reconfirm(request_id, audit)
        return request.as_dict()

    @app.post("/permission/reject", tags=["permission"])
    def permission_reject(
        body: ApprovalRejectRequest,
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
        workflow_manager: WorkflowManager = Depends(workflow_manager_dependency),
    ) -> dict[str, Any]:
        request_id = ensure_request_id(body.request_id)
        request = approvals.mark_rejected(request_id, body.reason, audit)
        if request.action == "workflow_stage_approval":
            workflow_manager.resolve_stage_approval(request_id, approved=False)
        return request.as_dict()

    @app.post("/permission/approve", response_model=OperationResultResponse, tags=["permission"])
    def permission_approve(
        body: ApprovalDecisionRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
        workflow_manager: WorkflowManager = Depends(workflow_manager_dependency),
    ) -> OperationResultResponse:
        request_id = ensure_request_id(body.request_id)
        request = approvals.mark_approved(request_id)
        display = relative_display(request.project, request.path)

        try:
            result = _execute_action(
                request,
                settings,
                approvals=approvals,
                workflow_manager=workflow_manager,
            )
        except BridgeError as exc:
            approvals.mark_failed(request_id, exc.message)
            if request.action == "workflow_stage_approval":
                try:
                    workflow_manager.resolve_stage_approval(request_id, approved=False)
                except BridgeError:  # pragma: no cover - defensive
                    pass
            audit.record(
                action=request.action,
                path=display,
                permission=request.permission_level.value,
                approved=True,
                result="failed",
                detail=exc.message,
                request_id=request_id,
            )
            raise

        approvals.mark_executed(request_id, result)
        detail = _result_summary(request.action, result)
        if request.workflow_id:
            detail = f"{detail} [workflow={request.workflow_id}]"
        audit.record(
            action=request.action,
            path=display,
            permission=request.permission_level.value,
            approved=True,
            result="success",
            detail=detail,
            request_id=request_id,
        )
        return OperationResultResponse(
            permissionLevel=request.permission_level.value,
            requestId=request_id,
            action=request.action,
            status=request.status.value,
            project=request.project,
            path=request.path,
            result=result,
        )

    # ---- Engineering toolchain (Phase 6) ------------------------------

    @app.get("/git/status", tags=["git"])
    def git_status(
        project: str = Query(..., min_length=1, max_length=100),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        try:
            result = GitManager(settings).status(project).as_dict()
        except BridgeError as exc:
            audit.record(action="git_status", path=project, permission="LEVEL_0", approved=True, result="rejected", detail=exc.message)
            raise
        audit.record(action="git_status", path=project, permission="LEVEL_0", approved=True, result="success")
        return result

    @app.get("/git/diff", tags=["git"])
    def git_diff(
        project: str = Query(..., min_length=1, max_length=100),
        staged: bool = Query(default=False),
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> dict[str, Any]:
        try:
            result = GitManager(settings).diff(project, staged=staged)
        except BridgeError as exc:
            audit.record(action="git_diff", path=project, permission="LEVEL_0", approved=True, result="rejected", detail=exc.message)
            raise
        audit.record(action="git_diff", path=project, permission="LEVEL_0", approved=True, result="success", detail=f"{result['size']} bytes")
        return result

    @app.post("/git/commit", status_code=status.HTTP_202_ACCEPTED, tags=["git"])
    def git_commit(
        body: GitCommitRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
        workflow_manager: WorkflowManager = Depends(workflow_manager_dependency),
    ) -> JSONResponse:
        validate_git_binding(body.workflow_id, body.stage_id)
        workflow_manager.validate_binding(body.workflow_id, body.stage_id, project=body.project)
        manager = GitManager(settings)
        return _register_pending(
            action="git_commit", project=body.project, path=".git", payload={"message": body.message},
            reason=body.reason or f"Commit workflow stage {body.stage_id}",
            preview_factory=lambda: __import__("json").dumps(manager.preview_commit(body.project, body.message), ensure_ascii=False, indent=2),
            settings=settings, audit=audit, approvals=approvals,
            workflow_id=body.workflow_id, stage_id=body.stage_id,
        )

    @app.post("/test/run", status_code=status.HTTP_202_ACCEPTED, tags=["test"])
    def test_run(
        body: TestRunRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
        workflow_manager: WorkflowManager = Depends(workflow_manager_dependency),
    ) -> JSONResponse:
        _, stage = workflow_manager.validate_binding(body.workflow_id, body.stage_id, project=body.project)
        if stage.stage_type.value != "TESTING":
            from app.security.validator import ValidationFailed
            raise ValidationFailed("Test commands can only bind to a TESTING stage")
        runner = TestRunner(settings)
        return _register_pending(
            action="test_run", project=body.project, path=f"workflow/{body.workflow_id}#{body.stage_id}",
            payload={"command": body.command}, reason=body.reason or f"Run {body.command}",
            preview_factory=lambda: __import__("json").dumps(runner.preview(body.project, body.command), ensure_ascii=False, indent=2),
            settings=settings, audit=audit, approvals=approvals,
            workflow_id=body.workflow_id, stage_id=body.stage_id,
        )

    @app.post(
        "/workflow/{workflow_id}/stage/rollback",
        status_code=status.HTTP_202_ACCEPTED,
        tags=["workflow"],
    )
    def workflow_stage_rollback(
        workflow_id: str,
        body: WorkflowRollbackRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
        workflow_manager: WorkflowManager = Depends(workflow_manager_dependency),
    ) -> JSONResponse:
        workflow = workflow_manager.get(workflow_id)
        stage = workflow.find_stage(body.stage_id)
        if stage is None:
            from app.security.validator import ResourceNotFound
            raise ResourceNotFound(f"Stage '{body.stage_id}' was not found")
        rollback = RollbackManager(settings)
        return _register_pending(
            action="workflow_rollback", project=workflow.project,
            path=f"workflow/{workflow_id}#{stage.id}",
            payload={"workflow_id": workflow_id, "stage_id": stage.id}, reason=body.reason,
            preview_factory=lambda: __import__("json").dumps(rollback.preview(workflow_id, stage.id), ensure_ascii=False, indent=2),
            settings=settings, audit=audit, approvals=approvals,
            workflow_id=workflow_id, stage_id=stage.id,
        )

    # ---- Persistent agent sessions (Phase 8) --------------------------

    @app.get("/session/list", tags=["session"])
    def session_list(
        project: str | None = Query(default=None, min_length=1, max_length=100),
        manager: SessionManager = Depends(session_manager_dependency),
    ) -> dict[str, Any]:
        return {"sessions": [session.as_dict() for session in manager.list(project)]}

    @app.get("/session/{session_id}", tags=["session"])
    def session_detail(
        session_id: str,
        manager: SessionManager = Depends(session_manager_dependency),
    ) -> dict[str, Any]:
        return manager.get(session_id).as_dict()

    @app.post("/session/create", status_code=status.HTTP_202_ACCEPTED, tags=["session"])
    def session_create(
        body: SessionCreateRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
        workflow_manager: WorkflowManager = Depends(workflow_manager_dependency),
    ) -> JSONResponse:
        if body.workflow_id and body.stage_id:
            workflow_manager.validate_binding(body.workflow_id, body.stage_id, project=body.project)
        return _register_pending(
            action="session_create",
            project=body.project,
            path="session",
            payload={
                "workflow_id": body.workflow_id,
                "stage_id": body.stage_id,
                "approval_id": body.approval_id,
            },
            reason=body.reason or "Create persistent agent session",
            preview_factory=lambda: "CREATE session metadata only; no command execution",
            settings=settings,
            audit=audit,
            approvals=approvals,
            workflow_id=body.workflow_id,
            stage_id=body.stage_id,
        )

    @app.post("/session/{session_id}/transition", status_code=status.HTTP_202_ACCEPTED, tags=["session"])
    def session_transition(
        session_id: str,
        body: SessionTransitionRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
        manager: SessionManager = Depends(session_manager_dependency),
    ) -> JSONResponse:
        session = manager.get(session_id)
        return _register_pending(
            action="session_transition",
            project=session.project,
            path=f"session/{session.id}",
            payload={"session_id": session.id, "status": body.status},
            reason=body.reason or f"Transition session to {body.status.upper()}",
            preview_factory=lambda: f"{session.status.value} → {body.status.upper()} (metadata only)",
            settings=settings,
            audit=audit,
            approvals=approvals,
            workflow_id=session.workflow_id,
            stage_id=session.stage_id,
            session_id=session.id,
        )

    # ---- Multi-agent runtime (Phase 9) --------------------------------

    @app.post("/agent/create", status_code=status.HTTP_202_ACCEPTED, tags=["agent"])
    def agent_create(
        body: AgentCreateRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
        sessions: SessionManager = Depends(session_manager_dependency),
        workflows: WorkflowManager = Depends(workflow_manager_dependency),
    ) -> JSONResponse:
        session = sessions.get(body.session_id)
        if session.project != body.project:
            raise ValidationFailed("Agent project does not match session project")
        if body.workflow_id and body.stage_id:
            workflows.validate_binding(body.workflow_id, body.stage_id, project=body.project)
        elif body.workflow_id or body.stage_id:
            raise ValidationFailed("workflow_id and stage_id must be provided together")
        return _register_pending(
            action="agent_create",
            project=body.project,
            path=f"session/{body.session_id}/agent",
            payload={
                "session_id": body.session_id,
                "role": body.role,
                "memory_scope": body.memory_scope,
                "model_id": body.model_id,
                "permissions": body.permissions,
                "workflow_id": body.workflow_id,
                "stage_id": body.stage_id,
            },
            reason=body.reason or f"Create {body.role.upper()} agent",
            preview_factory=lambda: f"CREATE scoped {body.role.upper()} agent using model selection; no tool execution",
            settings=settings,
            audit=audit,
            approvals=approvals,
            workflow_id=body.workflow_id,
            stage_id=body.stage_id,
            session_id=body.session_id,
        )

    @app.post("/agent/{agent_id}/transition", status_code=status.HTTP_202_ACCEPTED, tags=["agent"])
    def agent_transition(
        agent_id: str,
        body: AgentTransitionRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
        manager: AgentManager = Depends(agent_manager_dependency),
    ) -> JSONResponse:
        agent = manager.get(agent_id)
        return _register_pending(
            action="agent_transition",
            project=agent.project,
            path=f"agent/{agent.id}",
            payload={"agent_id": agent.id, "status": body.status},
            reason=body.reason or f"Transition agent to {body.status.upper()}",
            preview_factory=lambda: f"{agent.status.value} → {body.status.upper()} (agent metadata only)",
            settings=settings,
            audit=audit,
            approvals=approvals,
            workflow_id=agent.workflow_id,
            stage_id=agent.stage_id,
            session_id=agent.session_id,
        )

    @app.post("/agent/message", status_code=status.HTTP_202_ACCEPTED, tags=["agent"])
    def agent_message(
        body: AgentMessageRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
        manager: AgentManager = Depends(agent_manager_dependency),
    ) -> JSONResponse:
        sender = manager.get(body.from_agent)
        receiver = manager.get(body.to_agent)
        if sender.project != receiver.project:
            raise ValidationFailed("Agents may only communicate within one project")
        return _register_pending(
            action="agent_message",
            project=sender.project,
            path=f"agent/{sender.id}->{receiver.id}",
            payload={
                "from_agent": sender.id,
                "to_agent": receiver.id,
                "task": body.task,
                "context_reference": body.context_reference,
            },
            reason=body.reason or "Deliver audited agent message",
            preview_factory=lambda: f"MESSAGE {sender.role.value} → {receiver.role.value}; task metadata only",
            settings=settings,
            audit=audit,
            approvals=approvals,
            workflow_id=sender.workflow_id,
            stage_id=sender.stage_id,
            session_id=sender.session_id,
        )

    # ---- Workflow (Phase 5) -------------------------------------------

    def _to_view(workflow) -> WorkflowView:
        data = workflow.as_dict()
        data["stages"] = [WorkflowStageView(**stage) for stage in data["stages"]]
        return WorkflowView(**data)

    @app.post(
        "/workflow/create",
        response_model=WorkflowView,
        status_code=status.HTTP_201_CREATED,
        tags=["workflow"],
    )
    def workflow_create(
        body: WorkflowCreateRequest,
        manager: WorkflowManager = Depends(workflow_manager_dependency),
    ) -> WorkflowView:
        workflow = manager.create(
            project=body.project, name=body.name, description=body.description
        )
        return _to_view(workflow)

    @app.get("/workflow/list", response_model=WorkflowListResponse, tags=["workflow"])
    def workflow_list(
        manager: WorkflowManager = Depends(workflow_manager_dependency),
    ) -> WorkflowListResponse:
        summaries = [item.as_dict() for item in manager.list()]
        return WorkflowListResponse(workflows=summaries)  # type: ignore[arg-type]

    @app.get(
        "/workflow/{workflow_id}", response_model=WorkflowView, tags=["workflow"]
    )
    def workflow_detail(
        workflow_id: str,
        manager: WorkflowManager = Depends(workflow_manager_dependency),
    ) -> WorkflowView:
        return _to_view(manager.get(workflow_id))

    @app.post(
        "/workflow/{workflow_id}/stage/start",
        response_model=WorkflowStageView,
        status_code=status.HTTP_201_CREATED,
        tags=["workflow"],
    )
    def workflow_stage_start(
        workflow_id: str,
        body: WorkflowStageStartRequest,
        manager: WorkflowManager = Depends(workflow_manager_dependency),
    ) -> WorkflowStageView:
        stage = manager.start_stage(workflow_id, body.stage_type)
        return WorkflowStageView(**stage.as_dict())

    @app.post(
        "/workflow/{workflow_id}/stage/report",
        response_model=WorkflowStageView,
        tags=["workflow"],
    )
    def workflow_stage_report(
        workflow_id: str,
        body: WorkflowStageReportRequest,
        manager: WorkflowManager = Depends(workflow_manager_dependency),
    ) -> WorkflowStageView:
        stage = manager.submit_report(
            workflow_id, body.stage_id, title=body.title, body=body.body
        )
        return WorkflowStageView(**stage.as_dict())

    @app.post(
        "/workflow/{workflow_id}/stage/attach",
        response_model=WorkflowStageView,
        tags=["workflow"],
    )
    def workflow_stage_attach(
        workflow_id: str,
        body: WorkflowActionAttachRequest,
        manager: WorkflowManager = Depends(workflow_manager_dependency),
    ) -> WorkflowStageView:
        stage = manager.attach_action(
            workflow_id=workflow_id,
            stage_id=body.stage_id,
            approval_request_id=body.request_id,
        )
        return WorkflowStageView(**stage.as_dict())

    @app.post("/workflow/{workflow_id}/stage/agent", status_code=status.HTTP_202_ACCEPTED, tags=["workflow"])
    def workflow_stage_agent(
        workflow_id: str,
        body: WorkflowAgentAttachRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
        workflows: WorkflowManager = Depends(workflow_manager_dependency),
        agents: AgentManager = Depends(agent_manager_dependency),
    ) -> JSONResponse:
        workflow, stage = workflows.validate_binding(workflow_id, body.stage_id)
        agent = agents.get(body.agent_id)
        if agent.project != workflow.project:
            raise ValidationFailed("Agent project does not match workflow project")
        return _register_pending(
            action="workflow_agent_attach",
            project=workflow.project,
            path=f"workflow/{workflow_id}#{stage.id}",
            payload={"workflow_id": workflow_id, "stage_id": stage.id, "agent_id": agent.id},
            reason=body.reason or f"Attach {agent.role.value} agent to stage",
            preview_factory=lambda: f"ATTACH {agent.id} ({agent.role.value}) to {stage.stage_type.value}; metadata only",
            settings=settings,
            audit=audit,
            approvals=approvals,
            workflow_id=workflow_id,
            stage_id=stage.id,
            session_id=agent.session_id,
        )

    @app.post("/workflow/{workflow_id}/quality-gate", status_code=status.HTTP_202_ACCEPTED, tags=["workflow"])
    def workflow_quality_gate(
        workflow_id: str,
        body: WorkflowQualityGateRequest,
        settings: Settings = Depends(settings_dependency),
        audit: AuditLogger = Depends(audit_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
        workflows: WorkflowManager = Depends(workflow_manager_dependency),
        agents: AgentManager = Depends(agent_manager_dependency),
    ) -> JSONResponse:
        workflow, stage = workflows.validate_binding(workflow_id, body.stage_id, project=None)
        reviewer = agents.get(body.reviewer_agent_id)
        tester = agents.get(body.tester_agent_id)
        if reviewer.project != workflow.project or tester.project != workflow.project:
            raise ValidationFailed("Quality gate agents must belong to the workflow project")
        if reviewer.role.value != "REVIEWER" or tester.role.value != "TESTER":
            raise ValidationFailed("Quality gate requires REVIEWER and TESTER agents")
        gate = build_quality_gate(
            review_status=body.review_status,
            test_passed=body.test_passed,
            risk_level=body.risk_level,
            risk_assessment=body.risk_assessment,
            reviewer_agent_id=reviewer.id,
            tester_agent_id=tester.id,
        )
        return _register_pending(
            action="quality_gate_submit",
            project=workflow.project,
            path=f"workflow/{workflow_id}#{stage.id}/quality-gate",
            payload={"workflow_id": workflow_id, "stage_id": stage.id, "quality_gate": gate},
            reason=body.reason or "Submit Review → Test → Risk quality gate",
            preview_factory=lambda: f"REVIEW={gate['reviewStatus']} TEST={gate['testPassed']} RISK={gate['riskLevel']}; human approval remains separate",
            settings=settings,
            audit=audit,
            approvals=approvals,
            workflow_id=workflow_id,
            stage_id=stage.id,
        )

    @app.post(
        "/workflow/{workflow_id}/stage/approve",
        response_model=WorkflowStageAwaitingResponse,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["workflow"],
    )
    def workflow_stage_await(
        workflow_id: str,
        body: WorkflowStageApprovalRequest,
        manager: WorkflowManager = Depends(workflow_manager_dependency),
        settings: Settings = Depends(settings_dependency),
        approvals: ApprovalStore = Depends(approvals_dependency),
    ) -> WorkflowStageAwaitingResponse:
        workflow, stage, approval = manager.request_stage_approval(
            workflow_id, body.stage_id, reason=body.reason
        )
        queued_memory: list[str] = []
        if body.sync_memory:
            memory_manager = MemoryManager(settings)
            queued_memory = workflow_memory_agent(
                approvals, memory_manager, workflow, stage
            )
        approval_payload = approval.as_dict()
        approval_payload["memoryApprovalIds"] = queued_memory
        return WorkflowStageAwaitingResponse(
            workflow=_to_view(workflow),
            stage=WorkflowStageView(**stage.as_dict()),
            approval=approval_payload,
        )

    @app.post(
        "/workflow/{workflow_id}/cancel",
        response_model=WorkflowView,
        tags=["workflow"],
    )
    def workflow_cancel(
        workflow_id: str,
        body: WorkflowCancelRequest,
        manager: WorkflowManager = Depends(workflow_manager_dependency),
    ) -> WorkflowView:
        workflow = manager.cancel(workflow_id, reason=body.reason)
        return _to_view(workflow)

    @app.get("/audit/log", response_model=AuditLogResponse, tags=["system"])
    def audit_log(
        limit: int = Query(default=100, ge=1, le=1000),
        audit: AuditLogger = Depends(audit_dependency),
    ) -> AuditLogResponse:
        return AuditLogResponse(entries=audit.read_entries(limit), logFile=str(audit.log_file))

    return app


app = create_app()


def run() -> None:  # pragma: no cover - manual entrypoint
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.bridge_host,
        port=settings.bridge_port,
        reload=False,
    )


if __name__ == "__main__":  # pragma: no cover
    run()
