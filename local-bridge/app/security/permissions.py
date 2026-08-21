"""Permission policy and the persistent, approval-gated request store.

Phase 8 keeps the existing human-in-the-loop execution contract but makes the
approval queue durable. A request recovered after a restart is visible but can
never execute until a user explicitly reconfirms it.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Any

from app.security.validator import ApprovalError, ResourceNotFound


class PermissionLevel(str, Enum):
    LEVEL_0 = "LEVEL_0"
    LEVEL_1 = "LEVEL_1"
    LEVEL_2 = "LEVEL_2"


class ApprovalStatus(str, Enum):
    """Persisted approval lifecycle states.

    The legacy EXECUTED/FAILED values remain supported so existing workflow
    code and clients continue to receive meaningful terminal statuses.
    """

    PENDING = "pending"
    EXPIRED = "expired"
    RECOVERED = "recovered"
    RECONFIRMED = "reconfirmed"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    FAILED = "failed"


ACTION_LEVELS: dict[str, PermissionLevel] = {
    "health": PermissionLevel.LEVEL_0,
    "workspace_list": PermissionLevel.LEVEL_0,
    "project_tree": PermissionLevel.LEVEL_0,
    "file_read": PermissionLevel.LEVEL_0,
    "file_search": PermissionLevel.LEVEL_0,
    "memory_read": PermissionLevel.LEVEL_0,
    "memory_list": PermissionLevel.LEVEL_0,
    "context_project": PermissionLevel.LEVEL_0,
    "context_search": PermissionLevel.LEVEL_0,
    "session_read": PermissionLevel.LEVEL_0,
    "file_create": PermissionLevel.LEVEL_1,
    "file_write": PermissionLevel.LEVEL_1,
    "patch_apply": PermissionLevel.LEVEL_1,
    "git_command": PermissionLevel.LEVEL_1,
    "memory_append": PermissionLevel.LEVEL_1,
    "memory_decision": PermissionLevel.LEVEL_1,
    "memory_init": PermissionLevel.LEVEL_1,
    "workflow_stage_approval": PermissionLevel.LEVEL_1,
    "git_commit": PermissionLevel.LEVEL_1,
    "test_run": PermissionLevel.LEVEL_1,
    "workflow_rollback": PermissionLevel.LEVEL_1,
    "session_create": PermissionLevel.LEVEL_1,
    "session_transition": PermissionLevel.LEVEL_1,
    "agent_create": PermissionLevel.LEVEL_1,
    "agent_transition": PermissionLevel.LEVEL_1,
    "agent_message": PermissionLevel.LEVEL_1,
    "workflow_agent_attach": PermissionLevel.LEVEL_1,
    "quality_gate_submit": PermissionLevel.LEVEL_1,
    "runtime_create": PermissionLevel.LEVEL_1,
    "task_create": PermissionLevel.LEVEL_1,
    "task_transition": PermissionLevel.LEVEL_1,
    "team_create": PermissionLevel.LEVEL_1,
    "code_index": PermissionLevel.LEVEL_1,
    "project_memory_append": PermissionLevel.LEVEL_1,
    "intelligence_memory_append": PermissionLevel.LEVEL_1,
    "intelligence_analyze": PermissionLevel.LEVEL_1,
    "intelligence_decision_create": PermissionLevel.LEVEL_1,
    # Phase 25 intelligence writes are proposals/metadata only, but remain
    # explicit ApprovalStore actions so the persistent boundary is auditable.
    "intelligence_observation_record": PermissionLevel.LEVEL_1,
    "intelligence_pattern_analyze": PermissionLevel.LEVEL_1,
    "intelligence_prediction_analyze": PermissionLevel.LEVEL_1,
    "intelligence_outcome_record": PermissionLevel.LEVEL_1,
    "intelligence_knowledge_append": PermissionLevel.LEVEL_1,
    "intelligence_evidence_bundle": PermissionLevel.LEVEL_1,
    # Phase 27 validation records are measurement metadata only, but stay
    # explicit ApprovalStore actions so the persistent boundary is auditable.
    "intelligence_evaluation_record": PermissionLevel.LEVEL_1,
    "intelligence_benchmark_run": PermissionLevel.LEVEL_1,
    "intelligence_knowledge_improvement": PermissionLevel.LEVEL_1,
    # Phase 28 governance records are measurement/audit metadata only, but stay
    # explicit ApprovalStore actions so the persistent boundary is auditable.
    "intelligence_governance_evaluate": PermissionLevel.LEVEL_1,
    "intelligence_governance_review": PermissionLevel.LEVEL_1,
    # Phase 30 patch proposals are record-only; they never write source files.
    "context_patch_proposal": PermissionLevel.LEVEL_1,
    # Phase 31 LLM gateway: stateless chat is a read-only computation; every
    # persistent write (conversation/message/tool proposal) stays LEVEL_1 and
    # tool proposals are records only — never executed by the gateway.
    "llm_chat": PermissionLevel.LEVEL_0,
    "llm_chat_stream": PermissionLevel.LEVEL_0,
    "llm_conversation_create": PermissionLevel.LEVEL_1,
    "llm_message_append": PermissionLevel.LEVEL_1,
    "llm_tool_proposal": PermissionLevel.LEVEL_1,
    # Phase 32 · AI Assistant Productization. Reads and the stateless assistant
    # chat are LEVEL_0; anything that persists a credential or a preference is
    # LEVEL_1. Activating a provider credential is deliberately human-gated even
    # though the key arrives already encrypted.
    "assistant_user_settings": PermissionLevel.LEVEL_0,
    "assistant_provider_status": PermissionLevel.LEVEL_0,
    "assistant_provider_test": PermissionLevel.LEVEL_0,
    "assistant_context_status": PermissionLevel.LEVEL_0,
    "assistant_chat": PermissionLevel.LEVEL_0,
    "assistant_chat_stream": PermissionLevel.LEVEL_0,
    "assistant_provider_config": PermissionLevel.LEVEL_1,
    "assistant_provider_forget": PermissionLevel.LEVEL_1,
    "assistant_settings_update": PermissionLevel.LEVEL_1,
    "simulation_create": PermissionLevel.LEVEL_1,
    "simulation_analyze": PermissionLevel.LEVEL_1,
    "simulation_plan": PermissionLevel.LEVEL_1,
    "planning_memory_append": PermissionLevel.LEVEL_1,
    "execution_create": PermissionLevel.LEVEL_1,
    "execution_proposal": PermissionLevel.LEVEL_1,
    "execution_execute": PermissionLevel.LEVEL_1,
    "execution_memory_append": PermissionLevel.LEVEL_1,
    "execution_loop_create": PermissionLevel.LEVEL_1,
    "execution_loop_prepare": PermissionLevel.LEVEL_1,
    "execution_loop_verify": PermissionLevel.LEVEL_1,
    "execution_loop_rollback": PermissionLevel.LEVEL_1,
    "execution_loop_recover": PermissionLevel.LEVEL_1,
    "execution_dag_create": PermissionLevel.LEVEL_1,
    "execution_dag_advance": PermissionLevel.LEVEL_1,
    "engineering_graph_rebuild": PermissionLevel.LEVEL_1,
    "evolution_timeline_append": PermissionLevel.LEVEL_1,
    "benchmark_create": PermissionLevel.LEVEL_1,
    "benchmark_transition": PermissionLevel.LEVEL_1,
    "validation_create": PermissionLevel.LEVEL_1,
    "validation_transition": PermissionLevel.LEVEL_1,
    "validation_run_record": PermissionLevel.LEVEL_1,
    "demo_scenario_create": PermissionLevel.LEVEL_1,
    "replay_create": PermissionLevel.LEVEL_1,
    "artifact_export": PermissionLevel.LEVEL_1,
    "governance_debt_create": PermissionLevel.LEVEL_1,
    "governance_debt_transition": PermissionLevel.LEVEL_1,
    "governance_policy_evaluate": PermissionLevel.LEVEL_1,
    "governance_memory_append": PermissionLevel.LEVEL_1,
    "organization_entity_register": PermissionLevel.LEVEL_1,
    "organization_incident_create": PermissionLevel.LEVEL_1,
    "organization_decision_create": PermissionLevel.LEVEL_1,
    "organization_pattern_create": PermissionLevel.LEVEL_1,
    "organization_learning_scan": PermissionLevel.LEVEL_1,
    "organization_graph_sync": PermissionLevel.LEVEL_1,
    "organization_graph_snapshot_create": PermissionLevel.LEVEL_1,
    "organization_graph_snapshot_restore": PermissionLevel.LEVEL_1,
    "organization_strategy_create": PermissionLevel.LEVEL_1,
    "organization_strategy_evaluate": PermissionLevel.LEVEL_1,
    "organization_strategy_decision_create": PermissionLevel.LEVEL_1,
    "organization_strategy_decision_transition": PermissionLevel.LEVEL_1,
    "organization_memory_append": PermissionLevel.LEVEL_1,
    "model_route": PermissionLevel.LEVEL_0,
    "agent_status": PermissionLevel.LEVEL_0,
    "file_delete": PermissionLevel.LEVEL_2,
    "shell_command": PermissionLevel.LEVEL_2,
    "system_config": PermissionLevel.LEVEL_2,
}

RISK_BY_LEVEL: dict[PermissionLevel, str] = {
    PermissionLevel.LEVEL_0: "low",
    PermissionLevel.LEVEL_1: "medium",
    PermissionLevel.LEVEL_2: "high",
}


@dataclass(frozen=True)
class PermissionDecision:
    allowed: bool
    require_approval: bool
    permission_level: PermissionLevel
    risk: str
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "requireApproval": self.require_approval,
            "permissionLevel": self.permission_level.value,
            "risk": self.risk,
            "reason": self.reason,
        }


def level_for_action(action: str) -> PermissionLevel:
    try:
        return ACTION_LEVELS[action]
    except KeyError as exc:
        raise ApprovalError(f"Unknown action '{action}'") from exc


def evaluate(action: str, *, approved: bool = False) -> PermissionDecision:
    """Evaluate whether ``action`` may run right now."""
    level = level_for_action(action)
    risk = RISK_BY_LEVEL[level]
    if level is PermissionLevel.LEVEL_0:
        return PermissionDecision(True, False, level, risk, "Read-only operation is auto-approved")
    if approved:
        return PermissionDecision(True, False, level, risk, "User approval recorded for this request")
    reason = (
        "Modifying operation requires explicit user approval"
        if level is PermissionLevel.LEVEL_1
        else "Destructive operation requires mandatory user approval"
    )
    return PermissionDecision(False, True, level, risk, reason)


@dataclass
class ApprovalRequest:
    request_id: str
    action: str
    permission_level: PermissionLevel
    risk: str
    project: str
    path: str
    payload: dict[str, Any]
    reason: str
    preview: str
    created_at: str
    expires_at: str = ""
    status: ApprovalStatus = ApprovalStatus.PENDING
    resolved_at: str | None = None
    recovered_at: str | None = None
    result: dict[str, Any] | None = field(default=None)
    workflow_id: str | None = None
    stage_id: str | None = None
    session_id: str | None = None
    execution_loop_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "requestId": self.request_id,
            "action": self.action,
            "permissionLevel": self.permission_level.value,
            "risk": self.risk,
            "project": self.project,
            "path": self.path,
            "reason": self.reason,
            "preview": self.preview,
            "status": self.status.value,
            "createdAt": self.created_at,
            "expiresAt": self.expires_at,
            "resolvedAt": self.resolved_at,
            "recoveredAt": self.recovered_at,
            "workflowId": self.workflow_id,
            "stageId": self.stage_id,
            "sessionId": self.session_id,
            "executionLoopId": self.execution_loop_id,
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class ApprovalStore:
    """Thread-safe SQLite-backed approval queue.

    ``db_path=None`` intentionally creates an in-memory store for small unit
    tests. The application-level cached store always receives the configured
    file path, making requests survive process restarts and machine reboots.
    """

    def __init__(self, db_path: str | Path | None = None, *, ttl_seconds: int = 3600) -> None:
        self._lock = Lock()
        self._db_path = ":memory:" if db_path is None else str(db_path)
        if self._db_path != ":memory:":
            Path(self._db_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        self._ttl_seconds = ttl_seconds
        self._connection = sqlite3.connect(self._db_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS approvals (
                request_id TEXT PRIMARY KEY,
                action TEXT NOT NULL,
                permission_level TEXT NOT NULL,
                risk TEXT NOT NULL,
                project TEXT NOT NULL,
                path TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                reason TEXT NOT NULL,
                preview TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                status TEXT NOT NULL,
                resolved_at TEXT,
                recovered_at TEXT,
                result_json TEXT,
                workflow_id TEXT,
                stage_id TEXT,
                session_id TEXT,
                execution_loop_id TEXT
            )
            """
        )
        columns = {row["name"] for row in self._connection.execute("PRAGMA table_info(approvals)").fetchall()}
        if "execution_loop_id" not in columns:
            self._connection.execute("ALTER TABLE approvals ADD COLUMN execution_loop_id TEXT")
        self._connection.commit()

    @property
    def db_path(self) -> str:
        return self._db_path

    @staticmethod
    def _from_row(row: sqlite3.Row) -> ApprovalRequest:
        return ApprovalRequest(
            request_id=row["request_id"],
            action=row["action"],
            permission_level=PermissionLevel(row["permission_level"]),
            risk=row["risk"],
            project=row["project"],
            path=row["path"],
            payload=json.loads(row["payload_json"]),
            reason=row["reason"],
            preview=row["preview"],
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            status=ApprovalStatus(row["status"]),
            resolved_at=row["resolved_at"],
            recovered_at=row["recovered_at"],
            result=json.loads(row["result_json"]) if row["result_json"] else None,
            workflow_id=row["workflow_id"],
            stage_id=row["stage_id"],
            session_id=row["session_id"],
            execution_loop_id=row["execution_loop_id"],
        )

    @staticmethod
    def _audit(audit: Any, request: ApprovalRequest, action: str, result: str, detail: str) -> None:
        if audit is None:
            return
        audit.record(
            action=action,
            path=f"{request.project}:{request.path}",
            permission=request.permission_level.value,
            approved=False,
            result=result,
            detail=detail,
            request_id=request.request_id,
        )

    def _write(self, request: ApprovalRequest) -> None:
        self._connection.execute(
            """
            UPDATE approvals SET status=?, resolved_at=?, recovered_at=?, result_json=?,
              workflow_id=?, stage_id=?, session_id=?, execution_loop_id=? WHERE request_id=?
            """,
            (
                request.status.value,
                request.resolved_at,
                request.recovered_at,
                json.dumps(request.result, ensure_ascii=False) if request.result is not None else None,
                request.workflow_id,
                request.stage_id,
                request.session_id,
                request.execution_loop_id,
                request.request_id,
            ),
        )
        self._connection.commit()

    def create(
        self,
        *,
        action: str,
        project: str,
        path: str,
        payload: dict[str, Any],
        reason: str,
        preview: str,
        workflow_id: str | None = None,
        stage_id: str | None = None,
        session_id: str | None = None,
        execution_loop_id: str | None = None,
    ) -> ApprovalRequest:
        level = level_for_action(action)
        created = datetime.now(timezone.utc)
        request = ApprovalRequest(
            request_id=f"req_{secrets.token_hex(8)}",
            action=action,
            permission_level=level,
            risk=RISK_BY_LEVEL[level],
            project=project,
            path=path,
            payload=payload,
            reason=reason,
            preview=preview,
            created_at=created.isoformat(timespec="seconds"),
            expires_at=(created + timedelta(seconds=self._ttl_seconds)).isoformat(timespec="seconds"),
            workflow_id=workflow_id,
            stage_id=stage_id,
            session_id=session_id,
            execution_loop_id=execution_loop_id,
        )
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO approvals (
                    request_id, action, permission_level, risk, project, path,
                    payload_json, reason, preview, created_at, expires_at, status,
                    workflow_id, stage_id, session_id, execution_loop_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request.request_id,
                    request.action,
                    request.permission_level.value,
                    request.risk,
                    request.project,
                    request.path,
                    json.dumps(request.payload, ensure_ascii=False),
                    request.reason,
                    request.preview,
                    request.created_at,
                    request.expires_at,
                    request.status.value,
                    request.workflow_id,
                    request.stage_id,
                    request.session_id,
                    request.execution_loop_id,
                ),
            )
            self._connection.commit()
        return request

    def get(self, request_id: str) -> ApprovalRequest:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM approvals WHERE request_id=?", (request_id,)
            ).fetchone()
        if row is None:
            raise ResourceNotFound(f"Approval request '{request_id}' was not found")
        return self._from_row(row)

    def expire_due(self, audit: Any = None) -> list[ApprovalRequest]:
        expired: list[ApprovalRequest] = []
        now = datetime.now(timezone.utc)
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM approvals WHERE status IN (?, ?, ?)",
                (ApprovalStatus.PENDING.value, ApprovalStatus.RECOVERED.value, ApprovalStatus.RECONFIRMED.value),
            ).fetchall()
            for row in rows:
                request = self._from_row(row)
                if _parse_time(request.expires_at) <= now:
                    request.status = ApprovalStatus.EXPIRED
                    request.resolved_at = _utc_now()
                    self._write(request)
                    expired.append(request)
        for request in expired:
            self._audit(audit, request, "approval_expired", "expired", "Approval TTL elapsed")
        return expired

    def recover_pending(self, audit: Any = None) -> list[ApprovalRequest]:
        """Expire stale requests and mark live requests as recovered.

        Recovery is deliberately not confirmation. Recovered requests cannot
        be approved until ``reconfirm`` is called by an explicit user action.
        """
        self.expire_due(audit)
        recovered: list[ApprovalRequest] = []
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM approvals WHERE status=?", (ApprovalStatus.PENDING.value,)
            ).fetchall()
            for row in rows:
                request = self._from_row(row)
                request.status = ApprovalStatus.RECOVERED
                request.recovered_at = _utc_now()
                self._write(request)
                recovered.append(request)
        for request in recovered:
            self._audit(audit, request, "approval_recovered", "recovered", "Recovered after process restart; reconfirmation required")
        return recovered

    def list_pending(self) -> list[ApprovalRequest]:
        self.expire_due()
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM approvals WHERE status IN (?, ?, ?) ORDER BY created_at",
                (
                    ApprovalStatus.PENDING.value,
                    ApprovalStatus.RECOVERED.value,
                    ApprovalStatus.RECONFIRMED.value,
                ),
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def list_all(self) -> list[ApprovalRequest]:
        with self._lock:
            rows = self._connection.execute("SELECT * FROM approvals ORDER BY created_at DESC").fetchall()
        return [self._from_row(row) for row in rows]

    def reconfirm(self, request_id: str, audit: Any = None) -> ApprovalRequest:
        self.expire_due(audit)
        request = self.get(request_id)
        with self._lock:
            if request.status is not ApprovalStatus.RECOVERED:
                raise ApprovalError(
                    f"Approval request '{request_id}' must be recovered before reconfirmation"
                )
            request.status = ApprovalStatus.RECONFIRMED
            self._write(request)
        self._audit(audit, request, "approval_reconfirmed", "reconfirmed", "User reconfirmed recovered approval")
        return request

    def mark_approved(self, request_id: str) -> ApprovalRequest:
        self.expire_due()
        request = self.get(request_id)
        with self._lock:
            if request.status not in {ApprovalStatus.PENDING, ApprovalStatus.RECONFIRMED}:
                raise ApprovalError(
                    f"Approval request '{request_id}' is {request.status.value}; explicit reconfirmation is required after recovery"
                )
            request.status = ApprovalStatus.APPROVED
            self._write(request)
        return request

    def mark_rejected(self, request_id: str, reason: str = "Rejected by user", audit: Any = None) -> ApprovalRequest:
        request = self.get(request_id)
        with self._lock:
            if request.status not in {ApprovalStatus.PENDING, ApprovalStatus.RECOVERED, ApprovalStatus.RECONFIRMED}:
                raise ApprovalError(f"Approval request '{request_id}' is already {request.status.value}")
            request.status = ApprovalStatus.REJECTED
            request.result = {"reason": reason}
            request.resolved_at = _utc_now()
            self._write(request)
        self._audit(audit, request, "approval_rejected", "rejected", reason)
        return request

    def mark_executed(self, request_id: str, result: dict[str, Any]) -> ApprovalRequest:
        request = self.get(request_id)
        with self._lock:
            if request.status is not ApprovalStatus.APPROVED:
                raise ApprovalError(f"Approval request '{request_id}' is not approved")
            request.status = ApprovalStatus.EXECUTED
            request.result = result
            request.resolved_at = _utc_now()
            self._write(request)
        return request

    def mark_failed(self, request_id: str, message: str) -> ApprovalRequest:
        request = self.get(request_id)
        with self._lock:
            if request.status in {ApprovalStatus.EXECUTED, ApprovalStatus.REJECTED, ApprovalStatus.EXPIRED}:
                return request
            request.status = ApprovalStatus.FAILED
            request.result = {"error": message}
            request.resolved_at = _utc_now()
            self._write(request)
        return request

    def attach_binding(
        self,
        request_id: str,
        *,
        workflow_id: str | None = None,
        stage_id: str | None = None,
        session_id: str | None = None,
    ) -> ApprovalRequest:
        request = self.get(request_id)
        with self._lock:
            if workflow_id is not None:
                request.workflow_id = workflow_id
            if stage_id is not None:
                request.stage_id = stage_id
            if session_id is not None:
                request.session_id = session_id
            self._write(request)
        return request

    def attach_loop(self, request_id: str, execution_loop_id: str) -> ApprovalRequest:
        request = self.get(request_id)
        with self._lock:
            request.execution_loop_id = execution_loop_id
            self._write(request)
        return request

    def attach_session(self, request_id: str, session_id: str) -> ApprovalRequest:
        return self.attach_binding(request_id, session_id=session_id)

    def snapshot(self) -> list[dict[str, Any]]:
        """Return a serialisable inspection snapshot for backups/dashboard use."""
        return [
            {
                **request.as_dict(),
                "payload": request.payload,
                "result": request.result,
            }
            for request in self.list_all()
        ]

    def clear(self) -> None:
        with self._lock:
            self._connection.execute("DELETE FROM approvals")
            self._connection.commit()


@lru_cache(maxsize=1)
def get_approval_store() -> ApprovalStore:
    from app.config import get_settings

    settings = get_settings()
    return ApprovalStore(settings.approval_db_path, ttl_seconds=settings.approval_ttl_seconds)


def reset_approval_store() -> None:
    get_approval_store.cache_clear()
