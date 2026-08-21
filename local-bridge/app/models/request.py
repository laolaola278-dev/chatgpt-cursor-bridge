"""Request payload models."""

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Any


class FileCreateRequest(BaseModel):
    project: str = Field(..., min_length=1, max_length=100, description="Project directory name")
    path: str = Field(..., min_length=1, max_length=1024, description="Project relative file path")
    content: str = Field(default="", description="Full UTF-8 file content")
    reason: str = Field(default="", max_length=500, description="Why the change is required")


class FileWriteRequest(BaseModel):
    project: str = Field(..., min_length=1, max_length=100)
    path: str = Field(..., min_length=1, max_length=1024)
    content: str = Field(default="", description="Full UTF-8 replacement content")
    reason: str = Field(default="", max_length=500)


class PatchApplyRequest(BaseModel):
    project: str = Field(..., min_length=1, max_length=100)
    path: str = Field(..., min_length=1, max_length=1024)
    patch: str = Field(..., min_length=1, description="Unified diff limited to a single file")
    reason: str = Field(default="", max_length=500)


class ApprovalDecisionRequest(BaseModel):
    request_id: str = Field(..., min_length=4, max_length=64, description="Pending approval id")


class ApprovalReconfirmRequest(BaseModel):
    request_id: str = Field(..., min_length=4, max_length=64, description="Recovered approval id")


class ApprovalRejectRequest(BaseModel):
    request_id: str = Field(..., min_length=4, max_length=64, description="Approval id")
    reason: str = Field(default="Rejected by user", max_length=500)


class SessionCreateRequest(BaseModel):
    project: str = Field(..., min_length=1, max_length=100)
    workflow_id: str | None = Field(default=None, min_length=4, max_length=64)
    stage_id: str | None = Field(default=None, min_length=4, max_length=64)
    approval_id: str | None = Field(default=None, min_length=4, max_length=64)
    reason: str = Field(default="", max_length=500)


class SessionTransitionRequest(BaseModel):
    status: str = Field(..., min_length=1, max_length=32)
    reason: str = Field(default="", max_length=500)


class AgentCreateRequest(BaseModel):
    project: str = Field(..., min_length=1, max_length=100)
    session_id: str = Field(..., min_length=4, max_length=64)
    role: str = Field(..., min_length=1, max_length=32)
    memory_scope: str = Field(default="project", min_length=1, max_length=200)
    model_id: str | None = Field(default=None, max_length=100)
    permissions: list[str] | None = Field(default=None, max_length=20)
    workflow_id: str | None = Field(default=None, min_length=4, max_length=64)
    stage_id: str | None = Field(default=None, min_length=4, max_length=64)
    reason: str = Field(default="", max_length=500)


class AgentTransitionRequest(BaseModel):
    status: str = Field(..., min_length=1, max_length=32)
    reason: str = Field(default="", max_length=500)


class AgentMessageRequest(BaseModel):
    from_agent: str = Field(..., min_length=4, max_length=64)
    to_agent: str = Field(..., min_length=4, max_length=64)
    task: str = Field(..., min_length=1, max_length=4000)
    context_reference: str = Field(default="", max_length=500)
    reason: str = Field(default="", max_length=500)


class WorkflowAgentAttachRequest(BaseModel):
    stage_id: str = Field(..., min_length=4, max_length=64)
    agent_id: str = Field(..., min_length=4, max_length=64)
    reason: str = Field(default="", max_length=500)


class WorkflowQualityGateRequest(BaseModel):
    stage_id: str = Field(..., min_length=4, max_length=64)
    review_status: str = Field(default="approved", max_length=32)
    test_passed: bool
    risk_level: str = Field(..., min_length=1, max_length=16)
    risk_assessment: str = Field(..., min_length=1, max_length=4000)
    reviewer_agent_id: str = Field(..., min_length=4, max_length=64)
    tester_agent_id: str = Field(..., min_length=4, max_length=64)
    reason: str = Field(default="", max_length=500)


class MemoryInitRequest(BaseModel):
    project: str = Field(..., min_length=1, max_length=100)
    reason: str = Field(default="", max_length=500)


