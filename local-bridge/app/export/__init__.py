from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.audit.logger import AuditLogger
from app.security.permissions import PermissionLevel


class ArtifactExporter:
    """Write read-only engineering artifacts (reports, replays, scenarios)."""

    def __init__(self, root: str | Path, audit: AuditLogger | None = None) -> None:
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True); self.audit = audit

    def export(self, kind: str, project: str, payload: dict[str, Any], markdown: str = "") -> dict[str, Any]:
        artifact_id = f"artifact_{secrets.token_hex(6)}"
        record = {"id": artifact_id, "kind": kind, "project": project, "createdAt": datetime.now(timezone.utc).isoformat(timespec="seconds"), "payload": payload, "markdown": markdown, "readOnly": True}
        path = self.root / f"{artifact_id}.json"
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        if self.audit:
            self.audit.record(action="artifact_exported", path=f"artifacts/{artifact_id}", permission=PermissionLevel.LEVEL_1.value, approved=True, result="success", detail=f"{kind} artifact for {project}")
        return record

    def list(self, project: str | None = None) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for path in sorted(self.root.glob("artifact_*.json")):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):  # pragma: no cover - defensive
                continue
            if project and record.get("project") != project: continue
            records.append(record)
        return records[-100:][::-1]
