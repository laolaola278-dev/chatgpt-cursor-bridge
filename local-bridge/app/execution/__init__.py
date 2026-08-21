"""Phase 15 controlled engineering execution.

Every write here is metadata-first and approval-gated. The ControlledExecutor
validates preconditions, captures reversible snapshots and records results; it
never mutates project sources, runs shell commands, or bypasses ApprovalStore.
"""

from .executor import ControlledExecutor
from .manager import ExecutionManager
from .models import ExecutionProposal, ExecutionResult, ExecutionTask, ExecutionTaskStatus
from .planner import ExecutionPlanner
from .proposal import ExecutionProposalGenerator
from .storage import ExecutionStorage
from .task_builder import ImplementationTaskBuilder
from .verifier import VerificationService

__all__ = [
    "ControlledExecutor",
    "ExecutionManager",
    "ExecutionPlanner",
    "ExecutionProposal",
    "ExecutionProposalGenerator",
    "ExecutionResult",
    "ExecutionStorage",
    "ExecutionTask",
    "ExecutionTaskStatus",
    "ImplementationTaskBuilder",
    "VerificationService",
]