class MemoryAppendRequest(BaseModel):
    project: str = Field(..., min_length=1, max_length=100)
    document: str = Field(..., min_length=1, max_length=64, description="Whitelisted memory doc")
    content: str = Field(..., min_length=1, description="Markdown section to append")
    reason: str = Field(default="", max_length=500)


class MemoryDecisionRequest(BaseModel):
    project: str = Field(..., min_length=1, max_length=100)
    title: str = Field(..., min_length=1, max_length=200)
    context: str = Field(..., min_length=1, max_length=4000)
    decision: str = Field(..., min_length=1, max_length=4000)
    consequence: str = Field(..., min_length=1, max_length=4000)
    reason: str = Field(default="", max_length=500)


class WorkflowCreateRequest(BaseModel):
    project: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)


class WorkflowStageStartRequest(BaseModel):
    stage_type: str = Field(..., min_length=1, max_length=64)


class WorkflowStageReportRequest(BaseModel):
    stage_id: str = Field(..., min_length=4, max_length=64)
    title: str = Field(..., min_length=1, max_length=200)
    body: str = Field(..., min_length=1)


class WorkflowStageApprovalRequest(BaseModel):
    stage_id: str = Field(..., min_length=4, max_length=64)
    reason: str = Field(default="", max_length=500)
    sync_memory: bool = Field(default=False, description="Queue memory writes as approvals")


class WorkflowActionAttachRequest(BaseModel):
    stage_id: str = Field(..., min_length=4, max_length=64)
    request_id: str = Field(..., min_length=4, max_length=64)


class WorkflowCancelRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


class GitCommitRequest(BaseModel):
    project: str = Field(..., min_length=1, max_length=100)
    message: str = Field(..., min_length=1, max_length=500)
    workflow_id: str = Field(..., min_length=4, max_length=64)
    stage_id: str = Field(..., min_length=4, max_length=64)
    reason: str = Field(default="", max_length=500)


class TestRunRequest(BaseModel):
    project: str = Field(..., min_length=1, max_length=100)
    workflow_id: str = Field(..., min_length=4, max_length=64)
    stage_id: str = Field(..., min_length=4, max_length=64)
    command: str = Field(..., min_length=1, max_length=100)
    reason: str = Field(default="", max_length=500)


class WorkflowRollbackRequest(BaseModel):
    stage_id: str = Field(..., min_length=4, max_length=64)
    reason: str = Field(..., min_length=1, max_length=500)


class RuntimeCreateRequest(BaseModel):
    agent_id: str = Field(..., min_length=4, max_length=64)
    session_id: str = Field(..., min_length=4, max_length=64)
    workflow_id: str = Field(..., min_length=4, max_length=64)
    stage_id: str = Field(..., min_length=4, max_length=64)
    reason: str = Field(default="Create autonomous runtime metadata", max_length=500)


class TaskCreateRequest(BaseModel):
    workflow_id: str = Field(..., min_length=4, max_length=64)
    stage_id: str = Field(..., min_length=4, max_length=64)
    agent_id: str = Field(..., min_length=4, max_length=64)
    priority: int = Field(default=0, ge=0, le=100)
    context: dict[str, object] = Field(default_factory=dict)
    reason: str = Field(default="Create persistent task", max_length=500)


class TaskTransitionRequest(BaseModel):
    status: str = Field(..., min_length=1, max_length=32)
    reason: str = Field(default="Transition task", max_length=500)


class TeamCreateRequest(BaseModel):
    workflow_id: str = Field(..., min_length=4, max_length=64)
    members: list[str] = Field(..., min_length=2, max_length=5)
    leader: str = Field(..., min_length=4, max_length=64)
    reason: str = Field(default="Create human-supervised agent team", max_length=500)


class CodeIndexRequest(BaseModel):
    project: str = Field(..., min_length=1, max_length=100)
    reason: str = Field(default="Build read-only code intelligence index", max_length=500)


class ProjectMemoryProposalRequest(BaseModel):
    project: str = Field(..., min_length=1, max_length=100)
    category: str = Field(..., min_length=1, max_length=32)
    content: str = Field(..., min_length=1, max_length=65536)
    reason: str = Field(default="Record project intelligence memory proposal", max_length=500)


