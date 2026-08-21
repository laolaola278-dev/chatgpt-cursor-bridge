"""Architecture drift detector.

Read-only comparison of the current code reality (file/module layout and
imports) against the recorded engineering knowledge graph. Detects:

- unrecorded_dependency       : import edge with no recorded graph edge
- module_boundary_change      : new top-level module not recorded in graph
- circular_dependency         : cycle in the current dependency graph
- design_decision_drift       : approved/implemented decision without evidence
- deprecated_component_usage  : code still references a deprecated component

The detector only produces an ArchitectureDriftReport. It never fixes,
blocks execution or writes memory.
"""

from __future__ import annotations

from typing import Any

from .models import ArchitectureDriftReport, DriftIssue

_SEVERITY_WEIGHT = {"low": 5.0, "medium": 15.0, "high": 30.0}
_RECORDED_RELATIONS = {"depends_on", "calls", "implements", "tested_by"}


def _severity_weight(severity: str) -> float:
    return _SEVERITY_WEIGHT.get(severity, 5.0)


class ArchitectureDriftDetector:
    """Compares current architecture inputs against recorded graph data."""

    def detect(
        self,
        project: str,
        *,
        graph: dict[str, Any] | None = None,
        code_files: list[dict[str, Any]] | None = None,
        dependencies: list[dict[str, Any]] | None = None,
        decisions: list[dict[str, Any]] | None = None,
        deprecated_components: list[str] | None = None,
    ) -> ArchitectureDriftReport:
        graph = graph or {}
        nodes = graph.get("nodes") or []
        edges = graph.get("edges") or []
        code_files = code_files or []
        dependencies = dependencies or []
        decisions = decisions or []
        deprecated_components = deprecated_components or []

        issues: list[DriftIssue] = []
        issues.extend(self._unrecorded_dependencies(edges, dependencies))
        issues.extend(self._module_boundary_changes(nodes, code_files))
        issues.extend(self._circular_dependencies(dependencies))
        issues.extend(self._design_decision_drift(nodes, edges, decisions))
        issues.extend(self._deprecated_component_usage(dependencies, deprecated_components))

        drift_score = int(
            min(100, sum(_severity_weight(issue.severity) for issue in issues))
        )
        risk_level = "high" if drift_score >= 50 else "medium" if drift_score >= 25 else "low"

        return ArchitectureDriftReport(
            project=project,
            drift_score=drift_score,
            issues=sorted(issues, key=lambda issue: _severity_weight(issue.severity), reverse=True),
            risk_level=risk_level,
        )

    # -- detectors ----------------------------------------------------------

    @staticmethod
    def _edge_key(edge: dict[str, Any]) -> tuple[str, str]:
        return str(edge.get("source", "")), str(edge.get("target", ""))

    def _unrecorded_dependencies(
        self, edges: list[dict[str, Any]], dependencies: list[dict[str, Any]]
    ) -> list[DriftIssue]:
        recorded = {self._edge_key(edge) for edge in edges if edge.get("relation") in _RECORDED_RELATIONS}
        issues: list[DriftIssue] = []
        for dep in dependencies:
            source = str(dep.get("source") or dep.get("path") or "")
            target = str(dep.get("target") or dep.get("import") or "")
            if not source or not target:
                continue
            if (source, target) in recorded:
                continue
            # Only flag module-to-module edges, not intra-file noise.
            if source == target:
                continue
            issues.append(
                DriftIssue(
                    issue_type="unrecorded_dependency",
                    severity="medium",
                    location=f"{source} -> {target}",
                    evidence=[f"Import edge {source} -> {target} has no recorded graph relation"],
                    recommendation="Record the dependency in the engineering knowledge graph or update module boundaries",
                )
            )
        return issues[:50]

    @staticmethod
    def _module_boundary_changes(
        nodes: list[dict[str, Any]], code_files: list[dict[str, Any]]
    ) -> list[DriftIssue]:
        recorded_modules = {
            str(node.get("label", "")).split("/")[0]
            for node in nodes
            if str(node.get("type", "")).lower() in {"module", "service"}
        }
        recorded_modules.update(
            str(node.get("id", "")).split("/")[0] for node in nodes
            if str(node.get("type", "")).lower() in {"module", "service"}
        )
        seen: set[str] = set()
        issues: list[DriftIssue] = []
        for entry in code_files:
            path = str(entry.get("path", ""))
            module = path.split("/")[0]
            if not module or module in seen:
                continue
            seen.add(module)
            if module not in recorded_modules:
                issues.append(
                    DriftIssue(
                        issue_type="module_boundary_change",
                        severity="low",
                        location=module,
                        evidence=[f"Top-level module '{module}' exists in code but is not recorded in the knowledge graph"],
                        recommendation="Record the new module boundary or fold it into an existing recorded module",
                    )
                )
        return issues[:30]

    @staticmethod
    def _circular_dependencies(dependencies: list[dict[str, Any]]) -> list[DriftIssue]:
        adjacency: dict[str, set[str]] = {}
        for dep in dependencies:
            source = str(dep.get("source") or dep.get("path") or "")
            target = str(dep.get("target") or dep.get("import") or "")
            if source and target and source != target:
                adjacency.setdefault(source, set()).add(target)

        issues: list[DriftIssue] = []
        for node in sorted(adjacency):
            for target in sorted(adjacency.get(node, set())):
                if node in adjacency.get(target, set()):
                    issues.append(
                        DriftIssue(
                            issue_type="circular_dependency",
                            severity="high",
                            location=f"{node} <-> {target}",
                            evidence=[f"Mutual import detected between {node} and {target}"],
                            recommendation="Break the cycle by extracting the shared responsibility into a separate module",
                        )
                    )
        return issues[:30]

    @staticmethod
    def _design_decision_drift(
        nodes: list[dict[str, Any]], edges: list[dict[str, Any]], decisions: list[dict[str, Any]]
    ) -> list[DriftIssue]:
        decision_ids = {str(decision.get("id", "")) for decision in decisions}
        referenced = {str(edge.get("source", "")) for edge in edges}
        referenced.update(str(edge.get("target", "")) for edge in edges)
        referenced.update(str(node.get("id", "")) for node in nodes)

        issues: list[DriftIssue] = []
        for decision in decisions:
            decision_id = str(decision.get("id", ""))
            status = str(decision.get("status", "")).upper()
            if status not in {"APPROVED", "IMPLEMENTED"}:
                continue
            if decision_id in referenced:
                continue
            title = str(decision.get("title", decision_id))[:120]
            issues.append(
                DriftIssue(
                    issue_type="design_decision_drift",
                    severity="medium",
                    location=decision_id,
                    evidence=[f"Approved decision '{title}' has no implementation evidence in the knowledge graph"],
                    recommendation="Link the decision to implemented artifacts or mark it as superseded",
                )
            )
        return issues[:30]

    @staticmethod
    def _deprecated_component_usage(
        dependencies: list[dict[str, Any]], deprecated_components: list[str]
    ) -> list[DriftIssue]:
        deprecated = {name.lower() for name in deprecated_components}
        if not deprecated:
            return []
        issues: list[DriftIssue] = []
        for dep in dependencies:
            target = str(dep.get("target") or dep.get("import") or "")
            if target.lower() in deprecated or any(tok in target.lower() for tok in deprecated):
                issues.append(
                    DriftIssue(
                        issue_type="deprecated_component_usage",
                        severity="medium",
                        location=target,
                        evidence=[f"Current code still imports deprecated component '{target}'"],
                        recommendation="Migrate away from the deprecated component before further changes",
                    )
                )
        return issues[:30]
