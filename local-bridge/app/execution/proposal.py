from __future__ import annotations

from secrets import token_hex

from app.security.validator import ValidationFailed

from .models import ExecutionOperation, ExecutionProposal, ExecutionTask


class ExecutionProposalGenerator:
    """Generate an ExecutionProposal from a task.

    The proposal is metadata only. It lists intended file operations and a
    deterministic risk score; it is never executed by this class.
    """

    @staticmethod
    def _operations_for(task: ExecutionTask) -> list[ExecutionOperation]:
        operations: list[ExecutionOperation] = []
        for path in task.files:
            operations.append(
                ExecutionOperation(
                    operation_type="file.patch",
                    path=path,
                    reason=f"implement task: {task.title[:80]}",
                )
            )
        return operations

    def generate(self, task: ExecutionTask) -> ExecutionProposal:
        if not task.files:
            raise ValidationFailed("Execution proposal requires affected files")
        operations = self._operations_for(task)
        estimated = len(operations) + min(10, len(task.dependencies))
        risk_score = max(0, min(100, task.risk_score + len(operations) * 5))
        return ExecutionProposal(
            id=f"ep_{token_hex(8)}",
            task_id=task.id,
            project=task.project,
            workflow_id=task.workflow_id,
            operations=operations,
            estimated_changes=estimated,
            risk_score=risk_score,
        )
