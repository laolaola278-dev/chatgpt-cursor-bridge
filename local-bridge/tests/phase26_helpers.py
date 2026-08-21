from __future__ import annotations

from pathlib import Path

from app.intelligence.observation import Observation, ObservationStore, ObservationType


def observations(db: Path, project: str = "demo") -> list[Observation]:
    store = ObservationStore(db)
    rows = [
        ("2026-01-01T00:00:00+00:00", ObservationType.CODE_CHANGE, "changed parser", {"file": "src/parser.py", "module": "parser"}, "medium"),
        ("2026-01-02T00:00:00+00:00", ObservationType.TEST_RESULT, "pytest failed regression", {"file": "src/parser.py", "test": "tests/test_parser.py", "status": "failed"}, "high"),
        ("2026-01-03T00:00:00+00:00", ObservationType.BUILD_RESULT, "build failed", {"module": "parser", "status": "failed"}, "high"),
        ("2026-01-04T00:00:00+00:00", ObservationType.DEPENDENCY_CHANGE, "major dependency update", {"dependency": "lib-x", "old_version": "1.0", "new_version": "2.0", "change_type": "updated", "affected_components": ["parser"]}, "high"),
        ("2026-01-05T00:00:00+00:00", ObservationType.PERFORMANCE_EVENT, "latency increased", {"latency": 120, "module": "parser"}, "medium"),
        ("2026-01-06T00:00:00+00:00", ObservationType.ERROR_EVENT, "timeout in parser", {"module": "parser"}, "high"),
    ]
    return [store.record(project_id=project, type=kind, source="test-fixture", summary=summary, metadata=metadata, risk_level=risk, timestamp=timestamp) for timestamp, kind, summary, metadata, risk in rows]