class IntelligenceAnalyzeRequest(BaseModel):
    project: str = Field(..., min_length=1, max_length=100)
    changed_files: list[str] = Field(default_factory=list, max_length=200)
    test_coverage: int | None = Field(default=None, ge=0, le=100)
    security_sensitive: bool = False
    reason: str = Field(default="Analyze engineering risks and generate proposals", max_length=500)


class SimulationCreateRequest(BaseModel):
    project: str = Field(..., min_length=1, max_length=100)
    problem: str = Field(..., min_length=1, max_length=6000)
    reason: str = Field(default="Create engineering simulation", max_length=500)


class SimulationAnalyzeRequest(BaseModel):
    test_coverage: int | None = Field(default=None, ge=0, le=100)
    proposal_id: str | None = Field(default=None, min_length=4, max_length=100)
    reason: str = Field(default="Analyze candidate engineering scenarios", max_length=500)


class SimulationPlanRequest(BaseModel):
    scenario_id: str = Field(..., min_length=4, max_length=100)
    reason: str = Field(default="Generate an approval-aware engineering plan", max_length=500)


class IntelligenceDecisionCreateRequest(BaseModel):
    project: str = Field(..., min_length=1, max_length=100)
    proposal_id: str = Field(..., min_length=4, max_length=100)
    simulation_id: str | None = Field(default=None, min_length=4, max_length=100)
    selected_scenario: str | None = Field(default=None, min_length=4, max_length=100)
    confidence: float | None = Field(default=None, ge=0, le=1)
    alternatives: list[str] = Field(default_factory=list, max_length=20)
    title: str = Field(..., min_length=1, max_length=300)
    context: str = Field(..., min_length=1, max_length=6000)
    options: list[dict[str, str]] = Field(..., min_length=2, max_length=10)
    recommendation: str = Field(..., min_length=1, max_length=300)
    implementation_plan_id: str | None = Field(default=None, min_length=4, max_length=100)
    execution_status: str | None = Field(default=None, max_length=32)
    reason: str = Field(default="Create human-reviewed engineering decision", max_length=500)


class ExecutionCreateRequest(BaseModel):
    project: str = Field(..., min_length=1, max_length=100)
    plan_id: str = Field(..., min_length=4, max_length=100)
    workflow_id: str | None = Field(default=None, min_length=4, max_length=64)
    reason: str = Field(default="Create approval-gated implementation tasks from an approved plan", max_length=500)


class ExecutionProposalRequest(BaseModel):
    reason: str = Field(default="Generate a controlled execution proposal", max_length=500)


class ExecutionExecuteRequest(BaseModel):
    reason: str = Field(default="Execute an approved proposal under human control", max_length=500)


class ExecutionLoopCreateRequest(BaseModel):
    project: str = Field(..., min_length=1, max_length=100)
    plan_id: str = Field(..., min_length=4, max_length=100)
    workflow_id: str | None = Field(default=None, min_length=4, max_length=64)
    reason: str = Field(default="Create an approval-controlled engineering loop", max_length=500)


class ExecutionLoopActionRequest(BaseModel):
    quality_score: int | None = Field(default=None, ge=0, le=100, description="Observed quality score for verification")
    risk_score: int | None = Field(default=None, ge=0, le=100, description="Observed risk score for verification")
    test_passed: bool | None = Field(default=None, description="Whether the observed tests passed")
    reason: str = Field(default="Advance the engineering loop under approval control", max_length=500)


class ExecutionDagCreateRequest(BaseModel):
    project: str = Field(..., min_length=1, max_length=100)
    loop_ids: list[str] = Field(..., min_length=1, max_length=100)
    edges: list[dict[str, str]] = Field(default_factory=list, max_length=500)
    reason: str = Field(default="Create an approval-controlled execution DAG", max_length=500)


class ExecutionDagActionRequest(BaseModel):
    reason: str = Field(default="Advance the execution DAG under approval control", max_length=500)


class EngineeringGraphBuildRequest(BaseModel):
    project: str = Field(..., min_length=1, max_length=100)
    reason: str = Field(default="Rebuild the read-only engineering knowledge graph", max_length=500)


