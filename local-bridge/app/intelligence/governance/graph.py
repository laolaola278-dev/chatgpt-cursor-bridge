"""Phase 28 · Engineering Graph integration for governance findings.

Builds a read-only provenance graph linking Project -> Agent -> Prediction /
Recommendation / Decision -> Evaluation -> Risk -> Governance Finding. The
graph never mutates the Engineering Graph; mutation remains behind the
existing permission boundary.
"""

from __future__ import annotations

from typing import Any

from app.intelligence.governance.models import GovernanceRecord, RiskFinding
from app.intelligence.validation.models import DecisionOutcome, EvaluationRecord, RecommendationEffectiveness


class GovernanceGraphBuilder:
    """Deterministic read-only governance graph from stored records."""

    def build(
        self,
        *,
        project: str,
        evaluations: list[EvaluationRecord],
        effectiveness: list[RecommendationEffectiveness],
        decision_outcomes: list[DecisionOutcome],
        risks: list[RiskFinding],
        governance_records: list[GovernanceRecord],
    ) -> dict[str, Any]:
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        seen_nodes: set[str] = set()

        def add_node(node_id: str, node_type: str, label: str) -> None:
            if node_id in seen_nodes:
                return
            seen_nodes.add(node_id)
            nodes.append({"node_id": node_id, "node_type": node_type, "project": project, "label": label, "readOnly": True})

        def add_edge(source: str, target: str, relation: str) -> None:
            edges.append({"edge_id": f"{source}->{target}:{relation}", "source": source, "target": target, "relation": relation, "readOnly": True})

        add_node(f"project:{project}", "PROJECT", project)

        for evaluation in evaluations:
            add_node(f"evaluation:{evaluation.evaluation_id}", "EVALUATION", f"{evaluation.evaluation_kind} {evaluation.evaluation_result}")
            add_node(f"source:{evaluation.prediction_id}", "PREDICTION", evaluation.prediction_id)
            add_edge(f"project:{project}", f"source:{evaluation.prediction_id}", "HAS")
            add_edge(f"source:{evaluation.prediction_id}", f"evaluation:{evaluation.evaluation_id}", "EVALUATED_BY")
            if evaluation.agent_id:
                add_node(f"agent:{evaluation.agent_id}", "AGENT", evaluation.agent_id)
                add_edge(f"project:{project}", f"agent:{evaluation.agent_id}", "HAS")
                add_edge(f"agent:{evaluation.agent_id}", f"source:{evaluation.prediction_id}", "PRODUCED")
            if evaluation.model_id:
                add_node(f"model:{evaluation.model_id}", "MODEL", evaluation.model_id)
                add_edge(f"source:{evaluation.prediction_id}", f"model:{evaluation.model_id}", "PRODUCED_BY")

        for record in effectiveness:
            add_node(f"recommendation:{record.recommendation_id}", "RECOMMENDATION", record.recommendation_id)
            add_edge(f"project:{project}", f"recommendation:{record.recommendation_id}", "HAS")
            add_edge(f"recommendation:{record.recommendation_id}", f"evaluation:effectiveness:{record.effectiveness_id}", "EVALUATED_BY")

        for outcome in decision_outcomes:
            add_node(f"decision:{outcome.decision_id}", "DECISION", outcome.title)
            add_edge(f"project:{project}", f"decision:{outcome.decision_id}", "HAS")
            add_edge(f"decision:{outcome.decision_id}", f"evaluation:decision:{outcome.outcome_id}", "EVALUATED_BY")

        for finding in risks:
            add_node(f"risk:{finding.risk_id}", "RISK", f"{finding.risk_level} {finding.risk_score}")
            add_edge(f"source:{finding.source_id}", f"risk:{finding.risk_id}", "HAS_RISK")
            for governance in governance_records:
                if governance.source_id == finding.source_id:
                    add_node(f"governance:{governance.governance_id}", "GOVERNANCE_FINDING", governance.governance_result)
                    add_edge(f"risk:{finding.risk_id}", f"governance:{governance.governance_id}", "GOVERNED_BY")

        return {
            "project": project,
            "nodes": nodes,
            "edges": edges,
            "nodeCount": len(nodes),
            "edgeCount": len(edges),
            "readOnly": True,
        }


GovernanceGraph = GovernanceGraphBuilder
