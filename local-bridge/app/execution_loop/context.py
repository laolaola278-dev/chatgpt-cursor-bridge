from __future__ import annotations

from typing import Any

from app.execution_loop.orchestrator import ExecutionLoopOrchestrator


class LoopContextBuilder:
    """Assemble a read-only cross-loop context bundle.

    The bundle is derived entirely from persisted metadata; it never modifies
    loops, memory, or the approval store.
    """

    def __init__(self, orchestrator: ExecutionLoopOrchestrator, dag_manager=None) -> None:
        self.orchestrator = orchestrator
        self.dag_manager = dag_manager

    def build(self, loop_id: str) -> dict[str, Any]:
        loop = self.orchestrator.get(loop_id)
        bundle: dict[str, Any] = {
            "loop": loop.as_dict(),
            "tasks": [],
            "proposal": None,
            "result": None,
            "verification": loop.verification,
            "quality": loop.quality,
            "timeline": loop.history,
            "dagRelations": {"incoming": [], "outgoing": []},
            "relatedLoops": [],
            "readOnly": True,
        }
        for task_id in loop.task_ids:
            task = self.orchestrator.execution_manager.storage.get_task(task_id)
            if task is not None:
                bundle["tasks"].append(task.as_dict())
        if loop.proposal_id:
            proposal = self.orchestrator.execution_manager.storage.get_proposal(loop.proposal_id)
            bundle["proposal"] = proposal.as_dict() if proposal else None
        if loop.result_id:
            result = self.orchestrator.execution_manager.storage.get_result(loop.result_id)
            bundle["result"] = result.as_dict() if result else None

        if self.dag_manager is not None:
            for dag in self.dag_manager.list_dags(project=loop.project, limit=100):
                for edge in dag.edges:
                    if edge.source_loop == loop_id:
                        bundle["dagRelations"]["outgoing"].append({**edge.as_dict(), "dagId": dag.id})
                    if edge.target_loop == loop_id:
                        bundle["dagRelations"]["incoming"].append({**edge.as_dict(), "dagId": dag.id})
            related = set()
            for relation in bundle["dagRelations"]["outgoing"]:
                related.add(relation["targetLoop"])
            for relation in bundle["dagRelations"]["incoming"]:
                related.add(relation["sourceLoop"])
            bundle["relatedLoops"] = [self.orchestrator.get(rid).as_dict() for rid in sorted(related) if self.orchestrator.storage.get(rid) is not None]
        return bundle

    def related(self, loop_id: str) -> list[str]:
        bundle = self.build(loop_id)
        related = {item["sourceLoop"] for item in bundle["dagRelations"]["incoming"]}
        related.update(item["targetLoop"] for item in bundle["dagRelations"]["outgoing"])
        return sorted(related)
