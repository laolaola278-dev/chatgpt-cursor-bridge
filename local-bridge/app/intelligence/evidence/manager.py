from __future__ import annotations

from typing import Any

from .models import EvidenceBundle
from .storage import EvidenceStore


class DecisionEvidenceManager:
    def __init__(self, store: EvidenceStore) -> None:
        self.store = store

    def create_bundle(self, **kwargs: Any) -> EvidenceBundle:
        bundle = EvidenceBundle.build(**kwargs)
        return self.store.save(bundle)

    build_bundle = create_bundle

    def link_decision(self, bundle_id: str, decision_id: str, project_id: str) -> EvidenceBundle:
        return self.store.link_decision(bundle_id, decision_id, project_id)

    def for_decision(self, decision_id: str, project_id: str) -> EvidenceBundle | None:
        return self.store.get_for_decision(decision_id, project_id)
