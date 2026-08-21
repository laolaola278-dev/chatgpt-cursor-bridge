from __future__ import annotations

from .models import ExecutionProposal, ExecutionTask
from .proposal import ExecutionProposalGenerator
from .task_builder import ImplementationTaskBuilder


class ExecutionPlanner:
    """Turn an approved Engineering Plan into task and proposal metadata.

    Planner output is never an action: nothing here writes to project files,
    runs commands, or approves anything.
    """

    def __init__(self) -> None:
        self.builder = ImplementationTaskBuilder()
        self.proposal_generator = ExecutionProposalGenerator()

    def build_tasks(self, *, plan_id: str, project: str, workflow_id: str | None, plan_content: str) -> list[ExecutionTask]:
        return self.builder.build(
            plan_id=plan_id,
            project=project,
            workflow_id=workflow_id,
            plan_content=plan_content,
        )

    def build_proposal(self, task: ExecutionTask) -> ExecutionProposal:
        return self.proposal_generator.generate(task)
