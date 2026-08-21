from __future__ import annotations

from app.audit.logger import AuditLogger

from .models import ExecutionLoop, LoopStatus
from .orchestrator import ExecutionLoopOrchestrator

_INTERRUPTED = {
    LoopStatus.PLANNING,
    LoopStatus.PROPOSAL_READY,
    LoopStatus.WAITING_APPROVAL,
    LoopStatus.EXECUTING,
    LoopStatus.VERIFYING,
}


class ExecutionLoopRecovery:
    """Runtime Recovery 2.0 for execution loops.

    On startup, loops left in an interrupted state are marked RECOVERED and
    audited. Recovery never resumes execution, never approves a proposal and
    never invokes the executor: the user must explicitly re-confirm any
    subsequent step.
    """

    def __init__(self, orchestrator: ExecutionLoopOrchestrator, audit: AuditLogger | None = None) -> None:
        self.orchestrator = orchestrator
        self.audit = audit

    def recover(self) -> list[ExecutionLoop]:
        recovered: list[ExecutionLoop] = []
        for loop in self.orchestrator.list_loops(limit=1000):
            if loop.status not in _INTERRUPTED:
                continue
            self.orchestrator.recover(loop.id)
            recovered.append(loop)
        return recovered

    def recoverable(self) -> list[ExecutionLoop]:
        return [loop for loop in self.orchestrator.list_loops(limit=1000) if loop.status in _INTERRUPTED]
