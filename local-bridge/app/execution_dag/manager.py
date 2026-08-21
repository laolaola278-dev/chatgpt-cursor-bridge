from __future__ import annotations

from datetime import datetime, timezone
from secrets import token_hex

from app.audit.logger import AuditLogger
from app.execution_loop import ExecutionLoopOrchestrator
from app.security.validator import ResourceNotFound, ValidationFailed

from .models import DagEdge, DagStatus, DependencyType, ExecutionDag
from .storage import ExecutionDagStorage


class ExecutionDagManager:
    """Manage cross-loop execution order.

    The DAG only assigns ordering and generates proposals for ready loops. It
    never executes: every loop still enters the ApprovalStore pipeline and is
    executed through ControlledExecutor after explicit human approval.
    """

    def __init__(
        self,
        storage: ExecutionDagStorage,
        orchestrator: ExecutionLoopOrchestrator,
        *,
        audit: AuditLogger,
    ) -> None:
        self.storage = storage
        self.orchestrator = orchestrator
        self.audit = audit

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    # -- graph helpers --------------------------------------------------

    @staticmethod
    def _successors(edges: list[DagEdge]) -> dict[str, list[str]]:
        successors: dict[str, list[str]] = {edge.source_loop: [] for edge in edges}
        for edge in edges:
            successors.setdefault(edge.source_loop, []).append(edge.target_loop)
        return successors

    @staticmethod
    def _has_cycle(edges: list[DagEdge]) -> bool:
        successors = ExecutionDagManager._successors(edges)
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> bool:
            if node in visiting:
                return True
            if node in visited:
                return False
            visiting.add(node)
            for target in successors.get(node, []):
                if visit(target):
                    return True
            visiting.discard(node)
            visited.add(node)
            return False

        nodes = {edge.source_loop for edge in edges} | {edge.target_loop for edge in edges}
        return any(visit(node) for node in nodes)

    def _validate_edges(self, dag: ExecutionDag) -> None:
        known = set(dag.loop_ids)
        for edge in dag.edges:
            if edge.source_loop not in known:
                raise ValidationFailed(f"DAG edge source '{edge.source_loop}' is not part of the DAG")
            if edge.target_loop not in known:
                raise ValidationFailed(f"DAG edge target '{edge.target_loop}' is not part of the DAG")
            if edge.source_loop == edge.target_loop:
                raise ValidationFailed("DAG edges cannot self-reference a loop")
        if self._has_cycle(dag.edges):
            raise ValidationFailed("Cyclic execution dependency detected; A -> B -> A is forbidden")

    # -- lifecycle ------------------------------------------------------

    def create(self, *, project: str, loop_ids: list[str], edges: list[dict] | None = None) -> ExecutionDag:
        if not loop_ids:
            raise ValidationFailed("A DAG requires at least one execution loop")
        for loop_id in loop_ids:
            self.orchestrator.get(loop_id)  # 404 when the loop does not exist
        parsed_edges = [
            DagEdge(
                source_loop=edge["sourceLoop"],
                target_loop=edge["targetLoop"],
                dependency_type=DependencyType(edge.get("dependencyType", "depends_on")),
            )
            for edge in (edges or [])
        ]
        now = self._now()
        dag = ExecutionDag(
            id=f"edag_{token_hex(8)}",
            project=project,
            loop_ids=list(dict.fromkeys(loop_ids)),
            edges=parsed_edges,
            status=DagStatus.CREATED,
            created_at=now,
            updated_at=now,
            history=[],
        )
        self._validate_edges(dag)
        dag.history.append({"status": DagStatus.CREATED.value, "at": now, "detail": f"{len(dag.loop_ids)} loop(s)"})
        self.storage.save(dag)
        self.audit.record(
            action="execution_dag_created",
            path=f"{project}:dag/{dag.id}",
            permission="LEVEL_1",
            approved=False,
            result="created",
            detail=f"Execution DAG {dag.id} with {len(dag.edges)} edge(s)",
        )
        return dag

    def get(self, dag_id: str) -> ExecutionDag:
        dag = self.storage.get(dag_id)
        if dag is None:
            raise ResourceNotFound(f"Execution DAG '{dag_id}' was not found")
        return dag

    def list_dags(self, project: str | None = None, limit: int = 200) -> list[ExecutionDag]:
        return self.storage.list_dags(project=project, limit=limit)

    # -- readiness (read-only) ------------------------------------------

    def loop_statuses(self, dag_id: str) -> dict[str, str]:
        dag = self.get(dag_id)
        return {loop_id: self.orchestrator.get(loop_id).status.value for loop_id in dag.loop_ids}

    def ready_loops(self, dag_id: str) -> list[str]:
        dag = self.get(dag_id)
        statuses = self.loop_statuses(dag_id)
        dependents: dict[str, list[str]] = {}
        for edge in dag.edges:
            dependents.setdefault(edge.target_loop, []).append(edge.source_loop)
        ready: list[str] = []
        for loop_id in dag.loop_ids:
            if statuses[loop_id] in {"COMPLETED", "ROLLED_BACK", "CANCELLED", "FAILED"}:
                continue
            blocked = False
            for source in dependents.get(loop_id, []):
                if statuses.get(source) != "COMPLETED":
                    blocked = True
                    break
            if not blocked:
                ready.append(loop_id)
        return ready

    # -- advance (proposal-only) ----------------------------------------

    def advance(self, dag_id: str) -> dict:
        dag = self.get(dag_id)
        if dag.status in {DagStatus.COMPLETED, DagStatus.CANCELLED, DagStatus.FAILED}:
            raise ValidationFailed(f"Execution DAG is {dag.status.value}; it cannot be advanced")
        ready = self.ready_loops(dag_id)
        if not ready:
            raise ValidationFailed("No ready loop in the DAG; dependencies are not satisfied")
        loop = self.orchestrator.get(ready[0])
        prepared = self.orchestrator.prepare(loop.id)
        self.audit.record(
            action="execution_dag_advanced",
            path=f"{dag.project}:dag/{dag.id}",
            permission="LEVEL_1",
            approved=False,
            result="proposal",
            detail=f"proposal prepared for loop {prepared.id} (status {prepared.status.value})",
        )
        return {
            "dagId": dag.id,
            "loopId": prepared.id,
            "status": prepared.status.value,
            "proposalId": prepared.proposal_id,
            "readOnly": True,
        }

    def on_loop_completed(self, dag_id: str, loop_id: str) -> ExecutionDag:
        dag = self.get(dag_id)
        if loop_id not in dag.loop_ids:
            raise ValidationFailed("Loop is not part of the DAG")
        if all(self.loop_statuses(dag_id).get(loop) == "COMPLETED" for loop in dag.loop_ids):
            dag.status = DagStatus.COMPLETED
            dag.history.append({"status": DagStatus.COMPLETED.value, "at": self._now(), "detail": "all loops completed"})
            dag.updated_at = self._now()
            self.storage.save(dag)
            self.audit.record(
                action="execution_dag_completed",
                path=f"{dag.project}:dag/{dag.id}",
                permission="LEVEL_1",
                approved=False,
                result="completed",
                detail="All DAG loops completed",
            )
        return dag
