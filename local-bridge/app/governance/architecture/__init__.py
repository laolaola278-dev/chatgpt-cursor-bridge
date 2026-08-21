"""Architecture drift detection (read-only).

Compares current module/dependency reality against the recorded engineering
knowledge graph and emits drift issues. Nothing here modifies code, memory or
workflows; recommendations are advisory only.
"""

from .detector import ArchitectureDriftDetector
from .models import ArchitectureDriftReport, DriftIssue

__all__ = ["ArchitectureDriftDetector", "ArchitectureDriftReport", "DriftIssue"]
