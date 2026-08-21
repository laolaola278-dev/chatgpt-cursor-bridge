from __future__ import annotations

from collections.abc import Iterable
from secrets import token_hex
from typing import Any

from app.intelligence.common import ensure_project, ids, sanitize_text

from .models import EvidenceGraph, EvidenceGraphEdge, EvidenceGraphNode, EvidenceRelation


class IntelligenceEvidenceGraph:
    """Construct graph metadata in memory; it has no executor or write API."""

    @staticmethod
    def _get(item: Any, *names: str, default: Any = None) -> Any:
        if isinstance(item, dict):
            for name in names:
                if item.get(name) is not None:
                    return item[name]
            return default
        for name in names:
            value = getattr(item, name, None)
            if value is not None:
                return value
        return default

    @staticmethod
    def _items(value: Iterable[Any] | None) -> list[Any]:
        return list(value or [])

    def build(
        self,
        project: str,
        *,
        observations: Iterable[Any] = (),
        patterns: Iterable[Any] = (),
        trends: Iterable[Any] = (),
        correlations: Iterable[Any] = (),
        predictions: Iterable[Any] = (),
        impact_predictions: Iterable[Any] = (),
        recommendations: Iterable[Any] = (),
        decisions: Iterable[Any] = (),
        outcomes: Iterable[Any] = (),
        knowledge: Iterable[Any] = (),
        evaluations: Iterable[Any] = (),
    ) -> EvidenceGraph:
        project = ensure_project(project)
        nodes: dict[str, EvidenceGraphNode] = {}
        edges: list[EvidenceGraphEdge] = []

        def add_node(item: Any, node_type: str, label_names: tuple[str, ...], *, metadata: dict[str, Any] | None = None) -> str | None:
            raw_id = self._get(item, "id", "node_id", "nodeId", "pattern_id", "patternId", "trend_id", "trendId", "correlation_id", "correlationId", "prediction_id", "predictionId", "recommendation_id", "recommendationId", "outcome_id", "outcomeId", "evaluation_id", "evaluationId", default=None)
            if raw_id is None:
                raw_id = self._get(item, "strategy_id", "strategyId", "decision_id", "decisionId", default=None)
            if raw_id is None:
                return None
            item_project = self._get(item, "project_id", "projectId", "project", default=project)
            if item_project != project:
                return None
            node_id = sanitize_text(raw_id, limit=240)
            label = next((self._get(item, name, default="") for name in label_names if self._get(item, name, default="")), node_id)
            nodes.setdefault(node_id, EvidenceGraphNode(node_id, node_type, project, str(label), metadata or {}))
            return node_id

        def edge(source: str | None, target: str | None, relation: EvidenceRelation, evidence: Iterable[Any] = ()) -> None:
            if not source or not target or source == target or source not in nodes or target not in nodes:
                return
            edge_id = f"edge_{token_hex(6)}"
            edges.append(EvidenceGraphEdge(edge_id, project, source, target, relation, ids(list(evidence))))

        obs = self._items(observations)
        pats = self._items(patterns)
        trs = self._items(trends)
        corrs = self._items(correlations)
        preds = self._items(predictions)
        impacts = self._items(impact_predictions)
        recs = self._items(recommendations)
        decs = self._items(decisions)
        outs = self._items(outcomes)
        know = self._items(knowledge)
        evals = self._items(evaluations)

        for item in obs:
            add_node(item, "OBSERVATION", ("summary", "source", "type"))
        for item in pats:
            node = add_node(item, "PATTERN", ("summary", "pattern_type", "patternType"))
            for evidence_id in self._get(item, "evidence", default=[]) or []:
                edge(node, str(evidence_id), EvidenceRelation.OBSERVED_FROM, [str(evidence_id)])
        for item in trs:
            node = add_node(item, "TREND", ("metric", "direction", "period"))
            for evidence_id in self._get(item, "evidence", default=[]) or []:
                edge(node, str(evidence_id), EvidenceRelation.OBSERVED_FROM, [str(evidence_id)])
        for item in corrs:
            node = add_node(item, "CORRELATION", ("relationship", "interpretation"))
            event_ids = self._get(item, "events", "event_ids", default=[]) or []
            for event_id in event_ids:
                edge(node, str(event_id), EvidenceRelation.CORRELATED_WITH, [str(event_id)])
        for item in preds:
            node = add_node(item, "PREDICTION", ("prediction", "prediction_type", "predictionType"))
            for evidence_id in self._get(item, "evidence", default=[]) or []:
                edge(str(evidence_id), node, EvidenceRelation.SUPPORTS, [str(evidence_id)])
        for item in impacts:
            node = add_node(item, "IMPACT_PREDICTION", ("risk_level", "riskLevel", "why_risky"))
            for evidence_id in self._get(item, "evidence", default=[]) or []:
                edge(str(evidence_id), node, EvidenceRelation.SUPPORTS, [str(evidence_id)])
        for item in recs:
            node = add_node(item, "RECOMMENDATION", ("recommendation", "rationale"))
            prediction_id = self._get(item, "prediction_id", "predictionId", default=None)
            edge(str(prediction_id) if prediction_id else None, node, EvidenceRelation.RECOMMENDS, [str(prediction_id)] if prediction_id else [])
            for evidence_id in self._get(item, "evidence", default=[]) or []:
                edge(str(evidence_id), node, EvidenceRelation.SUPPORTS, [str(evidence_id)])
        for item in decs:
            node = add_node(item, "DECISION", ("title", "decision", "recommendation"))
            for recommendation_id in self._get(item, "recommendation_ids", "recommendationIds", default=[]) or []:
                edge(node, str(recommendation_id), EvidenceRelation.DECIDED_BY, [str(recommendation_id)])
            recommendation_id = self._get(item, "recommendation_id", "recommendationId", default=None)
            edge(node, str(recommendation_id) if recommendation_id else None, EvidenceRelation.DECIDED_BY, [str(recommendation_id)] if recommendation_id else [])
        for item in outs:
            node = add_node(item, "OUTCOME", ("actual_outcome", "actualOutcome", "status"))
            decision_id = self._get(item, "decision_id", "decisionId", default=None)
            edge(str(decision_id) if decision_id else None, node, EvidenceRelation.RESULTED_IN, [str(decision_id)] if decision_id else [])
        for item in know:
            node = add_node(item, "KNOWLEDGE", ("content", "category", "source"))
            for evidence_id in self._get(item, "evidence", default=[]) or []:
                edge(str(evidence_id), node, EvidenceRelation.LEARNED_FROM, [str(evidence_id)])
        for item in evals:
            node = add_node(item, "EVALUATION", ("evaluation_id", "evaluationId", "success", "correct"))
            source_id = self._get(item, "prediction_id", "predictionId", "recommendation_id", "recommendationId", default=None)
            edge(str(source_id) if source_id else None, node, EvidenceRelation.SUPPORTS, [str(source_id)] if source_id else [])

        # De-duplicate edges deterministically while retaining all provenance IDs.
        unique: dict[tuple[str, str, str], EvidenceGraphEdge] = {}
        for item in edges:
            key = (item.source_id, item.target_id, item.relationship)
            if key not in unique:
                unique[key] = item
            else:
                previous = unique[key]
                unique[key] = EvidenceGraphEdge(previous.edge_id, previous.project_id, previous.source_id, previous.target_id, previous.relation, ids(previous.evidence + item.evidence))
        return EvidenceGraph(project, list(nodes.values()), list(unique.values()))

    create = build
    build_graph = build


EvidenceGraphBuilder = IntelligenceEvidenceGraph