class EvolutionAppendRequest(BaseModel):
    project: str = Field(..., min_length=1, max_length=100)
    kind: str = Field(..., min_length=1, max_length=32)
    title: str = Field(..., min_length=1, max_length=300)
    content: str = Field(..., min_length=1, max_length=12000)
    source_id: str | None = Field(default=None, max_length=100)
    reason: str = Field(default="Record approved engineering evolution memory", max_length=500)


class BenchmarkCreateRequest(BaseModel):
    project: str = Field(..., min_length=1, max_length=100)
    repository: str = Field(..., min_length=1, max_length=500)
    cases: list[dict[str, str]] = Field(default_factory=list, max_length=200)
    reason: str = Field(default="Create a record-only benchmark", max_length=500)


class BenchmarkTransitionRequest(BaseModel):
    status: str = Field(..., min_length=1, max_length=32)
    reason: str = Field(default="Transition benchmark metadata", max_length=500)


class ValidationCreateRequest(BaseModel):
    project: str = Field(..., min_length=1, max_length=100)
    repository: str = Field(..., min_length=1, max_length=500)
    language: str = Field(default="unknown", max_length=40)
    framework: str = Field(default="unknown", max_length=40)
    scenarios: list[dict[str, str]] = Field(default_factory=list, max_length=100)
    reason: str = Field(default="Create record-only validation metadata", max_length=500)


class ValidationTransitionRequest(BaseModel):
    status: str = Field(..., min_length=1, max_length=32)
    reason: str = Field(default="Transition validation metadata", max_length=500)


class ValidationRunRequest(BaseModel):
    scenario_id: str = Field(..., min_length=4, max_length=100)
    workflow_id: str | None = Field(default=None, max_length=64)
    execution_loop_id: str | None = Field(default=None, max_length=100)
    agents: list[str] = Field(default_factory=list, max_length=20)
    result: str = Field(default="RECORDED", max_length=32)
    human_rating: float | None = Field(default=None, ge=0, le=100)
    reason: str = Field(default="Record validation run metadata", max_length=500)


class DemoScenarioCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    issue: str = Field(..., min_length=1, max_length=6000)
    reason: str = Field(default="Create record-only demo scenario", max_length=500)


class ReplayCreateRequest(BaseModel):
    project: str = Field(..., min_length=1, max_length=100)
    title: str = Field(..., min_length=1, max_length=300)
    reason: str = Field(default="Build engineering replay timeline", max_length=500)


class ExportCreateRequest(BaseModel):
    project: str = Field(..., min_length=1, max_length=100)
    kind: str = Field(..., min_length=1, max_length=32)
    payload: dict[str, Any] = Field(default_factory=dict)
    markdown: str = Field(default="", max_length=60000)
    reason: str = Field(default="Export engineering artifact", max_length=500)


class GovernanceDebtCreateRequest(BaseModel):
    project: str = Field(..., min_length=1, max_length=100)
    category: str = Field(..., min_length=1, max_length=40)
    severity: str = Field(..., min_length=1, max_length=16)
    source: str = Field(..., min_length=1, max_length=1000)
    affected_components: list[str] = Field(default_factory=list, max_length=100)
    estimated_cost: int = Field(default=0, ge=0, le=1000000)
    risk: str = Field(default="low", max_length=16)
    reason: str = Field(default="Create record-only technical debt item", max_length=500)


class GovernanceDebtTransitionRequest(BaseModel):
    status: str = Field(..., min_length=1, max_length=32)
    reason: str = Field(default="Transition technical debt metadata", max_length=500)


class GovernancePolicyEvaluateRequest(BaseModel):
    project: str = Field(..., min_length=1, max_length=100)
    signal: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(default="Evaluate engineering policies against governance signals", max_length=500)


class GovernanceTimelineAppendRequest(BaseModel):
    project: str = Field(..., min_length=1, max_length=100)
    category: str = Field(..., min_length=1, max_length=32)
    content: str = Field(..., min_length=1, max_length=12000)
    reason: str = Field(default="Record approved governance timeline memory", max_length=500)


class OrganizationEntityCreateRequest(BaseModel):
    type: str = Field(..., min_length=1, max_length=32)
    name: str = Field(..., min_length=1, max_length=200)
    parent_id: str | None = Field(default=None, max_length=100)
    metadata: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(default="Register organization graph entity", max_length=500)


