"""Execution boundary for Phase 10.

There is intentionally no implementation here: the existing approval pipeline
owns all side effects. Calling this class is a security failure, not a shortcut.
"""

from __future__ import annotations

from typing import Any

from app.security.validator import ApprovalError


class RuntimeExecutor:
    def execute(self, proposal: Any) -> None:
        raise ApprovalError("Runtime executor is disabled; proposals must enter the existing ApprovalManager")
