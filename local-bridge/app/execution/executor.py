from __future__ import annotations

import base64
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from secrets import token_hex
from typing import Any

from app.config import Settings
from app.git.manager import GitManager
from app.security.permissions import ApprovalStatus, ApprovalStore
from app.security.sandbox import get_project_dir, validate_path
from app.security.validator import ValidationFailed
from app.workflow.manager import WorkflowManager

from .models import (
    ExecutionProposal,
    ExecutionProposalStatus,
    ExecutionResult,
    ExecutionTask,
    ExecutionTaskStatus,
)
from .proposal import ExecutionProposalGenerator
from .storage import ExecutionStorage
from .verifier import VerificationService

ACTIVE_WORKFLOW_STATES = {"CREATED", "ANALYZING", "DESIGNING", "WAITING_APPROVAL", "IMPLEMENTING", "TESTING"}


class ControlledExecutor:
    """Execute an approved proposal.

    Execution here is strictly controlled: the executor validates every
    precondition, captures a reversible snapshot, and records a deterministic
    ExecutionResult. It NEVER writes project source files, runs shell commands,
    or mutates memory. Real file mutations continue to require the existing
    approval pipeline (patch_apply / file_write) through /permission/approve.
    """

    def __init__(
        self,
        storage: ExecutionStorage,
        settings: Settings,
        *,
        approvals: ApprovalStore | None = None,
        workflow_manager: WorkflowManager | None = None,
        verifier: VerificationService | None = None,
        snapshot_root: Path | None = None,
    ) -> None:
        self.storage = storage
        self.settings = settings
        self.approvals = approvals
        self.workflow_manager = workflow_manager
        self.verifier = verifier or VerificationService(settings)
        self.generator = ExecutionProposalGenerator()
        self.snapshot_root = snapshot_root or (settings.workspace_root.parent / "execution_snapshots")

    # -- preconditions --------------------------------------------------

    def _ensure_approval(self, approval_id: str | None) -> None:
        if not approval_id:
            raise ValidationFailed("Controlled execution requires an approved approval request")
        if self.approvals is None:
            raise ValidationFailed("Approval store is not available")
        request = self.approvals.get(approval_id)
        if request.status not in {ApprovalStatus.APPROVED, ApprovalStatus.EXECUTED}:
            raise ValidationFailed("Proposal execution requires an approved human approval")

    def _ensure_risk_unchanged(self, task: ExecutionTask, proposal: ExecutionProposal) -> None:
        expected = self.generator.generate(task)
        if expected.risk_score != proposal.risk_score:
            raise ValidationFailed("Proposal risk no longer matches the current task; regenerate the proposal")

    def _ensure_paths_valid(self, project: str, proposal: ExecutionProposal) -> None:
        from app.security.validator import BridgeError as _BridgeError

        for operation in proposal.operations:
            try:
                validate_path(project, operation.path, self.settings)
            except _BridgeError as exc:
                raise ValidationFailed(f"Execution path rejected: {exc.message}") from exc

    def _ensure_stage_active(self, task: ExecutionTask) -> None:
        if not task.workflow_id or self.workflow_manager is None:
            return
        workflow = self.workflow_manager.get(task.workflow_id)
        if workflow is None:
            raise ValidationFailed("Bound workflow no longer exists")
        if workflow.status.value not in ACTIVE_WORKFLOW_STATES:
            raise ValidationFailed(f"Workflow {workflow.status.value} is not active; execution is blocked")

    # -- snapshot -------------------------------------------------------

    def _task_dir(self, task: ExecutionTask) -> Path:
        segment = task.workflow_id or "standalone"
        target = self.snapshot_root / segment / task.id
        target.mkdir(parents=True, exist_ok=True)
        return target

    def capture_snapshot(self, task: ExecutionTask, proposal: ExecutionProposal) -> dict[str, Any]:
        target = self._task_dir(task)
        metadata_path = target / "metadata.json"
        if metadata_path.exists():
            return json.loads(metadata_path.read_text(encoding="utf-8"))
        files: list[dict[str, Any]] = []
        for operation in proposal.operations:
            path = validate_path(task.project, operation.path, self.settings)
            entry: dict[str, Any] = {"path": operation.path, "existed": False, "contentBase64": None}
            if path.is_file():
                entry["existed"] = True
                entry["contentBase64"] = base64.b64encode(path.read_bytes()).decode("ascii")
            files.append(entry)
        git_head: str | None = None
        try:
            root = get_project_dir(task.project, self.settings)
            head = (root / ".git").exists()
            if head:
                import subprocess

                result = subprocess.run(
                    ["git", "rev-parse", "HEAD"], cwd=str(root),
                    capture_output=True, text=True, shell=False, check=False, timeout=15,
                )
                if result.returncode == 0:
                    git_head = result.stdout.strip()
        except Exception:  # pragma: no cover - defensive
            git_head = None
        snapshot = {
            "proposalId": proposal.id,
            "taskId": task.id,
            "project": task.project,
            "workflowId": task.workflow_id,
            "capturedAt": time.time_ns(),
            "gitHead": git_head,
            "files": files,
        }
        metadata_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        return snapshot

    # -- execution ------------------------------------------------------

    def execute(self, task: ExecutionTask, proposal: ExecutionProposal, *, approval_id: str | None = None) -> ExecutionResult:
        self._ensure_approval(approval_id)
        self._ensure_risk_unchanged(task, proposal)
        self._ensure_paths_valid(task.project, proposal)
        self._ensure_stage_active(task)
        started = time.monotonic()

        task.status = ExecutionTaskStatus.APPROVED
        task.updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.storage.save_task(task)

        snapshot = self.capture_snapshot(task, proposal)
        if not (self._task_dir(task) / "metadata.json").exists():
            raise ValidationFailed("Execution snapshot was not created; execution aborted")

        task.status = ExecutionTaskStatus.EXECUTING
        task.updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.storage.save_task(task)

        files_changed = [operation.path for operation in proposal.operations]
        diff_summary = self._diff_summary(task.project, files_changed)
        errors: list[str] = []

        verification = self.verifier.verify(
            project=task.project,
            files=files_changed,
            snapshot_captured=True,
            approval_verified=True,
            diff_present=bool(diff_summary.get("changed", 0)),
        )
        duration_ms = int((time.monotonic() - started) * 1000)
        result = ExecutionResult(
            id=f"er_{token_hex(8)}",
            proposal_id=proposal.id,
            task_id=task.id,
            project=task.project,
            files_changed=files_changed,
            diff_summary=diff_summary,
            duration_ms=duration_ms,
            errors=errors,
            verification=verification,
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        self.storage.save_result(result)

        proposal.status = ExecutionProposalStatus.EXECUTED
        proposal.approval_id = approval_id
        self.storage.update_proposal(proposal)

        task.status = ExecutionTaskStatus.VERIFYING
        task.verification = verification
        task.updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.storage.save_task(task)

        task.status = ExecutionTaskStatus.COMPLETED if verification["status"] == "PASS" else ExecutionTaskStatus.FAILED
        task.updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.storage.save_task(task)

        return result

    def _diff_summary(self, project: str, files: list[str]) -> dict[str, Any]:
        try:
            diff = GitManager(self.settings).diff(project)
            changed = int(diff.get("size", 0) > 0)
            return {"changed": changed, "files": files, "diffBytes": int(diff.get("size", 0))}
        except Exception:
            return {"changed": 0, "files": files, "diffBytes": 0}
