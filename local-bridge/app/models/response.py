"""Response models returned by the bridge API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str
    version: str
    phase: str
    workspaceRoot: str
    logPath: str
    memoryRoot: str
    workflowRoot: str


class ProjectInfo(BaseModel):
    name: str
    path: str


class WorkspaceListResponse(BaseModel):
    projects: list[ProjectInfo]


class TreeNode(BaseModel):
    name: str
    path: str
    type: Literal["file", "directory"]
    size: int | None = None
    truncated: bool = False
    children: list["TreeNode"] = Field(default_factory=list)


TreeNode.model_rebuild()


class ProjectTreeResponse(BaseModel):
    project: str
    maxDepth: int
    ignored: list[str]
    tree: TreeNode


class FileReadResponse(BaseModel):
    file: str
    size: int
    content: str


class ApprovalPendingResponse(BaseModel):
    allowed: Literal[False] = False
    requireApproval: Literal[True] = True
    permissionLevel: str
    risk: str
    reason: str
    status: str
    requestId: str
    action: str
    project: str
    path: str
    preview: str
    createdAt: str
    workflowId: str | None = None
    stageId: str | None = None


class OperationResultResponse(BaseModel):
    allowed: Literal[True] = True
    requireApproval: Literal[False] = False
    permissionLevel: str
    requestId: str
    action: str
    status: str
    project: str
    path: str
    result: dict[str, Any]


class PendingApprovalsResponse(BaseModel):
    pending: list[dict[str, Any]]


class AuditLogResponse(BaseModel):
    entries: list[dict[str, Any]]
    logFile: str


class MemoryReadResponse(BaseModel):
    project: str
    document: str
    size: int
    content: str


class MemoryProjectSummary(BaseModel):
    project: str
    documents: list[str]


class MemoryListResponse(BaseModel):
    projects: list[MemoryProjectSummary]


class MemoryStatusResponse(BaseModel):
    project: str
    memoryDir: str
    documents: list[dict[str, Any]]
    decisions: list[dict[str, Any]]


class WorkflowStageView(BaseModel):
    id: str
    workflowId: str
    stageType: str
    status: str
    reportTitle: str | None = None
    report: str | None = None
    approvalRequestId: str | None = None
    approvedAt: str | None = None
    approvedBy: str | None = None
    actionIds: list[str] = Field(default_factory=list)
    agentIds: list[str] = Field(default_factory=list)
    qualityGate: dict[str, Any] | None = None
    createdAt: str
    updatedAt: str


class WorkflowView(BaseModel):
    id: str
    project: str
    name: str
    description: str
    currentStage: str
    status: str
    createdAt: str
    updatedAt: str
    completedAt: str | None = None
    cancelledReason: str | None = None
    stages: list[WorkflowStageView] = Field(default_factory=list)


class WorkflowSummaryView(BaseModel):
    id: str
    project: str
    name: str
    status: str
    currentStage: str
    stageCount: int
    updatedAt: str


class WorkflowListResponse(BaseModel):
    workflows: list[WorkflowSummaryView]


class WorkflowStageAwaitingResponse(BaseModel):
    workflow: WorkflowView
    stage: WorkflowStageView
    approval: dict[str, Any]


class ErrorResponse(BaseModel):
    error: str
    message: str