class OrganizationIncidentCreateRequest(BaseModel):
    project: str = Field(..., min_length=1, max_length=100)
    title: str = Field(..., min_length=1, max_length=200)
    summary: str = Field(..., min_length=1, max_length=4000)
    severity: str = Field(default="medium", max_length=16)
    service: str = Field(default="", max_length=200)
    signature: str = Field(default="", max_length=1000)
    reason: str = Field(default="Create record-only incident", max_length=500)


class OrganizationDecisionCreateRequest(BaseModel):
    project: str = Field(..., min_length=1, max_length=100)
    title: str = Field(..., min_length=1, max_length=200)
    context: str = Field(..., min_length=1, max_length=4000)
    decision: str = Field(..., min_length=1, max_length=4000)
    consequence: str = Field(..., min_length=1, max_length=4000)
    reason: str = Field(default="Create record-only org architecture decision", max_length=500)


class OrganizationPatternCreateRequest(BaseModel):
    category: str = Field(..., min_length=1, max_length=32)
    name: str = Field(..., min_length=1, max_length=200)
    summary: str = Field(..., min_length=1, max_length=4000)
    project: str = Field(..., min_length=1, max_length=100)
    tags: list[str] = Field(default_factory=list, max_length=20)
    reason: str = Field(default="Record enterprise engineering pattern", max_length=500)


class OrganizationLearningScanRequest(BaseModel):
    project: str = Field(..., min_length=1, max_length=100)
    reason: str = Field(default="Scan project for cross-project failure learning", max_length=500)


class OrganizationGraphSyncRequest(BaseModel):
    reason: str = Field(default="Sync organization entities into the reasoning graph", max_length=500)


class OrganizationGraphSnapshotCreateRequest(BaseModel):
    reason: str = Field(default="Create organization graph snapshot", max_length=500)


class OrganizationGraphSnapshotRestoreRequest(BaseModel):
    snapshot_id: str = Field(..., min_length=1, max_length=100)
    reason: str = Field(default="Restore organization graph snapshot", max_length=500)


class OrganizationStrategyCreateRequest(BaseModel):
    strategy_type: str = Field(..., min_length=1, max_length=32)
    title: str = Field(..., min_length=1, max_length=200)
    problem: str = Field(..., min_length=1, max_length=4000)
    affected_projects: list[str] = Field(default_factory=list, max_length=50)
    affected_teams: list[str] = Field(default_factory=list, max_length=50)
    benefits: list[str] = Field(default_factory=list, max_length=20)
    risks: list[str] = Field(default_factory=list, max_length=20)
    estimated_effort: str = Field(default="", max_length=200)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    priority: str = Field(default="medium", max_length=16)
    alternatives: list[str] = Field(default_factory=list, max_length=20)
    evidence: list[str] = Field(default_factory=list, max_length=20)
    reason: str = Field(default="Create organization engineering strategy proposal", max_length=500)


class OrganizationStrategyEvaluateRequest(BaseModel):
    strategy_ids: list[str] = Field(..., min_length=1, max_length=20)
    reason: str = Field(default="Evaluate organization strategy candidates", max_length=500)


class OrganizationStrategyDecisionCreateRequest(BaseModel):
    organization_id: str = Field(default="organization", max_length=100)
    title: str = Field(..., min_length=1, max_length=200)
    strategy_id: str = Field(..., min_length=1, max_length=100)
    source_graph_nodes: list[str] = Field(default_factory=list, max_length=100)
    alternatives: list[str] = Field(default_factory=list, max_length=20)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    impact_report: dict[str, object] = Field(default_factory=dict)
    risk_report: dict[str, object] = Field(default_factory=dict)
    reason: str = Field(default="Create organization decision", max_length=500)


class OrganizationStrategyDecisionTransitionRequest(BaseModel):
    decision_id: str = Field(..., min_length=1, max_length=100)
    status: str = Field(..., min_length=1, max_length=32)
    reason: str = Field(default="Transition organization decision", max_length=500)


class OrganizationStrategyMemoryAppendRequest(BaseModel):
    organization: str = Field(..., min_length=1, max_length=100)
    category: str = Field(..., min_length=1, max_length=32)
    content: str = Field(..., min_length=1, max_length=12000)
    reason: str = Field(default="Append organization strategy memory", max_length=500)


