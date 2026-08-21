from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app.audit.logger import AuditLogger
from app.security.permissions import PermissionLevel

from .models import EngineeringGraph, GraphEdge, GraphNode
from .storage import EngineeringGraphStorage


class EngineeringGraphManager:
    def __init__(self, storage: EngineeringGraphStorage, audit: AuditLogger | None = None) -> None:
        self.storage = storage
        self.audit = audit

    def rebuild(self, project: str, *, workflows: Iterable[dict[str, Any]] = (), tasks: Iterable[dict[str, Any]] = (), decisions: Iterable[dict[str, Any]] = (), loops: Iterable[dict[str, Any]] = (), agents: Iterable[dict[str, Any]] = (), memories: Iterable[dict[str, Any]] = (), verifications: Iterable[dict[str, Any]] = ()) -> EngineeringGraph:
        self.storage.clear_project(project)
        nodes: dict[str, GraphNode] = {}
        edges: list[GraphEdge] = []

        def add_node(node_type: str, value_id: str, label: str, metadata: dict[str, Any] | None = None) -> str:
            node_id = f"{node_type}:{value_id}"
            nodes[node_id] = GraphNode(node_id, node_type, project, label, metadata or {})
            return node_id

        def connect(source: str, target: str, relation: str, metadata: dict[str, Any] | None = None) -> None:
            if source and target and source != target:
                edges.append(GraphEdge(source, target, relation, project, metadata or {}))

        for item in workflows:
            workflow_id = str(item.get("id") or item.get("workflowId") or "unknown")
            add_node("workflow", workflow_id, workflow_id, item)
        for item in agents:
            agent_id = str(item.get("id") or item.get("agentId") or "unknown")
            add_node("agent", agent_id, str(item.get("role") or agent_id), item)
        for item in tasks:
            task_id = str(item.get("id") or item.get("taskId") or "unknown")
            task_node = add_node("task", task_id, str(item.get("title") or task_id), item)
            workflow_id = item.get("workflowId") or item.get("workflow_id")
            agent_id = item.get("agentId") or item.get("agent_id")
            if workflow_id: connect(f"workflow:{workflow_id}", task_node, "depends_on")
            if agent_id: connect(task_node, f"agent:{agent_id}", "created_by")
        for item in decisions:
            decision_id = str(item.get("id") or item.get("decisionId") or "unknown")
            decision_node = add_node("decision", decision_id, str(item.get("title") or decision_id), item)
            proposal_id = item.get("proposalId") or item.get("proposal_id")
            if proposal_id: connect(decision_node, f"proposal:{proposal_id}", "depends_on")
        for item in loops:
            loop_id = str(item.get("id") or item.get("loopId") or "unknown")
            loop_node = add_node("execution_loop", loop_id, loop_id, item)
            workflow_id = item.get("workflowId") or item.get("workflow_id")
            if workflow_id: connect(f"workflow:{workflow_id}", loop_node, "depends_on")
            for task_id in item.get("taskIds") or item.get("task_ids") or []:
                connect(loop_node, f"task:{task_id}", "depends_on")
        for item in verifications:
            verification_id = str(item.get("id") or item.get("verificationId") or "unknown")
            verification_node = add_node("verification", verification_id, verification_id, item)
            loop_id = item.get("executionLoopId") or item.get("execution_loop_id")
            if loop_id: connect(verification_node, f"execution_loop:{loop_id}", "verified_by")
        for item in memories:
            memory_id = str(item.get("id") or item.get("memoryId") or "unknown")
            memory_node = add_node("memory", memory_id, str(item.get("title") or item.get("category") or memory_id), item)
            decision_id = item.get("decisionId") or item.get("decision_id")
            if decision_id: connect(memory_node, f"decision:{decision_id}", "supersedes")

        for node in nodes.values(): self.storage.save_node(node)
        seen: set[tuple[str, str, str]] = set()
        for edge in edges:
            key = (edge.source, edge.target, edge.relation)
            if key not in seen:
                seen.add(key); self.storage.save_edge(edge)
        graph = self.storage.get_graph(project)
        if self.audit:
            self.audit.record(action="engineering_graph_rebuild", path=f"{project}:engineering-graph", permission=PermissionLevel.LEVEL_1.value, approved=True, result="success", detail=f"{len(graph.nodes)} nodes, {len(graph.edges)} edges")
        return graph

    def get(self, project: str) -> EngineeringGraph:
        return self.storage.get_graph(project)

    def query(self, project: str, keyword: str) -> dict[str, Any]:
        graph = self.storage.get_graph(project)
        needle = (keyword or "").strip().lower()
        if not needle:
            return {**graph.as_dict(), "query": keyword, "matched": 0}
        matched_ids = {node.id for node in graph.nodes if needle in node.id.lower() or needle in node.label.lower() or needle in str(node.metadata).lower()}
        edges = [edge for edge in graph.edges if edge.source in matched_ids or edge.target in matched_ids or needle in edge.relation.lower()]
        related_ids = matched_ids | {edge.source for edge in edges} | {edge.target for edge in edges}
        nodes = [node for node in graph.nodes if node.id in related_ids]
        return {"project": project, "query": keyword, "nodes": [node.as_dict() for node in nodes], "edges": [edge.as_dict() for edge in edges], "matched": len(matched_ids), "readOnly": True}
