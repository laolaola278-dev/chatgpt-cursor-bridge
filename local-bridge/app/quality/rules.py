"""Small deterministic quality rules; no external tools are invoked."""

from __future__ import annotations


def file_penalty(count: int) -> int: return max(0, min(30, max(0, count - 5) * 3))
def risk_penalty(risk: str) -> int: return {"low": 0, "medium": 10, "high": 25, "critical": 40}.get(risk.lower(), 20)
