from __future__ import annotations

import secrets
from typing import Any

from app.audit.logger import AuditLogger
from app.security.permissions import PermissionLevel

from .models import DemoScenario

DEMO_FLOW = [
    "ISSUE",
    "AGENT_ANALYSIS",
    "PROPOSAL",
    "APPROVAL",
    "EXECUTION",
    "VERIFICATION",
    "REPORT",
]

CATALOG: dict[str, dict[str, str]] = {
    "bug_fix_demo": {"name": "Bug Fix Demo", "issue": "Authentication failures observed after token rotation"},
    "feature_demo": {"name": "Feature Demo", "issue": "Add exportable engineering reports for stakeholders"},
    "recovery_demo": {"name": "Failure Recovery Demo", "issue": "Execution loop failed and was rolled back"},
}


class DemoScenarioManager:
    def __init__(self, audit: AuditLogger | None = None) -> None:
        self.audit = audit

    def create(self, name: str, issue: str) -> DemoScenario:
        scenario = DemoScenario(f"demo_{secrets.token_hex(6)}", name, issue, list(DEMO_FLOW))
        if self.audit:
            self.audit.record(action="demo_scenario_created", path=f"demo/{scenario.id}", permission=PermissionLevel.LEVEL_1.value, approved=True, result="success", detail=f"scenario {scenario.id} created; no execution")
        return scenario

    def catalog(self) -> list[dict[str, Any]]:
        return [{**value, "id": key, "stages": DEMO_FLOW, "readOnly": True} for key, value in CATALOG.items()]
