from __future__ import annotations

from typing import Any

from app.config import Settings


class VerificationService:
    """Analyze an execution outcome and produce verification suggestions.

    Verification is analysis only. It never auto-fixes, never reruns tests,
    and never modifies files.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def verify(
        self,
        *,
        project: str,
        files: list[str],
        snapshot_captured: bool = False,
        approval_verified: bool = False,
        diff_present: bool = False,
        test_passed: bool | None = None,
        quality_score: int | None = None,
        dependency_break: bool = False,
    ) -> dict[str, Any]:
        checks: list[str] = []
        if approval_verified:
            checks.append("approval_verified")
        if snapshot_captured:
            checks.append("snapshot_captured")
        if diff_present:
            checks.append("git_diff_present")
        if test_passed is True:
            checks.append("tests_passed")
        elif test_passed is False:
            checks.append("tests_failed")
        else:
            checks.append("tests_pending_human_confirmation")
        checks.append("no_dependency_break" if not dependency_break else "dependency_break_detected")
        if quality_score is not None:
            checks.append(f"quality_score:{max(0, min(100, int(quality_score)))}")
        checks.append(f"files_analyzed:{len(files)}")

        failed = dependency_break or test_passed is False or not snapshot_captured or not approval_verified
        status = "FAIL" if failed else "PASS"
        return {
            "status": status,
            "checks": checks,
            "project": project,
            "files": files,
            "snapshotCaptured": snapshot_captured,
            "approvalVerified": approval_verified,
            "qualityScore": quality_score,
            "readOnly": True,
            "autoFix": False,
        }
