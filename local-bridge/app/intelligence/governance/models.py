"""Phase 28 · Engineering Intelligence Governance Layer data models.

Every governance record is traceable, auditable, reproducible, and isolated
by project and agent. None of these records authorizes an action: the
governance layer only observes, analyzes, classifies, recommends, and
proposes. All persistent writes are queued through the existing ApprovalStore
before execution, and the layer never mutates policy, knowledge, memory, or
source code on its own.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from secrets import token_hex
from typing import Any

from app.intelligence.common import bounded_confidence, ensure_project, ids, sanitize_text, utc_now
from app.security.validator import ValidationFailed


class GovernanceKind(str, Enum):
    """What kind of intelligence claim is being governed."""

    PREDICTION = "prediction"
    RECOMMENDATION = "recommendation"
    DECISION = "decision"
    RISK = "risk"
    MODEL = "model"
    CONTEXT = "context"


GOVERNANCE_KINDS = {item.value for item in GovernanceKind}


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


RISK_LEVELS = {item.value for item in RiskLevel}
RISK_ORDER = {item.value: index for index, item in enumerate(RiskLevel)}


class GovernanceResult(str, Enum):
    """Result of a governance evaluation.

    The rule engine only ever produces PASS / WARNING / REVIEW_REQUIRED. The
    BLOCKED state is reserved for Quality Gate 14.0, which may prevent the
    downstream flow of an intelligence proposal.
    """

    PASS = "PASS"
    WARNING = "WARNING"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    BLOCKED = "BLOCKED"


GOVERNANCE_RESULTS = {item.value for item in GovernanceResult}


class PolicySeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    BLOCKING = "blocking"


class ReviewStatus(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"


REVIEW_STATUSES = {item.value for item in ReviewStatus}


class GovernanceMemoryCategory(str, Enum):
    FINDING = "finding"
    RISK = "risk"
    QUALITY = "quality"
    POLICY_VIOLATION = "policy_violation"
    REVIEW = "review"
    HISTORY = "history"


GOVERNANCE_MEMORY_CATEGORIES = {item.value for item in GovernanceMemoryCategory}


@dataclass(frozen=True)
class GovernanceRecord:
    """Unified governance evaluation for any intelligence claim.

    ``governance_result`` is derived deterministically from the rule engine.
    ``audit_request_id`` records the ApprovalStore request that authorized the
    write, keeping the governance boundary auditable.
    """

    governance_id: str
    project_id: str
    source_kind: str
    source_id: str
    risk_level: str
    risk_score: float
    confidence: float
    governance_result: str
    agent_id: str = ""
    model_id: str = ""
    policy_ids: list[str] = field(default_factory=list)
    evaluation_result: str = ""
    reason: str = ""
    evidence: list[str] = field(default_factory=list)
    created_at: str = ""
    audit_request_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_id", ensure_project(self.project_id))
        kind = str(self.source_kind).lower().strip()
        if kind not in GOVERNANCE_KINDS:
            raise ValidationFailed(f"Unknown governance source kind: {kind}")
        object.__setattr__(self, "source_kind", kind)
        object.__setattr__(self, "source_id", sanitize_text(self.source_id, limit=200))
        if not self.source_id:
            raise ValidationFailed("source_id is required for a governance record")
        risk = str(self.risk_level).upper().strip()
        if risk not in RISK_LEVELS:
            raise ValidationFailed(f"Unknown risk level: {risk}")
        object.__setattr__(self, "risk_level", risk)
        result = str(self.governance_result).upper().strip()
        if result not in GOVERNANCE_RESULTS:
            raise ValidationFailed(f"Unknown governance result: {result}")
        object.__setattr__(self, "governance_result", result)
        object.__setattr__(self, "governance_id", sanitize_text(self.governance_id, limit=200) or f"gov_{token_hex(8)}")
        object.__setattr__(self, "risk_score", round(max(0.0, min(100.0, float(self.risk_score))), 1))
        object.__setattr__(self, "confidence", bounded_confidence(self.confidence))
        object.__setattr__(self, "agent_id", sanitize_text(self.agent_id, limit=200))
        object.__setattr__(self, "model_id", sanitize_text(self.model_id, limit=200))
        object.__setattr__(self, "evaluation_result", sanitize_text(self.evaluation_result, limit=32))
        object.__setattr__(self, "reason", sanitize_text(self.reason, limit=4000))
        object.__setattr__(self, "policy_ids", ids(self.policy_ids))
        object.__setattr__(self, "evidence", ids(self.evidence))
        object.__setattr__(self, "created_at", self.created_at or utc_now())
        object.__setattr__(self, "audit_request_id", sanitize_text(self.audit_request_id, limit=100))

    def as_dict(self) -> dict[str, Any]:
        return {
            "governance_id": self.governance_id, "governanceId": self.governance_id,
            "project_id": self.project_id, "projectId": self.project_id,
            "source_kind": self.source_kind, "sourceKind": self.source_kind,
            "source_id": self.source_id, "sourceId": self.source_id,
            "agent_id": self.agent_id, "agentId": self.agent_id,
            "model_id": self.model_id, "modelId": self.model_id,
            "policy_ids": list(self.policy_ids), "policyIds": list(self.policy_ids),
            "risk_level": self.risk_level, "riskLevel": self.risk_level,
            "risk_score": self.risk_score, "riskScore": self.risk_score,
            "confidence": self.confidence,
            "evaluation_result": self.evaluation_result, "evaluationResult": self.evaluation_result,
            "governance_result": self.governance_result, "governanceResult": self.governance_result,
            "reason": self.reason, "evidence": list(self.evidence),
            "created_at": self.created_at, "createdAt": self.created_at,
            "audit_request_id": self.audit_request_id, "auditRequestId": self.audit_request_id,
            "readOnly": True,
        }


@dataclass(frozen=True)
class RiskFinding:
    """Output of the Intelligence Risk Analyzer.

    The analyzer only observes, analyzes, and classifies. It never performs
    any risk handling action.
    """

    risk_id: str
    project_id: str
    source_kind: str
    source_id: str
    risk_level: str
    risk_score: float
    confidence: float
    risk_factors: list[str]
    reason: str
    agent_id: str = ""
    model_id: str = ""
    similar_cases: list[str] = field(default_factory=list)
    created_at: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_id", ensure_project(self.project_id))
        object.__setattr__(self, "risk_id", sanitize_text(self.risk_id, limit=200) or f"risk_{token_hex(8)}")
        kind = str(self.source_kind).lower().strip()
        if kind not in GOVERNANCE_KINDS:
            raise ValidationFailed(f"Unknown governance source kind: {kind}")
        object.__setattr__(self, "source_kind", kind)
        object.__setattr__(self, "source_id", sanitize_text(self.source_id, limit=200))
        risk = str(self.risk_level).upper().strip()
        if risk not in RISK_LEVELS:
            raise ValidationFailed(f"Unknown risk level: {risk}")
        object.__setattr__(self, "risk_level", risk)
        object.__setattr__(self, "risk_score", round(max(0.0, min(100.0, float(self.risk_score))), 1))
        object.__setattr__(self, "confidence", bounded_confidence(self.confidence))
        object.__setattr__(self, "risk_factors", ids(self.risk_factors))
        object.__setattr__(self, "reason", sanitize_text(self.reason, limit=4000))
        object.__setattr__(self, "agent_id", sanitize_text(self.agent_id, limit=200))
        object.__setattr__(self, "model_id", sanitize_text(self.model_id, limit=200))
        object.__setattr__(self, "similar_cases", ids(self.similar_cases))
        object.__setattr__(self, "created_at", self.created_at or utc_now())

    def as_dict(self) -> dict[str, Any]:
        return {
            "risk_id": self.risk_id, "riskId": self.risk_id,
            "project_id": self.project_id, "projectId": self.project_id,
            "source_kind": self.source_kind, "sourceKind": self.source_kind,
            "source_id": self.source_id, "sourceId": self.source_id,
            "risk_level": self.risk_level, "riskLevel": self.risk_level,
            "risk_score": self.risk_score, "riskScore": self.risk_score,
            "confidence": self.confidence,
            "risk_factors": list(self.risk_factors), "riskFactors": list(self.risk_factors),
            "reason": self.reason, "agent_id": self.agent_id, "agentId": self.agent_id,
            "model_id": self.model_id, "modelId": self.model_id,
            "similar_cases": list(self.similar_cases), "similarCases": list(self.similar_cases),
            "created_at": self.created_at, "createdAt": self.created_at,
            "readOnly": True,
        }


@dataclass(frozen=True)
class PolicyViolation:
    violation_id: str
    policy_id: str
    project_id: str
    source_id: str
    source_kind: str
    severity: str
    reason: str
    confidence: float
    created_at: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_id", ensure_project(self.project_id))
        object.__setattr__(self, "violation_id", sanitize_text(self.violation_id, limit=200) or f"viol_{token_hex(8)}")
        object.__setattr__(self, "policy_id", sanitize_text(self.policy_id, limit=200))
        object.__setattr__(self, "source_id", sanitize_text(self.source_id, limit=200))
        kind = str(self.source_kind).lower().strip()
        if kind not in GOVERNANCE_KINDS:
            raise ValidationFailed(f"Unknown governance source kind: {kind}")
        object.__setattr__(self, "source_kind", kind)
        severity = str(self.severity).lower().strip()
        if severity not in {item.value for item in PolicySeverity}:
            raise ValidationFailed(f"Unknown policy severity: {severity}")
        object.__setattr__(self, "severity", severity)
        object.__setattr__(self, "reason", sanitize_text(self.reason, limit=2000))
        object.__setattr__(self, "confidence", bounded_confidence(self.confidence))
        object.__setattr__(self, "created_at", self.created_at or utc_now())

    def as_dict(self) -> dict[str, Any]:
        return {
            "violation_id": self.violation_id, "violationId": self.violation_id,
            "policy_id": self.policy_id, "policyId": self.policy_id,
            "project_id": self.project_id, "projectId": self.project_id,
            "source_id": self.source_id, "sourceId": self.source_id,
            "source_kind": self.source_kind, "sourceKind": self.source_kind,
            "severity": self.severity, "reason": self.reason,
            "confidence": self.confidence, "created_at": self.created_at,
            "createdAt": self.created_at, "readOnly": True,
        }


@dataclass(frozen=True)
class ReviewProposal:
    """Governance review proposal.

    A proposal only ever enters the ApprovalStore for human review. There is
    no automatic approval path anywhere in the governance layer.
    """

    proposal_id: str
    project_id: str
    source_id: str
    source_kind: str
    risk_level: str
    reason: str
    recommended_action: str
    confidence: float
    evidence: list[str] = field(default_factory=list)
    status: str = ReviewStatus.PROPOSED.value
    created_at: str = ""
    resolved_at: str = ""
    audit_request_id: str = ""
    reviewer_note: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_id", ensure_project(self.project_id))
        object.__setattr__(self, "proposal_id", sanitize_text(self.proposal_id, limit=200) or f"review_{token_hex(8)}")
        object.__setattr__(self, "source_id", sanitize_text(self.source_id, limit=200))
        kind = str(self.source_kind).lower().strip()
        if kind not in GOVERNANCE_KINDS:
            raise ValidationFailed(f"Unknown governance source kind: {kind}")
        object.__setattr__(self, "source_kind", kind)
        risk = str(self.risk_level).upper().strip()
        if risk not in RISK_LEVELS:
            raise ValidationFailed(f"Unknown risk level: {risk}")
        object.__setattr__(self, "risk_level", risk)
        object.__setattr__(self, "reason", sanitize_text(self.reason, limit=4000))
        object.__setattr__(self, "recommended_action", sanitize_text(self.recommended_action, limit=4000))
        object.__setattr__(self, "confidence", bounded_confidence(self.confidence))
        object.__setattr__(self, "evidence", ids(self.evidence))
        status = str(self.status).lower().strip()
        if status not in REVIEW_STATUSES:
            raise ValidationFailed(f"Unknown review status: {status}")
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "created_at", self.created_at or utc_now())
        object.__setattr__(self, "audit_request_id", sanitize_text(self.audit_request_id, limit=100))
        object.__setattr__(self, "reviewer_note", sanitize_text(self.reviewer_note, limit=4000))

    def as_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id, "proposalId": self.proposal_id,
            "project_id": self.project_id, "projectId": self.project_id,
            "source_id": self.source_id, "sourceId": self.source_id,
            "source_kind": self.source_kind, "sourceKind": self.source_kind,
            "risk_level": self.risk_level, "riskLevel": self.risk_level,
            "reason": self.reason, "recommended_action": self.recommended_action,
            "recommendedAction": self.recommended_action, "confidence": self.confidence,
            "evidence": list(self.evidence), "status": self.status,
            "created_at": self.created_at, "createdAt": self.created_at,
            "resolved_at": self.resolved_at, "resolvedAt": self.resolved_at,
            "audit_request_id": self.audit_request_id, "auditRequestId": self.audit_request_id,
            "reviewer_note": self.reviewer_note, "reviewerNote": self.reviewer_note,
            "readOnly": True,
        }


@dataclass(frozen=True)
class GovernanceMemoryRecord:
    """Governance memory entry.

    Governance memory only stores governance findings, risk findings, quality
    findings, policy violations, review outcomes, and historical governance
    decisions. Every write must pass Governance Proposal -> ApprovalStore ->
    Human Approval. There is no auto governance memory write.
    """

    memory_id: str
    project_id: str
    category: str
    content: str
    source: str
    confidence: float
    evidence: list[str] = field(default_factory=list)
    created_at: str = ""
    approval_request_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_id", ensure_project(self.project_id))
        object.__setattr__(self, "memory_id", sanitize_text(self.memory_id, limit=200) or f"gm_{token_hex(8)}")
        category = str(self.category).lower().strip()
        if category not in GOVERNANCE_MEMORY_CATEGORIES:
            raise ValidationFailed(f"Unknown governance memory category: {category}")
        object.__setattr__(self, "category", category)
        object.__setattr__(self, "content", sanitize_text(self.content, limit=12000))
        if not self.content.strip():
            raise ValidationFailed("content is required for governance memory")
        object.__setattr__(self, "source", sanitize_text(self.source, limit=500))
        object.__setattr__(self, "confidence", bounded_confidence(self.confidence))
        object.__setattr__(self, "evidence", ids(self.evidence))
        object.__setattr__(self, "created_at", self.created_at or utc_now())
        object.__setattr__(self, "approval_request_id", sanitize_text(self.approval_request_id, limit=100))

    def as_dict(self) -> dict[str, Any]:
        return {
            "memory_id": self.memory_id, "memoryId": self.memory_id,
            "project_id": self.project_id, "projectId": self.project_id,
            "category": self.category, "content": self.content, "source": self.source,
            "confidence": self.confidence, "evidence": list(self.evidence),
            "created_at": self.created_at, "createdAt": self.created_at,
            "approval_request_id": self.approval_request_id, "approvalRequestId": self.approval_request_id,
            "readOnly": True,
        }


@dataclass(frozen=True)
class GovernanceTrend:
    trend_id: str
    project_id: str
    metric: str
    period: str
    direction: str
    change_rate: float
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)
    sample_count: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_id", ensure_project(self.project_id))
        object.__setattr__(self, "metric", sanitize_text(self.metric, limit=100))
        object.__setattr__(self, "period", sanitize_text(self.period, limit=32))
        # Derived deterministic id: the same metric+period always yields the
        # same trend id, keeping repeated read-only snapshots stable.
        object.__setattr__(self, "trend_id", sanitize_text(self.trend_id, limit=200) or f"govtrend_{self.metric}_{self.period}")
        object.__setattr__(self, "direction", sanitize_text(self.direction, limit=32))
        object.__setattr__(self, "change_rate", round(float(self.change_rate), 4))
        object.__setattr__(self, "confidence", bounded_confidence(float(self.confidence)))
        object.__setattr__(self, "evidence", ids(self.evidence))
        object.__setattr__(self, "sample_count", max(0, int(self.sample_count)))

    def as_dict(self) -> dict[str, Any]:
        return {
            "trend_id": self.trend_id, "trendId": self.trend_id,
            "project_id": self.project_id, "projectId": self.project_id,
            "metric": self.metric, "period": self.period,
            "direction": self.direction, "change_rate": self.change_rate,
            "changeRate": self.change_rate, "confidence": self.confidence,
            "evidence": list(self.evidence), "sample_count": self.sample_count,
            "sampleCount": self.sample_count, "readOnly": True,
        }
