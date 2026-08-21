"""Git policy: validate commit data and forbid option injection."""

from __future__ import annotations

import re

from app.security.validator import ValidationFailed

WORKFLOW_ID = re.compile(r"^wf_[0-9a-f]{12,32}$")
STAGE_ID = re.compile(r"^stg_[0-9a-f]{12,32}$")


class GitPolicyError(ValidationFailed):
    code = "git_policy_violation"


def validate_commit_message(message: str) -> str:
    cleaned = (message or "").strip()
    if not cleaned:
        raise GitPolicyError("Commit message must not be empty")
    if len(cleaned) > 500:
        raise GitPolicyError("Commit message exceeds 500 characters")
    if "\x00" in cleaned or cleaned.startswith("-"):
        raise GitPolicyError("Invalid commit message")
    return cleaned


def validate_binding(workflow_id: str, stage_id: str) -> tuple[str, str]:
    if not WORKFLOW_ID.match(workflow_id or ""):
        raise GitPolicyError("A valid workflow_id is required")
    if not STAGE_ID.match(stage_id or ""):
        raise GitPolicyError("A valid stage_id is required")
    return workflow_id, stage_id
