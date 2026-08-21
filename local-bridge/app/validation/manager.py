from __future__ import annotations

import secrets
from typing import Any

from app.audit.logger import AuditLogger
from app.security.permissions import PermissionLevel

from .models import ValidationProject, ValidationRun, ValidationScenario, ValidationScenarioType, ValidationStatus
from .reference_cases import reference_case
from .storage import ValidationStorage

_ALLOWED = {
    ValidationStatus.CREATED: {ValidationStatus.RUNNING, ValidationStatus.CANCELLED},
    ValidationStatus.RUNNING: {ValidationStatus.COMPLETED, ValidationStatus.FAILED, ValidationStatus.CANCELLED},
    ValidationStatus.COMPLETED: set(), ValidationStatus.FAILED: set(), ValidationStatus.CANCELLED: set(),
}


class ValidationManager:
    def __init__(self, storage: ValidationStorage, audit: AuditLogger | None = None) -> None:
        self.storage = storage; self.audit = audit

    def create(self, project: str, repository: str, language: str, framework: str, scenarios: list[dict[str, Any]]) -> ValidationProject:
        record = ValidationProject(f"val_{secrets.token_hex(8)}", project, repository, language, framework)
        self.storage.save_project(record)
        records = [
            ValidationScenario(f"vsc_{secrets.token_hex(6)}", record.id, ValidationScenarioType(str(item.get("type", "FEATURE")).upper()), str(item.get("description", "")))
            for item in scenarios
        ]
        self.storage.save_scenarios(records)
        self._audit("validation_created", project, f"{record.id} with {len(records)} scenario(s)")
        return record

    def transition(self, validation_id: str, status: str) -> ValidationProject:
        current = self.storage.get(validation_id)
        if current is None: raise KeyError(validation_id)
        target = ValidationStatus(status)
        if target not in _ALLOWED[current.status]: raise ValueError(f"Invalid validation transition {current.status.value} -> {target.value}")
        updated = self.storage.update_status(validation_id, target)
        self._audit("validation_transition", updated.project, f"{validation_id}: {current.status.value} -> {target.value}")
        return updated

    def record_run(self, scenario_id: str, *, workflow_id: str | None = None, execution_loop_id: str | None = None, agents: list[str] | None = None, result: str = "RECORDED", human_rating: float | None = None) -> ValidationRun:
        run = ValidationRun(f"vrun_{secrets.token_hex(8)}", scenario_id, workflow_id, execution_loop_id, agents or [], result, human_rating)
        self.storage.save_run(run)
        self._audit("validation_run_recorded", "validation", f"{run.id} for scenario {scenario_id}")
        return run

    def reference_flows(self) -> dict[str, Any]:
        return {"cases": [{**value, "id": key} for key, value in reference_case_registry().items()], "readOnly": True}

    def _audit(self, action: str, project: str, detail: str) -> None:
        if self.audit: self.audit.record(action=action, path=f"{project}:validation", permission=PermissionLevel.LEVEL_1.value, approved=True, result="success", detail=detail)


def reference_case_registry() -> dict:
    from .reference_cases import REFERENCE_CASES
    return REFERENCE_CASES
