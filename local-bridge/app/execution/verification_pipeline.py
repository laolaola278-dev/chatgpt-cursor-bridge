from __future__ import annotations

from datetime import datetime, timezone
from secrets import token_hex
from typing import Any

from app.security.validator import ValidationFailed

from .models import ExecutionResult


class VerificationPipeline:
    """Aggregate post-execution evidence into a Verification Evidence Bundle.

    Detection only. The pipeline never fixes files, reruns commands, or
    mutates memory. Evidence is collected from the execution result plus any
    externally observed quality/risk/test signals.
    """

    def build(
        self,
        result: ExecutionResult,
        *,
        quality_score: int | None = None,
        risk_score: int | None = None,
        test_passed: bool | None = None,
        test_evidence: dict[str, Any] | None = None,
        dependency_impact: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        base = result.verification
        checks: list[str] = []
        if base.get("approvalVerified"):
            checks.append("approval_verified")
        if base.get("snapshotCaptured"):
            checks.append("snapshot_verified")
        diff_checked = bool(base.get("checks") and any(check.startswith("git_diff") or check.startswith("files_analyzed") for check in base["checks"]))
        if diff_checked:
            checks.append("diff_checked")
        if test_passed is True:
            checks.append("tests_passed")
        elif test_passed is False:
            checks.append("tests_failed")
        else:
            checks.append("tests_not_run")
        if quality_score is not None:
            checks.append(f"quality_score:{max(0, min(100, int(quality_score)))}")
        if risk_score is not None:
            checks.append(f"risk_score:{max(0, min(100, int(risk_score)))}")
        if dependency_impact and dependency_impact.get("affectedModules"):
            checks.append(f"dependency_impact:{len(dependency_impact['affectedModules'])}")
        if test_evidence and test_evidence.get("command"):
            checks.append("test_evidence_captured")

        failed = test_passed is False or base.get("status") == "FAIL"
        status = "FAIL" if failed else "PASS"

        evidence: dict[str, Any] = {
            "approval": {"verified": bool(base.get("approvalVerified"))},
            "snapshot": {
                "captured": bool(base.get("snapshotCaptured")),
                "files": base.get("files", []),
            },
            "gitDiff": {
                "changed": bool(result.diff_summary.get("changed", 0)),
                "files": result.files_changed,
                "diffBytes": int(result.diff_summary.get("diffBytes", 0)),
            },
            "testResult": "passed" if test_passed is True else "failed" if test_passed is False else "not_run",
            "testEvidence": test_evidence or {},
            "qualityScore": quality_score,
            "riskScore": risk_score,
            "dependencyImpact": dependency_impact or {"affectedModules": []},
            "durationMs": result.duration_ms,
            "collectedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        return {
            "id": f"vr_{token_hex(8)}",
            "executionId": result.id,
            "checks": checks,
            "status": status,
            "qualityScore": quality_score,
            "riskScore": risk_score,
            "testResult": "passed" if test_passed is True else "failed" if test_passed is False else "not_run",
            "evidence": evidence,
            "createdAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "readOnly": True,
            "autoFix": False,
        }

    def validate(self, report: dict[str, Any]) -> dict[str, Any]:
        if not report.get("checks"):
            raise ValidationFailed("Verification report has no checks")
        if report.get("status") not in {"PASS", "FAIL"}:
            raise ValidationFailed("Verification report status must be PASS or FAIL")
        if not isinstance(report.get("evidence"), dict):
            raise ValidationFailed("Verification evidence bundle is missing")
        return report
