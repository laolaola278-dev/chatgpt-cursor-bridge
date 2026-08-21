"""Project context aggregation for ChatGPT context recovery.

The service only reads project, memory, workflow, Git and audit state. Its one
write is an atomic JSON snapshot under CONTEXT_ROOT; it never edits Memory.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.audit.logger import AuditLogger
from app.config import Settings
from app.context.intelligence import ContextCompressor, ContextIndex, ContextSummaryGenerator
from app.git.manager import GitManager
from app.memory.models import MemoryDocument
from app.security.permissions import ApprovalStore
from app.security.sandbox import get_memory_dir, validate_project_name
from app.security.validator import BridgeError
from app.session import SessionManager, SessionStorage
from app.workflow.manager import WorkflowManager
from app.workflow.models import StageType, Workflow

_TASK_LINE = re.compile(r"^\s*-\s*\[\s*([ xX])\s*\]\s*(.+?)\s*$")


class ProjectContextService:
    def __init__(
        self,
        *,
        settings: Settings,
        workflow_manager: WorkflowManager,
        approvals: ApprovalStore,
        audit: AuditLogger,
    ) -> None:
        self._settings = settings
        self._workflows = workflow_manager
        self._approvals = approvals
        self._audit = audit
        self._sessions = SessionManager(
            storage=SessionStorage(settings.session_root),
            workflows=workflow_manager,
            approvals=approvals,
            audit=audit,
        )
        self._index = ContextIndex(settings.context_index_db_path)
        self._compressor = ContextCompressor()
        self._summary = ContextSummaryGenerator(self._compressor)

    @property
    def index(self) -> ContextIndex:
        return self._index

    def build(self, project: str) -> dict[str, Any]:
        project = validate_project_name(project)
        workflow = self._latest_workflow(project)
        stage = self._latest_stage(workflow)
        decisions = self._read_decisions(project)
        open_tasks = self._read_open_tasks(project)
        last_test = self._last_test_result(workflow)
        git_status = self._safe("git", lambda: GitManager(self._settings).status(project).as_dict())
        if git_status is None:
            git_status = {"status": "unavailable", "message": "Git status unavailable"}

        pending = [
            request.as_dict()
            for request in self._approvals.list_pending()
            if request.project == project
        ]
        recent_changes = [
            entry
            for entry in self._audit.read_entries(100)
            if self._belongs_to_project(entry, project)
        ][-12:]
        recent_errors = [
            entry for entry in recent_changes if entry.get("result") in {"failed", "rejected"}
        ][-10:]

        snapshot = {
            "project": project,
            "lastWorkflow": workflow.as_dict() if workflow else None,
            "lastStage": stage.as_dict() if stage else None,
            "activeTasks": open_tasks,
            "recentDecisions": decisions,
            "recentErrors": recent_errors,
            "updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        self._save_snapshot(project, snapshot)

        documents = self._read_documents(project)
        active_sessions = self._sessions.context(project)
        response = {
            "project": project,
            "currentWorkflow": workflow.as_dict() if workflow else None,
            "currentStage": stage.as_dict() if stage else None,
            "recentDecisions": decisions,
            "openTasks": open_tasks,
            "documents": documents,
            "activeSessions": active_sessions,
            "lastTestResult": last_test,
            "gitStatus": git_status,
            "pendingApprovals": pending,
            "recentChanges": recent_changes,
            "snapshot": {"path": str(self._snapshot_path(project)), "updatedAt": snapshot["updatedAt"]},
            "updatedAt": snapshot["updatedAt"],
        }
        response = self._compressor.compress(response)
        response["summary"] = self._summary.generate(response)
        self._index.index_context(project, response)
        return response

    def _latest_workflow(self, project: str) -> Workflow | None:
        workflows = [
            workflow
            for workflow in self._workflows.storage.all()
            if workflow.project == project
        ]
        return max(workflows, key=lambda item: item.updated_at, default=None)

    @staticmethod
    def _latest_stage(workflow: Workflow | None):
        if workflow is None or not workflow.stages:
            return None
        return max(workflow.stages, key=lambda item: item.updated_at)

    def _read_documents(self, project: str) -> list[dict[str, Any]]:
        try:
            memory_dir = get_memory_dir(project, self._settings)
            documents: list[dict[str, Any]] = []
            for document in MemoryDocument:
                path = memory_dir / document.value
                if path.exists() and path.is_file():
                    stat = path.stat()
                    documents.append({
                        "id": f"document:{document.value}",
                        "type": document.value,
                        "path": str(path),
                        "updatedAt": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(timespec="seconds"),
                    })
            return documents
        except (BridgeError, OSError):
            return []

    def _read_decisions(self, project: str) -> list[dict[str, Any]]:
        try:
            memory_dir = get_memory_dir(project, self._settings)
            path = memory_dir / MemoryDocument.DECISIONS.value
            if not path.exists():
                return []
            records: list[dict[str, Any]] = []
            for match in re.finditer(r"^##\s+(ADR-\d+)\s*$", path.read_text(encoding="utf-8"), re.MULTILINE):
                records.append({"id": match.group(1), "title": self._decision_title(path, match.end())})
            return records[-10:]
        except (BridgeError, OSError, UnicodeDecodeError):
            return []

    @staticmethod
    def _decision_title(path: Path, start: int) -> str:
        excerpt = path.read_text(encoding="utf-8")[start : start + 500]
        match = re.search(r"^Title:\s*(.+)$", excerpt, re.MULTILINE)
        return match.group(1).strip() if match else "Untitled decision"

    def _read_open_tasks(self, project: str) -> list[str]:
        try:
            memory_dir = get_memory_dir(project, self._settings)
            path = memory_dir / MemoryDocument.TASKS.value
            if not path.exists():
                return []
            return [
                match.group(2)
                for match in (_TASK_LINE.match(line) for line in path.read_text(encoding="utf-8").splitlines())
                if match and match.group(1).lower() == " "
            ][-20:]
        except (BridgeError, OSError, UnicodeDecodeError):
            return []

    @staticmethod
    def _last_test_result(workflow: Workflow | None) -> dict[str, Any] | None:
        if workflow is None:
            return None
        for stage in reversed(workflow.stages):
            if stage.stage_type is StageType.TESTING and stage.report:
                report = stage.report
                verdict = "passed" if re.search(r"\bpassed\b", report, re.IGNORECASE) else "failed"
                return {"status": verdict, "stageId": stage.id, "report": report, "updatedAt": stage.updated_at}
        return None

    @staticmethod
    def _belongs_to_project(entry: dict[str, Any], project: str) -> bool:
        path = str(entry.get("path", ""))
        return path.startswith(f"{project}:") or f"workflow/{project}" in path

    @staticmethod
    def _safe(label: str, operation: Callable[[], Any]) -> Any:
        try:
            return operation()
        except (BridgeError, OSError, ValueError) as exc:
            return {"status": "unavailable", "message": f"{label}: {exc}"}

    def _snapshot_path(self, project: str) -> Path:
        return self._settings.context_root / project / "current.json"

    def _save_snapshot(self, project: str, snapshot: dict[str, Any]) -> None:
        target = self._snapshot_path(project)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.tmp")
        temporary.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(target)
        # Keep a single workspace/context/current.json for tools that do not
        # yet know the project directory; it remains a context snapshot only.
        root_target = self._settings.context_root / "current.json"
        root_temporary = root_target.with_name(f".{root_target.name}.tmp")
        root_temporary.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        root_temporary.replace(root_target)