# ---------------------------------------------------------------------------
# Phase 25 · Engineering Intelligence Evolution
# ---------------------------------------------------------------------------

class IntelligenceObservationRecordRequest(BaseModel):
    project_id: str = Field(..., min_length=1, max_length=100)
    type: str = Field(..., min_length=1, max_length=40)
    source: str = Field(..., min_length=1, max_length=500)
    summary: str = Field(..., min_length=1, max_length=4000)
    metadata: dict[str, Any] = Field(default_factory=dict)
    risk_level: str = Field(default="low", max_length=16)
    reason: str = Field(default="Record an engineering observation", max_length=500)


class IntelligencePatternAnalyzeRequest(BaseModel):
    project_id: str = Field(..., min_length=1, max_length=100)
    limit: int = Field(default=500, ge=1, le=2000)
    reason: str = Field(default="Analyze project observations for recurring patterns", max_length=500)


class IntelligencePredictionAnalyzeRequest(BaseModel):
    project_id: str = Field(..., min_length=1, max_length=100)
    limit: int = Field(default=500, ge=1, le=2000)
    reason: str = Field(default="Generate evidence-backed engineering risk predictions", max_length=500)


class IntelligenceOutcomeRecordRequest(BaseModel):
    project_id: str = Field(..., min_length=1, max_length=100)
    strategy_id: str = Field(..., min_length=1, max_length=200)
    decision_id: str | None = Field(default=None, max_length=200)
    status: str = Field(..., min_length=1, max_length=32)
    expected_outcome: str = Field(..., min_length=1, max_length=4000)
    actual_outcome: str = Field(..., min_length=1, max_length=4000)
    difference: str = Field(default="", max_length=4000)
    evidence: list[str] = Field(default_factory=list, max_length=100)
    source: str = Field(default="user_decision", max_length=100)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    reason: str = Field(default="Record a human-reviewed strategy outcome", max_length=500)


class IntelligenceKnowledgeProposalRequest(BaseModel):
    project_id: str = Field(..., min_length=1, max_length=100)
    category: str = Field(..., min_length=1, max_length=32)
    content: str = Field(..., min_length=1, max_length=12000)
    source: str = Field(default="", max_length=500)
    evidence: list[str] = Field(default_factory=list, max_length=100)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(default="Propose intelligence knowledge for human approval", max_length=500)


class IntelligenceEvidenceBundleRequest(BaseModel):
    project_id: str = Field(..., min_length=1, max_length=100)
    decision_id: str | None = Field(default=None, max_length=200)
    observation_ids: list[str] = Field(default_factory=list, max_length=100)
    pattern_ids: list[str] = Field(default_factory=list, max_length=100)
    prediction_ids: list[str] = Field(default_factory=list, max_length=100)
    risk_ids: list[str] = Field(default_factory=list, max_length=100)
    strategy_ids: list[str] = Field(default_factory=list, max_length=100)
    recommendation_ids: list[str] = Field(default_factory=list, max_length=100)
    historical_evidence: list[str] = Field(default_factory=list, max_length=100)
    provenance: list[str] = Field(default_factory=list, max_length=100)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason: str = Field(default="Create a decision evidence bundle", max_length=500)


# ---------------------------------------------------------------------------
# Phase 27 · Engineering Intelligence Validation Layer
# ---------------------------------------------------------------------------

class IntelligenceEvaluationRecordRequest(BaseModel):
    project_id: str = Field(..., min_length=1, max_length=100)
    prediction_id: str = Field(..., min_length=1, max_length=200)
    evaluation_kind: str = Field(..., min_length=1, max_length=40)
    input_context: str = Field(default="", max_length=12000)
    prediction_result: str = Field(..., min_length=1, max_length=12000)
    expected_outcome: str = Field(..., min_length=1, max_length=12000)
    actual_outcome: str = Field(..., min_length=1, max_length=12000)
    evaluation_result: str = Field(..., min_length=1, max_length=16)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    agent_id: str | None = Field(default=None, max_length=200)
    model_id: str | None = Field(default=None, max_length=200)
    decision_id: str | None = Field(default=None, max_length=200)
    recommendation_id: str | None = Field(default=None, max_length=200)
    evidence: list[str] = Field(default_factory=list, max_length=100)
    reason: str = Field(default="Record a traceable intelligence evaluation", max_length=500)


