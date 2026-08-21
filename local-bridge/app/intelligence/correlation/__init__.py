"""Phase 26 correlation intelligence.

Correlation is temporal association only. The package deliberately never
labels an association as a causal explanation or invokes an action.
"""

from .engine import CorrelationEngine, FailureCorrelationEngine
from .models import CorrelationRelationship, CorrelationResult
from .storage import CorrelationStore

__all__ = [
    "CorrelationEngine",
    "FailureCorrelationEngine",
    "CorrelationRelationship",
    "CorrelationResult",
    "CorrelationStore",
]
