from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class EngineeringReport:
    project: str
    problem: list[dict[str, Any]] = field(default_factory=list)
    analysis: list[dict[str, Any]] = field(default_factory=list)
    decisions: list[dict[str, Any]] = field(default_factory=list)
    execution: list[dict[str, Any]] = field(default_factory=list)
    verification: list[dict[str, Any]] = field(default_factory=list)
    risk: list[dict[str, Any]] = field(default_factory=list)
    learning: list[dict[str, Any]] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))

    def as_dict(self) -> dict[str, Any]:
        return {"project": self.project, "problem": self.problem, "analysis": self.analysis, "decisions": self.decisions, "execution": self.execution, "verification": self.verification, "risk": self.risk, "learning": self.learning, "generatedAt": self.generated_at, "readOnly": True}

    def as_markdown(self) -> str:
        lines = [f"# Engineering Report · {self.project}", ""]
        sections = [("Problem", self.problem), ("Analysis", self.analysis), ("Decisions", self.decisions), ("Execution", self.execution), ("Verification", self.verification), ("Risk", self.risk), ("Learning", self.learning)]
        for title, items in sections:
            lines.append(f"## {title}")
            if not items:
                lines.append("- (none)")
            for item in items:
                lines.append(f"- {item.get('title', item.get('id', str(item)))}")
            lines.append("")
        return "\n".join(lines)