class IntelligenceBenchmarkRunRequest(BaseModel):
    project_id: str = Field(..., min_length=1, max_length=100)
    dataset_id: str = Field(..., min_length=1, max_length=200)
    model_id: str = Field(default="deterministic", max_length=200)
    predictions: list[str] = Field(default_factory=list, max_length=500)
    reason: str = Field(default="Run a deterministic intelligence benchmark", max_length=500)


class IntelligenceKnowledgeImprovementRequest(BaseModel):
    project_id: str = Field(..., min_length=1, max_length=100)
    evaluation_id: str = Field(..., min_length=1, max_length=200)
    prediction_id: str = Field(..., min_length=1, max_length=200)
    category: str = Field(..., min_length=1, max_length=32)
    content: str = Field(..., min_length=1, max_length=12000)
    source: str = Field(default="evaluation_feedback", max_length=500)
    evidence: list[str] = Field(default_factory=list, max_length=100)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason: str = Field(default="Propose a knowledge improvement for human approval", max_length=500)


# ---------------------------------------------------------------------------
# Phase 28 · Engineering Intelligence Governance Layer
# ---------------------------------------------------------------------------

class IntelligenceGovernanceEvaluateRequest(BaseModel):
    project_id: str = Field(..., min_length=1, max_length=100)
    source_kind: str = Field(..., min_length=1, max_length=32)
    source_id: str = Field(..., min_length=1, max_length=200)
    agent_id: str = Field(default="", max_length=200)
    model_id: str = Field(default="", max_length=200)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    evaluation_result: str = Field(default="", max_length=32)
    risk_level: str = Field(default="LOW", max_length=16)
    risk_score: float = Field(default=0.0, ge=0.0, le=100.0)
    context: str = Field(default="", max_length=12000)
    evidence: list[str] = Field(default_factory=list, max_length=100)
    reason: str = Field(default="Evaluate an intelligence claim against governance rules", max_length=500)


class ContextPatchProposalRequest(BaseModel):
    """Phase 30 · Structured Patch Proposal (record-only, never applies)."""

    project: str = Field(..., min_length=1, max_length=100)
    agent: str = Field(default="ASSISTANT", max_length=64)
    target_file: str = Field(..., min_length=1, max_length=500)
    target_symbol: str = Field(default="", max_length=200)
    proposed_change: str = Field(..., min_length=1, max_length=4000)
    reason: str = Field(..., min_length=1, max_length=2000)
    expected_impact: str = Field(default="", max_length=2000)
    risk: str = Field(default="medium", max_length=16)


class IntelligenceGovernanceReviewRequest(BaseModel):
    project_id: str = Field(..., min_length=1, max_length=100)
    proposal_id: str = Field(..., min_length=1, max_length=200)
    decision: str = Field(..., min_length=1, max_length=16, description="approved | rejected")
    reviewer_note: str = Field(default="", max_length=4000)
    reason: str = Field(default="Record a human governance review outcome", max_length=500)


class LlmMessageItem(BaseModel):
    """One message in the unified protocol (system / user / assistant / tool)."""

    role: str = Field(..., min_length=1, max_length=16)
    content: str = Field(default="", max_length=12000)
    name: str = Field(default="", max_length=100)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)


class LlmChatRequest(BaseModel):
    """Phase 31 · Stateless chat request. No persistence, no execution."""

    project: str = Field(..., min_length=1, max_length=100)
    messages: list[LlmMessageItem] = Field(..., min_length=1, max_length=100)
    model: str = Field(default="local/simulator-v1", max_length=200)
    provider: str = Field(default="", max_length=64)
    agent: str = Field(default="", max_length=64)
    temperature: float = Field(default=0.4, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, ge=16, le=16384)


