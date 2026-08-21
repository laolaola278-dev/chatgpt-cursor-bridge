"""Organization Engineering Intelligence (Phase 22).

Enterprise-level knowledge graph, cross-project learning, engineering pattern
library, organization health aggregation and the Engineering Command Center.
No module here can execute actions, modify source code or write memory
directly; every user-visible write flows through the ApprovalStore.
"""

from .graph import OrganizationGraphManager
from .health import OrganizationHealthAggregator
from .learning import CrossProjectLearner
from .models import (
    OrgDecision,
    OrgEntity,
    OrgEntityType,
    OrgFailurePattern,
    OrgGraph,
    OrgHealthReport,
    OrgIncident,
    OrgPattern,
    PatternCategory,
    SimilarFailureMatch,
)
from .patterns import EngineeringPatternLibrary
from .storage import OrganizationStorage

__all__ = [
    "OrganizationGraphManager",
    "OrganizationHealthAggregator",
    "CrossProjectLearner",
    "EngineeringPatternLibrary",
    "OrganizationStorage",
    "OrgEntity",
    "OrgEntityType",
    "OrgFailurePattern",
    "OrgGraph",
    "OrgHealthReport",
    "OrgIncident",
    "OrgDecision",
    "OrgPattern",
    "PatternCategory",
    "SimilarFailureMatch",
]
