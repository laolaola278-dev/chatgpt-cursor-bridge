"""Phase 16 approval-controlled engineering loop.

The orchestrator only coordinates: it plans, generates proposals, collects
verification and queues approvals. Direct side effects remain exclusively in
the existing ApprovalStore -> /permission/approve -> ControlledExecutor chain.
"""

from .context import LoopContextBuilder
from .models import ExecutionLoop, LoopStatus
from .orchestrator import ExecutionLoopOrchestrator
from .recovery import ExecutionLoopRecovery
from .rollback_manager import ExecutionLoopRollbackManager
from .storage import ExecutionLoopStorage

__all__ = [
    "ExecutionLoop",
    "ExecutionLoopOrchestrator",
    "ExecutionLoopRecovery",
    "ExecutionLoopRollbackManager",
    "ExecutionLoopStorage",
    "LoopContextBuilder",
    "LoopStatus",
]
