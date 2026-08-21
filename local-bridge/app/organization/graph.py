"""Organization Knowledge Graph manager.

Company -> Teams -> Projects -> Services -> Repositories, plus org-level
architecture decisions and incidents. Entity writes are metadata only and
are always routed through the ApprovalStore by the API layer.
"""

from __future__ import annotations

from typing import Any

from app.security.validator import ValidationFailed

from .models import OrgEntity, OrgEntityType, OrgGraph
from .storage import OrganizationStorage

_VALID_TYPES = {item.value for item in OrgEntityType}


class OrganizationGraphManager:
    def __init__(self, storage: OrganizationStorage) -> None:
        self.storage = storage

    def register(
        self,
        entity_type: str,
        name: str,
        parent_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> OrgEntity:
        try:
            entity_type_enum = OrgEntityType(entity_type.strip().upper())
        except ValueError as exc:
            raise ValidationFailed(f"Unknown org entity type '{entity_type}'") from exc
        name = (name or "").strip()
        if not name or len(name) > 200:
            raise ValidationFailed("Org entity name must contain 1-200 characters")
        if entity_type_enum is OrgEntityType.COMPANY:
            parent_id = None
        elif parent_id is None:
            raise ValidationFailed(f"{entity_type_enum.value} entity requires a parent")
        else:
            parent = self.storage.get_entity(parent_id)
            if parent is None:
                raise ValidationFailed(f"Parent entity '{parent_id}' was not found")
        entity = OrgEntity(entity_type=entity_type_enum, name=name, parent_id=parent_id, metadata=metadata or {})
        self.storage.save_entity(entity)
        return entity

    def get_graph(self) -> OrgGraph:
        entities = self.storage.list_entities()
        graph = OrgGraph()
        for entity in entities:
            payload = entity.as_dict()
            entity_type = entity.entity_type
            if entity_type is OrgEntityType.COMPANY:
                graph.company = payload
            elif entity_type is OrgEntityType.TEAM:
                graph.teams.append(payload)
            elif entity_type is OrgEntityType.PROJECT:
                graph.projects.append(payload)
            elif entity_type is OrgEntityType.SERVICE:
                graph.services.append(payload)
            elif entity_type is OrgEntityType.REPOSITORY:
                graph.repositories.append(payload)
            elif entity_type is OrgEntityType.ARCHITECTURE_DECISION:
                graph.decisions.append(payload)
            elif entity_type is OrgEntityType.INCIDENT:
                graph.incidents.append(payload)
        return graph

    def get_subtree(self, entity_id: str) -> list[dict[str, Any]]:
        if self.storage.get_entity(entity_id) is None:
            raise ValidationFailed(f"Entity '{entity_id}' was not found")
        output: list[dict[str, Any]] = []
        frontier = [entity_id]
        seen: set[str] = set()
        while frontier:
            current = frontier.pop(0)
            if current in seen:
                continue
            seen.add(current)
            for child in self.storage.children(current):
                output.append(child.as_dict())
                frontier.append(child.id)
        return output