class LlmConversationCreateRequest(BaseModel):
    """Phase 31 · Create a persisted conversation (approval-gated)."""

    project: str = Field(..., min_length=1, max_length=100)
    provider: str = Field(default="local", max_length=64)
    model: str = Field(default="local/simulator-v1", max_length=200)
    title: str = Field(..., min_length=1, max_length=200)
    agent: str = Field(default="", max_length=64)
    reason: str = Field(default="Create a conversation record for the LLM gateway", max_length=500)


class LlmConversationMessageRequest(BaseModel):
    """Phase 31 · Append a user message to a conversation (approval-gated)."""

    project: str = Field(..., min_length=1, max_length=100)
    content: str = Field(..., min_length=1, max_length=12000)
    agent: str = Field(default="", max_length=64)
    model: str = Field(default="", max_length=200)
    provider: str = Field(default="", max_length=64)
    reason: str = Field(default="Append a message to the conversation history", max_length=500)


class LlmToolProposalRequest(BaseModel):
    """Phase 31 · Record a model-requested tool call (approval-gated, never executes)."""

    project: str = Field(..., min_length=1, max_length=100)
    message_id: str = Field(..., min_length=1, max_length=200)
    tool_name: str = Field(..., min_length=1, max_length=200)
    arguments: str = Field(default="{}", max_length=8000)
    reason: str = Field(..., min_length=1, max_length=2000)


# ---------------------------------------------------------------------------
# Phase 32 · AI Assistant Productization
# ---------------------------------------------------------------------------

class ProviderConfigRequest(BaseModel):
    """Phase 32 · Submit a provider credential (approval-gated activation).

    ``api_key`` is consumed by the Bridge, encrypted with AES-256-GCM and
    dropped: it is never echoed back, never logged and never placed in the
    approval payload.
    """

    provider: str = Field(..., min_length=1, max_length=64)
    model: str = Field(default="", max_length=200)
    base_url: str = Field(default="", max_length=500)
    api_key: str = Field(default="", max_length=500, repr=False)
    keep_existing_key: bool = Field(default=False)
    reason: str = Field(default="Configure an LLM provider credential", max_length=500)


class ProviderForgetRequest(BaseModel):
    """Phase 32 · Delete every stored credential for one provider."""

    provider: str = Field(..., min_length=1, max_length=64)
    reason: str = Field(default="Forget the stored provider credential", max_length=500)


class ProviderTestRequest(BaseModel):
    """Phase 32 · One minimal connection probe.

    The response is limited to Connected / Failed / Not configured; no provider
    body, header or key material is returned.
    """

    provider: str = Field(..., min_length=1, max_length=64)
    model: str = Field(default="", max_length=200)
    api_key: str = Field(default="", max_length=500, repr=False)


class UserSettingsUpdateRequest(BaseModel):
    """Phase 32 · Update non-sensitive preferences (approval-gated)."""

    mode: str = Field(default="", max_length=16, description="user | developer")
    selected_provider: str = Field(default="", max_length=64)
    selected_model: str = Field(default="", max_length=200)
    onboarding_state: str = Field(default="", max_length=64)
    theme: str = Field(default="", max_length=32)
    language: str = Field(default="", max_length=32)
    reason: str = Field(default="Update assistant preferences", max_length=500)


class AssistantWebContextRequest(BaseModel):
    """Phase 32 · A user-approved page snapshot.

    ``trigger`` must be ``ask_ai`` and ``consented_at`` must be present: the
    Bridge rejects any bundle that a page load or refresh could have produced.
    """

    trigger: str = Field(default="", max_length=32)
    consented_at: str = Field(default="", max_length=64)
    page_title: str = Field(default="", max_length=300)
    page_url: str = Field(default="", max_length=2000)
    selected_text: str = Field(default="", max_length=8000)
    readable_content: str = Field(default="", max_length=20000)
    timestamp: str = Field(default="", max_length=64)


class AssistantChatRequest(BaseModel):
    """Phase 32 · Assistant chat. Stateless, read-only, never executes tools."""

    project: str = Field(..., min_length=1, max_length=100)
    messages: list[LlmMessageItem] = Field(..., min_length=1, max_length=100)
    provider: str = Field(default="", max_length=64)
    model: str = Field(default="", max_length=200)
    temperature: float = Field(default=0.4, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, ge=16, le=16384)
    web_context: AssistantWebContextRequest | None = Field(default=None)
